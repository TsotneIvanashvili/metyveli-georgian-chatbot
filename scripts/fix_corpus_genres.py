from __future__ import annotations

import argparse
import json
from pathlib import Path

from collect_wikisource import detect_genre


def fix_genres(path: Path) -> dict:
    resolved = path.resolve()
    workspace = Path(__file__).resolve().parents[1]
    if workspace not in resolved.parents:
        raise ValueError("Corpus path must stay inside the project workspace.")

    temporary = path.with_suffix(path.suffix + ".tmp")
    changed = 0
    records = 0
    with path.open("r", encoding="utf-8") as source, temporary.open(
        "w",
        encoding="utf-8",
    ) as destination:
        for line in source:
            if not line.strip():
                continue
            item = json.loads(line)
            corrected = (
                detect_genre(item.get("categories", []))
                or "ლიტერატურული ტექსტი"
            )
            if corrected != item.get("genre"):
                item["genre"] = corrected
                changed += 1
            destination.write(json.dumps(item, ensure_ascii=False) + "\n")
            records += 1

    temporary.replace(path)
    return {"records": records, "genres_changed": changed, "path": str(path)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--path",
        type=Path,
        default=Path("data/raw/wikisource/literature.jsonl"),
    )
    args = parser.parse_args()
    print(json.dumps(fix_genres(args.path), ensure_ascii=False, indent=2))
