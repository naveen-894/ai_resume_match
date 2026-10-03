"""Loads the curated website-content source files that back the chatbot's
knowledge base.

Content lives in versioned JSON files under knowledge/content/ — one file per
site section — rather than being scraped live, so updates are reviewable and
the ingestion pipeline is deterministic. Update modax.in, update the matching
JSON file here, then rerun `python -m app.chatbot.knowledge.ingest`.
"""
import json
import logging
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

CONTENT_DIR = Path(__file__).parent / "content"


@dataclass(frozen=True)
class ContentItem:
    id: str
    url: str
    title: str
    section: str
    content_type: str
    text: str


def load_content_items() -> list[ContentItem]:
    """Reads every *.json file in content/ and returns a flat list of items.
    Raises if a file is malformed or an item is missing a required field, so
    ingestion fails loudly rather than silently skipping content."""
    items: list[ContentItem] = []
    seen_ids: set[str] = set()

    for path in sorted(CONTENT_DIR.glob("*.json")):
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, list):
            raise ValueError(f"{path.name}: expected a JSON array of content items")

        for entry in raw:
            missing = {"id", "url", "title", "section", "content_type", "text"} - entry.keys()
            if missing:
                raise ValueError(f"{path.name}: item missing fields {missing}: {entry}")
            if entry["id"] in seen_ids:
                raise ValueError(f"{path.name}: duplicate content id '{entry['id']}'")
            seen_ids.add(entry["id"])
            items.append(ContentItem(**entry))

    logger.info("Loaded %d knowledge content items from %s", len(items), CONTENT_DIR)
    return items
