# Bruno runtime product integration — implementation status

这是 [`bruno-runtime-product-integration-v2.md`](./bruno-runtime-product-integration-v2.md)
的执行记录。当前阶段按审计项 P1–P6 完成了一轮实现和验收，后续继续从
`repo + spec + git` 接手即可。

## Previous → Current → Next

- Previous：Bruno 的原始 WebGPU 场景已经恢复，但桌区水岸、相机进入、旁听
  身份、回放弹窗和清理边界没有完全闭环。
- Current：P1–P6 的代码主链已经落地；入口、预览、入席、旁听、实时讨论、回放
  和相机交互均在同一个 Bruno Canvas 上运行。本轮又完成了一轮前端交互审计：
  按钮防重复、异步请求隔离、动态成员席位映射、弹层焦点和错误恢复已补齐，详见
  [`FRONTEND-INTERACTION-AUDIT.md`](./FRONTEND-INTERACTION-AUDIT.md)。
- Next：接入正式身份后做生产环境联调，并用独立测试桌完成双客户端收桌/断线演练；
  如果美术评审需要更高规格桌椅，只改 `src/bruno-runtime/Game/World/TableMeeting.js`
  及其资源边界。

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
- [x] 桌区新增临水半包围构图：透明水湾、岸线和两层轻水纹与原场景共享雾、光照
      和材质管线，补回车辆移除后缺失的水景关系；水湾桥侧保留开口，避免与原 Bruno
      桥的落点形成环形水障碍。
- [x] `TableMeeting` 使用项目自有的 lathed profile、圆角座椅和细节内衬，避免裸
      Cylinder / Capsule 作为最终桌椅；水面和状态标记保持克制，不承担讨论内容。
- [x] 浏览器截图确认桌区水景、桌椅和 Bruno 环境处于同一画面，环境动画和后处理
      仍在运行。

涉及文件：`src/bruno-runtime/Game/World/TableMeeting.js`、`Game/View.js`、
`src/product-ui.css`。

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
      不重复加入，也不重复发送已确认消息。
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
- 主动需求入口、关系/行动回响等产品计划能力不属于本次 P1–P6 范围。
