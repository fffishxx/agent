from fastapi import APIRouter
from dao import chat_session_dao  # ChatSession 数据访问对象

# ========================= 创建路由对象 =========================
session_router = APIRouter()


# ========================= 创建新会话 =========================
@session_router.post("")
async def create_session(n: int, agent_id: int, user_id: int):
    """
    创建新的聊天会话，并返回会话VO
    - n: 随机选取的示例数量
    - agent_id: 智能体ID
    - user_id: 用户ID
    """
    return chat_session_dao.create_session(n, agent_id, user_id)

@session_router.get("/hot")
async def get_hots(n: int, agent_id: int):
    return chat_session_dao.get_hots(n, agent_id)