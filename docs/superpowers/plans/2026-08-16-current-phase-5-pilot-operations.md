# 阶段 5：可运营部署与部门试点

**目标：** 将已经通过离线验证的助手以小范围、可回滚、可度量的方式提供给一个部门。

## 文件计划

- Create: `tests/e2e/test_knowledge_assistant.py`。
- Create: `.github/workflows/test.yml`, `.github/workflows/security.yml`。
- Create: `deploy/docker-compose.production.yml`, `deploy/nginx.conf`, `deploy/backup-runbook.md`。
- Create: `docs/operations/pilot-runbook.md`, `docs/operations/incident-response.md`, `docs/operations/weekly-review.md`。
- Modify: `Dockerfile`, `.dockerignore`, `README.md`, `.github/workflows/deploy.yml`, `api/routers/health.py`。

## 执行清单

- [ ] 在 CI 中运行格式化、类型检查、单元/接口/端到端测试、依赖漏洞扫描、镜像扫描和数据库迁移检查；只在全部通过后构建镜像。
- [ ] 生产镜像只启动 Uvicorn/Gunicorn 的 FastAPI 服务；Streamlit 如保留，作为单独 UI 服务，通过反向代理访问 API；启用 TLS、XSRF/CSRF 防护和域名 allowlist。
- [ ] 建立监控面板：请求量、p95 延迟、模型/工具失败、成本、引用缺失、知识新鲜度、拒答率、跨权限异常和用户反馈。
- [ ] 配置告警与紧急停用开关：任何跨工作区事件、无引用率突增、认证异常、数据库不可用或预算超标时关闭场景和工具调用。
- [ ] 每日备份数据库和对象存储元数据；每月至少执行一次恢复演练并记录恢复时间和结果。
- [ ] 选择 5–15 名已培训用户，先运行两周只读试点；每周复盘错误引用、资料过期、泄密风险、反馈、延迟和成本。
- [ ] 连续两个评审周期达到阶段 0 的质量/安全阈值后，再扩大到同部门；跨部门需从阶段 0 新建场景卡。

**验收：** 试点用户只看到本部门资料；所有核心监控和告警有效；备份恢复演练成功；治理组书面批准扩大、维持、修复或停止。
