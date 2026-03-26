import vertexai
from vertexai import agent_engines
import logging
import os
from typing import AsyncGenerator

logger = logging.getLogger(__name__)

class ChatService:
    def __init__(self):
        # Default values from user snippet, can be overridden by env vars
        self.project_id = os.getenv("PROJECT_ID", "mb-poc-352009")
        self.location = os.getenv("LOCATION", "us-central1")
        self.resource_id = os.getenv("REASONING_ENGINE_RESOURCE_ID", "projects/1047195478355/locations/us-central1/reasoningEngines/2020571418852327424")
        self._initialized = False

    def _ensure_initialized(self):
        if not self._initialized:
            try:
                logger.info(f"Initializing Vertex AI for project {self.project_id}...")
                vertexai.init(project=self.project_id, location=self.location)
                self._initialized = True
            except Exception as e:
                logger.error(f"Failed to initialize Vertex AI: {e}")
                raise

    async def create_session(self, user_id: str = "test_user") -> dict:
        self._ensure_initialized()
        try:
            logger.info(f"Connecting to Reasoning Engine: {self.resource_id}")
            remote_app = agent_engines.get(self.resource_id)
            
            logger.info(f"Creating session for user: {user_id}")
            # async_create_session returns a session object, expected to have an 'id' or be a dict
            remote_session = await remote_app.async_create_session(user_id=user_id)
            logger.info(f"Session created: {remote_session}")
            
            # Extract session ID safely
            session_id = None
            if isinstance(remote_session, dict):
                session_id = remote_session.get("id") or remote_session.get("name")
            elif hasattr(remote_session, "id"):
                session_id = remote_session.id
            elif hasattr(remote_session, "name"):
                session_id = remote_session.name
            else:
                session_id = str(remote_session)

            return {"session_id": session_id}
            
        except Exception as e:
            logger.error(f"Error creating session: {e}", exc_info=True)
            raise

    async def stream_query(self, session_id: str, message: str, user_id: str = "test_user") -> AsyncGenerator[str, None]:
        self._ensure_initialized()
        try:
            remote_app = agent_engines.get(self.resource_id)
            
            logger.info(f"Streaming query to session {session_id}...")
            async for event in remote_app.async_stream_query(
                user_id=user_id,
                session_id=session_id,
                message=message,
            ):
                # The event structure depends on the reasoning engine output.
                # Assuming it yields chunks of text or objects with 'content'.
                # We will convert to string to be safe for SSE.
                
                # Extract content
                content_obj = None
                if hasattr(event, "content"):
                    content_obj = event.content
                elif isinstance(event, dict) and "content" in event:
                    content_obj = event["content"]
                
                final_text = ""
                
                if content_obj:
                    # Handle dict content
                    if isinstance(content_obj, dict):
                        parts = content_obj.get("parts", [])
                        for part in parts:
                            if "text" in part:
                                final_text += part["text"]
                            elif "function_call" in part or "function_response" in part:
                                # Log but do not stream tool events to user
                                logger.info(f"Skipping tool event: {part.keys()}")
                                
                    # Handle object content (if using google.genai.types)
                    elif hasattr(content_obj, "parts"):
                        for part in content_obj.parts:
                            if hasattr(part, "text"):
                                final_text += part.text
                            elif isinstance(part, dict) and "text" in part:
                                final_text += part["text"]

                if final_text:
                    yield final_text
                else:
                    # Fallback only if strictly necessary and NOT a tool event
                    # We know tool events (function_call/response) yield no text, so we shouldn't emit anything.
                    pass

        except Exception as e:
            logger.error(f"Error streaming query: {e}", exc_info=True)
            yield f"Error: {str(e)}"
