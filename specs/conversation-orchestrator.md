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

## 接口契约

### REST / WebSocket

```text
POST /tables
GET  /tables/{id}
POST /tables/{id}/participants
GET  /tables/{id}/state
GET  /tables/{id}/replay
POST /tables/{id}/close
WS   /ws/tables/{table_id}?participant_id={participant_id}
```

Client events: `human_message`, `participant_joined`, `participant_left`, `request_debug_state`。

Server events: `message_committed`, `agent_action`, `table_state_changed`, `grounding_card`, `close_started`, `close_artifact_ready`。

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

## 已知坑位（Running Gotchas）

- 当前前端展示题目是“为什么我们越来越不会休息？”，后端旗舰评测题目是“AI Agent 真正进入企业，卡住的是技术还是采购？”；在 API 联调前需明确采用双 demo table 还是统一题目。
- 本机系统 Python 为 3.14；项目必须声明 3.11+ 兼容范围，避免无意使用 3.14 专属语法。
- API 接入前必须增加独立的 pre-loop SafetyDecision/Enforcement；critical hard violation 不能只依赖主持 Router 的 REFRAME，需能表达暂停、拦截或移出。
