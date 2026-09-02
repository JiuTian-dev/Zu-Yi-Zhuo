# 组一桌 · Table Runtime 规格

> Status: 融合实施中（2026-09-02）
> Scope: 项目自有桌面世界、鼠标环绕、讨论 HUD 与后端闭环

## 目标

- 用户进入一张桌后，只通过鼠标拖拽和滚轮观察桌面，不驾驶载具、不操作游戏角色。
- 3D 只承载桌、座位、人物、草地、灯光与环境；问题、成员信息和讨论历史由项目自己的 DOM HUD 承载。
- 后端是讨论事实来源：Lobby、fit-preview、建桌、入席、资料授权、WebSocket、递话、收桌和回放都可被前端调用。
- 断开后仍可通过 replay 重建桌面叙事；后端不可用时保留现有确定性 mock 演示。

## 场景结构

```
src/table-engine/                 # 项目桌面运行时
  Game/                            # renderer、材质、雾、风、地形、生命周期
  Game/CameraOrbit.js              # 鼠标拖拽环绕 + 滚轮缩放
  Game/World/World.js              # 一桌：桌、五席、人物、烛光、灯笼、花
src/TableWorld.tsx                 # React 挂载与卸载边界
src/live/api.ts                    # REST JSON client
src/live/backend.ts                # WS、剧本、mock fallback、桌生命周期
src/live/DiscussionPanel.tsx       # 只读讨论历史和状态回放
```

场景视觉属于“湖边的一桌”：暖色桌面、低饱和草地、微弱烛光和留白 HUD。第三方渲染代码只作为内部技术来源，界面、文案、挂载名、资源路径和交互均使用项目语义；许可证文件保留在 `src/table-engine/THIRD_PARTY_LICENSE.md`。

## 前后端接线

| 前端行为 | 后端契约 | 当前入口 |
|---|---|---|
| 首页桌卡/桌边预览 | `GET /tables/discovery`、`GET /tables/{id}/lobby` | `live/api.ts`、`App.tsx`、`Lobby.tsx` |
| 为什么想到你 | `POST /tables/{id}/lobby-fit` | `live/api.ts`、`Lobby.tsx` |
| 建桌与恢复桌 | `POST /tables`、`GET /tables/{id}` | `live/backend.ts` |
| 入席与资料授权 | `POST /tables/{id}/participants`、`POST .../consent` | `live/backend.ts`、入席弹层 |
| 实时对话/主持 | `WS /ws/tables/{id}` | `live/backend.ts`、`live/store.ts` |
| 冷启动递话 | WS `request_nudge` | 桌内对话 dock |
| 收桌 | WS `request_close`、`close_*` 事件 | `ClosingCard.tsx` |
| 讨论历史 | `GET /tables/{id}/replay` | `DiscussionPanel.tsx` |

隐私边界保持在服务端：入席前只显示公开 Lobby；资料是否对桌公开由用户勾选；回放默认使用公共投影，入席后才携带本人身份。

## 交互不变量

- 桌内拖拽只改变相机方位，不写入 Table State，不产生消息或行为事件。
- 所有真人消息仍以 `message_id` 发送，由后端负责幂等、证据、主持动作和安全判断。
- UI 不自行推断主持动作或重算收桌底稿；只消费 WS 事件和 replay 响应。
- `prefers-reduced-motion` 下禁用镜头大幅动效；窄屏保留 DOM HUD 和可键盘到达的按钮。

## 验证与状态

- `pnpm check`：通过
- `pnpm build`：通过；仍有包体积和 mock 动态导入提示
- `python -m pytest -q`：496 passed
- 已验收：浏览器真实拖拽视觉、桌海→预览→桌内→回放主路径、入席空内容校验、干净页面运行时无 error
- 待补：长时间反复进出桌面的 WebGL 资源回收压力测试、六种主持动作的独立 3D 姿态差异化
