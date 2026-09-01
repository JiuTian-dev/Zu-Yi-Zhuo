# 组一桌 Conversation Orchestrator 后端

这是单桌闭环的 FastAPI 后端：真人消息进入后，系统维护 evidence-first Table State，经过安全检查、silence-first Gate、六动作 Router 和 Host，写入可回放的状态快照与 InterventionRecord。每张桌还公开携带固定的“圆桌 Agent”角色；它不占真人席位，但会随安全暂停、软过期和收桌进入对应生命周期。

产品目标与后端契约的逐项对齐见 [ACCEPTANCE_MATRIX.md](D:/知乎黑客松/backend/ACCEPTANCE_MATRIX.md)。

## 本地运行

```powershell
cd D:\知乎黑客松\backend
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload
```

需要一份可重复的三桌评委/联调数据时，可执行幂等种子命令；已有同 ID 桌不会被覆盖：

```powershell
python -m app.cli.seed_demo --path D:\知乎黑客松\runtime\demo-tables.json
```

验证第一入口“公开信号 → 未完成性 → 候选种子”时，可运行只读机会预览：

```powershell
python -m app.cli.opportunity_demo
```

该命令只输出标准 JSON，不写入仓储、不联网，内置信号明确标记为 `public`。

验证一条真正穿过 REST、WebSocket、收桌产物、评估和回放的完整后端旅程时，可运行隔离的内存演示：

```powershell
python -m app.cli.journey_demo
```

该命令每次从空内存仓储开始，依次走过公开机会预览、4 人匹配建桌、动态第 5 席候选预览与票据邀请、候选接受入席、Lobby、真人消息、Agent 动作、收桌卡片、行动回报、四维反馈、评估指标和回放摘要；不会读取或写入 `TABLE_REPOSITORY_PATH`，也不会访问网络。

验证“相反事实 → 授权 source → GROUND → replay”窄闭环时，可运行隔离演示：

```powershell
python -m app.cli.grounding_demo
```

该命令只使用内存仓储和确定性公开 source，通过真实 REST/WebSocket 契约触发 D132 事实冲突检测，输出有限 JSON；不会读取或写入 `TABLE_REPOSITORY_PATH`，也不会访问网络或前端资源。

启动后可用：

- `GET /healthz`：进程存活探针。
- `GET /capabilities`：公开当前运行能力开关（仓储、确定性/自定义 provider、三类 source 是否注入、WebSocket 和 5 席上限）；不返回命令、模型名、token 或身份配置。
- `GET /readyz`：仓储就绪探针。
- `GET /tables?participant_id=...&include_closed=false`：首页桌发现；默认只列出未关闭桌，并按 viewer 做隐私投影。
- `GET /tables/discovery?limit=...`：首页批量桌卡；默认最多 20 张仍开放且未软过期桌，复用有界公开 Lobby 投影（同步桌包含 `sync_expires_at`），不返回完整 `TableState`、消息或私有资料。
- `POST /opportunities/preview`：从已获授权的公开问题/回答/文章信号中提取核心问题、未完成性证据、角色缺口和候选种子；候选种子保留有界的公开 `public_signal_ids`，响应同时带最多 20 条 `source_signals` 公开证据，不创建桌。
- `POST /intents/preview`：接收用户主动提出的一段自然语言需求，返回 `clarify`、`join_existing` 或 `new_table` 路由和最多 5 个有空席的公开桌候选（含 `available_seats`、可选 `origin_signal_ids` 与内嵌的 Lobby 公开投影）；不读取个人 source、不自动建桌或入席。
- `POST /participants/{participant_id}/intent-sessions`、`GET/DELETE .../{session_id}`、`POST .../{session_id}/turns`：让用户在本人作用域内与 Agent 进行最多 6 轮、默认 15 分钟的主动需求澄清；响应带当前消息上下文、剩余轮次和同一份路由预览，支持 `replace_context=true` 原地纠正。会话只存在进程内，不写桌状态、行为账本或 JSON，不自动申请、邀请、入席或建桌。
- `POST /opportunities/source-preview`：调用服务端注入的公开内容 source 获取信号，再运行机会预览；不创建桌或邀请。
- `POST /tables/{table_id}/grounding?participant_id=...`：桌内成员从已授权公开内容 source 请求一条资料卡；服务端暂存为下一次 evidence-backed `GROUND` 的 trusted card，响应只返回公开标题、摘要、来源和稳定的 `signal_id`，不修改 Table State。无结果返回 404，source 故障统一 fail-closed。
- Observer 只会在两位成员围绕同一窄范围事实主题给出带明确相反极性（如“需要/不需要”）的真人断言时创建 `FACT_CONFLICT`；现有 Router 随后进入 `GROUND`，无 trusted card 时 Host 回退 `PROBE`，不接受客户端提交的 disagreement 或来源。
- `POST /personal-context/source-preview?viewer_id=...`：调用服务端注入的用户授权个人 source，生成本人可见的兴趣/表达主题预览；不创建桌、不广播、不落盘。
- `PUT/GET/DELETE /participants/{participant_id}/personal-context/consent?viewer_id=...`：本人授予、查看或撤回个人层 scope（`profile`、`follows`、`favorites`、`public_content`）。
- `POST /matches/preview` → `POST /matches/confirm`：先预览公开席位和理由；来自机会预览的理由会附带 `evidence_signal_ids`，确认时可把公开 `signal_ids` 作为 `origin_signal_ids` 写入桌状态。
- `POST /matches/source-preview` → `POST /matches/source-confirm`：调用服务端注入的候选 source（知乎 CLI/MCP/OAuth 适配器）后复用同一匹配预览契约；预览只返回短期不透明 `preview_token`，确认由服务端复用已授权候选建桌，不把私有候选字段交给浏览器，也不会二次调用 source。票据默认 5 分钟、单次消费；过期、重复使用或无效票据返回 409。
- `GET /tables/{table_id}/lobby`：入席前的公开 Lobby 读模型，集中返回谁在里面、当前聊到哪、空席/角色缺口和公共来源 ID；同步围炉时还会带 `sync_expires_at` 供首页倒计时，不返回消息、私有资料、邀请队列或个人卡。
- `POST /tables/{table_id}/lobby-fit?participant_id=...`：候选人用自己的 `ParticipantSeed` 获取角色缺口级别的“为什么想到你”解释；这是用户主动发起的只读预览，不保存资料、不创建申请或邀请。账号选择不接收主动邀桌时仍可查看；no-match、满桌和已结束桌返回 `eligible=false`。
- `POST /tables/{table_id}/invitations?inviter_id=...`：由桌内成员邀请候选人；候选资料的私有字段不会出现在响应。
- `GET /participants/{participant_id}/invitations?viewer_id=...&status=...&offset=...&limit=...`：本人一次读取跨桌邀请收件箱；pending 优先并稳定排序，支持状态过滤和有界分页。每项复用公开 Lobby 桌卡，并由服务端给出 `can_respond` 及桌已关闭、软过期、满席、已处理或后来命中 no-match 等失效原因；不返回候选私有种子、消息或个人卡。
- `GET /tables/{table_id}/invitations?participant_id=...`：候选人查看自己的邀请。
- `POST /tables/{table_id}/invitations/{invitation_id}/respond?participant_id=...`：候选人接受或拒绝；接受才新增席位。
- `POST /tables/{table_id}/join-requests?participant_id=...`：候选人向已有桌表达加入意愿；请求会保留私有候选种子，但响应只返回展示名、角色和申请状态，不会直接新增席位。
- `GET /tables/{table_id}/join-requests?participant_id=...`：桌内成员查看脱敏申请队列，候选人只能查看自己的申请；`POST .../{request_id}/approve?participant_id=...` 由成员审核并生成现有邀请，候选人仍需通过邀请响应接口接受；`POST .../{request_id}/decline?participant_id=...` 拒绝申请。
- `GET/PUT /participants/{participant_id}/invitation-preference?viewer_id=...`：本人读取或保存跨桌账号级邀桌偏好；未设置返回 `few`。保存值优先于请求或授权 source 中可能过期的候选值，并约束未来匹配、动态推荐和新邀请；`none` 不撤回已有邀请/席位，也不阻断本人主动查看 Lobby 或提交 join request。
- `PUT /tables/{table_id}/participants/{participant_id}/invitation-preference?viewer_id=...`：本人更新当前桌席位的圆桌邀请偏好（`many`、`few`、`none`）；重复提交幂等，关闭/软过期桌拒绝写入。
- `POST /tables/{table_id}/sync/preview?participant_id=...` → `POST /tables/{table_id}/sync/upgrade?participant_id=...`：预览并执行从异步到同步的升级；成功状态带服务端 `sync_expires_at` 截止时间（默认 30 分钟），到期后首次 REST/列表/WS 访问会原子退回异步并广播 `table_mode_changed(reason=sync_window_expired)`。
- `POST /tables/{table_id}/soft-expire?participant_id=...`：主题或组合价值下降时软过期桌；桌从默认发现中隐藏，但历史和收桌路径保留。
- `POST /tables/{table_id}/participants/{participant_id}/leave?viewer_id=...`：参与者本人离桌；保留历史快照并立即停止该席位的后续写入。
- `GET /tables/{table_id}/recruitment?participant_id=...`：桌内成员查看当前是否应该补位。少于 4 人时建议补足基线；4 人桌只有在 high-priority 未决问题同时得到至少两位真人的 turn 证据、且仍缺通用信息角色时才返回 `live_role_gap`。满席、关闭、软过期和 critical 安全暂停均明确不建议补位；响应不含消息正文、成员身份或个人画像。
- `POST /tables/{table_id}/candidate-preview?participant_id=...` → `POST /tables/{table_id}/invitations/from-preview?inviter_id=...`：桌内成员主动请求候选 source；响应带同一份 `recruitment` 判断、角色缺口和含公开 `evidence_signal_ids` 的候选推荐，未给自定义 query 时用真人讨论派生的有界查询提示。每条推荐附短期不透明 `preview_token`，服务端用票据复用已授权候选创建 pending invitation，不把私有立场/经历交给浏览器。预览本身不修改桌状态、不创建邀请、不自动入席。
- `GET /tables/{table_id}/close-artifacts?participant_id=...`：收桌后重新取得共享基线和当前参与者的个人回响卡。
- `GET /tables/{table_id}/replay`：返回原始真人消息和状态快照，并附带公开的 `interventions`、`comments`、`comment_promotions` 账本和已保存的 `source_signals`；每条实际引用公开资料的 GROUND 干预还会在 `interventions[].grounding_card` 留下 `signal_id`、标题、摘要和来源引用，来源卡消费与状态/干预审计在仓储中一次提交，重连/重启时可直接恢复整桌叙事与来源链；生产注入 `identity_resolver` 后必须带当前成员 `participant_id`，本地无认证 Demo 才允许省略。
- `GET /tables/{table_id}/lineage`：沿 `origin_table_id` 返回最多 10 代、从最早祖先到当前桌的公开问题谱系；每代只含问题、版本、来源 ID 和公开来源快照，不返回成员或个人卡。
- `GET /tables/{table_id}/follow-ups?participant_id=...`：查询收桌底稿中的行动项及已回报结果。
- `POST /tables/{table_id}/follow-ups/{index}/outcome?participant_id=...`：回报行动结果；承诺只能由 owner 回报，结果会写入 JSON 快照，并原子沉淀一条本人可见的 `follow_up_outcome` 行为事件（只记录状态摘要）。
- `POST /tables/{table_id}/feedback?participant_id=...`：收桌后提交或更新认知、关系、行动、情绪四类 1–5 分价值反馈。
- `GET /tables/{table_id}/feedback?participant_id=...`：桌内成员查看匿名价值聚合；不返回他人的评分明细或备注。
- `GET /tables/{table_id}/evaluation?participant_id=...`：桌内成员查看当前单桌的隐私安全评估指标（真人轮次、主持介入/反思、每真人轮次介入率、有效介入率、按 opening/explore/tension/deepen/close 的介入分布、邀请接受率、外围评论/促成、行动回响和匿名价值反馈完成度）；只读派生，不返回个人评分、备注或行为事件明细。有效介入结果由服务端在反思账本中保留布尔标记，旧记录没有标记时仍可回放但不会冒充有效。
- `POST /tables/{table_id}/comments?author_id=...` / `GET /tables/{table_id}/comments`：外围评论独立账本；评论不占席位、不进入核心 turn。
- `GET /tables/{table_id}/comment-promotion-candidates?participant_id=...&limit=...`：桌内成员查看 Agent 从最近最多 100 条外围评论中筛出的安全候选；依据当前问题、明确问句和案例/经历线索给出自然语言理由，不返回分数、不累计安全 strike、不自动写入主桌。
- `POST /tables/{table_id}/comments/{comment_id}/promote?participant_id=...`：核心成员显式促成一条评论；服务端重新做安全检查，成功后以促成人身份写入主桌 turn，并保留 `source_comment_id` 和可回放的 `CommentPromotion`。
- `POST /participants/{participant_id}/no-match/{blocked_participant_id}?viewer_id=...`、`DELETE ...`、`GET /participants/{participant_id}/no-match?viewer_id=...`：本人管理“不再匹配”偏好；关系双向约束邀请和动态候选预览。
- `POST /tables/{table_id}/safety-reports?reporter_id=...` / `GET /tables/{table_id}/safety-reports?reporter_id=...`：桌内成员提交或查询自己的举报；举报正文不广播给同桌，账本供受控审核适配器读取。
- `GET /tables/{table_id}/safety-reports/moderation`：仅注入 `moderator_resolver` 的审核器可读取该桌私密举报队列；支持 `status` 筛选和 `offset`/`limit`（默认 100、最大 200）有界分页，未配置审核身份时返回 503，普通成员不能借此读取他人举报。
- `PATCH /tables/{table_id}/safety-reports/{report_id}`：审核器将举报状态单向推进为 `acknowledged` 或 `resolved`；可带 `reason`，重复当前状态幂等，已解决举报不可回退，状态更新不广播给桌内连接。
- `GET /tables/{table_id}/safety-reports/{report_id}/history`：审核器读取该举报的受信状态迁移链（审核器身份、原/目标状态和可选理由）；普通成员不可见，旧 JSON 快照按空链兼容加载。
- `POST /tables/{table_id}/safety/resolve` / `GET /tables/{table_id}/safety/resolutions`：仅对注入的 `moderator_resolver` 开放；可原子恢复 critical 暂停或移除一名成员，并读取不可变处置审计。未配置审核器时返回 503，不能用请求体自报 moderator。
- WebSocket 安全阶梯：正常分歧照常落账；窄词表识别到气氛升温时广播不含原文的 `safety_soft_intervention`，首次人身边界风险只向发送连接返回 `safety_private_reminder`，同一 actor 第二次才升级为 critical 暂停。私有 strike 计数随 JSON 重启恢复，不进入成员状态投影。
- `POST /tables/{table_id}/recompose?participant_id=...`：从已收桌的进化问题创建下一桌；参与者必须重新选择，不自动复制旧桌成员，并在新状态记录 `origin_table_id`。生产注入 `identity_resolver` 后要求由当前桌成员发起。
- `GET /participants/{participant_id}/relationship-memory?viewer_id=...`：本人查询已收桌中有证据的旧桌友提醒。
- `GET /participants/{participant_id}/question-footprint?viewer_id=...&limit=...`：本人查询有界的问题足迹，回顾已收桌中自己补上的视角、桌级认知变化，以及由 `origin_table_id` 直接长出的最多 3 张下一桌（仅公开桌 ID、问题、阶段和关闭标记）；不返回下一桌成员、消息或他人私密资料。
- `GET /participants/{participant_id}/action-echoes?viewer_id=...&limit=...`：本人查询跨已收桌的行动回响；只返回自己拥有的承诺或自己回报过的建议结果。
- `POST /tables/{table_id}/select?participant_id=...`：显式记录一次 open 桌选择；服务端生成稳定行为事件，不会自动入席或改变桌状态。
- `POST /tables/{table_id}/relationships/{related_participant_id}/save?participant_id=...`：收桌后由成员本人保存一段关系；服务端校验双方同桌身份并生成稳定事件，不复制个人卡或好友图。
- `POST/GET /participants/{participant_id}/behavior-events?viewer_id=...`：本人记录或读取受限的产品行为事件（选桌、收桌、关系保存、行动回响、价值反馈）；真人发言、收桌和首次价值反馈由后端自动沉淀，事件不广播给同桌。
- `GET /participants/{participant_id}/table-recommendations?viewer_id=...&limit=...`：本人拉取可解释的后续选桌建议；只使用最近最多 100 条可清除行为中的选桌、真人发言和正向行动回响，按桌/类型限制弱信号影响，并过滤关闭、软过期、满席、本人已入席和命中 no-match 的桌。响应只解释历史公开问题与角色缺口，不返回消息正文、事件编号或黑箱分数，也不会自动邀请或入席。
- `PUT/DELETE /participants/{participant_id}/saved-tables/{table_id}?viewer_id=...`、`GET /participants/{participant_id}/saved-tables?viewer_id=...&offset=...&limit=...`：本人私下收藏、取消和分页回看最多 100 张桌，按最近保存优先；关闭、软过期或满席桌仍可回看。收藏不广播、不改桌状态、不公开人数，也不会自动训练推荐或申请入席。
- `DELETE /participants/{participant_id}/behavior-events?viewer_id=...`：本人清除自己的行为账本；不删除消息、桌状态、收桌产物、安全审计或独立的收藏列表。

生产注入 `identity_resolver` 后，`POST /tables/{table_id}/participants?inviter_id=...`、`POST /tables/{table_id}/close?participant_id=...` 和 `GET /tables/{table_id}/interventions?participant_id=...` 也必须通过当前桌成员身份校验；未注入时保留本地 Demo 的无 query 调用。
- `WS /ws/tables/{table_id}?participant_id={participant_id}`：参与者实时收发消息、主持动作、状态和关闭产物；客户端可发送 `participant_invitation_preference` 更新本人当前席位偏好，服务端广播 `participant_invitation_preference_changed` 和最新投影状态。
- `WS /ws/tables/{table_id}?participant_id={viewer_id}&viewer_mode=observer`：只读旁听；立即收到公开状态和后续桌面事件，但不占席位、不写入消息或状态。
- `WS /ws/tables/{table_id}?participant_id={viewer_id}&viewer_mode=commenter`：外围评论连接；只接受 `peripheral_comment`，评论可由核心成员通过 REST 显式促成。
- 参与者 WebSocket 可发送 `request_nudge`：当首条真人表达暂未获得自然回应时，请求一次基于最近真人 turn 的轻量 `PROBE`；空桌、critical 暂停、软过期、收桌或两轮冷却内会返回结构化错误，递话会像普通主持动作一样广播并写入审计。
- `POST /tables/{table_id}/nudge?participant_id=...`：REST 调度同一份冷启动递话能力；与 WebSocket `request_nudge` 共用 evidence、生命周期、安全、冷却、Host 生成和审计写回规则，且只接受最近发言者的第一次表达。成功响应包含 `gate`、`route`、`action` 和按请求人投影的 `state`。

生产环境可设置 `WS_ALLOWED_ORIGINS` 为逗号分隔的完整 Origin 白名单（例如 `https://app.example.com`）。配置后 WebSocket 缺失或不匹配的 Origin 会在握手阶段以 1008 拒绝；`*` 不允许使用。未配置时保留本地 Demo 的兼容行为，`CORS_ORIGINS` 不会自动替代 WebSocket 白名单。

WebSocket 单个 JSON 文本帧默认最多 64 KiB，可用 `WS_MAX_FRAME_BYTES` 调整；超限连接以 1009 关闭。`human_message.text` 另限制为 4000 字符，超限只返回 `invalid_payload`，不会写入消息、状态或主持审计。

每条 WebSocket 连接默认每 60 秒最多接收 120 个事件，可用 `WS_MAX_EVENTS_PER_MINUTE` 调整。超限事件会在 JSON 解析和桌锁之前被丢弃，并返回 `rate_limited` 与 `retry_after_seconds`；连接保持可用，客户端应等待提示时间后再重试。

REST 的 `POST`、`PUT`、`PATCH`、`DELETE` 写请求默认按客户端地址每 60 秒最多 600 次，可用 `REST_MAX_MUTATIONS_PER_MINUTE` 或 `create_app(..., rest_max_mutations_per_minute=...)` 调整。超限返回 HTTP 429 和 `Retry-After`；`GET`、健康探针和 WebSocket 不计入此窗口。该限流器是单进程保护，多实例部署应在可信网关或共享限流器处统一执行。

通过 REST 完成补位、邀请接受、加入申请创建/审核/拒绝、同步升级、同意变更、邀请偏好更新、离桌、软过期、收桌或外围评论写入时，后端也会复用同一桌级 broadcaster：先发送对应语义事件（如 `participant_added`、`invitation_updated`、`join_request_created`、`join_request_approved`、`join_request_declined`、`participant_invitation_preference_changed`、`table_closed`）；只有桌状态真的迁移时，才会继续发送按 viewer 隐私投影的 `table_state_changed`。加入申请本身不改变桌状态，因此不会发送状态迁移。没有在线 WebSocket 时不影响 REST 成功；重复的幂等写入不会重复产生状态迁移事件。
REST 收桌还会在生成收桌底稿前发送 `close_started`；若证据不足而返回 409，只保留开始提示，不会写入 `closed` 状态或发送 `table_closed`。
同一桌的状态投影广播会在服务端串行发送，并丢弃低于最近已发送版本的过期投影；因此 REST/WS 并发写入不会让客户端回退到旧版 `TableState`。这只约束状态事件顺序，不改变仓储快照或消息事件契约。

默认开发态继续使用显式 `viewer_id`/`participant_id` 自证，方便本地 Demo。生产部署可在 `create_app(..., identity_resolver=...)` 注入同步身份解析器：解析器接收 FastAPI `Request` 或 WebSocket，返回已认证的内部主体 ID；所有自作用域 REST 写入/读取和参与者 WebSocket 握手都会校验主体一致性，缺失身份返回 401，不一致返回 403。解析器负责 JWT、会话、反向代理或 OAuth 校验，后端不保存知乎 token。

WebSocket `human_message.message_id` 是单桌幂等键：网络重试时，相同 ID 和内容会返回
`duplicate_message`，不会再次生成 turn、状态快照或主持动作；复用同一 ID 发送不同内容会被拒绝。评论促成同样按
`(table_id, comment_id)` 幂等，重复请求不生成新 turn/state。
安全检查仍在幂等提交前执行，因此未提交的危险消息不会占用消息 ID。

邀请状态为 `pending`、`accepted` 或 `declined`。同一候选人一旦被处理，不能再次收到同桌邀请；
拒绝不会改变桌状态，接受会把候选人和邀请状态作为一次持久化迁移写入 JSON 快照。

桌默认异步。同步升级请求需要 `wants_continue=true`、`sync_extra_value=true`，且至少两位成员已经有
高参与度证据；`discussion_quality`、`external_attention`、`public_value` 只会作为可解释加分信号。
同步围炉默认限时 30 分钟，可用 `SYNC_WINDOW_SECONDS` 或 `create_app(..., sync_window_seconds=...)` 调整；截止后服务端写入一个新的异步快照，不依赖前端倒计时或后台 scheduler。
真人桌最多 5 个席位，圆桌 Agent 作为独立的第六个公开角色不计入上限；少于 4 人的桌可以先建立并通过追加参与者或接受邀请逐步补齐，满桌后新入席会返回 409。

软过期是可回放的幂等状态迁移：请求需要桌内成员身份和非空原因，状态会记录 `soft_expiry_reason`。
软过期后拒绝新消息、成员变更、邀请、同步升级、主持/安全快照和来源卡片写入，WebSocket 返回
`table_soft_expired`；`GET /tables/{id}`、回放、行动回响和收桌仍可用，收桌后仍保留软过期标记。
收桌迁移在内存和 JSON 仓储中都原子持久化；带参与者身份的 REST/WS 收桌会把关闭状态与私有 `table_closed` 行为事件写进同一次仓储提交，重启后仍可读取关闭状态、收桌卡和行动回响，重复收桌不增加版本或重复事件。

候选资料可设置 `roundtable_invite_preference`：`many`、`few`（默认）或 `none`。账号级保存值会覆盖
请求或 source 中的旧值；选择 `none` 的候选人会在平台/他人主动发起的匹配、推荐和新邀请边界被跳过。
来源匹配确认还会重新检查预览后的偏好变化，避免用未过期票据绕过刚刚关闭的邀桌权限。

账号级偏好由本人 REST 接口写入独立持久账本，旧 JSON 快照按空账本兼容加载。已入席成员仍可通过 REST 或 WebSocket 调整当前桌席位偏好；该值只版本化写入当前 `TableState`，不反向覆盖账号值，也不会改写历史席位或撤回已发邀请。账号选择 `none` 后仍可主动查看 Lobby 适配度和申请加入，成员批准后由本人接受邀请才新增席位。

不再匹配偏好是参与者本人可写的全局关系账本，关系对两端对称生效；命中后服务端拒绝新邀请、过滤
动态候选预览，但不删除已有桌成员、历史消息或旧邀请。删除操作幂等，JSON 仓储会在重启后恢复。

默认使用内存仓储；设置 `TABLE_REPOSITORY_PATH` 后使用同目录原子 JSON 快照：

```powershell
$env:TABLE_REPOSITORY_PATH = "D:\知乎黑客松\runtime\tables.json"
python -m uvicorn app.main:app
```

候选 source 默认未配置。需要接入已获授权的 CLI/MCP/OAuth wrapper 时，可设置
`CANDIDATE_SOURCE_COMMAND` 为 JSON 字符串数组；后端会以无 shell 子进程方式调用它，stdin 输入
`{"query":"...","limit":20}`，stdout 返回候选数组或 `{"candidates":[...]}`。每个候选必须符合
`ParticipantSeed`，命令超时、非零退出、输出过大或字段不合法都会 fail-closed 为 502；注入式
source 即使返回惰性迭代器，API 也最多消费请求的 `limit` 条：

```powershell
$env:CANDIDATE_SOURCE_COMMAND = '["D:\\adapters\\zhihu-candidates.exe"]'
python -m uvicorn app.main:app
```

wrapper 自己负责知乎授权和 token 管理；不要把 secret、Cookie 或 MCP 配置交给浏览器或前端。

匹配预览票据默认保留 300 秒，可用 `SOURCE_MATCH_PREVIEW_TTL_SECONDS` 调整；票据只保存在当前进程内存中，
进程重启或多实例切换后不会继续有效。多实例部署需要在保持相同接口语义的前提下替换为共享、带 TTL 的票据存储。

机会发现可额外设置 `CONTENT_SIGNAL_SOURCE_COMMAND` 接入公开内容 CLI/MCP/OAuth wrapper。stdin 同样是
`{"query":"...","limit":20}`，stdout 返回信号数组或 `{"signals":[...]}`；每条信号必须符合
`ContentSignal`（`visibility` 必须为 `public`）。命令超时、非零退出、输出过大或信号不合法会 fail-closed 为 502，
未配置时 `/opportunities/source-preview` 返回 503：

```powershell
$env:CONTENT_SIGNAL_SOURCE_COMMAND = '["D:\adapters\zhihu-public-signals.exe"]'
python -m uvicorn app.main:app
```

个人授权层可额外设置 `PERSONAL_CONTEXT_SOURCE_COMMAND` 接入服务端 OAuth/CLI/MCP wrapper。stdin 为
`{"viewer_id":"...","scopes":["favorites"],"query":"...","limit":20}`，stdout 返回个人信号数组或 `{"signals":[...]}`；每条信号必须符合
`PersonalContextSignal` 且 `owner_id` 必须等于请求 viewer。后端不会接收或打印 access token，也不会把个人信号写入桌状态：

```powershell
$env:PERSONAL_CONTEXT_SOURCE_COMMAND = '["D:\\adapters\\zhihu-personal-context.exe"]'
python -m uvicorn app.main:app
```

个人 source 预览必须先有本人已授予且覆盖请求 scope 的 consent；撤回后立即返回 403。source 超时、退出失败、输出过大、JSON 不合法或 owner 不匹配时统一 fail-closed 为 502；未配置时返回 503。

三类 source 入口（候选、公开内容、个人上下文）都会在服务端先限制结果消费数量，再进行逐条 schema 校验；不会先把适配器的完整返回值读入内存后再切片。

动态补位判断由现有席位、公开角色缺口和真人讨论账本只读派生，不写第二份状态：4 人桌需要至少两条、两位不同发言者支持同一 high-priority open loop 才会建议补位。候选预览会过滤现有参与者、已被邀请过的候选人以及明确选择 `none` 的候选人；返回的 `recruitment`、`open_seats`、`role_gaps` 和候选理由（含可选公开 `evidence_signal_ids`）只用于成员选择，仍需通过现有邀请接口逐个发出邀请，候选人接受后才会新增席位。

机会预览只接受公开 source signal（问题/回答/文章标题、摘要、公开作者角色和公开立场），信号数量最多 20、
至少覆盖 2 位作者。输出的 `signal_ids` 和 `unfinishedness` 可回溯到原始来源；候选人仍需经过
`/matches/preview` 的席位与邀请偏好校验后才能建桌。确认匹配或直接建桌时可选持久化最多 20 个公开
`origin_signal_ids`，并可在同一请求中提交对应的 `origin_signals` 公共快照；回放和 JSON 重启会保留
这些 ID 与快照。快照位于独立的公开来源账本，不进入 `TableState`，且桌状态不会保存来源标题、摘要、私有立场或 token。
机会预览响应中的 `source_signals` 是本次请求的公开安全投影（含 `title`、`excerpt`、`source_ref`、公开作者信息和互动量），
同样受 `ContentSignal` 字段长度与 20 条上限约束；`GET /tables/{table_id}/replay` 会在存在快照时返回
`source_signals`，没有快照的旧 ID-only 桌仍只返回 `origin_signal_ids`。

Vite 开发源默认允许 `http://localhost:5173` 和 `http://127.0.0.1:5173`，可用逗号分隔的 `CORS_ORIGINS` 覆盖。

## 可选模型 provider

默认演示不调用外部模型，`CONVERSATION_PROVIDER` 未设置或为 `deterministic` 时不产生外部请求。
需要接入 OpenAI Responses 时安装可选依赖并设置运行时变量：

```powershell
python -m pip install -e ".[openai]"
$env:CONVERSATION_PROVIDER = "openai"
$env:OPENAI_API_KEY = "..."
$env:OPENAI_MODEL = "gpt-4o-mini"
```

provider 只改写确定性 Host 已经生成的 PASS/PROBE/REFRAME/CLOSE 文案；Gate、Safety、Router、状态证据、目标人和 GROUND 来源不交给模型决定。
模型只收到公开问题、当前子问题和确定性草稿，不会收到完整 Table State 或未同意的个人资料。输出为空、超出 120 字、包含系统腔/来源声称/链接或调用失败时自动回退到确定性草稿。
没有密钥或 SDK 时，`CONVERSATION_PROVIDER=openai` 会在启动阶段显式失败；默认 deterministic 模式不需要 OpenAI 依赖。

## 身份与隐私边界

- 参与者连接握手必须属于该桌；未知 `participant_id` 会收到 `unknown_participant` 并以 1008 关闭。
- `viewer_mode=observer` 是只读旁听连接：`participant_id` 仅作为连接标识，不要求属于桌内；状态始终按无 viewer 投影，发言、入席/离席、同意和收桌事件统一返回 `observer_read_only`，不会产生任何持久化写入。
- `viewer_mode=commenter` 是外围评论连接：`participant_id` 仅作为评论作者标识，不占席位；连接建立后收到公开状态，只接受 `peripheral_comment`，其他写事件返回 `commenter_read_only`。评论以 `comment_id` 做桌级幂等，单独持久化并广播，不会触发主持决策或改变 Table State。
- 评论升级必须由当前核心成员显式触发；升级前重新执行 Safety，危险评论只产生安全暂停快照，不写入核心 turn。成功升级的 turn 由促成人负责并带 `source_comment_id`，`comment_promoted` 与状态事件会广播给同桌连接。
- 举报接口只允许当前桌成员自证提交，目标必须是同桌另一名成员；`report_id` 桌级幂等。举报人只能读取自己的举报，完整账本不通过公共 API 暴露，避免被举报对象或旁听者反向读取。审核器状态迁移另存私有审计链，重复状态不生成伪事件。
- 成员离席后，仍未关闭的旧连接也会在每条真人消息进入安全检查前重新校验席位；不会因为 stale socket 写入安全暂停或消息快照。
- 成员也可通过自证的 REST leave 入口离桌；离桌会产生一个版本化成员快照，旧连接后续消息会返回 `unknown participant`。
- REST consent 必须带 `viewer_id`，且必须等于路径中的参与者；未注入身份解析器时这是开发态身份声明。生产部署应注入 `identity_resolver`，让服务端把查询主体与真实会话主体交叉校验。
- 邀请偏好更新同样必须由本人 `viewer_id` 自证；WebSocket 的 `participant_invitation_preference` 事件必须把 `participant_id` 与连接身份保持一致，旁观者和评论连接不能写入。
- 未同意时，状态投影隐藏 `declared_position`/`unused_relevant_experience`，PASS 主持话也不会广播经历原文。
- 当前默认没有候选 source，候选人仍可由显式 `ParticipantSeed` 候选池提供；没有依赖知乎非官方抓取。
- 可选 `CommandCandidateSource` 为官方/获授权的 CLI、MCP 或 OAuth wrapper 提供 stdin/stdout 接入；命令不经 shell，默认 5 秒超时和 1 MB 输出上限，后端只接收规范化 `ParticipantSeed`。
- 可选 `CommandContentSignalSource` 为机会发现接入同样的官方/获授权 wrapper；后端只接收 `visibility=public` 的规范化 `ContentSignal`，不会把原始 token 或私有行为写入桌状态。
- 可选 `CommandPersonalContextSource` 为用户授权个人层接入官方/获授权 wrapper；后端只接受 `visibility=private` 且 owner 与 viewer 一致的 `PersonalContextSignal`，预览响应只回给该 viewer，默认不持久化。
- 接入正式知乎 CLI/MCP/OAuth 时，通过 `create_app(..., candidate_source=...)` 注入适配器，适配器只返回已授权、规范化候选资料，服务端不会接收或记录 access token。
- 外部 source 调用默认有 5 秒超时；可在 `create_app(..., candidate_source_timeout_seconds=...)` 注入不同正数。超时统一返回通用 502，不会回退到未经授权的候选。
- source 命令的超时从子进程启动开始，覆盖 stdin 写入/关闭、stdout/stderr drain、进程退出和清理；任一阶段超时都会杀掉子进程并 fail-closed，避免 wrapper 卡在输入阶段占住 worker。
- 软过期桌不再出现在默认 `GET /tables`；使用 `include_closed=true` 可在历史/运营视图中看到它，且仍按 viewer 做隐私投影。
- 关系记忆只从已收桌状态的 `worth_continuing_with` 证据派生；本人身份通过 `viewer_id` 自证，响应只含旧桌问题、对方公开姓名、理由和证据定位，不含私有画像或个人卡全文。
- 行动回响只在收桌后开放，状态为 `completed`、`in_progress`、`blocked` 或 `dismissed`；原始收桌底稿保持不变，结果单独持久化并可在重启后恢复。
- 行动结果写入会自动生成本人可见的 `follow_up_outcome` 行为事件；相同状态的重复回报保持幂等，状态迁移会留下带迁移方向的事件 ID，备注不会进入行为事件。
- 首次提交四维价值反馈会在同一次仓储提交中生成本人可见的 `value_feedback_submitted` 事件；后续更新只覆盖反馈账本，不重复生成事件，也不把分数或备注写入行为事件。
- 选桌行为通过专用入口生成稳定 `table_selected` 事件；只允许仍可发现的 open 桌，重复选择幂等且不改变参与者席位。
- 关系保存通过专用入口生成稳定 `relationship_saved` 事件；只允许收桌后的双方成员主动操作，重复保存幂等且不改变关系记忆的只读派生规则。
- 带参与者身份的 REST/WS 收桌成功后在同一次仓储提交中生成稳定 `table_closed` 事件；事件只写入触发者的行为账本，不广播，重复收桌不会复制同一事件。无身份的旧仓储 `close_table` 入口仅迁移桌状态，保持脚本兼容。
- 通用行为事件接口仍按事件类型校验桌上下文：真人发言和行动回响必须属于当前桌成员，关系保存必须是收桌后的另一名成员，`table_closed` 与 `value_feedback_submitted` 只能由对应服务端路径生成；只有 `table_selected` 允许在入席前记录，服务端生成事件不接受客户端伪造。
- 行为账本清除只移除个人行为事件，保留桌事实和安全审计；删除操作幂等，后续新发言或行动仍可重新沉淀事件。
- 价值反馈只在收桌后开放，参与者可更新自己的单条反馈；聚合返回响应人数、四类价值均值和愿意再次参加人数，且不改变 Table State 或收桌底稿。JSON 仓储会为旧数据缺省空反馈账本。

## 验证

```powershell
python -m pytest -q
python -m compileall -q app tests
git diff --check
```
