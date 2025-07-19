from db import db
from tools import create_csv_file, scrape_multiple_links, scrape_web_page, create_agent

def seed_tools():
    tools_collection = db.tools
    agents_collection = db.agents
    settings_collection = db.settings

    # Initial tools data
    tools = [
        {"name": scrape_multiple_links.name, "description": scrape_multiple_links.description},
        {"name": scrape_web_page.name, "description": scrape_web_page.description},
        {"name": create_csv_file.name, "description": create_csv_file.description},
        {"name": create_agent.name, "description": create_agent.description}
    ]

    # Upsert each tool
    for tool in tools:
        tools_collection.update_one(
            {"name": tool["name"]},
            {"$set": tool},
            upsert=True
        )

    builder_agent_available_tools = f"\n".join(list(map(lambda x: f"Name: {x['name']}\nDescription: {x['description']}", filter(lambda x: x['name'] != create_agent.name, tools))))

    agents_collection.update_one(
        {"name": "Agent Builder Assistant (system)"},
        {
            "$set": {
                "name": "Agent Builder Assistant (system)",
                "instructions": f"""
                You are a helpful assistant responsible for creating new agents and equipping them with the appropriate tools based on their intended behavior.\nUse the create_agent_tool function to register a new agent by providing the agent's name, a clear description of what the agent should do (its instructions), and a list of tool names it should be allowed to use.\nEnsure the tool names match existing tools in the system, or the agent may be created without proper functionality.\nAvailable Tools:\n{builder_agent_available_tools}"""
                .strip(),
                "tools": list(map(lambda x: x['_id'], db.tools.find({"name": create_agent.name}))),
                "is_editable": False
            }
        },
        upsert=True
    )
    
    agents_collection.update_one(
        {"name": "Web Scraping Assistant (default)"},
        {
            "$set": {
                "name": "Web Scraping Assistant (default)",
                "instructions": """
                You are a helpful assistant that returns insights on data from a webpage.\nUse the scrape_web_page tool to get the content from the page.\nUse the scrape_multiple_links tool to scrape a website and return the content as a zip file.\nUse the create_csv_file too to turn table data from a website to a csv file. Return "could not generate csv" if the tool returns None.
                """.strip(),
                "tools": list(
                    map(lambda x: x['_id'], tools_collection.find(
                        {
                            "name": {"$in": list(map(lambda x: x['name'], tools))}
                        }
                    ))
                ),
                "is_editable": False
            }
        },
        upsert=True
    )

    if not settings_collection.find_one({}):
        settings_collection.update_one({}, {
            "$set": {
                "profile_settings": {
                    "username": "testaccount",
                    "email": "test@email.com"
                },
                "log_settings": {
                    "retention_period_days": 7,
                    "auto_delete_expired_logs": True
                },
                "model_settings": {
                    "model_name": "gpt-4.1",
                    "temperature": 0,
                    "max_tokens": 2000
                }
            }
        }, upsert=True)

    # CREATE INDEXES FOR BETTER PERFORMANCE
    try:
        # Users collection indexes
        db.users.create_index("email", unique=True)
        db.users.create_index("verification_token")
        db.users.create_index("password_reset_token")
        
        # Activity logs indexes - ENHANCED
        db.activity_logs.create_index([("user_id", 1), ("timestamp", -1)])
        db.activity_logs.create_index([("user_id", 1), ("action", 1)])
        db.activity_logs.create_index("timestamp", expireAfterSeconds=90*24*60*60)  # Auto-delete after 90 days
        db.activity_logs.create_index("action")  # For filtering by action type
        
        # Request history index
        db.request_history.create_index([("user_id", 1), ("session_id", 1)])
        
        print("Database indexes created successfully!")
    except Exception as e:
        print(f"Index creation warning: {e}")
        
    print("Tools seeded successfully!")
