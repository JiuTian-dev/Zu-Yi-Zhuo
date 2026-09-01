# 组一桌后端产品验收矩阵

这份矩阵把《知乎赛道一完整产品沉淀文档 v1.3》的后端相关目标，映射到当前可调用的契约、实现位置和回归证据。它只描述后端，不把前端视觉稿当作后端完成证明。

## 主链路

| 产品目标 | 后端契约 | 实现与证据 |
|---|---|---|
| 从公开知乎信号发现值得发生的问题 | `POST /opportunities/preview`、`POST /opportunities/source-preview` | `backend/app/opportunities/`、`backend/app/sources/`；`tests/test_opportunities.py`、`tests/test_content_source.py` |
| 一键验证公开机会发现首入口 | `python -m app.cli.opportunity_demo` | `backend/app/demo/public_signals.py`、`backend/app/cli/opportunity_demo.py`；`tests/test_opportunity_demo.py`；只读、确定性、无网络 |
| 一条命令验证公开机会到收桌后回响 | `python -m app.cli.journey_demo` | `backend/app/demo/journey.py`、`backend/app/cli/journey_demo.py`；`tests/test_journey_demo.py`；公开机会→4 人匹配→动态第 5 席邀请/入席→REST/WS→行动回报/反馈→确定性 JSON |
| 一键验证授权 source 驱动的 GROUND 闭环 | `python -m app.cli.grounding_demo` | `backend/app/demo/grounding.py`、`backend/app/cli/grounding_demo.py`；`tests/test_grounding_demo.py`；真实 REST/WS→事实冲突→GROUND→来源卡消费→replay，隔离内存且可重复 |
| 用户主动说出“我想围绕什么聊” | `POST /intents/preview` | `backend/app/intake.py`；`tests/test_intake.py`；支持 `clarify`、`join_existing`、`new_table` |
| 首页一次加载公开桌卡 | `GET /tables/discovery?limit=...`；同步桌透传 `sync_expires_at` | `backend/app/lobby.py`、`backend/app/api/app.py`；`tests/test_lobby.py`；默认最多 20 张开放桌 |
| 后续选桌随本人真实行为变聪明且可解释、可重置 | `GET /participants/{id}/table-recommendations`；`DELETE /participants/{id}/behavior-events` 立即恢复冷启动 | `backend/app/recommendations.py`、`backend/app/api/app.py`；`tests/test_table_recommendations.py`；弱信号按桌限权、过滤 no-match/不可入席桌、不返回原始消息或黑箱分数 |
| 静默旁听者可私下收藏并稍后回访 | `PUT/DELETE /participants/{id}/saved-tables/{table_id}`、`GET /participants/{id}/saved-tables` | `backend/app/api/repository.py`、`backend/app/api/app.py`；`tests/test_saved_tables.py`；本人作用域、幂等、最多 100 张、最近优先、JSON 原子恢复，不广播或自动训练推荐 |
| 评委/联调可重复验证三桌主链路 | `python -m app.cli.seed_demo --path ...` | `backend/app/demo/bootstrap.py`、`backend/app/cli/seed_demo.py`；`tests/test_demo_seed.py`；幂等且不覆盖已有实时状态 |
| 先解释为什么匹配，再确认建桌 | `POST /matches/preview` → `POST /matches/confirm`；授权 source 使用 `POST /matches/source-preview` → `POST /matches/source-confirm` 短期票据闭环 | `backend/app/matching/`、`backend/app/api/match_tickets.py`；`tests/test_matching.py`、`tests/test_candidate_preview.py`、`tests/test_source.py`；票据单次消费、过期与冲突重试，不重复调用 source |
| 4 人可开桌、5 席硬上限、邀请先于入席 | `/tables/{id}/invitations`、`/tables/{id}/join-requests` 及接受接口 | `backend/app/api/repository.py`、`backend/app/api/app.py`；`tests/test_join_requests.py`、`tests/test_api.py` |
| 用户无需预知桌 ID 即可发现并处理自己的邀请 | `GET /participants/{id}/invitations` 返回本人跨桌、可过滤分页的邀请收件箱；每项附公共 Lobby 上下文和服务端可响应状态 | `backend/app/api/app.py`、`backend/app/api/repository.py`；`tests/test_invitation_inbox.py`；身份错配、私有字段泄露、失效原因、接受闭环和 JSON 重启均有回归 |
| Agent 根据真实讨论判断“现在最缺谁” | `GET /tables/{id}/recruitment`；`candidate-preview.recruitment` | `backend/app/matching/engine.py`、`backend/app/api/app.py`；`tests/test_recruitment.py`；覆盖少于 4 人基线、4 人多说话者证据、角色已齐、满席/关闭/过期/安全暂停、身份隔离、无消息正文泄露和 JSON 重启 |
| 动态补位推荐可安全发邀请 | `POST /tables/{id}/candidate-preview` → `POST /tables/{id}/invitations/from-preview`；推荐票据绑定桌与邀请人，成功单次消费，冲突可重试 | `backend/app/api/match_tickets.py`、`backend/app/api/app.py`；`tests/test_candidate_preview.py`；候选接受后才新增席位，响应不含私有候选种子 |
| 入席前回答“谁在里面 / 聊到哪 / 为什么缺我” | `GET /tables/{id}/lobby`、`POST /tables/{id}/lobby-fit` | `backend/app/lobby.py`；`tests/test_lobby.py`；公开成员摘要与角色缺口均有界 |

## 桌内对话与 Agent

| 产品目标 | 后端契约 | 实现与证据 |
|---|---|---|
| 真人消息驱动 evidence-first Table State | `WS /ws/tables/{id}`、`GET /tables/{id}/state`、`GET /tables/{id}/replay` | `backend/app/orchestrator/`、`backend/app/api/websocket.py`；`tests/test_websocket.py`、`tests/test_observer_websocket.py` |
| Agent 固定为圆桌搭档，不占真人席位 | `TableState.agent` 生命周期字段 | `backend/app/domain/schemas.py`、`backend/app/api/repository.py`；`tests/test_agent_presence.py` |
| 默认沉默、六动作、可解释证据与主持审计 | `SILENCE / PASS / PROBE / REFRAME / GROUND / CLOSE`、`GET /tables/{id}/interventions` | `backend/app/orchestrator/gate.py`、`router.py`、`host.py`；`tests/test_gate_router.py`、`tests/test_host.py` |
| 内测可调优的主持节奏指标 | `GET /tables/{id}/evaluation` 返回每真人轮次介入率、有效介入率和五阶段介入计数；指标由现有真人 turn、状态快照和干预账本派生，成员可读且不返回主持推理正文 | `backend/app/domain/schemas.py`、`backend/app/api/app.py`、`backend/app/api/websocket.py`；`tests/test_evaluation.py`、`tests/test_websocket.py` |
| GROUND 可从授权公开 source 获取可信资料并可回放 | `POST /tables/{id}/grounding` 暂存一条带 `signal_id` 的 `GroundingCard`；Observer 对同一窄事实主题的明确相反断言自动生成 `FACT_CONFLICT`，后续 WS `GROUND` 只读 peek，最终由仓储原子消费、广播，并把已消费卡写入 `interventions[].grounding_card`；无卡时 Host 回退 `PROBE` | `backend/app/orchestrator/observer.py`、`backend/app/api/app.py`、`backend/app/api/repository.py`、`backend/app/api/websocket.py`；`tests/test_observer.py`、`tests/test_content_source.py`、`tests/test_websocket.py`、`tests/test_persistence.py`；客户端不能提交或伪造 disagreement/trusted card |
| Provider 可替换但不能越权改决策 | `CONVERSATION_PROVIDER` 与 `LLMProvider` | `backend/app/providers/`；`tests/test_providers.py`、`tests/test_openai_provider.py` |
| 异步默认，满足条件后显式升级限时同步 | `/tables/{id}/sync/preview` → `/tables/{id}/sync/upgrade`；`ConversationState.sync_expires_at` 到期自动回异步 | `backend/app/orchestrator/mode.py`、`backend/app/api/repository.py`、`backend/app/api/websocket.py`；`tests/test_mode.py`、`tests/test_api.py`、`tests/test_rest_fanout.py`、`tests/test_persistence.py` |
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
| 不匹配、邀请偏好和离桌权利由服务端执行 | 对称 no-match；账号级 `many/few/none` 覆盖旧 source/request 值并约束未来主动触达；当前桌偏好与历史席位互不改写；原子离桌 | `backend/app/api/repository.py`、`backend/app/api/app.py`；`tests/test_account_invitation_preference.py`、`tests/test_no_match.py`、`tests/test_api.py` |
| 举报只给本人或受控审核器，不能广播 | moderator resolver、状态迁移审计、分页队列 | `backend/app/api/app.py`；`tests/test_safety_reports.py`、`tests/test_safety_resolution.py` |
| 安全按风险逐级处理，不误伤正常分歧 | 气氛升温 `safety_soft_intervention`、首次边界 `safety_private_reminder`、重复边界 critical 暂停；strike 计数私有且可重启恢复 | `backend/app/orchestrator/safety.py`、`backend/app/api/repository.py`、`backend/app/api/websocket.py`；`tests/test_safety.py`、`tests/test_websocket.py`、`tests/test_comment_promotion.py`、`tests/test_persistence.py` |
| 重启后仍可恢复桌面与公开来源 | 原子 JSON snapshot repository，旧快照兼容 | `backend/app/api/repository.py`、`backend/app/main.py`；`tests/test_persistence.py` |
| 外部 source 失败时 fail-closed | 无 shell 命令桥、全链路超时、输出上限和通用错误 | `backend/app/sources/`；`tests/test_source.py`、`tests/test_content_source.py` |
| 前端可判断运行能力，不探测业务接口 | `GET /capabilities`、`/healthz`、`/readyz` | `backend/app/api/app.py`；`tests/test_api.py`、`tests/test_main.py` |
| REST/WS 写入可控，避免重复和资源滥用 | message 幂等、WS 帧/事件限额、REST mutation rate limit、状态广播版本单调、source 匹配票据有界且单次消费 | `backend/app/api/rate_limit.py`、`websocket.py`、`match_tickets.py`；`tests/test_rate_limit.py`、`tests/test_websocket.py`、`tests/test_source.py` |

## 当前验证基线

在 `D:\知乎黑客松\backend` 执行：

```powershell
python -m pytest -q
python -m compileall -q app tests
git diff --check
```

当前基线为 **470 passed**。最近一个后端功能切片是 D139（静默旁听者的私有收藏与回访）；实现提交为 `3f64c9c`，设计提交为 `a49ad58`。上一切片 D138（可解释、可重置的个性化后续选桌）为 `463 passed`，实现提交 `9ebeeee`，设计提交 `a3aba9c`。

## 不把以下事项误报为已完成

- 正式知乎 CLI/MCP/OAuth 凭证和 source 由部署方注入；仓库提供的是规范化适配器和 fail-closed 边界，不伪造授权数据。
- 多实例消息总线、数据库事务和共享限流器尚未纳入比赛版单进程目标。
- 本文不验收前端视觉、3D 资产、动画或浏览器部署；这些属于另一个 agent 的工作区内容。
