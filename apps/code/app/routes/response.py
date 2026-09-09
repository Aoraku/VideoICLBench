from typing import Any
from fastapi import Response, Request
from fastapi.responses import JSONResponse


def api_response(code: int, msg: str, data: Any = None, response: Response = None):
    # response参数是为了让FastAPI注入响应对象，以便后续的中间件（如SessionMiddleware）可以修改它
    # 我们只需要返回一个JSONResponse，中间件会处理剩下的事情
    
    # 如果提供了response对象，可以设置其状态码，但最终返回的是新的JSONResponse
    if response:
        response.status_code = code

    return JSONResponse(
        status_code=code,
        content={
            "code": code,
            "msg": msg,
            "data": data
        }
    )

def is_admin(request: Request):
    role = request.session.get("role")
    return role == "admin"