import json
import asyncio
import os
import uuid
from app.models import Conversation, ConversationMessage, User
from app.util.cloudinary import upload_to_cloudinary
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
        # jd_file_url = await upload_to_cloudinary(jd_file)
        jd_text = await extract_text_from_file(jd_file)
        jd_text = clean_text(jd_text)
    elif not jd_text:
        raise HTTPException(status_code=400, detail="JD text or file is required")

    if resume_file:
        validate_file(resume_file, "resume")
        # resume_file_url = await upload_to_cloudinary(resume_file)
        resume_text = await extract_text_from_file(resume_file)
        resume_text = clean_text(resume_text)
    elif not resume_text:
        raise HTTPException(status_code=400, detail="Resume text or file is required")
    thread = str(uuid.uuid4())
    convo = Conversation(
        user_id=current_user.id,
        thread_id=thread
    )
    db.add(convo)
    await db.commit()
    # ⚙️ Stream processing
    async def event_stream():
        async with AsyncPostgresSaver.from_conn_string(CHECKPOINT_DB_URL) as checkpointer:
            graph = resume_parser_graph(checkpointer)
            total_steps = 5
            current_step = 0

            async for chunk in graph.astream(
                {"resume_text": resume_text, "jd_text": jd_text},
                config={"configurable": {"thread_id": thread}}
            ):
                current_step += 1
                progress = int((current_step / total_steps) * 100)
                event_data = {
                    "progress": progress if progress <= 100 else 100,
                    "chunk": chunk,
                    "thread_id": thread,
                }
                yield f"data: {json.dumps(event_data)}\n\n"
                await asyncio.sleep(0.05)
            yield f"data: {json.dumps({'progress': 100, 'status': 'completed'})}\n\n"
        current_user.credits -= MATCH_RUN_COST
        await db.commit()
    
    return StreamingResponse(event_stream(), media_type="text/event-stream")


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

    async with AsyncPostgresSaver.from_conn_string(CHECKPOINT_DB_URL) as checkpointer:
        graph = chat_graph(checkpointer)
        out = await graph.ainvoke(
            {"thread_id": thread_id, "question": question, "history": history},
            config={"configurable": {"thread_id": thread_id}},
        )
    answer = out.get("answer")

    # store the AI message
    db.add(ConversationMessage(
        thread_id=thread_id,
        user_id=current_user.id,   # optional you can store None for ai
        role="assistant",
        message=answer
    ))
    await db.commit()
    current_user.credits -= CHAT_MESSAGE_COST
    return {"thread_id": thread_id, "answer": answer}


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
        select(Conversation).filter(Conversation.user_id == current_user.id).order_by(Conversation.updated_at.desc())
    )
    conversations = result.scalars().all()

    return [
        {
            "thread_id": conv.thread_id,
            "created_at": conv.created_at.isoformat(),
        }
        for conv in conversations
    ]