---
AIGC:
    Label: "1"
    ContentProducer: 001191440300708461136T1XGW3
    ProduceID: a6cc81b1715172b477c70fb5d7fbe175_e2da66e5acc111f1af37525400826444
    ReservedCode1: SXixZ94sQw+oLvtTBm0sjYNTO52jZM6hLZ4FLJFNlAa+NZAOR+J4/uGYaWcIR9/TBLSST24xImNlBs13dsYwKYQwWgajHC7dQTouPkLOV9Qp9Y9T0wZ+yj25BoB9rTK7tHNnEvxpSck6ST48NSV+roH61hU6PbAU6xdx09kkrFUZf5eWSEnP4KTelws=
    ContentPropagator: 001191440300708461136T1XGW3
    PropagateID: a6cc81b1715172b477c70fb5d7fbe175_e2da66e5acc111f1af37525400826444
    ReservedCode2: SXixZ94sQw+oLvtTBm0sjYNTO52jZM6hLZ4FLJFNlAa+NZAOR+J4/uGYaWcIR9/TBLSST24xImNlBs13dsYwKYQwWgajHC7dQTouPkLOV9Qp9Y9T0wZ+yj25BoB9rTK7tHNnEvxpSck6ST48NSV+roH61hU6PbAU6xdx09kkrFUZf5eWSEnP4KTelws=
---

# AI 实施提示词

> 以下内容可直接整段复制，作为上下文交给 AI 编程工具（Cursor / Claude Code / Codex）。配套设计文档为同目录 `00`–`03`。

---

## 提示词正文

### 任务

改造「拼一桌」项目首页：把首页改造成一个黄昏城市场景（公司楼下停车场），并在用户点击「开始匹配」时播放一段「车外第三人称跟车驶离城市」的过场动画，动画结束后跳转到现有匹配页。

仓库路径：`D:\Zu-Yi-Zhuo`。

### 背景

产品理念是「远离城市、回归本我、结交善缘、寻找知心朋友」。首页要演出的核心动作是「离开」：从城市（下班、公司楼下）出发，去往一处不被城市打扰的地方。

完整设计见 `docs/superpowers/specs/2026-09-10-home-city-road/` 下的 `00`–`03` 四份文档，**实现前必须先读完**。

### 技术栈与约束

- React 19 + Vite + Three.js `0.183.2`（`three/webgpu` + TSL）+ GSAP + Zustand
- 渲染管线与资产管线复用 `src/bruno-runtime/`，**不要另起一套**
- 仅桌面端，不做手机端适配
- 不引入新的大型依赖

### 模块边界（严格遵守）

```
src/home/
├── HomePage.tsx                    # 改：挂载场景、编排状态机
├── components/
│   ├── StartButton.tsx             # 新建：浮层「开始匹配」按钮
│   ├── FriendsDock.tsx             # 已有：仅加淡出动画
│   ├── AccountMenu.tsx             # 已有：仅加淡出动画
│   └── ProfilePage.tsx             # 已有：不动
├── scene/
│   ├── CityRoadScene.tsx           # 新建：场景装配总入口
│   ├── useDepartureSequence.ts     # 新建：GSAP 时间轴编排
│   ├── layers/
│   │   ├── RoadLayer.tsx           # 新建：近景路面（可平铺滚动）
│   │   ├── SceneryLayer.tsx        # 新建：中景立牌（视差滚动）
│   │   └── HorizonLayer.tsx        # 新建：远景（溶解过渡）
│   ├── vehicle/
│   │   ├── VehicleRig.tsx          # 新建：车体装配 + 镜头锁定 + 车身起伏
│   │   └── WheelSpin.tsx           # 新建：四轮独立旋转驱动
│   └── camera/
│       └── cameraTrack.ts          # 新建：相机关键帧定义
└── config/
    ├── departureTimeline.ts        # 新建：全部关键时间点
    └── sceneryStages.ts            # 新建：三段沿途配置
```

规则：

1. 相机关键帧只写在 `camera/cameraTrack.ts`，不散落在组件中
2. 时间点只写在 `config/departureTimeline.ts`
3. 三段沿途的参数只写在 `config/sceneryStages.ts`
4. 组件只负责渲染，不负责编排

### 关键实现要点

**1. 车外第三人称，车体与镜头锁定，只改世界。**
行驶过程中相机与车体保持固定相对位姿。「前进感」全部来自世界向后滚动与车轮旋转：

- 三层滚动：近景路面真实滚动（最快）→ 中景建筑与路灯视差滚动（中速）→ 远景天空与天际线（极慢，**只做溶解换地方，不做位移**）
- 车轮：四个独立节点（`wheel_fl/fr/rl/rr`）按车速持续旋转；车身轻微上下起伏强化行驶感
- 全程不出现车内视角，不做仪表台 / 方向盘 / 车内后视镜

**2. 相机路径。**
`boarding` 从 `idle` 停车位机位平滑绕到车尾后方跟随位：车尾正后方约 4.5m、高约 2.2m、略俯视，**不穿窗、不进入车内**。`driving` 期间镜头与车体锁定，不做推拉摇移。

**3. 「城市缩小」的承担方式。**
不再有后视镜作为窗口：城市缩小由 `driving` 段远景天际线后移淡出 + `outro` 抬升俯拍共同呈现。

**4. 状态机。**

```
idle ──点击──> boarding ──> driving ──> outro ──> departed
```

`boarding` 起即锁 `phase`，期间任何点击一律忽略。9.0s 时触发 `onDepartureEnd` 跳转，**只能触发一次**。

**5. 关键时间点**（详见 `02-timeline-and-fallbacks.md`）：
`boarding` 0–1.8s（绕到车尾后方跟随位）→ 起动 1.8–2.4s → 加速 2.4–5.8s → 巡航 5.8–7.2s → 抬升俯拍 7.2–9.0s → 跳转。

**6. UI 时序**：按钮 0–0.4s 淡出；`FriendsDock` 0.6–1.1s；`AccountMenu` 1.1–1.6s，错开。

### 禁止事项

- 不要做可驾驶的车辆（过场是纯动画，无操作）
- 不要做街道穿越、路口、红绿灯、可通行街景
- 不要为 `idle` 做多机位或自由视角
- **不要出现任何车内视角**（仪表台、方向盘、车内后视镜），不要做后视镜实时反射
- 不要把时间点或相机关键帧硬编码进组件
- 不要改动匹配页及其他页面
- 不要动 `src/home/` 之外已有文件的既有逻辑（除必要接线）

### 降级要求（必须逐条落地）

| 情况 | 处理 |
|---|---|
| 无 WebGL2 / WebGPU | 静态帧图片，点击直接跳转 |
| 资产加载失败 | 占位几何顶上，不阻塞 |
| 首屏资源未就绪 | 先出静态图，加载完淡入，不转圈 |
| 过场中重复点击 | `phase` 已锁，忽略 |
| 系统「减少动态效果」 | 跳过相机动画，0.3s 淡出后跳转 |

### 验收标准

- [ ] `idle` 机位固定，仅极轻微环境动效
- [ ] 点击后按钮 0.4s 内淡出，无残留
- [ ] 相机 1.8s 内平滑绕到车尾后方跟随位（约 4.5m 后、2.2m 高、略俯视），全程无穿模
- [ ] `driving` 期间车体与镜头锁定，画面中无车内视角
- [ ] 三层滚动依次呈现：路面 → 中景建筑与路灯 → 远景天际线，远景为溶解无硬切
- [ ] 车轮按车速持续旋转，车身有轻微起伏
- [ ] 「城市缩小」由 `driving` 段远景天际线后移淡出 + `outro` 俯拍呈现
- [ ] 7.2s 起抬升，9.0s 城市缩成一点
- [ ] `onDepartureEnd` 只触发一次
- [ ] 过场期间重复点击无响应
- [ ] 关闭 WebGL 后仍可点击跳转
- [ ] 桌面端帧率维持 60fps 左右

### 建议交付顺序

1. **骨架**：状态机 + 时间轴 + 浮层淡出（画面用占位几何），端到端能跑通到跳转
2. **车外场景**：`idle` 停车位场景装配（先用占位车），确认固定机位取景与帧率
3. **车外跟车**：`VehicleRig` + 车尾后方跟随位 + `boarding` 绕行与防穿模 + 四轮旋转 + 车身起伏
4. **三层滚动**：近景滚动 → 中景视差 → 远景溶解
5. **降级与验收**：逐条过验收清单

每完成一步提交一次，commit message 写清阶段。

---

## 附：给 AI 时必须一并提供的素材/信息

1. 本目录 `00`–`03` 四份设计文档
2. 素材实际文件（按 `03-assets.md` 的目录与命名落盘到 `public/assets/home/`）
3. 现有 `src/home/` 全部代码（让它知道有哪些既有组件与样式约定）
4. 现有 `src/bruno-runtime/` 的入口与资产加载器（复用依据）
5. 匹配页的路由路径与跳转方式（`onDepartureEnd` 的落点）
*（内容由AI生成，仅供参考）*
