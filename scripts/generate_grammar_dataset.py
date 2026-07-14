from __future__ import annotations

import argparse
import csv
import json
import random
import re
from pathlib import Path


COMMON_ERRORS = {
    "რა თქმა უნდა": "რათქმაუნდა",
    "მიუხედავად": "მიუხედავათ",
    "ალბათ": "ალბად",
    "რამდენიმე": "რამოდენიმე",
    "ერთ-ერთი": "ერთერთი",
    "აღვნიშნავ": "ავღნიშნავ",
    "ვნახავ": "ვნახამ",
    "დავწერ": "დავწერავ",
}


def add_double_space(text: str) -> str | None:
    positions = [match.start() for match in re.finditer(" ", text)]
    if not positions:
        return None
    position = positions[len(positions) // 2]
    return text[:position] + "  " + text[position + 1 :]


def add_space_before_punctuation(text: str) -> str | None:
    match = re.search(r"[,.;:!?]", text)
    if not match:
        return None
    return text[: match.start()] + " " + text[match.start() :]


def remove_space_after_punctuation(text: str) -> str | None:
    match = re.search(r"([,;:!?]) ", text)
    if not match:
        return None
    return text[: match.end() - 1] + text[match.end() :]


def replace_common_form(text: str) -> str | None:
    for correct, wrong in COMMON_ERRORS.items():
        if correct in text:
            return text.replace(correct, wrong, 1)
    return None


def mix_alphabet(text: str) -> str | None:
    replacements = {"ა": "a", "ე": "e", "ო": "o"}
    for index in range(len(text) // 3, len(text)):
        if text[index] in replacements:
            return (
                text[:index]
                + replacements[text[index]]
                + text[index + 1 :]
            )
    return None


TRANSFORMS = [
    ("double_space", add_double_space),
    ("space_before_punctuation", add_space_before_punctuation),
    ("missing_space_after_punctuation", remove_space_after_punctuation),
    ("common_spelling", replace_common_form),
    ("mixed_alphabet", mix_alphabet),
]


def generate(seed_path: Path, output_path: Path, seed: int = 42) -> dict:
    random.seed(seed)
    rows: list[dict] = []
    with seed_path.open("r", encoding="utf-8-sig", newline="") as handle:
        seeds = list(csv.DictReader(handle))

    for item in seeds:
        source_id = item["source_id"]
        correct_text = item["text"].strip()
        rows.append(
            {
                "source_id": source_id,
                "text": correct_text,
                "label": "correct",
                "error_type": "none",
                "correct_text": correct_text,
            }
        )
        created: set[str] = set()
        transform_order = TRANSFORMS[:]
        random.shuffle(transform_order)
        for error_type, transform in transform_order:
            corrupted = transform(correct_text)
            if not corrupted or corrupted == correct_text or corrupted in created:
                continue
            created.add(corrupted)
            rows.append(
                {
                    "source_id": source_id,
                    "text": corrupted,
                    "label": "error",
                    "error_type": error_type,
                    "correct_text": correct_text,
                }
            )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "source_id",
                "text",
                "label",
                "error_type",
                "correct_text",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)

    counts: dict[str, int] = {}
    for row in rows:
        counts[row["label"]] = counts.get(row["label"], 0) + 1
    return {
        "seed_sentences": len(seeds),
        "rows": len(rows),
        "class_counts": counts,
        "output": str(output_path),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--seed-file",
        type=Path,
        default=Path("data/grammar_seed.csv"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/processed/grammar_dataset.csv"),
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    print(
        json.dumps(
            generate(args.seed_file, args.output),
            ensure_ascii=False,
            indent=2,
        )
    )

