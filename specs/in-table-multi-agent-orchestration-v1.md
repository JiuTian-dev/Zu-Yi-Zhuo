# 组一桌：桌内 Multi-Agent 编排与阶段总结执行 SPEC v1.0

> Status: Ready for implementation
>
> Date: 2026-09-08
>
> Owner: 产品 / 后端工作线
>
> Parent contracts: [`conversation-orchestrator.md`](./conversation-orchestrator.md)、[`bruno-runtime-product-integration-v2.md`](./bruno-runtime-product-integration-v2.md)
>
> Runtime truth: [`backend/ARCHITECTURE.md`](../backend/ARCHITECTURE.md)、[`backend/ACCEPTANCE_MATRIX.md`](../backend/ACCEPTANCE_MATRIX.md)

## 0. Previous → Current → Next

- Previous：匹配页、Lobby、入席、真人消息、六种主持动作、回放和收桌已有真实 REST / WebSocket 主链；3D 进入维护状态。
- Current：桌内仍是“确定性 Observer / Gate / Router / Host + 可选文案改写模型”。它能驱动动作，但没有真正的专职 Agent 协作，也没有独立、可纠偏的阶段总结。
- Next：增加代码控制的桌内 Manager、有限的后台专职 Agent、版本化阶段总结和完整 eval，使 Agent 能持续提升讨论，而不只是对聊天作出反应。

## 1. 本轮目标

本轮只完成一条纵向链路：

```text
用户已经进入一张具体桌的匹配页
  → 看见真实 Lobby 与匹配理由
  → 旁听或入席
  → 真人讨论持续进入 TableState
  → 后台 Multi-Agent 理解内容与参与结构
  → 圆桌主持人选择沉默、递话、追问、重构或补充事实
  → 在真正的阶段边界发布可纠偏的阶段总结
  → 依据阶段总结推进下一阶段
  → 形成收桌公共底稿与个人卡
```

本轮的产品命题是：

> Multi-Agent 是否能让一张多人桌形成更清楚的问题、更有质量的分歧、更充分的参与和更可执行的结果。

阶段总结是这套系统的核心控制面，不是附加的聊天摘要。

## 2. 明确不做

本 SPEC 不实现或修改：

- 首页、Gallery、个人中心、好友列表、私聊和账户级邀请中心；
- 登录页、知乎 OAuth、Access Secret、真实知乎个人数据或全局推荐；
- 首次进入产品前的主动式画像追问；
- 手动建桌入口和全局“找桌 / 建桌”决策树；
- 第二套 3D Runtime、场景重做、Agent IP、镜头和动作资产；
- 自动替用户承诺行动、自动邀请新成员或自动关闭桌；
- 把多个后台 Agent 的名字、思考过程或争论直接展示给用户；
- 以引入某个 Agent 框架本身作为完成标准。

匹配页在本轮只承担已有桌的真实入口。只要能把一个合法 `table_id` 和用户期望身份交给现有 Lobby，本轮不扩展匹配算法。

## 3. 产品不变量

1. **一张桌只有一个公开主持人格。** 后台可以有多个 Agent，用户只看见“圆桌主持”。
2. **真人优先。** 消息先安全校验、幂等提交和广播；Agent 慢或失败不能阻塞真人继续交流。
3. **默认沉默。** Multi-Agent 的存在不能把每轮讨论变成 AI 点评。
4. **证据优先。** 任何共识、分歧、洞见、遗漏和下一问题都必须引用真实 `turn_id`。
5. **共识不能猜。** 没有足够证据时只能写“已提出”“仍待确认”或“存在分歧”，不能写成全桌共识。
6. **用户可纠偏。** 阶段总结发布后，桌内成员能指出误解、遗漏、伪共识或确认进入下一阶段。
7. **单一写入者。** 专职 Agent 只能生成 proposal；只有代码 Coordinator 能提交 `TableState`、阶段总结和主持动作。
8. **版本单调。** 所有 Agent 结果绑定输入版本；陈旧结果不得覆盖新消息产生的状态。
9. **私密不外溢。** 未经 consent 的经历、个人卡、私有 source 和内部 Agent prompt 不进入公共总结、事件或 trace。
10. **无模型仍可退化运行。** provider 不可用时，真人消息、确定性安全、基础主持和证据化简版总结仍可工作。

## 4. 为什么采用 Manager 架构

采用“代码控制的 Manager + agents as bounded workers”，不采用 Agent 之间自由 handoff：

```text
                         ┌─ Content Analyst
Human turn → Coordinator ├─ Participation Analyst
                         ├─ Facilitation Strategist
                         └─ Stage Summarizer → Summary Verifier
                                      ↓
                              Public Host Renderer
                                      ↓
                       AgentActionEvent / StageSummary
```

选择理由：

- 桌面需要一个主持人综合多个判断并保持统一语气；OpenAI 的官方编排文档把这种情况归为 manager / agents-as-tools，而 handoff 更适合让专职 Agent 直接接管用户对话。[OpenAI Agent orchestration](https://openai.github.io/openai-agents-python/multi_agent/)
- Anthropic 的生产经验指出，多 Agent 会显著增加协调和 token 成本，且所有 Agent 强依赖同一上下文时未必适合全量并行。因此本 SPEC 只在可独立分析的阶段运行有限并行，不做 Agent 群聊。[Anthropic multi-agent research system](https://www.anthropic.com/engineering/multi-agent-research-system)
- 当前仓库已有稳定的 FastAPI 状态机、`LLMProvider` 和原子仓储边界。先在这些边界上实现 manager pattern，比引入第二套 workflow runtime 更小、更容易验证。

首版不强制引入 OpenAI Agents SDK。保留 `AgentRuntime` 适配边界；只有当 eval 证明 SDK 能降低代码量或显著改善 trace、取消、并发和恢复时，才单独提出迁移 ADR。

## 5. Agent 角色

### 5.1 TableRunCoordinator（代码，不是自由决策模型）

职责：

- 接收已提交的真人 turn 和当前 `TableState`；
- 构造有界 `AgentContext`；
- 判断使用快路径还是阶段边界路径；
- 在预算内调用需要的专职 Agent；
- 校验、合并 proposal；
- 以 `expected_state_version` 做唯一写入；
- 丢弃陈旧结果、记录运行结果和降级原因；
- 决定是否让公共 Host 发言。

Coordinator 不生成自然语言，不读取未授权个人资料。

### 5.2 ContentAnalystAgent

输入：上一个已发布 checkpoint、checkpoint 后的真人 turns、当前问题和现有 evidence state。

输出 `ContentAnalysis`：

- 新的有证据洞见；
- 候选共识及支持/反对证据；
- 分歧类型与涉及成员；
- 未回答问题和缺失事实；
- 当前最有潜力的讨论线索；
- 建议阶段，但不能直接迁移阶段。

它不能输出用户可见主持文案。

### 5.3 ParticipationAnalystAgent

输入：公开或已授权的参与者状态、发言次序和最近 turns。

输出 `ParticipationAnalysis`：

- 尚未被接住的问题；
- 发言集中度；
- 长时间未发言但可能具有相关经历的成员；
- 合适的递话对象及证据；
- 是否应继续沉默。

它不能把安静自动解释为不参与，也不能强迫成员发言。

### 5.4 FacilitationStrategistAgent

输入：两个 analysis、当前阶段、最近干预、冷却信息和可信 Grounding 卡可用性。

输出 `InterventionProposal`：

```text
SILENCE | PASS | PROBE | REFRAME | GROUND | CHECKPOINT | CLOSE_CANDIDATE
```

它只提出动作、目标和证据。现有确定性 Safety、Gate 和硬规则可以否决 proposal。

### 5.5 StageSummarizerAgent

仅在 Coordinator 判定存在 checkpoint candidate 时运行。

职责是把已定位的证据组织成四个固定区块：

1. 已经说清楚的；
2. 当前仍存在的分歧；
3. 还缺的事实或视角；
4. 下一步最值得讨论的。

先定位证据、再总结。QMSum 的会议总结研究表明，长会议的一次性通用摘要很难覆盖不同需要，locate-then-summarize 和相关 span 标注更适合保留来源位置。[QMSum](https://arxiv.org/abs/2104.05938)

### 5.6 SummaryVerifierAgent

对 `StageSummaryDraft` 做逐项核验：

- 所有引用的 turn 是否存在且属于本桌；
- 文本是否能由所引 turns 支持；
- 发言者、行为、时间、否定和因果关系是否被改写；
- 是否把单人意见、相似意见或暂时无人反对误写成共识；
- 是否遗漏已知反例；
- 是否泄露未授权资料；
- `next_focus` 是否来自当前 open loop，而非凭空新增产品任务。

对话摘要已有实体、谓词、情境、指代和关系等细粒度事实错误；因此仅靠生成模型自信度不能发布总结。[DIASUMFACT](https://aclanthology.org/2023.acl-long.377/)

Verifier 输出 `approved / repair / reject`。最多允许一次定向修复；仍不通过则使用确定性简版或本轮不发布。

### 5.7 PublicHostRenderer

复用现有 Host，对外只渲染已经批准的动作或总结提示。

- 后台 Agent 名称、分数、争论和 chain-of-thought 不对外；
- 阶段总结主体进入独立卡片，Host 只说一句推进话；
- Host 文案不能添加 summary 中没有的事实；
- Host 文案失败时，summary 仍可发布，或使用确定性短句。

## 6. 两条运行路径

### 6.1 每个真人 turn 的快路径

```text
human_message
  → 身份 / 席位 / 长度 / 限速检查
  → Safety
  → message_id 幂等提交
  → 广播 message_committed
  → 确定性 Observer 更新 TableState
  → Coordinator eligibility check
      ├─ 不需要重分析：沿用 Gate / Router / Host
      └─ 需要分析：排入 bounded Agent run
  → 广播最新单调版本状态
```

硬要求：真人消息的 durable commit 和实时广播不等待任何外部模型。

### 6.2 阶段边界路径

```text
eligible checkpoint
  → stage_summary_started（只表示系统在整理，不暴露思考）
  → 固定 snapshot(input_state_version, turn range)
  → Content + Participation 可并行
  → Strategist 形成 CHECKPOINT proposal
  → Summarizer 生成 draft
  → Verifier approve / repair / reject
  → 重新读取当前 TableState.version
      ├─ 未变化：原子发布 summary + phase transition
      └─ 已变化：检查新 turn 是否影响结论
          ├─ 无影响：以新版本重新校验后提交
          └─ 有影响：丢弃并最多重跑一次
  → stage_summary_published
  → Public Host 用一句话把讨论交给 next_focus
```

同一张桌同一时刻最多有一个 checkpoint run。后续触发合并为一个 pending signal，不堆积任务。

## 7. 阶段与总结触发

阶段继续使用现有枚举：

```text
opening → explore → tension → deepen → close
```

### 7.1 语义触发（主要）

满足下列任一条件可形成 checkpoint candidate：

- 核心问题已被重新表述并得到至少两位成员的直接响应；
- 形成新的稳定分歧或已有分歧发生实质变化；
- 一条可信事实改变了讨论方向；
- 同一 open loop 连续被多位成员推进；
- 讨论开始重复、漂移或停滞，需要重新聚焦；
- close readiness 达到高，但在关闭前需要全桌核对；
- 成员显式请求“总结一下现在聊到哪里”。

### 7.2 数量与冷却约束（保护，不是主逻辑）

默认值必须可配置，首轮建议：

- 自动总结至少覆盖 4 条新的真人 turn；
- 自动总结至少包含 2 位不同成员的发言；
- 两次自动总结之间至少间隔 4 条真人 turn；
- 连续 12 条真人 turn 没有发布 checkpoint 时，强制做一次 eligibility review，但不保证发布；
- `opening` 阶段允许一次更早的“问题对齐”总结，但仍需至少两位成员发言；
- 手动请求可以绕过 turn 冷却，但不能绕过证据、权限和并发约束；
- 安全暂停期间不发布普通阶段总结。

阈值是初始参数，不是产品真理。必须通过场景 eval 和真实内测校准，不能直接把“总结次数”当成功指标。

### 7.3 阶段迁移约束

- 总结发布不必迁移阶段；同一阶段可有多个 checkpoint。
- 阶段只能前进，除受控恢复外不回退。
- `tension` 表示存在值得处理的分歧，不等于负面冲突或安全风险。
- `deepen` 必须有明确的 most-promising thread 或 high-priority open loop。
- 进入 `close` 仍沿用现有 close evidence gate；summary 不能自行关闭桌。

## 8. 上下文工程

每个专职 Agent 不接收全量 replay。长上下文中的相关信息可能因位置而难以稳定使用；应给模型最小高信号上下文，而不是依赖窗口足够大。[Lost in the Middle](https://arxiv.org/abs/2307.03172)、[Anthropic context engineering](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)

`AgentContext` 只包含：

- `table_id`、`input_state_version`、`core_question`、当前阶段；
- 最新已发布的 `StageSummary`，如有；
- 该 checkpoint 之后的真人 turns；
- 被当前问题或 proposal 引用的较早 evidence turns；
- 当前公开 `new_insights / consensus / disagreements / open_loops`；
- 最后一次非 SILENCE 干预及效果摘要；
- 有 consent 的最小参与者角色/经历投影；
- 可信 Grounding 卡是否可用，内容只给需要它的 Agent。

禁止包含：

- 全量个人卡、OAuth token、未授权经历、举报正文；
- 与当前桌无关的账户历史；
- 其他 Agent 的原始推理；
- 不受长度限制的 transcript 或 trace。

阶段总结同时是下阶段的压缩记忆，但不能替代 immutable turns。任何争议都以原始 turn 为准。

## 9. 新领域合同

所有新模型继续继承 `ContractModel`，保持 `extra="forbid"`。

### 9.1 StageSummary

```python
class StageSummary(ContractModel):
    summary_id: str
    table_id: str
    revision: int                 # 同一 summary 的纠偏版本
    status: Literal["published", "superseded"]
    input_state_version: int
    published_state_version: int
    phase: Phase
    trigger: Literal[
        "question_aligned", "disagreement_changed", "grounding_changed",
        "thread_advanced", "stalled", "manual", "pre_close"
    ]
    covered_turn_start: PositiveInt
    covered_turn_end: PositiveInt
    clarified: list[EvidenceStatement]          # <= 3
    disagreements: list[Disagreement]           # <= 3
    missing: list[EvidenceStatement]            # <= 3
    next_focus: EvidenceStatement | None
    created_at: float
    model: str
    used_fallback: bool
```

合同约束：

- 每个非空条目至少一个 `evidence_turn`；
- evidence 必须位于本桌且不晚于 `input_state_version` 对应 turn；
- `clarified` 不等同于 consensus；文字不得使用“大家一致认为”，除非满足共识规则；
- `covered_turn_start <= covered_turn_end`；
- `published_state_version > input_state_version`；
- 单个区块最多 3 条；公开总文本建议不超过 480 个中文字符；
- close 后不能新增非 `pre_close` summary；
- 旧 revision 不删除，标记 `superseded`，回放默认展示最新版本并可查看修改记录。

### 9.2 StageSummaryFeedback

```python
class StageSummaryFeedback(ContractModel):
    feedback_id: str
    table_id: str
    summary_id: str
    summary_revision: int
    participant_id: str
    kind: Literal[
        "misrepresented", "missing_point", "not_consensus", "ready_to_advance"
    ]
    note: str | None             # <= 240
    evidence_turns: list[PositiveInt]
    status: Literal["open", "applied", "dismissed"]
    created_at: float
```

只有当前桌成员可提交；observer 只读。`ready_to_advance` 可以无 note，其余类型必须有 note 或 evidence。

### 9.3 AgentRunRecord

这是受限内部审计，不进入公共 `TableState`：

```python
class AgentRunRecord(ContractModel):
    run_id: str
    table_id: str
    trigger_turn_id: PositiveInt
    input_state_version: int
    outcome: Literal[
        "no_action", "host_action", "summary_published", "stale_discarded",
        "fallback", "rejected", "timeout", "cancelled"
    ]
    invoked_agents: list[str]
    attempts: int
    latency_ms: int
    token_usage: TokenUsage
    used_fallback: bool
    error_code: str | None
    output_refs: list[str]
```

不保存原始 chain-of-thought。prompt/response 正文默认不进入仓储或第三方 trace。官方 tracing 文档也明确提醒 generation/tool spans 可能含敏感输入输出，因此生产默认只记元数据和已脱敏的结构化输出。[OpenAI tracing](https://openai.github.io/openai-agents-python/tracing/)

### 9.4 Agent proposals

内部增加：

- `ContentAnalysis`
- `ParticipationAnalysis`
- `InterventionProposal`
- `StageSummaryDraft`
- `SummaryVerification`

它们只在 Agent 边界传递，不直接成为用户 API。

## 10. 状态与持久化

### 10.1 TableState

`TableState` 只增加两个轻量引用：

```text
latest_stage_summary_id?: str
latest_stage_summary_revision?: int
```

完整阶段总结、反馈和 Agent run 使用独立账本，避免不断放大每个状态快照。

### 10.2 新账本

- `stage_summaries[table_id]`：append-only summary revisions；
- `stage_summary_feedback[table_id]`：成员纠偏；
- `agent_runs[table_id]`：受限运行元数据；
- 保留现有 `turns`、`interventions`、`replay snapshots` 为事实来源。

### 10.3 跨 worker single-flight

同一桌的 checkpoint 不能因为两个 ASGI worker 同时收到事件而重复运行：

- 增加 `AgentRunLeaseStore`，键为 `(table_id, purpose)`；
- 默认单进程使用内存 lease；配置 `SHARED_EPHEMERAL_STORE_PATH` 时复用 SQLite 事务实现；
- lease 至少包含 `run_id / input_state_version / owner / expires_at`；
- claim 使用单条原子事务，只允许一个 owner 成功；
- lease TTL 必须大于 checkpoint hard deadline，进程崩溃后可以自动过期；
- 相同 `table_id + input_state_version + trigger` 生成稳定幂等 run key；
- event bus 只传播已提交的 summary/state 提示，不传播 Agent prompt、私密上下文或半成品；
- v1 不引入 durable job queue。进程在模型调用中崩溃时允许该次自动总结丢失，但不允许产生半提交状态；成员可以重新请求。

### 10.4 原子提交

发布 summary 必须在一个仓储事务中：

1. 检查当前 `TableState.version == expected_state_version`；
2. 校验 evidence turns；
3. append `StageSummary`；
4. 可选迁移 phase / current_subquestion；
5. 更新 latest summary 引用；
6. 写入新 `TableState` 快照；
7. append `AgentRunRecord` 输出引用。

任一步失败则全部失败。模型调用发生在事务外，提交时必须重新校验版本。

反馈应用同样原子地产生新 revision，不覆盖旧 summary。

## 11. API 与 WebSocket

### 11.1 REST

新增：

```http
GET  /tables/{id}/stage-summaries?participant_id=...
GET  /tables/{id}/stage-summaries/latest?participant_id=...
POST /tables/{id}/stage-summaries/request?participant_id=...
POST /tables/{id}/stage-summaries/{summary_id}/feedback?participant_id=...
GET  /tables/{id}/agent-runs?participant_id=...     # 仅开发/受信调试身份
```

约束：

- participant 可以读取公共 summary 和自己的反馈；observer 可读取公共 summary，但不能纠偏或请求生成；
- `agent-runs` 不向普通桌内用户开放；
- request 接口只登记请求并返回 `202` 或已有运行状态，不同步等待模型；
- 同一 participant 对同一 summary revision 的相同 feedback 幂等；
- 所有写入继续走身份、席位、限速和生命周期校验。

### 11.2 WebSocket 入站

新增：

```json
{ "type": "request_stage_summary", "request_id": "..." }
```

可选后续增加结构化纠偏事件；v1 纠偏优先走 REST，减少 WS 写协议范围。

### 11.3 WebSocket 出站

新增：

```text
stage_summary_started
stage_summary_published
stage_summary_superseded
stage_summary_failed
```

`started` 只含 `table_id / input_state_version / trigger`。不显示“某 Agent 正在思考什么”。

`failed` 使用通用错误码；自动总结失败不弹破坏性错误，只恢复讨论。用户手动请求失败时才显示可重试提示。

`stage_summary_published` 携带最新公共 `StageSummary`，随后广播相同或更高版本的 `table_state_changed`；客户端继续拒绝版本倒退。

### 11.4 Replay

`GET /tables/{id}/replay` 增加：

- `stage_summaries`：所有已发布 revision；
- `stage_summary_feedback`：只返回当前 viewer 自己提交的反馈；
- 保持 turns、interventions、grounding card 和 close artifacts 原有语义。

## 12. 前端体验合同

### 12.1 展示位置

阶段总结是桌面上的一张可收起卡片，不替换消息流，也不新建页面：

```text
这一阶段我们走到了这里

说清楚了       仍有分歧
还缺什么       接下来聊什么
```

- 默认展示最新 summary；
- 新 summary 到达时轻提示，不抢焦点、不强制弹窗；
- 历史 summary 在现有历史/回放弹层查看；
- 3D 只接收已有 `visual_hint`，不新增第二套业务逻辑。

### 12.2 等待状态

只展示短状态：

```text
正在整理这一阶段…
正在核对有没有误解…
```

不展示 Agent 列表、内部路由、评分或逐步推理。

### 12.3 纠偏入口

每份 summary 提供四个轻量动作：

- 不是我的意思；
- 漏了一个关键点；
- 这点还没有共识；
- 可以进入下一步。

前三种允许补一句说明。提交后显示“已记录”，新 revision 发布后标识“根据桌友纠正”。

### 12.4 单一主持人格

- 所有用户可见 Agent 文案仍使用 `agent_id=roundtable-agent`；
- summary 卡不标注“Content Agent / Critic Agent”；
- 同一 checkpoint 最多出现一条主持推进消息；
- Host 不复述整张 summary。

## 13. 失败、并发和预算

### 13.1 Provider 失败

- 单个结构化调用最多一次 repair retry；
- 总 Agent run 设硬 deadline；
- timeout、malformed output、schema mismatch 均不可跨入状态写入；
- Content/Participation 某一路失败时，只有剩余输出加确定性状态足够满足合同才继续，否则回退或放弃；
- Verifier 不通过时不得“带病发布”。

### 13.2 建议预算

以下用于首轮 mock/联调验收，生产阈值后续按真实数据调整：

- 真人消息 commit + `message_committed`：不等待模型；
- `stage_summary_started`：请求后 300ms 内可观察到；
- 单个专职 Agent：soft timeout 4s，hard timeout 8s；
- 单次 checkpoint run：hard deadline 12s；
- 同时运行的专职 Agent 最多 2 个；
- 每个 checkpoint 最多 5 次模型调用，包含一次 repair；
- 每桌最多 1 个 active run + 1 个合并后的 pending trigger；
- 自动 checkpoint 失败不自动无限重试。

### 13.3 陈旧结果

- 每个输出带 `input_state_version`；
- 提交前版本变化时先判定新 turn 是否落在 summary 证据范围之后；
- 新 turn 反驳或修改了任何 summary item 时必须重跑；
- 最多自动重跑一次，仍变化则丢弃，等待下一次自然触发；
- 旧结果可以进入 `AgentRunRecord(outcome=stale_discarded)`，不能进入公共状态。

### 13.4 安全

- 现有 deterministic Safety 在所有 Agent 之前运行；
- 每个 Agent 输出都经过 schema、evidence、privacy guard；
- 写状态的工具边界再做一次权限和版本校验；
- 不能只依赖链首和链尾 guardrail，因为多 Agent 中间调用需要各自的工具级校验。[OpenAI guardrails](https://openai.github.io/openai-agents-python/guardrails/)

## 14. 评测体系

不能用“Agent 调用了几次”“总结生成了几份”证明讨论质量。

### 14.1 硬合同指标

必须达到：

- summary item evidence coverage = 100%；
- 引用不存在或跨桌 turn = 0；
- 未授权个人资料泄漏 = 0；
- 单人意见被写成全桌共识 = 0；
- 陈旧 Agent 结果覆盖新状态 = 0；
- 重复请求生成重复 summary revision = 0；
- 同一时刻公共主持人格数量 = 1；
- provider 失败后真人消息链可继续 = 100%。

### 14.2 质量指标

先建立 baseline，再设优化目标：

- 阶段边界准确率：人工判断应总结时是否总结；
- 打扰率：不需要总结/介入时是否保持沉默；
- 事实支持率：人工核对每条总结是否由引用 turns 支持；
- 分歧保真率：是否保留少数意见和不确定性；
- 纠偏率与纠偏后解决率；
- 参与覆盖：阶段内是否至少接住两个不同成员的有效贡献；
- 推进率：checkpoint 后若干 turn 是否围绕 `next_focus` 产生新事实、澄清或行动；
- 主持有效率：沿用现有 intervention reflection，但不让该指标自动改变策略。

### 14.3 固定场景集

至少包含：

1. 两人快速同意，但证据不足以称为全桌共识；
2. 两种定义互相错位，应 REFRAME；
3. 同一事实主题出现明确相反断言，应 GROUND 或 PROBE；
4. 一人连续发言、另一位拥有相关经历，应 PASS；
5. 讨论自然顺畅，应保持 SILENCE，不应机械总结；
6. 阶段总结发布后成员选择“不是我的意思”，生成可追踪 revision；
7. summary 生成期间新 turn 反驳旧结论，旧结果被丢弃；
8. provider 超时/非法 JSON，使用安全 fallback；
9. 未 consent 的经历不进入 AgentContext 或 summary；
10. observer 能看到 summary 但不能纠偏；
11. 安全暂停时普通 summary 不发布；
12. pre-close summary 通过后才允许现有 close 路径产生 artifacts。

### 14.4 评测方法

- 单元测试检查 schema、触发、版本、共识规则和 fallback；
- 仓储测试检查 JSON 重启、revision、幂等和原子提交；
- WebSocket 测试检查事件顺序、双客户端和消息不阻塞；
- provider contract 测试使用可脚本化 fake agent 输出；
- scenario replay 对同一 transcript 运行 deterministic 与 model-backed 两种模式；
- 浏览器 E2E 从具体匹配页进入同一张隔离测试桌，至少两位 participant + 一位 observer；
- 人工 reviewer 只看 transcript、summary 和动作，不看内部 prompt，避免被实现过程影响。

## 15. 实施分层与 stacked diffs

### D0 — 评测夹具与基线

目标：先把“好总结 / 坏总结 / 应沉默 / 应推进”写成固定 transcript fixtures。

- 新增 12 个场景和期望检查点；
- 记录当前单体 orchestrator 的 baseline；
- 不改运行时行为。

验收：fixtures 可重复执行，人工标注规则写清。

### D1 — 合同与持久化

- 增加 `StageSummary`、feedback、proposal 和 run record；
- 增加独立账本与 JSON 兼容加载；
- 增加内存 / SQLite `AgentRunLeaseStore`，保证跨 worker single-flight；
- 增加 optimistic summary bundle commit；
- 只加 API 读写骨架，不调用模型。

验收：字段级 schema、旧快照兼容、原子失败、幂等、隐私全绿。

### D2 — Deterministic Coordinator

- 新增 `TableRunCoordinator`、trigger policy、context builder；
- 消息提交后以受控后台任务启动 run，接入 lease、deadline、取消和 pending trigger 合并；
- 复用现有 Observer/Gate/Router/Host；
- 用当前 `TableState` 生成证据化简版阶段总结；
- 接入 WebSocket 事件和 replay。

验收：无模型模式走通具体匹配页 → 入桌 → summary → close。

### D3 — Summary vertical slice

- 接入 `StageSummarizerAgent` 与 `SummaryVerifierAgent`；
- 支持一次 repair 与 deterministic fallback；
- 前端增加 summary 卡、短等待状态和历史；
- 不增加其他专职 Agent。

验收：事实性、纠偏、并发 stale、超时场景全绿。

### D4 — 内容与参与双 Agent

- 接入 Content 与 Participation 两条独立、最多双并行分析；
- Strategist 合并 typed proposals；
- Host 仍是唯一公开输出；
- 增加运行元数据和 token/latency 预算。

验收：场景集相对 D2 baseline 有明确提升，且打扰率、延迟和成本在预算内。

### D5 — 用户纠偏闭环

- 四种轻量纠偏；
- summary revision 与 supersede；
- feedback 影响下一轮 AgentContext；
- 回放能解释“哪里被用户改过”。

验收：双客户端纠偏一致、旧 revision 可回放、新状态不倒退。

### D6 — 完整桌内 E2E 与新鲜审查

- 双 participant + observer；
- 自动与手动 checkpoint；
- 至少一次 PASS/PROBE/REFRAME/GROUND 中的有效动作；
- 阶段总结、纠偏、close artifacts；
- provider failure 与断线恢复演练；
- 从 fresh perspective 审查合同、隐私、状态版本和前端单主持人格。

验收：本 SPEC Definition of Done 全部满足。

## 16. 预计代码落点

```text
backend/app/domain/schemas.py
  StageSummary / Feedback / Agent proposal / AgentRunRecord

backend/app/orchestrator/
  coordinator.py
  context.py
  checkpoint.py
  agents/content.py
  agents/participation.py
  agents/strategy.py
  agents/summary.py
  agents/verify.py

backend/app/api/repository.py
  summary / feedback / run ledger + atomic bundles

backend/app/api/app.py
  stage summary REST

backend/app/api/websocket.py
  non-blocking trigger + summary events

backend/app/providers/
  reuse LLMProvider / resilient calls; do not bind domain to vendor SDK

src/live/contract.ts
src/live/api.ts
src/live/backend.ts
src/live/store.ts
src/live/StageSummaryPanel.tsx
src/App.tsx
  public summary UI only; no agent decision logic
```

重要共享边界保持单 owner：后端合同先落，再更新 `src/live/contract.ts`；前端不能先发明一套 summary 字段。

## 17. Definition of Done

本轮只有在以下条件全部成立时完成：

- [x] 一个真实 `table_id` 能从具体匹配页进入现有 Lobby 和同一桌内 Runtime；
- [x] 两位真实浏览器 participant 的消息不等待 Agent 模型即可提交和互相可见；
- [x] Coordinator 能按事件选择有限的专职 Agent，并保持单一状态写入者；
- [x] 普通顺畅讨论默认沉默，阶段边界与手动请求才发布总结；
- [x] 阶段总结固定包含“说清楚 / 分歧 / 缺失 / 下一步”四块；
- [x] 每个非空 summary item 都能从 replay 定位到真实 turns；
- [x] 成员可以纠偏，纠偏生成新 revision，旧 revision 可回放；
- [x] observer 只读，未 consent 信息不进入 summary；
- [x] 生成期间的新消息不会被旧 Agent 结果覆盖；
- [x] provider 超时、非法输出和中途失败均安全降级，真人讨论继续；
- [x] 后台 Agent 不直接面向用户，公开事件中只有圆桌主持人格；
- [ ] checkpoint 目前已进入 AgentContext 和 typed strategist proposal，但尚未把 summary next_focus 接回下一轮 Host route；
- [ ] pre-close summary 尚未接入 close transaction；公共底稿、个人卡和 replay 原有链路已保持不变；
- [x] contract、repository、orchestrator、WebSocket、双客户端和浏览器 E2E 全部通过；
- [x] 新增 eval 能区分“有帮助的推进”与“高频插话/高频总结”的标注规则，并固定输出 baseline 指标；
- [x] `git diff --check`、前端 check/build、后端 pytest、字段级合同审查通过；
- [x] 进度、验证命令、剩余风险与提交号写回本 SPEC 的 Progress Ledger。

## 18. Progress Ledger

| Diff | 状态 | 当前证据 | 下一步 |
| --- | --- | --- | --- |
| D0 评测夹具 | done | 12 场景 manifest；10 次重复 replay 无漂移；baseline=`evidence 1.0 / action_hit 0.6667 / interruption 0.0833 / p50 0.196ms / p95 0.240ms` | 真实数据接入后再校准标注阈值 |
| D1 合同/持久化 | done | Pydantic 合同、memory/JSON 独立账本、SQLite lease、原子 summary bundle；repository tests 7 passed | 生产规模可替换 SQLite/事件总线实现 |
| D2 Coordinator | done | bounded context、checkpoint policy、run service、deadline/lease/fallback、慢 provider 非阻塞测试 | 将 semantic auto-checkpoint 从 WS 事件队列中接回并保持旧顺序合同 |
| D3 Summary slice | done | summarizer/verifier、REST/WS/replay、summary card、feedback actions；前端 check/build 通过 | 下一步将 summary next_focus 影响 Host route |
| D4 Multi-Agent | scaffolded | Content/Participation 并行 typed specialist + strategist proposal 已接入 run ledger | 需要真实模型 eval 证明相对 D2 的收益与成本边界 |
| D5 纠偏 | done | 四种 feedback、revision/supersede、stale conflict、viewer-private replay、E2E 通过 | 增加跨 worker feedback transaction 压测 |
| D6 E2E | done | `529 passed`；Playwright 三 tab（2 participant + observer）进入、入席、发言、summary、折叠、截图通过 | 关闭本地演示服务后再提交；pre-close summary 留为下一迭代 |

## 19. 开放但不阻塞 D0–D2 的问题

以下不需要现在向用户追问，先由 eval 给出证据：

1. 自动 checkpoint 的最佳 turn 冷却是 4、6 还是更长；
2. Content 与 Participation 是否值得使用不同模型；
3. Summary Verifier 是否需要独立模型，还是同模型不同上下文已足够；
4. stage summary 卡默认常驻还是在数秒后折叠；
5. 是否采用 OpenAI Agents SDK 作为 `AgentRuntime` 的一个实现。

任何选择都不能改变本 SPEC 的领域合同、单写入者、证据、版本和隐私不变量。

## 20. 调研来源与决策边界

- [OpenAI Agents SDK — Agent orchestration](https://openai.github.io/openai-agents-python/multi_agent/)：Manager 与 handoff 的适用边界。
- [OpenAI Agents SDK — Guardrails](https://openai.github.io/openai-agents-python/guardrails/)：多 Agent 中间工具调用需要独立校验。
- [OpenAI Agents SDK — Tracing](https://openai.github.io/openai-agents-python/tracing/)：run / agent / generation / tool spans 与敏感数据注意事项。
- [OpenAI — A practical guide to building agents](https://openai.com/business/guides-and-resources/a-practical-guide-to-building-ai-agents/)：增量构建、manager pattern、guardrails 和先建立 eval baseline。
- [Anthropic — Effective context engineering for AI agents](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)：长流程中的高信号上下文与循环压缩。
- [Anthropic — How we built our multi-agent research system](https://www.anthropic.com/engineering/multi-agent-research-system)：orchestrator-worker、成本、协调复杂度、阶段记忆和 end-state checkpoints。
- [QMSum](https://arxiv.org/abs/2104.05938)：query-focused meeting summarization、相关 span 与 locate-then-summarize。
- [DIASUMFACT](https://aclanthology.org/2023.acl-long.377/)：对话总结的细粒度事实错误。
- [Lost in the Middle](https://arxiv.org/abs/2307.03172)：长上下文中的位置敏感与检索退化。

这些资料支持架构原则，不替代本仓库的运行证据。真正采用多少 Agent、阈值和模型配置，最终以固定场景、真实桌内回放、延迟、成本和用户纠偏数据决定。
