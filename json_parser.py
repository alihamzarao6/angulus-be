from bson import ObjectId
from json import JSONEncoder
from typing import Any, Dict, List

class MongoJSONEncoder(JSONEncoder):
    def default(self, obj: Any) -> Any:
        if isinstance(obj, ObjectId):
            return str(obj)
        return super().default(obj)

def parse_mongo_document(document: Dict) -> Dict:
    """Convert MongoDB document to JSON serializable format"""
    if document is None:
        return None
    
    if isinstance(document, dict):
        return {k: parse_mongo_document(v) for k, v in document.items()}
    elif isinstance(document, list):
        return [parse_mongo_document(item) for item in document]
    elif isinstance(document, ObjectId):
        return str(document)
    return document

def parse_mongo_documents(documents: List[Dict]) -> List[Dict]:
    """Convert a list of MongoDB documents to JSON serializable format"""
    return [parse_mongo_document(doc) for doc in documents] 