from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException
from starlette.responses import PlainTextResponse
from agent import AGENTS
from config import get_async_pg_pool, close_async_pg_pool
from web.routers import auth_router, session_router, chat_router
import logging

logger = logging.getLogger("AgentCenter")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    lifespan 生命周期事件：
    yield 之前：startup 服务启动时执行
    yield 之后：shutdown 服务关闭时执行
    """
    # ========== startup 启动初始化 ==========
    logger.info("===== 开始初始化所有 Agent =====")
    try:
        # 初始化异步数据库连接池
        await get_async_pg_pool()
        logger.info("===== 连接池初始化完毕 =====")

        for agent_id, agent in AGENTS.items():
            logger.info(f"正在初始化 agent: {agent_id}")
            await agent.init()
        logger.info("===== 所有 Agent 初始化完成 =====")
    except Exception as e:
        logger.error(f"Agent初始化失败: {e}", exc_info=True)
        # 初始化失败直接抛出，阻止服务启动
        raise

    yield

    # ========== shutdown 关闭销毁 ==========
    logger.info("===== 开始销毁所有 Agent 资源 =====")
    try:

        await close_async_pg_pool()
        logger.info("===== 销毁所有连接池 =====")

        for agent_id, agent in AGENTS.items():
            logger.info(f"释放 agent: {agent_id}")
            await agent.destroy()
            logger.info("===== 所有Agent资源释放完成 =====")

    except Exception as e:
        logger.error(f"Agent销毁异常: {e}", exc_info=True)


# ========================= 创建 FastAPI 实例 =========================
app = FastAPI(
    title="Agent Center Web Server",
    description="黑马程序员智能体中心",
    lifespan=lifespan
)


# ========================= 异常处理 =========================
async def system_exception_handler(req: Request, exc: Exception):
    """全局异常处理函数，将异常转换为 500 响应"""
    logger.error(f"全局捕获异常: {exc}", exc_info=True)
    return PlainTextResponse(
        content=f"Server Error: {str(exc)}",
        status_code=500
    )

# 捕获非HTTP的通用异常
app.add_exception_handler(Exception, system_exception_handler)


# 单独捕获HTTPException（404、401这类）
async def http_exception_handler(req: Request, exc: HTTPException):
    return PlainTextResponse(content=exc.detail, status_code=exc.status_code)

app.add_exception_handler(HTTPException, http_exception_handler)


# 根路径健康检查接口，调试用
@app.get("/")
async def root():
    return PlainTextResponse("Agent Center Service Running")


# ========================= 注册路由 =========================
app.include_router(auth_router, prefix="/auth", tags=["auth"])
app.include_router(session_router, prefix="/session", tags=["session"])
app.include_router(chat_router, prefix="/chat", tags=["chat"])

