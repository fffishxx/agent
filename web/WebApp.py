from fastapi import FastAPI, Request
from starlette.responses import PlainTextResponse
from routers import auth_router , session_router

# ========================= 创建 FastAPI 实例 =========================
app = FastAPI(
    title="Agent Center Web Server",
    description="黑马程序员智能体中心"
)


# ========================= 异常处理 =========================
def system_exception_handler(req: Request, exc: Exception):
    """
    全局异常处理函数，将异常转换为 500 响应
    """
    return PlainTextResponse(
        content=str(exc),
        status_code=500
    )


# 添加全局异常处理器
app.add_exception_handler(Exception, system_exception_handler)

app.include_router(auth_router, prefix="/auth", tags=["auth"])
app.include_router(session_router, prefix="/session", tags=["session"])