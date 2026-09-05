# 组一桌

组一桌是一款围绕“把值得聊的话，交给刚好在场的人”的多人讨论产品。
用户从正在发生的桌里选一个问题，先在桌边看看成员和缺席的视角，再进入同一片湖边 3D 场景，入席、发言，最后留下可以回看的讨论记录和收桌卡。

当前仓库是一个可以本地运行的前后端产品原型。前端主场景使用 Bruno Simon `folio-2025` 的实时 WebGPU / Three.js Runtime；产品交互和讨论状态由组一桌自己的 React、REST 和 WebSocket 层负责。

产品方向仍以 2026-08-26 定稿的[《完整产品沉淀与调研文档 v1.3》](docs/组一桌_知乎赛道一_完整产品沉淀文档_v1.3_最终排版.docx)为上位基线；本次代码对齐更新见[《完整产品沉淀与调研文档 v1.4》](docs/组一桌_知乎赛道一_完整产品沉淀文档_v1.4_代码对齐更新.docx)。本文记录产品计划在当前代码里的落地情况；`specs/bruno-runtime-product-integration-v2.md` 是实现约束，不替代产品定义。

## 产品计划（上位方向）

### 这不是一个普通聊天框

“组一桌”要解决的不是“帮我找一个人聊天”，而是让 AI 发现：哪些人正在靠近同一个问题，却还没有真正坐到一起。

AI 关注的也不只是热门问题，而是：

- 一组人有共同的问题，但拥有不同的经历和判断；
- 讨论里存在还没有被补上的视角或认知缺口；
- 这些人有真实表达和参与的可能；
- 这次交流有机会产生新的认识、关系、行动或情绪价值。

### 两个入口

- **偶遇**：用户看到一张正在形成的桌，先了解“为什么是这桌、还缺谁”，再决定旁听或入席。
- **主动需求**：用户直接说自己想找人聊什么、一起做什么，Agent 帮忙澄清问题，再推荐已有的桌或组织新桌。

主入口负责让人遇见一场本来不会发生的交流，主动入口负责承接明确的目的。两条路最后都进入同一个圆桌机制。

### 一桌如何工作

默认是一张 5 人真人桌，圆桌 Agent 作为主持人存在，不占真人席位。桌子默认异步，讨论变得密集时再升级成限时同步。

Agent 的重点是听和递话：必要时追问、换角度、把观点落到事实或行动上；如果桌子自己聊得好，Agent 应该少出现。评价一桌好不好，不看消息数量，而看有没有新事实或视角、有没有安全的分歧、有没有人被接住，以及问题有没有变得更清楚。

一次讨论结束后，除了共享的公共底稿，每个人还应得到不同的个人收桌卡。它们要回答：我带走了什么、判断改变了吗、接下来想做什么、这桌上有没有值得继续联系的人。

产品最终要形成两个循环：

```text
用户循环：好体验 → 有收获 → 产生行动或连接 → 愿意回来
问题循环：未完成问题 → 第一桌 → 新视角/关系/行动 → 下一桌
```

## 项目现状

截至 2026-09-05，主流程已经打通：

```text
队友首页交接
  → 匹配页选桌
  → 桌边预览
  → 进入同一套实时 3D 场景
  → 入席与资料授权
  → WebSocket 实时讨论
  → 当前场景上的历史弹窗
  → 收桌卡与回放
```

当前 checkout 主要对应队友首页之后的“匹配页 + 桌内”工作线：最终首页、首页 Gallery、
手动建桌和邀请入口由队友负责，通过 `docs/HOME-INTEGRATION-CONTRACT.md` 与本项目汇合。

这对应产品计划里的“主入口 + 第一桌闭环”。主动需求入口、当前桌关系保存和行动回响已经接入匹配页/桌内；完整的知乎公开信号配置、跨桌账户总览、最终首页汇合和正式身份仍未完成。

### 前端

- React + Vite，3D 底座是 Three.js WebGPU。
- 入口、Lobby、入席、讨论、历史和收桌卡都是 DOM 产品层，叠在同一个持续存在的 3D Runtime 上。
- 3D 场景已经迁入原运行时的地形、水面、植被、灯光、雾、风场、Bloom、景深和环境变化；原始 `terrain.png` 数据纹理已恢复，默认镜头现在能看到临水构图。
- 小车、驾驶、角色移动、游戏玩法、作品集菜单和可见的 Bruno 产品界面已经从生产路径移除。
- 桌内只允许鼠标拖拽改变镜头环绕角度，滚轮改变距离；这些操作不会写入后端，也不会影响桌状态。

### 后端

- FastAPI 提供桌发现、Lobby、桌状态、加入、资料授权、收桌和回放接口。
- WebSocket 负责真人发言、主持动作、状态更新、安全提示和收桌事件。
- 桌状态和回放以服务端为准，前端不会用本地假数据覆盖真实会话。
- 后端默认可以使用内存仓储；设置 `TABLE_REPOSITORY_PATH` 后可写入 JSON 快照。
- 后端还包含匹配预览、主动需求澄清、邀请、旁听、递话、收藏和安全相关接口；这些能力会按产品主流程逐步补齐更完整的前端入口。

### 当前不是最终生产版的部分

- 当前使用会话级 `guest-*` 身份；知乎 OAuth 申请已提交，生产身份、用户 token 托管和真实个人数据仍待官方凭据。接入清单见 [`specs/ZHIHU-OAUTH-REAL-DATA.md`](specs/ZHIHU-OAUTH-REAL-DATA.md)。
- Bruno 场景里的桌椅和席位目前是同一渲染管线下的程序化产品资产，后续可以替换成最终美术资产，但不会另起一套场景。
- 桌面端 WebGPU 是主要体验目标，浏览器兼容性和移动端体验还需要继续打磨。
- 本地开发时后端不可用会进入显式 mock 演示路径；真实后端可用时，数据不与 mock 混用。

## 最新进度

已完成：

- [x] 锁定 Bruno `folio-2025` 实时 3D 场景为唯一视觉基准。
- [x] 恢复原有地形与水景数据链路，并完成 1440×900 / 1920×1080 默认镜头的临水构图验收。
- [x] 复用原有材质、光照、雾、风、植被和后处理。
- [x] 移除车辆、Player、物理、碰撞玩法、作品集导航和相关菜单。
- [x] 实现鼠标环绕、滚轮缩放，并把相机状态和后端桌状态隔离。
- [x] 在同一 3D 场景上完成桌发现、Lobby、入席、实时讨论和历史弹窗。
- [x] 接通桌状态、成员、授权、主持动作、安全事件、收桌卡和 `/replay`。
- [x] 接入三轮主动需求澄清、无候选回首页草稿、首页上下文接收和真实行动回响。
- [x] 关系保存只在收桌后按真实成员和 `table_id` 触发，不在前端伪造关系结果。
- [x] 清理旧的 R3F / 低模桌海、定稿背景图和本地大模型；当前发布树只保留 Bruno Runtime 资源。
- [x] 前端 `check`、生产构建和后端测试通过。

最近一次验证结果：

```text
corepack pnpm check          passed
corepack pnpm build          passed
corepack pnpm verify:frontend passed
corepack pnpm verify:p0-p2   passed
backend pytest               507 passed
```

## 下一步方向

接下来沿着产品计划继续，把“坐下来和刚好在场的人聊一会儿”做完整，而不是再做一个游戏或作品集网站。

当前阶段按 [`specs/NEXT-STAGE-WATER-AND-RUNTIME-CLOSURE.md`](specs/NEXT-STAGE-WATER-AND-RUNTIME-CLOSURE.md) 已恢复 Bruno 水景并收紧数据一致性；双客户端传输和断线恢复已有可重复验收，正式身份、队友首页汇合和最终桌椅美术签收仍未完成。下一步沿产品计划进入以下扩展：

1. **完成首页汇合**：接入推荐桌、手动建桌、邀请和 `OpenTableContext`，不让匹配页重新承担首页职责。
2. **补真实候选 source**：有授权 source 后，完成 `MatchPlan` 预览、明确确认和公开来源验收。
3. **继续做跨桌延续**：再次遇见、再次邀桌和“问题长出下一桌”由首页承载总览，桌内只保留当前桌真实结果。
4. **守住 Bruno 的场景质量**：不再引入定稿图、低模世界或第二个 3D 渲染器。需要改视觉时，只在 `src/bruno-runtime/` 和对应资源边界内改。
5. **最后做生产化**：真实身份、持久化部署、WebSocket 故障演练、日志和 WebGPU 降级策略，优先于新增花哨玩法。

当前生产化的第一优先级已经切到知乎 OAuth 与真实数据。公开搜索适配器、服务端 source 边界、OAuth coordinator 和 Pages 回调中继已经就位；拿到 `Access Secret` 可先联调公开信号，拿到 `app_id` / `app_key` 后即可联调授权会话。当前还缺知乎稳定用户 ID/用户信息契约、个人 OAuth source 和前端身份 hydration。具体阻塞项和验收标准见 [`specs/ZHIHU-OAUTH-REAL-DATA.md`](specs/ZHIHU-OAUTH-REAL-DATA.md)。

## 代码边界

```text
src/
├── bruno-runtime/                 # Bruno Runtime 的适配版：唯一 3D 渲染和环境系统
│   ├── SceneBridge.js             # 后端投影到 3D 的唯一桥接
│   └── Game/
├── TableWorld.tsx                 # React 生命周期壳，负责挂载和销毁 Runtime
├── TableSea.tsx                   # DOM 桌发现，不再创建第二个 3D 场景
├── Lobby.tsx                      # 桌边预览和入席前信息
├── live/
│   ├── api.ts                     # REST 适配层
│   ├── backend.ts                 # WebSocket、连接和事件适配层
│   ├── identity.ts                # 当前开发身份；未来替换为登录身份适配器
│   ├── store.ts                   # 前端实时投影
│   ├── DiscussionPanel.tsx        # `/replay` 历史弹窗
│   └── mock.ts                    # 后端不可用时的显式兜底
└── App.tsx                        # 产品流程和 DOM 交互层

public/assets/bruno-runtime/       # Bruno 场景运行所需的公开资源
backend/                           # FastAPI 后端和测试
specs/                             # 当前 Bruno 融合规格和实施状态
docs/                              # 产品上位文档
```

代码中的 `@origin`、`PRODUCT DOM`、`PRODUCT 3D`、`PRODUCT DATA BOUNDARY` 注释用于区分上游复用、组一桌新增代码和后端适配边界。

当前版本不包含旧的 `sea`、`ValleyScene`、`Diorama`、`table-engine` 和对应的低模/定稿图片资源。早期探索仍可能出现在 Git 历史中，但不参与当前构建。

## 本地运行

需要 Node.js、Corepack 和 Python 3.11 以上版本。

### 1. 安装前端依赖

```powershell
corepack pnpm install
```

### 2. 启动后端

新开一个终端：

```powershell
cd backend
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload --port 8000
```

### 3. 启动前端

在项目根目录运行：

```powershell
corepack pnpm dev
```

打开 Vite 输出的地址，默认是 `http://127.0.0.1:5174/`。前端开发服务器会把 `/tables`、`/ws` 等请求代理到 `127.0.0.1:8000`。

如果后端没有启动，前端会进入 mock 演示模式；要验证真实桌状态、实时讨论和回放，需要同时启动后端。

本地如果要让旧的静态桌卡首次在空后端里创建演示桌，需要复制 `.env.example` 为 `.env.local`，并将 `VITE_ALLOW_DEV_SEED` 改为 `true`。这个开关只允许开发环境使用，业务错误不会因此被替换成 mock。

生产部署时可在 `.env.local` 或部署环境里设置 `VITE_API_BASE_URL` 和 `VITE_WS_BASE_URL`；留空则使用 Vite 开发代理或同源路径。

## 常用检查

```powershell
corepack pnpm check
corepack pnpm build
corepack pnpm verify:frontend
corepack pnpm verify:p0-p2   # 需要同时启动前后端

cd backend
pytest
```

## 第三方说明

Bruno Runtime 的来源、许可证和保留的版权信息见 [`src/bruno-runtime/THIRD_PARTY_NOTICES.md`](src/bruno-runtime/THIRD_PARTY_NOTICES.md)。相关上游代码说明见 [`src/bruno-runtime/ORIGIN.md`](src/bruno-runtime/ORIGIN.md)。

当前实施合同和具体边界见 [`specs/bruno-runtime-product-integration-v2.md`](specs/bruno-runtime-product-integration-v2.md)，执行状态见 [`specs/IMPLEMENTATION-STATUS.md`](specs/IMPLEMENTATION-STATUS.md)。

产品总方向见 [`docs/组一桌_知乎赛道一_完整产品沉淀文档_v1.3_最终排版.docx`](docs/组一桌_知乎赛道一_完整产品沉淀文档_v1.3_最终排版.docx)。
