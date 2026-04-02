import time
from typing import Dict, Any, Optional

class Cache:
    def __init__(self, ttl: int):
        self.ttl = ttl
        self._data: Dict[str, Dict[str, Any]] = {}

    def get(self, key: str) -> Optional[Any]:
        entry = self._data.get(key)
        if entry and time.time() - entry["timestamp"] < self.ttl:
            return entry["data"]
        return None

    def set(self, key: str, data: Any):
        self._data[key] = {
            "data": data,
            "timestamp": time.time()
        }

station_cache = Cache(ttl=300)
