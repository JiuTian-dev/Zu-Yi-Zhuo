# Runtime source map

`src/bruno-runtime/` is the actual scene island today. This file is kept at
the path named by the product spec so the boundary is easy to find while the
repository is still using the Bruno directory layout.

## Reused Bruno baseline

The environment and rendering files under `src/bruno-runtime/Game/` come from
`folio-2025@41046b5`: WebGPU/WebGL fallback, terrain and water shader path,
lighting, fog, weather, wind, foliage, scenery, bloom and cheap DOF. They are
the visual reference and should only change as part of a visual regression
review.

## Adapted runtime

| File | Boundary | What changed |
| --- | --- | --- |
| `Game/Game.js` | `BRUNO-ADAPTED` | Keeps the environment systems and removes the vehicle/game loop. |
| `Game/View.js` | `BRUNO-ADAPTED` | Starts at a stable product table anchor. |
| `Game/CameraOrbit.js` | `BRUNO-ADAPTED` | Mouse drag and wheel camera input only; no product writes. |
| `Game/World/World.js` | `BRUNO-ADAPTED` | Mounts only natural environment and product table furniture. |
| `SceneBridge.js` | `BACKEND-ADAPTER` | Projects backend state into visual-only scene state. |
| `runtimeController.ts` | `ZUOYIZHUO-UI` | Connects React lifecycle to the one runtime and camera intent. |

## Project-owned scene

`Game/tableAnchors.js` owns stable world coordinates. `Game/World/TableMeeting.js`
owns the product table, seats, cove and restrained speaker/action indicators.
It receives already-projected state and never calls REST or WebSocket APIs.

## Product shell and backend boundary

`TableWorld.tsx` owns create/destroy and the single Canvas. `App.tsx`,
`Lobby.tsx`, `TableSea.tsx` and `live/*` own DOM product interaction. REST
transport lives in `live/api.ts`; WebSocket, identity, reconnect and event
dedupe live in `live/backend.ts`; `/replay` is rendered by
`live/DiscussionPanel.tsx`.

## Third-party and removed capabilities

The upstream license and attribution stay in `THIRD_PARTY_NOTICES.md`. The
removed vehicle, respawn, player, physics, portfolio and game-interaction
files are listed in `REMOVAL-MANIFEST.md`; they are not loaded by the product
runtime.
