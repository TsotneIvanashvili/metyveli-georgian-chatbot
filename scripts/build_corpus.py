from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.rag import chunk_text


def load_json(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    records = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                records.append(json.loads(line))
    return records


def build(literature_path: Path, rules_path: Path, output_path: Path) -> dict:
    documents = load_jsonl(literature_path)
    documents.extend(load_json(rules_path))
    output_path.parent.mkdir(parents=True, exist_ok=True)

    chunk_count = 0
    duplicate_count = 0
    seen: set[str] = set()
    with output_path.open("w", encoding="utf-8") as handle:
        for document in documents:
            for index, text in enumerate(chunk_text(document.get("text", ""))):
                digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
                if digest in seen:
                    duplicate_count += 1
                    continue
                seen.add(digest)
                item = {
                    "id": f"{document.get('id', 'doc')}-chunk-{index + 1}",
                    "document_id": document.get("id", ""),
                    "title": document.get("title", "უსათაურო"),
                    "author": document.get("author", ""),
                    "genre": document.get("genre", "ტექსტი"),
                    "text": text,
                    "source_url": document.get("source_url", ""),
                    "license": document.get("license", ""),
                }
                handle.write(json.dumps(item, ensure_ascii=False) + "\n")
                chunk_count += 1

    return {
        "documents": len(documents),
        "chunks": chunk_count,
        "duplicate_chunks_removed": duplicate_count,
        "output": str(output_path),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--literature",
        type=Path,
        default=Path("data/raw/wikisource/literature.jsonl"),
    )
    parser.add_argument(
        "--rules",
        type=Path,
        default=Path("data/curated/grammar_rules.json"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/processed/knowledge_base.jsonl"),
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    print(
        json.dumps(
            build(args.literature, args.rules, args.output),
            ensure_ascii=False,
            indent=2,
        )
    )
