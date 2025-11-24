import os
import asyncio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from app import auth_routes
from app.util.db import Base, engine
from app.resume_match import router as match_router

app = FastAPI(title="AI Resume Matcher")

# ✅ CORS setup
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # later restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ✅ Include routes
app.include_router(match_router, prefix="/api")
app.include_router(auth_routes.router, prefix="/api")

# ✅ Environment variables for DB config
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("PASSWORD", "1234")
DB_HOST = os.getenv("HOST", "localhost")
DB_PORT = os.getenv("PORT", "5432")
DB_NAME = os.getenv("NAME", "ai_resume_matcher")

CHECKPOINT_DB_URL = (
    f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
)

# ✅ LangGraph checkpoint setup
async def setup_checkpoints():
    async with AsyncPostgresSaver.from_conn_string(CHECKPOINT_DB_URL) as saver:
        await saver.setup()  # Creates checkpoint table if missing
checkpoint_task = None
# ✅ Startup event (creates tables + checkpoints)
@app.on_event("startup")
async def on_startup():
    global checkpoint_task  # allow assignment to global var

    # Create SQLAlchemy tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Run checkpoint setup in background (and store reference)
    checkpoint_task = asyncio.create_task(setup_checkpoints())
