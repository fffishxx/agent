from langchain_core.tools import tool
from langgraph.prebuilt import ToolRuntime

from agent.tianji.tools.result.PrePlaceOrder import PrePlaceOrder
from config import logger
from util import HttpClientUtil, JsonUtil


@tool
def pre_place_order(course_ids: list, runtime: ToolRuntime):
    """
    根据课程 ID 查询课程数据，并将结果存储到 ToolResultHolder。

    Args:
        course_id : 课程 ID
        runtime: 获取运行参数
    """
    # 获取必要的配置数据
    user_token = runtime.context.user_token
    request_id = runtime.context.request_id

    course_ids = [str(id) for id in course_ids]

    # TODO 从 Nacos 获取业务系统网关实例
    url = f"http://127.0.0.1:10010/ts/orders/prePlaceOrde"

    # 发起 HTTP GET 请求获取订单数据
    response_data = HttpClientUtil.get(url, user_token, params={"courseIds": ",".join(course_ids)}) or {}
    data = response_data.get("data")
    if not data:
        logger.error(f"预下单失败，url={url}, courseIds={course_ids}")
        return None

    logger.debug("【Tool】 pre_place_order url=%s, data=%s, request_id=%s", url, data, course_ids)
    # 转换为 CourseInfo 对象
    order_info = PrePlaceOrder.of(data)

    # 将结果序列化json，返回给大模型
    return JsonUtil.to_str(order_info)