# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

想找一桌真实对话的人：从首页进入，浏览推荐/建桌/账户，再被送进匹配页或桌内。

## Product Purpose

组一桌把值得聊的话交给刚好在场的人。首页负责账户入口、推荐与手动建桌交接；匹配页展示正在发生的桌；桌内完成旁听、入席与讨论。

## Positioning

席位与匹配理由来自后端真实 Lobby / Match 合同，前端不伪造成员、匹配理由或知乎身份。

## Constraints

- 知乎正式 OAuth 在约定日期前不可用：首页可用本地演示登录，不得伪造知乎用户或写入 OAuth token。
- 首页不复制匹配/桌内业务判断；交接走 `HomeToMatchContext` / `OpenTableContext`。
- 匹配页与桌内现有实现由本仓库既有工作线维护；本次首页工作不改匹配页视觉与行为。

## Terminology

- 首页、匹配页、桌边预览（Lobby）、桌内、个人中心、演示登录

## Brand

产品名：组一桌。首页视觉资产：用户提供的露营结伴插画（全幅背景）。

## Accessibility

Web；交互控件需键盘可达；登录菜单支持 Escape 关闭。

## Open Questions

- 正式知乎 OAuth 接入后，演示登录如何平滑替换。
- 首页 Gallery / 手动建桌完整流程的视觉范围（本次先交付账户入口与个人中心）。
