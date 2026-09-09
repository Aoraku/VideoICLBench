
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware  # 添加CORS中间件
from app import models, database
from app.routes import problem, auth, submission, user, language, others
from starlette.middleware.sessions import SessionMiddleware # 引入中间件
from app.routes.response import api_response
import os
import uvicorn
import logging

# 配置日志记录器
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Simple OJ System - Student Template",
    description="A simple online judge system for programming assignments",
    version="1.0.0"
)

# 1. 添加日志中间件，记录所有进入的请求
@app.middleware("http")
async def log_requests(request: Request, call_next):
    logger.info(f"--> Incoming request: {request.method} {request.url}")
    response = await call_next(request)
    logger.info(f"<-- Outgoing response: {response.status_code}")
    return response

# 2. 添加CORS中间件配置，解决前端跨域问题
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8501", "http://127.0.0.1:8501"],  # Streamlit默认端口
    allow_credentials=True,  # 允许跨域请求携带cookie
    allow_methods=["*"],  # 允许所有HTTP方法
    allow_headers=["*"],  # 允许所有请求头
    expose_headers=["Set-Cookie"],  # 暴露Set-Cookie头
)

# 3. 增强会话中间件配置，确保在Linux下能够长期维持登录
app.add_middleware(
    SessionMiddleware, 
    secret_key=os.environ["VIC_SESSION_SECRET"],
    max_age=86400,  # 设置会话有效期为24小时
    same_site="lax",  # 允许跨站请求
    https_only=os.environ.get("VIC_HTTPS_ONLY", "0") == "1",  # 非HTTPS环境也允许
    session_cookie="session_id"  # 指定会话cookie名称
)

@app.get("/")
async def welcome():
    return {"status": "ok", "message": "Welcome to OJ API!"}

@app.on_event("startup")
async def startup():
    # database.reset_db()
    database.init_db()
    database.create_initial_admin()
    database.create_initial_language()


app.include_router(problem.router)
app.include_router(auth.router)
app.include_router(submission.router)
app.include_router(user.router)
app.include_router(language.router)
app.include_router(others.router)  

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return api_response(400, "参数错误", response=JSONResponse)

# 直接运行此文件时启动服务器
if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)