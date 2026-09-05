# P0–P2 产品任务清单：匹配页与桌内工作线

> Status: Active
> Product boundary confirmed: 2026-09-05
> Parent contract: [`bruno-runtime-product-integration-v2.md`](./bruno-runtime-product-integration-v2.md)
> Homepage handoff: [`HOME-INTEGRATION-CONTRACT.md`](../docs/HOME-INTEGRATION-CONTRACT.md)
> Formal Zhihu OAuth: blocked by provider availability until 2026-09-13; 不作为本清单完成门槛。

状态规则：`[x]` 只表示当前仓库已有代码或测试证据；`[ ]` 表示仍需实现、纠偏或重新验收。旧文档中的 Runtime P1–P6 与这里的产品 P0–P2 是两套编号，不互相替代。

本轮对齐结论（2026-09-05）：当前实现与验收只覆盖“匹配页 + 桌内”工作线。
“首页 → 匹配页”的发送端，以及“首页手动建桌 → 桌内”的 UI 发送端，必须等队友首页接入后再做联合验收；不能因为后端合同已经存在，就把首页功能计入当前工作线已完成项。

当前清单快照（2026-09-05）：共 59 项，已完成 48 项，保留 11 项开放项。
这 11 项集中在队友首页实际接入、知乎 OAuth 开放后的身份替换和跨工作线联合验收；当前匹配页、桌边预览、桌内实时讨论、回放、收桌、关系保存以及后端适配层没有被隐藏的 P0–P2 代码缺口。

## 0. 范围锁定

当前工作线只负责：

```text
队友首页交接
  → 匹配页
  → 桌边预览
  → 旁听 / 入席
  → 桌内实时讨论
  → 主持 / 历史 / 收桌 / 关系保存
```

以下前端不属于当前工作线：

- 最终首页与首页 Gallery；
- 首页手动建桌表单；
- 首页邀请对象编辑器与账户级邀请中心；
- Bruno 场景最终美术、Agent IP、六动作动画和镜头表演。

后端的建桌、邀请、申请入桌、身份和状态合同仍由当前工作线维护。队友首页只能通过这些合同接入，不复制业务规则。

## 1. 页面交接合同

### H1 — 首页 → 匹配页

- [x] 定义 `HomeToMatchContext`：来源、可选需求、可选推荐桌 ID、返回首页地址。
- [x] 禁止把私密画像、OAuth token 或完整候选资料放进 URL。
- [x] 匹配页能在缺少可选字段时进入可恢复空态，不自动造桌或自动入席。
- [x] 匹配页已在 `src/live/handoff.ts` / `src/App.tsx` 实现上下文接收：推荐桌走真实 Lobby，主动需求只预填找桌面板；不依赖对方 DOM。
- [x] 已在 `docs/HOME-INTEGRATION-CONTRACT.md` 固化首页调用示例、事件/key 和 TypeScript 类型。

### H2 — 匹配页 → 首页手动创建

- [x] 定义 `MatchToHomeDraft`：规范化题目、有限轮澄清摘要、无候选原因、来源会话 ID。
- [x] 匹配页只显示“返回首页继续创建”出口，不渲染题目/邀请对象创建表单。
- [x] 首页必须再次取得用户确认，才允许调用 `POST /tables`。
- [x] 草稿交接失败时保留用户已输入内容并提供复制/重试，不静默丢失；事件 + sessionStorage 正常交接，存储失败时仍保留当前上下文并显示恢复操作。
- [x] 交接函数按事件与 sessionStorage 两条独立路径返回成功；任一路径可用时不会把有效交接误报成失败。

### H3 — 首页或匹配页 → 桌边/桌内

- [x] 定义 `OpenTableContext`：真实 `table_id`、进入来源、期望 observer/participant 身份。
- [x] 桌内启动后以 `GET /tables/{id}` / lobby 投影校正本地期望，不相信纯前端 `joined=true`。
- [ ] 首页创建、AI 匹配确认、邀请接受三种来源进入同一套 Lobby 和 Bruno Runtime；当前代码已提供类型和复用入口，首页实际接入留 P2.3 联合验收。

## 2. P0 — 比赛主链稳定

### P0.1 范围纠偏

- [x] 已从匹配页移除“手动创建一桌”按钮、`CreateTablePanel` 挂载和相关样式入口。
- [x] 已移除匹配页中的账户级邀请中心入口；邀请列表最终由首页承载。
- [x] 保留 `createTable`、invitation、join-request 后端能力；前端适配和首页接入文档均已整理。
- [x] 统一文案：当前页按“匹配页/找桌”解释，不再把它当作“首页/大厅”。

### P0.2 真实匹配与桌边预览

- [x] 匹配页接收 `HomeToMatchContext.recommended_table_id` 后读取真实 lobby 与 `lobby-fit`，展示真实成员、空席和“为什么想到你”；首页实际发送端仍留 H3/P2.3 联合验收。
- [x] 桌卡、成员数、空席、阶段和缺失视角全部来自后端公共投影。
- [x] 后端错误展示 loading / empty / retry，不回退假成员或假匹配理由。
- [x] 已入席用户再次进入时直接恢复桌内，不重复调用 add-participant。

### P0.3 一张桌完整闭环

- [x] 使用独立测试桌完成：预览 → 旁听 → 入席 → consent → 双客户端发言；`p0-consent-20260905-01` 已通过桌内 UI 完成入席表达与授权，`p0-dual-20260905-01` 已完成双客户端实时表达。
- [x] 后端六动作事件统一进入 App 文案与 `SceneBridge → TableMeeting` 视觉状态；已加入静态验收覆盖六个动作。动作触发策略和最终 Agent 动画仍按队友视觉线单独签收。
- [x] 完成 request-close → 公共底稿 → 本人个人卡 → `/replay` → 刷新恢复（独立测试桌 `p0-dual-20260905-01`）。
- [x] 验证 observer 不能发言、收桌或读取 participant 私有个人卡；浏览器旁听路径无输入/收桌/个人卡，后端隐私边界由完整测试覆盖。
- [x] 断线重连不重复入席、不重复提交消息，旧 `state.version` 不覆盖新状态；客户端按 `/replay` 对账 pending 消息，服务端对重复 `message_id` 返回可关联错误。

### P0.4 工程验收

- [x] 固化 `pnpm verify:p0-p2` 双客户端黑盒验收脚本，只创建带时间戳的隔离测试桌；脚本覆盖双端消息广播、重复 ID 拒绝、回放单条、WS 重连和状态版本单调性。
- [x] `pnpm check`、`pnpm build`、`pnpm verify:frontend`、后端完整 pytest 全绿。
- [x] 桌面与 390×844 窄屏完成匹配、Lobby、历史、收桌卡回归；窄屏实测 `scrollWidth === innerWidth`。
- [x] 浏览器回归确认打开/关闭历史、入席、桌单抽屉及进出桌不会新增 renderer；全程保持 1 个 Canvas，桌内保持单条 WS，离开后旧 WS 关闭，再次进入不并发旧连接；RAF 维持匹配页 1 条 / 桌内 2 条，未产生新的 console error。
- [x] 本轮产品逻辑提交未修改队友负责的最终场景美术与动作表演；视觉问题只形成可交接 issue，最终视觉签收仍由视觉线负责。

## 3. P1 — 主动需求匹配与桌后延续

### P1.1 主动需求匹配

- [x] 匹配页接入 self-scoped intent session；前端最多允许三轮澄清，后端六轮仅作安全上限。
- [x] 有现有桌时展示真实候选、匹配理由、角色缺口和公开来源信号。
- [x] 有真实候选人的 source `MatchPlan` 时，只有用户点击明确确认按钮才调用票据确认接口（`/matches/source-confirm`；通用 `/matches/confirm` 仍由首页/全局匹配调用方使用）；确认时由服务端从票据里的 MatchPlan 证据保留公开 `origin_signal_ids`，不让前端补写。
- [x] `MatchPlan` 与“手动建桌”在 UI、代码和交接命名上区分：前者是 `sourcePlan/confirmSourceMatch`，后者是 `MatchToHomeDraft`，匹配页不创建桌。
- [x] 无现有桌且无真实候选时只显示空态与 `MatchToHomeDraft` 出口，不调用 `POST /tables`；真实浏览器已验证三轮后按钮禁用且交接数据落入 sessionStorage。
- [x] 已修复“做过 / 的人”等宽泛短语误匹配，并补当前回归测试；满桌、过期桌和隐私投影测试继续纳入完整回归。

### P1.2 关系与行动回响

- [x] 个人收桌卡已有“记住这个人”调用，后端只允许已收桌成员保存真实关系；独立测试桌浏览器已完成“记住这个人 → 已记住”，并收到真实 `201` 行为事件。
- [x] 收桌卡从 `/participants/{id}/action-echoes` 读取当前桌的行动回响；状态和备注直接使用后端返回值，不在前端生成完成状态。
- [x] 桌内/收桌页只展示当前桌相关关系动作；行动回响按真实 `table_id` 过滤，跨桌“我的回响”总览交给首页承载。
- [x] 再次打开一张桌时使用真实 `table_id` 和权限恢复，不复制历史数据到本地 fixture；已通过收桌后刷新恢复与已入席再次进入验证。

### P1.3 身份过渡

- [x] 保持 `AccountSession` 单一适配边界；OAuth 未开放前只显示明确 guest 身份。
- [x] guest ID 仅存在当前浏览器会话，不冒充知乎稳定用户 ID。
- [ ] 9 月 13 日后只替换身份/provider hydration，不改 TableState、匹配页或 3D 合同。

## 4. P2 — 首页手动创建的后端交接

P2 不是在当前匹配页新增页面，而是把已经具备的后端能力整理成队友首页可直接接入的合同。

当前底座：`POST /tables`、invitation、join request、本人 invitation inbox、关系保存及对应后端测试已经存在；P2 剩余工作重点是合同收口、TypeScript 示例、首页交接和双方汇合验收。

### P2.1 当前工作线：后端与适配层

- [x] 固化 `POST /tables` 请求/响应、幂等、容量和错误码文档。
- [x] 固化 invitation 创建、本人邀请 inbox、接受/拒绝和过期语义。
- [x] 固化 join request 创建、桌主查看、接受/拒绝和隐私边界。
- [x] 明确创建者是否自动入席、邀请对象在接受前不得预写 participants。
- [x] 提供最小 TypeScript 调用示例和 mock-free 集成测试 fixture；共享适配层现已包含 `previewMatch` / `confirmMatch`、可携带公开 `origin_signal_ids` / `origin_signals` 的 `createTable`，以及 invitation / join-request 函数；`TableState`、主持状态和 `/replay` 来源类型与后端对齐，私有资料不进入该合同。
- [x] 保证首页创建成功后返回真实 `table_id`，可直接进入现有 Lobby/桌内页。

### P2.2 队友工作线：首页 UI

- [ ] 在最终首页实现“手动组一桌”入口与表单。
- [ ] 用户明确确认题目、邀请对象和资料用途后再提交。
- [ ] 展示创建中、部分邀请失败、重试、满员和身份失效状态。
- [ ] 在首页承载邀请 inbox、手动创建历史和跨桌回访入口。
- [ ] 创建完成后通过 `OpenTableContext` 进入同一 Bruno 桌边/桌内页。

### P2.3 汇合验收

- [ ] 首页手动创建不会经过匹配页的自由创建表单。
- [ ] AI `MatchPlan` 确认与首页手动创建产生相同后端 TableState，但保留不同来源标记。
- [ ] 邀请接受前桌成员数不增加；接受后成员与席位通过后端事件同步。
- [ ] 首页、匹配页和桌内页切换不创建第二个 3D Runtime。

## 5. 暂不计入 P0–P2 完成门槛

- 知乎正式 OAuth 与个人真实数据 hydration：等待 2026-09-13 官方开放后联调。
- 完整好友申请、好友列表、私聊和关系图谱：比赛后扩展。
- 队友负责的最终首页视觉、Agent IP、GLB 资产和六动作表演：单独按视觉线验收。
- 语音讨论、多桌大规模并发和生产级推荐模型：不阻塞当前一张桌闭环。

## 6. 推荐执行顺序

1. 先完成 P0.1 范围纠偏，撤掉匹配页的手动创建与账户中心入口。
2. 完成 H1–H3 类型合同，再回归 P0 匹配 → 桌内完整链路。
3. 完成独立测试桌双客户端收桌/恢复，关闭 P0。
4. 完成 P1 主动需求的三轮上限、真实候选与无候选回首页出口。
5. 完成桌内关系保存和当前桌行动回响；跨桌总览留给首页。
6. 整理 P2 API/TypeScript 接入包交给队友，不在当前匹配页实现创建 UI。
7. 最后做双方汇合 E2E：首页 → 匹配或创建 → 同一桌内闭环。

## 6.2 开放项归类与关闭条件

为避免把“等待外部输入”误判成“当前代码没做完”，开放项按下面四类管理：

| 类别 | 对应项目 | 关闭条件 | 当前负责人 |
|---|---|---|---|
| 首页实际接入 | H3、P2.2、P2.3 | 队友首页完成发送端后，走一次首页推荐、首页手动创建、邀请接受三条真实浏览器路径 | 队友主责，双方验收 |
| 正式身份 | P1.3 | 2026-09-13 后取得知乎正式 OAuth 能力，只替换 `identity.ts` 的 provider hydration，并通过身份/隐私回归 | 用户本人；依赖知乎开放 |
| 跨线运行时汇合 | H3、P2.3 | 三种来源都复用同一个 `table_id`、Lobby、Bruno Canvas 和 TableState，不产生第二套 renderer 或本地状态 | 双方共同 |
| 最终视觉签收 | 由 Runtime spec 单独管理 | 队友完成 Agent IP、动作、桌椅和镜头表现后，按视觉基准截图签收 | 队友主责 |

关闭开放项时必须补真实证据（请求、状态、页面路径或截图）；不能只因类型、mock 或静态字符串存在就勾选。

## 6.1 工作线边界速查

| 事项 | 当前工作线（用户本人） | 队友首页 / Creative Frontend 线 |
|---|---|---|
| 页面 | 匹配页、桌边预览、桌内聊天与收桌 | 最终首页、Gallery、首页入口 |
| 手动建桌 | 维护 `POST /tables`、invitation、join-request 合同和适配函数 | 在首页实现建桌表单、邀请编辑和确认 UI |
| AI 找桌 | 主动需求澄清、真实候选、匹配理由、无候选草稿 | 首页发起需求并接收回首页草稿 |
| 进入桌内 | 维护 Lobby、旁听/入席、授权、WS、回放和恢复 | 创建或邀请成功后通过 `OpenTableContext` 进入 |
| 3D 表现 | 提供稳定数据投影和 `SceneBridge` 合同 | 最终桌椅、Agent IP、动作动画、镜头和环境美术 |
| 联合验收 | 提供接口、类型、真实状态与可重复测试 | 接入首页发送端后共同走完整浏览器路径 |

## 7. 本轮执行证据（2026-09-05）

- 真实浏览器桌面路径：独立桌 `p0-dual-20260905-01` 完成匹配页 → 桌边预览 → 旁听 → 靠近 → 参与者入席恢复 → 双客户端表达 → 历史弹层 → 收桌。
- 真实浏览器 consent 路径：独立桌 `p0-consent-20260905-01` 完成旁听 → 靠近 → 入席面板 → 填写经历 → 勾选资料授权 → participant WS → 入席表达；随后在 390×844 完成历史和收桌卡回归。
- 旁听会话确认：同一桌的实时表达和历史可见；没有“对这桌发言”、没有“收这桌”、没有 participant 个人收桌卡。
- 参与者会话确认：收桌卡展示真实表达和本人视角；刷新后通过 `/close-artifacts` 恢复。
- 权限恢复复核：sessionStorage 中的 `joined` 只作为启动时的 participant hydration 提示，桌内发言、主持请求和收桌按钮只由后端确认的 `liveViewerJoined` 驱动；过期缓存不会直接授权。
- 行动回响复核：收桌卡按真实 `table_id` 过滤 `/action-echoes`，明确展示后端的已完成、进行中、阻塞、搁置或尚未回报状态；无数据和接口失败均为诚实空态/错误态。
- 关系延续复核：独立桌 `p0-relationship-20260905-01` 收桌后展示真实关系候选，点击“记住这个人”成功变为“已记住”，请求命中后端关系保存接口。
- 主动找桌确认：`社区养老经验` 及两轮补充后显示 `已澄清 3/3`，不出现手动创建按钮；`MatchToHomeDraft` 包含规范化题目、三条上下文、无匹配原因和 session ID。
- source-match 确认测试确认：服务端票据消费后，`MatchPlan` 证据中的公开 `origin_signal_ids` 会写入新桌 `TableState`；测试验证两个来源 ID 均保留且不重复，顺序不由前端重排。
- 窄屏确认：390×844 匹配页主动找桌以及桌内历史/收桌卡均通过，`scrollWidth === innerWidth`，无可见按钮越界。
- 首页上下文接收确认：独立浏览器会话通过 `home_intent` sessionStorage 和 `home_return` 自定义事件分别打开主动找桌面板并预填问题；上下文消费后 sessionStorage 被清理。
- 推荐桌上下文确认：注入 `HomeToMatchContext.recommended_table_id` 后，匹配页真实请求 `/tables/{id}/lobby` 与 `/tables/{id}/lobby-fit`，展示后端成员、空席和“为什么想到你”；请求均返回 200，消费后不把推荐卡直接当作已入席。
- 桌内上下文接收确认：`home_create` 事件携带真实 `table_id` 后打开后端 Lobby，成员和空席来自真实投影；消费后 `open-table-context` key 被清理，未直接授予入席权限。
- 断线故障演练：隔离浏览器主动关闭参与者 WS，客户端在退避后重新建立连接；回放中的测试消息保持 1 条，桌内参与者保持 2 个，状态版本未回退。
- 可重复传输验收：`corepack pnpm verify:p0-p2` 通过，覆盖两个真实参与者 WS、重复消息 ID、回放对账和重连恢复。
- 资源生命周期回归：独立浏览器会话完成历史、入席、桌单抽屉开合和两次进出桌；全程 `canvas=1`，桌内单 WS、离开后 WS 为 closed、再次进入无并发旧连接，RAF 为匹配页 1 / 桌内 2，应用 `console error=0`。
- 代码检查：`corepack pnpm check`、`corepack pnpm build`、`corepack pnpm verify:frontend`、`git diff --check`；后端 `python -m pytest -q`：`507 passed`；在 Vite 代理与后端同时运行时 `corepack pnpm verify:p0-p2` 通过。
- 仍未勾选的项目是有意保留的真实缺口：队友首页尚未接入、OAuth 开放后的正式身份替换、最终视觉动作签收，以及首页汇合 E2E。双客户端传输、重复消息拒绝、回放对账、断线恢复和资源生命周期已有证据。
