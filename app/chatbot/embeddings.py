"""Embedding provider for the chatbot's retrieval pipeline.

Wraps langchain_openai (already a project dependency via langchain-openai) so the
rest of the chatbot code depends on a small, swappable interface rather than the
OpenAI SDK directly.
"""
import logging
from functools import lru_cache

from langchain_openai import OpenAIEmbeddings

from app.chatbot import config

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def get_embeddings_client() -> OpenAIEmbeddings:
    """A cached embeddings client. Cached because constructing it is cheap but
    repeated construction per-request is unnecessary overhead."""
    if config.EMBEDDING_PROVIDER != "openai":
        raise NotImplementedError(
            f"Embedding provider '{config.EMBEDDING_PROVIDER}' is not supported yet. "
            "Add a branch here to plug in another provider."
        )
    return OpenAIEmbeddings(model=config.EMBEDDING_MODEL, timeout=config.LLM_TIMEOUT_SECONDS)


async def embed_text(text: str) -> list[float]:
    """Embed a single piece of text (e.g. a user question)."""
    client = get_embeddings_client()
    return await client.aembed_query(text)


async def embed_documents(texts: list[str]) -> list[list[float]]:
    """Embed a batch of chunks (used by the ingestion pipeline)."""
    client = get_embeddings_client()
    return await client.aembed_documents(texts)
