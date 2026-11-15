# CS5351 deliverable map

This branch provides D1–D4 requirements, architecture and governance, and the shared D9 launch prompt. D4 defines verification and evidence recording; planned cases and reported observations are not test results. D5–D8 course artifacts remain scaffolded unless separately implemented. Wiring the schema and verification checks into required CI gates is part of D7. Load the OpenCode policy explicitly as documented in the permission model and verify its effective permissions before use.

| Deliverable | Planned location |
| --- | --- |
| D1 — Requirements | `docs/req/product.yaml`, `docs/req/requirements.yaml`, `docs/req/req-schema.json` |
| D2 — Architecture | `architecture-blueprint.md`, `docs/architecture/` (including ADRs, invariants, trace matrix, memory, permissions, evaluation and runtime policies) |
| D3 — Coding governance | `AGENTS.md`, `docs/code-governance/`, `.opencode/`, `.agent/` |
| D4 — Verification governance | `docs/code-governance/verification-constraints.md`, `docs/review-memo.md`, `docs/debt-register.md`, `docs/bug-diary.md` |
| D5 — Session evidence | `transcripts/` in the course submission; keep raw sessions out of the public repository |
| D6 — Process report | `Report.md` in the course submission; keep student identifiers out of the public repository |
| D7 — Repository and gates | `README.md`, `.github/workflows/ci.yml`, and branch protection settings |
| D8 — Source and tests | Existing implementation: `tradingagents/` and `cli/`; existing tests: `tests/`. Course submission paths: `src/` and `test/`, with new course tests split into `test/offline/` and `test/live/`. |
| D9 — Static launch prompt | `Prompt.md` at the repository root; versioned runtime prompts belong in `prompts/`. |

Maintain the project AI-use log at `docs/ai-use-log.yaml` without credentials or personal information. Verify the source and test layout when assembling the submission ZIP. The scaffold does not move upstream modules, change test discovery, or add blocking checks.

## 开发前状态与使用顺序（首版提案，待全组评审）

本次是 D1–D4、D9 的准备修订，不是功能 Demo，不代表测试已获批准。飞书各人的早期 FR 编号不是全局编号（例如早期 FR-03 曾指发布闸门）；开发统一使用 P4–6 整合推荐和本仓库 D1 的编号。最终 FR-03 是情绪缺测，原提案编号 REQ-TA-FR-002。五项范围不变：FR-01 发布证据、FR-02 数值复算、FR-03 情绪缺测、NFR-01 请求预算、NFR-02 消息大小。

先读 `docs/req/product.yaml` 和需求登记，再读 [共享接口 C0–C5](architecture/interface-contracts.md)、蓝图、ADR 和验证约束。共同约定要先评审，个人计划及测试再批准；不能用最后的 PR 批准替代实现前批准。

### 已读材料与证据边界

| 来源 | 已确认内容 | 尚不能推出的结论 |
| --- | --- | --- |
| 教师 Project Requirement Sheet，P5–10 | D1–D9、8 项必需架构制品、6 类阻断门禁、人工监督和真实记录 | 有目录或上游 CI 不代表已完成课程门禁 |
| Introduction S20、23、25 | TradingAgents/同等复杂度基线，OpenCode、前后效果比较、软件工程原创思路 | 新业务功能本身不等于软件工程原创；Codex 可替代 OpenCode 尚无教师确认 |
| 飞书导出 PDF，10 页，SHA256 `0cb42c41c3610c8c5e55e8438d98f400f2cdd183cff0569925f5eeb8778ddfbdf` | P4–6 为最终五项整合；P6–10 为协作手册；P1 为分支表和目录截图 | 较早的个人候选不自动入选；“默认都批准”不能作为审批记录；截图有右侧截断 |
| 队友 AAPL sentiment.md，SHA256 `d425e9f0eb2b4c076b555e5f0ba95f48d7714a4684a036bae2c0f55b86c54450` | 标题 Neutral/5.0，正文说明 Yahoo 异常、StockTwits 窗口不支持、Reddit 获取失败 | 不证明现实中没有新闻；不是本次独立在线复现 |
| 队友五股运行汇总，SHA256 `56f72230defd62aaa56c7b93631167b51ab55b5701cd82973593e2878df2dedc` | 记录 18–21 次 LLM 调用及标题现象；调用统计为队友报告 | 没有原始请求轨迹、环境和全部报告，不作为独立核验的调用总数 |

原件及原始会话保留在个人/课程交付材料中；公开仓库只保留必要出处与脱敏结论。已补核新 B3.1 ZIP（186 项，SHA256 `fe1211a3ebaeff9c15380b07e3aa920987d5aa0d6c0eb305ca3df9fd4d6b46e5`）：CRC/安全路径通过，静态确认 10 个 CI jobs、9 个 hooks 和 docs4/agents 四个角色说明；只读检查相关资料，未执行教师代码。SA PDF/PPT 已定位于 Canvas Files 根目录，页面显示最后修改为 2026-09-28；实际 PDF 第65页为 Evaluation Logbook，未确认公告所说的新页上线。VHIS 是教学参考，不是本项目的新基线，也没有因为该邮件自动增加 50 个门禁或 460 个测试的数量要求。

### 开发前必须关闭的事项

| 编号 | 需要确定/完成的内容 | 建议责任 | 当前状态 |
| --- | --- | --- | --- |
| R1 | 全组确认共同起始 SHA、Python 小版本、OpenCode 2.3.0 和依赖版本快照 | 统筹人，各成员核对 | 待团队确认；本机曾用 Python 3.11.2，不将会议转写的 3.11.3.1 当安装依据 |
| R2 | 评审 C0–C5 语义、具体函数/字段和共享文件整合责任人 | 五项负责人、统筹人 | 本 PR 提案，未批准 |
| R3 | FR-02 原始操作数、来源、期间、单位和预期值 | FR-02 负责人 | 待原始样本；不编造公司数据 |
| R4 | FR-03 来源有效性适配、时间边界、部分覆盖与评分失败规则 | FR-03 负责人，FR-01 消费方 | C3 提案，待测试和签名确认 |
| R5 | NFR-01 支持的传输路径/重试设置；NFR-02 两个调用点和规范序列化 | 两项负责人 | C4/C5 提案，待具体接入检查 |
| R6 | OpenCode 实际权限探测；补齐精确读取/测试样本路径 | 人工治理维护人 | 配置静态审查不等于真实生效；见 permission-model |
| R7 | 每人计划与测试的事前批准，且关联精确版本 | 各负责人、交叉审查人 | 未发生，不自动批准 |
| R8 | 新课程测试的收集、D1 schema/语义校验及教师六类门禁接入 | CI 负责人 | D7 待实现；上游 pytest 默认只收集 tests/ |
| R9 | 当前学校模型的小规模在线链路、结构化/回退兼容性和数据源结果 | 复现负责人 | 短 API 探针已通；独立离线 FR-03 探针 11 项通过、外部请求0；真实情绪诊断/整次股票分析待运行，凭据仅私密输入 |
| R10 | 5 项数量口径、OpenCode 替代政策、转录份数及报告分页歧义 | 组长向教师/TA 核实 | 未取得澄清，不擅自改写教师要求 |

R1–R7 是各相关功能进入 Build 前的检查项；R8 的相关门禁必须在功能合并前接入并验证。R9 可与只读规划并行；若真实接入失败，先区分供应商问题与实现缺陷，不把在线不可用写成离线验收失败或提升。先冻结可审查首版，后续按实际证据修订，不要求一次猜完所有实现细节。

### 五人使用 Codex 与课程流程

各人可以用自己的 Codex 理解材料、审查设计和组织工作。本修订由 Codex 协助准备，不能冒称 OpenCode 会话。Introduction S20 明确提到 OpenCode；未获得替代工具澄清前，课程应用实现仍按仓库 OpenCode 流程准备。`.opencode` 配置不会自动限制 Codex。不要借其他助手绕过课程代理被拒绝的操作、替学生批准或伪造原始记录。

每个功能负责人准备自己的计划、测试、代码、会话、结果及报告素材；另一成员交叉审查。公共文档统一维护，但负责人核实其条目。Issue 可选，审批记录不可省。既有分支不用重建；先保护在做的工作，再同步经评审的公共基线。

本修订建议以独立文档 PR 指向 `feat/course-deliverables`，使差异只含补充内容；组内评审后由统筹人合入该分支，再将整体文档基线 PR 合入 main。若决定直接建立新的公共基线，可另经讨论调整目标，不自动合并、重置或删除旧分支。


### 新 B3.1 对本项目的适用启示

示例将 Plan、Tester、Build、Verify 分开；用途是独立约束与验证，不是要求所有小组机械复制四个角色。当前小组三角色流程仍需真人事前审查测试，Build 不得自行改变验收；另一成员的 Codex 审查只能提供建议。示例也坦白区分权限意图和实际可执行的保护；因此本组配置静态正确不能写成所有访问已被拦截。运行策略应写清触发、行动、证据、继续/拒绝/降级决定及升级处理。不要整包复制 VHIS 工作流：其 B1/B3/B3.1 路径与本仓库不同，且部分 live job 会在未配置凭据时跳过。
