---
AIGC:
    Label: "1"
    ContentProducer: 001191440300708461136T1XGW3
    ProduceID: a6cc81b1715172b477c70fb5d7fbe175_e1689488acc111f1af37525400826444
    ReservedCode1: 4kNLntdxk5fBHd/B3E4wCoVS9wUYMFDb1ZODI2lqtzK1u2MLVWTBJ8JxnoKjUuB+xmrwShgJfoD/kIR3bRNP1mqzpXGo35W9+CjF+FuzCTNA6af9ZneaDJ+qn5xU2FAyvbfIDDKtMrOSiPescR4Jt8rgndPQyngMmgklcOkBTerVmhwePXfJBWDdU70=
    ContentPropagator: 001191440300708461136T1XGW3
    PropagateID: a6cc81b1715172b477c70fb5d7fbe175_e1689488acc111f1af37525400826444
    ReservedCode2: 4kNLntdxk5fBHd/B3E4wCoVS9wUYMFDb1ZODI2lqtzK1u2MLVWTBJ8JxnoKjUuB+xmrwShgJfoD/kIR3bRNP1mqzpXGo35W9+CjF+FuzCTNA6af9ZneaDJ+qn5xU2FAyvbfIDDKtMrOSiPescR4Jt8rgndPQyngMmgklcOkBTerVmhwePXfJBWDdU70=
---

# 时间轴、UI 时序与异常降级

## 1. 总时间轴（约 9 秒）

从点击到跳转，全长约 9s。三条泳道同时推进，互不越权。

| 时间 | 相机 / 画面 | UI 浮层 | 路由 |
|---|---|---|---|
| 0.0s | 点击，`idle` → `boarding` | 按钮开始淡出 | — |
| 0.0–1.8s | 相机从 `idle` 停车位机位平滑绕到车尾后方跟随位（车尾后方约 4.5m、高约 2.2m、略俯视） | 按钮 0–0.4s 走完；`FriendsDock`、`AccountMenu` 0.6–1.6s 错开淡出 | — |
| 1.8s | 就位，`boarding` → `driving` | 全空 | — |
| 1.8–2.4s | 起动：车身轻微前后顿挫、车灯亮起、车轮开始转动 | — | — |
| 2.4–5.8s | 加速：路面滚动提速、中景视差加快、车轮转速提升；城市段 → 城郊段 | — | — |
| 5.8–7.2s | 巡航：旷野段，速度感峰值 | — | — |
| 7.2–9.0s | 抬升俯拍：车变小、公路成一条线、城市缩成一点 | — | — |
| 9.0s | `outro` → `departed` | — | `onDepartureEnd` 触发，跳转匹配页 |

### 泳道分工

- **相机泳道**：只负责位姿（绕到车尾跟随位、俯拍）
- **画面泳道**：只负责三层滚动、车轮旋转与远景溶解
- **UI 泳道**：只负责淡出
- **路由泳道**：只在 9.0s 有一个动作

三者不互相调用，统一由一条 GSAP timeline 编排。

## 2. 关键时间点

| 名称 | 时间 | 说明 |
|---|---|---|
| `t_click` | 0.0s | 锁 phase，起 timeline |
| `t_board_end` | 1.8s | 相机就位（车尾后方跟随位） |
| `t_ignite` | 1.8–2.4s | 起动顿挫 |
| `t_accel` | 2.4–5.8s | 加速段 |
| `t_cruise` | 5.8–7.2s | 巡航段 |
| `t_rise` | 7.2–9.0s | 抬升俯拍 |
| `t_end` | 9.0s | 路由跳转 |

以上全部写在 `config/departureTimeline.ts`，改时间点只改这个文件。

## 3. UI 时序

| 元素 | 起 | 止 | 方式 |
|---|---|---|---|
| 「开始匹配」按钮 | 0.0s | 0.4s | 缩放反馈后淡出 |
| `FriendsDock` | 0.6s | 1.1s | 上移淡出 |
| `AccountMenu` | 1.1s | 1.6s | 上移淡出 |

错开而非同时，避免整块 UI 一起消失的板结感。

## 4. 异常与降级

| 情况 | 处理 |
|---|---|
| 无 WebGL2 / WebGPU | 退到静态帧图片，点击直接跳转，不播动画 |
| 资产加载失败 | 用占位几何顶上，不阻塞流程 |
| 首屏资源未就绪 | 先出静态图，加载完淡入，不显示 loading 转圈 |
| 过场中重复点击 | `phase` 已锁，忽略 |
| 系统开启「减少动态效果」 | 跳过相机动画，0.3s 淡出后直接跳转 |

降级路径必须在实现时逐条落地，不允许出现「白屏等资源」「点击无响应」两种状态。

## 5. 性能预算

| 项 | 目标 | 上限 |
|---|---|---|
| 帧率 | 60fps | 不低于 45fps |
| 树实例数 | 60 | 120（`InstancedMesh`） |
| 首屏可交互 | 1.5s | 3.0s |

原则：

1. 车体与镜头锁定，避免每帧重算相机位姿
2. 远景用雾遮远，不追求远景细节
3. 中景立牌用贴图而非模型，控制三角面
4. 事后测：`idle` 静止时 GPU 占用应接近零（仅轻微动画）

## 6. 验收清单

- [ ] `idle` 机位固定，仅极轻微环境动效
- [ ] 点击后按钮在 0.4s 内淡出，无残留
- [ ] 相机 1.8s 内平滑绕到车尾后方跟随位（约 4.5m 后、2.2m 高、略俯视），全程无穿模
- [ ] `driving` 期间车体与镜头锁定，无推拉摇移
- [ ] 画面中不出现车内视角（无方向盘 / 仪表台 / 车内后视镜）
- [ ] 三层滚动依次呈现：近景路面（最快）→ 中景建筑与路灯（视差）→ 远景天际线（极慢、仅溶解）
- [ ] 车轮按车速持续旋转，车身有轻微起伏
- [ ] 三段依次呈现：城市 → 城郊 → 旷野
- [ ] 远景切换为溶解，无硬切跳变
- [ ] 「城市缩小」由 `driving` 段远景天际线后移淡出 + `outro` 俯拍共同呈现
- [ ] 7.2s 起相机抬升，9.0s 城市缩成一点
- [ ] `onDepartureEnd` 准确触发一次，不重复
- [ ] 过场期间重复点击无任何响应
- [ ] 关闭 WebGL 后仍能点击跳转
- [ ] 开启「减少动态效果」后 0.3s 内跳转
*（内容由AI生成，仅供参考）*
