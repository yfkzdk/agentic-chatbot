# Agentic Chatbot — Java 主干 + Python AI 微服务 架构设计文档

> 版本：v1.0 | 日期：2026-08-08 | 状态：设计评审中

---

## 一、背景与动机

### 1.1 现状

当前系统为 **Streamlit 单体应用**（Python），通过 Sealos 单容器部署。核心技术栈：

- **前端**：Streamlit（Python 原生 Chat UI）
- **AI 引擎**：LangGraph + DeepSeek + 6 个 Tool（搜索/天气/股票/计算器/RAG/HITL 审批）
- **向量检索**：FAISS + bge-small-zh-v1.5 Embedding
- **持久化**：SQLite（对话历史 checkpoints + FAISS 索引）
- **可观测性**：LangSmith Tracing

### 1.2 当前架构的局限性

| 问题 | 影响 |
|------|------|
| 无用户认证 | 任何人打开链接都能用，无法区分用户、无法计费 |
| 无流控保护 | 单进程 Streamlit，高并发或恶意刷接口时直接崩溃 |
| 前端能力弱 | Streamlit 无法做复杂交互，响应式差，移动端体验差 |
| 紧耦合 | 前端 + 后端 + AI 逻辑混在 2 个 .py 文件里，难以拆分扩展 |
| 无审计追溯 | 无法记录"谁在什么时候做了什么"，日志散落在容器 stdout |
| 部署脆弱 | 只有一个 Pod，挂了就全挂，无法灰度、无法回滚 |

### 1.3 改造目标

引入 **Java 业务主干**，将现有系统拆分为三层：

```
【表现层】React/Vue SPA
     │
【业务层】Java Spring Boot（鉴权、限流、业务编排、数据持久化）
     │
【AI 层】Python FastAPI（LangGraph + RAG + 大模型调用）
```

核心原则：**业务归 Java，AI 归 Python，前端独立部署**。

---

## 二、全景架构图

```
                          ┌──────────────────────────────────────┐
                          │          CDN / Nginx 静态托管          │
                          │     (React SPA / Vue SPA / 小程序)     │
                          └──────────────┬───────────────────────┘
                                         │ HTTPS (WSS)
                                         ▼
┌────────────────────────────────────────────────────────────────────┐
│                     Java Spring Boot 业务层                         │
│                                                                    │
│  ┌──────────┐  ┌───────────┐  ┌────────────┐  ┌───────────────┐  │
│  │ 用户模块  │  │ 认证模块   │  │ 对话模块    │  │ 文件模块       │  │
│  │ 注册/登录 │  │ JWT Token │  │ CRUD / 列表 │  │ PDF 上传/存储  │  │
│  │ 个人信息  │  │ OAuth2    │  │ 历史查询    │  │ 元数据管理     │  │
│  └──────────┘  └───────────┘  └────────────┘  └───────────────┘  │
│                                                                    │
│  ┌──────────┐  ┌───────────┐  ┌────────────┐  ┌───────────────┐  │
│  │ 限流模块  │  │ 计费模块   │  │ 管理后台    │  │ AI 代理层      │  │
│  │ Bucket4j │  │ 额度管理  │  │ 用户管理    │  │ REST → Python │  │
│  │ IP/用户级 │  │ 消费记录  │  │ 运营数据    │  │ 超时/重试/降级 │  │
│  └──────────┘  └───────────┘  └────────────┘  └───────────────┘  │
│                                                                    │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │                    消息队列 (Kafka)                           │  │
│  │  · 对话日志异步写入      · AI 调用审计事件                     │  │
│  │  · PDF 异步处理          · 用户行为埋点                        │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                                                                    │
│  ┌────────────────┐  ┌─────────────────┐  ┌────────────────────┐  │
│  │   MySQL 8.0    │  │   Redis 7.x     │  │   对象存储 (OSS)   │  │
│  │ 业务数据持久化  │  │ 会话/缓存/限流   │  │   用户上传的 PDF   │  │
│  └────────────────┘  └─────────────────┘  └────────────────────┘  │
└──────────────────────────────┬─────────────────────────────────────┘
                               │ REST / gRPC（内网）
                               ▼
┌────────────────────────────────────────────────────────────────────┐
│                    Python FastAPI AI 微服务                         │
│                                                                    │
│  ┌─────────────────┐  ┌──────────────────┐  ┌─────────────────┐   │
│  │ 对话推理接口     │  │ PDF 解析 & RAG    │  │ 管理接口         │   │
│  │ POST /chat       │  │ POST /ingest     │  │ GET /health     │   │
│  │ POST /chat/stream│  │ POST /query      │  │ GET /stats      │   │
│  └─────────────────┘  └──────────────────┘  └─────────────────┘   │
│                                                                    │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │             LangGraph Agent (现有代码核心复用)                 │  │
│  │  · chat_node (LLM推理)  →  · tool_node (6个工具执行)          │  │
│  │  · HITL interrupt (股票购买审批)                               │  │
│  │  · DeepSeek Chat API 调用                                      │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                                                                    │
│  ┌────────────────┐  ┌─────────────────┐  ┌────────────────────┐  │
│  │  FAISS 向量库   │  │ Embedding 模型   │  │   LangSmith        │  │
│  │  本地持久化     │  │ bge-small-zh     │  │   全链路追踪       │  │
│  └────────────────┘  └─────────────────┘  └────────────────────┘  │
└────────────────────────────────────────────────────────────────────┘
```

---

## 三、各层详细设计

### 3.1 表现层（前端）

#### 技术选型

| 候选 | 优点 | 缺点 | 建议 |
|------|------|------|------|
| **React + Vite** | 生态最大、组件丰富、SSE 成熟 | 学习曲线陡 | ✅ 推荐 |
| Vue + Vite | 中文社区好、上手快 | AI/Chat 组件少 | 可选 |
| 直接写 HTML/JS | 最简单 | 不适合复杂交互 | 不推荐 |

#### 核心页面

| 页面 | 功能 |
|------|------|
| 登录/注册 | JWT 登录 + OAuth2（微信/GitHub） |
| 对话主页 | Chat UI + 对话列表侧边栏 + PDF 上传按钮 |
| 对话详情 | 消息流、HITL 审批按钮、正在调用工具的状态提示 |
| 用户中心 | 个人信息、API 额度、消费记录 |

#### 关键技术点

- **SSE (Server-Sent Events)** 接收 AI 流式输出（Java → 前端透传 Python 的流式 chunks）
- **WebSocket** 保活 + 实时推送审批请求
- **Markdown 渲染**（AI 回复包含格式化文本）

---

### 3.2 Java 业务层

#### 技术栈

| 组件 | 选型 | 版本 |
|------|------|------|
| 框架 | Spring Boot | 3.4.x |
| JDK | Eclipse Temurin | 21 LTS |
| ORM | MyBatis-Plus | 3.5.x |
| 认证 | Spring Security + jjwt | - |
| 限流 | Bucket4j（内存版） | 8.x |
| 消息队列 | Spring Kafka | 3.3.x |
| 缓存 | Spring Data Redis | - |
| 构建 | Maven Wrapper | - |

#### 数据库设计（MySQL 核心表）

```sql
-- 用户表
CREATE TABLE users (
    id          BIGINT PRIMARY KEY AUTO_INCREMENT,
    username    VARCHAR(64) UNIQUE NOT NULL,
    password    VARCHAR(256) NOT NULL,     -- BCrypt 加密
    email       VARCHAR(128),
    avatar_url  VARCHAR(512),
    role        VARCHAR(16) DEFAULT 'USER', -- USER / ADMIN
    quota_total INT DEFAULT 100,           -- 每月对话额度
    quota_used  INT DEFAULT 0,
    created_at  DATETIME DEFAULT NOW(),
    updated_at  DATETIME DEFAULT NOW()
);

-- 对话会话表（对应 LangGraph thread_id）
CREATE TABLE conversations (
    id          BIGINT PRIMARY KEY AUTO_INCREMENT,
    thread_id   VARCHAR(64) UNIQUE NOT NULL, -- 对应 Python 侧 thread_id
    user_id     BIGINT NOT NULL,
    title       VARCHAR(128) DEFAULT '新对话',
    status      VARCHAR(16) DEFAULT 'ACTIVE', -- ACTIVE / ARCHIVED
    created_at  DATETIME DEFAULT NOW(),
    updated_at  DATETIME DEFAULT NOW(),
    INDEX idx_user (user_id)
);

-- AI 调用审计表（通过 Kafka 异步写入）
CREATE TABLE ai_audit_logs (
    id          BIGINT PRIMARY KEY AUTO_INCREMENT,
    user_id     BIGINT,
    thread_id   VARCHAR(64),
    model       VARCHAR(64),               -- deepseek-chat
    prompt_tokens  INT,
    completion_tokens INT,
    latency_ms     INT,
    cost_cents     DECIMAL(10,4),
    success_flag   TINYINT DEFAULT 1,
    created_at     DATETIME DEFAULT NOW(),
    INDEX idx_user_date (user_id, created_at)
);
```

#### 核心 API 设计

```
# 用户认证
POST   /api/v1/auth/register        # 注册
POST   /api/v1/auth/login            # 登录，返回 JWT

# 对话管理（需要 Bearer Token）
GET    /api/v1/conversations          # 获取对话列表
POST   /api/v1/conversations          # 创建新对话
DELETE /api/v1/conversations/{id}     # 删除对话
GET    /api/v1/conversations/{id}/messages  # 获取历史消息

# AI 对话代理（核心）
POST   /api/v1/chat                   # 同步对话
POST   /api/v1/chat/stream            # 流式对话（SSE）
POST   /api/v1/chat/resume            # HITL 审批恢复

# PDF 上传
POST   /api/v1/files/upload           # 上传 PDF，内部转发 Python 做 embedding
GET    /api/v1/files                  # 已上传的文件列表
DELETE /api/v1/files/{id}             # 删除文件及对应向量

# 用户管理
GET    /api/v1/user/quota             # 查询剩余额度
GET    /api/v1/user/usage             # 查询消费统计

# 管理后台（需要 ADMIN 角色）
GET    /api/v1/admin/users            # 用户列表
GET    /api/v1/admin/stats            # 运营数据看板
```

#### JWT 认证流程

```
1. 用户 POST /auth/login → 验证用户名密码
2. 返回 Access Token (15min) + Refresh Token (7d)
3. 前端每次请求带 Authorization: Bearer <access_token>
4. Token 过期 → POST /auth/refresh 用 Refresh Token 换取新 Access Token
5. 退出登录 → Redis 中 Token 加入黑名单
```

#### 限流策略

| 限流对象 | 策略 | 参数 |
|---------|------|------|
| 全局 API | Bucket4j Token Bucket | 100 req/s |
| 登录接口 | 按 IP | 5 次/分钟 |
| 对话接口 | 按用户 ID | 20 次/分钟 |
| PDF 上传 | 按用户 ID | 5 次/小时 |

#### AI 代理层（连接 Python 的关键）

```java
// 伪代码：流式对话代理
@PostMapping("/chat/stream")
public Flux<ServerSentEvent<String>> chatStream(
    @RequestBody ChatRequest request,
    @AuthenticationPrincipal UserDetails user
) {
    // 1. 检查剩余额度
    checkQuota(user.getId());

    // 2. 转发请求到 Python AI 服务
    return webClient.post()
        .uri("http://python-ai-service:8000/chat/stream")
        .bodyValue(request)
        .retrieve()
        .bodyToFlux(String.class)
        .map(chunk -> ServerSentEvent.builder(chunk).build())
        // 3. 异步记录审计日志到 Kafka
        .doOnComplete(() -> kafkaTemplate.send("ai-audit", auditEvent))
        .doOnError(e -> {
            // 降级：Python 挂了返回友好错误
            return "AI 服务暂时不可用，请稍后重试";
        });
}
```

---

### 3.3 Python AI 微服务层

#### 改造要点

| 现状 | 改为 |
|------|------|
| `app_hitl.py` (Streamlit UI) | ❌ 删除，前端被 React 替代 |
| `agentic_chatbot_hitl_backend.py` | 拆分为 FastAPI routes |
| `MemorySaver`（内存 checkpointer） | 保留，单进程就够了 |
| `chatbot.db`（SQLite） | 保留为 FAISS + checkpoints，不存用户数据 |
| print 日志 | 结构化日志（structlog / loguru） |

#### FastAPI 路由设计

```python
# ai_service/main.py
from fastapi import FastAPI
from routes import chat, ingest, health

app = FastAPI(title="Agentic Chatbot AI Service", version="2.0")
app.include_router(chat.router)      # /chat, /chat/stream, /chat/resume
app.include_router(ingest.router)    # /ingest (PDF), /query (RAG)
app.include_router(health.router)    # /health, /stats
```

#### 接口改动

原有 LangGraph 核心逻辑（`chat_node`、`tool_node`、`_clean_tool_calls`、6 个 Tool、FAISS 检索）**全部原封不动保留**。唯一改动是把 Streamlit 的 `chatbot.stream()` 调用包装成 FastAPI 的 SSE 端点：

```python
@router.post("/chat/stream")
async def chat_stream(request: ChatRequest):
    """流式对话 — SSE 输出"""
    config = {"configurable": {"thread_id": request.thread_id}}

    async def event_generator():
        for msg_chunk, metadata in chatbot.stream(
            {"messages": [HumanMessage(content=request.message)]},
            config=config,
            stream_mode="messages",
        ):
            if isinstance(msg_chunk, AIMessage):
                yield f"data: {json.dumps({'type': 'text', 'content': msg_chunk.content})}\n\n"
            elif isinstance(msg_chunk, ToolMessage):
                yield f"data: {json.dumps({'type': 'tool', 'name': getattr(msg_chunk, 'name', 'tool')})}\n\n"

        # HITL 检查
        pending = get_pending_interrupt(request.thread_id)
        if pending:
            yield f"data: {json.dumps({'type': 'hitl', 'prompt': str(pending.value)})}\n\n"

        yield "data: [DONE]\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
```

---

### 3.4 消息队列（Kafka）Topic 设计

| Topic | 生产者 | 消费者 | 用途 |
|-------|--------|--------|------|
| `ai-audit` | Java（对话代理层） | Java（审计消费者） | AI 调用日志异步落盘 |
| `pdf-ingest` | Java（文件上传） | Python（PDF 处理器） | PDF 异步解析 + Embedding |
| `user-event` | Java（各模块） | Java（分析消费者） | 用户行为埋点 |
| `notification` | Java（HITL 审批） | Java（推送消费者） | 审批通知推送 |

---

## 四、部署架构

### 4.1 容器清单

| 容器 | 基础镜像 | 内存需求 | CPU | 端口 | 副本数 |
|------|---------|---------|-----|------|--------|
| **Java 业务服务** | eclipse-temurin:21-jre-alpine | 512 MB - 1 GB | 1-2 核 | 8080 | 2（高可用） |
| **Python AI 服务** | python:3.11-slim（含 PyTorch + Embedding） | 2-4 GB | 2-4 核 | 8000 | 1-2 |
| **MySQL** | mysql:8.0 | 512 MB - 1 GB | 1 核 | 3306 | 1 |
| **Redis** | redis:7-alpine | 256 MB | 0.5 核 | 6379 | 1 |
| **Kafka** | bitnami/kafka:3.9 | 1-2 GB | 1-2 核 | 9092 | 1 |
| **Nginx (前端)** | nginx:alpine | 64 MB | 0.2 核 | 80/443 | 1 |

### 4.2 Sealos 费用预估

| 配置 | 容器数 | 总内存 | 总 CPU | Sealos 月费估算 |
|------|--------|--------|--------|----------------|
| **当前方案** | 1 | 2 GB | 2 核 | 免费层 (0 元) |
| **精简版架构** (无 Kafka/Redis) | 3 | ~4 GB | 4 核 | ~50-80 元/月 |
| **完整版架构** | 6 | ~7-9 GB | 7-10 核 | ~150-250 元/月 |

> 注：费用为 Sealos 公有云估算，实际按阶梯定价。自建 K8s 集群硬件成本另计。

### 4.3 Kubernetes 编排示意

```yaml
# 核心服务部署略图
apiVersion: apps/v1
kind: Deployment
metadata:
  name: java-business-service
spec:
  replicas: 2
  template:
    spec:
      containers:
        - name: java-app
          image: ghcr.io/xxx/agentic-chatbot-java:latest
          env:
            - name: AI_SERVICE_URL
              value: "http://python-ai-service:8000"
          resources:
            requests: { memory: "512Mi", cpu: "500m" }
            limits:   { memory: "1Gi",   cpu: "2000m" }
          livenessProbe:
            httpGet: { path: /actuator/health, port: 8080 }
---
apiVersion: v1
kind: Service
metadata:
  name: python-ai-service
spec:
  selector: { app: python-ai }
  ports: [{ port: 8000 }]
```

---

## 五、关键风险与应对

| 风险 | 影响 | 应对措施 |
|------|------|----------|
| Python AI 服务 OOM（日志已验证） | PDF 解析崩溃 | Java 侧设 90s 超时 + 重试 1 次；Python 侧分批 embedding + gc.collect() |
| Java ↔ Python 网络延迟 | 对话响应变慢 | 同 K8s 集群内网通信，延迟 <5ms；SSE 流式减少首字等待 |
| Kafka 消息堆积 | 审计日志丢失 | 审计 topic 设置 7 天保留，消费者使用批量写入 MySQL |
| DeepSeek API 限流 | 对话失败 | Java 代理层实现指数退避重试 (1s→2s→4s)，3 次后降级提示 |
| 多副本 Python 的 FAISS 不一致 | 用户 A 上传的 PDF 副本 B 搜不到 | 用 StatefulSet + PVC 绑定，或引入共享存储（MinIO/NFS） |
| JWT 密钥泄露 | 安全风险 | 密钥不硬编码，通过 K8s Secret 注入，定期轮换 |

---

## 六、实施路线图

| 阶段 | 内容 | 预计工时 | 产出 |
|------|------|---------|------|
| **Phase 1** | Python 侧：Streamlit 拆为 FastAPI，保留全部 AI 逻辑 | 1-2 天 | FastAPI 可独立调用的 AI 服务 |
| **Phase 2** | Java 侧：用户模块 + JWT 认证 + MySQL 建表 | 2-3 天 | 可注册登录的后端 |
| **Phase 3** | Java 侧：AI 代理层 + 对话 CRUD + 限流 | 1-2 天 | 对话功能可用的后端 |
| **Phase 4** | 前端：React Chat UI + 对话管理 + PDF 上传 | 2-3 天 | 可用的前端界面 |
| **Phase 5** | Kafka + Redis 接入 + 审计日志 + 计费模块 | 1-2 天 | 完整企业级功能 |
| **Phase 6** | 联调 + 测试 + Sealos 部署 + 文档 | 1 天 | 上线 |

**总计：8-13 天**（单人全职）

---

## 七、删减建议

如果时间或成本受限，按以下顺序砍：

| 优先级 | 砍掉的组件 | 影响 | 节省 |
|--------|-----------|------|------|
| 1 | **Kafka** | 审计日志改成同步写 MySQL（单次对话多耗时 ~5ms） | 1 GB 内存 + ~50 元/月 |
| 2 | **Redis** | 限流改用 Bucket4j 内存版（单 Pod 够用），JWT 黑名单用内存 | 256 MB 内存 + ~30 元/月 |
| 3 | **React 前端** | 暂时保留 Streamlit，只拆分 Java + Python 后端 | 无，但多用户隔离仍实现不了 |
| 4 | **MySQL** | 用户数据存 SQLite（回到单体模式） | 512 MB 内存 |

**最低可行版本**：Java（Spring Boot + 内存限流 + SQLite） + Python（FastAPI），3 个容器，~3 GB 内存，月费 50 元以内。
