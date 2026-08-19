# 阶段 0：临床与治理立项 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在任何临床功能开发前冻结首期适应范围、风险边界、知识治理和试点评测规则。

**Architecture:** 建立由消化科负责人主导的临床治理组；所有高风险规则和知识发布均经过临床审批并留存版本记录。

**Tech Stack:** Markdown 文档、机构文档库、审批工单系统。

---

### Task 1：成立治理组并冻结适应范围

**Files:**
- Create: `docs/clinical-governance/charter.md`
- Create: `docs/clinical-governance/intended-use.md`

- [ ] 定义角色：消化科负责人（临床所有者）、急诊/护理代表（分流复核）、医学信息（工作流）、信息安全（数据）、法务/合规（合规）、产品负责人（发布）。
- [ ] 在 `intended-use.md` 写明“成人消化科门诊，腹痛、消化不良和反酸的医生端鉴别诊断辅助”；写明禁止自动诊断、处方、检查开立、病历写回和患者端诊疗。
- [ ] 由全部角色签字或在审批系统中确认版本 `1.0.0`。
- [ ] Commit: `docs: define clinical governance and intended use`。

### Task 2：定义红旗与降级策略

**Files:**
- Create: `docs/clinical-governance/red-flag-policy.md`
- Create: `docs/clinical-governance/out-of-scope-policy.md`

- [ ] 按 P0/P1/P2/P3 编制红旗表，包含触发条件、优先级、医生界面文案、推荐升级路径、规则所有者和复审日期。
- [ ] P0 明确包含消化道大出血、休克征象、急腹症高度可疑和意识异常；P0 行为必须是停止常规鉴别输出。
- [ ] 写明儿童、孕产妇、术后、非消化科主诉、关键字段缺失和证据不足的固定降级文本。
- [ ] 消化科负责人和急诊代表双人复核后发布 `1.0.0`。
- [ ] Commit: `docs: approve gastroenterology red flag policy`。

### Task 3：制定知识与数据治理

**Files:**
- Create: `docs/clinical-governance/knowledge-admission-policy.md`
- Create: `docs/clinical-governance/data-protection-policy.md`
- Create: `docs/clinical-governance/incident-response.md`

- [ ] 规定可准入来源、元数据、医学编辑切分、消化科审核、失效和紧急下架流程。
- [ ] 规定最小化采集、匿名病例 ID、独立加密身份映射、保存期限、访问审计与不将病例直接用于训练的规则。
- [ ] 定义安全事件分级、P0/P1 临床风险事件上报时限、停用权限、复盘和恢复发布要求。
- [ ] Commit: `docs: add knowledge data and incident governance`。

### Task 4：冻结验证方案

**Files:**
- Create: `docs/clinical-governance/clinical-evaluation-protocol.md`

- [ ] 定义脱敏回顾性病例集的纳入/排除标准、双盲专家评审方式、分歧裁决、P0 零漏检和 P1 目标召回阈值。
- [ ] 定义必须测量的指标：红旗召回、候选覆盖、引用正确性、无证据输出、医生改写率、响应时间和越权访问。
- [ ] 治理组批准后锁定版本；后续修改必须产生新版本和变更原因。
- [ ] Commit: `docs: approve clinical evaluation protocol`。
