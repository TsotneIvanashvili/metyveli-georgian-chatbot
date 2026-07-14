import re

from .grammar import GrammarAnalyzer


EMOJI_PATTERN = re.compile(
    "["
    "\U0001F1E6-\U0001F1FF"
    "\U0001F300-\U0001FAFF"
    "\u2600-\u27BF"
    "\uFE0F"
    "\u200D"
    "]+",
    flags=re.UNICODE,
)

PROTECTED_SEGMENT_PATTERN = re.compile(
    r"```.*?```|`[^`\n]+`|https?://[^\s<>()]+",
    flags=re.DOTALL | re.IGNORECASE,
)


def _protect_segments(value: str) -> tuple[str, list[str]]:
    segments: list[str] = []

    def replace(match: re.Match) -> str:
        segments.append(match.group(0))
        return f"\ue000{len(segments) - 1}\ue001"

    return PROTECTED_SEGMENT_PATTERN.sub(replace, value), segments


def _restore_segments(value: str, segments: list[str]) -> str:
    for index, segment in enumerate(segments):
        value = value.replace(f"\ue000{index}\ue001", segment)
    return value


def polish_model_response(
    value: str,
    grammar_analyzer: GrammarAnalyzer,
    *,
    allow_source_markers: bool = True,
) -> str:
    text, protected_segments = _protect_segments(value)
    text = EMOJI_PATTERN.sub("", text)
    text = re.sub(r"\*\*(.*?)\*\*", r"\1", text, flags=re.DOTALL)
    text = re.sub(r"(?m)^\s*\*\s+", "- ", text)
    text = re.sub(
        r"(?<!\S)\*([^\s*](?:[^*\n]*[^\s*])?)\*(?!\S)",
        r"\1",
        text,
    )
    text = re.sub(r"(?m)^\s*#{1,6}\s*", "", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(
        r"(?iu)\b([\w\u10A0-\u10FF]+)\b(?:\s+\1\b)+",
        r"\1",
        text,
    )
    if not allow_source_markers:
        text = re.sub(r"\s*\[წყარო\s+\d+\]", "", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    corrected = grammar_analyzer.analyze(text)["corrected"]
    return _restore_segments(corrected, protected_segments)
