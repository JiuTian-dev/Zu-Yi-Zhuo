# 前端交互审计与修复记录

这份记录对应 P1–P6 之后的一轮体验层修复。范围是入口、桌边预览、桌内 HUD、
入席、发言、主持请求、回放和收桌卡，不改变 Bruno 原场景的视觉基准，也不把
产品状态写进 3D 层。

## Previous → Current → Next

- Previous：主链已经接通，但按钮可以重复触发；异步请求在切桌后可能回写旧数据；
  动态后端成员无法稳定投影到场景席位；收桌卡和部分弹层缺少完整的焦点与关闭语义。
- Current：动作都有明确的可用条件、进行中态、失败反馈和恢复入口；REST/WS 响应
  按请求代次和成员身份收敛；动态成员、DOM 锚点和 3D 席位使用同一映射；回放和
  收桌卡都是覆盖在场景上的独立弹层。
- Next：接入正式身份后，用独立测试桌做双客户端收桌和断线演练；正式美术评审只
  需要继续看 `TableMeeting.js` 和水岸构图，不再改产品交互边界。

## 交互状态清单

| 区域 | 状态 | 处理 | 数据来源 |
| --- | --- | --- | --- |
| 桌单 | loading / empty / error | 初次读取不显示假桌；错误时保留明确的重连按钮 | `GET /tables/discovery` |
| 桌边预览 | loading / error / open / full / closed | 加载时按钮不可用；错误可重新读取；满桌只允许旁听 | `GET /tables/:id/lobby` |
| 入席 | editing / validating / joining / failed / joined | 空内容不发请求；入席中禁止重复提交；失败保留输入内容 | `POST /tables/:id/participants` |
| 桌内发言 | idle / pending / failed / committed | `message_id` 稳定；失败显示重试；非 participant 不渲染输入框 | WS `human_message` |
| 主持递话 | idle / pending / rejected | 禁止重复请求；服务端错误覆盖本地成功提示 | WS `request_nudge` |
| 收桌 | idle / pending / started / ready | 发送后禁用按钮；收到 `close_started` 后禁止新发言；产物 ready 后显示收桌卡 | WS `request_close` + `close_artifact_ready` |
| 回放 | loading / empty / error / ready | ready 前不渲染空的历史骨架；失败可重试；只读 `/replay` | `GET /tables/:id/replay` |
| 弹层 | open / closing / restored | Escape、背景点击、关闭按钮行为一致；Tab 不跑出弹层；关闭后焦点回到触发点 | DOM / Portal |
| 3D 映射 | loading / mapped / hidden | Runtime ready 时读取最新 store；后端 ID 映射到固定视觉席位；不会回退到第五席 | `TableMeeting` + `SceneBridge` |

## 本轮修复

- `App.tsx`：入席、递话、收桌和重试增加状态锁、反馈和恢复焦点；文案使用当前
  桌题和缺口；收桌卡支持“先留在这张桌”和重新打开；桌内动作在收束期间关闭；
  入席侧栏作为真正的 dialog 处理，背景不可点，Tab 只在侧栏内循环。
- `Lobby.tsx`：增加焦点循环和关闭后的焦点恢复；加载/错误不再展示假空席；错误可
  重新读取；只有后端明确返回 `open` 才允许进入。
- `TableSea.tsx`：区分加载、空桌和后端不可用；列表变化时修正选中索引；进入动作
  增加空值和阶段保护；演示桌单的重连入口明确可见。
- `DiscussionPanel.tsx` / `ClosingCard.tsx`：Portal、Escape、Tab 焦点圈、恢复焦点
  和背景交互隔离；回放响应未完成或失败时不渲染误导性的空内容。
- `TableWorld.tsx`：修复 Runtime 加载竞态，ready 时重新读取最新 live store。
- `TableMeeting.js`：建立后端参与者 ID 到视觉席位的稳定映射，动态成员不再与第五席
  共用锚点。
- `live/backend.ts` / `live/mock.ts`：状态 mutation 强制 participant 边界；模拟定时器
  统一登记，离桌后不会继续发消息；运行时过渡请求不会留下永远 pending 的 Promise；
  回放始终使用当前桌 ID，旧 WS、重连和收桌恢复请求不能回写新桌；消息重试保持
  pending 直到收到确认或超时。

## 验收命令

```text
corepack pnpm check
corepack pnpm build
corepack pnpm verify:frontend
git diff --check
```

浏览器路径：入口桌单 → 选择桌 → 桌边预览 → 旁听 / 入席 → 成员卡 → 发言 → 递话 →
回放 → 收桌 → 收桌卡 → 关闭后重新打开。桌面与窄屏均需确认场景仍在后方、背景不可
误操作、按钮不会重复提交。
