from fastapi import APIRouter, Response, status, Request, Depends, UploadFile, File
from sqlmodel import Session, select
from app.models import Problem, FrontEnd_Problem, User, FrontEnd_Visibility
from app.database import get_session
import json
from app.routes.response import api_response, is_admin

router = APIRouter(
    prefix="/api/problems",
    tags=["problems"]
)

# 共4+1+3个接口，分别是查看题目列表、添加题目、删除题目、查看题目信息 + 修改可视条件 + 新建特判、删除特判、查看特判

@router.get("/")
async def get_problems_list(response: Response, request: Request):
    """List all problems"""
    
    # 0713更新，验证是否登录
    # 处理401异常
    session_user_id = request.session.get("user_id")
    if not session_user_id:
        return api_response(401, "未登录", response=response)
    
    with get_session() as session:
        problems = session.exec(select(Problem)).all()
        return api_response(200, "success", response=response, data=[{"id": p.id, "title": p.title, "difficulty": p.difficulty if p.difficulty else '', "source": p.source if p.source else '', "author": p.author if p.author else ''} for p in problems])

@router.post("/")
async def add_problem(problem_info: FrontEnd_Problem, response: Response, request: Request):
    """Add a new problem"""
    
    # 处理401异常（所有已登录用户均可添加题目）
    session_user_id = request.session.get("user_id")
    
    if not session_user_id:
        return api_response(401, "未登录", response=response)
    
    # 无需处理403异常，所有已登录用户均可添加题目
    # if not is_admin(request):
    #     return api_response(403, "权限不足", response=response)
    
    # 处理400异常
    field = ["id", "title", "description", "input_description", "output_description", "samples", "constraints", "testcases"]
    missing = [f for f in field if getattr(problem_info, f, None) in (None, "")]
    
    if missing: # 存疑，是否需要验证类型不一致
        return api_response(400, "字段缺失", response=response)
    
    with get_session() as session:
        # 处理409异常
        if session.exec(select(Problem).where(Problem.id == problem_info.id)).first():
            return api_response(409, "id已存在", response=response)

        # FrontEnd_Problem 转换为 Problem (dict方法已被弃用，改为model_dump)
        problem = Problem.from_dict(problem_info.model_dump())
        
        session.add(problem)
        session.commit()
        return api_response(200, "add success", response=response, data={"id": problem.id, "title": problem.title})

@router.get("/{problem_id}")
async def get_problem_info(problem_id: str, response: Response, request: Request):
    """Get problem info by id"""
    
    # 0713更新，验证是否登录
    # 处理401异常
    session_user_id = request.session.get("user_id")
    if not session_user_id:
        return api_response(401, "未登录", response=response)
    
    with get_session() as session:
        problem = session.exec(select(Problem).where(Problem.id == problem_id)).first()
        if not problem:
            return api_response(404, "题目不存在", response=response)

        return api_response(200, "success", response=response, data=problem.to_dict())

@router.delete("/{problem_id}")
async def delete_problem(problem_id: str, response: Response, request: Request):
    """Delete problem by id"""
    
    # 处理401和403异常
    session_user_id = request.session.get("user_id")
    session_user_role = request.session.get("role")
    if not session_user_id:
        return api_response(401, "未登录", response=response)
    if session_user_role != "admin":
        return api_response(403, "权限不足", response=response)
    with get_session() as session:
        problem = session.exec(select(Problem).where(Problem.id == problem_id)).first()
        if not problem:
            return api_response(404, "题目不存在", response=response)
            
        session.delete(problem)
        session.commit()
        return api_response(200, "delete success", response=response, data={"id": problem.id, "title": problem.title})
    
    
@router.put('/{problem_id}/log_visibility')
async def update_problem_visibility(problem_id: str, visibility: FrontEnd_Visibility, response: Response, request: Request):
    """Update problem log visibility"""
    # 处理400异常
    if not isinstance(visibility.public_cases, bool):
        return api_response(400, "参数错误", response=response)
    
    # 处理401和403异常
    session_user_id = request.session.get("user_id")
    session_role = request.session.get("role")
    if not session_user_id:
        return api_response(401, "未登录", response=response)
    if session_role != "admin":
        return api_response(403, "权限不足", response=response)
    
    with get_session() as session:
        problem = session.exec(select(Problem).where(Problem.id == problem_id)).first()
        
        # 处理404异常
        if not problem:
            return api_response(404, f"题目不存在", response=response)
        
        # 更新可见性
        problem.public_cases = visibility.public_cases
        session.commit()
        return api_response(200, "log visibility updated", response=response, data={
            "problem_id": problem_id,
            "public_cases": visibility.public_cases
        })

@router.post('/{problem_id}/spj')
async def update_problem_spj(problem_id: str, response: Response, request: Request, file: UploadFile = File(...), language: str = "python"):
    """Set problem spj and upload spj program"""
    
    # 处理401和403异常
    session_user_id = request.session.get("user_id")
    session_role = request.session.get("role")
    if not session_user_id:
        return api_response(401, "未登录", response=response)
    if session_role != "admin":
        return api_response(403, "权限不足", response=response)
    
    # 处理400异常
    if not file:
        return api_response(400, "缺少SPJ脚本文件", response=response)
    
    # 检查文件类型
    if not file.filename.endswith(('.py', '.cpp', '.c', '.java')):
        return api_response(400, "不支持的文件类型", response=response)
    
    # 读取文件内容
    spj_code = await file.read()
    spj_code_str = spj_code.decode('utf-8')
    
    # 简单安全检查
    unsafe_patterns = ['os.system', 'subprocess', 'exec(', 'eval(', '__import__']
    if any(pattern in spj_code_str for pattern in unsafe_patterns):
        return api_response(400, "特判代码包含不安全操作", response=response)
    
    with get_session() as session:
        problem = session.exec(select(Problem).where(Problem.id == problem_id)).first()
        
        # 处理404异常
        if not problem:
            return api_response(404, "题目不存在", response=response)
        
        problem.judge_mode = 'spj'
        problem.spj_code = spj_code_str
        problem.spj_language = language
        
        session.commit()
        
        return api_response(200, "success", response=response, data={
            "problem_id": problem_id,
            "judge_mode": problem.judge_mode
        })

@router.delete('/{problem_id}/spj')
async def delete_problem_spj(problem_id: str, response: Response, request: Request):
    """Delete problem spj"""
    # 处理401和403异常
    session_user_id = request.session.get("user_id")
    session_role = request.session.get("role")
    if not session_user_id:
        return api_response(401, "未登录", response=response)
    if session_role != "admin":
        return api_response(403, "权限不足", response=response)
    
    with get_session() as session:
        problem = session.exec(select(Problem).where(Problem.id == problem_id)).first()
        # 处理404异常
        if not problem:
            return api_response(404, "题目不存在", response=response)
        
        problem.judge_mode = 'standard'
        problem.spj_code = None
        problem.spj_language = None
        
        session.commit()
        
        return api_response(200, "delete spj success", response=response, data={
            "problem_id": problem_id,
            "judge_mode": problem.judge_mode
        })

@router.get('/{problem_id}/judge_mode')
async def get_problem_judge_mode(problem_id: str, response: Response, request: Request):
    """Get problem judge mode and spj info"""
    # 处理401和403异常
    session_user_id = request.session.get("user_id")
    session_role = request.session.get("role")
    if not session_user_id:
        return api_response(401, "未登录", response=response)
    if session_role != "admin":
        return api_response(403, "权限不足", response=response)
    
    with get_session() as session:
        problem = session.exec(select(Problem).where(Problem.id == problem_id)).first()
        if not problem:
            return api_response(404, "题目不存在", response=response)
        
        # 返回评测模式及SPJ信息
        response_data = {
            "problem_id": problem_id,
            "judge_mode": problem.judge_mode
        }
        
        # 如果是SPJ模式，返回SPJ相关信息
        if problem.judge_mode == 'spj' and problem.spj_code:
            response_data["spj_language"] = problem.spj_language
            response_data["spj_code"] = problem.spj_code
            
        return api_response(200, "success", response=response, data=response_data)
