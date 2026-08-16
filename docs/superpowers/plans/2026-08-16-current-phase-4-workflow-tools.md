# 阶段 4：从知识助手升级到受控流程助手

**目标：** 在业务已经验证价值后，将演示工具体系替换为部门流程工具；先生成草稿，后创建待审批对象，最后才考虑写操作。

## 当前代码与改造决策

当前 `backend/tools.py` 直接暴露联网、股票和模拟购买工具，`human_approval` 只按线程 ID 接收 yes/no。企业版本必须采用“工具注册表 + 参数 schema + 权限 + 审批记录 + 幂等键 + 回滚策略”。不能仅复用现有股票审批逻辑。

## 文件计划

- Create: `backend/tools/registry.py` — 工具声明、风险级别、场景白名单。
- Create: `backend/tools/contracts.py` — 输入/输出 schema、幂等键、审批 token。
- Create: `backend/approvals/service.py`, `api/routers/approvals.py`。
- Create: `backend/integrations/<first-system>.py` — 第一个部门系统的只读或草稿适配器。
- Create: `tests/backend/test_tool_authorization.py`, `tests/backend/test_approval_lifecycle.py`。
- Modify: `backend/tools.py`, `backend/graph.py`, `api/routers/chat.py`, `app_hitl.py`。

## 执行清单

- [ ] 为每个候选工具建立动作卡：业务目的、影响对象、读/写级别、输入 schema、权限、审批人、超时、重试、幂等键、回滚和告警。
- [ ] 首先实现 L0 只读工具或 L1 草稿工具，例如从授权 Wiki/工单系统读取资料，或生成但不发送工单草稿。
- [ ] 为 L2 创建待审批对象实现审批记录：请求人、审批人、原始参数哈希、有效期、状态和决定；恢复操作必须绑定审批记录与用户/工作区，不接受裸 `thread_id`。
- [ ] 禁止 L3/L4 写入/外发工具进入首发版本；如未来启用，必须在模拟环境完成重复提交、超时、拒绝、过期、回滚和审计专项测试。
- [ ] 记录工具名称、版本、参数摘要、权限决策、审批和结果；敏感参数加密或只保留哈希。

**验收：** 未授权用户、审批过期、参数被篡改和重复请求均不能执行；影子模式下工具结果不改变真实业务系统；所有调用可追溯。
