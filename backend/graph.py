from langgraph.graph import StateGraph, START, END
from langchain_core.messages import SystemMessage, AIMessage, ToolMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import ToolNode, tools_condition

from .llm import llm
from .tools import tools
from .state import ChatState


# 让 LLM 感知工具
llm_with_tools = llm.bind_tools(tools)




def _clean_tool_calls(messages: list) -> list:
    """移除没有对应 ToolMessage 的 AIMessage 中的 tool_calls。

    DeepSeek API 要求带 tool_calls 的 AIMessage 后面必须紧跟
    对应的 ToolMessage，否则会报 400 错误。
    """
    cleaned = []
    for i, msg in enumerate(messages):
        if isinstance(msg, AIMessage) and msg.tool_calls:
            # 检查后面是否有对应每个 tool_call_id 的 ToolMessage
            remaining = messages[i + 1:]
            for tc in msg.tool_calls:
                matched = any(
                    isinstance(m, ToolMessage) and m.tool_call_id == tc.get("id")
                    for m in remaining
                )
                if not matched:
                    # 有孤儿 tool_call，移除整个 tool_calls
                    msg = AIMessage(
                        content=msg.content,
                        id=msg.id,
                    )
                    break
        cleaned.append(msg)
    return cleaned


# 节点 1
def chat_node(state: ChatState):
    """LLM 节点：可以直接回答，也可以调用合适的工具。"""

    system_message = SystemMessage(
        content=(
            "你是一个友好的智能聊天助手，可以使用多种工具来帮助用户。\n\n"

            "工具使用说明：\n"
            "- 使用 `rag_tool` 回答与已上传的 PDF 文档相关的问题。"
            "在回答 PDF 相关问题前，始终先检索相关文档内容。\n"
            "- 使用 `search_tool` 搜索时事新闻、最新信息或需要联网查询的内容。\n"
            "- 使用 `calculator` 进行数学计算。当有计算器可用时，不要手动计算复杂表达式。\n"
            "- 使用 `get_stock_price` 查询用户询问的股票当前价格。\n"
            "- 使用 `purchase_stock` 当用户想要购买股票时。\n"
            "- 使用 `get_current_weather` 查询用户询问的城市天气。\n\n"

            "不需要工具时直接回答一般性问题。"
            "不要凭空编造上传文档中的信息。"
            "如果用户询问 PDF 相关内容但没有上传文档，请提示用户上传 PDF。"
            "收到工具结果后，请用中文给出清晰、有帮助的最终回答。"
        )
    )

    # 过滤孤儿 tool_calls，避免 DeepSeek 400 错误
    history = _clean_tool_calls(list(state["messages"]))

    messages = [
        system_message,
        *history
    ]

    response = llm_with_tools.invoke(messages)

    return {"messages": [response]}

# 节点 2 - 工具节点
tool_node = ToolNode(tools)
# 检查点
checkpoint = MemorySaver()
# 图
graph = StateGraph(ChatState)
# 添加节点
graph.add_node('chat_node', chat_node)
graph.add_node('tools', tool_node)
# 添加边
graph.add_edge(START, 'chat_node')
graph.add_conditional_edges("chat_node", tools_condition)
graph.add_edge('tools', 'chat_node')
chatbot = graph.compile(checkpointer=checkpoint)

# 前端/API 共用的辅助函数
def get_all_threads():
    all_threads = set()
    for ckpt in checkpoint.list(None):
        all_threads.add(ckpt.config['configurable']['thread_id'])

    return list(all_threads)


def get_pending_interrupt(thread_id):
    """
    返回指定线程的第一个未处理的 LangGraph 中断。

    Returns:
        待处理的 Interrupt 对象，若无则返回 None。
    """

    config = {
        "configurable": {
            "thread_id": thread_id
        }
    }

    try:

        # 读取当前检查点状态
        state_snapshot = chatbot.get_state(config)

        # 部分 LangGraph 版本直接在 state 上暴露 interrupts
        direct_interrupts = getattr(
            state_snapshot,
            "interrupts",
            ()
        ) or ()

        if direct_interrupts:
            return direct_interrupts[0]

        # 其他 LangGraph 版本将 interrupts 存储在 tasks 内部
        tasks = getattr(
            state_snapshot,
            "tasks",
            ()
        ) or ()

        for task in tasks:

            task_interrupts = getattr(
                task,
                "interrupts",
                ()
            ) or ()

            if task_interrupts:
                return task_interrupts[0]

    except Exception:

        # 新创建的线程可能还没有检查点
        return None

    return None
