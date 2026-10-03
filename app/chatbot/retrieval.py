"""Retrieval service: embeds a user query and fetches grounding chunks from
the vector store. Kept separate from the LLM orchestration so the retrieval
strategy (top-k, score threshold, provider) can change independently."""
import logging

from app.chatbot import config, embeddings, vector_store

logger = logging.getLogger(__name__)


class RetrievedChunk:
    __slots__ = ("text", "url", "title", "section", "score")

    def __init__(self, text: str, url: str, title: str, section: str, score: float):
        self.text = text
        self.url = url
        self.title = title
        self.section = section
        self.score = score


async def retrieve(query: str, top_k: int | None = None) -> list[RetrievedChunk]:
    """Returns the most relevant knowledge-base chunks for `query`, filtered by
    a minimum similarity score. Returns an empty list (not an exception) on
    retrieval failure so the chatbot can fall back gracefully — callers should
    treat an empty result as "no confirmed information available"."""
    try:
        query_vector = await embeddings.embed_text(query)
        matches = await vector_store.query(query_vector, top_k=top_k)
    except vector_store.VectorStoreError:
        logger.exception("Vector store unavailable; answering without retrieval context")
        return []
    except Exception:
        logger.exception("Unexpected retrieval failure")
        return []

    chunks = []
    for match in matches:
        if match["score"] < config.RETRIEVAL_MIN_SCORE:
            continue
        meta = match["metadata"]
        chunks.append(
            RetrievedChunk(
                text=meta.get("text", ""),
                url=meta.get("url", ""),
                title=meta.get("title", ""),
                section=meta.get("section", ""),
                score=match["score"],
            )
        )
    return chunks
