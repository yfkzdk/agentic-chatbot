# 阶段 3：证据型鉴别诊断 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在红旗分诊允许的病例中生成带证据、可解释、可审计的三层鉴别诊断辅助结果。

**Architecture:** 发布后的知识库是唯一证据源；编排器仅能引用检索到的段落；安全校验器拒绝无引用、过期、超人群或与分诊结果冲突的输出。

**Tech Stack:** PostgreSQL、受控向量检索、LangGraph/LangChain、Pydantic structured output、pytest。

---

### Task 1：知识文档审核与发布

**Files:**
- Create: `api/routers/knowledge.py`
- Create: `backend/knowledge/service.py`
- Create: `backend/knowledge/release.py`
- Test: `tests/backend/test_knowledge_release.py`

- [ ] 写失败测试：未审核文档不能被检索；过期文档不能进入新发布版本；非知识管理员不能发布。
- [ ] 实现文档元数据：发布机构、来源类型、适用人群、发布日期、有效期、证据等级、审核人、原文定位和审核状态。
- [ ] 实现“提交→医学审核→管理员与医学审核人双确认→不可变发布版本”的状态机。
- [ ] Run: `pytest tests/backend/test_knowledge_release.py -v`。Expected: PASS。
- [ ] Commit: `feat: add reviewed knowledge release workflow`。

### Task 2：鉴别诊断编排与引用约束

**Files:**
- Create: `backend/differential/schema.py`
- Create: `backend/differential/service.py`
- Create: `api/routers/differential.py`
- Test: `tests/backend/test_differential_service.py`

- [ ] 写失败测试：P0 病例被拒绝；输出没有证据 ID 时被拒绝；所有候选必须属于 `must_exclude`、`common_possible` 或 `needs_more_information`。
- [ ] 定义结构化输出：候选疾病、层级、支持/反对特征、待补充信息、引用证据 ID、适用条件和不确定性说明。
- [ ] 将检索范围限制为所属机构、已发布版本、成人门诊、腹痛/消化不良/反酸；禁止通用联网搜索参与临床输出。
- [ ] Run: `pytest tests/backend/test_differential_service.py -v`。Expected: PASS。
- [ ] Commit: `feat: generate cited differential suggestions`。

### Task 3：临床安全校验与医生反馈

**Files:**
- Create: `backend/differential/safety.py`
- Create: `api/routers/feedback.py`
- Test: `tests/backend/test_differential_safety.py`

- [ ] 写失败测试：来源失效、适用人群不符、与 P1 红旗矛盾、关键特征缺失时输出固定降级结果。
- [ ] 校验每个主张的来源和发布版本；禁止处方、剂量、检查开立和确定性诊断语句。
- [ ] 实现采纳/部分采纳/不采纳反馈，并记录原因；反馈不得自动写入知识库或训练数据。
- [ ] Run: `pytest tests/backend/test_differential_safety.py -v`。Expected: PASS。
- [ ] Commit: `feat: enforce clinical safety and feedback audit`。
