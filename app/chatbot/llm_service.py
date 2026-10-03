"""LLM provider service: the one place that talks to the chat model.

Wraps langchain_openai.ChatOpenAI (same library already used elsewhere in this
backend) behind a small interface — stream_reply() / classify_guard() — so the
provider can be swapped by changing this file alone, with model name/timeouts/
temperature all coming from environment config.
"""
import logging
from collections.abc import AsyncIterator

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from app.chatbot import config

logger = logging.getLogger(__name__)


class LLMServiceError(Exception):
    """Raised on provider failure (timeout, rate limit, auth, etc.) so the
    orchestrator can show a safe fallback message instead of crashing."""


def _build_chat_model(model: str, temperature: float) -> ChatOpenAI:
    return ChatOpenAI(
        model=model,
        temperature=temperature,
        timeout=config.LLM_TIMEOUT_SECONDS,
        max_retries=config.LLM_MAX_RETRIES,
        max_tokens=config.LLM_MAX_TOKENS,
    )


def to_langchain_messages(
    system_prompt: str, history: list[dict], user_turn: str
) -> list[BaseMessage]:
    messages: list[BaseMessage] = [SystemMessage(content=system_prompt)]
    for turn in history:
        if turn["role"] == "user":
            messages.append(HumanMessage(content=turn["content"]))
        elif turn["role"] == "assistant":
            messages.append(AIMessage(content=turn["content"]))
    messages.append(HumanMessage(content=user_turn))
    return messages


async def stream_reply(
    system_prompt: str, history: list[dict], user_turn: str
) -> AsyncIterator[str]:
    """Streams the assistant's reply token-by-token. Raises LLMServiceError on
    provider failure (callers should catch this and show a safe fallback)."""
    model = _build_chat_model(config.LLM_MODEL, config.LLM_TEMPERATURE)
    messages = to_langchain_messages(system_prompt, history, user_turn)
    try:
        async for chunk in model.astream(messages):
            if chunk.content:
                yield chunk.content
    except Exception as exc:  # noqa: BLE001 — provider SDK raises various transport errors
        logger.exception("LLM streaming failed")
        raise LLMServiceError(str(exc)) from exc


async def complete(system_prompt: str, user_turn: str) -> str:
    """Non-streaming single completion, used for cheap classifier-style calls
    (e.g. the prompt-injection guard)."""
    model = _build_chat_model(config.GUARD_MODEL, 0.0)
    try:
        result = await model.ainvoke(
            [SystemMessage(content=system_prompt), HumanMessage(content=user_turn)]
        )
        return (result.content or "").strip()
    except Exception as exc:  # noqa: BLE001
        logger.exception("LLM completion failed")
        raise LLMServiceError(str(exc)) from exc
