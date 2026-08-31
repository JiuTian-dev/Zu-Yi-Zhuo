# 组一桌：Conversation Orchestrator 后端

> Status: confirmed by `组一桌_后端Conversation_Orchestrator_执行SPEC_v1.0.docx`
> Last updated: 2026-09-01

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

### ADR-11: WebSocket 消息按桌幂等提交

- **决策**: 客户端 `message_id` 在单桌内作为幂等键；服务端在仓储锁内分配递增 `turn_id`。相同 ID 与相同内容的重试只返回 `duplicate_message`，不会再次观察、路由或触发主持动作；同 ID 不同内容直接拒绝。
- **理由**: 移动端/浏览器在网络抖动后会重发消息，重复触发一次主持会污染证据、冷却和审计链；turn id 也不能由并发连接在锁外计算。
- **替代方案**: 仅在 WebSocket 进程内缓存 ID，或继续依赖客户端去重。
- **代价**: `HumanTurn` 增加可选 `message_id` 以兼容旧 JSON；未来数据库实现需把幂等键设为桌级唯一约束。

### ADR-12: 邀请先于动态入席

- **决策**: 桌成员由持有席位的参与者发起邀请；候选人通过自身 `participant_id` 接受或拒绝。邀请状态与候选人的完整 `ParticipantSeed` 独立持久化，公开响应只返回姓名、角色、理由和状态，不返回立场/经历。
- **理由**: 产品要求 4 人即可开桌、5 人最佳，候补应由人决定是否入席；拒绝后不重复催，且候选人的私密画像不能在邀请预览中泄露。
- **替代方案**: 直接把候选人写入 `TableState.participants`，或由前端本地维护 pending 状态。
- **代价**: JSON 快照新增可选 `invitations` 段；未来数据库实现需把 `(table_id, candidate_id)` 设为唯一键，并把状态更新与接受入席放在同一事务。

### ADR-13: 异步默认、显式升级同步

- **决策**: 新桌默认 `conversation.mode=async`；桌内成员可先预览升级条件，再用“两项硬条件”请求切换到 `sync`。讨论质量、外围关注和公共价值只作为透明的加分信号，不单独触发升级。
- **理由**: 陌生人同时在线的组织成本高，异步更适合冷启动；当人还想聊且值得现在聊时再升级，避免把同步当成默认负担。
- **替代方案**: 创建桌时强制同步，或完全由前端本地切换模式。
- **代价**: 模式切换会产生一个可回放的状态版本；跨进程部署时仍需把升级判断和状态迁移放进数据库事务。

### ADR-14: 圆桌邀请偏好由候选人控制

- **决策**: `ParticipantSeed.roundtable_invite_preference` 默认 `few`，候选人选择 `none` 时不进入圆桌匹配，也不能被创建邀请；偏好随已入席成员保留在状态中。
- **理由**: 产品要求用户可以多推、少推或不推圆桌邀请，且“拒绝后不重复催”必须有服务端约束。
- **替代方案**: 只在前端保存偏好，或让邀请方覆盖候选人的选择。
- **代价**: 候选资料和旧 JSON 都增加一个有默认值的枚举字段；真实用户设置接入后需要把该字段映射到资料源。

### ADR-15: Provider 只改写主持话，不改变决策

- **决策**: 可选 LLM provider 只接收公开问题、当前子问题和确定性 Host 草稿，并只改写 `PASS / PROBE / REFRAME / CLOSE` 的文本；Gate、Safety、Router、状态迁移、证据、目标人和 GROUND 来源仍由确定性代码控制。
- **理由**: 让 AI 具备自然表达能力，同时把模型漂移限制在可校验的文案层；隐私字段、来源事实和主持动作不能被模型越权生成。
- **替代方案**: 让模型直接决定动作或把完整 Table State 发给模型。
- **代价**: provider 调用失败、超长、系统腔或来源声称会回退到确定性草稿；真实 provider 仍需要外部密钥、额度和延迟治理。

### ADR-16: 五席是桌级硬上限

- **决策**: 仓储在直接创建、追加参与者、创建邀请和接受邀请四个写入口统一限制最多 5 名参与者；空桌或少于 4 人的桌仍允许先建立并逐步入席。
- **理由**: 产品把 4 人定义为可开桌、5 人定义为最佳规模；上限必须在服务端原子写路径执行，不能只靠匹配页或前端按钮。
- **替代方案**: 只在 `MatchRequest.table_size` 上限制，或允许桌面无限扩容。
- **代价**: 满桌时新邀请/入席返回冲突，候选人需要等待空位；未来若支持不同桌型，应把容量变成显式 Table 配置。

### ADR-17: 外部候选 source 只通过规范化适配器进入匹配

- **决策**: 增加 `POST /matches/source-preview`，由服务端注入的 `CandidateSource.search(query, limit)` 适配器返回已授权的 `ParticipantSeed`，随后复用现有 `MatchRequest`/`MatchPlan` 校验和隐私投影；默认未配置 source 时明确返回 503。
- **理由**: 知乎 CLI、MCP、OAuth 的授权和字段契约可能由外部适配器负责变化，核心匹配不应绑定 undocumented endpoint，也不应把 access token 传给前端或 LLM。
- **替代方案**: 后端直接抓取知乎网页/内部接口，或把外部 source 输出未经校验交给匹配。
- **代价**: 正式 source 尚需平台授权和适配器实现；source 故障/格式错误会返回 502，不能自动降级成未经授权的候选。

### ADR-18: 收桌卡可从证据快照重建

- **决策**: 增加 `GET /tables/{id}/close-artifacts?participant_id=...`，仅对已关闭且已知参与者返回共享基线和该参与者个人卡；卡片从不可变状态快照与真人消息重建，不额外复制个人资料。
- **理由**: WebSocket 是实时投递，不应成为收桌产物的唯一存储；断线、重启后仍要能恢复“问题进化 / 共识 / 行动 / 个人回响”。
- **替代方案**: 只在关闭瞬间推送一次，或把全体个人卡写进公共快照。
- **代价**: 重建逻辑必须保持确定性；未来若允许人工编辑收桌卡，需要另设版本化 artifact 存储。

### ADR-19: 外部候选源调用必须有界

- **决策**: `create_app` 为注入的 `CandidateSource.search` 提供正数超时（默认 5 秒）；超时与上游故障一样返回通用 502，不把适配器异常或凭据细节暴露给客户端。
- **理由**: CLI/MCP/OAuth 适配器属于外部系统，不能让一次卡住的检索请求占住 API worker；匹配预览应 fail-closed，而不是无限等待或降级成未经授权的候选。
- **替代方案**: 不设超时，或超时后回退到本地/网页抓取候选。
- **代价**: 慢 source 需要在适配器侧分页、缓存或提高注入超时；调用方要把 502 视为可重试的上游失败。

### ADR-20: 收桌准备度随快照持久化

- **决策**: Observer 每次接受真人消息后刷新 `close_readiness` 并写入不可变快照；Host 介入写回沿用同一刷新值，保证 Gate/Router 使用的边际价值信号与客户端、回放看到的状态一致。
- **理由**: 只在决策函数里临时计算会造成 UI 和回放落后一版，甚至让 CLOSE 路由与持久化状态互相矛盾。
- **替代方案**: 客户端自行重算，或仅在请求 close 时计算。
- **代价**: 收桌准备度的确定性公式属于状态契约，未来替换 Observer 时仍需保留刷新边界。

### ADR-21: 收桌行动结果是可恢复的独立账本

- **决策**: 关闭后通过 `GET /tables/{id}/follow-ups` 查询公共行动项，并由成员通过 `POST /tables/{id}/follow-ups/{index}/outcome` 回报 `completed / in_progress / blocked / dismissed`；承诺只能由拥有者回报，建议项由首位报告成员占用，结果写入内存或 JSON 仓储。
- **理由**: 收桌卡不应停留在一次性建议；用户需要在现实行动发生后看到回响，同时不把“聊到过”误写成“已经承诺”。
- **替代方案**: 只在前端本地保存状态，或把新行动直接追加成真人消息。
- **代价**: 行动项以关闭时公共底稿的稳定索引定位；未来若允许编辑底稿，需要升级为显式 artifact ID。

### ADR-22: 软过期是保留历史的生命周期迁移

- **决策**: 桌内成员可通过 `POST /tables/{id}/soft-expire` 将主题或组合价值下降的桌迁移为 `conversation.soft_expired=true`、`state=soft_expired`；记录原因并从默认桌发现中淡出。软过期后拒绝新消息、成员变更、邀请、同步升级、主持/安全快照和来源卡片写入，但保留参与者、消息、状态回放、行动回响和收桌能力；收桌后状态为 `closed` 且保留软过期标记与原因。迁移幂等，不删除数据，也不自动复制成员到新桌。
- **理由**: 产品要求桌子在问题热度或组合价值下降时停止消耗实时协作资源，同时保留可追溯的历史和后续收桌产物，支持围绕新问题重组新桌。
- **替代方案**: 直接删除桌、继续在旧桌接收消息，或让前端本地标记过期。
- **代价**: 客户端需要处理 `table_soft_expired` 错误；正式重组流程仍应创建新桌并重新走匹配/邀请边界。

### ADR-23: 关系记忆从收桌证据派生且只读

- **决策**: 增加按参与者查询的 `RelationshipMemory` 只读视图，来源限定为已收桌且 `PersonalCard.worth_continuing_with` 有证据的关系建议；每条记忆包含旧桌 ID、旧桌问题、对方公开姓名/参与者 ID、关系理由、证据 turn 和收桌状态版本。查询必须由本人 `viewer_id` 自证，响应不包含对方私有立场、经历或个人卡全文。记忆从持久化 Table State 派生，不另建可漂移的编辑副本。
- **理由**: 产品需要在再次遇到旧桌友时提醒“曾在哪桌围绕什么问题聊过”，但关系是否继续由人决定；派生式只读视图能复用收桌证据并避免额外一致性事务。
- **替代方案**: 前端本地保存关系、把关系写成新的公共消息，或建立允许 Agent 自由编辑的长期画像。
- **代价**: 只有已产生关系证据的已收桌才会出现记忆；未来接入好友/关注动作时需另设用户授权和关系状态，不把本接口当作社交关系写入口。

### ADR-24: 离桌由本人发起并复用原子成员迁移

- **决策**: 增加 `POST /tables/{id}/participants/{participant_id}/leave?viewer_id={participant_id}`，要求 `viewer_id` 与路径参与者一致；接口复用仓储 `remove_participant`，与 WebSocket `participant_left` 共享同一版本化成员快照和写入锁。离桌不删除历史消息或旧快照；离桌后的连接在下一次真人消息前会重新校验席位并被拒绝。关闭或软过期桌不可再离桌。
- **理由**: 产品要求成员可随时退出且不必解释，同时 stale socket 不能在退出后继续写入；把身份校验和迁移统一到服务端仓储可以避免 REST/WS 分叉。
- **替代方案**: 只在前端隐藏成员、把离桌当作删除用户，或为 REST/WS 各维护一套成员状态。
- **代价**: 离桌后桌内人数可能低于开桌门槛；补位必须重新走邀请/候选流程，不自动恢复离桌成员。

### ADR-25: 外部候选源通过无 shell 的 JSON 命令桥接

- **决策**: 在未核验稳定的知乎读取 API 之前，提供可选 `CommandCandidateSource`。后端启动一个服务端预配置的可执行命令，通过 stdin 发送 `{"query": ..., "limit": ...}`，要求 stdout 返回候选数组或 `{"candidates": [...]}`，再用 `ParticipantSeed` 严格校验后进入匹配。命令以参数数组执行，不经过 shell；进程、输出大小和候选数量均有界，任何非零退出、超时、非 JSON 或非法候选统一视为 source failure。API/日志不接收或打印 access token，正式 CLI/MCP/OAuth 适配器自行负责授权。
- **理由**: 官方知乎材料可确认 OpenAPI 凭证和发布 skill，但当前没有足以支撑本项目的稳定搜索/用户画像读取契约；命令桥允许接入官方或获授权的本地适配器，又避免把非官方抓取写进核心服务。
- **替代方案**: 直接请求 undocumented 知乎内部接口、把 Cookie/token 交给前端，或在没有授权 source 时降级到网页抓取。
- **代价**: 接入者需要提供一个小型 CLI/MCP wrapper 遵守 JSON stdin/stdout 契约；source 未配置时继续返回 503。

### ADR-26: 问题机会预览先做确定性未完成性判断

- **决策**: 增加 `POST /opportunities/preview`，接收已获授权的公开问题/回答/文章信号，返回 `OpportunityPreview`：规范化核心问题、带 source signal ID 的未完成性证据、角色缺口和 `ParticipantSeed` 候选池。候选池随后可直接交给现有 `/matches/preview`；预览不创建桌、不发送邀请。启发式只使用公开标题/摘要/作者公开角色/公开立场，所有输入必须标记为 `public`，信号数量与摘要长度有界。
- **理由**: 产品的第一入口不是“先有一群人再聊天”，而是发现一个值得发生的交流机会；先把问题未完成性和候选角色结构化，才能解释为什么要围绕这道题组桌，同时保持模型可替换。
- **替代方案**: 直接把搜索结果当作桌、让 LLM 自由生成问题/候选人，或在服务端抓取知乎私密行为。
- **代价**: V1 启发式不能替代语义聚类；真正的知乎 source 只需把授权结果映射为 `ContentSignal`，后续可替换 detector 而不改桌内闭环。

### ADR-27: 动态补位只推荐不自动入席

- **决策**: 增加 `POST /tables/{id}/candidate-preview?participant_id=...`。桌内成员可用当前问题或自定义 query 请求已授权 source；服务端结合桌内已有角色、主题词、候选经历和 `roundtable_invite_preference` 生成有理由的候选推荐，过滤已有席位及曾经邀请过的候选，返回 `open_seats`/`role_gaps` 和公开推荐字段。该接口不改 Table State、不创建邀请、不自动入席；成员仍需调用现有邀请接口逐个发出邀请。
- **理由**: 产品要求第 5 席可动态补入，但候补不是机械替补，Agent 应根据真实讨论判断现在最缺谁；把推荐和入席拆开既能利用实时桌状态，也保留候选人和桌内成员的选择权。
- **替代方案**: 满桌前自动把 source 返回的人写入 participants、只按相关性排序，或把候选推荐交给前端自行实现。
- **代价**: source 未配置时只能返回 503；角色缺口是 V1 确定性启发式，后续可替换为模型/行为信号而不改变邀请事务。

### ADR-28: 机会发现通过独立公开内容 source 桥接

- **决策**: 增加 `ContentSignalSource.search(query, limit)` 和 `POST /opportunities/source-preview`。服务端通过独立的 `CONTENT_SIGNAL_SOURCE_COMMAND` 无 shell 子进程获取已授权的公开问题/回答/文章信号，严格校验为 `ContentSignal` 后复用现有 `build_opportunity_preview`；source 只负责检索与授权，detector 负责未完成性、角色缺口和候选种子判断。source 未配置、超时、非零退出或信号不合法时统一 fail-closed，不创建桌或邀请。
- **理由**: 机会发现是产品入口，不能要求前端把原始来源拼成内部契约；独立内容 source 让官方 API、CLI、MCP 或 OAuth wrapper 可替换接入，同时不把未经验证的知乎内部读取接口硬编码进核心服务。
- **替代方案**: 复用候选人 source 返回混合数据、在 API 内抓取网页、或让前端直接持有知乎 token。
- **代价**: 接入者需要提供内容检索 wrapper，并保证只返回有授权的公开信号；source 未配置时机会预览保持 503。

## 接口契约

### REST / WebSocket

```text
POST /tables
POST /matches/preview
POST /matches/source-preview
POST /matches/confirm
POST /opportunities/source-preview
GET  /tables?participant_id={viewer_id}&include_closed={bool}
GET  /tables/{id}
POST /tables/{id}/participants
POST /tables/{id}/participants/{participant_id}/leave?viewer_id={participant_id}
POST /tables/{id}/candidate-preview?participant_id={participant_id}
POST /tables/{id}/invitations
GET  /tables/{id}/invitations?participant_id={candidate_id}
POST /tables/{id}/invitations/{invitation_id}/respond?participant_id={candidate_id}
POST /tables/{id}/sync/preview?participant_id={participant_id}
POST /tables/{id}/sync/upgrade?participant_id={participant_id}
GET  /tables/{id}/state
GET  /tables/{id}/replay
GET  /tables/{id}/interventions
GET  /tables/{id}/close-artifacts?participant_id={participant_id}
GET  /tables/{id}/follow-ups?participant_id={participant_id}
POST /tables/{id}/follow-ups/{index}/outcome?participant_id={participant_id}
POST /tables/{id}/soft-expire?participant_id={participant_id}
POST /tables/{id}/close
GET  /participants/{participant_id}/relationship-memory?viewer_id={participant_id}
WS   /ws/tables/{table_id}?participant_id={participant_id}
```

Client events: `human_message`, `participant_joined`, `participant_left`, `participant_consent`, `request_debug_state`。

Server events: `message_committed`, `agent_action`, `table_state_changed`, `grounding_card`, `close_started`, `close_artifact_ready`, `intervention_reflected`。

广播边界：同桌客户端共享公共事件；`request_debug_state` 与 `close_artifact_ready.personal_card` 仅发送给请求连接。
消息幂等：`human_message.message_id` 在单桌内唯一；重复同内容提交返回 `duplicate_message`，不产生新 turn/state/action/audit。
资料边界：状态投影默认隐藏其他参与者的 `declared_position` 和 `unused_relevant_experience`；只有本人显式同意后才公开。
邀请边界：邀请预览只返回候选人的公开姓名/角色/理由/状态；只有候选人自己能响应邀请，接受后才写入 `TableState.participants`。
模式边界：新桌默认异步；升级预览返回两项硬条件和三类加分信号，只有桌内成员提交两项硬条件为真且至少两位成员已有持续参与证据时才可切换同步。
邀请偏好：候选人 `roundtable_invite_preference=none` 时不会被匹配或收到邀请；未提供时按 `few` 处理。
发现边界：桌列表默认只返回未关闭桌，并按 viewer 投影状态；未提供 viewer 或未同意时，个人立场和经历保持隐藏。
软过期边界：软过期桌默认从发现列表隐藏；桌内对话、成员、邀请、同步、主持/安全快照和来源卡片写入均返回冲突，历史回放、状态查询、收桌和收桌后行动回响仍可用；重复软过期不增加版本。
关系记忆边界：只从已收桌的证据派生；`viewer_id` 必须等于路径参与者本人；只返回公开姓名、旧桌问题、关系理由和证据定位，不返回对方私有画像或个人卡全文；该接口只读。
离桌边界：REST/WS 均要求本人身份；离桌产生一个成员快照版本，保留历史但拒绝该参与者后续真人消息；软过期或关闭后不再允许成员迁移。
候选 source 边界：外部 source 只允许通过服务端注入的 `CandidateSource` 返回规范化 `ParticipantSeed`；未配置返回 503，输出不合法返回 502，不接受前端 token。
收桌产物边界：关闭前返回 409；关闭后只返回请求参与者自己的 `personal_card`，共享基线可恢复但不包含其他人的个人卡。
行动回响边界：follow-up 只在关闭后可读写；承诺由 owner 回报，建议项首位成员回报后锁定 reporter；结果不改变原始 Table State 或收桌底稿。

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

ConversationState(..., soft_expired, soft_expiry_reason?)

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
                                                                    ←── D36 provider-backed Host wording boundary
                                                                    ←── D44 soft-expired table lifecycle
                                                                                  ←── D46 participant leave REST parity
                                                                                        ←── D47 command-backed candidate source
                                                                                              ←── D48 opportunity discovery preview
                                                                                                    ←── D49 dynamic candidate replenishment preview
                                                                                                           ←── D50 content signal source bridge
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
| D27 Host profile-consent boundary | complete | PASS wording cites private experience only after explicit `profile_shared`; unconsented broadcasts retain public role context and redact experience text | 174 tests + privacy regression | `7277585` |
| D28 backend handoff guide | complete | runtime/install/configuration, WebSocket and privacy boundaries, optional provider usage, and verified commands documented in `backend/README.md` | documentation review + 174-test baseline | `0336a0d` |
| D29 SILENCE audit invariant | complete | all repository audit-write paths reject `SILENCE`, preserving the rule that silence produces no intervention record | 174 tests + compileall + diff check | `e00c379` |
| D30 schema audit invariant | complete | `InterventionRecord` itself rejects `SILENCE`, so JSON reload and direct model construction cannot bypass the no-pseudo-audit rule | 175 tests + compileall + diff check | `34fe1ce` |
| D31 WebSocket message idempotency | complete | table-scoped `message_id` dedupe with atomic server-side `turn_id` allocation; exact retries do not re-run Observer/Host and conflicting reuse is rejected | 178 tests + compileall + diff check | `eef2924` |
| D32 invitation lifecycle | complete | persistent pending/accepted/declined invitations with candidate-scoped response and redacted preview | 181 tests + compileall + diff check | `fe05845` + `78ae2fb` |
| D33 async-to-sync upgrade | complete | async-by-default conversation mode, explainable upgrade preview, and atomic sync migration | 184 tests + compileall + diff check | `5f9d3f7` + `fb82f8b` |
| D34 public table discovery | complete | list open tables with privacy-projected state and optional closed-table inclusion | 185 tests + compileall + diff check | `bc7f9be` |
| D35 roundtable invite preference | complete | candidate-controlled many/few/none preference enforced at matching and invitation boundaries | 187 tests + compileall + diff check | `008a984` |
| D36 optional Host wording provider | complete | provider-injected Host wording with public-context prompt, bounded output validation, deterministic fallback, and explicit runtime selection | 196 tests + compileall + diff check | `a04655e` |
| D37 five-seat table capacity | complete | repository-level five-seat cap for create/add/invite/accept paths with in-memory and JSON parity | 199 tests + compileall + diff check | `cd6e518` |
| D38 candidate source adapter boundary | complete | injectable CLI/MCP/OAuth-compatible candidate source, normalized source-preview endpoint, and privacy-safe failure responses | 203 tests + compileall + diff check | `e9bfcdf` |
| D39 reconnectable close artifacts | complete | evidence-backed close-artifacts REST recovery with participant-scoped personal card | 205 tests + compileall + diff check | `cffe3a8` |
| D40 stale WebSocket membership guard | complete | re-check participant membership after handshake and before safety/turn handling, preventing a departed socket from writing snapshots | 206 tests + compileall + diff check | `f8b2d79` |
| D41 bounded candidate-source calls | complete | injected candidate source calls have a positive timeout and fail closed with a generic 502 on timeout | 208 tests + compileall + diff check | `e95f4a5` |
| D42 persisted close-readiness snapshots | complete | Observer and Host writeback persist the same close-readiness value used by Gate/Router | 209 tests + compileall + diff check | `9076fca` |
| D43 follow-up outcome ledger | complete | close-card follow-ups expose a REST read/write contract with owner checks and JSON restart persistence | 214 tests + compileall + diff check | `aac94a0` |
| D44 soft-expired table lifecycle | complete | explicit soft-expire state, discovery filtering, read-only conversation boundary, history-preserving close path, and reconnect-safe WebSocket error | 218 tests + compileall + diff check | `5aab4c8` |
| D45 relationship memory view | complete | derive evidence-backed old-table relationship reminders from closed states with self-only REST access and no private profile leakage | 221 tests + compileall + diff check | `c9334c4` |
| D46 participant leave REST parity | complete | self-scoped REST leave endpoint sharing atomic repository membership migration with WebSocket | 222 tests + compileall + diff check | `58c0119` |
| D47 command-backed candidate source | complete | bounded no-shell JSON stdin/stdout bridge for authorized CLI/MCP/OAuth candidate adapters | 227 tests + compileall + diff check | `a7a28bc` |
| D48 opportunity discovery preview | complete | public-signal opportunity detector with unfinishedness evidence, role gaps, and normalized candidate seeds | 231 tests + compileall + diff check | `9eda0ce` + `874fa68` |
| D49 dynamic candidate replenishment preview | complete | member-scoped, source-backed recommendations for current role gaps without automatic seat or invitation writes | 236 tests + compileall + diff check | `9884bee` |
| D50 content signal source bridge | complete | bounded authorized public-content source feeding the existing opportunity detector without table or invitation writes | 242 tests + compileall + diff check | `573d2cf` |

## 已知坑位（Running Gotchas）

- 当前前端展示题目是“为什么我们越来越不会休息？”，后端旗舰评测题目是“AI Agent 真正进入企业，卡住的是技术还是采购？”；在 API 联调前需明确采用双 demo table 还是统一题目。
- 本机系统 Python 为 3.14；项目必须声明 3.11+ 兼容范围，避免无意使用 3.14 专属语法。
- API 接入前必须增加独立的 pre-loop SafetyDecision/Enforcement；critical hard violation 不能只依赖主持 Router 的 REFRAME，需能表达暂停、拦截或移出。
