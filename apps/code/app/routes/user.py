from fastapi import APIRouter, Response, HTTPException, status, Request, Depends
from sqlmodel import Session, select
from app.models import Problem, FrontEnd_Problem, User, FrontEnd_User, FrontEnd_Role
from app.database import get_session
import bcrypt
import json
import datetime
from app.routes.response import api_response, is_admin
import uuid
router = APIRouter(
    prefix="/api/users",
    tags=["users"]
)

# 共5个接口，分别是创建管理员账户、用户注册、查询用户信息、用户权限变更、用户列表查询

@router.post('/admin')
async def create_admin(user_info: FrontEnd_User, response: Response, request: Request):
    """Create admin"""
    
    # 处理401和403异常
    session_user_id = request.session.get("user_id")
    session_role = request.session.get("role")
    if not session_user_id:
        return api_response(401, "未登录", response=response)
    if session_role != "admin":
        return api_response(403, "权限不足", response=response)
    
    # 处理400异常
    field = ["username", "password"]
    missing = [f for f in field if getattr(user_info, f, None) in (None, "")]
    if missing or not (len(user_info.username) >= 3 and len(user_info.username) <= 40) or not len(user_info.password) >= 6:
        return api_response(400, f"参数错误", response=response)
    
    with get_session() as session:
        user = session.exec(select(User).where(User.username == user_info.username)).first()
        if user is not None:
            return api_response(400, "用户名已存在", response=response)
        user = User(
            user_id=uuid.uuid4().hex,
            username=user_info.username,
            password=bcrypt.hashpw(user_info.password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8"),
            join_time=datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).strftime("%Y-%m-%d"),
            role="admin",
            submit_count=0,
            resolve_count=0
        )
        session.add(user)
        session.commit()
        return api_response(200, "success", response=response, data={
            "user_id": user.user_id,
            "username": user.username
        })

@router.post('/')
async def register(user_info: FrontEnd_User, response: Response, request: Request):
    """User register"""
    
    # 处理400异常
    field = ["username", "password"]
    missing = [f for f in field if getattr(user_info, f, None) in (None, "")]
    if missing or not (len(user_info.username) >= 3 and len(user_info.username) <= 40) or not len(user_info.password) >= 6:
        return api_response(400, f"参数错误", response=response)
    
    with get_session() as session:
        user = session.exec(select(User).where(User.username == user_info.username)).first()
        if user:
            return api_response(400, "用户名已存在", response=response)
        
        user = User(
            user_id=uuid.uuid4().hex,
            username=user_info.username,
            password=bcrypt.hashpw(user_info.password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8"),
            join_time=datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).strftime("%Y-%m-%d"),
            role="user",
            submit_count=0,
            resolve_count=0
        )
        session.add(user)
        session.commit()
        session.refresh(user)
        return api_response(200, "register success", response=response, data={
            "user_id": user.user_id,
        })

@router.get('/{user_id}')
async def get_user(user_id: str, response: Response, request: Request):
    """Get user information"""
    
    session_user_id = request.session.get("user_id")
    session_role = request.session.get("role")
    
    # 处理401异常
    if not session_user_id:
        return api_response(401, "未登录", response=response)
    
    # 处理403异常
    if session_user_id != user_id and session_role != "admin":
        return api_response(403, "权限不足", response=response)
    
    with get_session() as session:
        user = session.exec(select(User).where(User.user_id == user_id)).first()
        
        # 处理404异常
        if user is None:
            return api_response(404, "用户不存在", response=response)
        
        return api_response(200, "success", response=response, data={
            "user_id": user.user_id,
            "username": user.username,
            "role": user.role
        })
    
@router.put('/{user_id}/role')
async def update_user_role(user_id: str, role_info: FrontEnd_Role, response: Response, request: Request):
    """Update user role"""
    role = role_info.role
    
    
    
    # 处理401和403异常
    session_user_id = request.session.get("user_id")
    session_role = request.session.get("role")
    if not session_user_id:
        return api_response(401, "未登录", response=response)
    if session_role != "admin":
        return api_response(403, "权限不足", response=response)
    
    # 处理400异常
    field = ["role"]
    missing = [f for f in field if getattr(role_info, f, None) in (None, "")]
    if missing or not isinstance(role_info.role, str):
        return api_response(400, f"参数错误", response=response)
    
    with get_session() as session:
        user = session.exec(select(User).where(User.user_id == user_id)).first()
        
        # 处理404异常
        if user is None:
            return api_response(404, "用户不存在", response=response)
        
        user.role = role
        session.add(user)
        session.commit()

        return api_response(200, "role updated", response=response, data={
            "user_id": user.user_id,
            "role": user.role
        })
    
@router.get('/')
async def get_users(response: Response, request: Request, page: int = 1, page_size: int = 20):
    """List All Users"""
    
    # 处理403异常
    if not is_admin(request):
        return api_response(403, "权限不足", response=response)
    
    page = max(1, page)
    page_size = max(1, page_size)
    
    with get_session() as session:
        total = len(session.exec(select(User)).all())
        users = session.exec(select(User).offset((page - 1) * page_size).limit(page_size)).all()
        users_return = []
        for user in users:
            users_return.append(
                {
                    "user_id": user.user_id,
                    "username": user.username,
                    "role": user.role,
                    "join_time": user.join_time,
                    "submit_count": user.submit_count,
                    "resolve_count": user.resolve_count
                }
            )
        return api_response(200, "success", response=response, data={
            "total": total,
            "users": users_return
        })
