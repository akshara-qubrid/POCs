from typing import Any, Dict, List

from .llm_client import chat_completion, get_response_text
from .state import SharedState
from .utils import extract_json

MAX_ITERATIONS = 10  # prevent infinite tool-call loops


class AgentExecutor:
    def __init__(self, name: str, description: str, state: SharedState, model: str, max_tokens: int = 1024):
        self.name = name
        self.description = description
        self.state = state
        self.model = model
        self.max_tokens = max_tokens

    def _build_messages(self, instruction: str) -> List[Dict[str, str]]:
        system_message = {
            "role": "system",
            "content": (
                f"You are {self.name}. {self.description}\n"
                "Only respond with valid JSON. Do not include markdown, prose, or code fences."
                ' When you need external data, return JSON {"tool": "tool_name", "input": "..."}.'
                ' When finished, return JSON {"final": ... }.'
                f" Available tools:\n{self.state.get_tool_descriptions()}"
            ),
        }
        # Build a properly alternating conversation (user/assistant/user/...)
        # to comply with Qubrid API requirements.
        messages = [system_message]
        alternating = []
        last_role = None
        for msg in self.state.history[-20:]:
            role = msg["role"]
            if role == last_role:
                continue  # skip consecutive same-role messages
            alternating.append({"role": role, "content": msg["content"]})
            last_role = role
        messages.extend(alternating)
        if messages and messages[-1]["role"] == "user":
            messages[-1]["content"] = instruction
        else:
            messages.append({"role": "user", "content": instruction})
        return messages

    def run(self, instruction: str) -> Any:
        for iteration in range(MAX_ITERATIONS):
            messages = self._build_messages(instruction)
            print(f"  [{self.name}] LLM call #{iteration + 1} (model={self.model})")
            response = chat_completion(self.model, messages, max_tokens=self.max_tokens, temperature=0.3)
            text = get_response_text(response)
            self.state.add_message("assistant", text)
            action = extract_json(text)
            if "tool" in action and "input" in action:
                print(f"  [{self.name}] → tool call: {action['tool']}")
                tool_output = self.state.run_tool(action["tool"], action["input"])
                instruction = (
                    f"Tool '{action['tool']}' returned: {tool_output}. "
                    "Continue and provide the final JSON result with key 'final'."
                )
                continue
            if "final" in action:
                return action["final"]
            if isinstance(action, dict):
                return action
            raise ValueError(f"[{self.name}] LLM response did not contain a valid tool or final JSON: {text[:200]}")
        raise RuntimeError(f"[{self.name}] exceeded {MAX_ITERATIONS} iterations without a final response")
