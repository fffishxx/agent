from abc import ABC, abstractmethod
from typing import AsyncIterable, Any

from util import JsonUtil

# ------------------ 常量 ------------------

STOP_EVENT = {"eventType": 1002}   # 标准 SSE 停止事件结构，用于前端识别结束信号


# ------------------ SSE 格式化工具方法 ------------------

def format_sse_data(data: dict) -> str:
    """
    将数据格式化为标准的 SSE (Server-Sent Events) 单条消息格式。

    SSE 格式要求每条消息以 "data: <内容>" 开头，并以两个换行结尾。
    """
    return f"data: {JsonUtil.to_str(data)}\n\n"


def make_sse_event(event_type: int, data: Any) -> str:
    """
    构建 SSE 事件格式的字符串。

    :param event_type: 自定义事件类型编号
    :param data: 事件附带的数据内容
    """
    return format_sse_data({"eventType": event_type, "eventData": data})


# ------------------ Base Agent 抽象类 ------------------

class BaseAgent(ABC):
    """
    所有智能体的基础抽象类。

    该类提供：
    - execute() 等统一交互接口
    - 会话生命周期方法（init/destroy）
    子类必须实现 execute/session_detail/delete_session/id 等方法。
    """

    # ------------------ 必须实现的抽象方法 ------------------

    @abstractmethod
    async def execute(self, question: str, session_id: str, user_token: str) -> AsyncIterable[str]:
        """
        执行智能体主逻辑方法。

        要求：
        - 返回异步可迭代对象，用于 SSE 流式输出
        - 子类需自己在可迭代对象中调用 make_sse_event 生成 SSE 字符串
        """
        pass

    @abstractmethod
    def id(self) -> int:
        """
        返回当前智能体的唯一 ID（用于 Redis 标识）。
        子类必须自行定义。
        """
        pass

    @abstractmethod
    async def session_detail(self, user_id: int, session_id: str) -> list:
        """
        根据会话 ID 获取会话详情。

        由子类实现对应业务逻辑，例如：
        - 查询数据库
        - 查询缓存记录
        """
        pass

    @abstractmethod
    async def delete_session(self, session_id: str):
        """
        删除与 session_id 相关的数据。

        可用场景：
        - 用户清空会话
        - 系统回收无效会话
        """
        pass

    # ------------------ 可选实现的生命周期方法 ------------------

    async def init(self):
        """
        智能体初始化钩子（可选实现）。
        在系统启动或 Agent 加载时触发。
        """
        pass

    async def destroy(self):
        """
        智能体销毁钩子（可选实现）。
        在服务退出或 Agent 卸载时触发。
        """
        pass