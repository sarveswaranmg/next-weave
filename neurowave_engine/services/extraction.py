"""Memory extraction service"""
import json
import logging
from typing import List, Optional
from openai import AsyncOpenAI, OpenAI
from neurowave_engine.schemas.memory import ExtractedMemory
from neurowave_engine.db.models import MemoryTypeEnum
from neurowave_engine.core.config import settings

logger = logging.getLogger(__name__)

EXTRACTION_PROMPT = """Analyze the following user message and extract any durable memories that should be stored.

Return ONLY a valid JSON array with extracted memories. Each memory should have:
- type: one of ["episodic", "semantic", "identity", "procedural"]
- content: the memory content (string)
- summary: brief summary (string)
- importance_score: 0.0 to 1.0 (float)

Rules:
- Extract ONLY meaningful, durable information
- Ignore greetings, pleasantries, and small talk
- For semantic memories: extract facts about user preferences
- For identity memories: extract behavioral patterns and goals
- For procedural memories: extract how the AI should behave
- For episodic memories: extract significant events or topics discussed
- Set importance_score based on likely future usefulness (0.05 for trivial, 0.95 for critical)

Return empty array [] if no meaningful memories should be extracted.

User message:
{message}

JSON Response:
"""


class MemoryExtractionService:
    """Service for extracting memories from conversations"""

    def __init__(self):
        self.client = OpenAI(api_key=settings.openai_api_key)
        self.async_client = AsyncOpenAI(api_key=settings.openai_api_key)

    def extract_memories(self, message: str) -> List[ExtractedMemory]:
        """
        Extract memories from a user message synchronously.

        Args:
            message: User message text

        Returns:
            List of extracted memories
        """
        try:
            response = self.client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {
                        "role": "user",
                        "content": EXTRACTION_PROMPT.format(message=message),
                    }
                ],
                temperature=0.3,
                max_tokens=1000,
            )

            response_text = response.choices[0].message.content
            extracted_data = json.loads(response_text)

            if not isinstance(extracted_data, list):
                logger.warning("Extraction response is not a list")
                return []

            extracted_memories = []
            for item in extracted_data:
                try:
                    extracted_memories.append(
                        ExtractedMemory(
                            memory_type=MemoryTypeEnum(item["type"]),
                            content=item["content"],
                            summary=item.get("summary", ""),
                            importance_score=float(item.get("importance_score", 0.5)),
                            metadata={"extraction_method": "llm"},
                        )
                    )
                except (KeyError, ValueError) as e:
                    logger.warning(f"Failed to parse extracted memory: {e}")
                    continue

            return extracted_memories

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse extraction response: {e}")
            return []
        except Exception as e:
            logger.error(f"Memory extraction error: {e}")
            return []

    async def extract_memories_async(self, message: str) -> List[ExtractedMemory]:
        """
        Extract memories from a user message asynchronously.

        Args:
            message: User message text

        Returns:
            List of extracted memories
        """
        try:
            response = await self.async_client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {
                        "role": "user",
                        "content": EXTRACTION_PROMPT.format(message=message),
                    }
                ],
                temperature=0.3,
                max_tokens=1000,
            )

            response_text = response.choices[0].message.content
            extracted_data = json.loads(response_text)

            if not isinstance(extracted_data, list):
                logger.warning("Extraction response is not a list")
                return []

            extracted_memories = []
            for item in extracted_data:
                try:
                    extracted_memories.append(
                        ExtractedMemory(
                            memory_type=MemoryTypeEnum(item["type"]),
                            content=item["content"],
                            summary=item.get("summary", ""),
                            importance_score=float(item.get("importance_score", 0.5)),
                            metadata={"extraction_method": "llm"},
                        )
                    )
                except (KeyError, ValueError) as e:
                    logger.warning(f"Failed to parse extracted memory: {e}")
                    continue

            return extracted_memories

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse extraction response: {e}")
            return []
        except Exception as e:
            logger.error(f"Memory extraction error: {e}")
            return []


# Singleton instance
memory_extraction_service = MemoryExtractionService()
