"""Environment-driven configuration for the website chatbot.

All chatbot settings are read from environment variables (loaded via the same
.env the rest of the app already uses) so the LLM provider, embedding model
and vector database can be swapped without touching code.
"""
import os

from dotenv import find_dotenv, load_dotenv

load_dotenv(find_dotenv())


def _float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def _bool(name: str, default: bool) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "on"}


# --- Company / branding -----------------------------------------------------
COMPANY_NAME = os.getenv("CHATBOT_COMPANY_NAME", "Modax")
COMPANY_WEBSITE = os.getenv("CHATBOT_COMPANY_WEBSITE", "https://modax.in")
CONTACT_PAGE_URL = os.getenv("CHATBOT_CONTACT_URL", "https://modax.in/contact")
LEAD_NOTIFICATION_EMAIL = os.getenv("LEAD_NOTIFICATION_EMAIL", "vnaveen894@gmail.com")

# --- LLM ---------------------------------------------------------------------
LLM_PROVIDER = os.getenv("CHATBOT_LLM_PROVIDER", "openai")
LLM_MODEL = os.getenv("CHATBOT_LLM_MODEL", "gpt-4o-mini")
LLM_TEMPERATURE = _float("CHATBOT_LLM_TEMPERATURE", 0.3)
LLM_MAX_TOKENS = _int("CHATBOT_LLM_MAX_TOKENS", 700)
LLM_TIMEOUT_SECONDS = _float("CHATBOT_LLM_TIMEOUT_SECONDS", 20)
LLM_MAX_RETRIES = _int("CHATBOT_LLM_MAX_RETRIES", 2)

GUARD_MODEL = os.getenv("CHATBOT_GUARD_MODEL", "gpt-4o-mini")

# --- Embeddings / retrieval ---------------------------------------------------
EMBEDDING_PROVIDER = os.getenv("CHATBOT_EMBEDDING_PROVIDER", "openai")
EMBEDDING_MODEL = os.getenv("CHATBOT_EMBEDDING_MODEL", "text-embedding-3-small")
EMBEDDING_DIMENSIONS = _int("CHATBOT_EMBEDDING_DIMENSIONS", 1536)
RETRIEVAL_TOP_K = _int("CHATBOT_TOP_K", 4)
RETRIEVAL_MIN_SCORE = _float("CHATBOT_MIN_SCORE", 0.3)

# --- Vector store (Pinecone) --------------------------------------------------
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY", "")
PINECONE_INDEX_NAME = os.getenv("PINECONE_INDEX_NAME", "modax-chatbot-kb")
PINECONE_CLOUD = os.getenv("PINECONE_CLOUD", "aws")
PINECONE_REGION = os.getenv("PINECONE_REGION", "us-east-1")
PINECONE_NAMESPACE = os.getenv("PINECONE_NAMESPACE", "website-kb")

# --- Chunking / ingestion -----------------------------------------------------
CHUNK_SIZE_CHARS = _int("CHATBOT_CHUNK_SIZE_CHARS", 900)
CHUNK_OVERLAP_CHARS = _int("CHATBOT_CHUNK_OVERLAP_CHARS", 150)

# --- Conversation / session ---------------------------------------------------
SESSION_TTL_HOURS = _int("CHATBOT_SESSION_TTL_HOURS", 24)
MAX_HISTORY_MESSAGES = _int("CHATBOT_MAX_HISTORY_MESSAGES", 12)
MAX_MESSAGE_LENGTH = _int("CHATBOT_MAX_MESSAGE_LENGTH", 2000)

# --- Rate limiting / abuse prevention ------------------------------------------
RATE_LIMIT_MESSAGE = os.getenv("CHATBOT_RATE_LIMIT_MESSAGE", "20/minute")
RATE_LIMIT_LEAD = os.getenv("CHATBOT_RATE_LIMIT_LEAD", "5/hour")
RATE_LIMIT_SESSION = os.getenv("CHATBOT_RATE_LIMIT_SESSION", "10/minute")
MAX_REQUEST_BODY_BYTES = _int("CHATBOT_MAX_REQUEST_BYTES", 20_000)

# Shared secret the Next.js proxy must send; defense-in-depth on top of CORS
# since the backend's global CORS policy currently allows all origins.
INTERNAL_API_KEY = os.getenv("CHATBOT_INTERNAL_API_KEY", "")

# --- Feature flags -------------------------------------------------------------
CHATBOT_ENABLED = _bool("CHATBOT_ENABLED", True)

# --- Email (reuses the Resend account already used by the marketing site) -----
RESEND_API_KEY = os.getenv("RESEND_API_KEY", "")
RESEND_FROM_EMAIL = os.getenv("CHATBOT_LEAD_FROM_EMAIL", "Modax Chatbot <onboarding@resend.dev>")

SUGGESTED_PROMPTS = [
    p.strip()
    for p in os.getenv(
        "CHATBOT_SUGGESTED_PROMPTS",
        "What services do you offer?|Tell me about your projects.|"
        "I need a custom software solution.|How can I start a project with your team?|"
        "How can I contact your company?",
    ).split("|")
    if p.strip()
]

GREETING_MESSAGE = os.getenv(
    "CHATBOT_GREETING_MESSAGE",
    f"Hi! Welcome to {COMPANY_NAME}. I'm your AI assistant. I can help you explore our "
    "services, understand our work, or discuss your project requirements. How can I help you today?",
)
