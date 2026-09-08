# 桌内 Multi-Agent 实施任务清单

> 对应 SPEC：[`in-table-multi-agent-orchestration-v1.md`](./in-table-multi-agent-orchestration-v1.md)
>
> 接力对象：GPT-5.6 Luna Max
>
> 范围：用户已进入具体匹配页之后，直到收桌；不处理登录、首页、好友、全局匹配、知乎 OAuth 或 3D 场景。

## 0. 接手规则

- 先读本清单、主 SPEC、`backend/ARCHITECTURE.md`、`backend/ACCEPTANCE_MATRIX.md`。
- 先运行 `git status --short` 和 `python -m pytest -q`，不要覆盖工作区已有改动。
- 后端领域合同是共享边界的唯一 owner；前端只镜像已确定的公开字段。
- 真人消息先提交和广播，任何模型调用都在提交之后；不得让聊天等待 Agent。
- `TableState` 是唯一状态真相，Coordinator 是唯一写入口；专职 Agent 只能返回 typed proposal。
- 每完成一个任务，更新本文状态与验证证据。只暂存本任务的精确路径，不使用 `git add .`。

状态：`done` 已完成；`scaffolded` 只有可运行骨架；`pending` 尚未实现。

## 1. 总体验收门槛

以下条件缺一不可：

- [x] 两位 participant 的消息无需等待模型即可互相可见，observer 始终只读。
- [x] 同一 `table_id + state_version` 在多 worker 下最多一个 Agent run 获得写资格。
- [x] 所有非空总结条目都有本桌真实 `turn_id`，不存在越桌、虚构或未授权资料。
- [x] 旧版本 Agent 结果无法覆盖新 `TableState`；总结发布与状态引用更新原子完成。
- [x] 公开界面只有一个“圆桌主持人”，后台专职 Agent 名称、推理和失败日志不对用户展示。
- [x] 普通讨论默认沉默；数量阈值只触发复核，当前发布入口为语义/manual/pre-close policy 与成员手动请求。
- [x] 用户纠偏创建新 revision，旧 revision 保留且 replay 可解释。
- [x] Provider 超时、非法结构和 verifier 拒绝时安全降级，真人讨论继续。
- [ ] summary → 下一轮主持动作 → pre-close → 公共底稿/个人卡使用同一证据链（pre-close summary 仍需下一迭代接入 close transaction）。
- [x] 后端全量测试、前端 check/build、双客户端 WebSocket 和真实浏览器路径全部通过；浏览器证据已留在 `output/playwright/`。

## 2. 任务依赖图

```text
D0 评测基线
 └─ D1 合同与账本
     └─ D2 确定性 Coordinator
         └─ D3 阶段总结纵切
             ├─ D4 内容/参与 Multi-Agent
             └─ D5 用户纠偏闭环
                 └─ D6 完整 E2E 与审查
```

## 3. 逐项任务与达标标准

### D0 — 评测夹具与基线

#### D0-1 建 12 类固定 transcript fixtures — `done`

产物：`backend/tests/fixtures/multi_agent/*.json`，覆盖顺畅讨论、沉默、递话、追问、重构、事实补充、阶段边界、虚假共识、错误归因、越桌证据、超时、收桌候选。

达标标准：

- [x] 每个 fixture 写明参与者、turn、初始状态、期望动作、期望/禁止总结项。
- [x] fixture 重放结果确定，同一输入连续运行 10 次无漂移。
- [x] 人工标注规则能区分“有效推进”和“高频插话/高频总结”。

#### D0-2 固化当前单体基线 — `done`

达标标准：

- [x] runner 输出证据覆盖率、干扰率、动作命中率、p50/p95 延迟；错误共识由 fixture annotation rule 固化。
- [x] 基线产物不依赖在线模型，CI 可重复运行。
- [x] 不修改现有运行时行为。

### D1 — 合同、账本与并发写入

#### D1-1 Pydantic 合同 — `done`

已落：`ContentAnalysis`、`ParticipationAnalysis`、`InterventionProposal`、`StageSummaryDraft`、`SummaryVerification`、`StageSummary`、`StageSummaryFeedback`、`AgentRunRecord`，以及 `TableState` 的两个轻量 summary 引用。

当前证据：骨架测试 9 passed；后端全量 516 passed。

剩余增强标准：

- [x] 增加本桌 turn 存在性校验（repository bundle commit）。
- [x] 增加总结条目数量/范围、字符上限和 participant attribution 校验边界。
- [x] 已对字段逐项与主 SPEC 第 9 节核对；repository 级约束仍由 D1-2 补齐。

#### D1-2 独立账本与旧快照兼容 — `done`

修改：`backend/app/api/repository.py` 与 repository tests。

达标标准：

- [x] summary、feedback、agent run 独立存储，不膨胀 `TableState` 快照。
- [x] memory 与 JSON 持久化行为一致；旧 JSON 没有 summary 字段仍可加载。
- [x] `(summary_id, revision)` 唯一；反馈幂等键重复提交不产生副本。
- [x] observer 无写权限；debug run 查询仅受信身份可访问。

#### D1-3 跨 worker lease 与 optimistic commit — `done`

已有 `AgentRunLeaseStore` 协议和单进程实现；需补 SQLite/生产实现。

达标标准：

- [x] claim 使用 SQLite 主键 + `BEGIN IMMEDIATE` 原子写入，不采用“先查再写”。
- [x] 崩溃 lease 有 TTL 过期/恢复策略；相同 table/version 并发只允许一个 winner。
- [x] summary bundle 在 repository 原子临界区写 summary 并推进 `TableState.version`。
- [x] `input_state_version != current_version` 时整包拒绝且无部分写入。

### D2 — 确定性 Coordinator

#### D2-1 Context builder 与 checkpoint policy — `done`

已有 bounded delta、summary 引用一致性、自动阈值复核、语义/manual/pre-close trigger 骨架。

达标标准：

- [x] 上下文只含当前桌、最新已发布 summary、未覆盖 turns 和明确允许的数据。
- [x] pending triggers 合并，不为每条消息无限排队。
- [x] 手动 checkpoint 受 WebSocket/REST mutation limiter 与单表 pending merge 约束。
- [x] 参数来自 `CheckpointPolicy`/service 配置并在测试中固定。

#### D2-2 后台 run 生命周期 — `done`

达标标准：

- [x] 真人消息 commit → broadcast；Host provider 后台运行，summary run 具备 deadline、取消、lease release、pending trigger merge 和 ledger。
- [x] 无 provider 时复用现有 Observer/Gate/Router/Host，并产出安全简版 checkpoint。
- [x] run 失败不会回滚或隐藏已经提交的真人消息；slow-provider 顺序测试覆盖。

#### D2-3 WebSocket/replay 确定性接入 — `done`

达标标准：

- [x] 新事件为 additive contract；replay 可重放相同 summary revision。
- [x] 保留现有 message/action/state 顺序合同。
- [x] 双客户端消息与 state broadcast 由单调版本门控且 stale intervention 丢弃。

### D3 — 阶段总结纵向切片

#### D3-1 Summarizer + Verifier — `done`

已有通用 `StructuredSpecialist`、一次 repair 后 typed fallback 的复用边界；具体角色尚未实现。

达标标准：

- [x] 新增 `agents/summary.py` 与 `agents/verify.py`，schema/prompt 独立。
- [x] verifier 拒绝时不得发布；resilient structured call 最多一次 repair，随后 typed fallback/放弃。
- [x] 每项 evidence 由 repository 校验定位到本桌 turn；summary 不把单人意见写入 TableState 共识。
- [x] 模型输出只能跨 typed proposal 边界，不能携带可执行状态 patch。

#### D3-2 Summary REST 与事件 — `done`

达标标准：

- [x] 实现 list/latest/request/feedback 接口。
- [x] 权限、404/409、幂等和 stale revision 有 repository/E2E 覆盖；通用 REST limiter 覆盖 429。
- [x] started/published/failed 只公开状态、错误码和 summary，不泄露 prompt/思维过程/私有资料。

#### D3-3 桌内 summary 卡 — `done`

修改：`src/live/contract.ts`、`api.ts`、`backend.ts`、`store.ts`、新增 `StageSummaryPanel.tsx`，最小接入 `src/App.tsx`。

达标标准：

- [x] 固定展示“已经说清 / 仍有分歧 / 还缺什么 / 下一步”。
- [x] 可收起、可看历史、短等待、失败可重试；不替换消息流。
- [x] evidence link 会定位当前消息或打开历史；窄屏、键盘和 reduced-motion 规则已覆盖。
- [x] 页面不出现后台 Agent 名称或内部状态。

### D4 — 内容与参与双 Agent

#### D4-1 Content + Participation 并行分析 — `done`

达标标准：

- [x] 最多两路并行，任一路失败通过 resilient typed fallback，不产生半结构结果。
- [x] Content 只判断内容结构；Participation 只判断参与结构。
- [x] 所有建议携带 `input_state_version`、confidence 和 evidence。

#### D4-2 Strategist 合并与唯一 Host — `scaffolded`

达标标准：

- [x] Strategist 只能提议受限 action，Coordinator/现有 loop 重新执行 gate/权限/版本校验。
- [x] `PASS` 必须有合法在席目标，其他 action 不允许目标。
- [x] Public Host Renderer 仍是唯一公开说话入口；一次 run 最多一个主持事件。
- [ ] D0 相对 D2 的真实模型提升和 token budget 尚未有线上数据，保留为发布前风险。

### D5 — 用户纠偏闭环

#### D5-1 四种反馈与 revision — `done`

达标标准：

- [x] 支持四种反馈 kind。
- [x] 修改生成 `revision + 1`；旧版标记 superseded 但不可删除。
- [x] repository stale revision 返回可理解的冲突，最新 revision 可 replay。

#### D5-2 反馈进入后续上下文与 replay — `done`

达标标准：

- [x] accepted correction 进入新 summary revision，下一轮 context 通过 latest summary 可见且保留 participant feedback ledger。
- [x] replay 显示 revision 链和反馈来源，不显示内部推理；匿名/observer 不返回他人 feedback。
- [x] 纠偏后的状态版本单调递增。

### D6 — 完整桌内 E2E 与发布审查

#### D6-1 自动化完整路径 — `done`

达标标准：

- [x] E2E 覆盖真实 table → Lobby → 入席 → 讨论 → 手动 summary → 纠偏 → replay；observer/双客户端另有 WebSocket 覆盖。
- [x] 既有 WebSocket regression 覆盖 PASS/PROBE/REFRAME/GROUND 合同。
- [x] provider malformed/timeout fallback、重复消息、stale intervention/重连路径已有测试。

#### D6-2 真实浏览器与 fresh review — `done`

达标标准：

- [x] Playwright 三 tab 完成两个独立 guest participant + 一个 observer 的真实路径；summary 卡截图留在 `output/playwright/in-table-summary.png`。
- [x] fresh review 复核合同、隐私、状态版本、可访问性和单主持人格。
- [x] `python -m pytest -q`、`corepack pnpm check`、`corepack pnpm build`、`git diff --check` 全绿。
- [x] 主 SPEC Progress Ledger 写入最终命令、结果、残余风险和提交号。

## 4. Luna 第一轮建议工作包

先只完成 `D0-1 → D0-2 → D1-2 → D1-3`，不要同时接前端。这个工作包结束时应形成一个可独立审查的后端 diff：有固定场景、有基线、有 memory/SQLite 账本、有真正跨 worker single-flight、有原子 summary bundle commit，但尚不调用在线模型。

第一轮完成后再做 `D2`；只有 deterministic 路径完整通过，才进入 `D3` 的模型总结与 UI。`D4` 是否保留两路专职 Agent 必须由相对 D2 baseline 的评测结果决定。

## 5. 当前仓库交接状态

- 主 SPEC：已完成。
- 合同：已落骨架并有严格校验。
- Coordinator：已落 context、checkpoint policy、lease 协议与 no-runtime-wiring 骨架。
- Provider：复用现有 `LLMProvider` 和 resilient retry/fallback，不绑定供应商 SDK。
- 生产 WebSocket：已接入 additive summary 事件；真人消息仍先提交广播，Host 在后台运行。
- 当前验证：backend 全量 530 passed；`corepack pnpm check` 与 `corepack pnpm build` 通过；Playwright 三 tab 路径通过。
