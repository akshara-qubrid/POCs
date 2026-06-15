import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List


@dataclass
class Tool:
    name: str
    description: str
    func: Callable[[str], Any]


@dataclass
class SharedState:
    memory_path: str = "memory_governance_memory.json"
    history: List[Dict[str, Any]] = field(default_factory=list)
    tools: Dict[str, Tool] = field(default_factory=dict)
    memory_store: List[Dict[str, Any]] = field(default_factory=list)
    tool_log: List[Dict[str, Any]] = field(default_factory=list)

    def __post_init__(self):
        self.load_memory()

    def add_message(self, role: str, content: str, metadata: Dict[str, Any] = None) -> None:
        self.history.append({"role": role, "content": content, "metadata": metadata or {}})

    def register_tool(self, tool: Tool) -> None:
        self.tools[tool.name] = tool

    def get_tool_descriptions(self) -> str:
        if not self.tools:
            return "No tools registered."
        return "\n".join([f"{tool.name}: {tool.description}" for tool in self.tools.values()])

    def _normalize_tool_key(self, tool_name: str) -> str:
        normalized = []
        for ch in tool_name.lower():
            normalized.append(ch if ch.isalnum() else "_")
        return "".join(normalized).strip("_")

    def _find_tool_key(self, requested_tool_name: str) -> str | None:
        normalized_requested = self._normalize_tool_key(requested_tool_name)
        normalized_tools = {self._normalize_tool_key(name): name for name in self.tools}
        if normalized_requested in normalized_tools:
            return normalized_tools[normalized_requested]
        candidates = [name for name in self.tools if normalized_requested in self._normalize_tool_key(name) or self._normalize_tool_key(name) in normalized_requested]
        if len(candidates) == 1:
            return candidates[0]
        if "swot" in normalized_requested:
            for name, tool in self.tools.items():
                if "competit" in name.lower() or "competit" in tool.description.lower():
                    return name
        return None

    def run_tool(self, tool_name: str, tool_input: str) -> Any:
        resolved_tool = self._find_tool_key(tool_name)
        if not resolved_tool:
            raise KeyError(f"Tool '{tool_name}' not registered")
        result = self.tools[resolved_tool].func(tool_input)
        self.tool_log.append({"tool": resolved_tool, "input": tool_input, "output": result})
        self.add_message("assistant", f"{resolved_tool} output: {result}")
        return result

    def add_memory(self, record: Dict[str, Any]) -> None:
        self.memory_store.append(record)
        self.save_memory()

    def save_memory(self) -> None:
        if self.memory_path == ":memory:":
            return  # in-memory only, no persistence
        path = Path(self.memory_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.memory_store, f, indent=2)

    def load_memory(self) -> None:
        if self.memory_path == ":memory:":
            self.memory_store = []
            return
        path = Path(self.memory_path)
        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    self.memory_store = json.load(f)
            except Exception:
                self.memory_store = []
        else:
            self.memory_store = []

    def query_memory(self, query_text: str) -> List[Dict[str, Any]]:
        query_lower = query_text.lower()
        return [item for item in self.memory_store if query_lower in json.dumps(item).lower()]
