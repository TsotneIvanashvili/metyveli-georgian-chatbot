import json
import re
from collections.abc import AsyncIterator, Sequence
import httpx

from .config import Settings


class OllamaUnavailableError(RuntimeError):
    """Raised when the local Ollama service cannot answer."""


class OllamaDegenerateResponseError(RuntimeError):
    """Raised when generation gets stuck in a repetitive loop."""


def response_is_repetitive(value: str) -> bool:
    words = re.findall(r"[\w\u10A0-\u10FF]+", value.casefold())
    if len(words) < 12:
        return False

    recent = words[-24:]
    if max(recent.count(word) for word in set(recent)) >= 8:
        return True

    for size in (2, 3, 4):
        if len(recent) < size * 3:
            continue
        tail = tuple(recent[-size:])
        previous = tuple(recent[-size * 2 : -size])
        before_previous = tuple(recent[-size * 3 : -size * 2])
        if tail == previous == before_previous:
            return True
    return False


class OllamaClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @property
    def chat_url(self) -> str:
        return f"{self.settings.ollama_base_url.rstrip('/')}/api/chat"

    @property
    def headers(self) -> dict[str, str]:
        if not self.settings.ollama_api_key:
            return {}
        return {"Authorization": f"Bearer {self.settings.ollama_api_key}"}

    async def status(self) -> dict:
        url = f"{self.settings.ollama_base_url.rstrip('/')}/api/tags"
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                response = await client.get(url, headers=self.headers)
                response.raise_for_status()
                payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            return {
                "connected": False,
                "model": self.settings.ollama_model,
                "model_available": False,
                "error": str(exc),
            }

        names = [item.get("name", "") for item in payload.get("models", [])]
        return {
            "connected": True,
            "model": self.settings.ollama_model,
            "model_available": self.settings.ollama_model in names,
            "available_models": names,
        }

    async def stream_chat(
        self,
        messages: Sequence[dict[str, str]],
    ) -> AsyncIterator[str]:
        payload = {
            "model": self.settings.ollama_model,
            "messages": list(messages),
            "stream": True,
            # Qwen3's reasoning pass materially improves factual accuracy and
            # Georgian coherence. Ollama returns reasoning separately, while
            # this client streams only the final answer content.
            "think": True,
            "options": {
                "temperature": 0.15,
                "top_k": 40,
                "top_p": 0.85,
                "min_p": 0.05,
                "repeat_penalty": 1.18,
                "repeat_last_n": 256,
                "num_ctx": self.settings.ollama_context_size,
            },
        }
        timeout = httpx.Timeout(
            connect=10,
            read=self.settings.ollama_timeout_seconds,
            write=30,
            pool=10,
        )

        try:
            generated = ""
            async with httpx.AsyncClient(timeout=timeout) as client:
                async with client.stream(
                    "POST",
                    self.chat_url,
                    headers=self.headers,
                    json=payload,
                ) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if not line:
                            continue
                        data = json.loads(line)
                        content = data.get("message", {}).get("content", "")
                        if content:
                            generated += content
                            if response_is_repetitive(generated):
                                raise OllamaDegenerateResponseError(
                                    "Ollama produced a repetitive response."
                                )
                            yield content
                        if data.get("done"):
                            break
        except OllamaDegenerateResponseError:
            raise
        except (httpx.HTTPError, json.JSONDecodeError) as exc:
            raise OllamaUnavailableError(str(exc)) from exc
