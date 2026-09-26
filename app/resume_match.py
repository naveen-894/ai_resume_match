import json
import asyncio
import logging
import os
import uuid
from app.models import Conversation, ConversationMessage, User
from app.util.s3 import upload_to_s3
from app.util.db import get_session
from app.util.dependencies import get_current_user
from fastapi import APIRouter, Form, UploadFile, File, HTTPException, Depends, Body
from fastapi.responses import StreamingResponse
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from app.graph import chat_graph, resume_parser_graph
from app.util.text_extraction import extract_text_from_file
from app.util.validations import clean_text, validate_file

router = APIRouter()
logger = logging.getLogger(__name__)
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("PASSWORD")
DB_HOST = os.getenv("HOST")
DB_PORT = os.getenv("PORT")
DB_NAME = os.getenv("NAME")

CHECKPOINT_DB_URL = (
    f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
)

@router.post("/match")
async def match_resume(
    jd_text: str = Form(None),
    resume_text: str = Form(None),
    jd_file: UploadFile = File(None),
    resume_file: UploadFile = File(None),
    current_user: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_session)
):
    MATCH_RUN_COST = float(os.getenv("MATCH_RUN_COST", 0.03))
    # 🪙 Check if user has credits
    if current_user.credits <= 0 or current_user.credits - MATCH_RUN_COST < 0:
        raise HTTPException(status_code=402, detail="Insufficient credits")
    # 🧾 Validate and extract text
    if jd_file:
        validate_file(jd_file, "jd")
        # jd_file_url = await upload_to_s3(jd_file, "jd")
        jd_text = await extract_text_from_file(jd_file)
        jd_text = clean_text(jd_text)
    elif not jd_text:
        raise HTTPException(status_code=400, detail="JD text or file is required")

    if resume_file:
        validate_file(resume_file, "resume")
        # resume_file_url = await upload_to_s3(resume_file, "resume")
        resume_text = await extract_text_from_file(resume_file)
        resume_text = clean_text(resume_text)
    elif not resume_text:
        raise HTTPException(status_code=400, detail="Resume text or file is required")
    thread = str(uuid.uuid4())
    convo = Conversation(
        user_id=current_user.id,
        thread_id=thread,
        jd_text=jd_text,
        resume_text=resume_text,
    )
    db.add(convo)
    await db.commit()
    # ⚙️ Stream processing
    async def event_stream():
        try:
            async with AsyncPostgresSaver.from_conn_string(CHECKPOINT_DB_URL) as checkpointer:
                graph = resume_parser_graph(checkpointer)
                total_steps = 4  # parse_resume, parse_jd, skill_chain, reasoning_chain
                current_step = 0
                match_result = {}

                async for chunk in graph.astream(
                    {"resume_text": resume_text, "jd_text": jd_text},
                    config={"configurable": {"thread_id": thread}}
                ):
                    current_step += 1
                    match_result.update(chunk)
                    progress = int((current_step / total_steps) * 100)
                    event_data = {
                        "progress": progress if progress <= 100 else 100,
                        "chunk": chunk,
                        "thread_id": thread,
                    }
                    yield f"data: {json.dumps(event_data)}\n\n"
                    await asyncio.sleep(0.05)
        except Exception:
            logger.exception("Match run failed for thread %s", thread)
            yield f"data: {json.dumps({'status': 'error', 'error': 'Something went wrong while analysing the match. Please try again.'})}\n\n"
            return
        yield f"data: {json.dumps({'progress': 100, 'status': 'completed'})}\n\n"
        # Only charge for runs that completed
        convo.match_result = match_result
        current_user.credits -= MATCH_RUN_COST
        await db.commit()
    
    return StreamingResponse(event_stream(), media_type="text/event-stream")


def _sections_from_state(values: dict) -> dict:
    """Rebuild the per-node sections (same shape as the streamed chunks) from graph state."""
    return {
        "parse_resume": {"resume_summary": values.get("resume_summary")},
        "parse_jd": {"jd_summary": values.get("jd_summary")},
        "skill_chain": {
            "skills_matching": values.get("skills_matching", []),
            "missing_skills": values.get("missing_skills", []),
        },
        "reasoning_chain": {
            "bullet_summary": values.get("bullet_summary"),
            "match_percentage": values.get("match_percentage"),
            "reasoning": values.get("reasoning"),
        },
    }


@router.get("/match/{thread_id}")
async def get_match_result(
    thread_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    res = await db.execute(select(Conversation).where(
        Conversation.thread_id == thread_id,
        Conversation.user_id == current_user.id
    ))
    convo = res.scalar_one_or_none()
    if not convo:
        raise HTTPException(status_code=404, detail="Thread not found")

    sections = convo.match_result
    if sections is None:
        # Matches run before match_result was stored: recover them from the checkpoint history.
        # The latest checkpoint can't be used directly because chat turns on the same thread drop
        # match-only fields, so walk back to the newest checkpoint that still has the final score.
        async with AsyncPostgresSaver.from_conn_string(CHECKPOINT_DB_URL) as checkpointer:
            graph = resume_parser_graph(checkpointer)
            async for snapshot in graph.aget_state_history({"configurable": {"thread_id": thread_id}}):
                if snapshot.values.get("match_percentage") is not None:
                    sections = _sections_from_state(snapshot.values)
                    break
        if sections is None:
            raise HTTPException(status_code=404, detail="No results found for this match")
        convo.match_result = sections
        await db.commit()

    return {"thread_id": thread_id, "sections": sections}


@router.post("/chat/{thread_id}")
async def continue_chat(
    thread_id: str,
    question: str = Body(..., embed=True),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    CHAT_MESSAGE_COST = float(os.getenv("CHAT_MESSAGE_COST", 0.002))
    if current_user.credits <= 0 or current_user.credits - CHAT_MESSAGE_COST < 0:
        raise HTTPException(status_code=402, detail="Insufficient credits")
    res = await db.execute(select(Conversation).where(
        Conversation.thread_id == thread_id,
        Conversation.user_id == current_user.id
    ))
    convo = res.scalar_one_or_none()
    if not convo:
        raise HTTPException(status_code=404, detail="Thread not found")
    # store the user's message
    result = await db.execute(
        select(ConversationMessage)
        .where(ConversationMessage.thread_id == thread_id)
        .order_by(ConversationMessage.created_at.desc())
        .limit(10)
    )
    history = [
        {"role": m.role, "message": m.message}
        for m in result.scalars().all()[::-1]
    ]
    db.add(ConversationMessage(
        thread_id=thread_id,
        user_id=current_user.id,
        role="user",
        message=question
    ))
    await db.commit()

    chat_input = {"thread_id": thread_id, "question": question, "history": history}
    if convo.match_result:
        # Prefer the stored result; otherwise the summaries are restored from the checkpoint
        chat_input["resume_summary"] = (convo.match_result.get("parse_resume") or {}).get("resume_summary")
        chat_input["jd_summary"] = (convo.match_result.get("parse_jd") or {}).get("jd_summary")

    # Stream the answer token by token as SSE: {"type": "token"} events, then "done" (or "error")
    async def event_stream():
        tokens = []
        answer = None
        refused = False
        try:
            async with AsyncPostgresSaver.from_conn_string(CHECKPOINT_DB_URL) as checkpointer:
                graph = chat_graph(checkpointer)
                async for mode, payload in graph.astream(
                    chat_input,
                    config={"configurable": {"thread_id": thread_id}},
                    stream_mode=["messages", "updates"],
                ):
                    if mode == "messages":
                        chunk, metadata = payload
                        # Only stream the answering model; the topic guard's classifier output is internal
                        if metadata.get("langgraph_node") == "answer" and chunk.content:
                            tokens.append(chunk.content)
                            yield f"data: {json.dumps({'type': 'token', 'content': chunk.content})}\n\n"
                    elif "answer" in payload:
                        answer = payload["answer"].get("answer")
                    elif "off_topic" in payload:
                        answer = payload["off_topic"].get("answer")
                        refused = True
        except Exception:
            logger.exception("Chat failed for thread %s", thread_id)
            yield f"data: {json.dumps({'type': 'error', 'error': 'Something went wrong while answering. Please try again.'})}\n\n"
            return

        answer = answer or "".join(tokens)
        # store the AI message; charge only for answered, in-scope questions
        db.add(ConversationMessage(
            thread_id=thread_id,
            user_id=current_user.id,   # optional you can store None for ai
            role="assistant",
            message=answer
        ))
        if not refused:
            current_user.credits -= CHAT_MESSAGE_COST
        await db.commit()
        yield f"data: {json.dumps({'type': 'done', 'thread_id': thread_id, 'answer': answer})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.get("/chat/{thread_id}")
async def get_chat_history(thread_id: str, 
                           current_user = Depends(get_current_user),
                           db: AsyncSession = Depends(get_session)):
    # verify user is owner of the thread
    result = await db.execute(
        select(Conversation).filter(
            Conversation.thread_id == thread_id,
            Conversation.user_id == current_user.id
        )
    )
    conversation = result.scalar_one_or_none()
    if not conversation:
        raise HTTPException(status_code=404, detail="Thread not found")

    # load messages
    result = await db.execute(
        select(ConversationMessage)
        .filter(ConversationMessage.thread_id == thread_id)
        .order_by(ConversationMessage.created_at.asc())
    )
    messages = result.scalars().all()

    return {
        "thread_id": thread_id,
        "messages": [
            {
                "id": m.id,
                "role": m.role,
                "content": m.message,
                "created_at": m.created_at.isoformat()
            }
            for m in messages
        ]
    }

@router.get("/conversations")
async def list_user_conversations(
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_session)
):
    result = await db.execute(
        select(Conversation).filter(Conversation.user_id == current_user.id).order_by(Conversation.created_at.desc())
    )
    conversations = result.scalars().all()

    def summary(conv):
        result = conv.match_result or {}
        return {
            "thread_id": conv.thread_id,
            "created_at": conv.created_at.isoformat(),
            "job_title": ((result.get("parse_jd") or {}).get("jd_summary") or {}).get("title"),
            "candidate_name": ((result.get("parse_resume") or {}).get("resume_summary") or {}).get("name"),
            "match_percentage": (result.get("reasoning_chain") or {}).get("match_percentage"),
        }

    return [summary(conv) for conv in conversations]