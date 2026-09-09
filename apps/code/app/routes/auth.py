from fastapi import APIRouter, Response, HTTPException, status, Request, Depends
from sqlmodel import Session, select
from app.models import Problem, FrontEnd_Problem, User, FrontEnd_User, FrontEnd_Role
from app.database import get_session
import bcrypt
import json
import datetime
from app.routes.response import api_response, is_admin

router = APIRouter(
    prefix="/api/auth",
    tags=["auth"]
)

# 共2个接口，分别是用户登录、用户登出

@router.post('/login')
async def login(user_info: FrontEnd_User, response: Response, request: Request):
    """User login"""
    
    # 处理400异常
    field = ["username", "password"]
    missing = [f for f in field if getattr(user_info, f, None) in (None, "")]
    if missing or not isinstance(user_info.username, str) or not isinstance(user_info.password, str):
        return api_response(400, f"参数错误", response=response)
    
    with get_session() as session:
        user = session.exec(select(User).where(User.username == user_info.username)).first()
        
        # 处理401和403异常
        if user is None:
            return api_response(401, "用户名或密码错误", response=response)
        if not bcrypt.checkpw(user_info.password.encode('utf-8'), user.password.encode('utf-8')):
            return api_response(401, "用户名或密码错误", response=response)
        if user.role == 'banned':
            return api_response(403, "用户被禁用", response=response)
        
        # 设置会话信息, SessionMiddleware会自动处理cookie
        request.session["user_id"] = user.user_id
        request.session["role"] = user.role
        
        return api_response(200, "login success", response=response, data={
            "user_id": user.user_id,
            "username": user.username,
            "role": user.role
        })


@router.post('/logout')
async def logout(response: Response, request: Request):
    """User logout"""
    
    # 处理401异常
    user_self = request.session.get("user_id")
    if not user_self:
        return api_response(401, "未登录", response=response)
    
    # 清除会话, SessionMiddleware会自动处理cookie
    request.session.clear()
    
    return api_response(200, "logout success", response=response, data=None)