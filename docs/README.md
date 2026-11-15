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
| 飞书导出 PDF，10 页，SHA256 `0cb42c41c3610c8c5e55e8438d98f400f2cdd183cff0569925f5eeb8778ddfbd` | P4–6 为最终五项整合；P6–10 为协作手册；P1 为分支表和目录截图 | 较早的个人候选不自动入选；“默认都批准”不能作为审批记录；截图有右侧截断 |
| 队友 AAPL sentiment.md，SHA256 `d425e9f0eb2b4c076b555e5f0ba95f48d7714a4684a036bae2c0f55b86c54450` | 标题 Neutral/5.0，正文说明 Yahoo 异常、StockTwits 窗口不支持、Reddit 获取失败 | 不证明现实中没有新闻；不是本次独立在线复现 |
| 队友五股运行汇总，SHA256 `56f72230defd62aaa56c7b93631167b51ab55b5701cd82973593e2878df2dedc` | 记录 18–21 次 LLM 调用及标题现象；调用统计为队友报告 | 没有原始请求轨迹、环境和全部报告，不作为独立核验的调用总数 |

原件及原始会话保留在个人/课程交付材料中；公开仓库只保留必要出处与脱敏结论。已补核新 B3.1 ZIP（186 项，SHA256 `fe1211a3ebaeff9c15380b07e3aa920987d5aa0d6c0eb305ca3df9fd4d6b46e5`）：CRC/安全路径通过，静态确认 10 个 CI jobs、9 个 hooks 和 docs4/agents 四个角色说明；只读检查相关资料，未执行教师代码。SA PDF/PPT 已定位于 Canvas Files 根目录，页面显示最后修改为 2026-09-28；实际 PDF 第65页为 Evaluation Logbook，未确认公告所说的新页上线。VHIS 是教学参考，不是本项目的新基线，也没有因为该邮件自动增加 50 个门禁或 460 个测试的数量要求。

### v1 已选定的工作约定

本 PR 已选择一版具体接口，见 [v1 字段和调用边界](architecture/interface-contracts.md#v1-shared-record-layout)。确认这些共同约定后即可按任务推进；尚未实现不等于还要重新讨论设计。公共接口按 JSON-compatible mappings 交换，内部类型可适配，沿用现有模块和 AgentState，不新建五个网络服务。

| 事项 | 首版约定 | 允许后续调整的条件 |
| --- | --- | --- |
| 源码与环境 | 官方9fa1196；沿用已验证Python3.11环境，记录小版本/依赖 | 统筹公布共同起点SHA；仅真实兼容差异触发环境变更，不因会议转写重装 |
| 共享接口 | C0–C5字段、结果状态和函数边界固定为1.0 | 接入发现冲突时，说明影响并同步合同与测试 |
| 正式输出 | 同一PublicationResult控制CLI/API/报告/记忆；拒绝时rating=null | 安全语义变更需ADR和真实人工审查 |
| 情绪来源 | news/stocktwits/reddit三源；原版日期窗口；0/3直接UNKNOWN/null并跳过情绪模型 | 新来源或来源有效规则变更需明确扩scope；下游不能自行填0/5 |
| 请求预算 | 成品课程profile先建议40次，边界测试3次；隐式重试0，回退另计 | 完整基线表明不足时调整配置，不把某次复现16/20次护栏变成产品要求 |
| 上下文限制 | 两个指定调用点，规范JSON消息计量；拟用65536字节 | 依据真实必需块大小调整配置与测试；不作用于所有原版请求 |
| 分支与整合 | 每项独立分支，现有分支可继续；沿用会议安排由LIU Huansong统筹 | 组内另有安排或冲突时调整；公共文件用小patch整合 |
| 记录与交付 | 各人保留真实会话/结果和报告素材，交叉审查 | 不预填贡献、批准或成绩；公共报告在集成后汇总 |

模型profile和4096输出上限是有记录的初始配置，不是课程硬阈值。16384输入token/80%压缩点仍是未启用设计候选；可靠计量与容量未核验前不宣称token守卫生效。16/20次复现上限仅为独立诊断保护，不能证明NFR-01已经实现，也不能当作正常产品预算。

### 按阶段处理的准备清单

| 时间点 | 具体事项 | 当前处理方式 |
| --- | --- | --- |
| 本项写代码前 | 使用共同基线与v1合同，列确切文件/适配点；批准该项计划与独立测试；验证所用角色权限 | 各负责人按任务处理，不要求等其他四项材料全部齐全 |
| FR-02真实案例验收前 | 补原始操作数、期间、单位和来源 | FR-02负责人补证据；可先做合成公式测试，不阻断FR-03 |
| 本项合并前 | 课程离线测试确实收集，相关schema/语义、安全、回归、AI-use与审批门禁接入；有真人PR评审 | CI负责人/统筹安排；当前上游CI绿不等于六类门禁已全实现 |
| 真实效果比较前 | 固定模型/思考/数据/运行配置，取得完整基线与改进结果 | 复现并行推进；截断、预算耗尽、连接失败分别记录 |
| 最终交付前 | 联合集成回执、报告/反思/贡献、五人真实会话、视频、README、完整源码测试和打包路径 | 用最终同一SHA组装，不能把各人PR结果当集成版结果 |

权限配置的精确路径补充及真实探测仍由人工治理维护人完成，见 permission-model。若本项确有缺读/写路径，只暂停该项越界操作；不扩大为任意代理访问。完整在线基线是效果比较前置，不是所有独立离线模块开始设计的前置。

### 需要组内实质确认的少数事项

1. **是否接受接口v1.0**：特别是UNKNOWN/null、统一正式输出、上下文先于预算、共享字段与当前在做的实现是否冲突。内部实现细节无需全组逐项开会。
2. **公共改动怎样整合**：按会议安排由LIU Huansong统筹，各人提交小patch和PR；每项实际计划/测试仍要有明确真人审查，不把确认公共文档等同批准所有功能代码。
3. **只有坚持完全替换课程工具时才需澄清替代政策**：本版默认Codex辅助理解/规划/审查，OpenCode保留规定实现过程。Introduction的N项数量口径仍未获教师澄清；继续当前五项，组长方便时集中核实，不擅自扩成十项或宣布教师已批准。

其余如环境版本记录、每项fixture、CI接入和报告排版是责任人的执行事项；按上表时间点补齐即可。会话先按五人各保留完整记录准备，最终报告同时检查字数与排版要求，不为每个旧文字歧义暂停开发。FR-02原始证据和真实实验结果不能由AI编造，但也不必全组开会才能收集。

### 五人使用 Codex 与课程流程

各人可以用自己的 Codex 理解材料、审查设计和组织工作。本修订由 Codex 协助准备，不能冒称 OpenCode 会话。Introduction S20 明确提到 OpenCode；未获得替代工具澄清前，课程应用实现仍按仓库 OpenCode 流程准备。`.opencode` 配置不会自动限制 Codex。不要借其他助手绕过课程代理被拒绝的操作、替学生批准或伪造原始记录。

每个功能负责人准备自己的计划、测试、代码、会话、结果及报告素材；另一成员交叉审查。公共文档统一维护，但负责人核实其条目。Issue 可选，审批记录不可省。既有分支不用重建；先保护在做的工作，再同步经评审的公共基线。

本修订建议以独立文档 PR 指向 `feat/course-deliverables`，使差异只含补充内容；组内评审后由统筹人合入该分支，再将整体文档基线 PR 合入 main。若决定直接建立新的公共基线，可另经讨论调整目标，不自动合并、重置或删除旧分支。


### 新 B3.1 对本项目的适用启示

示例将 Plan、Tester、Build、Verify 分开；用途是独立约束与验证，不是要求所有小组机械复制四个角色。当前小组三角色流程仍需真人事前审查测试，Build 不得自行改变验收；另一成员的 Codex 审查只能提供建议。示例也坦白区分权限意图和实际可执行的保护；因此本组配置静态正确不能写成所有访问已被拦截。运行策略应写清触发、行动、证据、继续/拒绝/降级决定及升级处理。不要整包复制 VHIS 工作流：其 B1/B3/B3.1 路径与本仓库不同，且部分 live job 会在未配置凭据时跳过。

### 独立真实情绪诊断补充

AAPL、2026-11-10 的真实原版情绪节点诊断已成功：三个来源不可用时仍输出 Neutral/5.0/Low。报告 SHA256 `29ec0f5dbd5dffd055edf2c76850ed1d012f4eee065b65ba0b5b4d958123ca60`。本次显式增加了160英文词的简短叙述要求，属于受控诊断；不能当作与队友设置完全一致的完整基线。独立 market-only 单股图流程现已完成（AAPL、2026-11-10，官方9fa1196，252行真实Yahoo行情，讨论各1轮）；基本面/新闻/情绪分析角色未纳入该主流程，不能当作所有角色基线。请求thinking disabled、单次输出4096；最后两次外围SSE接收并聚合，官方源码未改。累计保守尝试20次含16次HTTP200和4次用量未知连接异常，不等于20次已计费调用；已停止发送。完成状态JSON SHA256 `5235c0b8780e60c2ae3314af48f317db9dd0c0f9deb9d59e929108b4d9c42ade`。这只是复现证据，不是本组NFR-01/02已实现。
