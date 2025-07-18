from bson import ObjectId
from fastapi.exceptions import RequestValidationError
from typing_extensions import List, Optional
from fastapi import FastAPI, HTTPException, Response
from openai import OpenAI
from dotenv import load_dotenv
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from agents import Agent, Runner, handoff
from agents.tool import WebSearchTool
from seed import seed_tools
from tools import scrape_multiple_links, scrape_web_page, create_csv_file, create_agent as create_agent_tool
from json_parser import parse_mongo_documents, parse_mongo_document
from utils import build_agent
import os
from db import db
from openai.types.responses.easy_input_message_param import EasyInputMessageParam
from uuid import uuid4


load_dotenv()

# Get API key from environment variable
api_key = os.getenv("OPENAI_API_KEY")

if not api_key:
    raise ValueError("OPENAI_API_KEY environment variable is not set")

client = OpenAI(api_key=api_key)
app = FastAPI()

# seed tools to db
seed_tools()


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)

# Mount the output directory for static file serving
app.mount("/output", StaticFiles(directory="output"), name="output")

class MessageRequest(BaseModel):
    content: str
    agent_id: Optional[str]
    session_id: Optional[str]


class ProfileSettings(BaseModel):
    email: str
    username: str

class LogSettings(BaseModel):
    retention_period_days: int
    auto_delete_expired_logs: bool

class ModelSettings(BaseModel):
    model_name: str
    temperature: float
    max_tokens: int

class SettingsRequest(BaseModel):
    profile_settings: Optional[ProfileSettings] = None
    log_settings: Optional[LogSettings] = None
    model_settings: Optional[ModelSettings] = None


# class PromptMessageRequest(BaseModel):
#     repeat_history_id: Optional[str]
#     message: Optional[MessageRequest]
class CreateAgentRequest(BaseModel):
    name: str
    instructions: str
    tools: List[str]
    icon_name: Optional[str]



@app.get("/")
async def hello_world():
    return {
        'message': 'Welcome to FastAPI!',
        'status': 'success'
    }


@app.post("/message")
async def send_message(request: MessageRequest):
    session_id = request.session_id or str(uuid4())

    # save user's message request
    db.request_history.insert_one({
        "content": request.content,
        "agent_id": request.agent_id,
        "session_id": session_id,
        "role": "user"
    })

    session_history = list(
        map(
            lambda x: EasyInputMessageParam(
                content=x['content'],
                status='completed',
                role=x['role']
            ),
            db.request_history.find(
                filter={"session_id": session_id},
                # sort={"_id": -1},
                limit=20
            )
        )
    )

    translator_agent = Agent(name="translator", instructions="""
    You will receive a block of text in either English or Portuguese.
    Detect the language of the input and always respond in the *same language* as the input.
    Your output must match the input language exactly—if the input is in Portuguese, respond entirely in Portuguese; if it's in English, respond entirely in English.
    Do not mix languages in your output.
    """)

    
    if not request.agent_id:
        response = await Runner.run(translator_agent, session_history)

        # completion = client.chat.completions.create(
        #     model="gpt-4.1",
        #     messages=[
        #         {
        #             "role": "user",
        #             "content": request.content
        #         }
        #     ]
        # )

        # save message request for agent/bot
        db.request_history.insert_one({
            "content": response.final_output,
            "agent_id": request.agent_id,
            "session_id": session_id,
            "role": "assistant"
        })

        return {"message": response.final_output, "session_id": session_id}
    
    else:
        # build agent
        # run agent
        agent = build_agent(agent_id=request.agent_id)
        agent.handoffs.append(handoff(agent=translator_agent))
        result = await Runner.run(agent, session_history)
        # save message request for agent/bot
        db.request_history.insert_one({
            "content": result.final_output,
            "agent_id": request.agent_id,
            "session_id": session_id,
            "role": "assistant"
        })
        return {"message": result.final_output, "session_id": session_id}


@app.post("/agents/message")
async def run_agent_message(request: MessageRequest):
    agent = Agent(
        name="Web Scraping Assistant (default)", 
        instructions="""
        You are a helpful assistant that returns insights on data from a webpage. 
        Use the scrape_web_page tool to get the content from the page.
        Use the scrape_multiple_links tool to scrape a website and return the content as a zip file.
        Use the create_csv_file too to turn table data from a website to a csv file. Return "could not generate csv" if the tool returns None.
        """,        
        tools=[scrape_web_page, scrape_multiple_links, create_csv_file],
    )

    result = await Runner.run(agent, request.content)
    return result.final_output


@app.get("/tools")
async def list_available_tools():
    tools = list(db.tools.find({"name": {"$ne": create_agent_tool.name}}))
    return parse_mongo_documents(tools)


@app.get("/agents")
async def list_available_agents():
    agents = list(db.agents.find({}))
    # parsed_agents = parse_mongo_documents(agents)
    
    # Populate tools data for each agent
    for agent in agents:
        if "tools" in agent:
            tool_ids = agent["tools"]
            tools = list(db.tools.find({"_id": {"$in": tool_ids}}))
            agent["tools"] = parse_mongo_documents(tools)
    
    return parse_mongo_documents(agents)


@app.post("/agents")
async def create_agent(request: CreateAgentRequest):
    tools = list(db.tools.find({"_id": {"$in": list(map(lambda x: ObjectId(x), request.tools))}}))

    agent = db.agents.insert_one({
        "name": request.name, "instructions": request.instructions,
        "tools": list(map(lambda x: x.get("_id"), tools)),
        "is_editable": True,
        "icon_name": request.icon_name
    })

    return {"message": "created agent", "agent_id": str(agent.inserted_id)}

@app.get('/agents/{agent_id}')
def view_agent_details(agent_id: str):
    if not ObjectId.is_valid(agent_id):
        raise HTTPException(status_code=400, detail="Invalid agent id")
    
    agent = db.agents.find_one({"_id": ObjectId(agent_id)})
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    # Example: You may want to customize these fields based on your schema
    # For demonstration, we use static/dummy values for fields not in db

    tools = list(db.tools.find({"_id": {"$in": agent.get("tools", [])}})) or []

    output = {
        "_id": str(agent.get("_id")),
        "name": agent.get("name"),
        "instructions": agent.get("instructions"),
        "role": agent.get("role", "Research and Analysis"),
        "description": agent.get(
            "description",
            "An AI agent specialized in conducting research and providing detailed analysis on various topics."
        ),
        "tools": [
            tool.get("name", "Unknown Tool")
            for tool in tools
        ],
        "icon_name": agent.get("icon_name", "Binx Bond"),
        "tool_data": tools,
        "emoji": agent.get("emoji", "🔍"),
        "stats": {
            "totalConversations": agent.get("totalConversations", 150),
            "successRate": agent.get("successRate", "95%"),
            "avgResponseTime": agent.get("avgResponseTime", "2.5s")
        }
    }

    return parse_mongo_document(output)


@app.get('/prompt-history')
async def get_conversation_history():
    # Get distinct messages based on content and agent_id to prevent duplicates
    history = list(db.request_history.aggregate([
        { "$match": { "role": "user" } },
        {
            "$group": {
                "_id": {
                    "content": "$content",
                    "agent_id": "$agent_id",
                },
                "doc": {"$first": "$$ROOT"}
            }
        },
        {
            "$replaceRoot": {"newRoot": "$doc"}
        },
        { "$sort": { "_id": -1 } },
        { "$limit": 5 }
    ]))

    return parse_mongo_documents(history)


@app.put('/agents/{agent_id}')
async def update_agent(agent_id: str, request: CreateAgentRequest):
    try:
        if not ObjectId.is_valid(agent_id):
            raise HTTPException(status_code=400, detail="Invalid agent id")
        
        # Check if agent exists
        agent = db.agents.find_one({"_id": ObjectId(agent_id)})
        if not agent:
            raise HTTPException(status_code=400, detail="Agent not found")

        # Check if agent is editable
        if not agent.get("is_editable", False):
            raise HTTPException(status_code=403, detail="This agent cannot be edited")

        # Validate tools
        try:
            tools = list(db.tools.find({"_id": {"$in": list(map(lambda x: ObjectId(x), request.tools))}}))
            if len(tools) != len(request.tools):
                return {"error": "One or more tools not found"}, 400
        except Exception as e:
            return {"error": "Invalid tool IDs provided"}, 400

        # Update agent
        db.agents.update_one(
            {"_id": ObjectId(agent_id)},
            {
                "$set": {
                    "name": request.name,
                    "instructions": request.instructions,
                    "tools": list(map(lambda x: x.get("_id"), tools)),
                    "icon_name": request.icon_name
                }
            }
        )

        return {"message": "Agent updated successfully", "agent_id": agent_id}

    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=f"Failed to update agent: {str(e)}")


@app.delete('/agents/{agent_id}')
async def delete_agent(agent_id: str):
    try:
        if not ObjectId.is_valid(agent_id):
            raise HTTPException(status_code=400, detail="Invalid agent id")
        
        # Check if agent exists
        agent = db.agents.find_one({"_id": ObjectId(agent_id)})
        if not agent:
            raise HTTPException(status_code=404, detail="Agent not found")

        # Check if agent is editable
        if not agent.get("is_editable", False):
            raise HTTPException(status_code=403, detail="This agent cannot be deleted")

        # Delete agent
        db.agents.delete_one({"_id": ObjectId(agent_id)})
        
        return {"message": "Agent deleted successfully"}

    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        
        raise HTTPException(status_code=500, detail=f"Failed to delete agent: {str(e)}")


@app.get("/settings")
async def view_settings():
    settings = db.settings.find_one({})
    return parse_mongo_document(settings)


@app.patch("/settings")
async def save_settings(request: SettingsRequest):
    data = {}
    if request.model_settings:
        data["model_settings"] = request.model_settings.model_dump(mode="python")

    if request.log_settings:
        data["log_settings"] = request.log_settings.model_dump(mode="python")

    if request.profile_settings:
        data["profile_settings"] = request.profile_settings.model_dump(mode="python")

    if not len(data.keys()):
        raise HTTPException(status_code=400, detail="provide a setting to update")

    db.settings.update_one({}, {"$set": data}, upsert=True)
    settings_config = db.settings.find_one({})
    return parse_mongo_document(settings_config)


@app.get("/log-exports")
async def export_logs(export_type: str = "txt"):
    if export_type == "txt":
        try:
            with open("tools.log", "r") as log_file:
                log_content = log_file.read()
                
            return Response(
                content=log_content,
                media_type="text/plain",
                headers={
                    "Content-Disposition": "attachment; filename=tools.log"
                }
            )
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="Log file not found or has been deleted")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error reading log file: {str(e)}")
        
    else:
        raise HTTPException(status_code=400, detail="export_type not available")

if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000) 