import json
import os
from typing import Any


class SimpleMemory:
    def __init__(self, path: str | None = None):
        self.path = path or os.path.join(os.getcwd(), "apm_memory.json")
        self._load()

    def _load(self):
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                self.store_data = json.load(f)
        except Exception:
            self.store_data = []

    def store(self, item: Any):
        self.store_data.append(item)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self.store_data, f, indent=2)

    def query(self, query_text: str):
        # naive retrieval: return items containing query_text
        return [i for i in self.store_data if query_text in json.dumps(i)]
