from agentic_chatbot_hitl_backend import (
    chatbot,
    get_all_threads,
    ingest_rag_document
)

from langchain_core.messages import (
    BaseMessage,
    HumanMessage,
    AIMessage,
    ToolMessage
)

from langgraph.types import Command

import streamlit as st
import uuid
import tempfile
import os


# 为每个新对话生成唯一线程ID
def generate_thread_id():
    return str(uuid.uuid4())


# 将新线程ID加入对话列表
def add_thread(thread_id):

    # 避免重复添加同一个线程
    if thread_id not in st.session_state["chat_threads"]:
        st.session_state["chat_threads"].append(thread_id)


# 创建全新的对话
def reset_chat():

    # 生成并分配新线程ID
    st.session_state["thread_id"] = generate_thread_id()

    # 清空当前聊天消息
    st.session_state["message_history"] = []

    # ========================= HITL ADDED =========================
    # 清除任何待处理的人工审批请求
    st.session_state["pending_hitl"] = None
    # =============================================================

    # 将新线程加入对话列表
    add_thread(st.session_state["thread_id"])


# 从 LangGraph checkpointer 加载历史对话
def load_conversation(thread_id):

    # 获取选中线程的已保存状态
    state = chatbot.get_state(
        config={
            "configurable": {
                "thread_id": thread_id
            }
        }
    )

    # 返回已保存的消息，无消息时返回空列表
    return state.values.get("messages", [])


# ========================= HITL 辅助函数 =========================

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


def save_pending_interrupt(thread_id, interrupt_object):
    """
    将待处理的中断信息保存到 Streamlit 状态中。
    """

    st.session_state["pending_hitl"] = {
        "thread_id": thread_id,
        "prompt": str(interrupt_object.value)
    }


def sync_pending_interrupt(thread_id):
    """
    将 Streamlit 的 HITL 状态与 LangGraph 检查点同步。

    在以下场景中恢复待处理的审批请求：
    - Streamlit 重新运行
    - 浏览器刷新
    - 切换对话
    """

    pending_interrupt = get_pending_interrupt(thread_id)

    if pending_interrupt is not None:

        save_pending_interrupt(
            thread_id,
            pending_interrupt
        )

    else:

        current_pending = st.session_state.get(
            "pending_hitl"
        )

        if (
            current_pending is not None
            and current_pending.get("thread_id") == thread_id
        ):
            st.session_state["pending_hitl"] = None


def resume_hitl_execution(decision):
    """
    恢复被中断的 LangGraph 执行。

    Args:
        decision:
            "yes" 批准操作。
            "no" 拒绝操作。
    """

    pending_hitl = st.session_state.get(
        "pending_hitl"
    )

    if not pending_hitl:

        st.warning(
            "没有待处理的审批操作。"
        )

        return

    # 获取触发中断的线程
    interrupted_thread_id = pending_hitl["thread_id"]

    # 恢复时必须使用相同的线程 ID
    resume_config = {
        "configurable": {
            "thread_id": interrupted_thread_id
        },
        "metadata": {
            "thread_id": interrupted_thread_id
        },
        "run_name": "hitl_resume_trace",
    }

    try:

        # 显示恢复后的响应
        with st.chat_message("assistant"):

            status_placeholder = st.empty()
            status_placeholder.info("🔄 正在恢复执行...")

            def resumed_ai_only_stream():

                # 携带人工决策恢复图谱执行
                for message_chunk, metadata in chatbot.stream(
                    Command(resume=decision),
                    config=resume_config,
                    stream_mode="messages",
                ):

                    # 更新工具执行状态
                    if isinstance(
                        message_chunk,
                        ToolMessage
                    ):

                        tool_name = getattr(
                            message_chunk,
                            "name",
                            "tool"
                        )

                        status_placeholder.info(f"🔧 正在调用 `{tool_name}` …")

                    # 只流式输出 AI 生成的文本
                    if isinstance(
                        message_chunk,
                        AIMessage
                    ):

                        if message_chunk.content:
                            yield message_chunk.content

            # 展示流式输出的最终回答
            resumed_ai_message = st.write_stream(
                resumed_ai_only_stream()
            )

            # 检查是否又触发了新的中断
            next_interrupt = get_pending_interrupt(
                interrupted_thread_id
            )

            if next_interrupt is not None:

                save_pending_interrupt(
                    interrupted_thread_id,
                    next_interrupt
                )

                status_placeholder.warning("⚠️ 需要再次审批")

            else:

                # 没有更多待审批项
                st.session_state["pending_hitl"] = None

                status_placeholder.success("✅ 操作已完成")

        # 将助手响应保存到 Streamlit UI 历史中
        if resumed_ai_message:

            st.session_state["message_history"].append({
                "role": "assistant",
                "content": resumed_ai_message
            })

        # 重新运行以正常顺序显示响应
        st.rerun()

    except Exception as error:

        st.error(
            f"无法恢复执行: {error}"
        )


# ========================= 页面配置 =========================

st.set_page_config(
    page_title="智能聊天助手",
    page_icon="🤖"
)

# 显示主标题
st.title("LangGraph 智能聊天助手")


# 首次运行时初始化 message_history
if "message_history" not in st.session_state:
    st.session_state["message_history"] = []


# 首次运行时创建线程 ID
if "thread_id" not in st.session_state:
    st.session_state["thread_id"] = generate_thread_id()


# 存储所有对话线程 ID 的列表
if "chat_threads" not in st.session_state:
    st.session_state["chat_threads"] = get_all_threads()


# ========================= HITL ADDED =========================

# 存储当前待处理的人工审批请求
if "pending_hitl" not in st.session_state:
    st.session_state["pending_hitl"] = None

# =============================================================


# 将当前线程加入对话列表
add_thread(st.session_state["thread_id"])


# ========================= HITL ADDED =========================

# 页面刷新或重新运行后恢复待处理的审批
sync_pending_interrupt(
    st.session_state["thread_id"]
)

# =============================================================


# ========================= 侧边栏 - 对话管理 =========================

def get_thread_title(thread_id):
    """从线程的第一条用户消息中提取对话标题"""
    messages = load_conversation(thread_id)
    for msg in messages:
        if isinstance(msg, HumanMessage) and msg.content:
            # 取第一条用户消息的前20个字符做标题
            title = msg.content.strip().replace("\n", " ")
            return title[:20] + ("…" if len(title) > 20 else "")
    return "空对话"


# 显示侧边栏标题
st.sidebar.title("我的对话")


# 新建对话按钮
if st.sidebar.button("新建对话"):

    # 重置当前对话并创建新线程
    reset_chat()

    # 重新运行 Streamlit 以更新界面
    st.rerun()


# 倒序显示所有对话线程（最新在最上面）
for thread_id in st.session_state["chat_threads"][::-1]:

    # 提取对话标题
    title = get_thread_title(thread_id)

    # 当前选中的线程用特殊标识
    is_active = thread_id == st.session_state["thread_id"]
    prefix = "● " if is_active else "◌ "
    button_label = prefix + title

    # 为每个对话创建侧边栏按钮
    if st.sidebar.button(
        button_label,
        key=thread_id
    ):

        # 将选中的线程设为当前线程
        st.session_state["thread_id"] = thread_id

        # 加载选中线程下的已保存消息
        messages = load_conversation(thread_id)

        # 临时列表，将 LangChain 消息
        # 转换为 Streamlit 所需的消息格式
        temp_messages = []

        # 遍历所有已保存的消息
        for message in messages:

            # 判断是否为用户发送的消息
            if isinstance(message, HumanMessage):
                role = "user"

            # 判断是否为 AI 发送的消息
            elif isinstance(message, AIMessage):
                role = "assistant"

            # 忽略其他消息类型，如 ToolMessage
            else:
                continue

            # 将 LangChain 消息转换为字典
            temp_messages.append({
                "role": role,
                "content": message.content
            })

        # 用选中的对话替换当前界面历史
        st.session_state["message_history"] = temp_messages

        # ========================= HITL ADDED =========================

        # 恢复该对话中待处理的审批
        sync_pending_interrupt(thread_id)

        # =============================================================

        # 重新运行应用以显示加载的消息
        st.rerun()


# ========================= 主聊天区域 =========================

# 显示当前对话名称
current_title = get_thread_title(st.session_state["thread_id"])
st.caption(f"📍 当前对话：{current_title}")

# 显示当前选中对话中的所有消息
for message in st.session_state["message_history"]:

    # 根据角色创建用户或助手的聊天气泡
    with st.chat_message(message["role"]):

        # 显示消息内容
        st.text(message["content"])


# ========================= HITL 审批界面 =========================

# 获取当前待处理的审批请求
pending_hitl = st.session_state.get(
    "pending_hitl"
)

# 检查待处理审批是否属于当前选中的对话
current_thread_has_pending_hitl = (
    pending_hitl is not None
    and pending_hitl.get("thread_id")
    == st.session_state["thread_id"]
)


# 显示审批控件
if current_thread_has_pending_hitl:

    st.warning(
        "🧑 需要人工审批\n\n"
        f"{pending_hitl['prompt']}"
    )

    approve_column, reject_column = st.columns(2)

    # 批准按钮
    with approve_column:

        if st.button(
            "✅ 批准",
            key=f"approve_{st.session_state['thread_id']}",
            type="primary",
            use_container_width=True
        ):

            # 将 "yes" 传回 interrupt()
            resume_hitl_execution("yes")

    # 拒绝按钮
    with reject_column:

        if st.button(
            "❌ 拒绝",
            key=f"reject_{st.session_state['thread_id']}",
            use_container_width=True
        ):

            # 将 "no" 传回 interrupt()
            resume_hitl_execution("no")


# ========================= 固定底部聊天输入框（支持 PDF 上传） =========================

# 将 st.chat_input 直接放在主区域。
# 这样它会固定在屏幕底部。
#
# accept_file=True 在输入框中添加附件按钮。
# file_type=["pdf"] 仅允许上传 PDF 文件。
submission = st.chat_input(
    "在这里输入...",
    accept_file=True,
    file_type=["pdf"],

    # 等待人工审批时禁用输入
    disabled=current_thread_has_pending_hitl
)


# 默认用户输入值
user_input = None


# 处理提交的文本和 PDF
if submission:

    # 获取用户输入的文本
    user_input = submission.text

    # 获取上传的文件
    # accept_file 启用时始终为列表
    uploaded_files = submission.files

    # 如果附带了 PDF，则处理
    if uploaded_files:

        uploaded_pdf = uploaded_files[0]

        # 保存临时文件路径
        temporary_file_path = None

        try:

            # 将上传的 PDF 保存为临时本地文件
            with tempfile.NamedTemporaryFile(
                delete=False,
                suffix=".pdf"
            ) as temporary_file:

                temporary_file.write(
                    uploaded_pdf.getvalue()
                )

                temporary_file_path = temporary_file.name

            # 调用后端的 RAG 文档处理函数
            with st.spinner(
                f"正在处理 {uploaded_pdf.name}..."
            ):

                ingest_rag_document(
                    temporary_file_path
                )

            # 显示 PDF 处理成功提示
            st.toast(
                f"{uploaded_pdf.name} 处理成功。",
                icon="✅"
            )

        except Exception as error:

            # 显示 PDF 处理错误
            st.error(
                f"PDF 处理失败: {error}"
            )

        finally:

            # 处理完成后删除临时 PDF 文件
            if (
                temporary_file_path
                and os.path.exists(temporary_file_path)
            ):
                os.remove(temporary_file_path)


# 当用户提交文本消息后执行
if user_input:

    # 将用户消息保存到 Streamlit session state
    st.session_state["message_history"].append({
        "role": "user",
        "content": user_input
    })

    # 在聊天界面中显示用户消息
    with st.chat_message("user"):
        st.text(user_input)

    # 将当前线程 ID 传递给 LangGraph
    # LangGraph 使用此 ID 来保存和恢复对话记忆
    CONFIG = {
        "configurable": {
            "thread_id": st.session_state["thread_id"]
        },
        "metadata": {
            "thread_id": st.session_state["thread_id"]
        },
        "run_name": "chat_trace",
    }

    # 助手流式输出区域
    with st.chat_message("assistant"):

        # 收集工具调用状态
        tool_names = []
        status_placeholder = st.empty()

        def ai_only_stream():

            for message_chunk, metadata in chatbot.stream(
                {
                    "messages": [
                        HumanMessage(content=user_input)
                    ]
                },
                config=CONFIG,
                stream_mode="messages",
            ):

                # 遇到 ToolMessage 时记录工具名
                if isinstance(message_chunk, ToolMessage):
                    name = getattr(message_chunk, "name", "tool")
                    if name not in tool_names:
                        tool_names.append(name)
                        status_placeholder.info(f"🔧 正在调用 `{name}` …")

                # 只流式输出 AI 文本
                if isinstance(message_chunk, AIMessage):
                    yield message_chunk.content

            # ========================= HITL ADDED =========================

            pending_interrupt = get_pending_interrupt(
                st.session_state["thread_id"]
            )

            if pending_interrupt is not None:
                save_pending_interrupt(
                    st.session_state["thread_id"],
                    pending_interrupt
                )
                yield (
                    "\n\n⚠️ 此操作需要您的审批。"
                    "请使用下方的批准或拒绝按钮。"
                )

            # =============================================================

        ai_message = st.write_stream(ai_only_stream())

        # 工具执行完毕，更新最终状态
        if tool_names:
            if get_pending_interrupt(st.session_state["thread_id"]) is not None:
                status_placeholder.success("⏸️ 等待人工审批")
            else:
                status_placeholder.success("✅ 工具执行完毕")

    # 将完整的助手响应保存到 Streamlit session state
    st.session_state["message_history"].append({
        "role": "assistant",
        "content": ai_message
    })

    # ========================= HITL ADDED =========================

    # 审批控件在脚本前面已渲染。
    # 重新运行以确保 interrupt() 后审批按钮立即出现。
    if (
        st.session_state.get("pending_hitl") is not None
        and st.session_state["pending_hitl"].get("thread_id")
        == st.session_state["thread_id"]
    ):
        st.rerun()

    # =============================================================