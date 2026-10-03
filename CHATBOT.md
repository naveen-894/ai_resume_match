# Website AI Chatbot

A RAG-powered AI assistant for the Modax marketing site (`modax.in`), living in
this backend (`app/chatbot/`) for now. The frontend widget lives in the
`modax` repo (`components/chatbot/`) and talks to this backend through Next.js
proxy routes.

> This backend currently serves two products: the AI Resume Matcher (existing
> `app/` modules) and the website chatbot (`app/chatbot/`). If the chatbot is
> ever split out, `app/chatbot/` plus the three `chatbot_*` tables are the
> whole surface area to move — nothing else in `app/` depends on it.

## Architecture

```
modax (Next.js)                          ai_resume_match (FastAPI)
┌─────────────────────────┐              ┌──────────────────────────────┐
│ components/chatbot/      │   HTTPS      │ app/chatbot/                  │
│  ChatWidget → useChat-    │ ───────────▶ │  routes.py  (API endpoints)   │
│  Session (fetch + SSE)    │              │  orchestrator.py (guard→      │
│                           │              │    retrieve→prompt→stream)    │
│ app/api/chatbot/*         │              │  retrieval.py → embeddings.py │
│  (server-side proxy;      │              │    + vector_store.py          │
│  adds shared secret,      │              │  llm_service.py (OpenAI)      │
│  streams SSE through)     │              │  lead_service.py →            │
└─────────────────────────┘              │    email_service.py (Resend)  │
                                           │  models.py (Postgres tables)  │
                                           └──────────────┬────────────────┘
                                                           │
                                              ┌────────────┴───────────┐
                                              │ Pinecone (vector store) │
                                              │ OpenAI (chat + embed)   │
                                              │ Resend (lead emails)    │
                                              └─────────────────────────┘
```

**Why this split:** the Next.js app never talks to OpenAI/Pinecone/Resend
directly — no provider keys or prompts are ever shipped to the browser. The
Next.js route handlers (`app/api/chatbot/*` in the `modax` repo) are a thin,
server-side proxy that adds a shared secret header and streams the backend's
SSE response straight through.

### Request flow (`POST /api/chatbot/message`)

1. `routes.py` validates the request, loads recent history from Postgres, sanitizes input.
2. `orchestrator.handle_message()`:
   - Runs the **prompt-injection guard** (`llm_service.complete` with `GUARD_SYSTEM_PROMPT`) — a cheap classifier call that blocks messages trying to manipulate the assistant itself (e.g. "ignore your instructions"), independent of the retrieved content.
   - Calls `retrieval.retrieve()` — embeds the question, queries Pinecone, filters by `CHATBOT_MIN_SCORE`.
   - Builds the user turn via `prompts.build_user_turn()`, which wraps retrieved chunks in a clearly delimited "Reference material (untrusted data)" block — this, plus the system prompt's explicit instruction to never treat retrieved content as commands, is the main prompt-injection defense.
   - Streams the answer via `llm_service.stream_reply()`.
3. `routes.py` streams `sources` then `token` events as SSE, persists the final assistant message, and the browser renders it live.

## Installation & configuration

```bash
cd ai_resume_match
uv sync                       # installs pinecone, httpx, pytest (new deps) alongside existing ones
cp .env.example .env           # fill in real values — see below
alembic upgrade head           # creates chatbot_sessions / chatbot_messages / chatbot_leads
python -m app.chatbot.knowledge.ingest   # one-time: embed + upsert the knowledge base into Pinecone
uvicorn app.main:app --reload --port 8000
```

In the `modax` repo:

```bash
cd modax
npm install                    # installs react-markdown, remark-gfm (new)
cp .env.example .env.local      # or add CHATBOT_BACKEND_URL / CHATBOT_INTERNAL_API_KEY to your .env
npm run dev
```

### Required environment variables

All chatbot env vars are listed with defaults in `ai_resume_match/.env.example`
and `modax/.env.example`. The ones you must actually set to go live:

| Variable | Where | Purpose |
|---|---|---|
| `OPENAI_API_KEY` | backend | Already required by the resume matcher; reused for chat + embeddings |
| `PINECONE_API_KEY` | backend | Vector database |
| `RESEND_API_KEY` | backend | Lead notification emails (same Resend account as the site's contact form) |
| `CHATBOT_INTERNAL_API_KEY` | **both** | Shared secret between the Next.js proxy and the FastAPI backend — must match in both `.env` files |
| `CHATBOT_BACKEND_URL` | frontend | Where the Next.js proxy forwards to (e.g. `https://api.modax.in` in production) |

Everything else (model names, timeouts, rate limits, prompts, suggested
prompts, greeting) has a sensible default and is overridable without a
redeploy of code — only of config.

## Database

Three new Postgres tables, added via Alembic migration
`c8f1a4b9d3e7_chatbot_tables.py` (run `alembic upgrade head`):

- **`chatbot_sessions`** — one row per browser session (`session_id`, the originating `page_url`, timestamps). No user account required.
- **`chatbot_messages`** — every turn (`role`, `content`, and `sources` used to ground assistant replies), keyed by `session_id`.
- **`chatbot_leads`** — captured leads (`name`, `email`, `requirements`, etc.), `UNIQUE(session_id)` so a session can only submit once (duplicate-submission prevention), plus `conversation_summary` and `notified_at`.

None of this touches the existing `users` / `conversations` tables used by the
resume matcher.

## Vector store (Pinecone)

A single serverless index (`PINECONE_INDEX_NAME`, default
`modax-chatbot-kb`) holds the knowledge base in namespace
`PINECONE_NAMESPACE` (default `website-kb`). `app/chatbot/vector_store.py`
creates the index on first ingestion run if it doesn't exist
(`vector_store.ensure_index()`), using `CHATBOT_EMBEDDING_DIMENSIONS` (1536
for `text-embedding-3-small`) and cosine similarity.

Swapping to a different vector DB means rewriting `vector_store.py` alone —
`retrieval.py` and the ingestion pipeline only call its four functions
(`ensure_index`, `upsert_chunks`, `query`, `delete_all`).

## Updating the knowledge base

Content is **not** scraped live — it's curated, versioned JSON under
`app/chatbot/knowledge/content/*.json`, one file per site section
(`company.json`, `services.json`, `hr.json`, `contact.json`,
`product_screenr.json`, `product_rawnn.json`, `products_overview.json`,
`faq.json`). Each entry has `id`, `url`, `title`, `section`, `content_type`,
`text`.

**To update the chatbot's knowledge after changing the live site:**

1. Edit the relevant JSON file (or add a new one) to reflect the new copy. Keep `url` pointing at the real page.
2. Run the ingestion pipeline:
   ```bash
   python -m app.chatbot.knowledge.ingest           # upserts changed/new chunks
   python -m app.chatbot.knowledge.ingest --reset    # or: wipe + re-ingest everything
   ```
   Chunk ids are derived deterministically from each item's `id`, so re-running after an edit overwrites the right vectors instead of duplicating them.
3. No restart needed — retrieval reads from Pinecone at request time.

`tests/chatbot/test_loader.py` guards against duplicate ids / malformed
entries in these files.

## Changing the LLM provider

Everything provider-specific is behind `app/chatbot/llm_service.py` (chat) and
`app/chatbot/embeddings.py` (embeddings). To switch providers:

1. Add a branch in `embeddings.get_embeddings_client()` / a new client in `llm_service._build_chat_model()` for the new provider's LangChain integration.
2. Update `CHATBOT_LLM_PROVIDER` / `CHATBOT_EMBEDDING_PROVIDER` and the corresponding model env vars.
3. If the new embedding model has a different vector size, update `CHATBOT_EMBEDDING_DIMENSIONS` and re-ingest with `--reset` (Pinecone indexes are fixed-dimension).

Nothing in `orchestrator.py`, `retrieval.py`, or the routes needs to change.

## How lead notifications work

1. Visitor fills the in-widget lead form (name, email, requirements; company/budget/preferred-contact optional) and submits.
2. `POST /api/chatbot/lead` → `lead_service.submit_lead()`:
   - If a lead already exists for this `session_id`, returns it as-is (no duplicate email, no duplicate row).
   - Otherwise builds a conversation summary from the session's message history, saves the lead, and calls `email_service.send_lead_notification()`.
3. `email_service.py` calls Resend's REST API directly (`POST https://api.resend.com/emails`) with the same `RESEND_API_KEY` and destination (`LEAD_NOTIFICATION_EMAIL`, default `vnaveen894@gmail.com`) as the site's existing contact form — reusing the integration at the provider level, since this backend is Python rather than the Node SDK the site uses.
4. If the email fails, the lead is still safely stored (`notified_at` stays `null`); the failure is logged, not surfaced to the visitor as an error.

## API endpoints

All under `/api/chatbot` (mounted in `app/main.py`), rate-limited per client IP via `slowapi`:

| Method | Path | Rate limit | Description |
|---|---|---|---|
| POST | `/api/chatbot/session` | `CHATBOT_RATE_LIMIT_SESSION` (10/min) | Creates a session; returns `session_id`, greeting, suggested prompts |
| DELETE | `/api/chatbot/session/{id}` | 10/min | Clears message history for a session (conversation reset) |
| POST | `/api/chatbot/message` | `CHATBOT_RATE_LIMIT_MESSAGE` (20/min) | Streams the assistant's reply as SSE (`sources`, `token`, `done`/`error` events) |
| POST | `/api/chatbot/lead` | `CHATBOT_RATE_LIMIT_LEAD` (5/hour) | Submits a captured lead |

If `CHATBOT_INTERNAL_API_KEY` is set, every request must include header
`X-Chatbot-Key: <that value>` — the Next.js proxy sends it automatically.

## Local development

Backend: `uvicorn app.main:app --reload --port 8000` (docs at `/docs`).
Frontend: `npm run dev` in `modax`, with `CHATBOT_BACKEND_URL=http://localhost:8000`.
The widget appears bottom-right on every page (mounted once in `app/layout.js`).

## Deployment

- Deploy this backend however the resume matcher is already deployed (it's the same FastAPI app); run `alembic upgrade head` as part of the release.
- Run `python -m app.chatbot.knowledge.ingest` once against production Pinecone after the first deploy, and again whenever `knowledge/content/*.json` changes.
- Set `CHATBOT_BACKEND_URL` on the `modax` deployment to the backend's public URL, and `CHATBOT_INTERNAL_API_KEY` identically on both sides.
- Set `CHATBOT_ENABLED=false` on the backend to turn the chatbot off instantly (returns 503) without a redeploy, e.g. during an incident.

## Troubleshooting

- **Widget shows "Unable to start the chat assistant"**: check `CHATBOT_BACKEND_URL` is reachable from the Next.js server, and that `CHATBOT_INTERNAL_API_KEY` matches on both sides (a mismatch returns 401, which the proxy currently surfaces as a generic failure).
- **Chatbot answers "I don't have confirmed information" for things that are on the site**: the knowledge base likely needs re-ingesting (`python -m app.chatbot.knowledge.ingest`), or `CHATBOT_MIN_SCORE` is too strict. `text-embedding-3-small` cosine scores for genuinely relevant short chunks typically land around 0.3–0.7, not 0.8+ — check actual scores for your content via Pinecone's console search (Database → your index → Browser → Search by ID on a known-good id) before raising this above the `0.3` default.
- **429 responses**: rate limit hit; tune `CHATBOT_RATE_LIMIT_MESSAGE` / `_LEAD` / `_SESSION`.
- **Lead emails not arriving**: check `RESEND_API_KEY` and `LEAD_NOTIFICATION_EMAIL` in the backend's `.env`; the lead itself is still saved in `chatbot_leads` even if the email fails — check `notified_at IS NULL` rows.
- **`alembic upgrade head` fails on a pre-existing DB**: same caveat as the existing migrations — if tables were ever created by `Base.metadata.create_all` before migrations existed, see the stamp instructions in the main `README.md`.

## Tests

```bash
cd ai_resume_match && uv run pytest tests/ -q      # 42 tests: chunking, retrieval, orchestrator
                                                     # (incl. prompt-injection scenarios), lead
                                                     # capture, email, full API (incl. rate limiting)
cd modax && npm test                                # widget open/close/greeting/lead-form tests
```

All backend tests run against an in-memory SQLite DB and mock OpenAI/Pinecone/Resend — no live
credentials or network access are required to run them.
