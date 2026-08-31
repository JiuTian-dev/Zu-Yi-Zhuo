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

### ADR-29: 收桌价值反馈进入独立回响账本

- **决策**: 增加 `ValueFeedback` 和 `FeedbackSummary`。已收桌参与者可通过 `POST /tables/{id}/feedback?participant_id=...` 提交或更新 1–5 分的认知、关系、行动、情绪四类价值，以及可选短备注和是否愿意再参加；`GET /tables/{id}/feedback?participant_id=...` 只返回桌内成员可见的匿名聚合，不返回他人的备注或单条评分。反馈记录写入内存/JSON 仓储，固定引用收桌状态版本，不改变 Table State 或收桌底稿。
- **理由**: 产品成功标准不只是“生成了卡片”，还要验证参与者是否真的获得认知、关系、行动和情绪价值；独立账本让回响可量化、可重启恢复，同时不把主观评价混入 evidence-first 对话状态。
- **替代方案**: 让前端本地保存评分、把反馈追加成真人消息，或直接公开每个人的分数与备注。
- **代价**: V1 只提供自填量表与匿名均值，不能替代真实内测；后续若需要实验分组或时间序列，应在账本上增加显式 feedback ID/批次。

### ADR-30: 静默旁听是只读连接，不占核心席位

- **决策**: WebSocket 增加 `viewer_mode=observer` 查询参数。旁听者使用自选 `participant_id` 作为连接标识，但不需要出现在桌内席位；连接建立后只接收经过全量隐私投影的公开状态和桌面事件，并允许请求同样经过投影的 debug state。旁听连接拒绝真人发言、入席/离席、资料同意和收桌等写事件，且不会写入 Table State、turn、邀请或反馈账本；默认 `viewer_mode=participant` 的现有协议保持不变。
- **理由**: 产品需要让外围评论和静默听众先观察“正在形成的桌”，又不能把旁听误当作第五席或让未入席者看到私有画像；在 WebSocket 层做只读边界能复用实时广播而不引入伪参与者。
- **替代方案**: 旁听者直接创建临时 ParticipantState、只在前端本地模拟旁听，或把所有状态原样广播后交给客户端过滤。
- **代价**: V1 旁听只读，不提供外围评论写入口；后续评论若落地，应单独建公共评论账本并继续复用旁听身份边界。

### ADR-31: 外围评论独立于核心真人 turn

- **决策**: WebSocket 增加 `viewer_mode=commenter` 和 `peripheral_comment` 事件；评论者不占核心席位，只能提交有界文本，服务端以 `(table_id, comment_id)` 做幂等提交并把 `PeripheralComment` 写入独立评论账本。评论通过 REST `POST/GET /tables/{id}/comments` 与 WebSocket 事件共享同一账本，旁听者、评论者和核心成员都能看到；评论不会进入 Observer、Gate、Router、Host、Reflection 或核心 turn 证据链。评论者连接仍只能看到全量隐私投影后的公共状态。
- **理由**: 产品需要外围观众可以提出问题、补充线索，但不能用低承诺评论稀释核心桌的节奏或占用第五席；独立账本同时保留回放与审核边界。
- **替代方案**: 把评论伪装成匿名 ParticipantState、直接追加 HumanTurn，或让前端本地维护评论而不广播。
- **代价**: V1 只提供文本评论和幂等写入，未实现评论排序、点赞或升级到主桌；后续应由 Agent/主持策略显式挑选高质量评论递进核心桌。

### ADR-32: 问题进化通过显式重组创建下一桌

- **决策**: `TableState` 增加可选 `origin_table_id`；已收桌桌子可调用 `POST /tables/{id}/recompose`，服务端从收桌共享基线读取带证据的 `evolved_question`，要求调用方提供一组重新选择且数量有界的 `ParticipantSeed`，创建一张新桌并记录来源桌。重组不复制旧成员、邀请、评论、反馈或消息，源桌和新桌均保持独立可回放。
- **理由**: 产品的问题飞轮要求“原问题进化 → 下一桌”，但重组不应把旧桌成员机械搬运到新局；显式来源链接既保留问题谱系，也让候选与邀请重新经过用户选择和隐私边界。
- **替代方案**: 直接复制旧桌、只返回一段文本让前端自行建桌，或把新问题覆盖写回旧桌。
- **代价**: V1 只支持从已收桌创建单层来源链接；未来若需要多代问题图谱，可在此字段之上扩展 lineage 查询而不改变桌内状态机。

### ADR-33: 不再匹配偏好是全局、双向的写入边界

- **决策**: 增加按参与者本人授权的全局 `no-match` 偏好。参与者只能为自己创建、删除或查询目标参与者的屏蔽关系；关系以 `(participant_id, blocked_participant_id)` 持久化，邀请创建与动态候选预览在任一方向命中时都拒绝/过滤。屏蔽不移除已有桌成员、不删除历史消息，也不自动撤销已经发出的邀请。
- **理由**: 产品明确要求用户可以屏蔽某人并选择以后不再匹配；把它放在服务端全局账本可覆盖 REST、WebSocket 后续入口和重启恢复，同时避免把安全意愿依赖前端本地过滤。
- **替代方案**: 只在当前桌临时隐藏、由前端维护黑名单，或屏蔽后立即改写历史桌成员。
- **代价**: V1 只约束本服务的邀请和候选预览；外部候选 source 仍返回原始授权结果，由服务端在有 viewer 身份的入口过滤；未来接入统一用户身份后可把该账本映射为账号级偏好。

### ADR-34: 举报进入独立、最小可见的安全账本

- **决策**: 增加桌级 `SafetyReport` 账本。桌内成员可以自证身份后提交有界的举报类别、描述和目标参与者；`report_id` 在桌内幂等，重复提交只返回原记录。举报查询默认只允许举报人读取自己的记录，举报正文不广播给同桌、不进入 HumanTurn、Table State 或主持证据链。仓储保留供后续审核适配器读取的完整记录，但当前不提供无认证的公共管理员接口。
- **理由**: 产品要求支持举报，同时安全信息不能被旁观者或被举报对象反向读取；独立账本让审核可以异步接入，不把举报动作误当作自动封禁或主持判断。
- **替代方案**: 把举报写成核心消息、把举报内容广播给全桌，或用未认证的管理端点暴露所有举报。
- **代价**: V1 的审核处理状态由后续受控运营/适配器更新；当前 API 只负责安全收集、幂等和举报人可见性，不自动移除成员或关闭桌。

### ADR-35: 用户授权个人层通过短生命周期 source 进入

- **决策**: 增加 `PersonalContextSource` 适配器和 `POST /personal-context/source-preview?viewer_id=...`。适配器在服务端完成 OAuth/CLI/MCP 授权，返回只属于该 viewer 的关注、收藏、个人公开表达等规范化 `PersonalContextSignal`；服务端只生成私有、短生命周期的主题预览，不把 access token 交给前端、不把个人信号写入 Table State 或默认 JSON 快照。source 未配置、超时或 owner 不匹配时 fail-closed。
- **理由**: 产品需要“从用户自己的长期表达和兴趣出发”发现问题，但个人层比公共内容更敏感；将授权和读取封装在 source，既能接入真实 OAuth，又能让核心机会/匹配逻辑不绑定平台私有接口。
- **替代方案**: 前端直接携带 token 调知乎、把个人收藏原文永久落盘，或把个人信号广播给同桌。
- **代价**: V1 只提供 viewer 自己的预览，不自动创建桌、不自动公开个人画像；正式 OAuth scope、刷新和撤权由外部适配器负责，后续可把预览作为机会检测的私有输入。

### ADR-36: 个人 source 必须先通过服务端 scope 授权闸门

- **决策**: 增加全局 `PersonalContextConsent` 账本和本人自证的授权/撤回接口。预览请求必须声明 `profile`、`follows`、`favorites`、`public_content` 中的一个或多个 scope，且全部包含在当前授权中；撤回后立即拒绝 source 调用。授权只记录 scope，不记录 token 或个人信号；外部适配器仍负责真实 OAuth 授权、刷新和平台撤权。
- **理由**: 产品要求个人数据由用户授权并可撤回；把 scope 检查放在服务端能阻止前端绕过 UI 直接读取个人层，也让关注/收藏等敏感范围清晰可审计。
- **替代方案**: 只让前端勾选但服务端不校验、每次请求携带布尔 `consented`，或把 OAuth token 存进桌仓储。
- **代价**: V1 仍使用开发态 `viewer_id` 自证，生产环境需替换为真正会话身份；撤回只删除本服务授权状态，平台侧撤权由 adapter 完成。

### ADR-37: 外围评论只能经核心成员明确促成后进入主桌

- **决策**: 增加 `POST /tables/{id}/comments/{comment_id}/promote?participant_id={member_id}`。只有当前核心成员可以显式选择一条外围评论升级；服务端重新执行安全检查后，以核心成员为负责人的 `HumanTurn` 写入主桌，并在 turn 上保留 `source_comment_id`。评论原文和升级记录分别保留在 `PeripheralComment` 与 `CommentPromotion` 账本中，使用 `(table_id, comment_id)` 幂等。升级和主桌状态、turn 必须作为一个仓储事务提交；评论内容命中安全策略时只写安全暂停快照，不写入核心 turn。
- **理由**: 产品需要让外围高价值补充可以反哺主桌，但不能让旁听者绕过席位、身份和安全边界直接注入核心讨论。显式成员选择与可回放来源链同时保留责任归属、审核证据和问题上下文。
- **替代方案**: 自动按点赞/排序升级、把评论直接伪装成匿名真人 turn，或只在前端复制文本而不进入服务端证据链。
- **代价**: V1 只提供成员触发的单条文本升级，不做自动排序、投票或批量推广；生产环境应把 `participant_id` 替换为真实会话身份，并可由 Agent/主持策略调用同一显式接口。

### ADR-38: 圆桌 Agent 是独立的公开席位，不计入真人席位上限

- **决策**: `TableState` 增加稳定的 `AgentPresence`（默认 id 为 `roundtable-agent`、展示名“圆桌 Agent”、角色“对话搭档”），并标记 `active`、`paused` 或 `closed` 状态。它是每张桌固定存在的第六个公开角色，不进入 `participants`、邀请、匹配、no-match 或隐私投影；真人席位仍最多 5 人，4 人即可开桌。安全暂停、软过期和收桌分别把 Agent 标记为 `paused` 或 `closed`，正常主持写回保持 `active`。
- **理由**: 产品明确区分“5 位真人 + 1 位圆桌 Agent”；把 Agent 只藏在事件名里会让重连、旁听和前端桌面无法稳定渲染角色，也容易把 Agent 误算成真人席位。独立公开元数据能补齐身份而不污染真人证据链。
- **替代方案**: 把 Agent 伪装成 `participants` 中的第六个成员、只依赖 WebSocket `agent_action` 事件，或让前端硬编码 Agent 身份。
- **代价**: V1 只记录单一固定 Agent 身份和生命周期状态，不支持多 Agent、Agent 配置或跨桌人格；生产环境可在此结构上扩展 provider/model 展示元数据。

### ADR-39: JSON 收桌必须与内存收桌保持原子、可重启一致

- **决策**: `JsonTableRepository.close_table` 覆盖内存实现，沿用同一幂等状态迁移规则并把关闭快照、真人 turn、干预、邀请、评论、反馈、举报、授权和 Agent 生命周期一起写入原子 JSON 替换；重复关闭不增加版本。旧快照若缺少 Agent 字段，则按 `conversation.closed`/`soft_expired` 自动补齐 `closed`/`paused` 状态。
- **理由**: 收桌是产品闭环的关键持久化边界；如果重启后恢复为未关闭桌，收桌卡、行动回响和问题重组都会失真。复用仓储事务能避免只更新内存而丢失历史。
- **替代方案**: 继续依赖继承的内存 `_append`、启动时扫描并猜测关闭状态，或把收桌标记交给前端保存。
- **代价**: V1 仍是单进程 JSON 仓储；多进程部署需要把同样的状态迁移下沉到数据库事务并加锁。

### ADR-40: 回放响应同时返回公开叙事账本

- **决策**: 扩展 `GET /tables/{id}/replay`，在原有 `messages + snapshots` 之外返回 `interventions`、`comments` 和 `comment_promotions`。这些记录均为桌级公开叙事或来源链；举报、个人授权和价值反馈等私有账本不进入回放。现有字段保持不变，新增列表默认兼容旧客户端。
- **理由**: 重连和复盘不应要求前端再拼接多个接口才能恢复“人说了什么、Agent 做了什么、外围补充如何进入主桌”；统一响应也能让评论升级的来源证据可追溯。
- **替代方案**: 继续只返回状态快照、由前端并发请求多个账本，或把举报/个人数据一并暴露在回放中。
- **代价**: V1 返回完整桌级公开账本，不提供事件分页或时间窗口；后续高流量部署需按版本/游标分页。

### ADR-41: 产品行为层用本人可见的受限事件账本沉淀

- **决策**: 增加 `BehaviorEvent` 账本与 self-scoped `POST/GET /participants/{id}/behavior-events`。事件类型只允许 `table_selected`、`human_message`、`relationship_saved`、`follow_up_outcome`；可选桌、状态版本、关联参与者和有界备注，不保存完整消息正文或 token。真人 turn 由仓储自动生成 `human_message` 事件，其他行为由客户端在本人身份下显式上报；`event_id` 桌/用户范围幂等，冲突重用拒绝。JSON 仓储原子持久化并兼容缺失账本的旧文件。
- **理由**: 产品希望画像从真实选择、发言、关系和行动回响中逐渐长出来，但行为数据比公共桌状态更敏感；统一小账本既能支撑后续画像/推荐，又不会把个人轨迹广播给同桌或写进 Table State。
- **替代方案**: 让前端本地维护行为、把所有行为拼进真人消息，或开放任意 JSON metadata 造成隐私和 schema 漂移。
- **代价**: V1 只提供事件记录与本人回读，不自动推断画像、不跨用户公开关系；生产环境需把 `viewer_id` 接到真实会话身份并增加分页/保留策略。

### ADR-42: 行动回响与行为事件必须同一事务落账

- **决策**: `record_follow_up_outcome` 在保存收桌行动结果的同时，自动追加本人可见的 `follow_up_outcome` 行为事件；事件只携带桌 ID、当前关闭状态版本和有界状态摘要，不携带行动备注或完整底稿。相同参与者对同一行动重复回报同一状态保持幂等；状态变化生成新的事件。内存与 JSON 仓储都必须在同一写路径中提交两份账本。
- **理由**: 产品飞轮要求“行动回响”能反哺后续画像，但行动结果与行为事件若分开写入，会出现一边成功、一边丢失的不可解释状态。将事件派生自已校验的 follow-up 结果，既避免前端漏报，也不扩大个人备注的传播面。
- **替代方案**: 继续要求前端额外 POST 行为事件、把行动结果复制进 Table State，或只记录最后一次结果而丢失状态变化轨迹。
- **代价**: V1 的事件摘要只表达状态，不保存备注全文；未来接入真实账号和分析管道时仍需分页、保留与删除策略。

### ADR-43: 外部 source 超时覆盖完整子进程生命周期

- **决策**: `CommandCandidateSource`、`CommandContentSignalSource` 和 `CommandPersonalContextSource` 的单次调用预算从创建子进程开始计时，覆盖 stdin 写入/关闭、stdout/stderr drain、进程退出和任务清理；任何阶段超时都杀掉子进程并返回各自的通用 source error。适配器仍使用无 shell 参数数组和既有输出上限。
- **理由**: 只限制读取阶段无法保护 API worker：一个启动后不读取 stdin 的 wrapper 就能让 `drain()` 无限等待，绕过 D41 的 fail-closed 约束。统一全链路预算可以让 source 故障在确定时间内释放资源，也避免把凭据或底层异常暴露给客户端。
- **替代方案**: 只继续限制 `process.wait()`、依赖操作系统 pipe 缓冲区，或为每类 source 单独实现不一致的超时逻辑。
- **代价**: wrapper 必须在预算内消费请求并返回；超时包括进程启动开销，极慢但合法的 source 需要在适配器侧优化或由调用方显式提高注入预算。

### ADR-44: 选桌行为由服务端生成稳定事件

- **决策**: 增加 `POST /tables/{id}/select?participant_id={viewer_id}`，只校验桌存在且仍处于可发现的 open 生命周期，然后由服务端生成不绑定状态版本、但稳定 `event_id` 的 `table_selected` 行为事件。接口不新增席位、不改变 Table State、不广播；重复选择复用行为账本幂等规则。通用行为事件 POST 仍保留，供关系保存等没有独立领域写入口的行为使用。
- **理由**: 选桌是产品行为层的首个冷启动信号，不能依赖前端随意拼接 event_id 或把一次浏览误当入席。由服务端生成事件可确保桌引用、版本和生命周期一致，同时不把“选择”越权成“加入”。
- **替代方案**: 继续让前端直接 POST 任意 `table_selected` 事件、在 `GET /tables` 时隐式记录选择，或选择时自动加入桌。
- **代价**: V1 只支持 open 桌的显式选择，不记录浏览/曝光；正式认证接入后需把 `participant_id` 替换为会话主体。

### ADR-45: 关系保存只在收桌后按成员身份落账

- **决策**: 增加 `POST /tables/{id}/relationships/{related_participant_id}/save?participant_id={viewer_id}`。服务端要求桌已关闭、viewer 与 target 都曾属于该桌且两者不同，再生成稳定的 `relationship_saved` 行为事件；接口不复制个人卡、不修改 Table State 或关系记忆派生源。重复保存复用行为账本幂等规则。
- **理由**: 产品中的“加好友/继续连接”必须建立在真实桌内关系和收桌后的主动选择上，不能由前端任意写入陌生人关系。把保存动作限制在已结束桌并复用 self-scoped 行为账本，能让后续画像知道用户主动选择过谁，同时保持关系记忆只读、无社交图漂移。
- **替代方案**: 继续接受任意 `relationship_saved` JSON、在对话中自动生成关系，或把关系保存直接写入长期好友图。
- **代价**: V1 只记录保存动作，不提供好友请求/取消保存或跨平台同步；正式社交能力接入时应在此事件旁新增授权关系服务。

### ADR-46: 行为事件按类型校验桌上下文

- **决策**: 仓储统一校验行为事件与桌上下文：`table_selected` 允许在入席前记录；`human_message` 与 `follow_up_outcome` 必须由当前桌成员写入，后者还要求桌已关闭；`relationship_saved` 必须由当前桌成员在收桌后指向另一名当前成员。JSON 重启加载复用同一校验，发现不兼容事件即拒绝恢复。
- **理由**: self-scoped 只解决“谁能读写自己的账本”，不能保证事件描述的桌内事实成立；如果任意 viewer 可以伪造真人发言或跨桌关系，后续画像和推荐会被污染。类型化边界保留冷启动选桌的预入席需求，同时让其余行为都来自已验证的桌上下文。
- **替代方案**: 只在 API 层做一次校验、允许所有事件作为客户端埋点，或把行为事件完全从持久化文件中排除。
- **代价**: 旧 JSON 中不符合新上下文规则的行为账本需要人工清理或迁移；未来真实账号接入后仍需把成员身份绑定到会话认证。

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
POST /tables/{id}/recompose
POST /tables/{id}/feedback?participant_id={participant_id}
GET  /tables/{id}/feedback?participant_id={participant_id}
GET  /participants/{participant_id}/relationship-memory?viewer_id={participant_id}
POST /participants/{participant_id}/behavior-events?viewer_id={participant_id}
GET  /participants/{participant_id}/behavior-events?viewer_id={participant_id}
POST /tables/{id}/select?participant_id={viewer_id}
POST /tables/{id}/relationships/{related_participant_id}/save?participant_id={viewer_id}
POST /tables/{id}/comments?author_id={author_id}
GET  /tables/{id}/comments
POST /tables/{id}/comments/{comment_id}/promote?participant_id={member_id}
POST /participants/{participant_id}/no-match/{blocked_participant_id}?viewer_id={participant_id}
DELETE /participants/{participant_id}/no-match/{blocked_participant_id}?viewer_id={participant_id}
GET  /participants/{participant_id}/no-match?viewer_id={participant_id}
POST /tables/{id}/safety-reports?reporter_id={reporter_id}
GET  /tables/{id}/safety-reports?reporter_id={reporter_id}
POST /personal-context/source-preview?viewer_id={viewer_id}
PUT  /participants/{participant_id}/personal-context/consent?viewer_id={participant_id}
DELETE /participants/{participant_id}/personal-context/consent?viewer_id={participant_id}
GET  /participants/{participant_id}/personal-context/consent?viewer_id={participant_id}
WS   /ws/tables/{table_id}?participant_id={participant_id}&viewer_mode={participant|observer|commenter}
```

Client events: `human_message`, `participant_joined`, `participant_left`, `participant_consent`, `request_debug_state`。

Server events: `message_committed`, `agent_action`, `table_state_changed`, `grounding_card`, `close_started`, `close_artifact_ready`, `intervention_reflected`, `comment_promoted`。

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
参与层级边界：`observer` 只读且不占席位；`commenter` 只能写独立公共评论，评论不触发主持决策、不进入核心 turn 或状态证据链。
收桌产物边界：关闭前返回 409；关闭后只返回请求参与者自己的 `personal_card`，共享基线可恢复但不包含其他人的个人卡。
行动回响边界：follow-up 只在关闭后可读写；承诺由 owner 回报，建议项首位成员回报后锁定 reporter；结果不改变原始 Table State 或收桌底稿。
不再匹配边界：no-match 关系只能由本人写入/删除/读取；关系对两端对称生效，命中时不允许创建邀请且从当前桌候选预览中过滤；不修改既有桌成员、历史 turn、旧邀请或收桌产物。
举报边界：SafetyReport 只能由当前桌成员自证提交；`report_id` 桌级幂等；举报正文只对举报人本人回读，审核侧通过受控仓储/适配器读取，不向同桌广播，也不自动改写对话状态。
个人授权边界：PersonalContextSource 只接受服务端已授权适配器的规范化信号；`viewer_id` 必须与每条 signal 的 owner 一致；预览只返回本人、默认不落盘，不把 token、关注/收藏原文或个人轨迹广播给其他参与者。
个人 scope 边界：个人 source 预览必须带 scope 且命中本人当前授权；授权/撤回只能由本人操作，撤回立即拒绝后续读取；scope 账本不含 token、不进入 Table State，平台 OAuth 撤权由外部 adapter 负责。
评论升级边界：外围评论默认永远不进入核心 turn；只有当前核心成员显式促成且安全检查通过时才写入 `HumanTurn`，turn 保留 `source_comment_id` 与促成人；重复请求不产生新状态，关闭/软过期/安全暂停或未入席促成均拒绝。
行为层边界：行为事件只能由本人 `viewer_id` 写入或读取；事件类型、桌引用、状态版本、关联参与者和备注均有 schema 上限，真人发言和 follow-up 状态迁移由服务端自动记录；open 桌选择通过专用入口由服务端生成稳定 `table_selected` 事件；follow-up 事件只记录状态摘要，不保存行动备注或完整消息正文；事件不广播给同桌、不进入 Table State。

### 数据模型 / 类型定义

```text
Phase = opening | explore | tension | deepen | close
Action = SILENCE | PASS | PROBE | REFRAME | GROUND | CLOSE
DisagreementType = fact_conflict | causal_disagreement | layer_mismatch |
                   definition_mismatch | value_conflict | experience_gap

TableState(table_id, version, core_question, current_subquestion, phase,
           momentum, close_readiness, insights<=8, consensus<=5,
           disagreements, open_loops<=3, participants, origin_table_id?, conversation,
           intervention, agent)

ConversationState(..., soft_expired, soft_expiry_reason?)

AgentActionEvent(action, target_participant_id?, text?, visual_hint,
                 evidence_turns, state_version, confidence)

HumanTurn(..., message_id?, source_comment_id?)
CommentPromotion(promotion_id, table_id, comment_id, promoter_id,
                 turn_id, state_version, message_id)
AgentPresence(agent_id, display_name, role, status=active|paused|closed)
BehaviorEvent(event_id, participant_id, event_type, table_id,
              state_version?, related_participant_id?, detail?)
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
                                                                                                                  ←── D51 post-close value feedback ledger
                                                                                                                         ←── D52 read-only observer WebSocket
                                                                                                                              ←── D53 peripheral comment ledger
                                                                                                                                     ←── D54 evolved-question table recompose
                                                                                                                                          ←── D55 global no-match preference boundary
                                                                                                                                                ←── D56 safety report ledger and privacy boundary
                                                                                                                                                       ←── D57 authorized personal context source boundary
                                                                                                                                                               ←── D58 personal context consent and scope gate
                                                                                                                                                                       ←── D59 explicit peripheral comment promotion with provenance
                                                                                                                                                                             ←── D60 explicit AgentPresence lifecycle contract
                                                                                                                                                                                   ←── D61 JSON close lifecycle persistence
                                                                                                                                                                                         ←── D62 replay public narrative artifacts
                                                                                                                                                                                                ←── D63 product behavior event ledger
                                                                                                                                                                                                      ←── D64 follow-up behavior event wiring
                                                                                                                                                                                                           ←── D65 source full-lifecycle timeout
                                                                                                                                                                                                                 ←── D66 server-generated table selection event
                                                                                                                                                                                                                       ←── D67 post-close relationship save event
                                                                                                                                                                                                                              ←── D68 behavior event context validation
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
| D51 post-close value feedback ledger | complete | self-scoped post-close four-dimension value feedback with JSON persistence and member-only aggregate summary | 247 tests + compileall + diff check | `72bfed9` |
| D52 read-only observer WebSocket | complete | observer-mode public projection with no seat, turn, invitation, consent, or close mutations | 249 tests + compileall + diff check | `918a5af` |
| D53 peripheral comment ledger | complete | commenter-mode public comments with independent persistence, idempotency, and no core-turn mutation | 253 tests + compileall + diff check | `b484496` |
| D54 evolved-question table recompose | complete | close-only next-table creation with persisted origin link and no automatic member copying | 256 tests + compileall + diff check | `ef544d1` |
| D55 global no-match preference boundary | complete | self-scoped persistent no-match ledger, symmetric invitation rejection and candidate-preview filtering | 261 tests + compileall + diff check | `201d72c` |
| D56 safety report ledger and privacy boundary | complete | self-scoped idempotent reports, persisted for controlled moderation without peer disclosure | 265 tests + compileall + diff check | `3f82db6` |
| D57 authorized personal context source boundary | complete | server-side OAuth/CLI/MCP adapter seam with viewer-only ephemeral personal preview | 271 tests + compileall + diff check | `9d33685` |
| D58 personal context consent and scope gate | complete | self-scoped persistent scope consent, revoke path, and preview enforcement | 273 tests + compileall + diff check | `4e5cc42` |
| D59 explicit peripheral comment promotion | complete | member-triggered safe comment-to-core turn with provenance, privacy-aware fanout, and idempotent JSON persistence | 278 tests + compileall + diff check | `931783d` |
| D60 explicit AgentPresence lifecycle contract | complete | stable public Agent identity outside human participants with safety/expiry/close status and legacy persistence defaults | 280 tests + compileall + diff check | `64b9463` |
| D61 JSON close lifecycle persistence | complete | restart-safe idempotent close snapshot and legacy Agent lifecycle normalization | 281 tests + compileall + diff check | `7965cf1` |
| D62 replay public narrative artifacts | complete | replay response includes interventions, comments, and comment promotion provenance | 281 tests + compileall + diff check | `96aa8c4` |
| D63 product behavior event ledger | complete | self-scoped bounded behavior events with automatic human-message capture, namespaced IDs, and JSON persistence | 284 tests + compileall + diff check | `766cb50` |
| D64 follow-up behavior event wiring | complete | follow-up outcome writes atomically emit self-scoped `follow_up_outcome` events with status-only summaries and transition-aware idempotency | 287 tests + compileall + diff check | `70aaca1` |
| D65 source full-lifecycle timeout | complete | candidate/content/personal command bridges enforce one timeout across process startup, stdin, drain, exit, and cleanup | 290 tests + compileall + diff check | `26abb0d` |
| D66 server-generated table selection event | complete | open-table selection endpoint emits a stable self-scoped `table_selected` behavior event without mutating membership or state | 291 tests + compileall + diff check | `0fb1bbc` |
| D67 post-close relationship save event | complete | closed-table member-only relationship save endpoint emits a stable self-scoped `relationship_saved` event without persistent social-graph writes | 292 tests + compileall + diff check | `732ebde` |
| D68 behavior event context validation | complete | behavior events enforce type-specific table membership/lifecycle rules in memory, API, and JSON reload | 294 tests + compileall + diff check | `0b87fcc` |

## 已知坑位（Running Gotchas）

- 当前前端展示题目是“为什么我们越来越不会休息？”，后端旗舰评测题目是“AI Agent 真正进入企业，卡住的是技术还是采购？”；在 API 联调前需明确采用双 demo table 还是统一题目。
- 本机系统 Python 为 3.14；项目必须声明 3.11+ 兼容范围，避免无意使用 3.14 专属语法。
- API 接入前必须增加独立的 pre-loop SafetyDecision/Enforcement；critical hard violation 不能只依赖主持 Router 的 REFRAME，需能表达暂停、拦截或移出。
