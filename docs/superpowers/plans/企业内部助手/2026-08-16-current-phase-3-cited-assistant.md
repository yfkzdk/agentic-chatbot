# 阶段 3：带来源的部门知识与流程助手

**目标：** 把通用聊天图改造成只在首发场景内工作、强制引用知识库、支持草稿生成和人工反馈的内部助手。

## 文件计划

- Create: `backend/scenarios/registry.py` — 场景配置、提示词版本、输出 schema、工具白名单。
- Create: `backend/scenarios/knowledge_assistant.py` — 首发部门知识助手编排。
- Create: `backend/response_guard.py` — 引用、权限、敏感信息和输出边界校验。
- Create: `api/routers/feedback.py`, `api/schemas/feedback.py`。
- Create: `tests/backend/test_citations.py`, `tests/backend/test_response_guard.py`, `tests/api/test_feedback.py`。
- Modify: `backend/graph.py`, `backend/tools.py`, `api/routers/chat.py`, `api/schemas.py`, `app_hitl.py`。

## 执行清单

- [ ] 将现有 `chat_node` 的通用系统提示词替换为按 `scenario_key` 加载的版本；请求必须指定且只能选择用户已授权场景。
- [ ] 移除股票购买、天气和通用联网搜索等非企业首发工具；将 `calculator` 移出默认工具集，直至实现 AST 安全解析和场景授权。
- [ ] 当问题属于知识问答时，先检索发布知识库；模型输出固定为 `answer`、`citations`、`knowledge_release`、`limitations`、`requires_human_review`。
- [ ] `response_guard` 校验每个事实性答案至少有一条用户有权读取、未过期的证据；否则输出“当前已授权知识库未找到依据”，不编造答案。
- [ ] 对总结和草稿生成显示“草稿，需人工确认”，并附输入资料范围；禁止模型声称已经执行操作或代表公司承诺。
- [ ] 在 UI 显示来源抽屉、知识版本、反馈按钮和“报告错误/资料过期”入口；不在界面暴露其他工作区会话。
- [ ] 用阶段 0 的 30 条任务运行离线测试，记录回答、引用、模型版本、提示词版本、耗时和成本。

**验收：** 100% 知识性回答都有可访问引用；权限不足、无答案、过期资料、注入文本和超范围请求均安全降级；用户反馈进入审计队列。
