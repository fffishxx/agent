import asyncio
import uuid
from typing import Optional

from langchain_core.messages import HumanMessage, AIMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.constants import START, END
from langgraph.graph.state import CompiledStateGraph, StateGraph

from agent.BaseAgent import *
from agent.tianji.RouteState import RouteState
from agent.tianji.nodes import *
from agent.tianji.tools.result import CourseInfo
from common import INTENT_TO_AGENT
from config import logger, get_async_pg_pool
from langgraph.types import StateSnapshot


class RouterAgent(BaseAgent):
    """
    RouterAgent 是整个天机系统的核心路由智能体。

    负责：
    - 构建和维护 LangGraph 的推理状态图
    - 管理意图识别与路由逻辑
    - 以流式 SSE 输出最终结果
    - 持久化每个会话的状态（使用 LangGraph + Postgres Checkpointer）
    """

    # 声明用于 Graph 的所有节点智能体（节点 = 子 Agent）
    INTENT_MAPS = {
        "intent_agent": IntentAgent(),
        "recommend_agent": RecommendAgent(),
        "buy_agent": BuyAgent(),
        "consult_agent": ConsultAgent(),
        "knowledge_agent": KnowledgeAgent(),
        "unknown_agent": UnknownAgent(),
    }

    def __init__(self):
        self.graph: Optional[CompiledStateGraph] = None
        self.checkpointer: Optional[AsyncPostgresSaver] = None  # 用于保存会话状态的 Postgres Checkpointer

    async def init(self):
        """
        初始化 RouterAgent
        """
        # 检查会话记忆所需要的表是否存在
        await self.check_table()

        # 获取异步数据库连接池实例
        async_pg_pool = await get_async_pg_pool()
        # 创建checkpointer是用于实现会话记忆的
        self.checkpointer = AsyncPostgresSaver(conn=async_pg_pool)
        self.init_graph()

    # ---------------- Graph 初始化 ----------------
    def init_graph(self):
        build = StateGraph(RouteState)
        #添加节点
        for name , agent in self.INTENT_MAPS.items():
            build.add_node(name, agent.execute)

        build.add_edge(START,"intent_agent")

        #添加条件边

        def condition_func(state: RouteState):
            return state.get("intent", "UNKNOWN")

        build.add_conditional_edges(
            "intent_agent",
            condition_func,
            INTENT_TO_AGENT
        )

        for agent in INTENT_TO_AGENT.values():
            build.add_edge(agent,END)

        # 编译 Graph，并启用 Checkpointer
        self.graph = build.compile(checkpointer = self.checkpointer)
        logger.info("初始化图成功....")


    async def check_table(self):
        """
        检查数据库中是否存在会话记忆相关的表，如果不存在则创建
        """
        async_pg_pool = await get_async_pg_pool()
        conn = None
        try:
            # 先创建一个临时checkpointer，用于检查数据库中相关的表是否存在，如果不存在则创建
            conn = await async_pg_pool.getconn()
            await conn.set_autocommit(True) # 设置自动提交，不使用显式事务块
            checkpointer = AsyncPostgresSaver(conn=conn)
            await checkpointer.setup()  # 如果会话记忆相关的表不存在，会自动创建
        finally:
            if conn is not None:
                await async_pg_pool.putconn(conn)

    async def execute(self, question: str, session_id: str, user_token: str, tool_result=None) -> AsyncIterable[str]:

        try:
            request_id = uuid.uuid4().hex

            # 构建 Graph 执行上下文
            config = RunnableConfig(configurable={
                "thread_id": session_id,
                "user_token": user_token,  # 将自定义参数传递给子智能体
                "request_id": request_id  # 将自定义参数传递给子智能体
            })

            # 用户输入封装
            inputs = {"messages": [HumanMessage(question)]}


            logger.info("图开始执行...")
            # 开始图的流式执行
            res = self.graph.astream(
                input=inputs,
                config=config,
                subgraphs=True,  # 需要得到子图的输出
                stream_mode="messages",
            )
            # 工具调用的执行结果
            tool_result = {}
            try:
                async for node_info, (message, metadata) in res:
                    # 获取消息 tags（例如 IntentAgent）
                    tags = metadata.get("tags", [])

                    # 主动跳过 IntentAgent 阶段输出
                    if "IntentAgent" in tags:
                        continue

                    # ToolMessage 是工具输出，不对用户显示
                    if isinstance(message, ToolMessage):
                        if not message.status == "success":
                            continue
                        _content = message.content
                        if _content:
                            if message.name == "query_course_by_id":
                                course_info = JsonUtil.to_obj(_content, CourseInfo)
                                tool_result[f"courseInfo_{course_info.id}"] = course_info

                        continue

                    # 提取 message 内容
                    content = getattr(message, "content", None)
                    if not content:
                        continue
                    # SSE 输出文本事件
                    yield make_sse_event(1001, content)
            except asyncio.CancelledError:
                # 客户端中断，也需要安全关闭流
                await res.aclose()
                raise

            # 工具调用结果在结束时统一输出（tag 1003）
            if tool_result:
                yield make_sse_event(1003, tool_result)
        except Exception as e:
            logger.exception("RouterAgent error")
            yield make_sse_event(2001, str(e))

        # SSE 最终停止事件（前端用于关闭流）
        yield format_sse_data(STOP_EVENT)

    def id(self) -> int:
        """
        RouterAgent 的固定 ID。
        """
        return 1001

    async def session_detail(self, user_id: int, session_id: str) -> list:
        """
        查询指定 session 的消息历史（从 LangGraph 的 Checkpointer 中恢复）。

        同时会自动解析 ToolMessage，用于还原“查询课程/预下单”的参数结构。
        """
        config = RunnableConfig(configurable={"thread_id": session_id})
        state_snapshot: StateSnapshot = await self.graph.aget_state(config)
        messages = state_snapshot.values.get("messages", [])

        result = []
        tool_message: Optional[ToolMessage] = None

        for message in messages:
            msg_type = ""
            content = message.content
            params = {}

            # 用户消息
            if isinstance(message, HumanMessage):
                msg_type = "USER"

            # 模型回复消息
            elif isinstance(message, AIMessage):
                msg_type = "ASSISTANT"

                # 如果 AIMessage 紧随 ToolMessage，恢复工具返回内容
                if tool_message:
                    _content = tool_message.content
                    if tool_message.name == "query_course_by_id":
                        course_info = JsonUtil.to_obj(_content, CourseInfo)
                        params = {f"courseInfo_{course_info.id}": course_info}
                    tool_message = None

            # 工具调用消息（需要保留，下一条 AIMessage 会用到）
            elif isinstance(message, ToolMessage):
                tool_message = message

            # 将有效消息加入结果结构
            if msg_type and content:
                result.append({"type": msg_type, "content": content, "params": params})

        return result

    async def delete_session(self, session_id: str):
        """暂不实现"""
        pass


# 全局 RouterAgent 实例
router_agent = RouterAgent()