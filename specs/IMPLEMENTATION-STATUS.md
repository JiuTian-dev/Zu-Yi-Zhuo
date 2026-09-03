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

> 2026-09-03 阶段更新：水景数据链路、临水默认构图、状态版本单调性、WS
> 重连、稳定消息 ID、统一 REST/WS 适配和 SceneBridge 已落地。严格 DoD
> 仍保留双客户端证据、正式身份和最终桌椅美术签收，不能把这些未完成项写成已完成。

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
- Backend `pytest` — **496 passed** (20.52s; Python dependency deprecation
  warnings only).
- Browser smoke on `http://127.0.0.1:5174/` with local backend on `:8000`:
  original Bruno environment rendered; table entry → lobby → same 3D room;
  backend seat count and live connection shown; a real viewer message was
  committed and then returned by `/replay`; history opened as a
  darkened/blurred overlay. Fresh page load finished with 0 console errors
  (only the Windows WebGPU `powerPreference` warning).
- Visual captures at `1440×900` and `1920×1080` show the restored water band,
  white shoreline detail, table and original lighting/post-processing together;
  captures are local QA artifacts under `output/playwright/` and are ignored by
  Git.

## Known local-state note

Browser smoke used the development `viewer` identity. The existing local
`learning-to-rest` table therefore contains the validation participant and a
few validation messages; it was not reset or deleted to avoid destroying
backend state outside the frontend code change.

## 当前缺口

- 产品桌椅仍是 Bruno 材质管线下的程序化产品资产，尚未达到最终美术签收；
  后续替换时仍应只改 `TableMeeting` 与它的资源边界。
- 目前使用开发态 `viewer` 身份，正式登录/身份解析器还没有接入前端。
- 还缺两台独立浏览器的并行加入、断线后恢复、低/中/高质量档和移动端的
  完整验收证据；这些是证据缺口，不代表后端接口未实现。
- 主动需求入口、关系/行动回响等产品计划后续能力尚未进入本阶段。
