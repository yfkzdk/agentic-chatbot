# Agentic Chatbot — 基于 LangGraph 的多工具智能聊天机器人

基于 LangGraph 编排多智能体工具调用架构，集成 Tavily 联网搜索、OpenWeather 天气查询、Alpha Vantage 股票行情、FAISS 向量检索等 7 个工具节点，支持 Human-in-the-Loop 人工审批与 PDF 文档 RAG 问答。

## 功能特性

- 🤖 **多工具智能调度** — LangGraph 状态驱动，自动路由到合适的工具
- 📄 **PDF RAG 问答** — 上传 PDF 文档，基于 FAISS + 中文 Embedding 语义检索
- 🌐 **联网搜索** — Tavily 实时搜索
- 🌤️ **天气查询** — OpenWeather API 实时天气
- 📈 **股票查询 / 模拟购买** — Alpha Vantage 行情 + HITL 人工审批
- 🧮 **数学计算** — 内置安全沙箱计算器
- 💬 **中文对话** — DeepSeek 大模型驱动，全中文交互
- 📝 **多会话管理** — SQLite 持久化，支持对话切换与恢复

## 技术栈

Python · LangGraph · DeepSeek · Streamlit · Tavily · FAISS · SQLite · Docker

## 快速开始

### 1. 配置 API Key

```bash
cp .env.example .env
# 编辑 .env，填入你的 API Key（DeepSeek、Tavily、OpenWeather、Alpha Vantage）
```

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

### 3. 启动

```bash
# 方式一：Streamlit 前端（完整聊天界面）
streamlit run app_hitl.py --server.port 8501

# 方式二：FastAPI 服务（供其他应用调用，SSE 流式）
uvicorn api.main:app --host 0.0.0.0 --port 8000
```

访问 http://localhost:8501（前端）或 http://localhost:8000/docs（API 文档）

### Docker 部署

```bash
docker build -t agentic-chatbot .
docker run --env-file .env -p 8501:8501 agentic-chatbot
```

## 项目结构

```
├── app_hitl.py                      # Streamlit 前端（中文 UI + HITL 审批）
├── agentic_chatbot_hitl_backend.py  # LangGraph 后端（7 个工具 + 图谱编排）
├── requirements.txt                 # Python 依赖
├── Dockerfile                       # Docker 构建文件
├── .dockerignore
└── .env.example                     # 环境变量模板
```

## License

MIT
