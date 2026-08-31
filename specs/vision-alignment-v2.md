# 组一桌：前端 v2 终极目标对齐

> Status: 已与产品确认（2026-09-01 四项决策拍板）
> Branch: `codex/frontend-v2`（独立于后端会话的 `codex/backend-d05-reflection-close`）
> Supersedes: `specs/zuoyizhuo-worlds.md` 中「不加 Lobby」「无 live discussion」的收缩性边界（保留其视觉/无障碍/性能契约）

## 1. 一句话愿景

打开首页 5 秒内看到一张 AI 为我挑的具体桌；切桌时整个世界跟着变；进桌前先在 Lobby 看「谁在里面、聊到哪、为什么缺我」；入席后讨论是活的——Agent 会递话、问题会推进、收桌有公共底稿和个人卡，最后「问题长出下一桌」。

## 2. 已锁定决策（2026-09-01）

| 决策 | 选择 | 备注 |
|---|---|---|
| 旗舰场景 | 瑞士山谷（用户拍板，推翻 v1.1 文档的篝火优先） | 篝火降为第二世界预览 |
| 场景技术路线 | 混合：AI 背景板 relighting + 深度视差中层 + 少量真 3D 点缀 | 全真 3D 超预算，不做 |
| 首页形态 | 一屏一桌 Hallway（中央主桌 + 两侧信标 + 滚轮/←→切桌 + 世界同步转场） | 推翻 8-29 编辑部长页决策 |
| 讨论数据源 | 直连真后端 WS（demo scenarios 剧本驱动，无需 LLM key），前端保留 mock 兜底 | 后端 D01-D11 已完成，155 测试通过 |
| 必做范围 | 场景升级 + 首页改造 + 预览 Lobby + 旁听 + 收桌卡 + 回响 + 环境音 | 移动端打磨顺延 |

## 3. 终态体验走查（Demo 主线，2-3 分钟）

1. **打开首页**：中央一张主桌卡（桌题/成员/缺失视角/**为什么想到你**），两侧远处 2-3 张候选桌信标，背景即山谷世界。
2. **切桌**：滚轮或 ←→，背景世界光线/雾色/位移 shader 同步电影感转场（displacement）。
3. **预览 Lobby**：点「坐下来看看」→ 谁在里面 / 聊到哪了 / 为什么缺你 / 为什么想到你 → 选 **旁听** 或 **入席**。
4. **进入具体桌**：传送门 → 镜头推入湖边空席（现有 2.5D 管线 + relighting 去纸片感）。
5. **真讨论**：真人打字 → 后端 Table State 推进 → `message_committed`/`agent_action`（SILENCE/PASS/PROBE/REFRAME/GROUND/CLOSE）实时点亮说话席、主持人递话光球、问题卡从 Q0 推进到子问题。
6. **动态补位**：讨论中空席文案随 Table State 更新（缺什么视角）。
7. **收桌**：`close_started` → 收桌仪式；`close_artifact_ready` → 公共底稿 + 个人收桌卡（共识/分歧/洞察）。
8. **回响**：收桌页尾部「这道问题长出了下一桌」→ 回到发现层，飞轮闭合。

## 4. 技术选型（调研已验证的链接）

- **背景转场**：双平面 crossfade + displacement step（GL Transitions 思路，https://gl-transitions.com/）；索引驱动，DOM 与 WebGL 订阅同一 `activeIndex`。
- **卡片→世界**：沿用现有 portal/transition-cover 机制（已验证连续性）。
- **信标**：DOM 按钮（可聚焦、aria 完整）+ 呼吸光点；世界内信标可用 drei Billboard（https://github.com/pmndrs/drei）。
- **relighting**：Codrops《Relighting Images with Depth Maps and Three.js》（https://tympanus.net/codrops/2026/08/19/relighting-images-with-depth-maps-and-three-js/），治纸片感。
- **对话可视化**：AI Town 架构借鉴——「谁在说 = 打字锁」状态机（https://github.com/a16z-infra/ai-town）；drei `<Html>` 头顶短气泡 + 底部字幕条 + 侧栏 transcript 分层（https://drei.docs.pmnd.rs/misc/html）。
- **状态层**：无新依赖——vanilla store + `useSyncExternalStore`；高频量走 ref/transient 更新（zustand transient 模式，https://github.com/pmndrs/zustand#transient-updates-for-often-occurring-state-changes；R3F pitfalls：https://r3f.docs.pmnd.rs/advanced/pitfalls）。
- **后端契约**：`specs/conversation-orchestrator.md`（WS `/ws/tables/{id}?participant_id=`；事件 `message_committed/agent_action/table_state_changed/grounding_card/close_started/close_artifact_ready`）。dev 走 Vite 代理规避 CORS。
- **环境音**：Web Audio 程序化合成（风/湖水/篝火白噪音），默认关闭。
- **素材备选**（若需真 3D 点缀）：KayKit Forest（CC0，6.1MB）、Quaternius Stylized Nature（CC0）、Poly Haven Alps Field HDRI（CC0）——见调研报告。

## 5. 十小时里程碑（stacked diffs，每个 ≤300 行、独立可构建）

| Diff | 内容 | 验证 |
|---|---|---|
| D1 | Hallway 首页：一屏一桌 + 信标 + 为什么想到你 + 切桌世界转场 | `pnpm check` + build + 浏览器走查 |
| D2 | Lobby 预览层 + 旁听/入席双路径 | 同上 |
| D3 | WS 真讨论接入：socket→store→HUD 重构 + mock 兜底 | 后端起服 + 浏览器全路径 |
| D4 | 收桌卡 + 回响（close 事件驱动） | 同上 |
| D5 | 环境音 | 手动开关验证 |
| D6 | 场景视觉升级（relighting/雾光/第五席 3D 椅） | build + 截图对比 |

## 6. 验收标准

- 5-10 秒内能指出「推荐给我的具体桌是什么」并看到推荐理由。
- 切桌时世界（光/雾/场景）同步转场，无跳切。
- Lobby 三问齐全：谁在里面 / 聊到哪 / 为什么缺你；旁听与入席两条路。
- 桌内：谁在说（光）、谁缺失（第五席）、Agent 何时介入（六动作语义）全部可读；至少一次问题推进与一次动态补位。
- 收桌出现公共底稿 + 个人卡；回响页完成「问题长出下一桌」。
- 全程键盘可达、reduced-motion 可用、非 WebGL 环境有 DOM 兜底；`pnpm check` + `pnpm build` 零错误。

## 7. 执行账本（2026-09-01，分支 codex/frontend-v2）

| Diff | 提交 | 验证 |
|---|---|---|
| D1 Hallway 首页 | `12bce02` + `055763c`（修复 UseCanvas portal 不传播 props → hallwayState 外部驱动） | 浏览器实测：一屏一桌、信标切桌、世界随桌切换（uniform 进度 0→1→swap）、零 console 错误 |
| D2 Lobby + 旁听 | `9ede417` | 浏览器实测：CTA→Lobby（6 席位/预览台词/推荐理由）→旁听→seated（is-listening）；join 路径→seated 后 join sheet 自动开→入席成功 |
| D3 WS 真讨论 | `cf65105` | 真后端（uvicorn :8000 + Vite 代理）实测：剧本台词经 4 条木偶连接进入 orchestrator，`message_committed`/`agent_action`/`table_state_changed` 驱动 HUD；主持人 GROUND「落在桌面」+ 问题推进「允许自己停下之后…」；真人入席发言→主持人 PROBE；后端不可达自动降级 mock |
| D4 收桌卡 + 回响 | `ffc5799` | 真后端实测：request_close→close_started→close_artifact_ready→收桌卡（公共底稿+个人卡+回响）全渲染 |
| D5 环境音 | `9fa73f1` | Web Audio 程序化合成（山谷：风/水/鸟鸣；默认关闭）；tsc+build 绿 |
| D6 场景升级 | `7d500a4` | 深度重打光（深度梯度法线+指针跟随主光，亮度 ±7%）+ 淡光束；tsc+build 绿；**视觉确认待面板可见时补** |
| 回归 | — | 390×844：无横向溢出、thumb 上置、HUD 全部入屏、seated/退回/焦点还原路径通（焦点还原在隐藏标签页受 rAF 节流限制，可见状态沿用既有已验证模式） |

运行方式：前端 `npx vite --port 5173`；后端 `cd backend && python -m uvicorn app.main:app --port 8000`（未启动则前端自动进入 mock 演示模式）。

遗留（按优先级）：
1. D6 光束/重打光的视觉确认（等待浏览器面板可见，必要时调 uIntensity）。
2. 主持人六动作的差异化视觉（现统一用 PASS 姿态 + 文案标签区分）。
3. 剧本对话节奏打磨与收桌时机（close_readiness 达标提示）。
