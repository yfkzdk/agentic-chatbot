# 阶段 1：把演示基座改为安全多用户核心

**目标：** 在保留 FastAPI、LangGraph 和 Streamlit 的前提下，消除当前全局会话、公开接口和单机状态。

## 当前代码与改造决策

| 当前文件 | 当前问题 | 本阶段结果 |
|---|---|---|
| `api/main.py` | `CORS=*`，无认证 | 只允许企业前端域名，接入 OIDC/JWT 中间件 |
| `api/schemas.py` | 聊天请求没有用户/工作区语义 | 拆为 `api/schemas/`，引入工作区和版本字段 |
| `api/routers/chat.py` | 任意 `thread_id` 可聊天/恢复 | 从身份注入工作区，校验会话所有权 |
| `api/routers/threads.py` | 可列出/删除所有会话 | 仅返回当前用户可见的会话 |
| `backend/graph.py` | 相对路径 `chatbot.db`，单连接 | 使用可配置的生产数据库 checkpointer |
| `app_hitl.py` | 直接读写图状态，展示全局会话 | 只调用受保护 API，不直连 backend |

## 文件计划

- Create: `backend/settings.py` — 环境配置、启动期必填项校验。
- Create: `backend/db.py` — 数据库连接、迁移入口和健康检查。
- Create: `backend/audit.py` — 安全审计事件写入。
- Create: `api/dependencies/auth.py` — JWT 验证与 `CurrentActor`。
- Create: `api/dependencies/workspace.py` — 会话/知识库工作区授权。
- Create: `api/schemas/auth.py`, `api/schemas/chat.py`, `api/schemas/workspace.py`。
- Create: `tests/api/test_auth.py`, `tests/api/test_thread_isolation.py`, `tests/backend/test_settings.py`。
- Modify: `api/main.py`, `api/routers/chat.py`, `api/routers/threads.py`, `api/routers/health.py`, `backend/graph.py`, `app_hitl.py`, `requirements.txt`, `Dockerfile`。

## 执行清单

- [ ] 先写测试：无 token 请求 `POST /chat/stream` 返回 401；用户 A 访问用户 B 的会话返回 404；管理员与普通用户的权限不同。
- [ ] 实现 `CurrentActor(user_id, organization_id, roles)`；`organization_id` 不从请求体读取，只从已验证令牌映射。
- [ ] 给会话、知识文档、审计事件增加 `organization_id`、`owner_id`、`created_at`、`updated_at` 和不可变 ID；所有查询在仓储层强制按工作区过滤。
- [ ] 用 PostgreSQL 替换 `chatbot.db` 作为生产运行时依赖；本地开发允许单独 `.env` 指向临时数据库，不允许生产回退 SQLite。
- [ ] 把 Streamlit 改为 FastAPI 客户端：登录后保存短期 token，只通过 `/api` 读写数据。
- [ ] 限制 CORS 域名、请求体和并发数；SSE 客户端断开时取消下游模型任务。
- [ ] `/health/live` 只确认进程；`/health/ready` 检查数据库、已发布知识库和必要配置但不泄露密钥。
- [ ] 用非 root 用户运行 Docker；固定依赖版本、启用依赖/镜像漏洞扫描。

**验收：** `pytest tests/api/test_auth.py tests/api/test_thread_isolation.py tests/backend/test_settings.py -v` 通过；跨组织数据读取为零；恢复一份数据库备份成功；旧公开会话接口不再可用。
