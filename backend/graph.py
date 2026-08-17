import os
import sqlite3
from typing import TypedDict, Annotated

from langchain_openai import ChatOpenAI
from langchain_core.messages import BaseMessage, SystemMessage, HumanMessage, AIMessage, ToolMessage
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from langgraph.types import interrupt

from .tools import tools
from .settings import settings as _settings


# ========================= LLM =========================

llm = ChatOpenAI(
    model="deepseek-chat",
    temperature=0.7,
    base_url="https://api.deepseek.com",
    api_key=os.getenv("DEEPSEEK_API_KEY"),
)

# 让 LLM 感知工具
llm_with_tools = llm.bind_tools(tools)


# ========================= 对话状态 =========================

class ChatState(TypedDict):

    messages: Annotated[list[BaseMessage], add_messages]
    # HITL 审批决策（human_approval 节点写入，供 purchase_stock 等工具读取）
    pending_approval: dict


# ========================= HITL 审批白名单 =========================

# 需要人工审批的工具：这些工具被调用前，图会先路由到 human_approval 节点
APPROVAL_REQUIRED_TOOLS = {
    "purchase_stock",
}


# ========================= 节点 =========================

def clean_tool_calls(messages: list) -> list:
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


# 节点 1：LLM 推理，可以直接回答，也可以调用合适的工具
def chat_node(state: ChatState):

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
    history = clean_tool_calls(list(state["messages"]))

    messages = [
        system_message,
        *history
    ]

    response = llm_with_tools.invoke(messages)

    return {"messages": [response]}


# 节点 2：人工审批（HITL 唯一入口）
def human_approval(state: ChatState):
    """对需要审批的工具调用发起 interrupt，等待人工决策。

    中断后图挂起；客户端通过 /chat/resume 传入 {"decision": "yes"/"no"}，
    本节点重新执行（LangGraph 从节点开头重放），拿到决策后写入
    pending_approval 状态，供后续工具节点读取。

    拒绝时：移除待审批的 tool_calls 并追加 ToolMessage 告知拒绝原因，
    避免 LLM 反复发起同一个购买请求。
    """
    last_message = state["messages"][-1]
    pending_tools = [
        tc for tc in getattr(last_message, "tool_calls", [])
        if tc.get("name") in APPROVAL_REQUIRED_TOOLS
    ]

    # 待审批请求列表（发给客户端的结构化信息）
    requests = [
        {
            "tool": tc["name"],
            "args": tc.get("args", {}),
            "message": f"Approve calling `{tc['name']}`?",
        }
        for tc in pending_tools
    ]

    # 暂停执行，等待人工决策（恢复时会返回客户端提交的 dict）
    decision = interrupt({"action": "human_approval", "requests": requests})

    if isinstance(decision, dict):
        decision = decision.get("decision", "no")

    if decision == "yes":
        # 批准：tool_calls 原样保留，路由到 tools 执行
        return {"pending_approval": {"decision": "yes"}}

    # 拒绝：追加系统提示，让 chat_node 向用户解释操作已取消。
    # 上一条 AIMessage 的 tool_calls 因没有对应的 ToolMessage 响应，
    # 会由 chat_node 的 clean_tool_calls 自动清除，避免 LLM 重复发起购买
    return {
        "pending_approval": {"decision": "no"},
        "messages": [
            HumanMessage(
                content="（系统提示：上一项操作已被人工拒绝，"
                "请向用户说明操作已取消，不要再次发起该操作。）"
            ),
        ],
    }


# 节点 3：执行工具
tool_node = ToolNode(tools)


# ========================= 路由 =========================

def route_after_chat(state: ChatState) -> str:
    """chat_node 之后的控制：有审批工具 → human_approval；有普通工具 → tools；否则结束。"""
    last_message = state["messages"][-1]
    tool_calls = getattr(last_message, "tool_calls", None) or []

    if not tool_calls:
        return END

    if any(tc.get("name") in APPROVAL_REQUIRED_TOOLS for tc in tool_calls):
        return "human_approval"

    return "tools"


def route_after_approval(state: ChatState) -> str:
    """human_approval 之后：批准则执行工具，拒绝则回到 chat_node 说明结果。"""
    decision = state.get("pending_approval", {}).get("decision", "no")
    if decision == "yes":
        return "tools"
    return "chat_node"


# ========================= 图的边 =========================

def build_graph(checkpointer):
    """装配状态图（全部控制逻辑集中于此）。

    控制流：
        chat_node ──无工具调用──> END
             │
             ├──普通工具──> tools ──> chat_node
             │
             └──审批工具──> human_approval ──批准──> tools
                                 │
                                 └──拒绝──> chat_node
    """
    graph = StateGraph(ChatState)

    # 节点
    graph.add_node('chat_node', chat_node)
    graph.add_node('human_approval', human_approval)
    graph.add_node('tools', tool_node)

    # 边
    graph.add_edge(START, 'chat_node')
    graph.add_conditional_edges("chat_node", route_after_chat, {
        "human_approval": "human_approval",
        "tools": "tools",
        END: END,
    })
    graph.add_conditional_edges("human_approval", route_after_approval, {
        "tools": "tools",
        "chat_node": "chat_node",
    })
    graph.add_edge('tools', 'chat_node')

    return graph.compile(checkpointer=checkpointer)


# ========================= 检查点 & 图 =========================

# 对话记忆持久化（SqliteSaver：写入数据库，重启/多进程不丢）
# checkpoint 与 ORM 共用同一个配置源（settings.database_url），
# 未来切换 PostgreSQL 时一处改、两处生效。
def _checkpoint_db_path() -> str:
    """从 settings.database_url 提取 SQLite 文件路径。"""
    url = _settings.database_url
    if url.startswith("sqlite:///"):
        return url[len("sqlite:///"):]
    # 非 SQLite（如 PostgreSQL）时暂回退本地文件；后续接 PG checkpointer 时替换
    return "chatbot.db"


_checkpoint_conn = sqlite3.connect(_checkpoint_db_path(), check_same_thread=False)
checkpoint = SqliteSaver(_checkpoint_conn)
checkpoint.setup()

chatbot = build_graph(checkpointer=checkpoint)


# ========================= HITL 控制 =========================

def get_pending_interrupt(thread_id):
    """读取指定线程的状态快照，返回第一个未处理的 LangGraph 中断。

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


# ========================= 会话辅助 =========================

def get_conversation_messages(thread_id):
    """读取指定线程的历史消息（LangChain 消息对象列表，无消息返回空）。"""
    try:
        state = chatbot.get_state(config={"configurable": {"thread_id": thread_id}})
        return state.values.get("messages", [])
    except Exception:
        return []


def get_all_threads():
    """列出所有对话线程 ID。"""
    all_threads = set()
    for ckpt in checkpoint.list(None):
        all_threads.add(ckpt.config['configurable']['thread_id'])

    return list(all_threads)


def delete_thread(thread_id):
    """删除一个对话线程的全部历史（checkpoint 全清）。"""
    checkpoint.delete_thread(thread_id)
