import json
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

import redis.asyncio as redis
from app.core.config import get_settings

logger = logging.getLogger(__name__)

# In-memory fallback storage when Redis is unavailable
_in_memory_storage: Dict[str, Dict[str, Any]] = {}


class ConversationContext:
    """Manages conversation context for users, including pending clarifications."""
    
    def __init__(self):
        self.settings = get_settings()
        self.redis_url = self.settings.redis_url
        self._redis: Optional[redis.Redis] = None
        self.ttl = 300  # 5 minutes TTL for context
        self._use_redis = True
    
    async def _get_redis(self) -> Optional[redis.Redis]:
        """Get or create Redis connection."""
        if not self._use_redis:
            return None
        if self._redis is None:
            try:
                self._redis = redis.from_url(self.redis_url, decode_responses=True)
                # Test connection
                await self._redis.ping()
            except Exception as e:
                logger.warning("Redis connection failed: %s. Using in-memory fallback.", e)
                self._use_redis = False
                self._redis = None
        return self._redis
    
    async def _get_context_key(self, user_id: str) -> str:
        """Get Redis key for user context."""
        return f"assistant:context:{user_id}"
    
    async def get_context(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get conversation context for a user."""
        try:
            r = await self._get_redis()
            if r is not None:
                key = await self._get_context_key(user_id)
                data = await r.get(key)
                if data:
                    return json.loads(data)
                return None
            else:
                # Use in-memory storage
                key = await self._get_context_key(user_id)
                if key in _in_memory_storage:
                    # Check TTL
                    stored = _in_memory_storage[key]
                    created_at = datetime.fromisoformat(stored.get("created_at", datetime.utcnow().isoformat()))
                    if datetime.utcnow() - created_at < timedelta(seconds=self.ttl):
                        return stored
                    else:
                        # Expired, remove it
                        del _in_memory_storage[key]
                return None
        except Exception as e:
            logger.error("Error getting context for user %s: %s", user_id, e)
            return None
    
    async def set_pending_clarification(
        self,
        user_id: str,
        original_text: str,
        parsed_title: str,
        parsed_description: str,
        clarification_type: str,
        clarification_question: str,
        intent: str = "create_task",
        partial_data: Optional[Dict[str, Any]] = None
    ) -> None:
        """Store pending clarification context for a user."""
        try:
            r = await self._get_redis()
            key = await self._get_context_key(user_id)
            context = {
                "pending_clarification": True,
                "intent": intent,
                "original_text": original_text,
                "parsed_title": parsed_title,
                "parsed_description": parsed_description,
                "clarification_type": clarification_type,
                "clarification_question": clarification_question,
                "partial_data": partial_data or {},
                "created_at": datetime.utcnow().isoformat(),
                "ttl": self.ttl
            }
            if r is not None:
                await r.setex(key, self.ttl, json.dumps(context, default=str))
            else:
                # Use in-memory storage
                _in_memory_storage[key] = context
            logger.info("Stored pending clarification for user %s", user_id)
        except Exception as e:
            logger.error("Error storing context for user %s: %s", user_id, e)
    
    async def consume_clarification(
        self,
        user_id: str,
        clarification_response: str
    ) -> Optional[Dict[str, Any]]:
        """Get and remove pending clarification context, returning combined task info."""
        try:
            r = await self._get_redis()
            key = await self._get_context_key(user_id)
            
            if r is not None:
                data = await r.get(key)
                if not data:
                    return None
                context = json.loads(data)
                # Delete the context
                await r.delete(key)
            else:
                # Use in-memory storage
                if key not in _in_memory_storage:
                    return None
                context = _in_memory_storage[key]
                # Delete the context
                del _in_memory_storage[key]
            
            if not context.get("pending_clarification"):
                return None
            
            # Combine original info with clarification
            combined = {
                "intent": context["intent"],
                "original_text": context["original_text"],
                "parsed_title": context["parsed_title"],
                "parsed_description": context["parsed_description"],
                "clarification_response": clarification_response,
                "clarification_type": context["clarification_type"],
                "partial_data": context.get("partial_data", {})
            }
            
            logger.info("Consumed pending clarification for user %s", user_id)
            return combined
        except Exception as e:
            logger.error("Error consuming context for user %s: %s", user_id, e)
            return None
    
    async def clear_context(self, user_id: str) -> None:
        """Clear all context for a user."""
        try:
            r = await self._get_redis()
            key = await self._get_context_key(user_id)
            if r is not None:
                await r.delete(key)
            else:
                # Use in-memory storage
                if key in _in_memory_storage:
                    del _in_memory_storage[key]
            logger.info("Cleared context for user %s", user_id)
        except Exception as e:
            logger.error("Error clearing context for user %s: %s", user_id, e)
    
    async def close(self) -> None:
        """Close Redis connection."""
        if self._redis:
            await self._redis.close()
            self._redis = None

    async def store_message_context(
        self,
        user_id: str,
        message: str,
        parsed_data: Dict[str, Any]
    ) -> None:
        """Store message context for multi-message task creation."""
        try:
            r = await self._get_redis()
            key = f"assistant:messages:{user_id}"
            
            # Get existing messages
            if r is not None:
                data = await r.get(key)
                messages = json.loads(data) if data else []
            else:
                messages = _in_memory_storage.get(key, [])
            
            # Add new message
            messages.append({
                "text": message,
                "parsed": parsed_data,
                "timestamp": datetime.utcnow().isoformat()
            })
            
            # Keep only last 10 messages
            messages = messages[-10:]
            
            if r is not None:
                await r.setex(key, 3600, json.dumps(messages, default=str))  # 1 hour TTL
            else:
                _in_memory_storage[key] = messages
                
            logger.info("Stored message context for user %s", user_id)
        except Exception as e:
            logger.error("Error storing message context for user %s: %s", user_id, e)

    async def get_message_context(
        self,
        user_id: str
    ) -> list[Dict[str, Any]]:
        """Get stored message context for a user."""
        try:
            r = await self._get_redis()
            key = f"assistant:messages:{user_id}"
            
            if r is not None:
                data = await r.get(key)
                return json.loads(data) if data else []
            else:
                return _in_memory_storage.get(key, [])
        except Exception as e:
            logger.error("Error getting message context for user %s: %s", user_id, e)
            return []

    async def clear_message_context(self, user_id: str) -> None:
        """Clear message context for a user."""
        try:
            r = await self._get_redis()
            key = f"assistant:messages:{user_id}"
            if r is not None:
                await r.delete(key)
            else:
                if key in _in_memory_storage:
                    del _in_memory_storage[key]
        except Exception as e:
            logger.error("Error clearing message context for user %s: %s", user_id, e)
