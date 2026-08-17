"""Streamlit 前端（纯客户端）。

通过 HTTP 调用受保护的 FastAPI 后端（api/），不再直连 backend。
用户需先注册/登录，拿到 JWT 后才能对话、管理会话、上传 PDF。
"""
import json

import requests
import streamlit as st

API_BASE = "http://127.0.0.1:8000"


# ========================= 基础状态 =========================

def api_headers():
    """带 JWT 的请求头；未登录返回空。"""
    token = st.session_state.get("token")
    if not token:
        return {}
    return {"Authorization": f"Bearer {token}"}


# ========================= 认证 =========================

def register(email, password):
    resp = requests.post(f"{API_BASE}/auth/register", json={"email": email, "password": password})
    return resp


def login(email, password):
    resp = requests.post(
        f"{API_BASE}/auth/login",
        data={"username": email, "password": password},
    )
    if resp.status_code == 200:
        st.session_state["token"] = resp.json()["access_token"]
        st.session_state["email"] = email
    return resp


def logout():
    for key in ["token", "email", "message_history", "chat_threads", "thread_id", "pending_hitl"]:
        st.session_state.pop(key, None)
    st.rerun()


# ========================= 会话 =========================

def fetch_threads():
    resp = requests.get(f"{API_BASE}/threads/", headers=api_headers())
    if resp.status_code == 200:
        return resp.json()["threads"]
    return []


def fetch_messages(thread_id):
    resp = requests.get(f"{API_BASE}/threads/{thread_id}/messages", headers=api_headers())
    if resp.status_code == 200:
        return resp.json()["messages"]
    return []


def delete_thread(thread_id):
    requests.delete(f"{API_BASE}/threads/{thread_id}", headers=api_headers())


def stream_chat(thread_id, message):
    """调用 /chat/stream，返回 (事件列表, 新 thread_id)。"""
    headers = {**api_headers(), "Content-Type": "application/json"}
    resp = requests.post(
        f"{API_BASE}/chat/stream",
        json={"message": message, "thread_id": thread_id},
        headers=headers,
        stream=True,
    )
    new_thread_id = resp.headers.get("X-Thread-ID", thread_id)
    events = []
    for line in resp.iter_lines():
        if line:
            try:
                line = line.decode("utf-8")
                if line.startswith("data: "):
                    events.append(json.loads(line[6:]))
            except Exception:
                continue
    return events, new_thread_id


def resume_chat(thread_id, decision):
    """调用 /chat/resume，返回事件列表。"""
    headers = {**api_headers(), "Content-Type": "application/json"}
    resp = requests.post(
        f"{API_BASE}/chat/resume",
        json={"thread_id": thread_id, "decision": decision},
        headers=headers,
        stream=True,
    )
    events = []
    for line in resp.iter_lines():
        if line:
            try:
                line = line.decode("utf-8")
                if line.startswith("data: "):
                    events.append(json.loads(line[6:]))
            except Exception:
                continue
    return events


# ========================= 事件解析 =========================

def text_from_events(events):
    """从 SSE 事件里提取 AI 文本。"""
    parts = []
    for e in events:
        if e.get("type") == "text":
            content = e.get("content", "")
            if content:
                parts.append(content)
    return "".join(parts)


def hitl_from_events(events):
    """从事件里提取 HITL 审批信息。"""
    for e in events:
        if e.get("type") == "hitl":
            return e
    return None


def error_from_events(events):
    for e in events:
        if e.get("type") == "error":
            return e.get("detail")
    return None


# ========================= 页面 =========================

st.set_page_config(page_title="研发知识助手", page_icon="🤖")

# 未登录 → 显示登录/注册页
if "token" not in st.session_state:
    st.title("🤖 研发知识助手")
    tab_login, tab_register = st.tabs(["登录", "注册"])

    with tab_login:
        with st.form("login_form"):
            email = st.text_input("邮箱")
            password = st.text_input("密码", type="password")
            submitted = st.form_submit_button("登录")
            if submitted:
                resp = login(email, password)
                if resp.status_code == 200:
                    st.rerun()
                else:
                    st.error(resp.json().get("detail", "登录失败"))

    with tab_register:
        with st.form("register_form"):
            email = st.text_input("邮箱", key="reg_email")
            password = st.text_input("密码", type="password", key="reg_password")
            submitted = st.form_submit_button("注册")
            if submitted:
                resp = register(email, password)
                if resp.status_code == 201:
                    st.success("注册成功，请切换到登录页登录")
                else:
                    st.error(resp.json().get("detail", "注册失败"))

    st.stop()


# 已登录 → 主界面
with st.sidebar:
    st.write(f"👤 {st.session_state.get('email', '')}")
    if st.button("退出登录"):
        logout()

    st.title("我的对话")
    if st.button("新建对话"):
        st.session_state["message_history"] = []
        st.session_state["thread_id"] = None
        st.session_state["pending_hitl"] = None
        st.rerun()

    chat_threads = fetch_threads()
    st.session_state["chat_threads"] = chat_threads

    for tid in reversed(chat_threads):
        if st.button(f"💬 {tid[:12]}…", key=tid):
            st.session_state["thread_id"] = tid
            st.session_state["message_history"] = fetch_messages(tid)
            st.session_state["pending_hitl"] = None
            st.rerun()


st.title("🤖 研发知识助手")

if "message_history" not in st.session_state:
    st.session_state["message_history"] = []
if "thread_id" not in st.session_state:
    st.session_state["thread_id"] = None
if "pending_hitl" not in st.session_state:
    st.session_state["pending_hitl"] = None

# 渲染历史消息
for message in st.session_state["message_history"]:
    with st.chat_message(message["role"]):
        st.text(message["content"])

# HITL 审批控件
pending_hitl = st.session_state.get("pending_hitl")
if pending_hitl:
    st.warning(f"🧑 需要人工审批\n\n{pending_hitl.get('prompt', '请确认操作')}")

    c1, c2 = st.columns(2)
    with c1:
        if st.button("✅ 批准", type="primary"):
            events = resume_chat(pending_hitl["thread_id"], "yes")
            err = error_from_events(events)
            if err:
                st.error(err)
            else:
                answer = text_from_events(events)
                if answer:
                    st.session_state["message_history"].append({"role": "assistant", "content": answer})
                st.session_state["pending_hitl"] = None
                st.rerun()
    with c2:
        if st.button("❌ 拒绝"):
            events = resume_chat(pending_hitl["thread_id"], "no")
            err = error_from_events(events)
            if err:
                st.error(err)
            else:
                answer = text_from_events(events)
                if answer:
                    st.session_state["message_history"].append({"role": "assistant", "content": answer})
                st.session_state["pending_hitl"] = None
                st.rerun()

# 输入框
submission = st.chat_input("在这里输入...")
if submission:
    user_input = submission

    st.session_state["message_history"].append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.text(user_input)

    with st.chat_message("assistant"):
        placeholder = st.empty()
        placeholder.info("思考中…")

        events, thread_id = stream_chat(st.session_state["thread_id"], user_input)
        st.session_state["thread_id"] = thread_id

        answer = text_from_events(events)
        hitl = hitl_from_events(events)
        err = error_from_events(events)

        if err:
            placeholder.error(err)
        elif answer:
            placeholder.text(answer)
            st.session_state["message_history"].append({"role": "assistant", "content": answer})
        else:
            placeholder.text("（无回复）")

        if hitl:
            st.session_state["pending_hitl"] = {
                "thread_id": thread_id,
                "prompt": hitl.get("prompt", "请确认操作"),
            }
            st.rerun()
