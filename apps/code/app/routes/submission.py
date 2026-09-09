from fastapi import APIRouter, Response, status, Request, Depends, BackgroundTasks
from sqlmodel import Session, select
from app.models import Problem, FrontEnd_Problem, User, Submission, FrontEnd_Submission, Language, Log
from app.database import get_session
import json
from app.routes.response import api_response, is_admin
from app.judge import run_code
from app.spj import execute_spj_script, check_set_equal
import datetime
import uuid

router = APIRouter(
    prefix="/api/submissions",
    tags=["submissions"]
)

async def online_judge(session: Session, user: User, problem: Problem, submission: Submission, language: Language):
    
    testcases = json.loads(problem.testcases)
    # 优先题目限制，若未给出则按照语言限制
    time_limit = problem.time_limit or language.time_limit or 1.0
    memory_limit = (problem.memory_limit or language.memory_limit or 128 ) * 1024 * 1024
    statuses = []
    score = 0
    
    judge_mode = problem.judge_mode or 'standard'
    
    for idx, testcase in enumerate(testcases):
        input_str = testcase["input"]
        expected_output = testcase["output"].strip()

        run_status, run_output, used_time, used_memory = run_code(
            submission.code,
            input_str,
            language,
            time_limit,
            memory_limit
        )

        if run_status == "OK":
            if judge_mode == "standard":
                # 标准评判：忽略行尾空格和最后的空行
                if run_output.strip() == expected_output:
                    statuses.append({"id": idx + 1, "result": "AC", "score": 10, "time": used_time, "memory": used_memory/1024/1024})
                    score += 10
                else:
                    statuses.append({"id": idx + 1, "result": "WA", "score": 0, "time": used_time, "memory": used_memory/1024/1024})
            
            elif judge_mode == "strict":
                # 严格评判：完全相同（包括空格和换行）
                if run_output == expected_output:
                    statuses.append({"id": idx + 1, "result": "AC", "score": 10, "time": used_time, "memory": used_memory/1024/1024})
                    score += 10
                else:
                    statuses.append({"id": idx + 1, "result": "WA", "score": 0, "time": used_time, "memory": used_memory/1024/1024})
            
            elif judge_mode == "spj":
                # 特判评测：如果有上传的SPJ脚本，执行它；否则使用默认特判方法
                try:
                    if problem.spj_code:
                        # 使用上传的SPJ脚本
                        is_correct = execute_spj_script(
                            problem.spj_code,
                            input_str,
                            expected_output, 
                            run_output,
                            problem.spj_language or 'python'
                        )
                    else:
                        # 使用默认特判方法（集合判断）
                        is_correct = check_set_equal(expected_output, run_output)
                        
                    if is_correct:
                        statuses.append({
                            "id": idx + 1, 
                            "result": "AC", 
                            "score": 10, 
                            "time": used_time, 
                            "memory": used_memory/1024/1024
                        })
                        score += 10
                    else:
                        statuses.append({
                            "id": idx + 1, 
                            "result": "WA", 
                            "score": 0, 
                            "time": used_time, 
                            "memory": used_memory/1024/1024
                        })
                except Exception as e:
                    statuses.append({
                        "id": idx + 1, 
                        "result": "SPJ_ERROR", 
                        "score": 0, 
                        "time": used_time, 
                        "memory": used_memory/1024/1024,
                        "error": str(e)
                    })
            else:
                # 默认为标准评判
                if run_output.strip() == expected_output.strip():
                    statuses.append({
                        "id": idx + 1, 
                        "result": "AC", 
                        "score": 10, 
                        "time": used_time, 
                        "memory": used_memory/1024/1024
                    })
                    score += 10
                else:
                    statuses.append({
                        "id": idx + 1, 
                        "result": "WA", 
                        "score": 0, 
                        "time": used_time, 
                        "memory": used_memory/1024/1024
                    })
                
        elif run_status in ["TLE", "MLE", "RE", "CE"]:
            statuses.append({"id": idx + 1, "result": run_status, "score": 0, "time": used_time, "memory": used_memory/1024/1024})
        else:
            statuses.append({"id": idx + 1, "result": "UNK", "score": 0, "time": used_time, "memory": used_memory/1024/1024})

    
    status_short = "error" if any(status['result'] == 'UNK' for status in statuses) else "success"
    
    # 当所有测试用例通过且之前未通过时
    user_submissions = session.exec(select(Submission).where(Submission.user_id == user.user_id, Submission.problem_id == problem.id, Submission.score == submission.counts)).first()

    if score == submission.counts and not user_submissions:
    # if score == submission.counts:
        user.resolve_count += 1
        session.commit()
        
    submission.status_short = status_short
    submission.status = json.dumps(statuses)
    submission.score = score
    session.commit()

# run_judge_task function is created by Claude 3.7
def run_judge_task(session_factory, user_id, problem_id, submission_id, language_name):
    """Background task to run the judge"""
    with session_factory() as session:
        user = session.exec(select(User).where(User.user_id == user_id)).first()
        problem = session.exec(select(Problem).where(Problem.id == problem_id)).first()
        submission = session.exec(select(Submission).where(Submission.id == submission_id)).first()
        language = session.exec(select(Language).where(Language.name == language_name)).first()
        
        if all([user, problem, submission, language]):
            # Create a new asyncio event loop for the background task
            import asyncio
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            # Run the judge
            try:
                loop.run_until_complete(online_judge(session, user, problem, submission, language))
            finally:
                loop.close()

@router.post('/')
async def create_submission(submission_info: FrontEnd_Submission, background_tasks: BackgroundTasks, response: Response, request: Request):
    """Submit an online judge"""
    
    # 处理401和403异常
    user_id = request.session.get("user_id")
    user_role = request.session.get("role")
    if not user_id:
        return api_response(401, f"未登录", response=response)
    if user_role == 'banned':
        return api_response(403, f"用户被禁用", response=response)
    
    # 处理400异常
    field = ["problem_id", "language", "code"]
    missing = [f for f in field if getattr(submission_info, f, None) in (None, "")]
    if missing or not isinstance(submission_info.problem_id, str) or not isinstance(submission_info.language, str) or not isinstance(submission_info.code, str):
        return api_response(400, f"参数错误", response=response)
    
    with get_session() as session:
        problem = session.exec(select(Problem).where(Problem.id == submission_info.problem_id)).first()
        user = session.exec(select(User).where(User.user_id == user_id)).first()
        # 处理404异常
        if not problem:
            return api_response(404, f"题目不存在", response=response)
        language = session.exec(select(Language).where(Language.name == submission_info.language)).first()
        if not language:
            return api_response(404, f"语言不存在", response=response)
        
        # 如果一分钟之内提交超过3次，429异常
        submit_time=datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8)))
        
        submissions = session.exec(select(Submission).where(Submission.user_id == user.user_id)).all()
        if sum(datetime.datetime.strptime(s.submit_time, "%Y-%m-%d %H:%M:%S").replace(tzinfo=datetime.timezone(datetime.timedelta(hours=8))) >= submit_time - datetime.timedelta(minutes=1) for s in submissions) > 3:
            return api_response(429, "提交次数超出限制", response=response)
        
        submission = Submission(
            id=uuid.uuid4().hex,
            user_id=user.user_id,
            problem_id=problem.id,
            code=submission_info.code,
            language=submission_info.language,
            status='',
            status_short='pending',
            score=0,
            counts=10 * len(json.loads(problem.testcases)),
            submit_time=submit_time.strftime("%Y-%m-%d %H:%M:%S")
        )
        session.add(submission)
        session.commit()
        
        user.submit_count += 1
        session.commit()
        
        submission_id = submission.id
        
        # 后台任务异步评测
        background_tasks.add_task(
            run_judge_task, 
            get_session,
            user.user_id,
            problem.id,
            submission_id,
            submission.language
        )
        
        return api_response(200, "success", response=response, data={
            "submission_id": submission_id,
            "status": "pending"
        })


@router.get('/{submission_id}')
async def check_submission(submission_id: str, response: Response, request: Request):
    """Check the status of a submission"""
    # 处理400异常
    if not submission_id or not isinstance(submission_id, str):
        return api_response(400, f"参数错误", response=response)
    
    with get_session() as session:
        submission = session.exec(select(Submission).where(Submission.id == submission_id)).first()
        # 处理404异常
        if not submission:
            return api_response(404, f"提交不存在", response=response)
        # 处理401和403异常
        session_user_id = request.session.get("user_id")
        session_role = request.session.get("role")
        if not session_user_id:
            return api_response(401, "未登录", response=response)
        if session_user_id != submission.user_id and session_role != "admin":
            return api_response(403, "权限不足", response=response)
        
        return api_response(200, "success", response=response, data={
            "problem_id": submission.problem_id,
            "status": submission.status_short,
            "score": submission.score,
            "counts": submission.counts
        })

@router.get('/')
async def get_submissions(response: Response, request: Request, user_id: str = None, 
                          problem_id: str = None, status: str = None, page: int = None, page_size: int = None):

    """Get all submissions"""
    
    
    
    with get_session() as session:
        # 处理401异常
        session_user_id = request.session.get("user_id")
        session_role = request.session.get("role")
        if not session_user_id:
            return api_response(401, "未登录", response=response)
        # 处理403异常
        if (user_id and session_user_id != user_id) and session_role != "admin":
            return api_response(403, "权限不足", response=response)
        
        # 处理400异常
        if not user_id and not problem_id:
            return api_response(400, f"参数错误", response=response)
        if page and not page_size:
            return api_response(400, f"参数错误", response=response)
        if not page and page_size:
            page = 1
            
            
        submissions = session.exec(select(Submission)).all()
        if user_id:
            submissions = [submission for submission in submissions if submission.user_id == user_id]
        if problem_id:
            submissions = [submission for submission in submissions if submission.problem_id == problem_id]
        if status:
            submissions = [submission for submission in submissions if submission.status_short == status]
            
        if page and page_size:
            submissions = submissions[(page - 1) * page_size: page * page_size]
        
        submissions_return = []
        for sub in submissions:
            if sub.status_short == "success":
                submissions_return.append({
                    "submission_id": sub.id,
                    "problem_id": sub.problem_id,
                    "status": 'success',
                    "score": sub.score,
                    "counts": sub.counts
                })
            else:
                submissions_return.append({
                    "submission_id": sub.id,
                    "problem_id": sub.problem_id,
                    "status": sub.status_short,
                })
        return api_response(200, "success", response=response, data={
            "total": len(submissions),
            "submissions": submissions_return
        })

@router.put('/{submission_id}/rejudge')
async def update_submission(submission_id: str, background_tasks: BackgroundTasks, response: Response, request: Request):
    """Update a submission"""
    
    
    # 处理401和403异常
    session_user_id = request.session.get("user_id")
    session_role = request.session.get("role")
    if not session_user_id:
        return api_response(401, "未登录", response=response)
    if session_role != "admin":
        return api_response(403, "权限不足", response=response)
    
    # 处理400异常
    if not submission_id or not isinstance(submission_id, str):
        return api_response(400, "参数错误", response=response)
    
    with get_session() as session:
        submission = session.exec(select(Submission).where(Submission.id == submission_id)).first()
        
        # 处理404异常
        if not submission:
            return api_response(404, "提交不存在", response=response)
        
        submission.status_short = 'pending'
        submission.score = 0
        submission.status = ''
        session.commit()
        
        # 后台任务异步评测
        background_tasks.add_task(
            run_judge_task, 
            get_session,
            submission.user_id,
            submission.problem_id,
            submission.id,
            submission.language
        )
        
        return api_response(200, "rejudge started", response=response, data={
            "submission_id": submission.id,
            "status": "pending"
        })
        

@router.get('/{submission_id}/log')
async def get_submission_log(submission_id: str, response: Response, request: Request):
    """Get the log of a submission"""
    
    with get_session() as session:
        submission = session.exec(select(Submission).where(Submission.id == submission_id)).first()
        if submission:
            problem = session.exec(select(Problem).where(Problem.id == submission.problem_id)).first()
            session_problem_id = problem.id
        else:
            session_problem_id = ''
            
        session_user_id = request.session.get("user_id")
        session_role = request.session.get("role")
        
        log = Log(
            user_id = session_user_id or 0,
            problem_id = session_problem_id,
            time = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).strftime("%Y-%m-%d")
        )
        
        # 处理401异常
        if not session_user_id:
            log.status = "401"
            session.add(log)
            session.commit()
            return api_response(401, "未登录", response=response)
        
        # 处理400异常
        if not submission_id or not isinstance(submission_id, str):
            log.status = "400"
            session.add(log)
            session.commit()
            return api_response(400, "参数错误", response=response)
        
        # 处理404异常
        if not submission:
            log.status = "404"
            session.add(log)
            session.commit()
            return api_response(404, "提交不存在", response=response)
        
        
        
        # 处理403异常
        if (session_user_id != submission.user_id) and session_role != "admin" and problem.public_cases != True:
            log.status = "403"
            session.add(log)
            session.commit()
            return api_response(403, "权限不足", response=response)
        
        log.status = "200"
        session.add(log)
        session.commit()
        
        statuses = submission.to_dict()['status']
        return api_response(200, "success", response=response, data={
            "details": statuses,
            "score": submission.score,
            "counts": submission.counts,
        })
    