# 首页接入合同

> 状态：匹配页 / 桌内工作线已整理，最终首页由队友接入。
> 目的：让首页调用真实后端能力，并把用户送进现有匹配页或桌内链路。

## 先说边界

当前仓库的页面职责不是一个“大而全大厅”:

- 首页负责 Gallery、首页推荐、手动组一桌、邀请对象编辑、邀请收件箱和跨桌账户入口。
- 匹配页负责接收首页上下文、展示正在发生的桌、主动找桌、桌边预览和“为什么想到你”。
- 桌内负责旁听、入席、资料授权、实时讨论、主持动作、历史、收桌和当前桌的关系保存。
- `src/live/api.ts` 是 REST 适配边界；`src/live/backend.ts` 是 WebSocket 适配边界。
- 首页不能复制匹配或桌内的业务判断，也不能把邀请对象提前写进 participants。

知乎正式 OAuth 在 2026-09-13 前不可用。接入前使用当前浏览器会话的 guest 身份，不能在首页伪造知乎用户或写入 token。

## 页面交接

### 首页 → 匹配页

使用 `HomeToMatchContextLike`（类型位于 `src/live/contract.ts`）传递最小上下文：

```ts
type HomeToMatchContextLike = {
  source: 'home_recommendation' | 'home_intent' | 'home_invitation' | 'home_return'
  initial_question?: string
  recommended_table_id?: string
  return_to_home?: string
}
```

只传推荐桌 ID 或有限的需求草稿。不要把私密画像、OAuth token、完整候选资料放进 URL 或前端事件。

匹配页收到 `recommended_table_id` 后仍要请求真实 `/tables/{id}/lobby` 和 `/tables/{id}/lobby-fit`，不能根据首页卡片直接认为用户已经入席。

当前匹配页接收实现位于 `src/live/handoff.ts` 与 `src/App.tsx`：

- 首页可以调用 `handoffHomeContext(context)`；实现会校验并裁剪字段，只传最小上下文。
- 同壳通过 `zuoyizhuo:home-to-match-context` 事件接收，刷新或跨壳通过
  `sessionStorage` key `zuoyizhuo:home-to-match-context` 恢复。
- `recommended_table_id` 只触发真实 Lobby 加载；`initial_question` 只预填主动找桌面板。
- 推荐桌失效时显示可关闭的错误，不自动降级为假桌、不自动创建、不自动入席。

### 匹配页 → 首页手动创建

没有真实正在发生的桌，也没有可确认的公开候选时，匹配页只发出 `MatchToHomeDraftLike`，不调用 `POST /tables`：

```ts
type MatchToHomeDraftLike = {
  kind: 'manual_create_draft'
  normalized_question: string
  clarification_messages: string[]
  no_match_reason: string
  source_session_id?: string
}
```

当前实现通过 `src/live/handoff.ts` 完成短期交接：

1. 写入当前浏览器 `sessionStorage`；
2. 派发 `zuoyizhuo:match-to-home-draft` 事件；
3. 首页读取后填充自己的建桌表单；
4. 首页必须再次取得用户明确确认，才允许创建真实桌。

跨路由或两个前端壳合并时，首页可以监听事件，也可以调用 `readMatchDraft()`。成功接收后调用 `clearMatchDraft()`，避免刷新后重复填充。

### 首页 / 匹配页 → 桌内

使用 `OpenTableContextLike`：

```ts
type OpenTableContextLike = {
  table_id: string
  source: 'match' | 'home_create' | 'invitation'
  intent: 'listen' | 'join'
}
```

三种来源最终都进入同一套 Lobby 和 Bruno Runtime。桌内先读取真实状态，再决定是否显示发言框、主持控制和个人卡；不要只依据首页传入的 `intent` 或本地 `joined` 布尔值。

当前匹配页也提供 `handoffOpenTable(context)`、`readOpenTableContext()` 和
`clearOpenTableContext()`：同壳事件名为 `zuoyizhuo:open-table-context`，短期恢复 key 为
`zuoyizhuo:open-table-context`。接收后先请求真实 Lobby；`intent` 只表示期望进入方式，
不等于已经入席。

## 手动建桌：真实 API 顺序

### 1. 创建桌

```http
POST /tables
Content-Type: application/json
```

```json
{
  "table_id": "optional-client-request-id",
  "core_question": "你要讨论的具体问题",
  "participants": [
    {
      "participant_id": "owner-id",
      "display_name": "发起人",
      "role": "实践者",
      "declared_position": "我做过相关实践"
    }
  ],
  "origin_signal_ids": [],
  "origin_signals": []
}
```

约束：

- `core_question` 必填；桌最多 5 个 participants，具体角色和 seed 字段以 `ParticipantSeed` 为准。
- 创建者若作为 `participants` 传入，会成为真实成员；没有传入的邀请对象不能被首页当作已入席。
- `table_id` 可由首页生成稳定值用于重试判重；重复或容量冲突按 `409` 展示可重试错误，不静默重复创建。
- 成功返回真实 `TableState`，首页随后使用其中的 `table_id` 打开桌边或桌内。

### 2. 邀请对象

```http
POST /tables/{table_id}/invitations?inviter_id={owner_id}
Content-Type: application/json
```

```json
{
  "candidate": {
    "participant_id": "candidate-id",
    "display_name": "受邀人",
    "role": "研究者"
  },
  "reason": "为什么邀请这个人"
}
```

邀请成功只产生 `pending` invitation，不增加席位。首页应逐项显示成功/失败；单项失败允许重试，不能因为一项失败就重建整张桌。

### 3. 邀请收件箱与接受

```http
GET /participants/{participant_id}/invitations?viewer_id={participant_id}
POST /tables/{table_id}/invitations/{invitation_id}/respond?participant_id={participant_id}
Content-Type: application/json
```

```json
{ "accept": true }
```

只有接受邀请才会新增席位。收件箱由服务端返回 `can_respond` 和失效原因（已处理、桌已关闭、过期、满席等），首页必须按服务端结果更新，不能本地把邀请直接改成“已入席”。

### 4. 申请入桌（不是邀请）

匹配页或桌卡若允许用户主动申请，可调用：

```http
POST /tables/{table_id}/join-requests?participant_id={candidate_id}
Content-Type: application/json
```

申请只进入脱敏申请队列，不直接增加 participants。桌内成员审核后生成 invitation，申请人仍需接受 invitation 才能入席。

## 可直接复用的前端适配函数

这些函数已经在 `src/live/api.ts`：

- `createTable(coreQuestion, participants, tableId?, { origin_signal_ids?, origin_signals? })`
- `previewMatch({ core_question, candidates, table_size? })` / `confirmMatch({ core_question, candidates, table_size?, table_id?, origin_signal_ids?, origin_signals? })`
- `createInvitation(tableId, inviterId, candidate, reason)`
- `fetchInvitationInbox(participantId)`
- `respondInvitation(tableId, invitationId, participantId, accept)`
- `createJoinRequest(tableId, participant, message?)`
- `fetchJoinRequests(tableId, participantId)`
- `approveJoinRequest(tableId, requestId, participantId, reason)`
- `declineJoinRequest(tableId, requestId, participantId)`
- `saveTableForLater(participantId, tableId)` / `removeSavedTable(...)`

首页只需要负责表单状态、提交反馈和路由，不需要重新实现隐私投影、容量校验、邀请生命周期或桌状态合并。

如果首页承担“AI 找桌”的全局入口，先调用 `previewMatch` 展示服务端返回的席位与理由，用户明确确认后再调用 `confirmMatch`。这条路径只确认后端生成的 `MatchPlan`；自由填写题目和邀请对象仍走首页自己的 `createTable` + invitation 路径，不能把两条流程混成一张单人手动桌。

## P2 验收口径

- 首页手动创建不会先经过匹配页，也不会在匹配页渲染手动创建表单。
- 创建成功后只有一个真实 `table_id`，能进入现有 Lobby；不创建第二个 Canvas 或第二份桌状态。
- 邀请接受前成员数不增加；接受后通过后端响应 / WebSocket 更新。
- 刷新、重复点击和部分失败都显示可恢复状态；不使用假成员、假匹配理由或前端自己拼的邀请状态。
- 首页接入完成后，再做一次“首页 → 匹配页 / 首页建桌 → 同一桌内 → 收桌”的联合浏览器验收。

当前可先运行 `corepack pnpm verify:home-contract` 做后端合同验收。该脚本只模拟
首页的 REST 调用，覆盖重复建桌拒绝、邀请 pending 不占席、收件箱可响应、接受后成员
同步和状态版本推进；它不能替代队友首页 UI 与跨页面 Canvas 的联合验收。
