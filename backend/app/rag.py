import json
import re
from dataclasses import dataclass
from pathlib import Path

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import linear_kernel


@dataclass(slots=True)
class KnowledgeRecord:
    id: str
    title: str
    text: str
    source_url: str
    author: str = ""
    genre: str = "ტექსტი"
    license: str = ""

    def public_dict(self, score: float | None = None) -> dict:
        payload = {
            "id": self.id,
            "title": self.title,
            "author": self.author,
            "genre": self.genre,
            "source_url": self.source_url,
            "license": self.license,
            "text": self.text,
        }
        if score is not None:
            payload["score"] = round(float(score), 4)
        return payload


def normalize_georgian_text(value: str) -> str:
    value = value.replace("\ufeff", " ").replace("\u00a0", " ")
    value = re.sub(r"[ \t]+", " ", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip()


def chunk_text(text: str, size: int = 1_100, overlap: int = 180) -> list[str]:
    clean = normalize_georgian_text(text)
    if len(clean) <= size:
        return [clean] if clean else []

    chunks: list[str] = []
    start = 0
    while start < len(clean):
        end = min(start + size, len(clean))
        if end < len(clean):
            natural_break = max(
                clean.rfind("\n", start + size // 2, end),
                clean.rfind(". ", start + size // 2, end),
                clean.rfind("? ", start + size // 2, end),
                clean.rfind("! ", start + size // 2, end),
            )
            if natural_break > start:
                end = natural_break + 1
        piece = clean[start:end].strip()
        if piece:
            chunks.append(piece)
        if end >= len(clean):
            break
        start = max(end - overlap, start + 1)
    return chunks


class KnowledgeBase:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.records: list[KnowledgeRecord] = []
        self.vectorizer: TfidfVectorizer | None = None
        self.matrix = None

    @property
    def ready(self) -> bool:
        return bool(self.records) and self.matrix is not None

    def load(self) -> None:
        self.records = []
        if not self.path.exists():
            return

        with self.path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                try:
                    item = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ValueError(
                        f"Invalid JSONL at {self.path}:{line_number}"
                    ) from exc
                text = normalize_georgian_text(str(item.get("text", "")))
                if len(text) < 40:
                    continue
                self.records.append(
                    KnowledgeRecord(
                        id=str(item.get("id", line_number)),
                        title=str(item.get("title", "უსათაურო")),
                        text=text,
                        source_url=str(item.get("source_url", "")),
                        author=str(item.get("author", "")),
                        genre=str(item.get("genre", "ტექსტი")),
                        license=str(item.get("license", "")),
                    )
                )

        if not self.records:
            return

        self.vectorizer = TfidfVectorizer(
            analyzer="char_wb",
            ngram_range=(2, 5),
            min_df=1,
            max_features=60_000,
            sublinear_tf=True,
        )
        searchable = [
            " ".join([record.title, record.author, record.genre, record.text])
            for record in self.records
        ]
        self.matrix = self.vectorizer.fit_transform(searchable)

    def search(
        self,
        query: str,
        limit: int = 4,
        min_score: float = 0.025,
        allowed_genres: set[str] | None = None,
    ) -> list[dict]:
        if not self.ready or self.vectorizer is None:
            return []

        query_vector = self.vectorizer.transform([normalize_georgian_text(query)])
        scores = linear_kernel(query_vector, self.matrix).ravel()
        ranked_indices = scores.argsort()[::-1]

        results: list[dict] = []
        seen_sources: set[str] = set()
        for index in ranked_indices:
            score = float(scores[index])
            if score < min_score:
                break
            record = self.records[int(index)]
            if allowed_genres is not None and record.genre not in allowed_genres:
                continue
            source_key = record.source_url or record.title
            if source_key in seen_sources:
                continue
            seen_sources.add(source_key)
            results.append(record.public_dict(score=score))
            if len(results) >= limit:
                break
        return results
