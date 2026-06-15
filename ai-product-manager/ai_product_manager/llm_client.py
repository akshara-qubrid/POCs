import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Dict, List


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

# Model assigned to this POC: openai/gpt-oss-120b
DEFAULT_MODEL = "openai/gpt-oss-120b"


def _get_config() -> Dict[str, str]:
    base_url = os.getenv("QUBRID_BASE_URL")
    api_key = os.getenv("QUBRID_API_KEY")
    if not base_url or not api_key:
        raise RuntimeError("QUBRID_BASE_URL and QUBRID_API_KEY must be set for live LLM calls.")
    return {"base_url": base_url.rstrip("/"), "api_key": api_key}


def chat_completion(model: str, messages: List[Dict], max_tokens: int = 1024, temperature: float = 0.7) -> Dict:
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
    try:
        with urllib.request.urlopen(req, timeout=120) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Qubrid API HTTP {exc.code}: {body}") from exc


def get_response_text(response: Dict) -> str:
    choices = response.get("choices") or []
    if not choices:
        raise ValueError("LLM returned no choices")
    return choices[0].get("message", {}).get("content", "")
