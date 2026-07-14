"""Transparent numeric features used by the trained grammar classifier."""

from __future__ import annotations

import re
from collections.abc import Sequence

import numpy as np


COMMON_WRONG_FORMS = (
    "რათქმაუნდა",
    "მიუხედავათ",
    "ალბად",
    "რამოდენიმე",
    "ერთერთი",
    "არააქვს",
    "ვინხარ",
    "დავწერავ",
    "ავღნიშნავ",
    "ვნახამ",
)


def extract_rule_features(texts: Sequence[str]) -> np.ndarray:
    rows = []
    for value in texts:
        text = str(value)
        rows.append(
            [
                len(re.findall(r"[ \t]{2,}", text)),
                len(re.findall(r"\s+[,.;:!?]", text)),
                len(re.findall(r"[,;:!?](?=[^\s\d\n])", text)),
                len(re.findall(r"[A-Za-zА-Яа-я]", text)),
                sum(text.lower().count(form) for form in COMMON_WRONG_FORMS),
                len(re.findall(r"[!?.,]{2,}", text)),
                float(not bool(re.search(r"[.!?„”\"]$", text.strip()))),
                min(len(text), 300) / 300,
            ]
        )
    return np.asarray(rows, dtype=float)
