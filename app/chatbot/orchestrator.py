"""Conversation orchestration: ties together the prompt-injection guard,
retrieval, and the LLM into one conversational turn.

Yields structured events so the API layer can stream sources first, then
tokens, over SSE:
    {"type": "sources", "sources": [{"url", "title"}, ...]}
    {"type": "token", "content": str}
"""
import logging
from collections.abc import AsyncIterator

from app.chatbot import config, llm_service, prompts, retrieval

logger = logging.getLogger(__name__)


async def _is_prompt_injection(user_message: str) -> bool:
    try:
        verdict = await llm_service.complete(prompts.GUARD_SYSTEM_PROMPT, user_message)
    except llm_service.LLMServiceError:
        # Fail open on guard-model errors — the grounding rules in the main system
        # prompt are the second line of defense, and we'd rather answer than block.
        logger.warning("Prompt-injection guard failed; allowing message through")
        return False
    return verdict.strip().lower().startswith("block")


def _dedupe_sources(chunks) -> list[dict]:
    seen: set[str] = set()
    sources: list[dict] = []
    for chunk in chunks:
        if chunk.url and chunk.url not in seen:
            seen.add(chunk.url)
            sources.append({"url": chunk.url, "title": chunk.title})
    return sources


async def handle_message(
    history: list[dict], user_message: str
) -> AsyncIterator[dict]:
    """history: list of {"role": "user"|"assistant", "content": str}, oldest first.
    Truncated by the caller to config.MAX_HISTORY_MESSAGES before calling this."""
    if await _is_prompt_injection(user_message):
        yield {"type": "sources", "sources": []}
        yield {"type": "token", "content": prompts.INJECTION_REDIRECT_MESSAGE}
        return

    chunks = await retrieval.retrieve(user_message, top_k=config.RETRIEVAL_TOP_K)
    yield {"type": "sources", "sources": _dedupe_sources(chunks)}

    user_turn = prompts.build_user_turn(user_message, chunks)
    try:
        async for token in llm_service.stream_reply(prompts.SYSTEM_PROMPT, history, user_turn):
            yield {"type": "token", "content": token}
    except llm_service.LLMServiceError:
        yield {"type": "token", "content": prompts.SERVICE_UNAVAILABLE_MESSAGE}
