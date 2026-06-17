from typing import List, Optional
from pydantic import BaseModel

class LoginRequest(BaseModel):
    username: str
    password: str

class RegisterRequest(BaseModel):
    username: str
    password: str
    display_name: str
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

class DataQuery(BaseModel):
    station_code: str
    begin_time: str = ""
    end_time: str = ""
    count: int = 200
    device_code: Optional[str] = None

class ForecastRequest(BaseModel):
    station_code: str
    prediction_length: int = 72
    context_length: int = 72
    mode: str = "univariate"
