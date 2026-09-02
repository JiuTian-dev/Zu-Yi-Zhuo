# 组一桌 × Bruno 实时 3D 运行时融合 SPEC v2.0

> Status: **Active / 唯一实施合同**
>
> Confirmed by product: 2026-09-02
>
> Visual baseline: `D:\folio-2025` at commit `41046b5`
>
> Product repository: `D:\知乎黑客松` / `codex/frontend-v2`

> Execution record: [`IMPLEMENTATION-STATUS.md`](./IMPLEMENTATION-STATUS.md)
>
> Supersedes: `table-runtime-spec.md`、`vision-alignment-v2.md`、`zuoyizhuo-worlds.md` 与 `HANDOFF-2026-09-02.md` 中所有相冲突的视觉和运行时结论

## 0. 不可误读的产品决定

本项目所说的“改之前那套好看的真实 3D 场景”，**专指 Bruno Simon 的 `folio-2025` 实时 WebGPU / Three.js 运行时及其原始场景质量**。

它不是：

- `public/assets/valley-world-clean.png` 或任何其他定稿背景图；
- `src/ValleyScene.tsx` + `src/Diorama.tsx` 的 2.5D / 低模重搭；
- `src/TableWorld.tsx`、`src/TableSea.tsx` 或 `src/table-engine/Game/World/TableMeeting.js` 中用基础几何体拼出的简化桌景；
- 一张看起来像 3D 的图片加少量前景模型。

本次工作的本质是：

> **保住 Bruno 原运行时的视觉能力和场景氛围，在原场景上做产品化减法，再把“组一桌”的完整前后端能力接入。**

“去掉 Bruno 痕迹”指移除产品界面内可见的 Bruno 品牌、作品集内容、车辆和游戏机制；不代表删除其优秀渲染管线。MIT 许可证和版权声明必须保留在第三方声明文件中，但不出现在产品 UI。

如果实现与本节冲突，以本节为准。

## 1. 目标与完成结果

用户最终应经历一条连续产品路径：

```text
入口选桌
  → 桌边预览（成员、空席、为什么想到你）
  → 在同一 Bruno 3D 世界中靠近所选桌
  → 入席与资料授权
  → WebSocket 实时讨论和主持
  → 当前 3D 场景上方打开历史
  → 收桌卡 / 恢复回放
```

目标结果同时满足以下六项：

1. Bruno 原场景的构图、地形、水体、光照、材质、景深、后处理、环境动画和总体氛围尽量原样保留。
2. 页面内无小车、驾驶、角色移动、玩法机制、作品集菜单或可见 Bruno 品牌内容。
3. 鼠标拖拽只环绕相机，滚轮只缩放相机，永远不写后端状态。
4. 3D 是持续存在的沉浸式底座；DOM 是清楚、可访问的产品交互层。
5. 后端是桌和讨论的唯一事实来源；前端不伪造真实会话状态。
6. 代码能一眼区分上游复用、项目新增、适配层和被移除能力。

## 2. P0 产品不变量

以下任一项不满足，都不能称为完成。

### 2.1 视觉不变量

- 桌面端主体验必须运行 Bruno 的真实实时 3D 管线，不允许用图片、视频或低模重搭伪装成主场景。
- 以 `D:\folio-2025@41046b5` 的干净运行结果作为对比基准；比较的是运行时画面，不是后来生成的“定稿图”。
- 保留原始空间尺度、可见距离、地形起伏、水岸关系、植被密度、雾层、日照色彩、材质响应、Bloom、景深和风场造成的整体观感。
- 产品桌、座椅和参与者资产必须与 Bruno 场景处于同一美术完成度。不可用圆柱、胶囊、球体等裸基础几何作为最终可见成品。
- 删除车辆后必须修复其视觉空洞：构图重心、阴影、地表痕迹和相机落点仍要成立，但不可借机重做整套场景。
- 讨论文本不以大量 billboard 卡片遮挡世界；主要内容属于 DOM 对话层。3D 内只允许克制的席位、说话者、主持动作和状态提示。

### 2.2 单一运行时不变量

- 应用只拥有一个持续挂载的 Bruno 3D Runtime / Canvas。
- 入口、预览、靠近桌面、入席和历史弹窗是同一运行时中的镜头与产品状态变化，不是几套互不相关的场景轮换。
- 不在 Bruno Runtime 外再挂第二个 R3F 主场景；React 可以负责生命周期和 DOM，但不能悄悄替换渲染底座。
- 切换桌子时复用环境和渲染资源，只更新所选桌锚点与后端投影，不重复创建 renderer、后处理链和全量资产。

### 2.3 数据不变量

- `TableState.version` 是客户端接受状态更新的单调时钟；旧版本不得覆盖新版本。
- 桌状态、成员、授权、消息、主持动作、收桌和回放只来自 REST / WS 响应。
- 相机方位、缩放、hover、弹窗开关属于本地 UI 状态，不进入 TableState，也不发 WS 事件。
- `/replay` 是历史弹窗的权威数据；实时内存消息只能在等待 replay 时做临时增量展示，不能覆盖或改写 replay。
- mock 与真实后端数据不得混用。

## 3. 视觉基准与来源锁定

### 3.1 上游基准

| 项目 | 决定 |
|---|---|
| 上游仓库 | `D:\folio-2025` |
| 基准提交 | `41046b5`（组一桌改造前的 Bruno 运行时） |
| 基准性质 | 只读视觉与代码来源；不得直接在该工作树继续堆产品改动 |
| 许可证 | MIT；版权声明进入 `THIRD_PARTY_NOTICES.md` |
| 决定性捕获 | 固定 viewport、像素比、随机种子、时间与天气后生成基准截图 |

实施前必须在本仓库记录上游 commit、迁入源码和资产清单、原始场景基准截图、删除车辆后的对比截图以及所有上游实质修改。

### 3.2 明确否决的视觉来源

以下内容可以保留在 Git 历史中说明探索过程，但不得作为最终 3D 主体验：

| 当前实现 | 判定 | 最终处理 |
|---|---|---|
| `public/assets/valley-world-clean.png` | 否决：定稿背景图 | 不作为桌内背景或桌面 fallback |
| `src/ValleyScene.tsx` | 否决：不是 Bruno 原运行时 | 新运行时验收后移除主路径引用 |
| `src/Diorama.tsx` | 否决：低模 / 2.5D 重搭 | 新运行时验收后删除或移入历史归档 |
| `src/TableWorld.tsx` | 否决：简化程序化桌景 | 保留为 React 生命周期壳；真实渲染由 `src/bruno-runtime/Game` 挂载 |
| `src/TableSea.tsx` 与 `src/sea/*` 的低模桌海 | 不作为视觉基准 | DOM 选桌或 Bruno 世界内桌锚点替代后删除主路径引用 |
| `src/table-engine/Game/World/TableMeeting.js` 的基础几何成品 | 否决：美术质量不足 | 删除；产品桌锚点迁入 Bruno Runtime，由同一材质/阴影管线渲染 |

替换采用“先让新 Bruno Runtime 达到视觉门槛，再切主入口”，避免中途留下空白产品。

## 4. Bruno 模块保留、改造与删除矩阵

### 4.1 必须保留的视觉核心

| 能力 | Bruno 代表模块 | 要求 |
|---|---|---|
| WebGPU 渲染与质量档 | `Rendering.js`、`Quality.js`、`PreRenderer.js` | 保留 renderer 初始化、分辨率策略与能力降级 |
| 后处理 | `Rendering.js`、`Passes/cheapDOF.js` | 保留 Bloom、cheapDOF 和最终色彩关系 |
| 材质系统 | `Materials.js`、`Materials/MeshDefaultMaterial.js`、palette | 保留调色板、核心阴影、投影阴影、地面反弹与水邻近响应 |
| 地形和地表 | `Terrain.js`、`World/Floor.js`、terrain 资产 | 保留原高度、颜色、草密度和大尺度空间 |
| 水体 | `Water.js`、`World/WaterSurface.js` | 保留原水面材质、岸线与动画表现 |
| 光照和雾 | `Ligthing.js`、`Fog.js` | 保留原有色阴影、雾层和景深协作 |
| 昼夜和环境 | `Cycles/DayCycles.js`、`Weather.js`、`Wind.js`、`Noises.js` | 保留环境变化；产品可固定默认时段但不能降级观感 |
| 植被与环境动画 | `Grass.js`、`Trees.js`、`Bushes.js`、`Flowers.js`、`Leaves.js`、`WindLines.js` | 保留密度、风场、实例化和运动语言 |
| 场景陈设 | `Scenery.js`、`Fences.js`、`Benches.js`、`PoleLights.js`、`Lanterns.js` | 无品牌、无玩法的环境资产尽量保留 |
| 帧循环和资源加载 | `Ticker.js`、`Time.js`、`ResourcesLoader.js`、`Viewport.js` | 改造成可创建、可暂停、可销毁的产品 Runtime |

### 4.2 需要产品化改造的模块

| 原能力 | 改造结果 |
|---|---|
| `Game.js` | 变为最小 `TableRuntime` 组合根，只装配保留视觉系统、桌场景和桥接层 |
| `View.js` / Inputs | 变为 `CameraOrbit`：拖拽环绕、滚轮缩放、边界约束、DOM 交互仲裁 |
| `World.js` | 变为纯环境世界；车辆、玩法对象和作品区不再实例化 |
| `Intro.js` / `Reveal.js` | 只保留有价值的加载和转场语言，全部文案与品牌替换为组一桌 |
| `Areas.js` / `Scenery.js` | 逐对象审查；只保留自然环境和中性陈设，删除作品集展区与彩蛋 |
| 天气特效 | 仅保留环境性雨、雪、叶、风；删除由玩法触发的攻击、爆炸或灾害效果 |

### 4.3 必须从生产路径移除

- `VisualVehicle`、车辆 GLB、`PhysicsVehicle`、`Player`、`Physics`、`PhysicsWireframe`、`Tracks`、`Respawns`；
- 键盘 / 手柄 / 摇杆驾驶输入以及角色移动状态；
- `Objects` 中仅服务于碰撞玩法的对象逻辑；
- `Explosions`、`ExplosiveCrates`、`Fireballs`、可交互破坏、保龄球等玩法；
- `Tornado` / `VisualTornado` 等游戏灾害；
- `InteractivePoints`、`Zones`、`Map`、作品项目区、职业区、社交区、时间机器等作品集导航；
- `Achievements`、`KonamiCode`、`Easter`、`BlackFriday`、`Notifications`；
- Bruno 的 `Menu`、`Title`、`Modals`、个人介绍、项目文案、社交链接和品牌图形；
- 原多人 `Server`、`Whispers` 等与组一桌后端重复或冲突的状态通道；
- 与上述能力专属的资源、CSS、DOM 和加载项。

删除必须是“停止加载 + 停止实例化 + 移除资源 + 移除入口”四项同时完成，不能只做 `display: none`。

## 5. 目标前端架构

```text
React Product Shell
├── Discovery / Lobby / Seat / Discussion / History / Close DOM
├── ProductState（路由、弹窗、相机意图；非桌事实）
└── BackendGateway（REST + WS + reconnect + replay）
             │ typed events / commands
             ▼
SceneBridge（只把产品投影映射为视觉指令）
             │
             ▼
Bruno TableRuntime（唯一 Canvas）
├── upstream/   原 Bruno 视觉核心，少改
├── adapted/    生命周期、相机、世界装配
└── product/    桌、席位、主持人、状态提示
```

目标目录可按构建约束微调，但边界不得混合：

```text
src/
├── experience/
│   ├── BrunoRuntimeHost.tsx        # React 生命周期壳
│   ├── sceneBridge.ts              # 产品状态 → 视觉指令
│   ├── upstream/                   # [BRUNO-UPSTREAM] 尽量原样复用
│   ├── adapted/                    # [BRUNO-ADAPTED] 有登记的最小修改
│   └── product/                    # [ZUOYIZHUO-SCENE] 桌、席位、主持动作
├── product/                        # [ZUOYIZHUO-UI] DOM 产品层
└── integration/
    ├── rest/                       # [BACKEND-REST]
    ├── websocket/                  # [BACKEND-WS]
    └── contracts/                  # 后端契约镜像与解析
```

每个迁入或新增模块顶部必须有一项来源标记：

```js
/** @origin BRUNO-UPSTREAM — folio-2025@41046b5, behavior preserved */
/** @origin BRUNO-ADAPTED — lifecycle/input adaptation; see ORIGIN.md */
/** @origin ZUOYIZHUO-SCENE — project-owned 3D product element */
/** @origin BACKEND-ADAPTER — REST/WS transport only */
```

仓库必须新增 `src/experience/ORIGIN.md`，逐文件记录上游路径、commit、改动原因和归属。被删除的游戏模块记录在 removal manifest 中，不保留死代码冒充边界。

## 6. 单一 3D Runtime 生命周期

1. 应用启动时创建一次 renderer、scene、camera、后处理和共享环境资源。
2. 桌单加载后，SceneBridge 将桌 ID 映射到稳定 `tableAnchor`。
3. 选桌和预览只切镜头目标、DOM 和选中态。
4. 进入桌内时镜头从预览位过渡到桌边观察位，Canvas 不卸载。
5. 入席后只更新席位占用、说话者和主持视觉，环境继续运行。
6. 历史弹窗打开时 Runtime 仍在后方渲染，可降低帧率，但不能替换成静态图。
7. 页面真正离开或 HMR 重建时，显式释放监听器、RAF、GPU 纹理、几何体和 renderer。

React Strict Mode 下重复 mount/unmount 不得产生第二个循环、重复 WebSocket 或 GPU 资源泄漏。

## 7. 产品状态机

产品导航状态与后端讨论阶段必须分离。

```text
DISCOVERY
  └─ select(tableId) → LOBBY
       ├─ back → DISCOVERY
       ├─ listen → ENTERING → TABLE_OBSERVER
       └─ join → ENTERING → SEAT_CONSENT → TABLE_PARTICIPANT

TABLE_OBSERVER / TABLE_PARTICIPANT
  ├─ history.open → HISTORY_OVERLAY（正交覆盖态）
  ├─ backend close_started → CLOSING
  ├─ close_artifact_ready → CLOSED_ARTIFACT
  └─ exit → DISCOVERY
```

后端 `opening | explore | tension | deepen | close` 只描述讨论进程，不得被复用为页面路由。

### 7.1 入口选桌与预览

- `GET /tables/discovery` 提供桌卡事实；本地只保存 loading / error / selected ID。
- 桌卡显示问题、成员数、空席、阶段和缺失视角；不伪造成员。
- 选桌后调用 `GET /tables/{id}/lobby`。
- “为什么想到你”调用 `POST /tables/{id}/lobby-fit`；若从全局匹配创建桌，则使用 `POST /matches/preview` → `POST /matches/confirm` 流程。
- Bruno Runtime 始终挂载；选桌和桌边预览是镜头状态，可访问选择控件仍是 DOM。

### 7.2 入席与讨论

- 观察者可以看公开投影和历史，但不能发言或收桌。
- 入席前展示资料授权选择；先加入，再提交本人授权，任一步失败都展示可恢复错误。
- WS 使用实际 participant identity；禁止用固定 `viewer` 身份冒充生产用户。
- 输入消息生成稳定 `message_id`，发送中、失败重试和已提交状态可见。

## 8. 后端唯一事实来源：完整接入矩阵

### 8.1 REST

| 产品能力 | 权威契约 | 前端必须实现 |
|---|---|---|
| 发现桌 | `GET /tables/discovery` | loading / empty / error / refresh，使用公共投影 |
| 桌边预览 | `GET /tables/{id}/lobby` | 成员、空席、子问题、缺失视角、状态 |
| 为什么想到你 | `POST /tables/{id}/lobby-fit?participant_id=...` | 展示 `eligible`、`matched_role_gap`、`reason` |
| 匹配建桌 | `POST /matches/preview` → `POST /matches/confirm` | 若入口提供“为我组桌”，完整呈现和确认匹配方案 |
| 创建桌 | `POST /tables` | 只用于真实创建或明确开发种子，不把 404 静默伪装成新桌 |
| 恢复桌状态 | `GET /tables/{id}?participant_id=...` | 首次进入、刷新和重连后恢复隐私投影 |
| 入席 | `POST /tables/{id}/participants` | 冲突、满席、身份失败可恢复 |
| 资料授权 | `POST /tables/{id}/participants/{pid}/consent?viewer_id=...` | 当前授权状态与服务端一致 |
| 离席 | `POST /tables/{id}/participants/{pid}/leave?viewer_id=...` | 若 UI 暴露离席，必须真实落库并同步 |
| 回放 | `GET /tables/{id}/replay?participant_id=...` | 消息、快照、主持记录、grounding 和来源投影 |
| 收桌恢复 | `GET /tables/{id}/close-artifacts?participant_id=...` | 刷新或 WS 断线后恢复公共底稿和个人卡 |

### 8.2 WebSocket

连接：`WS /ws/tables/{id}?participant_id={pid}`。

主产品流的客户端命令是 `human_message`、`request_nudge`、`request_close`。入席和授权优先使用 REST，由后端广播成员 / consent 变化；前端不得同时通过 REST 和 WS 重复提交同一次 mutation。

| 服务端事件 | 产品表现 |
|---|---|
| `message_committed` | 以服务端提交结果进入对话流；按 `message_id` 去重 |
| `agent_action` | 展示六种动作、目标、文案和证据；驱动克制的 3D 主持提示 |
| `table_state_changed` | 只接受不低于当前 version 的隐私投影 |
| `participant_added` / `participant_left` / `participant_consent_changed` | 更新席位和成员 DOM，不由 3D 推断 |
| `safety_enforced` | 显示安全边界状态并采用返回的 TableState |
| `close_started` | 禁止重复收桌，显示进行中 |
| `close_artifact_ready` | 展示公共底稿和仅本人可见的个人卡 |
| `error` | 可读错误、保留未发送文本、允许安全重试 |

六种主持动作 `SILENCE / PASS / PROBE / REFRAME / GROUND / CLOSE` 必须全部有可辨识但不过度表演的 DOM 状态；3D 至少以光、朝向或席位焦点作辅助，不得自行决定动作。

### 8.3 重连与一致性

- 断线使用有上限的指数退避，并显示连接状态。
- 重连后先恢复当前 TableState，再拉 `/replay`，最后继续消费新 WS 事件。
- 按 `message_id` 去重消息，按 `state.version` 去重状态，按 intervention ID 去重主持记录。
- 收桌后重连调用 `/close-artifacts`，不能要求用户再次收桌。
- 页面不得用旧闭包、演示脚本或本地计时器推进真实桌阶段。

## 9. 相机与输入合同

- 鼠标左键拖拽围绕当前桌中心改变 azimuth / polar；不平移桌或角色。
- 滚轮在限定半径内平滑缩放；不可穿过桌面、地形或水面。
- pointer up 后可保留轻微阻尼，不保留驾驶惯性。
- 进入桌面使用产品默认构图，并提供“回到桌面”重置按钮。
- `prefers-reduced-motion` 时缩短或取消大幅镜头过渡。
- 事件起点位于按钮、输入框、历史、入席弹层或 `[data-ui-interactive]` 内时，Orbit 不得启动。
- 单击席位与拖拽用移动阈值区分。
- 相机输入不得调用 REST、发送 WS、改变 participant 或 TableState。
- 移动端如支持，使用单指环绕和双指缩放；性能不支持时明确提示，不偷换成定稿图主体验。

## 10. DOM 产品层与 3D 边界

DOM 负责品牌、桌单、预览、成员与空席、匹配理由、入席授权、讨论正文与输入、连接状态、主持动作证据、历史、收桌卡、错误和无障碍语义。

3D 负责环境、桌椅、与服务端成员投影一致的席位占用、当前说话者、主持目标和收束阶段的辅助视觉；不承载长篇正文、表单或关键操作。

## 11. 对话历史弹窗

- 历史是覆盖态，不跳页、不换场景。
- 打开后 Bruno 3D 仍在后方；仅对场景容器暗化和适度模糊。
- DOM 弹窗通过 Portal 位于 Canvas 上方，锁定背景产品交互和 Orbit，支持关闭、Escape、焦点圈和焦点恢复。
- 每次打开或按 freshness 策略调用 `/replay`；展示 loading、empty、error、retry。
- 内容至少包含消息顺序、参与者、主持动作、阶段变化、grounding 来源和收桌状态。
- 已入席用户携带本人 identity；观察者只取后端允许的公共投影。
- fetch 失败时可展示“本连接已收到但尚未确认完整”的实时消息并明确标注；不得构造假历史。
- 关闭后焦点回到打开按钮，3D 恢复正常清晰度和帧率。

## 12. Mock / 后端不可用策略

- 正常模式始终先连接真实后端；不得默认启动演示脚本。
- 只有确认后端不可达时才允许进入隔离 Demo Mode，持续显示“演示数据，不会保存”。
- Demo 使用独立 store、table ID 命名空间和确定性数据；恢复真实连接时整会话切换，禁止混合。
- 4xx 业务错误不等于后端不可用，不能自动 fallback。
- 生产构建可通过配置完全关闭 Demo Mode。

## 13. 品牌清理与许可证边界

最终用户路径中不得出现 Bruno Simon 姓名、folio 标题、个人介绍、项目名称、社交链接、Logo、车辆、驾驶教学、地图、成就、彩蛋或作品集交互点。

MIT License、`Copyright (c) 2025 Bruno Simon`、上游 commit 和文件来源必须保留在代码 / 分发声明中。完成前执行大小写不敏感的源码、构建产物和浏览器可见文本扫描；许可证命中允许，产品 DOM、Canvas 文案和网络内容命中不允许。

## 14. 实施阶段与硬门槛

### M0 — 基准冻结

- 在干净的 `folio-2025@41046b5` 启动上游；固定镜头、时间、天气、seed 和 viewport。
- 保存运行时基准截图与模块 / 资产 manifest；当前产品失败实现只作为反例。

**Gate:** 能证明基准来自真实 Bruno Runtime，而非图片。

### M1 — 干净迁入渲染内核

- 迁入视觉核心和必要资产；在 React 壳中只挂一个 Runtime。
- 建立 create / pause / resume / destroy 生命周期；保持原场景画质，暂不接产品桌。

**Gate:** 与 M0 并排比较，除品牌 UI 外无明显降级；无第二 Canvas。

### M2 — 删除车辆、玩法和品牌

- 按第 4.3 节完成代码、资源、加载项和 UI 四层删除；修复构图和地表。
- 完成源码 / 构建 / 浏览器品牌扫描。

**Gate:** 无车、无驾驶、无角色移动、无品牌，但仍一眼是原 Bruno 场景质量。

### M3 — 相机和产品桌

- 接入 Orbit、输入仲裁和镜头状态。
- 使用通过视觉评审的桌、座椅、参与者和主持人资产，建立稳定 tableAnchor / seatId / participantId 映射。

**Gate:** 桌景美术不拉低环境质量；拖拽和滚轮只改变镜头。

### M4 — REST 产品路径

- 完成 discovery、lobby、fit、恢复桌、入席、consent。
- DOM 与 3D 席位一致；真实后端错误不静默转 mock。

**Gate:** 真实后端走通入口选桌 → 预览 → 入席，刷新可恢复。

### M5 — WS 实时讨论

- 完成 identity、连接、消息幂等、重连、六种主持动作、安全和成员事件。
- 消息与主持动作同时更新 DOM 和克制的 3D 提示。

**Gate:** 两个真实客户端可互相看到提交消息、状态和主持动作。

### M6 — 历史、收桌和恢复

- 完成 `/replay` 覆盖弹窗、收桌事件和 `/close-artifacts` 刷新恢复。
- 验证公共底稿与个人卡隐私边界。

**Gate:** 断线 / 刷新后仍恢复完整历史和正确个人收桌卡。

### M7 — 删除失败路径并回归

- 移除否决场景、重复 renderer、无用资源和死 CSS。
- 补齐来源文档、测试和最终截图；回归桌面、窄屏、reduced motion 和断线。

**Gate:** 第 16 节全部通过。

## 15. 验证合同

### 15.1 自动化

- `corepack pnpm check`；
- `corepack pnpm build`；
- 后端完整 `python -m pytest -q`；
- 单元：state version、WS 去重、重连、mock 隔离、相机不触发网络；
- 集成：REST / WS 契约与 identity / privacy；
- E2E：入口 → 预览 → 入席 → 双客户端发言 → 主持 → replay → close → refresh recovery。

### 15.2 视觉

固定捕获 1440×900、1920×1080 桌面和 390×844 窄屏；覆盖入口远景、预览、入席默认构图、拖拽后构图、历史、六种主持动作和收桌卡，并保留原 Bruno 基准、去车后、产品桌完成后三组并排图。

通过标准：场景不是静态背景图；地形、水、植被、光、雾、材质、景深和环境动画均实际运行；去车和加桌未造成空洞、廉价几何感或光照割裂；DOM 不遮核心桌景。视觉方向经用户确认后再进入大规模后端 UI 收尾。

### 15.3 运行时

- 参考桌面 1920×1080、默认质量、预热后目标 ≥ 45 FPS；
- 没有每帧 React state 更新；
- 打开 / 关闭历史 20 次不增加 renderer、WS 或 RAF 数量；
- 切桌 20 次不重复下载共享环境资产；
- 干净加载无 console error、未处理 Promise 或持续失败请求。

## 16. Definition of Done

### 视觉与场景

- [ ] 主场景由 Bruno 原实时 3D Runtime 驱动，不是图片或低模重搭。
- [ ] 原构图、地形、水、光、材质、景深、后处理、动画和氛围通过对比验收。
- [ ] 车辆、驾驶、角色移动、游戏机制和可见 Bruno 品牌全部消失。
- [ ] 产品桌、座椅、参与者和主持人达到同场景美术质量。
- [ ] 全流程只有一个持续挂载的 3D Runtime。

### 产品与后端

- [ ] 真实后端走通选桌、预览、匹配理由、入席、授权和恢复。
- [ ] WS 发言、幂等、重连、安全事件和六种主持动作完整落地。
- [ ] 历史弹窗覆盖当前 3D，内容以 `/replay` 为准。
- [ ] 收桌、个人卡、公共底稿及 `/close-artifacts` 恢复完整。
- [ ] mock 只在后端不可达时隔离启用，并有醒目标记。
- [ ] 隐私投影和 identity 边界经双用户测试验证。

### 工程质量

- [ ] `ORIGIN.md` 和第三方 MIT 声明完整。
- [ ] 生产路径无失败方案、重复 renderer 和游戏死代码。
- [ ] check、build、后端测试、集成测试和 E2E 全绿。
- [ ] 视觉、性能、资源释放、窄屏与 reduced-motion 回归通过。
- [ ] Git 工作树清楚；每阶段有可回退的独立提交和验证证据。

## 17. Git 交付纪律

实施使用当前 `codex/frontend-v2` 分支，按可验证阶段提交：

1. `docs: define bruno runtime product integration v2`
2. `chore: freeze bruno runtime visual baseline`
3. `feat: import bruno visual runtime core`
4. `refactor: remove vehicle gameplay and portfolio surfaces`
5. `feat: add table camera and production scene assets`
6. `feat: bridge table rest state into runtime`
7. `feat: connect websocket discussion and host actions`
8. `feat: add replay overlay and close recovery`
9. `test: verify integrated table journey and visual baseline`
10. `chore: remove rejected scene implementations`

每个提交必须只含该阶段文件、记录验证结果、不提交范围外的 `3D/` 或用户 DOCX、不污染 `D:\folio-2025` 工作树，并且不在下一道 Gate 通过前删除最后一个可运行路径。

## 18. 非目标

- 不重做 Bruno 的材质、地形或后处理来追求另一套美术风格。
- 不恢复驾驶、物理、角色移动或作品集玩法。
- 不让 3D 自行承担讨论编排、业务状态或隐私判断。
- 不把全部后端管理端能力塞进桌内；“完整落地”指第 8 节的用户产品闭环。
- 不以“build 通过”替代真实浏览器、真实后端和视觉验收。

## 19. 当前仓库事实（spec 创建时）

- 原主路径 `ValleyScene/Diorama + valley-world-clean.png` 已移除；当前由 Bruno Runtime 作为唯一渲染底座。
- `TableWorld.tsx` 只负责生命周期；旧 `table-engine` 与低模桌海已移除。
- REST、WS、历史和收桌已有部分适配代码，可按契约复用，但必须重新验证 identity、重连、隐私和 mock 隔离。
- 最近“approved valley scene”类提交不代表当前产品批准；本 spec 已明确推翻该结论。
- 用户已有的 `3D/` 和 DOCX 是工作区素材，不属于本次 spec 提交。
