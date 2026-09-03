# 组一桌

组一桌是一款围绕“把值得聊的话，交给刚好在场的人”的多人讨论产品。
用户从正在发生的桌里选一个问题，先在桌边看看成员和缺席的视角，再进入同一片湖边 3D 场景，入席、发言，最后留下可以回看的讨论记录和收桌卡。

当前仓库是一个可以本地运行的前后端产品原型。前端主场景使用 Bruno Simon `folio-2025` 的实时 WebGPU / Three.js Runtime；产品交互和讨论状态由组一桌自己的 React、REST 和 WebSocket 层负责。

## 项目现状

截至 2026-09-03，主流程已经打通：

```text
入口选桌
  → 桌边预览
  → 进入同一套实时 3D 场景
  → 入席与资料授权
  → WebSocket 实时讨论
  → 当前场景上的历史弹窗
  → 收桌卡与回放
```

### 前端

- React + Vite，3D 底座是 Three.js WebGPU。
- 入口、Lobby、入席、讨论、历史和收桌卡都是 DOM 产品层，叠在同一个持续存在的 3D Runtime 上。
- 3D 场景保留原运行时的地形、湖水、植被、灯光、雾、风场、Bloom、景深和环境变化。
- 小车、驾驶、角色移动、游戏玩法、作品集菜单和可见的 Bruno 产品界面已经从生产路径移除。
- 桌内只允许鼠标拖拽改变镜头环绕角度，滚轮改变距离；这些操作不会写入后端，也不会影响桌状态。

### 后端

- FastAPI 提供桌发现、Lobby、桌状态、加入、资料授权、收桌和回放接口。
- WebSocket 负责真人发言、主持动作、状态更新、安全提示和收桌事件。
- 桌状态和回放以服务端为准，前端不会用本地假数据覆盖真实会话。
- 后端默认可以使用内存仓储；设置 `TABLE_REPOSITORY_PATH` 后可写入 JSON 快照。
- 后端还包含匹配预览、主动需求澄清、邀请、旁听、递话、收藏和安全相关接口；这些能力会按产品主流程逐步补齐更完整的前端入口。

### 当前不是最终生产版的部分

- 当前使用本地 `viewer` 身份，生产环境还需要接入真实登录和身份解析。
- Bruno 场景里的桌椅和席位目前是同一渲染管线下的程序化产品资产，后续可以替换成最终美术资产，但不会另起一套场景。
- 桌面端 WebGPU 是主要体验目标，浏览器兼容性和移动端体验还需要继续打磨。
- 本地开发时后端不可用会进入显式 mock 演示路径；真实后端可用时，数据不与 mock 混用。

## 最新进度

已完成：

- [x] 锁定 Bruno `folio-2025` 实时 3D 场景为唯一视觉基准。
- [x] 复用原有地形、湖水、材质、光照、雾、风、植被和后处理。
- [x] 移除车辆、Player、物理、碰撞玩法、作品集导航和相关菜单。
- [x] 实现鼠标环绕、滚轮缩放，并把相机状态和后端桌状态隔离。
- [x] 在同一 3D 场景上完成桌发现、Lobby、入席、实时讨论和历史弹窗。
- [x] 接通桌状态、成员、授权、主持动作、安全事件、收桌卡和 `/replay`。
- [x] 清理旧的 R3F / 低模桌海、定稿背景图和本地大模型；当前发布树只保留 Bruno Runtime 资源。
- [x] 前端 `check`、生产构建和后端测试通过。

最近一次验证结果：

```text
corepack pnpm check   passed
corepack pnpm build   passed
backend pytest        496 passed
```

## 项目方向

接下来只沿着一条线继续：把“坐下来和刚好在场的人聊一会儿”做完整，而不是再做一个游戏或作品集网站。

1. **先守住 Bruno 的场景质量**：不再引入定稿图、低模世界或第二个 3D 渲染器。需要改视觉时，只在 `src/bruno-runtime/` 和对应的 Bruno 资源边界内改。
2. **把产品交互做清楚**：入口负责发现，Lobby 负责理解这桌，桌内负责参与；DOM 负责信息和操作，3D 负责空间感和氛围。
3. **继续补齐后端能力的前端入口**：匹配理由、主动需求、邀请、旁听、递话、收藏、收桌后的行动回响，都要接真实 API，并保留错误和权限状态。
4. **再做生产化**：真实身份、持久化部署、WebSocket 重连、日志和 WebGPU 降级策略，优先于新增花哨玩法。

## 代码边界

```text
src/
├── bruno-runtime/                 # Bruno Runtime 的适配版：唯一 3D 渲染和环境系统
│   └── Game/
├── TableWorld.tsx                 # React 生命周期壳，负责挂载和销毁 Runtime
├── TableSea.tsx                   # DOM 桌发现，不再创建第二个 3D 场景
├── Lobby.tsx                      # 桌边预览和入席前信息
├── live/
│   ├── api.ts                     # REST 适配层
│   ├── backend.ts                 # WebSocket、连接和事件适配层
│   ├── store.ts                   # 前端实时投影
│   ├── DiscussionPanel.tsx        # `/replay` 历史弹窗
│   └── mock.ts                    # 后端不可用时的显式兜底
└── App.tsx                        # 产品流程和 DOM 交互层

public/assets/bruno-runtime/       # Bruno 场景运行所需的公开资源
backend/                           # FastAPI 后端和测试
specs/                             # 当前 Bruno 融合规格和实施状态
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

打开 Vite 输出的地址，默认是 `http://localhost:5173/`。前端开发服务器会把 `/tables`、`/ws` 等请求代理到 `127.0.0.1:8000`。

如果后端没有启动，前端会进入 mock 演示模式；要验证真实桌状态、实时讨论和回放，需要同时启动后端。

## 常用检查

```powershell
corepack pnpm check
corepack pnpm build

cd backend
pytest
```

## 第三方说明

Bruno Runtime 的来源、许可证和保留的版权信息见 [`src/bruno-runtime/THIRD_PARTY_NOTICES.md`](src/bruno-runtime/THIRD_PARTY_NOTICES.md)。相关上游代码说明见 [`src/bruno-runtime/ORIGIN.md`](src/bruno-runtime/ORIGIN.md)。

当前实施合同和具体边界见 [`specs/bruno-runtime-product-integration-v2.md`](specs/bruno-runtime-product-integration-v2.md)，执行状态见 [`specs/IMPLEMENTATION-STATUS.md`](specs/IMPLEMENTATION-STATUS.md)。
