from typing import List, Optional
from pydantic import BaseModel

class LoginRequest(BaseModel):
    username: str
    password: str

class RegisterRequest(BaseModel):
    username: str
    password: str
    display_name: Optional[str] = None
    role: str = "user"

class UserResponse(BaseModel):
    id: int
    username: str
    display_name: str
    role: str
    created_at: str

class TokenResponse(BaseModel):
    token: str
    user: UserResponse

class ForecastRequest(BaseModel):
    station_code: str
    prediction_length: int = 72
    context_length: int = 72
    mode: str = "univariate"
