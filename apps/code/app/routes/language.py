from fastapi import APIRouter, Response, status, Request, Depends
from sqlmodel import Session, select
from app.models import Language, FrontEnd_Language
from app.database import get_session
import json
from app.routes.response import api_response, is_admin
from app.judge import run_code
import datetime
import uuid

router = APIRouter(
    prefix="/api/languages",
    tags=["languages"]
)

@router.post('/')
async def create_language(language_info: FrontEnd_Language, response: Response, request: Request):
    """Create language"""

    
    
    # 处理401和403异常（0713更新，所有已登录用户均可注册语言，无需403）
    session_user_id = request.session.get("user_id")
    session_role = request.session.get("role")
    if not session_user_id:
        return api_response(401, "未登录", response=response)
    # if session_role != "admin":
    #     return api_response(403, "权限不足", response=response)
    
    # 处理400异常
    field = ["name", "file_ext", "run_cmd"]
    missing = [f for f in field if getattr(language_info, f, None) in (None, "")]
    if missing or not isinstance(language_info.name, str) or not isinstance(language_info.file_ext, str) or not isinstance(language_info.run_cmd, str):
        return api_response(400, f"参数错误", response=response)
    
    with get_session() as session:
        # 处理400异常
        language = session.exec(select(Language).where(Language.name == language_info.name)).first()
        if language:
            return api_response(400, f"该语言已存在", response=response)
        
        
        language = Language(
            name=language_info.name,
            file_ext=language_info.file_ext,
            compile_cmd=language_info.compile_cmd,
            run_cmd=language_info.run_cmd,
            source_template=language_info.source_template,
            time_limit=language_info.time_limit,
            memory_limit=language_info.memory_limit,
        )
        session.add(language)
        session.commit()
        return api_response(200, "language registered", response=response, data={"name": language.name})

@router.get('/')
async def get_languages(response: Response):
    """Get languages"""

    with get_session() as session:
        languages = session.exec(select(Language)).all()
        return api_response(200, "success", response=response, 
            data={"name":[language.name for language in languages]})