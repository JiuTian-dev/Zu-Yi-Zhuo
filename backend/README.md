# 组一桌 Conversation Orchestrator 后端

这是单桌闭环的 FastAPI 后端：真人消息进入后，系统维护 evidence-first Table State，经过安全检查、silence-first Gate、六动作 Router 和 Host，写入可回放的状态快照与 InterventionRecord。

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
- `POST /matches/preview` → `POST /matches/confirm`：先预览公开席位和理由，再创建桌。
- `POST /matches/source-preview`：调用服务端注入的候选 source（知乎 CLI/MCP/OAuth 适配器）后复用同一匹配预览契约。
- `POST /tables/{table_id}/invitations?inviter_id=...`：由桌内成员邀请候选人；候选资料的私有字段不会出现在响应。
- `GET /tables/{table_id}/invitations?participant_id=...`：候选人查看自己的邀请。
- `POST /tables/{table_id}/invitations/{invitation_id}/respond?participant_id=...`：候选人接受或拒绝；接受才新增席位。
- `POST /tables/{table_id}/sync/preview?participant_id=...` → `POST /tables/{table_id}/sync/upgrade?participant_id=...`：预览并执行从异步到同步的升级。
- `POST /tables/{table_id}/soft-expire?participant_id=...`：主题或组合价值下降时软过期桌；桌从默认发现中隐藏，但历史和收桌路径保留。
- `POST /tables/{table_id}/participants/{participant_id}/leave?viewer_id=...`：参与者本人离桌；保留历史快照并立即停止该席位的后续写入。
- `GET /tables/{table_id}/close-artifacts?participant_id=...`：收桌后重新取得共享基线和当前参与者的个人回响卡。
- `GET /tables/{table_id}/follow-ups?participant_id=...`：查询收桌底稿中的行动项及已回报结果。
- `POST /tables/{table_id}/follow-ups/{index}/outcome?participant_id=...`：回报行动结果；承诺只能由 owner 回报，结果会写入 JSON 快照。
- `GET /participants/{participant_id}/relationship-memory?viewer_id=...`：本人查询已收桌中有证据的旧桌友提醒。
- `WS /ws/tables/{table_id}?participant_id={participant_id}`：实时消息、主持动作、状态和关闭产物。

WebSocket `human_message.message_id` 是单桌幂等键：网络重试时，相同 ID 和内容会返回
`duplicate_message`，不会再次生成 turn、状态快照或主持动作；复用同一 ID 发送不同内容会被拒绝。
安全检查仍在幂等提交前执行，因此未提交的危险消息不会占用消息 ID。

邀请状态为 `pending`、`accepted` 或 `declined`。同一候选人一旦被处理，不能再次收到同桌邀请；
拒绝不会改变桌状态，接受会把候选人和邀请状态作为一次持久化迁移写入 JSON 快照。

桌默认异步。同步升级请求需要 `wants_continue=true`、`sync_extra_value=true`，且至少两位成员已经有
高参与度证据；`discussion_quality`、`external_attention`、`public_value` 只会作为可解释加分信号。
桌最多 5 个席位；少于 4 人的桌可以先建立并通过追加参与者或接受邀请逐步补齐，满桌后新入席会返回 409。

软过期是可回放的幂等状态迁移：请求需要桌内成员身份和非空原因，状态会记录 `soft_expiry_reason`。
软过期后拒绝新消息、成员变更、邀请、同步升级、主持/安全快照和来源卡片写入，WebSocket 返回
`table_soft_expired`；`GET /tables/{id}`、回放、行动回响和收桌仍可用，收桌后仍保留软过期标记。

候选资料可设置 `roundtable_invite_preference`：`many`、`few`（默认）或 `none`。选择 `none` 的候选人会
在匹配和邀请边界被跳过。

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
- 成员离席后，仍未关闭的旧连接也会在每条真人消息进入安全检查前重新校验席位；不会因为 stale socket 写入安全暂停或消息快照。
- 成员也可通过自证的 REST leave 入口离桌；离桌会产生一个版本化成员快照，旧连接后续消息会返回 `unknown participant`。
- REST consent 必须带 `viewer_id`，且必须等于路径中的参与者；当前这是开发态身份声明，不等同于生产认证。
- 未同意时，状态投影隐藏 `declared_position`/`unused_relevant_experience`，PASS 主持话也不会广播经历原文。
- 当前默认没有候选 source，候选人仍可由显式 `ParticipantSeed` 候选池提供；没有依赖知乎非官方抓取。
- 可选 `CommandCandidateSource` 为官方/获授权的 CLI、MCP 或 OAuth wrapper 提供 stdin/stdout 接入；命令不经 shell，默认 5 秒超时和 1 MB 输出上限，后端只接收规范化 `ParticipantSeed`。
- 接入正式知乎 CLI/MCP/OAuth 时，通过 `create_app(..., candidate_source=...)` 注入适配器，适配器只返回已授权、规范化候选资料，服务端不会接收或记录 access token。
- 外部 source 调用默认有 5 秒超时；可在 `create_app(..., candidate_source_timeout_seconds=...)` 注入不同正数。超时统一返回通用 502，不会回退到未经授权的候选。
- 软过期桌不再出现在默认 `GET /tables`；使用 `include_closed=true` 可在历史/运营视图中看到它，且仍按 viewer 做隐私投影。
- 关系记忆只从已收桌状态的 `worth_continuing_with` 证据派生；本人身份通过 `viewer_id` 自证，响应只含旧桌问题、对方公开姓名、理由和证据定位，不含私有画像或个人卡全文。
- 行动回响只在收桌后开放，状态为 `completed`、`in_progress`、`blocked` 或 `dismissed`；原始收桌底稿保持不变，结果单独持久化并可在重启后恢复。

## 验证

```powershell
python -m pytest -q
python -m compileall -q app tests
git diff --check
```
