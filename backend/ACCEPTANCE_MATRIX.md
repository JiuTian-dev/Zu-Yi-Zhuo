# 组一桌后端产品验收矩阵

这份矩阵把《知乎赛道一完整产品沉淀文档 v1.3》的后端相关目标，映射到当前可调用的契约、实现位置和回归证据。它只描述后端，不把前端视觉稿当作后端完成证明。

## 主链路

| 产品目标 | 后端契约 | 实现与证据 |
|---|---|---|
| 从公开知乎信号发现值得发生的问题 | `POST /opportunities/preview`、`POST /opportunities/source-preview` | `backend/app/opportunities/`、`backend/app/sources/`；`tests/test_opportunities.py`、`tests/test_content_source.py` |
| 用户主动说出“我想围绕什么聊” | `POST /intents/preview` | `backend/app/intake.py`；`tests/test_intake.py`；支持 `clarify`、`join_existing`、`new_table` |
| 首页一次加载公开桌卡 | `GET /tables/discovery?limit=...` | `backend/app/lobby.py`、`backend/app/api/app.py`；`tests/test_lobby.py`；默认最多 20 张开放桌 |
| 评委/联调可重复验证三桌主链路 | `python -m app.cli.seed_demo --path ...` | `backend/app/demo/bootstrap.py`、`backend/app/cli/seed_demo.py`；`tests/test_demo_seed.py`；幂等且不覆盖已有实时状态 |
| 先解释为什么匹配，再确认建桌 | `POST /matches/preview` → `POST /matches/confirm` | `backend/app/matching/`；`tests/test_matching.py`、`tests/test_candidate_preview.py` |
| 4 人可开桌、5 席硬上限、邀请先于入席 | `/tables/{id}/invitations`、`/tables/{id}/join-requests` 及接受接口 | `backend/app/api/repository.py`、`backend/app/api/app.py`；`tests/test_join_requests.py`、`tests/test_api.py` |
| 入席前回答“谁在里面 / 聊到哪 / 为什么缺我” | `GET /tables/{id}/lobby`、`POST /tables/{id}/lobby-fit` | `backend/app/lobby.py`；`tests/test_lobby.py`；公开成员摘要与角色缺口均有界 |

## 桌内对话与 Agent

| 产品目标 | 后端契约 | 实现与证据 |
|---|---|---|
| 真人消息驱动 evidence-first Table State | `WS /ws/tables/{id}`、`GET /tables/{id}/state`、`GET /tables/{id}/replay` | `backend/app/orchestrator/`、`backend/app/api/websocket.py`；`tests/test_websocket.py`、`tests/test_observer_websocket.py` |
| Agent 固定为圆桌搭档，不占真人席位 | `TableState.agent` 生命周期字段 | `backend/app/domain/schemas.py`、`backend/app/api/repository.py`；`tests/test_agent_presence.py` |
| 默认沉默、六动作、可解释证据与主持审计 | `SILENCE / PASS / PROBE / REFRAME / GROUND / CLOSE`、`GET /tables/{id}/interventions` | `backend/app/orchestrator/gate.py`、`router.py`、`host.py`；`tests/test_gate_router.py`、`tests/test_host.py` |
| Provider 可替换但不能越权改决策 | `CONVERSATION_PROVIDER` 与 `LLMProvider` | `backend/app/providers/`；`tests/test_providers.py`、`tests/test_openai_provider.py` |
| 异步默认，满足条件后显式升级同步 | `/tables/{id}/sync/preview` → `/tables/{id}/sync/upgrade` | `backend/app/orchestrator/mode.py`；`tests/test_mode.py` |
| 冷启动递话、安全暂停和实时广播 | `POST /tables/{id}/nudge`、WS `request_nudge`、安全事件 | `backend/app/api/nudge.py`、`backend/app/api/websocket.py`；`tests/test_websocket.py`、`tests/test_safety.py` |

## 收桌与问题飞轮

| 产品目标 | 后端契约 | 实现与证据 |
|---|---|---|
| 收桌时生成共同基线与个人回响卡 | `POST /tables/{id}/close`、`GET /tables/{id}/close-artifacts` | `backend/app/orchestrator/close.py`；`tests/test_reflection_close.py`、`tests/test_journey_smoke.py` |
| 行动项可在现实发生后回报结果 | `/tables/{id}/follow-ups` 读写接口 | `backend/app/api/repository.py`；`tests/test_api.py`、`tests/test_action_echoes.py` |
| 认知、关系、行动、情绪四维价值反馈 | `/tables/{id}/feedback` | `backend/app/domain/schemas.py`、`backend/app/api/app.py`；`tests/test_feedback.py` |
| 问题进化到下一桌、保留来源谱系 | `/tables/{id}/recompose`、`/tables/{id}/lineage`、问题足迹 | `backend/app/api/repository.py`；`tests/test_recompose.py`、`tests/test_question_footprint.py` |
| 再遇到旧桌友时给出证据提醒 | `GET /participants/{id}/relationship-memory` | `backend/app/api/app.py`；`tests/test_api.py` |
| 记录选择、行动、关系保存等产品行为且可清除 | `/participants/{id}/behavior-events` | `backend/app/api/repository.py`；`tests/test_behavior_events.py` |

## 隐私、安全与运行边界

| 产品/工程约束 | 后端保证 | 证据 |
|---|---|---|
| 半公开资料，未同意不展示立场与经历 | viewer-scoped REST/WS 投影，个人卡定向返回 | `backend/app/api/privacy.py`、`backend/app/api/websocket.py`；`tests/test_identity.py`、`tests/test_privileged_identity.py` |
| 不匹配、邀请偏好和离桌权利由服务端执行 | 对称 no-match、`many/few/none`、原子离桌 | `backend/app/api/repository.py`；`tests/test_no_match.py`、`tests/test_api.py` |
| 举报只给本人或受控审核器，不能广播 | moderator resolver、状态迁移审计、分页队列 | `backend/app/api/app.py`；`tests/test_safety_reports.py`、`tests/test_safety_resolution.py` |
| 重启后仍可恢复桌面与公开来源 | 原子 JSON snapshot repository，旧快照兼容 | `backend/app/api/repository.py`、`backend/app/main.py`；`tests/test_persistence.py` |
| 外部 source 失败时 fail-closed | 无 shell 命令桥、全链路超时、输出上限和通用错误 | `backend/app/sources/`；`tests/test_source.py`、`tests/test_content_source.py` |
| 前端可判断运行能力，不探测业务接口 | `GET /capabilities`、`/healthz`、`/readyz` | `backend/app/api/app.py`；`tests/test_api.py`、`tests/test_main.py` |
| REST/WS 写入可控，避免重复和资源滥用 | message 幂等、WS 帧/事件限额、REST mutation rate limit | `backend/app/api/rate_limit.py`、`websocket.py`；`tests/test_rate_limit.py`、`tests/test_websocket.py` |

## 当前验证基线

在 `D:\知乎黑客松\backend` 执行：

```powershell
python -m pytest -q
python -m compileall -q app tests
git diff --check
```

当前基线为 **398 passed**。最近一个后端功能切片是 D116（幂等三桌 Demo 种子）；对应实现提交为 `f1824f7`、`92cde69`、`012b10a`，账本提交待本轮回写。

## 不把以下事项误报为已完成

- 正式知乎 CLI/MCP/OAuth 凭证和 source 由部署方注入；仓库提供的是规范化适配器和 fail-closed 边界，不伪造授权数据。
- 多实例消息总线、数据库事务和共享限流器尚未纳入比赛版单进程目标。
- 本文不验收前端视觉、3D 资产、动画或浏览器部署；这些属于另一个 agent 的工作区内容。
