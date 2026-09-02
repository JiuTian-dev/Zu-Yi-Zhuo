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

## Progress

- [x] M0 visual baseline frozen and documented.
- [x] M1 selected Bruno runtime and original visual assets imported.
- [x] M2 single persistent canvas with lifecycle cleanup.
- [x] M3 mouse orbit + wheel zoom, no car/player movement.
- [x] M4 table discovery and lobby are DOM overlays on the same runtime.
- [x] M5 REST/WS table state, join, consent, live messages, host/safety
      events and closing cards are wired.
- [x] M6 replay modal overlays the current 3D scene and reads `/replay`.
- [x] M7 old low-poly/R3F scene sources and visible portfolio/game layer removed.
- [x] M8 frontend, backend and browser smoke verification completed for the
      current local environment.

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

## Remaining risk

The product table furniture is intentionally small and procedural because no
new external model was authorized. If a final art asset is supplied later,
replace only `src/bruno-runtime/Game/World/TableMeeting.js`; do not replace the
Bruno runtime or introduce a second renderer.
