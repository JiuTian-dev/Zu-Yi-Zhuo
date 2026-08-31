# 组一桌：Conversation Orchestrator 后端

> Status: confirmed by `组一桌_后端Conversation_Orchestrator_执行SPEC_v1.0.docx`
> Last updated: 2026-08-31

## 目标与反目标（缓存锚点区）
<!-- 本区保存稳定产品决策与接口契约，尽量少改。 -->

### 目标

- 先证明单桌闭环：真人消息进入后，系统维护可解释的 Table State，并决定沉默或做一次最小主持介入。
- 主持动作固定为 `SILENCE / PASS / PROBE / REFRAME / GROUND / CLOSE`。
- 每个判断保存 evidence、confidence、action 与后续 outcome，可回放、可评测。
- 默认沉默；Agent 连续两次介入之间必须留出真人空间。
- 第一条完整纵切为：Schema → Demo seeds → Observer → Gate/Router → Host → Reflection/Close → API/WebSocket。

### 反目标（明确不做的事）

- 不做复杂匹配、People-Problem Graph、大规模知乎用户图谱。
- 不做实时语音、多桌并发、Redis、微服务或复杂 Agent workflow 框架。
- 不训练自研模型，不在业务逻辑中绑定单一 LLM provider。
- 不把聊到的建议自动写成承诺，不让 GROUND 编造来源。

## 架构决策记录（ADR）

### ADR-1: 单体 FastAPI + 轻量 orchestrator

- **决策**: 后端使用 Python、FastAPI、Pydantic v2；流程由自写 orchestrator 组织。
- **理由**: 比赛版优先结构化输出、可调试与可重复 Demo。
- **替代方案**: LangGraph/LangChain、微服务。
- **代价**: 后续复杂分支需要自行维护状态机。

### ADR-2: Evidence-first Table State

- **决策**: Table State 是下一步主持判断用的实时黑板，不是聊天摘要；重要判断携带 turn evidence。
- **理由**: 降低 Observer 脑补，支持回放与黄金案例评测。
- **替代方案**: 只保存 latest summary 或全量历史回灌。
- **代价**: Schema 需要严格的字段上限与版本管理。

### ADR-3: 规则优先、模型可替换

- **决策**: Gate 先执行确定性硬规则；Observer/Router/Host/Reflection 通过 provider adapter 接入模型。
- **理由**: SILENCE、冷却期、安全与失败回退不能依赖模型漂移。
- **替代方案**: 单次大模型直接生成主持话。
- **代价**: 需要维护规则与模型判断的边界。

### ADR-4: 进程内仓储起步

- **决策**: 单桌开发期先使用 repository protocol + in-memory 实现；数据库接线后置。
- **理由**: CLI/golden cases 可先独立验证核心状态演进。
- **替代方案**: 第一批即接 PostgreSQL/Supabase。
- **代价**: API 联调前要补持久化实现。

### ADR-5: 桌级 WebSocket 广播，个人产物定向发送

- **决策**: 同一桌的已连接客户端共同接收 `message_committed`、`agent_action`、`table_state_changed` 与安全事件；`request_debug_state` 和包含个人卡的 `close_artifact_ready` 只返回请求者。
- **理由**: 多人对话必须共享现场状态，同时不能把某个参与者的个人卡泄露给其他人。
- **替代方案**: 只回传发送者，或把所有事件广播后由前端过滤。
- **代价**: 连接生命周期和断线清理需要由进程内路由管理；跨进程部署时需替换为共享消息总线。

### ADR-6: 显式 ASGI 入口与可选 JSON 持久化

- **决策**: `app.main:app` 作为部署入口；设置 `TABLE_REPOSITORY_PATH` 时使用原子 JSON 仓储，未设置时继续使用内存仓储，方便本地 Demo 与测试。
- **理由**: 开发者可以用同一入口启动后端，并能明确选择重启后是否保留桌状态。
- **替代方案**: 让部署命令直接导入内部 `app.api.app:app`，或默认写入工作目录。
- **代价**: JSON 仓储仍是单进程方案，生产多实例需要替换 repository 实现。

### ADR-7: 参与者资料默认半公开，按连接做投影

- **决策**: `declared_position` 与 `relevant_experience` 默认只对本人可见；参与者通过自己的 REST/WS 身份显式同意后，才向同桌公开。撤回同意立即恢复隐藏。消息正文和由现场消息产生的证据仍属于桌面公共内容。
- **理由**: 产品文档要求先获得同意再暴露个人/职业信息，且个人卡不能泄露给其他参与者。
- **替代方案**: 创建桌时默认全部公开，或把完整内部状态交给前端自行过滤。
- **代价**: API/WS 必须按请求者生成状态投影；跨进程部署需把同意状态放入共享仓储。

### ADR-8: 匹配先预览再确认建桌

- **决策**: `POST /matches/preview` 只返回公开席位和证据理由；`POST /matches/confirm` 在服务端重新计算同一候选池并把选中席位写入新桌。匹配核心保持有界、确定性和可替换，暂不依赖知乎非官方接口。
- **理由**: 先让用户理解“为什么是这些人”，再进入对话；同时避免通过抓取或逆向 API 形成不可维护的外部依赖。
- **替代方案**: 直接随机建桌，或把模型/平台搜索结果未经校验写入桌状态。
- **代价**: 当前匹配使用候选池而不是全网召回；接入正式资料源时只需替换输入适配器。

### ADR-9: Close 是幂等状态迁移

- **决策**: 只有在能生成 evidence-backed close artifacts 后才把桌迁移为 `phase=close`/`conversation.closed=true`；重复 close 不增加版本；关闭后拒绝新的真人消息。
- **理由**: 结束桌面必须可恢复、可回放且不能在“没有证据”的空桌上误关闭。
- **替代方案**: 只返回一次性卡片，不写状态；或收到 close 请求立即锁桌。
- **代价**: 客户端需要处理 `table_closed` 错误和关闭后的最终状态事件。

### ADR-10: 主持动作独立审计日志

- **决策**: 每个真实的非 `SILENCE` 主持动作写入 `InterventionRecord`；记录包含路由 action、evidence、confidence、模型/耗时/Token 元数据和可选 outcome/reflection。日志与状态快照分离，支持单独查询和重启恢复。
- **理由**: Table State 只保留下一步黑板和最后动作，不能替代完整的可解释回放；`SILENCE` 没有可发送动作，也不生成伪审计记录。
- **替代方案**: 只在状态里覆盖保存最后一次动作，或把审计字段塞进前端事件。
- **代价**: JSON 快照格式增加可选 `interventions` 段；未来接数据库时需要独立事件表。

## 接口契约

### REST / WebSocket

```text
POST /tables
POST /matches/preview
POST /matches/confirm
GET  /tables/{id}
POST /tables/{id}/participants
GET  /tables/{id}/state
GET  /tables/{id}/replay
GET  /tables/{id}/interventions
POST /tables/{id}/close
WS   /ws/tables/{table_id}?participant_id={participant_id}
```

Client events: `human_message`, `participant_joined`, `participant_left`, `participant_consent`, `request_debug_state`。

Server events: `message_committed`, `agent_action`, `table_state_changed`, `grounding_card`, `close_started`, `close_artifact_ready`, `intervention_reflected`。

广播边界：同桌客户端共享公共事件；`request_debug_state` 与 `close_artifact_ready.personal_card` 仅发送给请求连接。
资料边界：状态投影默认隐藏其他参与者的 `declared_position` 和 `unused_relevant_experience`；只有本人显式同意后才公开。

### 数据模型 / 类型定义

```text
Phase = opening | explore | tension | deepen | close
Action = SILENCE | PASS | PROBE | REFRAME | GROUND | CLOSE
DisagreementType = fact_conflict | causal_disagreement | layer_mismatch |
                   definition_mismatch | value_conflict | experience_gap

TableState(table_id, version, core_question, current_subquestion, phase,
           momentum, close_readiness, insights<=8, consensus<=5,
           disagreements, open_loops<=3, participants, conversation,
           intervention)

AgentActionEvent(action, target_participant_id?, text?, visual_hint,
                 evidence_turns, state_version, confidence)
```

### LLM provider

```python
class LLMProvider(Protocol):
    async def structured(self, task, messages, schema, config): ...
    async def text(self, task, messages, config): ...
```

失败策略：结构化解析失败只重试一次；再次失败沿用上一版 state 并返回安全默认 `SILENCE`。Host 失败不发送半成品。

## 约束清单

- 禁触文件: `3D/` 原始资产、现有前端视觉实现；后端通过事件契约接入，不让前端理解内部推理。
- Diff 预算: 单个 diff 原则上不超过 300 行，必须可独立验证、提交与回滚。
- 状态边界: `open_loops<=3`、`new_insights<=8`、`consensus<=5`；重要判断必须有 evidence turns。
- 主持边界: 默认 1-3 句、通常不超过 120 个中文字符；禁用“检测到/根据分析/作为AI”等系统腔。
- 安全边界: safety check 高于 Gate；来源不确定时不得 GROUND。
- 兼容边界: Python 3.11+、Pydantic v2；前端 `AgentAction` 枚举保持完全一致。

---

## Stacked Diff 拓扑（可变区）

```text
master
  ←── D01 domain contracts + validation
        ←── D02 demo seeds + deterministic Observer/CLI
              ←── D03 Gate + Router golden cases
                    ←── D03.1 decision-loop integration + cooldown writeback
                          ←── D04 Host generator
                                ←── D05 Reflection + Close
                                            ←── D06 FastAPI + WebSocket + replay
                                                  ←── D07 persistence + integration QA
                                                        ←── D08 provider adapter + fail-closed calls
                                                              ←── D11 runtime entrypoint + configurable persistence
```

## Progress Ledger

| Diff | Status | Output | Verification | Commit |
|---|---|---|---|---|
| Design confirmation | complete | DOCX execution SPEC v1.0 + repository execution plan | Source reviewed in full | `7c7f82c` |
| D01 domain contracts | complete | Pydantic enums, Table State, intervention/artifact contracts | 17 schema tests + compileall + JSON Schema audit | `ee5f045` |
| D02 Observer/CLI | complete | 5 role seeds, 3 scripted dialogues, immutable state update and JSON replay | 34 tests + compileall + 3 CLI replays | `d5a59e6` |
| D03 Gate/Router | complete | explainable silence-first Gate + independent six-action Router | 26 golden cases, 100% accuracy; 71 total tests | `90e3fce` |
| D03.1 loop integration | complete | Gate→Router seam, intervention writeback/cooldown, routed CLI, reachable PASS | 80 tests + 4 CLI replays | `49663d8` |
| D04 Host | complete | six action-specific natural Chinese host events, visual hints and safe fallbacks | 104 tests + compileall; naturalness/contract checkpoint | `7bf7b9e` |
| D05 Reflection/Close | complete | deterministic effect log with post-intervention evidence attribution; close-readiness refresh; Q0→Q1 shared baseline; personal cards; commitment/suggestion extraction | 123 tests + compileall + diff review; explicit stale-turn regression | `a00df65` |
| D06 API/WS | complete | FastAPI REST table lifecycle, immutable in-memory replay (`messages + snapshots`), structured WebSocket message/join/leave/debug events, Host action delivery and cooldown writeback | 132 tests + compileall + REST/WS contract review | `c1cb020` + `dcc4d89` |
| D06c realtime artifacts | complete | WebSocket close lifecycle (`close_started`/`close_artifact_ready`) and server-only trusted grounding-card delivery | 147 tests + compileall + privacy/source-boundary review | `1d0e37e` |
| D07a safety boundary | complete | pre-loop deterministic SafetyDecision/Enforcement; CRITICAL pause/intercept snapshot; Host/record hard stop | 138 tests + compileall + safety bypass review | `f6ead4d` |
| D07b persistence/QA | complete | atomic JSON snapshot repository with strict load validation, restart recovery and safety-only snapshots; deterministic replay QA | 142 tests + compileall + 10 persisted flagship runs | `e0f554d` |
| D08 provider adapter | complete | vendor-neutral `LLMProvider` protocol; Pydantic-validated structured calls with one repair retry; typed previous-state/fallback path; Host text never emits empty or half-built output | 152 tests + compileall + diff check | `7f52a6a` |
| D09 grounding persistence | complete | JSON snapshots persist trusted grounding cards, consume them atomically, and load legacy files without the optional card section | 154 tests + compileall + diff check | `c4e66db` |
| D10 table WebSocket fanout | complete | table-scoped connection registry; public message/action/state/safety/close-start events fan out to peers; debug state and personal close cards remain requester-only; disconnect cleanup | 155 tests + compileall + diff check | `99d8bcc` |
| D11 runtime entrypoint | complete | `app.main:app` ASGI entrypoint; `TABLE_REPOSITORY_PATH` selects restart-safe JSON repository while default remains in-memory | 155 tests + compileall + import smoke check | `b0da261` |
| D12 REST privacy projection | complete | participant profile fields default to redacted; owner view, explicit consent/revocation endpoint, and replay projections preserve public evidence while hiding private profile data | 156 tests + compileall + diff check | `195f4bc` |
| D13 WebSocket consent projection | complete | connection-scoped viewer identity; consent event is self-scoped; public consent change broadcasts while each state event is independently redacted | 157 tests + compileall + privacy regression | `a52f228` |
| D14 matching core | complete | bounded deterministic candidate selection with role diversity, question-term evidence, stable output, and public-only seat/reason contracts | 160 tests + compileall + diff check | `ad0de75` |
| D15 matching REST preview | complete | `POST /matches/preview` exposes selected public seats and reasons without private profile fields | 161 tests + compileall + API contract check | `ad0de75` |
| D16 matching confirmation | complete | `POST /matches/confirm` recomputes and commits the selected seats into a new table while returning the public match plan and redacted initial state | 162 tests + compileall + API contract check | `4d4e49a` |
| D17 close state migration | complete | evidence-backed close marks table closed and rejects later human messages; repeated close is idempotent | 162 tests + compileall + close regression | `f5a09de` |
| D18 intervention audit log | complete | non-SILENCE Host actions are persisted with evidence/confidence/metadata; JSON restart recovery and `GET /tables/{id}/interventions` query are covered; SILENCE creates no record | 163 tests + compileall + audit persistence regression | `5b942c7` |
| D19 reflection writeback | complete | after two post-intervention human turns, deterministic ReflectionResult is attached to the audit record and broadcast as `intervention_reflected` | 164 tests + compileall + reflection regression | `ba110cb` |
| D20 match explanation privacy | complete | private position/experience may influence selection internally but public match reasons expose only role-derived terms; regression checks no private text leaks | 164 tests + compileall + redaction regression | `81e6539` |
| D21 optional OpenAI provider | complete | lazy-loaded `AsyncOpenAI.responses` adapter for structured/text calls, environment configuration, explicit missing-key failure, and optional dependency isolation | 167 tests + compileall + diff check | `fc3e326` |
| D22 runtime integration probes | complete | configurable Vite-friendly CORS plus `/healthz` and `/readyz` probes without exposing table data | 169 tests + compileall + diff check | `cf67435` |
| D23 REST consent identity boundary | complete | REST profile consent now requires explicit `viewer_id` matching the participant path, aligned with WebSocket self-scoping | 170 tests + privacy regression | `27342f9` |
| D24 repository write serialization | complete | re-entrant process lock covers in-memory and JSON compound reads/writes; competing consent updates retain both changes and ordered versions | 171 tests + compileall + diff check | `6794029` |
| D25 atomic intervention audit | complete | WebSocket host state and its non-SILENCE audit record commit as one repository bundle; invalid audit leaves the prior snapshot untouched | 173 tests + compileall + diff check | `16a03a0` |
| D26 WebSocket identity handshake | complete | unknown `participant_id` is rejected before registration or state delivery with a structured error and close code 1008 | 173 tests + compileall + diff check | `4cc808e` |

## 已知坑位（Running Gotchas）

- 当前前端展示题目是“为什么我们越来越不会休息？”，后端旗舰评测题目是“AI Agent 真正进入企业，卡住的是技术还是采购？”；在 API 联调前需明确采用双 demo table 还是统一题目。
- 本机系统 Python 为 3.14；项目必须声明 3.11+ 兼容范围，避免无意使用 3.14 专属语法。
- API 接入前必须增加独立的 pre-loop SafetyDecision/Enforcement；critical hard violation 不能只依赖主持 Router 的 REFRAME，需能表达暂停、拦截或移出。
