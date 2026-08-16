# 阶段 2：把全局 PDF RAG 改为企业知识库

**目标：** 将 `backend/rag.py` 的单个 `faiss_db` 替换为按工作区隔离、审核、版本化和可引用的知识服务。

## 当前代码与改造决策

`ingest_rag_document()` 现在将任意 PDF 覆盖写入固定 `faiss_db`，`get_retriever()` 又对所有人加载同一索引且启用危险反序列化。此阶段不再提供“上传后立即全局可问”的能力；文档必须经历提交、审核、发布三个状态。

## 文件计划

- Create: `backend/knowledge/models.py` — 文档、分块、发布版本、访问范围模型。
- Create: `backend/knowledge/service.py` — 上传、解析、审核、发布、撤销。
- Create: `backend/knowledge/retrieval.py` — 工作区和发布版本过滤的检索。
- Create: `api/routers/knowledge.py` — 文档管理与检索证据接口。
- Create: `api/schemas/knowledge.py`。
- Create: `tests/backend/test_knowledge_lifecycle.py`, `tests/backend/test_retrieval_isolation.py`。
- Modify: `backend/rag.py`, `backend/tools.py`, `api/routers/ingest.py`, `api/main.py`, `app_hitl.py`。

## 执行清单

- [ ] 写测试：未发布文档不能检索；过期文档不能进入新发布；A 工作区资料不会出现在 B 工作区结果中；撤销发布后立即不可检索。
- [ ] 将上传保存到受控对象存储，文件名换为随机 ID；限制大小、页数、MIME、PDF 文件头、解析时间和并发，并在隔离 worker 解析。
- [ ] 为每份知识记录来源、所有者、密级、范围、发布日期、复审日期、审核人、状态和原文定位；默认 `in_review`。
- [ ] 将向量数据按 `organization_id + knowledge_release_id` 分区；不要从用户可写位置反序列化 FAISS pickle。优先使用支持元数据过滤的托管/数据库向量检索，或只加载由服务端原子发布的可信索引。
- [ ] 引入发布版本：只有 `published` 文档进入一次不可变 release；旧版本标记 `superseded`，不静默覆盖。
- [ ] 让 RAG 工具返回结构化证据：文档标题、版本、段落、页码、来源链接、访问范围和内容片段。
- [ ] 删除 Streamlit 的直接 PDF 处理逻辑，改成“上传→审核状态→发布→可检索”的管理界面。

**验收：** 生命周期和隔离测试全通过；每次知识回答可显示来源和版本；恶意/超限 PDF 被拒绝且不会写入检索库。
