# Bruno scene runtime boundary

This directory is the production WebGPU/Three.js scene island adapted from the
clean `folio-2025` baseline at commit `41046b5` in `D:\folio-2025`.

## Reused from the original runtime

`Rendering`, `Materials`, `Terrain`, `Water`, `Fog`, `Wind`, `Weather`, the day
and year cycles, grass, foliage, trees, flowers, fences, benches, lanterns,
pole lights, scenery, bloom, cheap DOF and the original data-driven terrain
assets are intentionally preserved. They are the visual baseline: changing
them is a visual-regression decision, not a product-UI refactor.

## Product additions

- `Game.js` composes the visual systems without the portfolio/game loop.
- `SceneBridge.js` is the only product-state-to-scene adapter; it receives
  backend projections and forwards only visual state to the table object.
- `CameraOrbit.js` owns mouse drag orbit and wheel zoom only.
- `World/TableMeeting.js` adds the product table furniture inside the same
  renderer; it does not own participant data, selection, or conversation.
- `TableWorld.tsx`, `TableSea.tsx`, `Lobby.tsx`, `App.tsx` and `live/*` own the
  product shell, REST/WS state and DOM interaction layer.

## Explicitly removed

The vehicle, driving, player movement, Rapier physics, tracks, explosions,
combat/toys, portfolio title/menu/overlay, interactive portfolio points,
network game server and game-specific audio are not part of this runtime.
The canvas never writes table state; only REST and the participant WebSocket
may do that.

## Runtime contract

There is one persistent `.bruno-runtime-canvas`. React may show or hide DOM
layers above it, but must not create a second renderer or replace it with a
background image. The visible document title and UI brand belong to 组一桌.
