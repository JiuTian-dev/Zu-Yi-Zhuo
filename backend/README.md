# 组一桌 Conversation Orchestrator 后端

这是单桌闭环的 FastAPI 后端：真人消息进入后，系统维护 evidence-first Table State，经过安全检查、silence-first Gate、六动作 Router 和 Host，写入可回放的状态快照与 InterventionRecord。每张桌还公开携带固定的“圆桌 Agent”角色；它不占真人席位，但会随安全暂停、软过期和收桌进入对应生命周期。

## 本地运行

```powershell
cd D:\知乎黑客松\backend
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload
```

启动后可用：

- `GET /healthz`：进程存活探针。
- `GET /readyz`：仓储就绪探针。
- `GET /tables?participant_id=...&include_closed=false`：首页桌发现；默认只列出未关闭桌，并按 viewer 做隐私投影。
- `POST /opportunities/preview`：从已获授权的公开问题/回答/文章信号中提取核心问题、未完成性证据、角色缺口和候选种子；不创建桌。
- `POST /opportunities/source-preview`：调用服务端注入的公开内容 source 获取信号，再运行机会预览；不创建桌或邀请。
- `POST /personal-context/source-preview?viewer_id=...`：调用服务端注入的用户授权个人 source，生成本人可见的兴趣/表达主题预览；不创建桌、不广播、不落盘。
- `PUT/GET/DELETE /participants/{participant_id}/personal-context/consent?viewer_id=...`：本人授予、查看或撤回个人层 scope（`profile`、`follows`、`favorites`、`public_content`）。
- `POST /matches/preview` → `POST /matches/confirm`：先预览公开席位和理由，再创建桌。
- `POST /matches/source-preview`：调用服务端注入的候选 source（知乎 CLI/MCP/OAuth 适配器）后复用同一匹配预览契约。
- `POST /tables/{table_id}/invitations?inviter_id=...`：由桌内成员邀请候选人；候选资料的私有字段不会出现在响应。
- `GET /tables/{table_id}/invitations?participant_id=...`：候选人查看自己的邀请。
- `POST /tables/{table_id}/invitations/{invitation_id}/respond?participant_id=...`：候选人接受或拒绝；接受才新增席位。
- `POST /tables/{table_id}/sync/preview?participant_id=...` → `POST /tables/{table_id}/sync/upgrade?participant_id=...`：预览并执行从异步到同步的升级。
- `POST /tables/{table_id}/soft-expire?participant_id=...`：主题或组合价值下降时软过期桌；桌从默认发现中隐藏，但历史和收桌路径保留。
- `POST /tables/{table_id}/participants/{participant_id}/leave?viewer_id=...`：参与者本人离桌；保留历史快照并立即停止该席位的后续写入。
- `POST /tables/{table_id}/candidate-preview?participant_id=...`：桌内成员按当前问题请求候选 source，返回角色缺口和有理由的公开候选推荐；不修改桌状态、不创建邀请、不自动入席。
- `GET /tables/{table_id}/close-artifacts?participant_id=...`：收桌后重新取得共享基线和当前参与者的个人回响卡。
- `GET /tables/{table_id}/follow-ups?participant_id=...`：查询收桌底稿中的行动项及已回报结果。
- `POST /tables/{table_id}/follow-ups/{index}/outcome?participant_id=...`：回报行动结果；承诺只能由 owner 回报，结果会写入 JSON 快照。
- `POST /tables/{table_id}/feedback?participant_id=...`：收桌后提交或更新认知、关系、行动、情绪四类 1–5 分价值反馈。
- `GET /tables/{table_id}/feedback?participant_id=...`：桌内成员查看匿名价值聚合；不返回他人的评分明细或备注。
- `POST /tables/{table_id}/comments?author_id=...` / `GET /tables/{table_id}/comments`：外围评论独立账本；评论不占席位、不进入核心 turn。
- `POST /tables/{table_id}/comments/{comment_id}/promote?participant_id=...`：核心成员显式促成一条评论；服务端重新做安全检查，成功后以促成人身份写入主桌 turn，并保留 `source_comment_id` 和可回放的 `CommentPromotion`。
- `POST /participants/{participant_id}/no-match/{blocked_participant_id}?viewer_id=...`、`DELETE ...`、`GET /participants/{participant_id}/no-match?viewer_id=...`：本人管理“不再匹配”偏好；关系双向约束邀请和动态候选预览。
- `POST /tables/{table_id}/safety-reports?reporter_id=...` / `GET /tables/{table_id}/safety-reports?reporter_id=...`：桌内成员提交或查询自己的举报；举报正文不广播给同桌，账本供受控审核适配器读取。
- `POST /tables/{table_id}/recompose`：从已收桌的进化问题创建下一桌；参与者必须重新选择，不自动复制旧桌成员，并在新状态记录 `origin_table_id`。
- `GET /participants/{participant_id}/relationship-memory?viewer_id=...`：本人查询已收桌中有证据的旧桌友提醒。
- `WS /ws/tables/{table_id}?participant_id={participant_id}`：参与者实时收发消息、主持动作、状态和关闭产物。
- `WS /ws/tables/{table_id}?participant_id={viewer_id}&viewer_mode=observer`：只读旁听；立即收到公开状态和后续桌面事件，但不占席位、不写入消息或状态。
- `WS /ws/tables/{table_id}?participant_id={viewer_id}&viewer_mode=commenter`：外围评论连接；只接受 `peripheral_comment`，评论可由核心成员通过 REST 显式促成。

WebSocket `human_message.message_id` 是单桌幂等键：网络重试时，相同 ID 和内容会返回
`duplicate_message`，不会再次生成 turn、状态快照或主持动作；复用同一 ID 发送不同内容会被拒绝。评论促成同样按
`(table_id, comment_id)` 幂等，重复请求不生成新 turn/state。
安全检查仍在幂等提交前执行，因此未提交的危险消息不会占用消息 ID。

邀请状态为 `pending`、`accepted` 或 `declined`。同一候选人一旦被处理，不能再次收到同桌邀请；
拒绝不会改变桌状态，接受会把候选人和邀请状态作为一次持久化迁移写入 JSON 快照。

桌默认异步。同步升级请求需要 `wants_continue=true`、`sync_extra_value=true`，且至少两位成员已经有
高参与度证据；`discussion_quality`、`external_attention`、`public_value` 只会作为可解释加分信号。
真人桌最多 5 个席位，圆桌 Agent 作为独立的第六个公开角色不计入上限；少于 4 人的桌可以先建立并通过追加参与者或接受邀请逐步补齐，满桌后新入席会返回 409。

软过期是可回放的幂等状态迁移：请求需要桌内成员身份和非空原因，状态会记录 `soft_expiry_reason`。
软过期后拒绝新消息、成员变更、邀请、同步升级、主持/安全快照和来源卡片写入，WebSocket 返回
`table_soft_expired`；`GET /tables/{id}`、回放、行动回响和收桌仍可用，收桌后仍保留软过期标记。
收桌迁移在内存和 JSON 仓储中都原子持久化；重启后仍可读取关闭状态、收桌卡和行动回响，重复收桌不增加版本。

候选资料可设置 `roundtable_invite_preference`：`many`、`few`（默认）或 `none`。选择 `none` 的候选人会
在匹配和邀请边界被跳过。

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
`ParticipantSeed`，命令超时、非零退出、输出过大或字段不合法都会 fail-closed 为 502：

```powershell
$env:CANDIDATE_SOURCE_COMMAND = '["D:\\adapters\\zhihu-candidates.exe"]'
python -m uvicorn app.main:app
```

wrapper 自己负责知乎授权和 token 管理；不要把 secret、Cookie 或 MCP 配置交给浏览器或前端。

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

动态补位预览会过滤现有参与者、已被邀请过的候选人以及明确选择 `none` 的候选人；返回的 `open_seats`、`role_gaps`
和候选理由只用于成员选择，仍需通过现有邀请接口逐个发出邀请，候选人接受后才会新增席位。

机会预览只接受公开 source signal（问题/回答/文章标题、摘要、公开作者角色和公开立场），信号数量最多 20、
至少覆盖 2 位作者。输出的 `signal_ids` 和 `unfinishedness` 可回溯到原始来源；候选人仍需经过
`/matches/preview` 的席位与邀请偏好校验后才能建桌。

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
- 举报接口只允许当前桌成员自证提交，目标必须是同桌另一名成员；`report_id` 桌级幂等。举报人只能读取自己的举报，完整账本不通过公共 API 暴露，避免被举报对象或旁听者反向读取。
- 成员离席后，仍未关闭的旧连接也会在每条真人消息进入安全检查前重新校验席位；不会因为 stale socket 写入安全暂停或消息快照。
- 成员也可通过自证的 REST leave 入口离桌；离桌会产生一个版本化成员快照，旧连接后续消息会返回 `unknown participant`。
- REST consent 必须带 `viewer_id`，且必须等于路径中的参与者；当前这是开发态身份声明，不等同于生产认证。
- 未同意时，状态投影隐藏 `declared_position`/`unused_relevant_experience`，PASS 主持话也不会广播经历原文。
- 当前默认没有候选 source，候选人仍可由显式 `ParticipantSeed` 候选池提供；没有依赖知乎非官方抓取。
- 可选 `CommandCandidateSource` 为官方/获授权的 CLI、MCP 或 OAuth wrapper 提供 stdin/stdout 接入；命令不经 shell，默认 5 秒超时和 1 MB 输出上限，后端只接收规范化 `ParticipantSeed`。
- 可选 `CommandContentSignalSource` 为机会发现接入同样的官方/获授权 wrapper；后端只接收 `visibility=public` 的规范化 `ContentSignal`，不会把原始 token 或私有行为写入桌状态。
- 可选 `CommandPersonalContextSource` 为用户授权个人层接入官方/获授权 wrapper；后端只接受 `visibility=private` 且 owner 与 viewer 一致的 `PersonalContextSignal`，预览响应只回给该 viewer，默认不持久化。
- 接入正式知乎 CLI/MCP/OAuth 时，通过 `create_app(..., candidate_source=...)` 注入适配器，适配器只返回已授权、规范化候选资料，服务端不会接收或记录 access token。
- 外部 source 调用默认有 5 秒超时；可在 `create_app(..., candidate_source_timeout_seconds=...)` 注入不同正数。超时统一返回通用 502，不会回退到未经授权的候选。
- 软过期桌不再出现在默认 `GET /tables`；使用 `include_closed=true` 可在历史/运营视图中看到它，且仍按 viewer 做隐私投影。
- 关系记忆只从已收桌状态的 `worth_continuing_with` 证据派生；本人身份通过 `viewer_id` 自证，响应只含旧桌问题、对方公开姓名、理由和证据定位，不含私有画像或个人卡全文。
- 行动回响只在收桌后开放，状态为 `completed`、`in_progress`、`blocked` 或 `dismissed`；原始收桌底稿保持不变，结果单独持久化并可在重启后恢复。
- 价值反馈只在收桌后开放，参与者可更新自己的单条反馈；聚合返回响应人数、四类价值均值和愿意再次参加人数，且不改变 Table State 或收桌底稿。JSON 仓储会为旧数据缺省空反馈账本。

## 验证

```powershell
python -m pytest -q
python -m compileall -q app tests
git diff --check
```
