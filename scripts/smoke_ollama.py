import asyncio
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.config import get_settings
from backend.app.ollama_client import OllamaClient
from backend.app.prompts import build_system_prompt


async def main() -> None:
    client = OllamaClient(get_settings())
    parts: list[str] = []
    async for chunk in client.stream_chat(
        [
            {
                "role": "system",
                "content": build_system_prompt("grammar", []),
            },
            {"role": "user", "content": "სალამი"},
        ]
    ):
        parts.append(chunk)

    response = "".join(parts)
    print(
        json.dumps(
            {
                "characters": len(response),
                "words": len(response.split()),
                "response": response,
            },
            ensure_ascii=True,
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
