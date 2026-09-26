# schemas.py
from pydantic import BaseModel, ConfigDict, EmailStr, field_validator

class UserBase(BaseModel):
    email: EmailStr

# For signup (user creation)
class UserCreate(UserBase):
    password: str

    @field_validator("password")
    @classmethod
    def password_fits_bcrypt(cls, v: str) -> str:
        # bcrypt only uses the first 72 bytes and the bcrypt library rejects longer input
        if len(v.encode()) > 72:
            raise ValueError("Password must be at most 72 bytes long")
        if not v:
            raise ValueError("Password is required")
        return v

# For login (authentication)
class UserLogin(UserBase):
    password: str

# For returning user info (optional)
class UserResponse(UserBase):
    id: int

    model_config = ConfigDict(from_attributes=True)
