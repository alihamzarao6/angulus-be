from pymongo import MongoClient
from pymongo.errors import ConnectionFailure
import os
from dotenv import load_dotenv



# Load environment variables
load_dotenv()

# MongoDB connection configuration
MONGO_URI = os.getenv('MONGO_URI', 'mongodb://localhost:27017')
DB_NAME = os.getenv('DB_NAME', 'angulus')

try:
    # Create MongoDB client
    client = MongoClient(MONGO_URI)
    
    # Test the connection
    client.admin.command('ping')
    print("Successfully connected to MongoDB!")
    
    # Get database instance
    db = client[DB_NAME]
    
except ConnectionFailure as e:
    print(f"Could not connect to MongoDB: {e}")
    raise
