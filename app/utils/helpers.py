"""Utility functions"""
import json
import logging

logger = logging.getLogger(__name__)


def serialize_json(obj):
    """Serialize object to JSON-compatible format"""
    try:
        return json.dumps(obj)
    except TypeError:
        return str(obj)


def deserialize_json(data: str):
    """Deserialize JSON string"""
    try:
        return json.loads(data)
    except json.JSONDecodeError:
        logger.warning(f"Failed to deserialize: {data}")
        return {}


def truncate_text(text: str, max_length: int = 1000) -> str:
    """Truncate text to max length"""
    if len(text) <= max_length:
        return text
    return text[:max_length - 3] + "..."
