# Bruno runtime product integration — implementation status

这是 [`bruno-runtime-product-integration-v2.md`](./bruno-runtime-product-integration-v2.md)
的执行记录。当前阶段按审计项 P1–P6 完成了一轮实现和验收，后续继续从
`repo + spec + git` 接手即可。

## Previous → Current → Next

- Previous：Bruno 的原始 WebGPU 场景已经恢复，但桌区水岸、相机进入、旁听
  身份、回放弹窗和清理边界没有完全闭环。
- Current：P1–P6 的代码主链已经落地；入口、预览、入席、旁听、实时讨论、回放
  和相机交互均在同一个 Bruno Canvas 上运行。桌边水湾已删除独立几何，改为项目
  遮罩接入 Bruno 原生 `Terrain / Floor / WaterSurface`，并通过本轮浏览器验收。
- Next：按 [`P0-P2-PRODUCT-TASKS.md`](./P0-P2-PRODUCT-TASKS.md) 做队友首页汇合、最终
  视觉动作签收和跨来源 E2E；正式身份仍等知乎 OAuth 开放后替换 hydration。

## 2026-09-05 页面职责校正

- 当前仓库里的桌单和主动需求界面是“匹配页”，不是队友尚未完成的最终首页。
- 用户本人负责匹配页、桌边预览和桌内聊天闭环；队友负责最终首页、首页 Gallery、
  首页手动建桌/邀请入口以及 Creative Frontend / 3D 表现。
- 匹配页允许确认后端真实生成的匹配方案，但不放自由填写题目与邀请对象的手动建桌表单。
- 无真实候选时，匹配页展示诚实空态，并把澄清后的题目草稿交还首页；只有首页再次得到
  用户确认后，才调用 `POST /tables` 和 invitation 合同。
- 后端创建、邀请和申请入桌能力继续由产品逻辑与后端线维护；页面归属调整不删除后端能力。
- 当前工作树中的 `CreateTablePanel` 及其匹配页挂载已移除；首页接入仍以
  `specs/P0-P2-PRODUCT-TASKS.md` 与首页交接合同为准，不能把匹配页入口当作 P2 已完成证据。
- 截至 2026-09-05，产品 P0–P2 清单共 59 项，已完成 48 项，开放 11 项；开放项均已
  归类为首页实际接入、OAuth 后身份替换、跨线汇合验收或最终视觉签收，不再把它们混写成
  当前匹配页/桌内代码缺口。
- P2.1 共享 REST 适配层已与后端创建合同对齐：`createTable` 可传公开来源 ID/快照，
  `ParticipantSeed`、`TableState`、主持状态和 `/replay` 来源字段也已补齐；不携带私有画像
  或 OAuth token。
- 主动需求的 source-match 确认会从服务端短期票据中的 MatchPlan 证据派生公开来源 ID，
  写入新桌的 `TableState`；客户端不需要、也不能重新提交候选私有资料。
- 页面交接的事件与 `sessionStorage` 现在按“任一路径成功即可交接”判定结果；存储受限时同壳
  事件仍会成功，事件异常时已写入的短期上下文仍可被目标页面恢复。

后续产品任务以 [`P0-P2-PRODUCT-TASKS.md`](./P0-P2-PRODUCT-TASKS.md) 为准；本文件其余
P1–P6 仍只记录 Bruno Runtime 融合阶段，不与产品优先级 P0–P2 混为同一套编号。

## 产品与运行时不变量

- `src/bruno-runtime/Game/*` 是唯一 3D 渲染器，继续复用 Bruno 的地形、水、植被、
  灯光、天气、雾、Bloom、景深和环境动画。
- `src/TableSea.tsx`、`src/Lobby.tsx`、`src/App.tsx` 是 DOM 产品层；没有第二套
  R3F 场景，也没有截图背景兜底。
- `CameraOrbit` 只负责鼠标拖拽环绕和滚轮缩放，不读写 REST / WebSocket 状态。
- `src/live/api.ts` 是 REST 边界，`src/live/backend.ts` 是 WS 边界。桌状态、成员、
  授权、主持动作、收桌卡和回放都以服务端响应为准。
- `DiscussionPanel` 只读取 `/replay`，不在回放接口失败时悄悄拼接实时消息或前端假数据。
- `src/live/mock.ts` 只存在于明确的开发态后端不可用路径；正常后端错误会显示错误状态。
- 源码边界通过 `@origin`、`PRODUCT DOM`、`PRODUCT 3D`、`PRODUCT DATA BOUNDARY`、
  `src/experience/ORIGIN.md` 和 `REMOVAL-MANIFEST.md` 标记。

## P1–P6 完成情况

### P1 — 相机进入、单 Canvas 与 3D 锚点

- [x] 入口 → 桌边预览 → “靠近这桌”使用同一 Bruno Canvas。
- [x] 相机通过 `SceneBridge.transitionToTable()` 从远景平滑进入桌区；运行时尚未
      就绪时由 `runtimeController` 暂存请求，避免卡在过渡态。
- [x] 桌区、主持人和席位 DOM 使用 Bruno 相机投影的 3D 锚点，而不是固定百分比。
- [x] 历史、菜单和入席弹层打开时锁住 3D 输入；关闭后恢复输入。

涉及文件：
`src/bruno-runtime/Game/CameraOrbit.js`、`Game.js`、`SceneBridge.js`、
`runtimeController.ts`、`Game/tableAnchors.js`、`src/App.tsx`。

### P2 — 原场景视觉基准、桌区水岸与产品家具

- [x] Bruno 原始地形、水面、植被、雾、灯光、材质、Bloom、景深和风场继续由原
      Runtime 驱动，没有换成低模世界或定稿图片。
- [x] 桌区临水半包围构图保留桥侧开口；独立透明水湾、岸线和 Torus 水纹已删除，
      改由项目遮罩进入 Bruno 原生 `Terrain / Floor / WaterSurface`，与远处河道共享
      水深、岸线、动态细节、雾和后处理。
- [x] `TableMeeting` 使用项目自有的 lathed profile、圆角座椅和细节内衬，避免裸
      Cylinder / Capsule 作为最终桌椅；水面和状态标记保持克制，不承担讨论内容。
- [x] 浏览器截图已在 1440×900、1920×1080 和窄屏完成同材质对照，并在左右环绕、
      最近/最远缩放后确认水体不穿过桌椅或桥；产品最终视觉签收仍待完成。

涉及文件：`src/bruno-runtime/Game/Terrain.js`、`Game/World/Floor.js`、
`Game/World/WaterSurface.js`、`Game/World/TableMeeting.js`、`Game/View.js`。

### P3 — 后端事实来源与旁听身份

- [x] 默认桌 ID 统一为 `learning-to-rest`。
- [x] 每个浏览器会话生成独立的 `guest-*` 身份；旁听使用独立 observer ID，不会
      因为固定的开发用户存在就自动升级成 participant。
- [x] 入席只通过 `POST /tables/:id/participants`，入席后才打开 participant WS；
      旁听者没有发言和主持控制权。
- [x] Lobby 和 Discovery 不再从 `humanActors` / `galleryTables` 拼造错误状态；
      后端不可用时只走显式开发种子路径。

涉及文件：`src/live/identity.ts`、`live/backend.ts`、`live/contract.ts`、
`src/App.tsx`、`src/Lobby.tsx`。

### P4 — 回放弹窗、透明 2D 层与无障碍

- [x] 历史弹窗使用 Portal 覆盖在当前 3D 场景上；背景继续渲染，只暗化和模糊。
- [x] 回放显示真实消息、主持动作、状态快照、来源信号、grounding、收桌摘要、
      个人卡和统计计数；接口无数据时明确显示空态。
- [x] 使用 `role="dialog"`、`aria-modal`、Escape、关闭按钮、Tab 焦点循环和关闭
      后焦点恢复；主页面在弹窗期间设置 inert。
- [x] 文字、卡片和按钮保持半透明、低遮挡的产品层风格；窄屏历史入口不会被状态
      条覆盖。
- [x] 入口主题卡、桌单，以及桌内主题卡、当前问题、对话、桌边提示和入席提示都
      支持独立抽屉收起；收起后保留可访问的打开把手，且不影响 3D 或后端状态。
- [x] 入口与桌内底部场景信息条已移除，不再用黑色横框占据场景前景。

涉及文件：`src/live/DiscussionPanel.tsx`、`src/product-ui.css`、`src/App.tsx`。

### P5 — 双客户端、重连与收桌生命周期

- [x] 两个独立浏览器会话完成过旁听、入席、满桌状态、实时消息和 `/replay` 对照。
- [x] participant / observer 的 WS 连接模式分离；断线后按当前身份重新连接，
      不重复加入，也不重复发送已确认消息；pending 消息会按 `/replay` 对账。
- [x] `corepack pnpm verify:p0-p2` 固化双客户端黑盒验收：重复 `message_id` 被拒绝、
      回放保持单条、重连保持成员和版本。
- [x] 独立浏览器完成历史、入席、桌单抽屉开合和两次进出桌；全程保持单 Canvas，
      桌内单 WS，离开后旧连接关闭，再次进入不并发旧连接，RAF 与 console error 均无异常增长。
- [x] 收桌事件、收桌卡和回放恢复分支已接入；observer 不会读取 participant 专属
      个人卡或触发收桌。
- [x] 实时状态版本、消息 ID 和服务端成员数会驱动 DOM 和 3D 席位状态。

本地验收没有主动关闭当前 `learning-to-rest`，避免破坏共享开发数据；收桌接口和
恢复语义由后端测试覆盖，生产联调时还需用独立测试桌做一次完整收桌演练。

### P6 — 清理、标注、稳定性和验收工具

- [x] 移除车辆 / 驾驶 / 玩家移动 / 游戏机制和 respawn 资源；具体清单见
      `src/bruno-runtime/REMOVAL-MANIFEST.md`。
- [x] 新增 `src/experience/ORIGIN.md`，说明 Bruno 原始层、项目适配层和后端适配层。
- [x] Vite 固定 `5174` 并固定 HMR client port，避免开发服务端口漂移导致 Runtime
      动态模块从错误端口加载。
- [x] 新增 `pnpm verify:frontend`，检查品牌/车辆残留、单 Canvas、Portal、后端边界、
      资源清理和来源标注。
- [x] 完成 TypeScript 检查、前端构建、差异空白检查、后端测试和真实浏览器路径验证。

## 验收证据

- `corepack pnpm verify:frontend` — passed。
- `corepack pnpm check` — passed。
- `corepack pnpm build` — passed；仅保留 WebGPU Runtime 体积较大的既有 chunk warning。
- `git diff --check` — passed。
- 后端 `python -m pytest -q` — 真实本地后端测试通过；Python 依赖仅有既有 deprecation warning。
- `python -m compileall -q app tests` — passed。
- 浏览器 `http://127.0.0.1:5174/` + `127.0.0.1:8000`：入口、桌边预览、旁听、入席、
  实时发言、回放、刷新重连、鼠标拖拽和滚轮缩放均已走过；两个会话看到同一个 Bruno Canvas。
- 浏览器控制台无应用错误；只剩 Windows WebGPU 的 `powerPreference` 提示。

## 当前边界与风险

- 当前身份仍是开发态的 per-session `guest-*`；正式登录或身份解析器接入后，只需替换
  `src/live/identity.ts`，不要把身份逻辑放回 3D 层。
- 当前桌椅是项目自有的程序化高细节资产，已经不再是裸基础几何；若最终美术评审要求
  外部 GLB，只替换 `TableMeeting` 的资源加载，不能回退 Bruno 世界或新增第二个 Canvas。
- 收桌的真实浏览器演练应使用独立测试桌；共享本地桌保留了本轮验证产生的 participant
  和消息，未执行 reset / delete。
- 跨桌行动回响总览、首页手动建桌/邀请 UI 和正式 OAuth 不属于当前匹配页与桌内工作线；
  具体接入边界以 [`P0-P2-PRODUCT-TASKS.md`](./P0-P2-PRODUCT-TASKS.md) 为准。
