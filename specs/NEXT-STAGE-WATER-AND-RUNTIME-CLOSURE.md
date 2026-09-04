# 下一阶段：水景恢复与运行时收口

> 状态：S1 / S2 / S3 / S4 landed；S5 与产品视觉签收 pending
> 制定时间：2026-09-03  
> 上位产品文档：[`docs/组一桌_知乎赛道一_完整产品沉淀文档_v1.3_最终排版.docx`](../docs/组一桌_知乎赛道一_完整产品沉淀文档_v1.3_最终排版.docx)  
> 视觉与技术合同：[`bruno-runtime-product-integration-v2.md`](./bruno-runtime-product-integration-v2.md)  
> Bruno 基准：`D:\folio-2025@41046b5`（只读）

## 1. 这一次要解决什么

这一阶段不扩产品功能，先把当前 Bruno 融合版收回到可信、可继续开发的状态，重点完成两件事：

1. 恢复 Bruno 原场景里的水景语言，让水重新成为默认构图的重要部分，而不是只保留一个几乎看不见的水面模块。
2. 收紧前后端一致性和 3D 状态映射，补上当前“主流程能跑，但严格验收还没完成”的缺口。

完成后再进入主动需求入口、关系回响等下一轮产品扩展。

## 2. 已确认的水景问题

用户提供的参考图只用于确认水景方向，不作为需要上传的产品图片，也不带回图中的电视、手柄、地图按钮等原作品内容。

需要恢复的是这套视觉关系：

- 水道沿地形弯曲并包围陆地，使桌子处在“临水而坐”的空间里；
- 水体有深蓝水心、青绿色浅滩和暖色陆地之间的清楚层次；
- 岸边有连续但不规则的白色泡沫带，水面有少量顺着水势运动的亮色流线；
- 水面继续受 Bruno 的雾、光照、昼夜、景深和后处理影响，不做贴在地面上的独立低模河流；
- 默认镜头下水面应占据有意义的画面比例，同时桌子仍是视觉和产品焦点。

本阶段确认并修复了一个确定缺口：

- `src/bruno-runtime/Game/Terrain.js` 使用 `this.game.resources.terrainTexture` 生成地表颜色、水深、草密度、岸线和水面细节遮罩；
- `src/bruno-runtime/Game/Game.js` 已恢复加载 `terrainTexture`，并固定 `flipY = false`；
- `public/assets/bruno-runtime/terrain/` 已包含浏览器直载的 `terrain.png`；
- Bruno 基准提交同时包含 `terrain.png` / `terrain.ktx`，并显式加载为 `terrainTexture`。

因此本阶段先恢复了原地形数据链路，而不是另画一条河；当前 `landing` 锚点和默认镜头已在 1440×900、1920×1080 下检查到临水构图。

2026-09-04 的实机截图又确认了一个不能靠调色解决的问题：

- 远处河道由 Bruno 原生 `Terrain → Floor → WaterSurface` 链路生成，拥有水深、岸线、动态水纹、屏幕模糊、雾和昼夜光照；
- 桌边水湾目前由 `TableMeeting.addWaterCove()` 单独创建半透明 `ShapeGeometry`，并用静态 `TorusGeometry` 模拟岸线和水纹；
- 桌边水湾位于地面附近，而原生水面位于 `Water.surfaceElevation`，两者不是同一水面，也不共享同一细节遮罩；
- 实际结果是桌边水湾像覆盖在暖色地面上的透明塑料片，缺少原河道的深蓝水心、青色浅滩、白色泡沫和流动感。

因此 S2 的构图方向保留，但原独立水湾实现不通过视觉验收，必须接回 Bruno 原生水体管线。
本轮已完成该修复：桌边水湾现在通过 `Terrain.terrainNode()` 的项目遮罩
进入 `Floor` 和 `WaterSurface`，`TableMeeting` 不再挂载独立水面、岸线或水纹网格。

## 3. 不可破坏的边界

- 只保留一个 Bruno WebGPU Runtime 和一个 Canvas。
- 不引入背景定稿图、旧低模世界、第二个 R3F 场景或独立水景渲染器。
- 不恢复车辆、驾驶、Player、物理玩法、作品集内容或可见 Bruno 品牌。
- 相机拖拽和滚轮缩放只改变本地镜头，不发送 REST / WS 请求。
- 后端继续是桌状态、成员、授权、消息、主持动作、收桌卡和回放的唯一事实来源。
- `D:\folio-2025` 只用于读取 `41046b5` 的代码和资源，不在其工作树内修改。
- 视觉验证图放在已忽略的本地 QA 目录，不把参考图或“定稿图”当产品资源提交到 Git。

## 4. 执行阶段

### S0 — 把现状记录准确

- 将实施状态从“全部完成”修正为“主流程已跑通，严格 DoD 待完成”。
- 固定一次当前页面捕获条件：viewport、像素比、桌 ID、相机参数、时间和天气。
- 在相同条件下记录当前版与 `folio-2025@41046b5` 的差异，重点看水、岸线、地形、植被和后处理。

验收：后续执行者能从 `repo + spec + git` 知道哪些已完成、哪些仍是缺口。

### S1 — 恢复原生水景数据链路

1. 从 Bruno 基准迁入适合浏览器直载的原始地形数据纹理，优先使用无额外解码依赖的 `terrain.png`。
2. 在 `Game.loadResources()` 中以正确过滤方式加载 `terrainTexture`，保持 `flipY = false`，确认色彩空间不破坏数据通道。
3. 验证 `Terrain.terrainNode()` 的 R/G/B 通道分别重新驱动铺装、草地/阴影、水深与岸线效果。
4. 保留当前删除车辙和物理依赖的改动；不要为恢复水景重新引入 `Tracks` 或 Rapier。
5. 对照 Bruno 基准检查 `Water.js`、`WaterSurface.js`、`Floor.js` 和 `MeshDefaultMaterial.js`，只修复有证据的偏差。

验收：水深渐变、白色岸线和动态流线重新出现；控制台没有缺失纹理、WebGPU 节点或资源错误。

### S2 — 把桌子放回正确的水岸构图

- 保留当前 `landing` 桌锚点、默认镜头和桥侧约 97° 的干燥开口；本轮不移动桥、桌子和相机来掩盖水体问题。
- 删除 `TableMeeting.addWaterCove()` 中独立的 `product-table-water-cove`、`product-table-water-shoreline` 和 `product-table-water-ripple` 几何。
- 新增项目自有的桌区弯月水湾遮罩，使用稳定桌锚点和程序化距离场描述内岸、外岸、桥侧开口与低频不规则边缘；不直接涂改 Bruno 原始 `terrain.png`。
- 将该遮罩合并进 `Terrain.terrainNode()` 的运行时投影：B 通道连续表达浅滩到深水并驱动 `Floor` 下沉，水区同时抑制 G 通道草密度；桥侧开口保持原始地形数据。
- 桌区和远处河道只由同一个 `WaterSurface` 渲染，共享 `detailsMask()`、`shoreNode`、动态 ripples、屏幕模糊、雾、光照、天气和质量档位。
- 岸线与水纹不得再用规则 Torus 描边；它们必须从同一水深遮罩自然生成，并在桌区和原河道之间保持相同的颜色层次与运动速度。
- 至少检查默认视角、左右各一次明显环绕、最近和最远缩放；水不能穿过桌脚、座椅、桥面或干燥落脚点。

验收：在 1440×900 和 1920×1080 下，桌边与远处河道必须表现为同一种水：都有深浅层次、动态流线、连续但不规则的亮岸线，并受同一套雾、光照、景深和后处理影响。关闭桌区遮罩后原 Bruno 河道不得发生回归；拖拽和缩放后桥侧开口仍清楚，桌子仍是第一视觉焦点。

### S3 — 收紧后端事实边界

- `TableState.version` 使用单调比较，旧事件不能覆盖新状态。
- 只有明确的网络不可达或开发开关可以进入 mock；401、403、404、409、422、500 等业务/服务错误必须如实显示。
- 不再因任意 `GET /tables/:id` 失败而自动创建同名桌；自动种子只允许显式开发路径。
- WS 重连采用有上限的指数退避；重连后按 `state → replay → close artifacts` 恢复。
- 发言使用稳定 `message_id`，提供发送中、失败和安全重试状态，并按服务端提交结果去重。
- 将固定 `viewer` 收进身份适配器；本阶段可以保留开发身份，但不得散落在业务组件中。

验收：断网、重连、重复事件、乱序事件和常见 4xx 都有自动化测试；真实错误不会被假数据掩盖。

### S4 — 完成产品状态到 3D 的映射

- 新增或收口唯一 `SceneBridge`，只负责把服务端投影转换成视觉指令。
- 真实成员状态驱动五个席位的空闲、占用、本人和当前发言者状态。
- 六种主持动作 `SILENCE / PASS / PROBE / REFRAME / GROUND / CLOSE` 在 DOM 中完整呈现，在 3D 中只做克制提示。
- 3D 点击只表达本地选择意图，所有入席、授权、发言和收桌 mutation 仍由产品层调用后端。
- 历史弹窗继续覆盖同一个 3D 场景，并补齐 replay 的主持记录、grounding、收桌状态、加载失败重试和焦点恢复。

验收：两个真实浏览器客户端加入同一桌后，席位、发言者、主持动作、收桌和 replay 都能从服务端同步恢复。

### S5 — 视觉与运行时终验

- 前端类型检查、生产构建、后端测试全部通过。
- 用真实后端走通：选桌 → Lobby → 入席/授权 → 双客户端发言 → 主持动作 → 历史 → 收桌 → 刷新恢复。
- 检查 React Strict Mode 下没有第二个 Canvas、重复 RAF、重复监听器或重复 WebSocket。
- 记录低/中/高质量档的水景表现；低档可以减少模糊和粒子，但不能让水与岸线消失。
- 由产品方对默认构图做一次视觉签收。没有签收前，不把“水景完成”写进 README 的已完成项。

## 5. 完成标准

本阶段只有同时满足以下条件才算完成：

- 默认画面能直接看到围绕或贴近桌区的动态水景；水有深浅层次、白色岸线和流动细节，整体仍是 Bruno 原运行时的视觉语言。
- 上述效果来自恢复后的 terrain/water 管线，不是图片背景、独立低模河道或后处理障眼法。
- 车辆、游戏机制和可见 Bruno 品牌仍然为零。
- 桌状态不会被旧 WS 事件回滚，真实后端错误不会触发 mock 或偷偷建桌。
- 席位、发言者、主持动作、历史和收桌都来自后端并能在重连后恢复。
- 自动化检查和双客户端真实链路通过，实施状态文档记录证据与剩余风险。

## 6. 建议提交顺序

1. `docs: define water and runtime closure stage`
2. `fix: restore Bruno terrain data texture`
3. `fix: route table cove through Bruno water pipeline`
4. `fix: harden backend state and reconnect flow`
5. `feat: bridge live table state into Bruno scene`
6. `test: verify water runtime and two-client flow`

每个提交保持单一目的。当前代码已完成 S1、S2、S3、S4；S2 的技术验收已通过，
仍需产品方对默认构图做最终视觉签收。S5 的双客户端、断线恢复和正式身份仍待补证，
未因此宣称本阶段严格完成。

## 7. 本次执行记录

- S1：迁入 `terrain.png`，由 `Game.loadResources()` 以数据纹理方式加载；没有引入独立河道、车辆或物理依赖。
- S2：保留 `landing` 原锚点和桥侧约 97° 开口的弯月构图，删除独立半透明平面与静态
  Torus 描边，改为 `Terrain.terrainNode()` 的项目遮罩扩展原生
  `Terrain / Floor / WaterSurface` 管线。已在 1440×900、1920×1080、窄屏，以及左右
  环绕和滚轮缩放后检查；桌边水面、岸线与远处河道共享同一套材质和后处理。
- S3：统一 `requestRaw` REST 请求和可配置 API/WS origin；状态版本只接受更新版本；WS 使用有上限退避重连；消息显示 pending/failed/retry；`viewer` 集中在 `live/identity.ts`。
- S4：新增唯一 `SceneBridge`，把服务端桌状态、当前发言者、主持动作和收桌阶段映射到 `TableMeeting`，历史继续从 `/replay` 读取。
- S5：`pnpm check`、`pnpm build`、后端 496 项测试和一次真实后端发言→`/replay` 浏览器链路已通过；双客户端及正式身份仍是后续验收项。
