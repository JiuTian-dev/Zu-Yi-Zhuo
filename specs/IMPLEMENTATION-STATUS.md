# Bruno runtime product integration — implementation status

This is the execution record for
[`bruno-runtime-product-integration-v2.md`](./bruno-runtime-product-integration-v2.md).
It is intentionally short so the next contributor can continue from
`repo + spec + git`.

## Goal

Use Bruno Simon's original `folio-2025` WebGPU/Three.js runtime as the visual
baseline, remove its vehicle/player/game/portfolio product layer, and mount
组一桌's backend-driven table product above the same persistent canvas.

## Invariants now enforced in code

- `src/bruno-runtime/Game/*` is the only 3D renderer and reuses the original
  terrain, water, foliage, lighting, weather and post-processing pipeline.
- `src/TableSea.tsx`, `src/Lobby.tsx` and `src/App.tsx` are DOM product layers;
  there is no second R3F scene or screenshot background.
- `src/bruno-runtime/Game/CameraOrbit.js` owns pointer orbit and wheel zoom;
  it never calls REST or WebSocket APIs.
- `src/live/api.ts` is the REST boundary and `src/live/backend.ts` is the WS
  boundary. Table state, members, consent, host actions, safety events, close
  artifacts and replay are applied from backend responses.
- `src/live/DiscussionPanel.tsx` renders messages only from `/replay`; it does
  not silently substitute the live stream when replay is unavailable.
- `src/live/mock.ts` is isolated behind the explicit backend-unavailable path.
- Source boundaries are marked with `@origin`, `PRODUCT DOM`, `PRODUCT 3D`,
  `PRODUCT DATA BOUNDARY` and `THIRD_PARTY_NOTICES.md`.

> 2026-09-03 审计结论：下面的勾选项记录的是主流程实现里程碑，
> 不等于严格 DoD 已完成。当前仍有地形数据纹理缺失、水景构图、状态版本、
> 重连、真实身份和 3D 状态映射等缺口。下一阶段执行合同见
> [`NEXT-STAGE-WATER-AND-RUNTIME-CLOSURE.md`](./NEXT-STAGE-WATER-AND-RUNTIME-CLOSURE.md)。

## 已完成的实现里程碑（非严格 DoD）

- [x] M0 Bruno baseline commit and source boundary locked; deterministic visual
      captures remain part of the next-stage acceptance.
- [x] M1 selected Bruno runtime and original visual assets imported.
- [x] M2 single persistent canvas with lifecycle cleanup.
- [x] M3 mouse orbit + wheel zoom, no car/player movement.
- [x] M4 table discovery and lobby are DOM overlays on the same runtime.
- [x] M5 REST/WS happy path for table state, join, consent, live messages,
      host/safety events and closing cards is wired; recovery semantics remain.
- [x] M6 replay modal overlays the current 3D scene and reads `/replay`.
- [x] M7 old low-poly/R3F scene sources and visible portfolio/game layer removed.
- [x] M8 frontend, backend and one-browser smoke verification completed for the
      current local environment; two-client and visual-matrix acceptance remain.

## Verification evidence

- `corepack pnpm check` — passed.
- `corepack pnpm build` — passed; only the expected large WebGPU runtime chunk
  warning remains.
- `git diff --check` — passed.
- Backend `pytest` — **496 passed** (21.73s; Python dependency deprecation
  warnings only).
- Browser smoke on `http://127.0.0.1:5174/` with local backend on `:8000`:
  original Bruno environment rendered; table entry → lobby → same 3D room;
  backend seat count and live connection shown; drag orbit and wheel zoom
  changed only the camera; refresh restored the active room; history opened as
  a darkened/blurred overlay and displayed the backend replay.

## Known local-state note

Browser smoke used the development `viewer` identity. The existing local
`learning-to-rest` table therefore contains the validation participant and a
few validation messages; it was not reset or deleted to avoid destroying
backend state outside the frontend code change.

## 当前缺口

- `Terrain.js` 依赖的 `terrainTexture` 没有被加载，仓库也尚未包含原始
  `terrain.png/ktx`；这会破坏水深、岸线、地表颜色和草地遮罩。
- 当前默认桌锚点和镜头尚未完成临水构图验收，水景没有达到 Bruno 基准。
- 产品桌椅仍是程序化占位资产，尚未达到严格视觉 DoD。
- 状态版本单调性、WS 重连、消息 pending/重试和错误到 mock 的边界仍需收紧。
- 五个席位、当前发言者和六种主持动作尚未完整映射到 3D。
- 仍缺双真实客户端、隐私投影、断线恢复和视觉矩阵的完整验收证据。
