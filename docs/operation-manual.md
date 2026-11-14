# CS5351 小组操作手册（OpenCode 2.3.0）

每人认领一条需求，从同一文档基线开分支。流程是：只读计划 → 队友批准计划和测试 → 先写并运行测试 → 实现 → 核验 → 功能 PR。分工可在线下完成，不要求另开 Issue。

## 1. 对齐分支与共享接口

先把 `feat/course-deliverables` 提 PR 到小组仓库的 `main`，请队友核对需求、架构和权限。合并后，从更新后的 `main` 分别开功能分支：

```bash
git fetch origin
git switch -c feat/fr-01-publication-gate origin/main
git rev-parse HEAD
```

记下起始 SHA。已有分支的组员不必重开；先保存进行中的工作，再同步已审查的基线，复核权限和 diff。文档未合并时可先只读规划；从文档分支提前开的功能 PR 先以文档分支为 base，文档合并后再切回 `main` 并检查差异。若文档 PR 是 squash merge，先确认功能分支只带自己的变更。

提前约定最终建议发布入口和模型请求入口。NFR-01 与 NFR-02 共用的顺序是：检查或缩减消息 → 确认可发送 → 扣一次调用额度 → 发送。

## 2. 核对配置，用 course-plan 出只读计划

从仓库根目录运行：

```bash
opencode --version
opencode debug config
opencode debug agents
opencode mcp list
opencode plugin list
```

版本应为 `2.3.0`（[官方下载](https://github.com/anomalyco/opencode/releases/tag/v2.3.0#assets)）。确认加载的是 `.opencode/opencode.jsonc`，能看到三个课程 Agent，且默认是 `course-plan`。不再用 `OPENCODE_CONFIG` 或 `--pure`。按[权限模型](architecture/permission-model.md)实测允许读、禁写、禁 shell、Build 按路径询问及冻结路径拒绝。发现额外插件、MCP 或权限差异，先处理并复查，不发正式任务。

运行 `opencode`，用 `/agents`（默认 `Ctrl+X` 后按 `a`）选择 `course-plan`。如果用网页，启动 `opencode serve --hostname 127.0.0.1 --port 4096`，按终端显示的地址和登录提示进入，再从 Agent 菜单选择；不要分享登录凭据。

```text
先读 AGENTS.md，再按 Prompt.md 和 D1–D4 进入 Plan 阶段。
本轮只做 FR-01 / INV-01，起始提交为 <SHA>。

列出每条验收标准对应的组件、接口与测试；要读或改的确切文件、
共享接口、失败处理和回滚方式；以及固定输入、预期结果和测试命令。
同时覆盖 CLI、Python API、正式报告和决策记忆：
合法评级且引用本次运行的有效证据应能发布并查回源材料；
非法评级、缺失、未知或跨运行引用应被拦截，不能作为正式决策流出。

权限不足时列出所需文件并停下。不生成或编辑代码。
结束时写 WAITING FOR PLAN AND TEST APPROVAL。
```

其他需求替换 ID 和验收案例。让队友明确批准**同一版计划、确切文件范围、正反例和预期结果**；记录审批人、时间及计划版本或链接。最终 PR 的批准不能代替实现前审批。

## 3. 用 course-build 先写测试，再写实现

审批后用 Agent 菜单切到 `course-build`，提供获批记录、计划和文件清单。分两次下指令：

1. 只写获批离线测试，使用固定样本与假模型。由人在终端运行该测试，确认关键反例按预期暴露原有缺口。缺依赖、导入错误或没收集到用例不算有效反例。
2. 把实际失败断言与原因交回 OpenCode，再授权改获批的业务文件。只做最小实现；若要扩文件范围、动共享接口、加依赖或改验收条件，先请队友复审。编辑逐次批准，不选永久授权。

三个 Agent 都不能执行 shell；测试、Git 操作、审批和合并由人控制。

## 4. 人工复测，切到 course-verify

在项目虚拟环境中安装开发依赖（如未安装）：`python -m pip install -e ".[dev]"`。复测自己的精确文件，再跑回归：

```bash
python -m pytest -q test/offline
python -m pytest -q tests test/offline
git diff --check
git status --short
```

显式传入 `test/offline`，因为默认测试目录是 `tests/`。记录实际命令、版本、结果和未运行项；在线测试单独记录。FR-01 要同时证明假证据会被拦截、合法建议会放行，避免全部拒绝也能通过测试。

切到 `course-verify`，给它实际 diff 和测试结果，逐条核对 D1 验收、D2 边界和 D4 证据。Verify 给审查建议，队友给最终结论。

## 5. 保存会话，提交功能 PR

保存 Plan、Build 和 Verify 的会话 ID、审批和人为纠偏记录。2.3.0 用 `opencode session list` 查 ID；把真实会话导出到公开仓库之外，例如：

```bash
opencode session export ses_REPLACE_ME > "../fr01-plan-private.json"
```

按实际 ID 分别导出，使用尚不存在的文件名防止覆盖；D5 按课程要求整理成标注转录，注明何时批准、拒绝、叫停或纠偏及其理由。原始转录、个人信息、API Key 和完整配置调试输出不要提交到公开仓库。

人工检查 diff，只暂存获批的源码、测试和脱敏文档。提交后运行 `git push -u origin HEAD`，在小组仓库开 PR，例如 `[FR-01] Enforce evidence-backed publication`。PR 正文包含：

- 需求 / 不变量和起始 SHA。
- 实现前审批：计划与测试版本、审批人、时间和记录链接。
- 实际改动范围、共享入口和回滚方法。
- 改动前失败断言、改动后正常例／反例／回归结果，以及未运行项。
- 人工干预和剩余风险。

队友实审后，在 [D4 审查记录](review-memo.md)留下结论。涉及共享入口的 PR 错开合并，每合一批跑集成回归。确认正式 CI 确实收集课程离线测试，必过检查会阻止不合格的合并。

官方参考：[配置迁移](https://opencode.ai/docs/migrate-v1) · [终端模式](https://opencode.ai/docs/cli/tui/) · [调试和会话导出](https://opencode.ai/docs/cli/commands/) · [Web](https://opencode.ai/docs/cli/web/)
