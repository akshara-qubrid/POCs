import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Dict, List

try:
    from langsmith import Client as LangSmithClient
    from langsmith.run_helpers import traceable  # noqa: F401 – imported for side-effects
    _LANGSMITH_AVAILABLE = True
except ImportError:
    _LANGSMITH_AVAILABLE = False


def _load_dotenv() -> None:
    env_path = Path(__file__).resolve().parents[2] / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())


_load_dotenv()

# Model assigned to this POC: mistralai/Mistral-7B-Instruct-v0.3
DEFAULT_MODEL = "mistralai/Mistral-7B-Instruct-v0.3"

# LangSmith project for this POC
_LS_PROJECT = os.getenv("LANGCHAIN_PROJECT_APM", "ai-product-manager")


def _get_config() -> Dict[str, str]:
    base_url = os.getenv("QUBRID_BASE_URL")
    api_key = os.getenv("QUBRID_API_KEY")
    if not base_url or not api_key:
        raise RuntimeError("QUBRID_BASE_URL and QUBRID_API_KEY must be set for live LLM calls.")
    return {"base_url": base_url.rstrip("/"), "api_key": api_key}


def _get_langsmith_client() -> "LangSmithClient | None":
    """Return a LangSmith client if tracing is enabled, else None."""
    if not _LANGSMITH_AVAILABLE:
        return None
    if os.getenv("LANGCHAIN_TRACING_V2", "").lower() not in ("true", "1"):
        return None
    api_key = os.getenv("LANGCHAIN_API_KEY")
    endpoint = os.getenv("LANGCHAIN_ENDPOINT", "https://api.smith.langchain.com")
    if not api_key:
        return None
    try:
        return LangSmithClient(api_url=endpoint, api_key=api_key)
    except Exception:
        return None


def _post_trace(
    client: "LangSmithClient",
    run_name: str,
    inputs: dict,
    outputs: dict,
    start_time: float,
    end_time: float,
    error: str | None = None,
    metadata: dict | None = None,
) -> None:
    """Fire-and-forget: post a single LLM trace to LangSmith."""
    try:
        import datetime
        usage = {}
        if outputs and not error:
            u = outputs.get("usage") or outputs.get("usage_metadata") or {}
            usage = {
                "prompt_tokens": u.get("prompt_tokens", u.get("input_tokens", 0)),
                "completion_tokens": u.get("completion_tokens", u.get("output_tokens", 0)),
                "total_tokens": u.get("total_tokens", 0),
            }

        client.create_run(
            name=run_name,
            run_type="llm",
            project_name=_LS_PROJECT,
            inputs={"messages": inputs.get("messages", [])},
            outputs={"response": outputs} if not error else {},
            error=error,
            start_time=datetime.datetime.utcfromtimestamp(start_time),
            end_time=datetime.datetime.utcfromtimestamp(end_time),
            extra={
                "metadata": {
                    **(metadata or {}),
                    "model": inputs.get("model", "unknown"),
                    "max_tokens": inputs.get("max_tokens"),
                    "project": _LS_PROJECT,
                },
                "usage_metadata": usage,
            },
        )
    except Exception as exc:
        # Tracing failures must never break the main pipeline
        print(f"  [LangSmith] trace post failed: {exc}")


def chat_completion(
    model: str,
    messages: List[Dict],
    max_tokens: int = 1024,
    temperature: float = 0.7,
    run_name: str = "chat_completion",
) -> Dict:
    config = _get_config()
    url = f"{config['base_url']}/chat/completions"
    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "top_p": 1,
        "stream": False,
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {config['api_key']}",
        },
    )

    ls_client = _get_langsmith_client()
    start = time.time()
    error_msg = None
    response = {}

    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            response = json.load(resp)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        error_msg = f"Qubrid API HTTP {exc.code}: {body}"
    finally:
        end = time.time()
        if ls_client:
            _post_trace(
                client=ls_client,
                run_name=run_name,
                inputs={**payload, "model": model},
                outputs=response,
                start_time=start,
                end_time=end,
                error=error_msg,
                metadata={"model": model, "max_tokens": max_tokens, "temperature": temperature},
            )

    if error_msg:
        raise RuntimeError(error_msg)

    return response


def get_response_text(response: Dict) -> str:
    choices = response.get("choices") or []
    if not choices:
        raise ValueError("LLM returned no choices")
    return choices[0].get("message", {}).get("content", "")
