"""Splits content items into embedding-sized chunks, preserving metadata.

Most curated content items are already short, self-contained paragraphs, so
most items pass through as a single chunk. Longer items are split on sentence
boundaries with a small overlap so retrieval doesn't lose context at a chunk edge.
"""
import re
from dataclasses import dataclass

from app.chatbot import config
from app.chatbot.knowledge.loader import ContentItem

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


@dataclass(frozen=True)
class Chunk:
    id: str
    text: str
    embedding_text: str
    metadata: dict


def _split_text(text: str, size: int, overlap: int) -> list[str]:
    if len(text) <= size:
        return [text]

    sentences = _SENTENCE_SPLIT.split(text)
    chunks: list[str] = []
    current = ""

    for sentence in sentences:
        candidate = f"{current} {sentence}".strip()
        if len(candidate) <= size:
            current = candidate
            continue
        if current:
            chunks.append(current)
        # carry the tail of the previous chunk forward for continuity
        tail = current[-overlap:] if overlap and current else ""
        current = f"{tail} {sentence}".strip()

    if current:
        chunks.append(current)
    return chunks or [text]


def chunk_content_items(items: list[ContentItem]) -> list[Chunk]:
    chunks: list[Chunk] = []
    for item in items:
        pieces = _split_text(item.text, config.CHUNK_SIZE_CHARS, config.CHUNK_OVERLAP_CHARS)
        for idx, piece in enumerate(pieces):
            chunk_id = item.id if len(pieces) == 1 else f"{item.id}__{idx}"
            # Embed title + section alongside the body text, not the body alone.
            # Short natural-language questions ("What services do you offer?")
            # often share almost no vocabulary with a body paragraph but match
            # strongly on the page title/section ("AI Solutions" / "AI Scoring
            # & Matching") — without this, cosine similarity for exactly the
            # right chunk can score *below* unrelated chunks on generic queries.
            embedding_text = f"{item.title}\n{item.section}\n{piece}"
            chunks.append(
                Chunk(
                    id=chunk_id,
                    text=piece,
                    embedding_text=embedding_text,
                    metadata={
                        "source_id": item.id,
                        "url": item.url,
                        "title": item.title,
                        "section": item.section,
                        "content_type": item.content_type,
                        "text": piece,
                    },
                )
            )
    return chunks
