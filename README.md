# AI Resume Matcher — Backend

FastAPI + LangGraph service that parses a resume and a job description, compares skills, and returns a match score with reasoning. Results stream to the client as Server-Sent Events.

Frontend: [`ai_resume_matcher_fed`](../ai_resume_matcher_fed).

This backend also hosts the **Modax website AI chatbot** (`app/chatbot/`) — a separate feature
unrelated to resume matching, sharing this repo for deployment convenience for now. See
[`CHATBOT.md`](./CHATBOT.md) for its architecture, setup, and docs. Its frontend widget lives in
the `modax` repo.

## Pipeline

```
START ─┬─> parse_resume ─┐
       └─> parse_jd ─────┴─> skill_chain ─> reasoning_chain ─> END
```

`parse_resume` and `parse_jd` run in parallel; `skill_chain` waits for both. Models per node are set in `llm_config.json`. Graph state is checkpointed to Postgres so follow-up chat (`/api/chat/{thread_id}`) can reuse the parsed summaries.

## Requirements

- Python 3.13
- PostgreSQL (running locally or reachable over the network)
- An OpenAI API key
- For `.doc` uploads only: `antiword` (`brew install antiword`). `.pdf`, `.docx` and `.txt` work without extra tools.

## Setup

1. Create the database:

   ```bash
   createdb -U postgres ai_resume_matcher
   ```

2. Create a `.env` in the project root:

   ```env
   OPENAI_API_KEY=sk-...          # read automatically by langchain_openai.ChatOpenAI

   # Postgres
   HOST=localhost
   PORT=5432
   NAME=ai_resume_matcher
   DB_USER=postgres
   PASSWORD=your-db-password

   # Auth. Generate the key with: python -c "import secrets; print(secrets.token_urlsafe(64))"
   JWT_SECRET_KEY=
   ACCESS_TOKEN_EXPIRE_MINUTES=10080   # 7 days
   # Only for accounts created before passwords were bcrypt-hashed. They are re-hashed on
   # their next login; remove this once they have all logged in (or reset their passwords).
   LEGACY_PASSWORD_CIPHER_KEY=

   # Credits charged per request (users start with 3.0)
   MATCH_RUN_COST=0.03
   CHAT_MESSAGE_COST=0.002

   # Optional, only used if file uploads to S3 are re-enabled
   S3_ACCESS_KEY_ID=
   S3_SECRET_ACCESS_KEY=
   S3_REGION=ap-south-1
   S3_BUCKET=
   ```

   Note: `PORT` here is the **database** port. Some hosts (Heroku, Render, Railway) set `PORT` for the web server, so set it explicitly when deploying.

3. Install dependencies:

   ```bash
   uv sync
   # or: python -m venv .venv && source .venv/bin/activate && pip install -e .
   ```

4. Apply migrations:

   ```bash
   alembic upgrade head
   ```

   On a database that was created by the app before migrations were tracked (tables exist but
   `alembic_version` is empty), run `alembic stamp 6d7b8dfb3d1e` first.

## Run

```bash
uvicorn app.main:app --reload --port 8000
```

On startup the app creates its tables and the LangGraph checkpoint tables if they don't exist. API docs: http://127.0.0.1:8000/docs

## API

| Method | Path | Description |
| --- | --- | --- |
| POST | `/api/auth/signup` | `{email, password}` → `{access_token}` |
| POST | `/api/auth/login` | `{email, password}` → `{access_token}` |
| POST | `/api/match` | Multipart form: `resume_text` or `resume_file`, `jd_text` or `jd_file`. Streams SSE events, one per graph node, then `{"status": "completed"}` (or `{"status": "error"}`) |
| GET | `/api/match/{thread_id}` | Stored results of a past match (same shape as the streamed chunks) |
| POST | `/api/chat/{thread_id}` | `{question}`. Streams SSE `{"type": "token"}` events then `{"type": "done", "answer"}`. Uses the last 10 messages as context. Questions unrelated to the resume/job match are refused (and not charged) |
| GET | `/api/chat/{thread_id}` | Chat history for a match |
| GET | `/api/conversations` | The current user's past matches |

All endpoints except auth need `Authorization: Bearer <token>`. Matches are only charged once they complete.
