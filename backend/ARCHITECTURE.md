# 组一桌后端架构

更新时间：2026-09-04
适用范围：`D:\知乎黑客松\backend`

这份文档只描述后端当前代码，不把前端表现、3D 场景或还没有拿到的知乎 OAuth 能力写成已完成。

## 先看结论

后端是一个单体 FastAPI 服务。它以 `TableState` 为每张桌的核心事实，REST 和 WebSocket 都通过同一个仓储完成状态迁移；主持决策、安全、匹配和收桌产物都在服务端生成，前端只负责展示和发起操作。

```text
React / 3D 前端
      │
      ├── REST：发现、匹配、入席、授权、回放、收桌后的回响
      └── WebSocket：真人发言、Agent 动作、状态广播、旁听、外围评论
      │
      ▼
FastAPI（app/main.py）
      │  启动配置、依赖注入、CORS、能力探针
      ▼
API 适配层（app/api/app.py + websocket.py）
      │  身份校验、参数校验、隐私投影、限流、事件广播
      ▼
业务模块
      ├── orchestrator：安全 → Observer → Gate → Router → Host → Reflection
      ├── matching / opportunities：匹配、机会发现、动态补位
      ├── lobby / intake / personal：入席前信息、主动需求、个人上下文
      └── comment_curation / recommendations：外围评论和后续推荐
      │
      ▼
仓储（app/api/repository.py）
      ├── TableState 版本快照
      ├── 真人消息和主持干预账本
      ├── 邀请、申请、评论、举报、反馈、行动回响
      └── 个人行为、收藏、来源快照和授权同意
      │
      ├── 默认：进程内存
      └── 可选：JSON 快照 + SQLite 协调文件

外部边界（可选）
├── 知乎/其他平台 source：规范化 JSON → ParticipantSeed / ContentSignal
├── LLM provider：只改写 Host 文字，不改变决策
└── Zhihu OAuth coordinator：服务端换 token、加密存储、会话身份
```

## 1. 后端负责什么

### 后端负责

- 保存每张桌的事实状态、版本和可回放历史。
- 处理匹配、入席、邀请、申请、旁听和动态补位。
- 让真人消息经过安全检查和 evidence-first 状态更新。
- 决定 Agent 是否发言，以及六种主持动作：`SILENCE`、`PASS`、`PROBE`、`REFRAME`、`GROUND`、`CLOSE`。
- 生成收桌后的共享基线、个人回响卡、行动项、价值反馈和问题谱系。
- 对 REST 和 WebSocket 执行身份、隐私、幂等、限流和状态边界。
- 在配置了授权 source 时，接收已经规范化的知乎公开内容或个人上下文。

### 后端不负责

- 不渲染 3D 场景，不保存相机位置，也不处理鼠标拖拽和滚轮缩放。
- 不把前端提交的 disagreement、来源卡或 Agent 决策当成事实。
- 不在没有后端数据时伪造正式知乎用户身份。
- 不把 LLM 当成状态机；模型最多参与安全边界内的文字改写或可替换的辅助任务。

## 2. 启动入口与依赖装配

### `backend/app/main.py`

`app/main.py` 是部署入口，`uvicorn app.main:app` 导入时完成一次应用装配：

1. 根据 `TABLE_REPOSITORY_PATH` 选择 `InMemoryTableRepository` 或 `JsonTableRepository`。
2. 根据 `CONVERSATION_PROVIDER` 选择确定性模式或可选的 OpenAI Responses provider。
3. 根据三类 source 配置选择命令适配器或 HTTPS JSON 适配器。
4. 根据 OAuth 环境变量决定是否创建 `ZhihuOAuthService`。
5. 把仓储、provider、source、身份解析器、事件总线和限流器注入 `create_app()`。

`create_app()` 位于 `backend/app/api/app.py`，它是实际的 composition root。除了注册路由，还会建立：

- CORS 中间件。
- REST 写请求限流器。
- source-match 和候选邀请短期票据存储。
- 主动需求澄清会话存储。
- WebSocket 本地连接表、桌级锁和可选跨进程事件总线。
- 可选 OAuth 路由和 OAuth 身份解析器。

### 常用配置

| 配置 | 默认行为 | 作用 |
| --- | --- | --- |
| `TABLE_REPOSITORY_PATH` | 不设置，内存 | JSON 桌状态快照；设置后支持重启恢复 |
| `SHARED_EPHEMERAL_STORE_PATH` | 不设置，内存 | SQLite 保存短期票据和主动需求会话 |
| `EVENT_BUS_PATH` | 不设置，进程内广播 | SQLite 公共事件总线，供多 worker 转发 |
| `SHARED_RATE_LIMIT_PATH` | 不设置，进程内限流 | SQLite 共享 REST 限流窗口 |
| `CONVERSATION_PROVIDER` | `deterministic` | `openai` 只在明确配置时启用 |
| `CANDIDATE_SOURCE_COMMAND/URL` | 未配置 | 候选人来源 |
| `CONTENT_SIGNAL_SOURCE_COMMAND/URL` | 未配置 | 公开内容和 Grounding 来源 |
| `PERSONAL_CONTEXT_SOURCE_COMMAND/URL` | 未配置 | 用户授权后的个人上下文来源 |
| `CORS_ORIGINS` | 本地 5173 | REST 跨域来源 |
| `WS_ALLOWED_ORIGINS` | 未设置时兼容本地 Demo | WebSocket Origin 白名单 |
| `WS_MAX_FRAME_BYTES` | 64 KiB | 单个 WebSocket 文本帧上限 |
| `WS_MAX_EVENTS_PER_MINUTE` | 120 | 单连接入站事件限速 |
| `REST_MAX_MUTATIONS_PER_MINUTE` | 600 | REST 写请求限速 |
| `SYNC_WINDOW_SECONDS` | 1800 秒 | 同步围炉的服务端有效期 |

OAuth 还需要 `ZHIHU_APP_ID`、`ZHIHU_APP_KEY`、`ZHIHU_OAUTH_REDIRECT_URI`、`ZHIHU_OAUTH_ENCRYPTION_KEY` 和相应存储配置。没有完整配置时，OAuth 路由不会注册。

## 3. 代码分层

当前代码是“单体 + 明确模块边界”，不是微服务，也不是严格的 Clean Architecture。路由编排集中在 `app/api/app.py`，但状态模型、决策逻辑和外部适配器已经分开。

### 入口和适配层

| 目录/文件 | 作用 |
| --- | --- |
| `app/main.py` | 部署入口和环境变量装配 |
| `app/api/app.py` | FastAPI、REST 路由、请求模型、业务依赖编排 |
| `app/api/websocket.py` | WebSocket 协议、连接管理、桌级锁、状态/事件广播 |
| `app/api/identity.py` | 可注入的用户身份和审核员身份边界 |
| `app/api/privacy.py` | 按 viewer 生成 `TableState` 投影 |
| `app/api/intervention.py` | 主持干预审计记录构造 |
| `app/api/nudge.py` | 冷启动递话复用服务 |
| `app/api/match_tickets.py` | source 匹配和候选邀请的短期、单次票据 |
| `app/api/intent_sessions.py` | 主动需求澄清会话及 SQLite 版本 |
| `app/api/rate_limit.py` | 进程内和 SQLite REST 限流 |
| `app/api/event_bus.py` | 可选 SQLite 公共事件总线 |

### 领域模型

`app/domain/schemas.py` 和 `app/domain/enums.py` 定义 Pydantic 契约。关键对象如下：

- `TableState`：桌的当前版本快照。
- `ParticipantState`：真人成员在桌内的公开状态。
- `ConversationState`：讨论阶段、安全级别、异步/同步、关闭和软过期状态。
- `InterventionState`：Agent 上次动作、推荐动作、沉默/发言理由和冷却计数。
- `AgentPresence`：固定的圆桌 Agent 公共席位，不计入 5 个真人席位。
- `HumanTurn`：已经提交的真人消息。
- `InterventionRecord`：主持动作及其证据、模型、耗时、反思结果和 Grounding 卡。
- `ParticipantSeed`：建桌/匹配阶段的候选资料，包含公开字段和有限的公开来源 ID。
- `ContentSignal`：公开内容来源信号；`PersonalContextSignal` 是本人授权、本人可见的私有信号。
- `SharedBaseline`、`PersonalCard`、`FollowUpItem`：收桌产物和行动回响。

所有契约模型都禁止未声明字段。很多模型还验证 ID 唯一、证据 turn 存在、来源属于允许范围、个人信号属于当前 viewer 等边界。

## 4. `TableState` 是怎样工作的

一张桌不是一行不断覆盖的记录，而是一组按 `version` 递增的快照：

```text
version 0  建桌
    │
version 1  真人消息 → Observer 更新成员立场/阶段
    │
version 2  Agent 非 SILENCE 动作 → 记录干预和证据
    │
version 3  新消息或安全暂停
    │
version N  收桌 / 软过期 / 同步到期 / 受控恢复
```

`InMemoryTableRepository` 内部按桌保存：

- `states[table_id]`：所有 `TableState` 快照。
- `turns[table_id]`：真人消息。
- `interventions[table_id]`：非 `SILENCE` 主持审计。
- 邀请、加入申请、行动结果、价值反馈、外围评论和促成记录。
- no-match、账号邀桌偏好、个人授权同意、行为事件和收藏。
- 安全举报及审核审计、安全处置、安全 strike。
- 公开来源快照和当前待消费的 trusted Grounding 卡。

仓储返回深拷贝，调用者不能直接改掉内部状态。所有状态迁移都检查：桌是否关闭、是否软过期、参与者是否存在、版本是否正好递增、票据是否仍有效。

### JSON 仓储

`JsonTableRepository` 继承内存仓储，保留同一组方法和契约，额外把状态写入 JSON：

- 顶层读写前刷新磁盘快照。
- 使用同目录 sibling lock 文件串行化跨进程读改写。
- 通过临时文件和原子替换保存。
- 旧快照字段缺失时按兼容规则加载，非法快照直接失败。

这是当前项目的轻量部署实现，不等同于生产级关系数据库。多 worker 还需要配合 SQLite 短期存储、事件总线和共享限流。

## 5. 一条真人消息的完整路径

WebSocket 的 `human_message` 是核心写入路径：

```text
客户端发送 human_message(message_id, participant_id, text)
        │
        ▼
Origin / 身份 / JSON frame / 连接限速检查
        │
        ▼
校验成员、关闭状态、软过期和 critical 安全暂停
        │
        ▼
evaluate_safety(text)
  ├── 普通消息：继续
  ├── 气氛升温：消息仍可落账，广播 soft intervention
  ├── 首次人身边界：只给发送者私下提醒
  └── 重复或明确高风险：写入安全暂停快照
        │
        ▼
repository.append_message_once()
  ├── message_id 幂等检查
  ├── 生成服务端 turn_id
  ├── observe_turn() 生成新的 TableState
  └── 同一事务写入真人行为事实和状态快照
        │
        ▼
decide_intervention()
  ├── refresh_close_readiness
  ├── Gate：是否值得打断自然讨论
  └── Router：选择六种动作之一
        │
        ▼
Host 生成确定性动作和文字
  └── 可选 provider 只改写文字，不接触私有 TableState
        │
        ▼
record_intervention() + append_intervention_bundle()
  ├── 写入下一个状态版本
  ├── 写入 InterventionRecord
  └── GROUND 时原子消费 trusted card
        │
        ▼
广播 message_committed / agent_action / grounding_card / state
```

### Observer

`app/orchestrator/observer.py` 是当前确定性状态观察器。它从真人 turn 推导：

- 当前发言者的立场、参与度、贡献和最后发言 turn。
- 讨论阶段、动量、当前子问题和 open loop。
- 技术层与采购层的 `LAYER_MISMATCH`。
- 同一窄事实主题下的明确相反断言 `FACT_CONFLICT`。

客户端不能自己提交 disagreement、evidence turn 或来源。后端只接受真人文字，再由 Observer 产生这些结构化状态。

### Gate / Router / Host

- Gate 默认沉默，只有存在可解释的高价值候选并且有 turn 证据时才允许发言。
- Router 只做动作选择，不生成文字。
- Host 负责把动作变成给用户看的短句和 `visual_hint`。
- `GROUND` 必须使用后端 trusted card；没有卡时会降级为 `PROBE`，不会编造来源或事实。
- Provider 不可以修改 Gate、Router、Safety 或证据；失败时使用确定性文字或旧值。

## 6. REST API 按产品能力分组

路由全部注册在 `app/api/app.py`，OAuth 路由由 `app/auth/zhihu.py` 在配置齐全时额外注册。

### 运行探针

```text
GET  /healthz
GET  /readyz
GET  /capabilities
```

`/capabilities` 只返回仓储类型、provider 类型、三类 source 是否配置、OAuth 是否配置、WebSocket 是否可用和 5 席上限，不返回 token、命令、密钥或身份。

### 建桌、发现和入席前 Lobby

```text
POST /tables
GET  /tables
GET  /tables/discovery
GET  /tables/{table_id}
GET  /tables/{table_id}/state
GET  /tables/{table_id}/lobby
POST /tables/{table_id}/lobby-fit
POST /tables/{table_id}/select
```

`/tables/discovery` 和 `/lobby` 是公开读模型，不返回完整消息、私有资料或邀请队列。`/select` 只记录本人主动选择，不会自动入席。

### 匹配、机会发现和主动需求

```text
POST /opportunities/preview
POST /opportunities/source-preview
POST /intents/preview

POST /matches/preview
POST /matches/confirm
POST /matches/source-preview
POST /matches/source-confirm

POST /participants/{participant_id}/intent-sessions
GET  /participants/{participant_id}/intent-sessions/{session_id}
POST /participants/{participant_id}/intent-sessions/{session_id}/turns
POST /participants/{participant_id}/intent-sessions/{session_id}/source-preview
DELETE /participants/{participant_id}/intent-sessions/{session_id}
```

规则是“先预览，再确认”：source 预览给浏览器的是短期不透明票据，确认时由服务端 claim/consume，避免浏览器提交私有候选资料或重复调用 source。主动需求澄清不自动建桌、邀请或入席。

### 成员、申请、邀请和偏好

```text
POST /tables/{table_id}/participants
POST /tables/{table_id}/participants/{participant_id}/leave
POST /tables/{table_id}/join-requests
GET  /tables/{table_id}/join-requests
POST /tables/{table_id}/join-requests/{request_id}/approve
POST /tables/{table_id}/join-requests/{request_id}/decline

POST /tables/{table_id}/invitations
POST /tables/{table_id}/invitations/from-preview
GET  /tables/{table_id}/invitations
GET  /participants/{participant_id}/invitations
POST /tables/{table_id}/invitations/{invitation_id}/respond

GET  /participants/{participant_id}/invitation-preference
PUT  /participants/{participant_id}/invitation-preference
PUT  /tables/{table_id}/participants/{participant_id}/invitation-preference
POST /tables/{table_id}/participants/{participant_id}/consent
POST /tables/{table_id}/sync/preview
POST /tables/{table_id}/sync/upgrade
POST /tables/{table_id}/soft-expire
GET  /tables/{table_id}/recruitment
POST /tables/{table_id}/candidate-preview
```

服务端硬限制真人最多 5 人。动态补位只生成候选推荐和邀请票据，不会自动加人；候选人接受邀请后才新增席位。旁听连接不占真人席位。

### 桌内消息、评论和主持能力

```text
POST /tables/{table_id}/grounding
POST /tables/{table_id}/nudge
POST /tables/{table_id}/comments
GET  /tables/{table_id}/comments
GET  /tables/{table_id}/comment-promotion-candidates
POST /tables/{table_id}/comments/{comment_id}/promote
```

外围评论有独立账本，不直接进入核心 turn。只有核心成员显式促成后，评论才会以真人 turn 写入桌内，并保留 `source_comment_id`。

### 回放、收桌和问题飞轮

```text
GET  /tables/{table_id}/replay
GET  /tables/{table_id}/lineage
GET  /tables/{table_id}/interventions
GET  /tables/{table_id}/close-artifacts
GET  /tables/{table_id}/follow-ups
POST /tables/{table_id}/follow-ups/{follow_up_index}/outcome
GET  /tables/{table_id}/evaluation
POST /tables/{table_id}/feedback
GET  /tables/{table_id}/feedback
POST /tables/{table_id}/close
POST /tables/{table_id}/recompose
```

`/replay` 返回真人消息、状态快照、主持干预、评论、评论促成和已经保存的公开来源信号。收桌卡由服务端从状态和 turn 证据派生，个人卡按当前成员定向返回。

### 个人行为和关系边界

```text
GET  /participants/{participant_id}/relationship-memory
GET  /participants/{participant_id}/question-footprint
GET  /participants/{participant_id}/action-echoes
POST /participants/{participant_id}/behavior-events
GET  /participants/{participant_id}/behavior-events
DELETE /participants/{participant_id}/behavior-events
GET  /participants/{participant_id}/table-recommendations
PUT  /participants/{participant_id}/saved-tables/{table_id}
DELETE /participants/{participant_id}/saved-tables/{table_id}
GET  /participants/{participant_id}/saved-tables
POST /tables/{table_id}/relationships/{related_participant_id}/save
POST /participants/{participant_id}/no-match/{blocked_participant_id}
DELETE /participants/{participant_id}/no-match/{blocked_participant_id}
GET  /participants/{participant_id}/no-match
```

这些数据默认只对本人可见。行为账本可以由本人清除，但不会回删真人消息、状态快照、安全审计或收藏列表。

### 安全和审核

```text
POST  /tables/{table_id}/safety-reports
GET   /tables/{table_id}/safety-reports
GET   /tables/{table_id}/safety-reports/moderation
GET   /tables/{table_id}/safety-reports/{report_id}/history
PATCH /tables/{table_id}/safety-reports/{report_id}
POST  /tables/{table_id}/safety/resolve
GET   /tables/{table_id}/safety/resolutions
```

普通成员只能提交和查看自己的举报；审核队列、举报状态迁移和安全恢复需要注入 `moderator_resolver`。客户端不能在请求体里自报审核员身份。

## 7. WebSocket 协议

入口：

```text
WS /ws/tables/{table_id}?participant_id={id}&viewer_mode=participant
WS /ws/tables/{table_id}?participant_id={id}&viewer_mode=observer
WS /ws/tables/{table_id}?participant_id={id}&viewer_mode=commenter
```

### 入站事件

| 事件 | 权限 | 是否改桌 |
| --- | --- | --- |
| `human_message` | participant | 是，写 turn 和状态 |
| `participant_joined` | participant | 只广播当前状态 |
| `participant_left` | participant | 是，原子移除席位 |
| `participant_consent` | participant | 是，更新资料授权 |
| `participant_invitation_preference` | participant | 是，更新当前席位偏好 |
| `request_nudge` | participant | 是，可能生成 Agent 动作 |
| `request_close` | participant | 是，收桌并返回个人卡 |
| `peripheral_comment` | commenter | 是，写外围评论账本 |
| `request_debug_state` | 所有连接 | 否，只返回当前投影 |

Observer 只能读状态和桌面事件；commenter 只能写外围评论。每桌有 `asyncio.Lock` 串行处理写入，避免两条消息同时计算出相同的 turn 或状态版本。

### 出站事件

常用事件包括：

```text
table_state_changed
message_committed
agent_action
grounding_card
intervention_reflected
safety_soft_intervention
safety_private_reminder
safety_enforced
participant_consent_changed
participant_invitation_preference_changed
table_mode_changed
close_started
close_artifact_ready
peripheral_comment
```

状态事件使用 `project_state_for_viewer()` 重新投影。也就是说，同一张桌的成员、旁听者和不同权限连接收到的状态内容可能不同；公共事件总线只转发公开事件和状态版本提示，不转发个人卡、私有资料或 token。

## 8. 身份、隐私和安全边界

### 身份模式

身份解析器是可注入的函数：

- 未注入时：本地 Demo 继续接受显式 `viewer_id` / `participant_id`，便于联调。
- 注入后：URL query 或 WebSocket 参数只是声明值，服务端会拿可信 session subject 进行比对。
- 不匹配返回 403，无会话返回 401。
- 审核员使用独立 `moderator_resolver`，不复用普通参与者身份。

当前 OAuth coordinator 生成的是服务端内部 `session-*` 主体。知乎官方稳定用户 ID 和用户信息字段尚未完成最终确认，因此不能把它写成正式知乎账号绑定。

### 隐私投影

`app/api/privacy.py` 是统一出口。它会把内部状态裁剪成 viewer 能看的状态：

- Lobby/发现只给公开成员摘要、阶段、问题、空席和来源 ID。
- 成员能看到当前桌的成员状态，但私有资料仍受 consent 控制。
- 个人卡、个人上下文信号和行为账本只给本人。
- 回放要求生产身份下的当前桌内成员；早期快照里没有该 viewer 时仍可以从桌内身份读取整桌回放。
- 安全 strike、审核举报正文、OAuth token 永远不进入公开投影。

### 写入保护

- WebSocket 消息用 `message_id` 幂等；同 ID 的不同内容会被拒绝。
- source 预览票据有 TTL、绑定用途/桌/邀请人并且单次消费。
- WebSocket frame、消息长度、入站事件和 REST 写请求都有上限。
- 状态广播版本单调递增，旧状态不会覆盖新状态。
- source 超时、非 2xx、超大响应、非法 JSON 都 fail-closed。
- GROUND 资料必须是服务端暂存的 trusted card，不能由客户端伪造。

## 9. 外部数据和 provider 接入

### Source 适配器

后端只依赖三个协议：

```python
CandidateSource.search(query, limit) -> Sequence[ParticipantSeed]
ContentSignalSource.search(query, limit) -> Sequence[ContentSignal]
PersonalContextSource.search(viewer_id, scopes, query, limit) -> Sequence[PersonalContextSignal]
```

实现有两类：

1. `Command*Source`：以无 shell 子进程运行外部 CLI/MCP/OAuth wrapper，用 stdin/stdout 传 JSON，限制超时和输出大小。
2. `Http*Source`：向服务端配置的 HTTPS JSON gateway 发 POST，token 只放 `Authorization: Bearer` 请求头，不进入 URL、日志和错误正文。

`backend/adapters/zhihu_source.py` 是一个适配器示例：它把知乎官方公开搜索或单账号联调结果归一化成后端契约。它不把知乎原始响应直接暴露给前端，也不是多用户 OAuth 服务。

### Provider

`LLMProvider` 只有结构化输出和文本输出两个抽象。默认 `deterministic` 不访问外部模型；`OpenAIResponsesProvider` 是可选实现。

Provider 的安全边界：

- Gate、Router、Safety 和证据由确定性代码决定。
- Host 只把公开问题、当前子问题和确定性草稿交给文字 provider。
- provider 返回空值、越界文字或调用失败时，使用安全 fallback。
- 结构化 provider 失败两次后优先使用旧的已验证值或显式 fallback。

## 10. 知乎 OAuth 当前状态

OAuth 是后端的可选能力，不是默认启动依赖。代码在 `app/auth/zhihu.py`：

```text
GET  /auth/zhihu/start
GET  /auth/zhihu/callback
GET  /auth/session
POST /auth/logout
POST /auth/zhihu/disconnect
```

当前 coordinator 已实现：

- 服务端生成授权 state 并校验回调。
- 服务端使用 `app_id/app_key` 换取 token。
- 浏览器只保存 `Secure + HttpOnly` session cookie。
- token 使用 Fernet 加密写入 SQLite，并保存过期时间。
- OAuth session 可以作为 REST/WS 的 `identity_resolver`。
- 退出时删除 session；断开时删除本地知乎连接。

尚未可以宣称完成的部分：

- 真实 `app_id`、`app_key` 和 `Access Secret` 尚未注入部署环境。
- 知乎 OAuth 开放时间和官方稳定用户信息字段仍以平台确认结果为准。
- 多用户 OAuth gateway 还没有把每个用户的 token 映射到个人 source。
- 前端仍需要在 OAuth 成功后以 `/auth/session` 完成正式身份 hydration。

在 OAuth 开放前，公开数据可以走服务端 Access Secret source；个人创作、关注和收藏只能做明确绑定的单账号联调，不能冒充多用户登录。

## 11. 一次典型产品旅程如何穿过后端

```text
公开机会 / 主动需求
        │
        ├── /opportunities/preview 或 /intents/preview
        ├── /matches/preview
        └── 用户确认 /matches/confirm
        │
        ▼
建桌：TableState v0
        │
        ├── /tables/{id}/lobby（入席前公开读模型）
        ├── invitation / join-request（如需要补位）
        └── participant consent
        │
        ▼
桌内 WebSocket
        │
        ├── human_message → TableState 快照
        ├── Agent 六动作 → InterventionRecord
        ├── observer / commenter → 独立评论账本
        ├── /grounding → trusted card → GROUND
        └── safety → 提醒 / 暂停 / 审核恢复
        │
        ▼
收桌
        │
        ├── SharedBaseline
        ├── PersonalCard
        ├── FollowUp / feedback / evaluation
        └── replay / lineage / relationship memory
        │
        ▼
下一桌：显式 recompose，记录 origin_table_id
```

这里有两个重要约束：

1. 旁听、收藏、选择和推荐不会偷偷变成入席或发言。
2. “下一桌”是显式创建的新桌，不复制旧成员，也不把个人隐私资料带过去。

## 12. Demo、测试和验收

### 本地 Demo

| 命令 | 验证内容 |
| --- | --- |
| `python -m app.cli.seed_demo --path ...` | 幂等写入三张可重复评委桌 |
| `python -m app.cli.opportunity_demo` | 公开信号 → 未完成性 → 候选种子 |
| `python -m app.cli.intent_demo` | 多轮主动需求澄清 → source 预览 |
| `python -m app.cli.grounding_demo` | 相反事实 → trusted source → GROUND → replay |
| `python -m app.cli.journey_demo` | 公开机会 → 匹配 → 邀请 → 入席 → 对话 → 收桌 → 回响 |

Demo 使用隔离内存仓储，除 `seed_demo` 外不会读写生产快照，也不联网。

### 测试层次

- `test_schemas.py`：契约和边界校验。
- `test_observer.py`、`test_gate_router.py`、`test_host.py`、`test_safety.py`：核心决策。
- `test_api.py`、`test_identity.py`、`test_privileged_identity.py`：REST 身份和权限。
- `test_websocket.py`、`test_observer_websocket.py`、`test_rest_fanout.py`：实时链路和广播。
- `test_persistence.py`、`test_shared_coordination.py`：JSON、SQLite 短期存储和多 worker 协调。
- `test_source.py`、`test_http_sources.py`、`test_zhihu_source_adapter.py`：外部数据边界。
- `test_zhihu_oauth.py`：OAuth coordinator 的本地协议测试。
- `test_journey_smoke.py`、`test_demo_seed.py`：完整产品旅程和 Demo 可重复性。

当前仓库最近一次后端全量基线为 **506 passed**；本次只新增说明文档，没有修改运行代码。

## 13. 当前明确的缺口

这些不是架构未知，而是已经知道、但还没有条件或没有做完的部分：

1. **正式身份还没落地**：生产需要真正的 session/JWT/OAuth 身份解析；当前无 resolver 的模式是开发兼容模式。
2. **OAuth 真实联调未完成**：等待知乎开放和正式凭据，稳定用户信息字段也要平台确认。
3. **个人数据 source 未完成多用户闭环**：需要一个服务端 gateway 按 viewer 找到对应 OAuth token，并输出 `PersonalContextSignal`。
4. **生产持久化仍是轻量实现**：JSON + SQLite 适合比赛和小规模联调；正式部署建议迁移到托管数据库、队列和共享缓存，但要保持现有领域契约。
5. **审核员接入留给部署层**：后端已经有 `moderator_resolver` 和审核账本，但没有绑定具体的账号系统。
6. **端到端双账号验收需要真实环境**：尤其是 OAuth、个人 source、跨 worker WebSocket、token 过期和知乎 429/5xx。

## 14. 建议的阅读顺序

如果要理解实现，不需要先看全部 3000 多行路由，按下面顺序读：

1. `app/main.py`：看应用是如何装配的。
2. `app/domain/schemas.py`：先理解 `TableState`、`HumanTurn`、`InterventionRecord`。
3. `app/api/repository.py`：看状态快照和所有账本怎样提交。
4. `app/api/websocket.py`：看一条真人消息怎样进入状态机。
5. `app/orchestrator/observer.py`、`gate.py`、`router.py`、`host.py`：看 Agent 为什么说或不说。
6. `app/api/privacy.py`、`identity.py`：看同一张桌为什么不同人收到不同内容。
7. `app/matching/engine.py`、`app/lobby.py`、`app/opportunities/`、`app/personal/`：看建桌前的产品链路。
8. `app/sources/`、`app/providers/`、`app/auth/zhihu.py`：最后看外部系统接入。
9. `tests/`：用测试确认每条边界，而不是只看 happy path。

相关资料：

- [后端运行说明](./README.md)
- [后端验收矩阵](./ACCEPTANCE_MATRIX.md)
- [Conversation Orchestrator SPEC](../specs/conversation-orchestrator.md)
- [知乎 OAuth 与真实数据接入清单](../specs/ZHIHU-OAUTH-REAL-DATA.md)
- [产品沉淀文档](../docs/组一桌_知乎赛道一_完整产品沉淀文档_v1.3_最终排版.docx)

维护这份文档时，以运行代码、测试和 SPEC 的最新结果为准；如果三者不一致，应先修正实现或契约，再更新这里的描述。
