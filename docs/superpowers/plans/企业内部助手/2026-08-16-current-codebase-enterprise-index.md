# 基于现有代码的企业内部助手升级计划

当前代码已经具备可复用原型能力：Streamlit 聊天界面（`app_hitl.py`）、FastAPI（`api/`）、LangGraph 工作流（`backend/graph.py`）、PDF RAG（`backend/rag.py`）、工具（`backend/tools.py`）和 SQLite 会话。它不适合直接上线为企业服务，因为会话、文档和权限均为全局状态。

本计划先把它改成“部门知识与流程助手”：对已授权制度、项目资料、产品资料和运行手册进行带来源的问答、摘要和草稿生成；默认只读，不直接执行业务动作。确认部门价值后再按审批扩展工具。

| 阶段 | 文档 | 基于当前代码的主要改造 | 退出条件 |
|---|---|---|---|
| 0 | `2026-08-16-current-phase-0-business-scope.md` | 选择一个部门和三个任务，建立知识与验收标准 | 业务/内容/安全负责人批准 |
| 1 | `2026-08-16-current-phase-1-secure-core.md` | 改造 `api/main.py`、`api/schemas.py`、路由和 SQLite 全局状态 | 登录、隔离、审计、测试通过 |
| 2 | `2026-08-16-current-phase-2-knowledge-rag.md` | 重构 `backend/rag.py` 和 `ingest.py` 为受控知识库 | 已发布知识才可被授权用户检索 |
| 3 | `2026-08-16-current-phase-3-cited-assistant.md` | 重构 `graph.py`、`chat.py`、`app_hitl.py` 为带引用的部门助手 | 离线任务集达到质量阈值 |
| 4 | `2026-08-16-current-phase-4-workflow-tools.md` | 替换天气/股票/计算器等演示工具为受控流程工具 | 影子运行和审批测试通过 |
| 5 | `2026-08-16-current-phase-5-pilot-operations.md` | Docker、CI、监控、备份、灰度和部门试点 | 连续两轮治理评审通过 |

不建议当前就实现 `ARCHITECTURE_DESIGN.md` 中的 Java、Kafka、React 全栈方案。先在现有 Python 基座完成一个部门的真实闭环；当出现多部门、高并发、复杂审批或现有身份平台整合需求时，再把 FastAPI 保留为 AI 服务并逐步拆出业务层。
