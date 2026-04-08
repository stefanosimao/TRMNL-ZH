"""
Global in-memory cache for storing data fetched by background jobs.
"""
import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Dict, Any, Optional, TypedDict

logger = logging.getLogger(__name__)

_DEBUG_DIR = os.path.join("generated", "debug")
_DEBUG_KEYS = {"switchbot", "meteo", "alerts", "summary"}

class CacheEntry(TypedDict):
    """Represents a single entry in the global cache."""
    data: Any
    timestamp: float
    error: Optional[str]

class GlobalCache:
    """
    A simple in-memory cache to share state between background scheduled jobs
    and the FastAPI request handlers.
    """
    def __init__(self):
        """Initializes the cache dictionary."""
        self._cache: Dict[str, CacheEntry] = {}

    def get(self, key: str) -> Optional[Any]:
        """
        Retrieves valid data for a given key.
        
        Args:
            key: The identifier for the cached data.
            
        Returns:
            The cached data if present and no error occurred, else None.
        """
        entry = self._cache.get(key)
        if entry and not entry.get("error"):
            return entry["data"]
        return None

    def get_with_meta(self, key: str) -> Optional[CacheEntry]:
        """
        Retrieves the raw CacheEntry including timestamp and error metadata.
        
        Args:
            key: The identifier for the cached data.
            
        Returns:
            The CacheEntry dictionary, or None if not found.
        """
        return self._cache.get(key)

    def set(self, key: str, data: Any, error: Optional[str] = None):
        """
        Stores data in the cache with the current timestamp.

        Args:
            key: The identifier for the cached data.
            data: The payload to cache.
            error: Optional error message if the fetch failed.
        """
        self._cache[key] = {
            "data": data,
            "timestamp": time.time(),
            "error": error
        }
        if key in _DEBUG_KEYS:
            self._write_debug_file(key, data)

    def _write_debug_file(self, key: str, data: Any):
        """Write cached data to a JSON debug file for easy inspection."""
        try:
            os.makedirs(_DEBUG_DIR, exist_ok=True)
            payload: dict = {
                "data": data,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            if key == "summary" and isinstance(data, str):
                from .services.gemini import _count_lines
                payload["chars"] = len(data)
                payload["wrapped_lines"] = _count_lines(data)
            path = os.path.join(_DEBUG_DIR, f"{key}.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2, default=str, ensure_ascii=False)
        except Exception as e:
            logger.warning(f"Failed to write debug file for '{key}': {e}")

    def set_error(self, key: str, error: str):
        """
        Marks an existing cache entry with an error and updates its timestamp.
        If the entry doesn't exist, initializes it with None data.
        
        Args:
            key: The identifier for the cached data.
            error: The error message to record.
        """
        entry = self._cache.get(key)
        if entry:
            entry["error"] = error
            entry["timestamp"] = time.time()
        else:
            self._cache[key] = {"data": None, "timestamp": time.time(), "error": error}

global_cache = GlobalCache()
