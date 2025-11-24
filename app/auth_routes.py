# routes/auth_routes.py
from sqlalchemy import select
from app.util.db import get_session
from fastapi import APIRouter, HTTPException, Depends
from .auth import create_access_token, encrypt_password, verify_password
from .models import User
from .schemas import UserCreate, UserLogin
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/auth", tags=["Auth"])

@router.post("/signup")
async def signup(user: UserCreate, db: AsyncSession = Depends(get_session)):
    # ✅ check existing email
    result = await db.execute(select(User).filter(User.email == user.email))
    db_user = result.scalar_one_or_none()

    if db_user:
        raise HTTPException(status_code=400, detail="Email already registered")

    # ✅ encrypt password instead of hashing
    encrypted_password = encrypt_password(user.password)

    new_user = User(email=user.email, hashed_password=encrypted_password)
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)

    # ✅ create access token
    access_token = create_access_token(data={"email": new_user.email, "user_id": str(new_user.id)})
    return {"access_token": access_token, "token_type": "bearer"}

@router.post("/login")
async def login(user: UserLogin, db: AsyncSession = Depends(get_session)):
    result = await db.execute(select(User).filter(User.email == user.email))
    db_user = result.scalar_one_or_none()

    if not db_user or not verify_password(user.password, db_user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    access_token = create_access_token(data={"email": db_user.email, "user_id": str(db_user.id)})
    return {"access_token": access_token, "token_type": "bearer"}