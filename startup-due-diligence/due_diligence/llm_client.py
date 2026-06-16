import datetime
import json
import os
import time
import uuid
import urllib.error
import urllib.request
from pathlib import Path
from typing import Dict, List, Optional

try:
    from langsmith import Client as LangSmithClient
    _LANGSMITH_AVAILABLE = True
except ImportError:
    _LANGSMITH_AVAILABLE = False


def _load_dotenv() -> None:
    env_path = Path(__file__).resolve().parents[2] / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


_load_dotenv()

# Model assigned to this POC: deepseek-ai/deepseek-r1-distill-llama-70b
DEFAULT_MODEL = "deepseek-ai/deepseek-r1-distill-llama-70b"


def _ls_project() -> str:
    """Read lazily so .env is guaranteed to be loaded first."""
    return os.getenv("LANGCHAIN_PROJECT_DD", "startup-due-diligence")


def _get_config() -> Dict[str, str]:
    base_url = os.getenv("QUBRID_BASE_URL")
    api_key = os.getenv("QUBRID_API_KEY")
    if not base_url or not api_key:
        raise RuntimeError("QUBRID_BASE_URL and QUBRID_API_KEY must be set for live LLM calls.")
    return {"base_url": base_url.rstrip("/"), "api_key": api_key}


def _get_langsmith_client() -> Optional["LangSmithClient"]:
    """Return a configured LangSmith client if tracing is enabled, else None."""
    if not _LANGSMITH_AVAILABLE:
        return None
    if os.getenv("LANGCHAIN_TRACING_V2", "").lower() not in ("true", "1"):
        return None
    api_key = os.getenv("LANGCHAIN_API_KEY")
    if not api_key or api_key == "your_langsmith_api_key_here":
        return None
    endpoint = os.getenv("LANGCHAIN_ENDPOINT", "https://api.smith.langchain.com")
    try:
        return LangSmithClient(api_url=endpoint, api_key=api_key)
    except Exception as exc:
        print(f"  [LangSmith] client init failed: {exc}")
        return None


def _trace(
    client: "LangSmithClient",
    run_id: uuid.UUID,
    run_name: str,
    messages: list,
    response: dict,
    start_dt: datetime.datetime,
    end_dt: datetime.datetime,
    error: Optional[str],
    model: str,
    max_tokens: int,
    temperature: float,
) -> None:
    """Create + update a LangSmith LLM run — the correct two-step pattern."""
    try:
        project = _ls_project()

        client.create_run(
            name=run_name,
            run_type="llm",
            project_name=project,
            inputs={"messages": messages},
            id=str(run_id),
            start_time=start_dt,
            extra={
                "metadata": {
                    "model": model,
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                    "project": project,
                }
            },
        )

        usage = {}
        if response and not error:
            u = (
                response.get("usage")
                or response.get("usage_metadata")
                or {}
            )
            usage = {
                "prompt_tokens":     u.get("prompt_tokens",     u.get("input_tokens",  0)),
                "completion_tokens": u.get("completion_tokens", u.get("output_tokens", 0)),
                "total_tokens":      u.get("total_tokens", 0),
            }

        client.update_run(
            run_id=str(run_id),
            end_time=end_dt,
            outputs={"response": response} if not error else {},
            error=error,
            extra={
                "metadata": {
                    "model": model,
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                    "project": project,
                },
                "usage_metadata": usage,
            },
        )
    except Exception as exc:
        print(f"  [LangSmith] trace failed: {exc}")


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
    run_id = uuid.uuid4()
    start_dt = datetime.datetime.now(datetime.timezone.utc)
    error_msg: Optional[str] = None
    response: Dict = {}

    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            response = json.load(resp)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        error_msg = f"Qubrid API HTTP {exc.code}: {body}"
    finally:
        end_dt = datetime.datetime.now(datetime.timezone.utc)
        if ls_client:
            _trace(
                client=ls_client,
                run_id=run_id,
                run_name=run_name,
                messages=messages,
                response=response,
                start_dt=start_dt,
                end_dt=end_dt,
                error=error_msg,
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
            )

    if error_msg:
        raise RuntimeError(error_msg)

    return response


def get_response_text(response: Dict) -> str:
    choices = response.get("choices") or []
    if not choices:
        raise ValueError("LLM returned no choices")
    return choices[0].get("message", {}).get("content", "")
