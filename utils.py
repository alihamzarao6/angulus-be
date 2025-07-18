from agents import Agent
from bson import ObjectId
from db import db
from tools import scrape_web_page, scrape_multiple_links, create_csv_file, create_agent
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Map tool names to their function implementations
TOOL_MAP = {
    "scrape_web_page": scrape_web_page,
    "scrape_multiple_links": scrape_multiple_links,
    "create_csv_file": create_csv_file,
    "create_agent": create_agent
}

def build_agent(agent_id: str) -> Agent:
    """
    Build an agent using data from the database and initialize it with the Agent SDK.
    
    Args:
        agent_name (str): The name of the agent to build
        
    Returns:
        Agent: An initialized Agent instance
        
    Raises:
        ValueError: If the agent is not found in the database
    """
    # Get agent data from database
    agent_data = db.agents.find_one({"_id": ObjectId(agent_id)})
    if not agent_data:
        raise ValueError(f"Agent '{agent_id}' not found in database")
    
    # Get tool IDs from the database and map them to actual function tools
    tool_ids = agent_data.get('tools', [])
    tools = []
    
    # Get tool names from database using tool IDs
    for tool_id in tool_ids:
        tool_data = db.tools.find_one({"_id": tool_id})
        if tool_data and tool_data["name"] in TOOL_MAP:
            tools.append(TOOL_MAP[tool_data["name"]])
    
    try:
        # Initialize the agent with data from database
        agent = Agent(
            name=agent_data.get('name'),
            instructions=agent_data['instructions'],
            tools=tools
        )
        
        return agent
        
    except Exception as e:
        raise Exception(f"Failed to create agent: {str(e)}")
