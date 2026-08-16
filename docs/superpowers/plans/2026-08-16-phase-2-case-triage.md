# 阶段 2：病例结构化与红旗分诊 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为成人消化科门诊建立可审阅病例输入和独立于模型的红旗分诊能力。

**Architecture:** 自由文本只能产生待确认字段；医生确认的 `ClinicalFeature` 才进入规则引擎。规则引擎优先于 LLM，P0 直接终止常规鉴别路径。

**Tech Stack:** FastAPI、Pydantic、SQLAlchemy、规则配置 YAML/数据库版本、pytest。

---

### Task 1：病例与特征接口

**Files:**
- Create: `api/schemas/cases.py`
- Create: `api/routers/cases.py`
- Create: `backend/cases/service.py`
- Test: `tests/api/test_cases.py`

- [ ] 写失败测试：未标记成年或门诊的病例返回 422；保存特征时缺少主诉或持续时间返回字段错误；版本冲突返回 409。
- [ ] 实现 `POST /cases` 和 `PUT /cases/{id}/features`，字段覆盖腹痛位置/性质/时长、反酸/烧心、呕吐、排便、体重变化、生命体征、既往史、用药、过敏史和已有检查。
- [ ] 每项特征带 `source=clinician|model_suggestion` 与 `confirmed_at`；未确认模型字段不得作为规则输入。
- [ ] Run: `pytest tests/api/test_cases.py -v`。Expected: PASS。
- [ ] Commit: `feat: add confirmed adult outpatient case capture`。

### Task 2：受控文本提取

**Files:**
- Create: `backend/extraction/service.py`
- Create: `api/routers/extraction.py`
- Test: `tests/backend/test_extraction.py`

- [ ] 写失败测试：提取服务永远不能覆盖已确认字段；输出只包含白名单字段和原文证据片段。
- [ ] 实现 `POST /cases/{id}/extract`，以结构化 JSON schema 请求模型；结果标记为 `model_suggestion`，且 API 不自动保存为确认值。
- [ ] 对身份证号、手机号、地址和姓名执行请求前脱敏；保留本地最小关联 ID。
- [ ] Run: `pytest tests/backend/test_extraction.py -v`。Expected: PASS。
- [ ] Commit: `feat: add clinician reviewed case extraction`。

### Task 3：红旗规则引擎

**Files:**
- Create: `backend/triage/rules/v1.yaml`
- Create: `backend/triage/engine.py`
- Create: `api/routers/triage.py`
- Test: `tests/backend/test_triage_engine.py`

- [ ] 写失败测试：呕血伴低血压命中 P0；进行性吞咽困难命中 P1；无红旗的反酸病例为 P2；P0 不允许调用鉴别接口。
- [ ] 将每条规则配置为规则 ID、版本、触发字段、风险等级、固定处置文案和复审日期；运行结果保存为不可变 `RedFlagAssessment`。
- [ ] 实现 `POST /cases/{id}/triage` 和鉴别接口前置检查。
- [ ] Run: `pytest tests/backend/test_triage_engine.py -v`。Expected: PASS。
- [ ] Commit: `feat: add versioned gastroenterology red flag triage`。
