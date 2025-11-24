# schemas.py
from pydantic import BaseModel, EmailStr

class UserBase(BaseModel):
    email: EmailStr

# For signup (user creation)
class UserCreate(UserBase):
    password: str

# For login (authentication)
class UserLogin(UserBase):
    password: str

# For returning user info (optional)
class UserResponse(UserBase):
    id: int

    class Config:
        orm_mode = True
