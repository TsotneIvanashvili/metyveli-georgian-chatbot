"""Collect Georgian literary works from Georgian Wikisource.

The script keeps only pages whose categories identify a literary genre.
It stores source URL, author, category and license beside every text.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
from pathlib import Path
from typing import Iterable

import httpx
from bs4 import BeautifulSoup


API_URL = "https://ka.wikisource.org/w/api.php"
USER_AGENT = (
    "Mozilla/5.0 (compatible; SitqvaEducationalProject/1.0; "
    "+mailto:TBCTechSchool@geolab.edu.ge)"
)
API_USER_AGENT = (
    "SitqvaEducationalProject/1.0 "
    "(educational project; TBCTechSchool@geolab.edu.ge)"
)
GENRE_PATTERNS = {
    "ლექსი": ("ლექს", "პოეზ"),
    "მოთხრობა": ("მოთხრობ", "პროზა"),
    "პოემა": ("პოემ",),
    "რომანი": ("რომან",),
    "ზღაპარი": ("ზღაპ",),
    "იგავი": ("იგავ",),
    "ნოველა": ("ნოველ",),
    "დრამა": ("დრამ",),
}


def chunks(items: list[int], size: int) -> Iterable[list[int]]:
    for start in range(0, len(items), size):
        yield items[start : start + size]


def api_get(client: httpx.Client, params: dict) -> dict:
    response = client.get(API_URL, params=params)
    response.raise_for_status()
    payload = response.json()
    if "error" in payload:
        raise RuntimeError(payload["error"])
    return payload


def list_all_pages(client: httpx.Client) -> list[dict]:
    pages: list[dict] = []
    continuation: dict = {}
    while True:
        params = {
            "action": "query",
            "list": "allpages",
            "apnamespace": 0,
            "aplimit": "max",
            "format": "json",
            "formatversion": 2,
            **continuation,
        }
        payload = api_get(client, params)
        pages.extend(payload.get("query", {}).get("allpages", []))
        if "continue" not in payload:
            return pages
        continuation = payload["continue"]


def detect_genre(categories: list[str]) -> str | None:
    joined = " ".join(categories).lower()
    for genre, patterns in GENRE_PATTERNS.items():
        if any(pattern in joined for pattern in patterns):
            return genre
    return None


def clean_html_and_author(html: str) -> tuple[str, str]:
    soup = BeautifulSoup(html, "html.parser")
    author = ""
    author_link = soup.find(
        "a",
        attrs={"title": re.compile(r"^ავტორი:")},
    )
    if author_link:
        author = author_link.get_text(" ", strip=True)

    for element in soup.select(
        "table, style, script, noscript, sup, .mw-editsection, .noprint"
    ):
        element.decompose()
    text = soup.get_text("\n", strip=True)
    text = text.replace("\u00a0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip(), author


def fetch_metadata(
    client: httpx.Client,
    page_ids: list[int],
    delay: float,
) -> Iterable[dict]:
    for page_batch in chunks(page_ids, 50):
        payload = api_get(
            client,
            {
                "action": "query",
                "prop": "categories|info",
                "pageids": "|".join(str(page_id) for page_id in page_batch),
                "cllimit": "max",
                "inprop": "url",
                "format": "json",
                "formatversion": 2,
            },
        )
        yield from payload.get("query", {}).get("pages", [])
        if delay:
            time.sleep(delay)


def fetch_content(
    client: httpx.Client,
    page_ids: list[int],
    delay: float,
) -> Iterable[dict]:
    # Wikimedia returns parsed revision content for at most 10 pages per request.
    for page_batch in chunks(page_ids, 10):
        payload = api_get(
            client,
            {
                "action": "query",
                "prop": "revisions",
                "pageids": "|".join(str(page_id) for page_id in page_batch),
                "rvprop": "content",
                "rvparse": 1,
                "format": "json",
                "formatversion": 2,
            },
        )
        yield from payload.get("query", {}).get("pages", [])
        if delay:
            time.sleep(delay)


def collect(output: Path, max_docs: int, delay: float) -> dict:
    output.parent.mkdir(parents=True, exist_ok=True)
    timeout = httpx.Timeout(60)
    headers = {
        "User-Agent": USER_AGENT,
        "Api-User-Agent": API_USER_AGENT,
    }
    saved = 0
    duplicates = 0
    skipped = 0
    seen_hashes: set[str] = set()

    with httpx.Client(timeout=timeout, headers=headers, follow_redirects=True) as client:
        all_pages = list_all_pages(client)
        page_ids = [int(page["pageid"]) for page in all_pages]
        literary_metadata: dict[int, dict] = {}
        for page in fetch_metadata(client, page_ids, delay):
            categories = [
                item.get("title", "").removeprefix("კატეგორია:")
                for item in page.get("categories", [])
            ]
            genre = detect_genre(categories)
            if genre:
                page["categories_clean"] = categories
                page["genre"] = genre
                literary_metadata[int(page["pageid"])] = page
        skipped = len(page_ids) - len(literary_metadata)

        with output.open("w", encoding="utf-8") as handle:
            for content_page in fetch_content(
                client,
                list(literary_metadata),
                delay,
            ):
                page = literary_metadata[int(content_page["pageid"])]
                categories = page["categories_clean"]
                genre = page["genre"]
                revisions = content_page.get("revisions", [])
                html = revisions[0].get("content", "") if revisions else ""
                if not html:
                    skipped += 1
                    continue

                text, author = clean_html_and_author(html)
                if len(text) < 120:
                    skipped += 1
                    continue
                content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
                if content_hash in seen_hashes:
                    duplicates += 1
                    continue
                seen_hashes.add(content_hash)

                record = {
                    "id": f"wikisource-{page['pageid']}",
                    "page_id": page["pageid"],
                    "title": page.get("title", "უსათაურო"),
                    "author": author,
                    "genre": genre,
                    "categories": categories,
                    "text": text,
                    "source_url": page.get("fullurl", ""),
                    "license": "CC BY-SA, ქართული ვიკიწყარო",
                    "content_sha256": content_hash,
                }
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
                saved += 1
                if max_docs and saved >= max_docs:
                    break

    return {
        "available_pages": len(page_ids),
        "saved_documents": saved,
        "duplicates_removed": duplicates,
        "skipped_non_literary_or_empty": skipped,
        "output": str(output),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/raw/wikisource/literature.jsonl"),
    )
    parser.add_argument(
        "--max-docs",
        type=int,
        default=0,
        help="0 means every matching literary page.",
    )
    parser.add_argument("--delay", type=float, default=0.05)
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    result = collect(args.output, args.max_docs, args.delay)
    print(json.dumps(result, ensure_ascii=False, indent=2))
