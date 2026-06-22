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
        # Local conversation history owned by this executor — guaranteed alternating.
        self._local_messages: List[Dict[str, str]] = []

    @property
    def _system_message(self) -> Dict[str, str]:
        return {
            "role": "system",
            "content": (
                f"You are {self.name}. {self.description}\n"
                "Only respond with valid JSON. Do not include markdown, prose, or code fences."
                ' When you need external data, return JSON {"tool": "tool_name", "input": "..."}.'
                ' When finished, return JSON {"final": ... }.'
                f" Available tools:\n{self.state.get_tool_descriptions()}"
            ),
        }

    def _append_user(self, content: str) -> None:
        """Append a user turn, merging with the previous user turn if needed."""
        if self._local_messages and self._local_messages[-1]["role"] == "user":
            # Merge to avoid consecutive user messages
            self._local_messages[-1]["content"] += "\n" + content
        else:
            self._local_messages.append({"role": "user", "content": content})

    def _append_assistant(self, content: str) -> None:
        """Append an assistant turn, merging with the previous assistant turn if needed."""
        if self._local_messages and self._local_messages[-1]["role"] == "assistant":
            # Merge to avoid consecutive assistant messages
            self._local_messages[-1]["content"] += "\n" + content
        else:
            self._local_messages.append({"role": "assistant", "content": content})

    def _build_messages(self) -> List[Dict[str, str]]:
        """Return [system] + local conversation, which is always properly alternating."""
        return [self._system_message] + self._local_messages

    def run(self, instruction: str) -> Any:
        # Reset local history for each new run so agents don't bleed state.
        self._local_messages = []
        self._append_user(instruction)

        for iteration in range(MAX_ITERATIONS):
            messages = self._build_messages()
            print(f"  [{self.name}] LLM call #{iteration + 1} (model={self.model})")
            response = chat_completion(
                self.model, messages, max_tokens=self.max_tokens, temperature=0.3,
                run_name=f"{self.name} call #{iteration + 1}",
            )
            text = get_response_text(response)
            self._append_assistant(text)
            # Also record in shared state for cross-agent visibility
            self.state.add_message("assistant", text)

            action = extract_json(text)
            if "tool" in action and "input" in action:
                print(f"  [{self.name}] → tool call: {action['tool']}")
                tool_output = self.state.run_tool(action["tool"], action["input"])
                # Add tool result as a user turn so the conversation stays alternating
                tool_msg = (
                    f"Tool '{action['tool']}' returned: {tool_output}. "
                    "Continue and provide the final JSON result with key 'final'."
                )
                self._append_user(tool_msg)
                continue
            if "final" in action:
                return action["final"]
            if isinstance(action, dict):
                return action
            raise ValueError(f"[{self.name}] LLM response did not contain a valid tool or final JSON: {text[:200]}")
        raise RuntimeError(f"[{self.name}] exceeded {MAX_ITERATIONS} iterations without a final response")
