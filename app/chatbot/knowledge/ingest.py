"""Knowledge ingestion CLI: load -> chunk -> embed -> upsert into Pinecone.

Rerunnable and idempotent — chunk ids are deterministic (derived from the
content item id), so re-running after editing a content JSON file just
overwrites the affected vectors instead of duplicating them.

Usage:
    python -m app.chatbot.knowledge.ingest            # upsert all current content
    python -m app.chatbot.knowledge.ingest --reset     # wipe the namespace first
"""
import argparse
import asyncio
import logging

from app.chatbot import embeddings, vector_store
from app.chatbot.knowledge.chunker import chunk_content_items
from app.chatbot.knowledge.loader import load_content_items

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

BATCH_SIZE = 50


async def run(reset: bool = False) -> None:
    vector_store.ensure_index()

    if reset:
        logger.info("Resetting namespace before ingestion")
        await vector_store.delete_all()

    items = load_content_items()
    chunks = chunk_content_items(items)
    logger.info("Prepared %d chunks from %d content items", len(chunks), len(items))

    for i in range(0, len(chunks), BATCH_SIZE):
        batch = chunks[i : i + BATCH_SIZE]
        vectors_values = await embeddings.embed_documents([c.embedding_text for c in batch])
        vectors = [
            {"id": chunk.id, "values": values, "metadata": chunk.metadata}
            for chunk, values in zip(batch, vectors_values)
        ]
        await vector_store.upsert_chunks(vectors)
        logger.info("Upserted chunks %d-%d of %d", i + 1, i + len(batch), len(chunks))

    logger.info("Ingestion complete: %d chunks indexed", len(chunks))


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest website knowledge into Pinecone")
    parser.add_argument(
        "--reset", action="store_true", help="Delete all existing vectors before ingesting"
    )
    args = parser.parse_args()
    asyncio.run(run(reset=args.reset))


if __name__ == "__main__":
    main()
