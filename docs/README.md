# 项目文档

规范版本：1.0。状态：Proposed，待团队评审。需求状态与批准记录以[D1需求登记](req/requirements.yaml)和[PR评审记录](review-memo.md)为准。

FR-03 已有实测模块候选与[完整交接入口](fr03.md)，验证版本与范围见[脱敏证据](fr03-evidence.json)。这不替代规格批准或其他模块的状态。

## 项目范围

TradingAgents Pro基于TradingAgents单股分析流程，增加以下能力：

| 编号 | 目标 | 规范 |
|---|---|---|
| FR-01 | 证据可追溯与确定性发布检查 | C1 |
| FR-02 | 指定财务指标复算与核验记录 | C2 |
| FR-03 | 情绪来源覆盖与缺测状态 | C3 |
| NFR-01 | 单轮实际模型请求预算 | C4 |
| NFR-02 | 指定调用点的消息大小控制 | C5 |

INV-01约束正式决策发布与记忆写入，INV-02约束请求上限。系统边界、验收条件和共享接口见下列文档。

## 文档索引

| 交付物 | 文件 |
|---|---|
| D1 需求 | [产品范围](req/product.yaml)、[需求登记](req/requirements.yaml)、[校验Schema](req/req-schema.json) |
| D2 架构 | [蓝图](../architecture-blueprint.md)、[ADR-001](architecture/adr/001-choice-tbd.md)、[共享接口C0–C5](architecture/interface-contracts.md)、[不变量](architecture/invariants.md)、[追踪矩阵](architecture/trace-matrix.md)、[状态设计](architecture/memory-design.md)、[权限模型](architecture/permission-model.md)、[运行策略](architecture/runtime-policy-catalog.md)、[候选方案比较](architecture/evaluation-table.md) |
| D3 开发治理 | [入口AGENTS](../AGENTS.md)、[结构约束](code-governance/structural-constraints.md)、[工具清单](code-governance/mcp-tool-manifest.md)、[权限配置](../.opencode/opencode.jsonc)、[课程权限副本](../.opencode/permissions.jsonc)、[常驻规则](../.opencode/rules.md)、[项目公约](../.agent/rules.md) |
| D4 验证治理 | [验证约束](code-governance/verification-constraints.md)、[PR评审](review-memo.md)、[技术债](debt-register.md)、[Bug记录](bug-diary.md)、[在线验收：五家公司 CLI 复跑](live-acceptance.md#five-company-cli-rerun-on-19-november-2026) |
| D5 会话记录 | 交付包中的`transcripts/`，保留真实会话及人工干预说明 |
| D6 过程报告 | 交付包中的`Report.md` |
| D7 仓库与CI | [项目README](../README.md)、[工作流](../.github/workflows/ci.yml)、分支保护设置 |
| D8 源码与测试 | `tradingagents/`、`cli/`、`tests/`；新增课程测试为`test/offline/`与`test/live/` |
| D9 启动说明 | [Prompt.md](../Prompt.md) |

## 开发与评审

1. 确认共同起点SHA和接口版本，阅读D1、D2及相关治理规则。
2. 每项需求使用独立分支；执行计划、测试设计和精确文件范围经真人批准后进入实现。
3. 按D4执行离线验证、回归和适用的在线检查，提交代码、结果及评审记录。
4. 统筹整合共享文件，执行集成回归后合并。需求、接口或验收条件变更时同步更新相关制品。

OpenCode使用Plan、Build、Verify角色；权限检查和执行边界见[权限模型](architecture/permission-model.md)。运行配置见[接口规范](architecture/interface-contracts.md#working-defaults-and-limits-with-different-purposes)。

需求负责人维护本项代码、测试、真实过程记录和报告素材。公共状态、Schema、模型调用与报告适配由统筹人LIU Huansong整合。跨模块接口变更须由受影响负责人评审。

## 记录与交付

AI使用情况记录在[AI-use日志](ai-use-log.yaml)，问题与待办记录在[评审记录](review-memo.md)、[技术债](debt-register.md)和[Bug记录](bug-diary.md)。测试结果须关联版本、输入、配置及实际输出。凭据、学号和原始会话不进入公开仓库。

应用开发保留上游包结构；最终交付包按课程`src/`、`test/`要求核对源码和测试映射。报告、视频和集成结果使用同一最终版本。

## FR-03 implemented module handoff

[FR-03 feature, report section and reproduction](fr03.md) is the current module entry; [sanitized evidence](fr03-evidence.json) contains recorded versions/results. FR-03 has a passing module candidate in [PR #6](https://github.com/EverForests/TradingAgents_Pro/pull/6); other requirements and formal specification approvals keep their recorded status. Private D5 exports and reflection material are assembled separately for the course submission, not committed here. The root Report.md and other members' transcripts remain the team's responsibility.
