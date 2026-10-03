"""Pinecone vector store wrapper.

Kept behind a small interface (ensure_index / upsert_chunks / query / delete_all)
so the vector database could be swapped later without touching retrieval.py or
the ingestion pipeline.
"""
import asyncio
import logging
from functools import lru_cache
from typing import Any

from pinecone import Pinecone, ServerlessSpec
from pinecone.exceptions import PineconeApiException

from app.chatbot import config

logger = logging.getLogger(__name__)


class VectorStoreError(Exception):
    """Raised when the vector store is unavailable or misconfigured, so callers
    (the retrieval service) can fail gracefully instead of crashing the chat API."""


@lru_cache(maxsize=1)
def get_client() -> Pinecone:
    if not config.PINECONE_API_KEY:
        raise VectorStoreError("PINECONE_API_KEY is not configured")
    return Pinecone(api_key=config.PINECONE_API_KEY)


def ensure_index() -> None:
    """Create the knowledge-base index if it doesn't exist yet. Safe to call
    repeatedly (e.g. at the start of every ingestion run)."""
    pc = get_client()
    try:
        existing = set(pc.list_indexes().names())
        if config.PINECONE_INDEX_NAME not in existing:
            logger.info("Creating Pinecone index %s", config.PINECONE_INDEX_NAME)
            pc.create_index(
                name=config.PINECONE_INDEX_NAME,
                dimension=config.EMBEDDING_DIMENSIONS,
                metric="cosine",
                spec=ServerlessSpec(cloud=config.PINECONE_CLOUD, region=config.PINECONE_REGION),
            )
    except PineconeApiException as exc:
        raise VectorStoreError(f"Failed to ensure Pinecone index: {exc}") from exc


def _get_index():
    pc = get_client()
    return pc.Index(config.PINECONE_INDEX_NAME)


async def upsert_chunks(vectors: list[dict[str, Any]]) -> None:
    """vectors: list of {"id": str, "values": list[float], "metadata": dict}"""
    index = _get_index()
    try:
        await asyncio.to_thread(
            index.upsert, vectors=vectors, namespace=config.PINECONE_NAMESPACE
        )
    except PineconeApiException as exc:
        raise VectorStoreError(f"Pinecone upsert failed: {exc}") from exc


async def query(embedding: list[float], top_k: int | None = None) -> list[dict[str, Any]]:
    """Returns a list of {"id", "score", "metadata"} matches, best first."""
    index = _get_index()
    try:
        result = await asyncio.to_thread(
            index.query,
            vector=embedding,
            top_k=top_k or config.RETRIEVAL_TOP_K,
            namespace=config.PINECONE_NAMESPACE,
            include_metadata=True,
        )
    except PineconeApiException as exc:
        raise VectorStoreError(f"Pinecone query failed: {exc}") from exc

    matches = result.get("matches") if isinstance(result, dict) else result.matches
    return [
        {
            "id": m["id"] if isinstance(m, dict) else m.id,
            "score": m["score"] if isinstance(m, dict) else m.score,
            "metadata": (m["metadata"] if isinstance(m, dict) else m.metadata) or {},
        }
        for m in matches or []
    ]


async def delete_all() -> None:
    """Wipes the knowledge-base namespace. Used before a full re-ingestion run."""
    index = _get_index()
    try:
        await asyncio.to_thread(
            index.delete, delete_all=True, namespace=config.PINECONE_NAMESPACE
        )
    except PineconeApiException as exc:
        # Pinecone returns 404 if the namespace doesn't exist yet (nothing to delete)
        if "404" not in str(exc):
            raise VectorStoreError(f"Pinecone delete failed: {exc}") from exc
