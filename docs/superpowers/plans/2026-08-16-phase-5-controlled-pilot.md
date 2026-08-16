# 阶段 5：受控临床试点 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在单机构、少量受训消化科医生中进行可随时停止的真实工作流试点。

**Architecture:** 试点开关按机构、科室、用户和知识发布版本控制；系统只提供辅助页面，不写回 EMR，所有高风险事件进入治理组复盘。

**Tech Stack:** Feature flag、RBAC、OpenTelemetry、监控告警、审计报表。

---

### Task 1：试点准入与培训

**Files:**
- Create: `docs/pilot/site-readiness-checklist.md`
- Create: `docs/pilot/clinician-training.md`
- Create: `docs/pilot/user-acknowledgement.md`

- [ ] 仅允许阶段 0 指定机构、消化科和完成培训的医生使用。
- [ ] 培训必须覆盖适应范围、红旗提醒、证据阅读、降级行为、不得替代临床判断、事件上报和停用流程。
- [ ] 医生在首次使用前确认知悉系统仅为辅助工具且不得用于范围外患者。
- [ ] Commit: `docs: add pilot readiness and clinician training`。

### Task 2：试点开关、监控与告警

**Files:**
- Create: `backend/pilot/feature_flags.py`
- Create: `backend/pilot/metrics.py`
- Create: `docs/pilot/alert-runbook.md`
- Test: `tests/backend/test_feature_flags.py`

- [ ] 写失败测试：未受训用户、非试点机构、非消化科角色和旧知识库版本都不能启用鉴别诊断接口。
- [ ] 监控调用量、延迟、失败率、P0/P1 命中、降级率、无引用率、医生采纳/改写率和安全事件。
- [ ] 配置告警：P0 漏检、任意跨机构访问、无引用输出、错误率或响应时延超过治理组阈值时立即通知值班负责人并自动关闭试点开关。
- [ ] Run: `pytest tests/backend/test_feature_flags.py -v`。Expected: PASS。
- [ ] Commit: `feat: add controlled pilot guardrails`。

### Task 3：周度治理与扩大决策

**Files:**
- Create: `docs/pilot/weekly-governance-template.md`
- Create: `docs/pilot/exit-decision-template.md`

- [ ] 每周审阅性能指标、所有 P0/P1、医生反馈、知识库更新和未关闭事件。
- [ ] 高风险事件必须按阶段 0 事件响应流程完成停用、根因分析、修复、回归和再批准。
- [ ] 试点结束时由治理组选择“扩大、维持、修复后重试或停止”；不得仅依据使用量或采纳率扩大范围。
- [ ] Commit: `docs: define pilot governance and exit decision`。
