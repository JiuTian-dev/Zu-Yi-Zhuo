# 代码审查与项目对齐总览（2026-09-05）

> 本文是一次基于当前仓库代码、运行入口、现有测试脚本和产品 SPEC 的只读审查记录。
> 它不把“接口已经存在”直接等同于“前端产品已经完成”，也不把队友负责的首页 UI 计入当前工作线。

## 0. 一句话结论

当前项目的核心产品闭环已经成立：

```text
队友首页交接
  → 匹配页读取真实桌状态
  → 桌边预览 / 靠近
  → 旁听或入席
  → WebSocket 实时讨论
  → Agent 主持动作 / 场景反馈
  → 回放 / 收桌卡 / 关系延续
```

现在最需要做的不是再增加一个页面，而是把已有闭环变得更容易维护、更容易和队友首页汇合，并为正式身份、真实数据和生产运行补齐边界。

当前仓库属于：

> **匹配页 + 桌内 + Conversation Orchestrator + Bruno 3D Runtime 的可运行产品线。**

它不是队友尚未完成的最终首页，也不应把“首页手动建桌 UI”重新塞回匹配页。

---

## 1. 审查范围与证据

本次对齐检查了：

- 根目录 README、`specs/`、`docs/` 中的产品和工程约定；
- React/Vite 入口、匹配页、桌内页、3D Runtime、REST/WS 适配层；
- FastAPI 组合根、REST 路由、WebSocket、编排器、仓储和 source adapter；
- `P0–P2` 产品清单、Runtime `P1–P6` 文档和首页交接合同；
- 当前分支提交历史、配置文件、mock/seed 入口和测试脚本。

当前分支：`codex/frontend-v2`。

当前 HEAD：`58dd685 docs: record homepage handoff browser evidence`。

主要验证命令已在近期提交记录中通过：

- `corepack pnpm check`
- `corepack pnpm build`
- `corepack pnpm verify:frontend`
- `corepack pnpm verify:p0-p2`
- `corepack pnpm verify:home-contract`
- `backend` 下 `python -m pytest -q`（近期记录为 507 passed）

本文件本身只新增审查记录，不修改业务逻辑。

---

## 2. 项目全貌

### 2.1 产品分层

项目实际有四层，不能混成一个“前端页面”：

| 层 | 责任 | 当前状态 |
| --- | --- | --- |
| 队友首页 | 产品入口、Gallery、AI 找桌入口、首页手动建桌、邀请入口、账户级回访 | 由队友负责，当前仓库通过合同接入 |
| 匹配页 | 接收首页上下文、展示真实 Lobby、解释为什么想到你、主动需求找桌、桌边预览 | 当前工作线，主链已跑通 |
| 桌内页 | 旁听/入席、资料授权、消息、主持动作、历史、收桌卡、关系延续 | 当前工作线，主链已跑通 |
| 后端编排层 | TableState、Observer、Gate、Router、Host、Reflection、Close、REST/WS、隐私和回放 | 当前工作线，能力完整，生产化仍有缺口 |

### 2.2 当前用户路径

正式产品路径应保持为一条连续的 Table First 体验，不插入新的随机大厅或第二套世界：

```text
远处发现一张桌
  → 匹配页显示桌题、成员、空席、匹配理由
  → 点击“靠近这桌”
  → 同一个 Bruno Canvas 做镜头靠近
  → 选择“旁边听听”或“入席”
  → 入席后提交发言并获得后端确认
  → 后端通过 WS 推送消息、状态、AgentActionEvent、visual_hint
  → 历史抽屉读取 /replay
  → 收桌后读取 shared baseline、personal card、follow-ups
```

相机拖拽和滚轮缩放只改变本地镜头，不改变后端状态。这条边界是正确的，需要继续保持。

### 2.3 当前代码地图

```text
D:\知乎黑客松
├─ src/
│  ├─ main.tsx                         React 挂载入口
│  ├─ App.tsx                          全局阶段 + 桌内协调器
│  ├─ TableSea.tsx                     匹配页 / 桌发现 DOM 层
│  ├─ Lobby.tsx                        桌边预览、成员、匹配理由、入席入口
│  ├─ TableWorld.tsx                   单 Canvas Bruno Runtime 容器
│  ├─ DrawerToggle.tsx                 卡片/抽屉收起控制
│  ├─ domain.ts                        旧的前端展示类型和开发 fixture
│  ├─ actors.ts                         开发种子成员，不是正式用户来源
│  ├─ live/
│  │  ├─ api.ts                         REST 适配层
│  │  ├─ backend.ts                     WS、重连、入席、回放、状态同步
│  │  ├─ contract.ts                    后端 DTO 的 TypeScript 镜像
│  │  ├─ store.ts                       桌内实时状态外部 store
│  │  ├─ identity.ts                    guest session / OAuth hydration 边界
│  │  ├─ handoff.ts                     首页 ↔ 匹配页交接合同
│  │  ├─ mock.ts                        后端不可用时的显式本地演示流
│  │  └─ *.tsx                          历史、主动需求、关系和收桌 UI
│  └─ bruno-runtime/
│     ├─ Game/Game.js                   Bruno 原始环境的产品化生命周期入口
│     ├─ Game/World/World.js            地形、水、植被、灯光、雾、风等环境组合
│     ├─ Game/World/TableMeeting.js     组一桌产品桌区和视觉状态
│     ├─ Game/CameraOrbit.js             鼠标镜头输入，不写后端状态
│     ├─ SceneBridge.js                  TableState → 3D 表现的边界
│     ├─ runtimeController.ts            React ↔ Runtime 生命周期和投影
│     └─ ORIGIN.md / REMOVAL-MANIFEST.md 上游来源和移除项记录
├─ backend/
│  ├─ app/main.py                       配置、provider、repository、source 的组合根
│  ├─ app/api/app.py                    REST 路由和业务编排入口
│  ├─ app/api/websocket.py              WS 协议、连接、广播、锁和幂等
│  ├─ app/domain/                       Pydantic schema、TableState、事件类型
│  ├─ app/orchestrator/                 Observer → Gate → Router → Host → Reflection
│  ├─ app/repository/                   Memory / JSON 仓储和账本
│  ├─ app/sources/                      候选、公开内容、个人上下文 source adapter
│  ├─ app/providers/                    deterministic / OpenAI provider
│  └─ tests/                            REST、WS、隐私、动作、回放、source、身份测试
├─ specs/                               执行清单、Runtime、产品和 OAuth 规格
├─ docs/                                架构、工程、测试和首页交接文档
└─ functions/auth/callback.js           Pages OAuth callback relay
```

### 2.4 代码所有权

| 范围 | 你负责 | 队友负责 | 汇合方式 |
| --- | --- | --- | --- |
| 产品逻辑 | 匹配页、桌边预览、旁听/入席、桌内聊天、历史、收桌、关系延续 | 不复制这套状态机 | `HomeToMatchContext`、`OpenTableContext` |
| 后端 | TableState、匹配合同、REST/WS、身份隐私、回放、收桌、source | 不直接改业务语义 | 稳定 API + WS 事件 |
| 3D | Bruno Runtime 产品化边界、SceneBridge、状态映射合同 | 最终桌椅、Agent IP、动作动画、镜头表演、环境美术签收 | `AgentActionEvent`、`visual_hint`、单 Canvas |
| 首页 | 提供首页接入合同和示例 | 最终首页、Gallery、手动建桌、邀请、账户入口 | 首页只交接上下文，不复制后端规则 |

重要原则：后端建桌和邀请接口属于当前工作线维护，但它们的调用 UI 属于队友首页；接口存在不代表匹配页应该重新出现“手动建桌”按钮。

---

## 3. 运行时与数据流

### 3.1 前端阶段状态

`App.tsx` 当前同时承担全局阶段和桌内协调：

```text
App phase:
gallery → lobby → expanding → world → collapsing

桌内 phase:
discovering → approaching → seated
```

桌内还叠加：

- `join`：资料授权、旁听/入席和等待后端确认；
- `history`：回放抽屉/弹层；
- `menu`：产品操作层；
- `close`：请求收桌、等待收桌卡；
- `drawer`：卡片收起，不改变桌状态；
- `pending`：消息、主持动作或 REST mutation 的进行中状态。

现在这些状态可以工作，但主要集中在 `App.tsx`，是后续最明显的维护风险。

### 3.2 桌内消息主链

```text
用户提交消息
  → live/backend.ts 做身份、连接和幂等处理
  → WebSocket /ws/tables/{table_id}
  → backend/api/websocket.py 校验 origin、身份、成员资格、限流和帧大小
  → append_message_once
  → Observer 生成新的 TableState
  → Gate 判断是否需要主持
  → Router 选择 SILENCE / PASS / PROBE / REFRAME / GROUND / CLOSE
  → Host 生成可见文案和 visual_hint
  → Reflection / Close 更新后续状态
  → WS 广播 message、agent event、grounding、state、close artifact
  → store.ts 更新 React UI
  → SceneBridge.js 把安全投影同步到 Bruno Runtime
```

后端事实来源是 `TableState` 和持久化账本，前端不应自己推断成员、匹配理由、主持动作和回放内容。

### 3.3 REST / WS 分工

| 类型 | 用途 | 例子 |
| --- | --- | --- |
| REST | 一次性读取、确认或持久化变更 | discovery、lobby、participants、consent、replay、close、invitations |
| WS | 桌内实时输入和事件流 | human message、participant、agent event、state、nudge、close |
| sessionStorage | 页面交接和本地 guest session | 首页 handoff、room session、viewer identity |
| Runtime bridge | 后端状态到 3D 的视觉投影 | speaking、seat state、action、close、anchor |

### 3.4 后端模块关系

```text
FastAPI create_app
  ├─ repository: Memory / JSON
  ├─ provider: deterministic / optional OpenAI
  ├─ sources: candidate / content / personal context
  ├─ identity / privacy / rate limit / event bus
  ├─ REST route groups
  └─ WebSocket table channel

TableState
  → Observer
  → Gate
  → Router
  → Host
  → Reflection / Close / Safety / Mode
```

这是一个“模块化单体”，不是微服务，也不需要现在拆微服务。当前最重要的是保持合同稳定和状态可回放。

---

## 4. 当前完成度对齐

### 已经比较稳的部分

- Bruno 原始环境作为唯一 3D 底座，单 Canvas；没有恢复小车、驾驶和第二套低模世界。
- 匹配页 → Lobby → 桌内的主链已经存在，且同一张桌复用同一 `table_id`、`TableState` 和 Runtime。
- 鼠标拖拽/滚轮只控制相机，不修改后端桌状态。
- 旁听与入席有不同的身份和连接模式；入席后才允许发言和需要成员资格的动作。
- REST 读取 Lobby、桌状态、回放；WS 负责实时讨论和主持事件。
- 重连、消息去重、状态版本、重复提交防护和回放对账已有实现与测试。
- 历史、收桌卡、公共底稿、个人卡和关系行动已经有前端/后端接缝。
- 代码中已经有 `@origin`、`PRODUCT 3D`、`PRODUCT DOM`、`PRODUCT DATA BOUNDARY` 等边界标记。
- 后端已有公开 source adapter、匹配预览/确认、邀请和申请入桌等接口，隐私投影和 fail-closed 规则也已存在。

### 已有能力但不能标成“最终完成”

| 项目 | 现状 | 不能提前宣称完成的原因 |
| --- | --- | --- |
| 队友首页汇合 | 合同、类型和验证脚本已有 | 首页发送端和三条真实浏览器路径仍需双方联合验收 |
| 正式身份 | guest session 已可用 | 知乎 OAuth 尚未开放/尚未取得正式字段，前端还没有正式 hydration |
| 真实个人数据 | OAuth 协调器和 source 适配边界已有 | app credentials、稳定用户字段和正式授权范围待外部条件 |
| 最终桌椅/Agent IP | Bruno 环境和状态映射已有 | 最终 3D 资产、六动作表演和视觉签收由队友负责 |
| 生产持久化 | Memory/JSON 可用于本地和演示 | JSON 不是多进程生产数据库，事件总线和部署拓扑还未定稿 |
| WebGPU 兼容 | 桌面主路径可用 | 移动端、WebGL fallback、低性能设备降级还未完成 |
| 多桌关系延续 | 关系保存和行动回响已有 | 账户级总览、好友/私聊和跨桌推荐属于后续阶段 |

### 需要特别清理的代码漂移

1. `src/domain.ts` 仍保留 `campfire / valley / workshop` 和静态 `galleryTables`；当前生产工作线实际只有 Bruno Swiss Valley 主场景。它们可以作为开发 fixture，但不应继续像产品事实一样参与类型和默认视图。
2. `src/actors.ts` 的 `humanActors` 是开发种子，只能在 `VITE_ALLOW_DEV_SEED=true` 的建桌兜底使用；正式运行不能把它当成真实成员来源。
3. `src/live/contract.ts` 手工镜像后端大量 Pydantic 结构，`src/domain.ts` 又有一套展示模型，长期存在字段漂移风险。
4. `src/live/backend.ts` 同时管理 REST、WS、重连、guest identity、入席策略和 mock fallback；目前可用，但边界过宽。
5. `App.tsx` 同时管理全局导航、Lobby、桌内状态、抽屉、弹层、镜头阶段、交接和 mutation feedback；逻辑正确性已有修复，但继续加功能会增加状态竞争风险。

---

## 5. 代码审查结果：风险分级

### P0：现在就应该守住的边界

#### P0.1 首页归属不能回退

匹配页不再实现手动建桌 UI。它只接收：

- 首页推荐桌 ID；
- 首页主动需求草稿；
- 首页创建完成后的 `OpenTableContext`；
- 邀请接受后进入同一桌的上下文。

任何新按钮都要先问：这是匹配页行为，还是首页行为？如果是创建、邀请、账户 inbox，优先回到首页合同。

#### P0.2 后端不可用时不能静默伪造真实产品

当前 `status === 0` 才进入 `mock.ts`，业务错误不会静默变成 mock，这是正确方向。但生产版本还应增加：

- 明确的 `VITE_DEMO_MODE` 或等价配置；
- UI 上可见的演示状态；
- mock 事件和真实后端事件的 telemetry 区分；
- 生产构建默认不允许 seed 和 mock。

否则 API 网关故障可能看起来像“产品仍在正常工作”，会掩盖真实问题。

#### P0.3 运行环境配置必须显式

Vite 开发服务器固定为 `5174`，并通过 proxy 访问 `8000`；后端 CORS 默认文档仍以 `5173` 为示例。当前本地 proxy 不受影响，但生产或直接跨域访问时必须显式配置 `CORS_ORIGINS` 和 `WS_ALLOWED_ORIGINS`，不能依赖默认值。

### P1：下一阶段应该做

#### P1.1 首页联合验收

至少真实验收三条来源：

1. 首页推荐桌 → 匹配页 → 桌内；
2. 首页手动建桌 → 匹配页/直接桌内 → 同一桌；
3. 首页邀请接受 → 成员同步 → 桌内入席。

三条路径必须复用同一个 `table_id`、Lobby、TableState、Bruno Canvas 和 WS 语义。

#### P1.2 正式身份 hydration

知乎 OAuth 开放后只替换 `identity.ts` 的 provider hydration 和服务端会话校验，不重写桌内状态机。需要验证：

- guest → Zhihu account 的迁移策略；
- 稳定用户 ID 与显示字段；
- profile consent 和私有数据 source 的范围；
- token 不进入前端、TableState 或 replay；
- 退出、过期和重新授权路径。

#### P1.3 前端状态协调器

不建议现在大重写 `App.tsx`，但下一轮应把状态分成三个明确的 reducer/控制器：

```text
NavigationState: gallery / lobby / world / transition
RoomState: discovering / approaching / observer / participant / closed
OverlayState: none / join / history / menu / close / relationship
```

按钮只发 intent，副作用统一由 controller 处理，避免组件同时改 phase、sessionStorage、REST、WS 和 3D interaction lock。

#### P1.4 统一前端合同来源

短期给 `live/contract.ts` 增加运行时校验；中期从 OpenAPI/JSON Schema 或共享 schema 生成客户端类型。`domain.ts` 只保留真正的 UI view model，开发 fixture 移到 `src/dev-fixtures/`，避免产品代码继续引用旧世界和旧成员。

### P2：质量、性能和最终体验

#### P2.1 3D 锚点投影优化

当前 React 层每帧查询 `[data-anchor]` 并写 DOM 样式。它能工作，但在卡片、弹层、Agent、桌边提示增多后会产生不必要的查询和 layout pressure。建议改为：

- Runtime 维护固定 anchor registry；
- 只在相机、viewport、DPR 或锚点状态变化时计算投影；
- 统一写 CSS variables 或单个 transform style；
- 非可见抽屉不参与投影；
- 3D 失效时保留 DOM 语义位置，不阻塞操作。

#### P2.2 WebGPU 和资源策略

Bruno `Game` bundle 已经较大，动态加载是必要的。后续做：

- Gallery 阶段降低 Runtime 更新频率或使用静态预览层；
- 资源按桌区和质量档位拆分；
- 检测 WebGPU 能力并给低性能设备清晰降级；
- 保持单 Renderer/单 Canvas，不为了兼容性恢复第二个世界。

#### P2.3 最终视觉签收

环境基准是 Bruno 原始场景的构图、湖水、灯光、雾、Bloom、景深和动画。桌椅、Agent IP、动作动画和进入表演由队友线完成，但验收必须看完整路径，而不是只看单独模型：

```text
匹配页卡片 → 靠近镜头 → 入席 → Agent 介入 → 收桌
```

### 未来阶段

- Memory/JSON → PostgreSQL + Redis/可靠事件总线；
- 多 worker 下的 WS 广播、锁、幂等和 replay consistency；
- source adapter 的真实知乎数据、匹配质量评估和可追溯来源；
- 跨桌问题 lineage：上一桌未解决的问题如何长出下一桌；
- 账户级邀请、再次遇见、关系总览；
- 语音、同步升级和更复杂主持模式；
- 质量指标：主持介入是否必要、讨论是否推进、收桌后是否产生后续，而不是只看消息数量。

---

## 6. 前端可优化方向

### 6.1 推荐先做的方向：稳定状态，而不是继续堆视觉

当前前端最有价值的优化顺序是：

1. 把按钮动作统一成 intent，并为每个 intent 定义 `idle / pending / success / error / cancelled`；
2. 把“旁听”和“入席”做成清晰的互斥状态，不用 UI 文案猜测后端是否已确认；
3. 将历史、菜单、收桌和关系卡统一为 Overlay contract，明确谁拥有焦点、谁锁定 Runtime 输入；
4. 所有真实数据组件显示 data status：`live / reconnecting / demo / stale / error`；
5. 只有后端确认后才改变成员数、席位、主持动作和收桌状态。

### 6.2 视觉融合方向

保留当前 Bruno 场景作为主视觉基准，DOM 产品层继续遵守“少遮挡、可收起、半透明、场景仍可见”：

- 卡片层默认收起为短标题/胶囊，只在需要时展开；
- 历史和收桌卡采用场景暗化 + 轻微 blur，不做全屏白底后台；
- 所有 2D 层使用统一的层级、透明度、边框和动效 token；
- 3D 锚点只负责空间提示，不承担完整业务内容；
- 业务内容始终保留 DOM 语义和键盘路径，不能只画在 WebGL 上。

### 6.3 现在不要做的事

- 不要重新做一个低模世界或第二套 Renderer；
- 不要在匹配页恢复手动建桌和账户中心；
- 不要在前端编造成员、匹配理由、回放或知乎个人资料；
- 不要因为视觉调整重写 TableState、WS 事件或主持动作语义；
- 不要在 OAuth 未开放前把 guest 字段伪装成知乎资料；
- 不要先拆微服务或大规模重写后端路由，先把产品合同和生产边界稳定下来。

---

## 7. 建议的执行顺序

### 本周：对齐和收口

- [ ] 和队友确认首页 → 匹配页的 `HomeToMatchContext` 与创建完成后的 `OpenTableContext`；
- [ ] 把 `mock`、dev seed、真实后端三种状态在 UI 和构建配置上分开；
- [ ] 把 `domain.ts` 的旧 world/fixture 迁出产品主路径；
- [ ] 补齐直接跨域部署的 CORS/WS 环境变量说明；
- [ ] 对 `App.tsx` 当前状态转移画出状态表，不立即重写。

### 下一阶段：生产和联调

- [ ] 首页三条真实路径联合 E2E；
- [ ] OAuth 开放后接入正式 session hydration；
- [ ] 前端 runtime contract 校验；
- [ ] `App.tsx` 的 Navigation/Room/Overlay 状态拆分；
- [ ] 明确后端生产 persistence、WS 广播和部署拓扑。

### 再下一阶段：体验和性能

- [ ] 3D anchor registry 和按变化投影；
- [ ] WebGPU 能力检测、资源分档和移动端降级；
- [ ] 队友最终桌椅、Agent IP、动作和镜头表演视觉签收；
- [ ] source-backed match、问题 lineage、关系延续质量评估。

---

## 8. 需要和产品一起确认的决策

这些不是代码细节，最好先对齐再动：

1. 下一阶段是否锁定一张 Bruno Swiss Valley 主场景，暂不恢复多世界产品概念？
2. 首页进入匹配页时，是否继续保持同一 Canvas/同一视觉壳，只切换产品阶段？
3. 演示 fallback 是否只允许本地开发和演示环境，生产环境完全禁用？
4. OAuth 开放后，哪些知乎字段允许出现在桌边卡片，哪些只用于后端匹配、不展示给其他成员？
5. 前端下一轮优先级是“状态稳定/真实数据”还是“最终桌椅与 Agent 动作视觉签收”？
6. 桌内收桌后的关系入口，第一版只做再次邀桌/保存关系，还是要同时做账户级好友和私聊？
7. 目标设备是否可以先明确为桌面 WebGPU，移动端只做可读性降级，而不是完整 3D 等价体验？

---

## 9. 最终对齐结论

项目现在的主要问题不是“没有架构”，而是：

> **架构已经形成，但产品入口分工、运行时边界、前端状态层和生产环境边界需要继续收口。**

因此下一步建议保持：

```text
先锁边界和合同
→ 再做首页联合验收
→ 再接正式身份和真实数据
→ 再拆前端状态与优化投影性能
→ 最后做生产持久化、兼容性和长期关系能力
```

这条顺序不会偏离当前分工：你继续负责匹配页、桌内和后端事实链；队友负责首页和 Creative Frontend/3D；双方只在稳定合同和同一张完整桌上汇合。
