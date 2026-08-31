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
- `POST /matches/preview` → `POST /matches/confirm`：先预览公开席位和理由，再创建桌。
- `WS /ws/tables/{table_id}?participant_id={participant_id}`：实时消息、主持动作、状态和关闭产物。

WebSocket `human_message.message_id` 是单桌幂等键：网络重试时，相同 ID 和内容会返回
`duplicate_message`，不会再次生成 turn、状态快照或主持动作；复用同一 ID 发送不同内容会被拒绝。
安全检查仍在幂等提交前执行，因此未提交的危险消息不会占用消息 ID。

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
