# 阶段 1：安全生产底座 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将当前单用户演示服务改造成具备身份、机构隔离、审计、限流和可恢复性的医生端服务。

**Architecture:** FastAPI 作为唯一 API 入口；OIDC 身份映射为机构、角色和用户；PostgreSQL 保存事务数据与 LangGraph 检查点，对象存储保存文件，向量库按机构和知识发布版本隔离。

**Tech Stack:** FastAPI、Pydantic、PostgreSQL、Alembic、OIDC/JWT、Redis、S3 兼容对象存储、OpenTelemetry、pytest。

---

### Task 1：配置、身份与访问控制

**Files:**
- Create: `backend/settings.py`
- Create: `api/dependencies/auth.py`
- Create: `api/dependencies/authorization.py`
- Modify: `api/main.py`
- Test: `tests/api/test_authorization.py`

- [ ] 写失败测试：未携带令牌访问 `POST /cases` 返回 401；医生读取另一机构病例返回 404；知识管理员可以访问知识接口。
- [ ] 实现 `CurrentActor(user_id, organization_id, roles)`，只接受经验证的 OIDC JWT，并以 `organization_id` 作为所有数据查询的强制过滤条件。
- [ ] 用依赖注入保护所有现有路由；删除公开的线程列表/删除能力或仅保留管理员受控迁移端点。
- [ ] Run: `pytest tests/api/test_authorization.py -v`。Expected: PASS。
- [ ] Commit: `feat: add organization scoped authentication`。

### Task 2：替换演示持久化与全局知识库

**Files:**
- Create: `backend/db/session.py`
- Create: `backend/db/models.py`
- Create: `alembic/versions/001_initial_clinical_schema.py`
- Create: `backend/storage/cases.py`
- Modify: `backend/graph.py`
- Test: `tests/backend/test_organization_isolation.py`

- [ ] 写失败测试：两个机构创建同名病例 ID 时不能互相读取；删除一个机构的病例不影响另一机构数据。
- [ ] 创建 `cases`、`audit_events`、`knowledge_releases`、`knowledge_documents` 和 `clinician_feedback` 表；所有业务表拥有不可为空的 `organization_id`。
- [ ] 将 `chatbot.db` 和相对路径 SQLite 检查点替换为 PostgreSQL checkpointer；将向量索引命名空间设为 `organization_id/knowledge_release_id`。
- [ ] Run: `pytest tests/backend/test_organization_isolation.py -v`。Expected: PASS。
- [ ] Commit: `feat: replace global storage with tenant scoped persistence`。

### Task 3：输入、上传与工具安全

**Files:**
- Create: `backend/security/input_limits.py`
- Create: `backend/security/safe_math.py`
- Modify: `api/routers/ingest.py`
- Modify: `backend/tools.py`
- Test: `tests/security/test_input_limits.py`
- Test: `tests/security/test_safe_math.py`

- [ ] 写失败测试：超限 PDF、伪造 MIME、超长消息和 AST 以外表达式被拒绝；`2 + 2` 返回 `4`。
- [ ] 限制请求体、文件大小、页数、解析时间和并发；验证 PDF 文件头并在隔离 worker 解析。
- [ ] 删除 `eval`，使用 AST 白名单仅接受数字、括号、`+ - * / **` 和明确列出的数学函数。
- [ ] Run: `pytest tests/security -v`。Expected: PASS。
- [ ] Commit: `fix: enforce input limits and remove eval`。

### Task 4：可观测性、恢复与安全部署

**Files:**
- Create: `backend/observability.py`
- Modify: `api/routers/health.py`
- Modify: `Dockerfile`
- Create: `docker-compose.production.yml`
- Test: `tests/api/test_health.py`

- [ ] 实现 `/health/live` 和 `/health/ready`；ready 检查数据库、对象存储、已发布知识库和关键配置，不输出密钥。
- [ ] 为请求记录 request ID、用户/机构伪名、延迟、模型/工具调用、错误码；禁止记录原始敏感文本到普通日志。
- [ ] 用非 root 用户运行 API；使用固定镜像摘要、密钥注入、TLS 反向代理和仅启动 ASGI 服务的容器入口。
- [ ] 执行数据库恢复演练和备份校验；Run: `pytest tests/api/test_health.py -v`。Expected: PASS。
- [ ] Commit: `feat: add observability readiness and hardened deployment`。
