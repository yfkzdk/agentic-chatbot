# 阶段 4：临床验证与影子运行 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在不影响实际临床决策的前提下验证安全性、临床价值和运行可靠性。

**Architecture:** 使用脱敏回顾性病例完成离线盲评；影子运行的输出只用于授权评估者复盘，不能显示给实际接诊医生或写入病历。

**Tech Stack:** 脱敏数据集、版本化评测集、指标仓库、BI 仪表盘、审计日志。

---

### Task 1：构建冻结评测集

**Files:**
- Create: `docs/evaluation/dataset-card.md`
- Create: `docs/evaluation/labeling-guide.md`
- Create: `tests/fixtures/clinical_eval/manifest.json`

- [ ] 从经批准的脱敏病例中抽样，按腹痛、消化不良/反酸、P0/P1、共病、少见病和信息不全分层。
- [ ] 两名独立消化科医生完成红旗、优先排除项、合理候选和关键缺失信息标注；第三名专家裁决分歧。
- [ ] 冻结病例、标签、知识库版本和模型版本；禁止用评测集调试后仍报告为独立测试。
- [ ] Commit: `docs: freeze clinical evaluation dataset protocol`。

### Task 2：自动化离线评测

**Files:**
- Create: `scripts/run_clinical_eval.py`
- Create: `backend/evaluation/metrics.py`
- Create: `docs/evaluation/acceptance-thresholds.md`
- Test: `tests/backend/test_evaluation_metrics.py`

- [ ] 写失败测试：指标脚本正确计算 P0 漏检数、P1 召回、无来源率和拒答正确率。
- [ ] 生成逐病例结果，包含规则版本、模型版本、提示词版本、知识发布版本、输出和引用。
- [ ] 将 P0 零漏检、P1 目标召回、100% 临床主张可追溯、零越权动作定义为发布门槛；阈值由阶段 0 治理组签署。
- [ ] Run: `pytest tests/backend/test_evaluation_metrics.py -v`。Expected: PASS。
- [ ] Commit: `feat: add reproducible clinical evaluation`。

### Task 3：影子运行与复盘

**Files:**
- Create: `backend/shadow/service.py`
- Create: `docs/evaluation/shadow-runbook.md`
- Create: `docs/evaluation/weekly-review-template.md`

- [ ] 将影子输出与实际流程隔离，仅供获授权评估者在事后查看。
- [ ] 每周复盘全部 P0/P1、随机抽样 P2、所有无引用/降级/超时事件；形成问题、所有者、截止时间和回归用例。
- [ ] 任一 P0 漏检立即暂停影子发布、执行事件流程、修复后重新跑完整评测集。
- [ ] Commit: `docs: add shadow operation and review process`。
