from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
import bcrypt

from ..database import get_db
from ..models import User
from ..auth.jwt import create_token
from ..auth.middleware import get_current_user, require_role
from ..schemas import LoginRequest, RegisterRequest, TokenResponse, UserResponse

router = APIRouter(prefix="/api/auth", tags=["auth"])

def user_to_response(u: User) -> dict:
    return {
        "id": u.id, "username": u.username, "display_name": u.display_name,
        "role": u.role, "created_at": u.created_at.strftime("%Y-%m-%d %H:%M") if u.created_at else ""
    }

@router.post("/login")
def login(req: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == req.username).first()
    if not user or not bcrypt.checkpw(req.password.encode(), user.password_hash.encode()):
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    token = create_token(user.id, user.role)
    return TokenResponse(token=token, user=UserResponse(**user_to_response(user)))

@router.post("/register")
def register(req: RegisterRequest, user: dict = Depends(require_role("admin", "super_admin")), db: Session = Depends(get_db)):
    if db.query(User).filter(User.username == req.username).first():
        raise HTTPException(status_code=400, detail="用户名已存在")
    if req.role not in ("user", "admin", "super_admin"):
        raise HTTPException(status_code=400, detail="无效的角色")
    if req.role == "super_admin" and user.get("role") != "super_admin":
        raise HTTPException(status_code=403, detail="只有超级管理员可以创建超级管理员")
    pw_hash = bcrypt.hashpw(req.password.encode(), bcrypt.gensalt()).decode()
    new_user = User(username=req.username, password_hash=pw_hash, display_name=req.display_name, role=req.role)
    db.add(new_user); db.commit(); db.refresh(new_user)
    return UserResponse(**user_to_response(new_user))

@router.get("/me")
def me(user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    u = db.query(User).filter(User.id == user["user_id"]).first()
    if not u: raise HTTPException(status_code=404, detail="用户不存在")
    return {"user": user_to_response(u)}

@router.get("/users")
def list_users(user: dict = Depends(require_role("admin", "super_admin")), db: Session = Depends(get_db)):
    users = db.query(User).order_by(User.id).all()
    return {"users": [user_to_response(u) for u in users]}

@router.delete("/users/{user_id}")
def delete_user(user_id: int, user: dict = Depends(require_role("super_admin")), db: Session = Depends(get_db)):
    target = db.query(User).filter(User.id == user_id).first()
    if not target: raise HTTPException(status_code=404, detail="用户不存在")
    db.delete(target); db.commit()
    return {"ok": True}
