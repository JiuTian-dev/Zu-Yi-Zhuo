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
- `POST /tables/{table_id}/invitations?inviter_id=...`：由桌内成员邀请候选人；候选资料的私有字段不会出现在响应。
- `GET /tables/{table_id}/invitations?participant_id=...`：候选人查看自己的邀请。
- `POST /tables/{table_id}/invitations/{invitation_id}/respond?participant_id=...`：候选人接受或拒绝；接受才新增席位。
- `POST /tables/{table_id}/sync/preview?participant_id=...` → `POST /tables/{table_id}/sync/upgrade?participant_id=...`：预览并执行从异步到同步的升级。
- `WS /ws/tables/{table_id}?participant_id={participant_id}`：实时消息、主持动作、状态和关闭产物。

WebSocket `human_message.message_id` 是单桌幂等键：网络重试时，相同 ID 和内容会返回
`duplicate_message`，不会再次生成 turn、状态快照或主持动作；复用同一 ID 发送不同内容会被拒绝。
安全检查仍在幂等提交前执行，因此未提交的危险消息不会占用消息 ID。

邀请状态为 `pending`、`accepted` 或 `declined`。同一候选人一旦被处理，不能再次收到同桌邀请；
拒绝不会改变桌状态，接受会把候选人和邀请状态作为一次持久化迁移写入 JSON 快照。

桌默认异步。同步升级请求需要 `wants_continue=true`、`sync_extra_value=true`，且至少两位成员已经有
高参与度证据；`discussion_quality`、`external_attention`、`public_value` 只会作为可解释加分信号。

候选资料可设置 `roundtable_invite_preference`：`many`、`few`（默认）或 `none`。选择 `none` 的候选人会
在匹配和邀请边界被跳过。

默认使用内存仓储；设置 `TABLE_REPOSITORY_PATH` 后使用同目录原子 JSON 快照：

```powershell
$env:TABLE_REPOSITORY_PATH = "D:\知乎黑客松\runtime\tables.json"
python -m uvicorn app.main:app
```

Vite 开发源默认允许 `http://localhost:5173` 和 `http://127.0.0.1:5173`，可用逗号分隔的 `CORS_ORIGINS` 覆盖。

## 可选模型 provider

默认演示不调用外部模型。需要接入 OpenAI Responses 时安装可选依赖，并在应用代码中注入 `OpenAIResponsesProvider`：

```powershell
python -m pip install -e ".[openai]"
$env:OPENAI_API_KEY = "..."
$env:OPENAI_MODEL = "gpt-4o-mini"
```

provider 会把结构化结果交给现有的 Pydantic/一次重试/安全回退边界；没有密钥或 SDK 时会显式失败，不会让半成品 Host 事件进入桌面。

## 身份与隐私边界

- 参与者连接握手必须属于该桌；未知 `participant_id` 会收到 `unknown_participant` 并以 1008 关闭。
- REST consent 必须带 `viewer_id`，且必须等于路径中的参与者；当前这是开发态身份声明，不等同于生产认证。
- 未同意时，状态投影隐藏 `declared_position`/`unused_relevant_experience`，PASS 主持话也不会广播经历原文。
- 当前候选人来自显式 `ParticipantSeed` 候选池；没有依赖知乎非官方抓取。接入正式知乎 OAuth/API 前，需要平台提供可核验的授权与资料接口契约。

## 验证

```powershell
python -m pytest -q
python -m compileall -q app tests
git diff --check
```
