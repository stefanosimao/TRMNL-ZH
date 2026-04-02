import time
from typing import Dict, Any, Optional, TypedDict

class CacheEntry(TypedDict):
    data: Any
    timestamp: float
    error: Optional[str]

class GlobalCache:
    def __init__(self):
        self._cache: Dict[str, CacheEntry] = {}

    def get(self, key: str) -> Optional[Any]:
        entry = self._cache.get(key)
        if entry and not entry.get("error"):
            return entry["data"]
        return None

    def get_with_meta(self, key: str) -> Optional[CacheEntry]:
        return self._cache.get(key)

    def set(self, key: str, data: Any, error: Optional[str] = None):
        self._cache[key] = {
            "data": data,
            "timestamp": time.time(),
            "error": error
        }

    def set_error(self, key: str, error: str):
        entry = self._cache.get(key)
        if entry:
            entry["error"] = error
            entry["timestamp"] = time.time()
        else:
            self._cache[key] = {"data": None, "timestamp": time.time(), "error": error}

global_cache = GlobalCache()
