from fastapi import UploadFile, File, APIRouter, Response, status, Request, Depends, BackgroundTasks
from sqlmodel import Session, select, SQLModel, create_engine
from app.models import Problem, FrontEnd_Problem, User, Submission, FrontEnd_Submission, Language, Log
from app.database import get_session
import bcrypt
import json
from app.routes.response import api_response, is_admin
from app.judge import run_code
import datetime
from app.database import reset_db, init_db, create_initial_admin, create_initial_language
import uuid

router = APIRouter(
    prefix="/api",
    tags=["others"]
)

@router.get('/logs/access')
async def get_logs(response: Response, request: Request, user_id: str = None, 
                problem_id: str = None, page: int = None, page_size: int = None):
    
    # 处理400异常？貌似不会400异常。
    
    # 处理401和403异常
    session_user_id = request.session.get('user_id')
    session_user_role = request.session.get('role')
    if not session_user_id:
        return api_response(401, "用户未登录", response=response)
    if session_user_role != 'admin':
        return api_response(403, "权限不足", response=response)
    
    with get_session() as session:
        logs = session.exec(select(Log)).all()
        if user_id:
            logs = [log for log in logs if log.user_id == user_id]
        if problem_id:
            logs = [log for log in logs if log.problem_id == problem_id]
        if page and page_size:
            logs = logs[(page - 1) * page_size: page * page_size]
            
        logs_return = []
        for log in logs:
            logs_return.append({
                "user_id": log.user_id,
                "problem_id": log.problem_id,
                "action": log.action,
                "time": log.time,
                "status": log.status
            })
        return api_response(200, "success", response=response, data=logs_return)


@router.post('/reset')
async def reset_system(response: Response, request: Request):
    """Reset the system"""
    # 处理401和403异常
    session_user_id = request.session.get('user_id')
    session_user_role = request.session.get('role')
    if not session_user_id:
        return api_response(401, "用户未登录", response=response)
    if session_user_role != 'admin':
        return api_response(403, "权限不足", response=response)
    
    # 重置数据库
    reset_db()
    init_db()
    create_initial_admin()
    create_initial_language()
    
    request.session.clear()
    
    return api_response(200, "system reset successfully", response=response)


@router.get('/export')
async def export_data(response: Response, request: Request):
    """Export the database data"""
    # 处理401和403异常
    session_user_id = request.session.get('user_id')
    session_user_role = request.session.get('role')
    if not session_user_id:
        return api_response(401, "用户未登录", response=response)
    if session_user_role != 'admin':
        return api_response(403, "权限不足", response=response)
    
    with get_session() as session:
        users = session.exec(select(User)).all()
        problems = session.exec(select(Problem)).all()
        submissions = session.exec(select(Submission)).all()

        users_return = []
        for user in users:
            users_return.append({
                "user_id": user.user_id,
                "username": user.username,
                "password": user.password,
                "role": user.role,
                "join_time": user.join_time,
                "submit_count": user.submit_count,
                "resolve_count": user.resolve_count
            })
        problems_return = []
        for problem in problems:
            problems_return.append({
                "id": problem.id,
                "title": problem.title,
                "description": problem.description,
                "input_description": problem.input_description,
                "output_description": problem.output_description,
                "samples": json.loads(problem.samples),
                "constraints": problem.constraints,
                "testcases": json.loads(problem.testcases),
                
                "hint": problem.hint,
                "source": problem.source,
                "tags": json.loads(problem.tags),
                "time_limit": problem.time_limit,
                "memory_limit": problem.memory_limit,
                "author": problem.author,
                "difficulty": problem.difficulty
            })
        submissions_return = []
        for submission in submissions:
            submissions_return.append({
                "submission_id": submission.id,
                "user_id": submission.user_id,
                "problem_id": submission.problem_id,
                "language": submission.language,
                "code": submission.code,
                "status": json.loads(submission.status),
                "score": submission.score,
                "counts": submission.counts
            })

        return api_response(200, "success", response=response, data={
            "users": users_return,
            "problems": problems_return,
            "submissions": submissions_return
        })

@router.post("/import")
async def import_data(request: Request, response: Response, file: UploadFile = File(...)):
    
    # 处理401和403异常
    session_user_id = request.session.get('user_id')
    session_user_role = request.session.get('role')
    if not session_user_id:
        return api_response(401, "用户未登录", response=response)
    if session_user_role != 'admin':
        return api_response(403, "权限不足", response=response)
    
    # 检验空文件
    if file.size == 0:
        return api_response(400, "空文件", response=response)
    
    # 文件类型校验
    if not file.filename.endswith(".json"):
        return api_response(400, "非JSON文件", response=response)

    try:
        content = await file.read()
        data = json.loads(content.decode("utf-8"))
    except Exception:
        return api_response(400, "JSON解析失败", response=response)

    # 校验参数
    if not isinstance(data, dict) or not any(k in data for k in ["users", "problems", "submissions"]):
        return api_response(400, "JSON参数错误", response=response)
    
    users = data.get("users", [])
    problems = data.get("problems", [])
    submissions = data.get("submissions", [])

    with get_session() as session:
        # 处理用户导入
        for u in users:
            # 校验参数
            if not all(k in u for k in ["username", "password", "role"]):
                return api_response(400, "用户导入参数错误", response=response)
            
            # 处理冲突数据
            existing_user = session.exec(select(User).where(User.username == u['username'])).first()
            if existing_user:
                session.delete(existing_user)
                session.commit()
                
            # 新建
            user_obj = User(user_id=u['user_id'] or uuid.uuid4().hex,
                            username=u["username"],
                            password=u["password"],
                            join_time=u["join_time"] or datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).strftime("%Y-%m-%d"),
                            role=u["role"] or 'user',
                            submit_count=u["submit_count"] or 0,
                            resolve_count=u["resolve_count"] or 0
                        )
            
            session.add(user_obj)
            session.commit()

        # 处理题目导入
        for p in problems:
            # 校验参数
            if not all(k in p for k in ["id", "title", "description", "input_description", "output_description", "samples", "constraints", "testcases"]):
                return api_response(400, "题目导入参数错误", response=response)
            
            # 处理冲突数据
            existing_problem = session.exec(select(Problem).where(Problem.id == p["id"])).first()
            if existing_problem:
                session.delete(existing_problem)
                session.commit()
            
            # 新建
            problem_obj = Problem(
                id=p["id"],
                title=p["title"],
                description=p["description"],
                input_description=p["input_description"],
                output_description=p["output_description"],
                samples=json.dumps(p["samples"]),
                constraints=p["constraints"],
                testcases=json.dumps(p["testcases"])
            )
            if 'hint' in p:
                problem_obj.hint = p["hint"]
            if 'source' in p:
                problem_obj.source = p["source"]
            if 'tags' in p:
                problem_obj.tags = json.dumps(p["tags"])
            if 'time_limit' in p:
                problem_obj.time_limit = p["time_limit"]
            if 'memory_limit' in p:
                problem_obj.memory_limit = p["memory_limit"]
            if 'author' in p:
                problem_obj.author = p["author"]
            if 'difficulty' in p:
                problem_obj.difficulty = p["difficulty"]
                
            session.add(problem_obj)
            session.commit()

        # 处理提交导入
        for s in submissions:
            # 校验参数
            if not all(k in s for k in ["user_id", "problem_id", "language", "code", "details", "score", "counts", "submit_time"]):
                return api_response(400, "提交导入参数错误", response=response)
            
            # 新建对象，默认生成id
            submission_obj = Submission(
                id=uuid.uuid4().hex,
                user_id=s["user_id"],
                problem_id=s["problem_id"],
                language=s["language"],
                code=s["code"],
                status=json.dumps(s["details"]),
                score=s["score"],
                counts=s["counts"],
                submit_time=s["submit_time"]
            )
            submission_obj.status_short = "success" if len(s["details"]) else "pending"
            
            # 如果给出了评测id，处理冲突数据
            if 'submission_id' in s:
                submission_obj.id = s["submission_id"]
                existing_submission = session.exec(select(Submission).where(Submission.id == s["submission_id"])).first()
                if existing_submission:
                    session.delete(existing_submission)
                    session.commit()
            
            session.add(submission_obj)
            session.commit()


    return api_response(200, "import success", response=response)