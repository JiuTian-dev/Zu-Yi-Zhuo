# 组一桌：发现世界大厅与深夜篝火纵切

> Status: confirmed for implementation
> Last updated: 2026-08-26

<!-- CACHE ANCHOR: stable product decisions and contracts. Change rarely. -->

## 1. Objective

Build a desktop-first, responsive web prototype whose first impression is a living social world rather than an AI tool. The demo must prove one complete vertical slice:

`发现世界大厅 → 靠近篝火世界 → 选择“离开大城市”桌 → 穿越转场 → 坐到篝火旁`

The lobby should make users want to enter. The table scene should make them want to stay.

## 2. Product architecture

### Level 1: Discover Worlds lobby

- A spatial gallery containing three distant luminous worlds: 深夜篝火、瑞士山谷、午后 Workshop.
- Worlds are not rectangular cards. Each is a self-contained environmental aperture with depth, light, and ambient motion.
- A world reveals several forming tables only when approached/focused.
- Lobby responsibilities: discovery, curiosity, choice.
- Lobby must not expose a complete discussion UI or a fully expanded campfire scene.

### Level 2: A specific table

- The selected world expands into the complete interaction environment.
- The campfire room includes five seats, four human roles, one meaningful empty seat, Agent-as-fire, table state, discussion cues, and peripheral listeners.
- Table responsibilities: presence, conversation, belonging, entry.

### Core boundary

- Do not build one giant campfire hall containing many identical tables.
- Do not make the homepage itself a specific table.
- The same world may contain multiple topics, but each selected table becomes a unique encounter.

## 3. Demo content contract

### Flagship table

- Topic: 关于离开大城市这件事，他们已经聊了三天。
- State: 4 人已入席.
- Missing role: 这一桌，还缺一个真正离开过的人。
- Primary action: 坐下来看看.

### Campfire-world neighboring tables

- 留在大城市，真的值得吗？
- 三十岁以后，重新开始意味着什么？

### Other-world glimpse content

- Swiss valley: 第一次一个人旅行 / 为什么我们越来越不会休息 / 值得专程去吃的地方.
- Workshop: AI 时代还要学编程吗 / 一个想法怎样变成产品 / 怎样重新找回创造欲.

## 4. Visual system

### Subject and audience

- Subject: high-value encounters emerging from Zhihu's accumulated human experience.
- Audience: hackathon judges and first-time users, including people uninterested in AI technology.
- Single first-screen job: create an immediate desire to approach one glowing world.

### Palette

- Midnight Ink: `#07101C`
- Lake Fog: `#18283A`
- Coal: `#100C09`
- Ember: `#FF9B42`
- Fire Gold: `#FFD28A`
- Moon Paper: `#E9EEF2`

### Typography

- Emotional/display role: a restrained Chinese serif stack (`Noto Serif SC`, `Source Han Serif SC`, `Songti SC`).
- Interface/body role: a modern Chinese sans stack (`Inter`, `Noto Sans SC`, `Microsoft YaHei`).
- Utility labels use modest tracking and no techno-style all-caps decoration.

### Signature element

The fire is the Agent. It breathes, rises before speaking, and changes the nearby light. No robot avatar or AI badge is allowed.

### Composition risk

The lobby is staged as darkness with three spatial light sources rather than a conventional hero layout. Copy remains quiet and subordinate to the scene.

## 5. Motion contract

### Lobby entrance

1. Near-black opening with distant lights.
2. Camera drifts forward through soft atmospheric depth.
3. Brand line appears: “有些答案，不在任何一个人那里。”
4. Three worlds become legible through light, silhouette, and restrained labels.

### World focus

- Pointer movement produces small parallax only.
- Focusing a world shifts camera, color temperature, sound bed, and table labels together.
- Scroll, drag, arrow keys, and direct click can change the focused world.
- Reduced-motion mode replaces travel with short crossfades.

### Table entry

- Selected world aperture expands.
- Lobby UI recedes and blurs.
- Camera crosses a light/fog threshold.
- Campfire room resolves from silhouette to warm detail.
- Empty chair becomes the visual invitation.

### Agent intervention

- Flame height and local light increase subtly.
- Only then does the host line appear.
- No chat bubble labeled “AI 主持人”.

## 6. Interaction and accessibility contract

- Keyboard can focus worlds, select a table, enter, and return.
- Focus rings are visible but visually integrated.
- `prefers-reduced-motion` disables camera sweeps, strong parallax, and long staged delays.
- Audio is muted by default and requires an explicit toggle.
- Mobile keeps the hierarchy but reduces post-processing and pointer-dependent effects.
- If WebGL is unavailable, a composed visual fallback preserves navigation and copy.

## 7. Technical architecture

- Vite + React + TypeScript.
- React Three Fiber + Drei for scene graph and camera.
- GSAP for orchestrated DOM/scene transitions.
- CSS modules or scoped plain CSS for typography and interface layers.
- Route/state contract:
  - `/` — Discover Worlds lobby.
  - `/world/campfire` — campfire world with forming tables.
  - `/table/leaving-the-city` — complete campfire table scene.
- Initial scene data is local and typed; no backend or AI API in this phase.
- Generated raster art may provide depth layers, but interactive light, fire, particles, focus, and navigation remain code-driven.

## 8. Component/data contracts

```ts
type WorldId = 'campfire' | 'valley' | 'workshop'

interface WorldSummary {
  id: WorldId
  name: string
  atmosphere: string
  accent: string
  tables: TableSummary[]
}

interface TableSummary {
  id: string
  worldId: WorldId
  hook: string
  seatedCount: number
  missingPerspective: string
}
```

Primary UI state is `focusedWorld`, `selectedTable`, `transitionPhase`, and `motionPreference`. Scene components consume state but do not own routing decisions.

## 9. Non-goals

- Backend, authentication, real Zhihu integration, matchmaking, or live discussion.
- Full free-roam game controls.
- Complex digital-human animation.
- Three fully developed table interiors.
- Dashboard, card grid, ChatGPT-style transcript, points, levels, or AI iconography.

## 10. Acceptance criteria

- A first-time user can identify three distinct worlds without seeing a card grid.
- Focusing campfire reveals multiple forming tables and the flagship missing-person hook.
- Entering the flagship table uses a continuous spatial transition rather than a hard page cut.
- The table contains four occupied seats and one semantically meaningful empty seat.
- The fire visibly acts as host at least once.
- The experience is usable at 1440x900, 1920x1080, and 390x844.
- No critical console errors; production build succeeds.
- Keyboard and reduced-motion paths are verified.

<!-- END CACHE ANCHOR -->

## 11. Stacked diff topology

```text
main
  └── D1 project shell + typed scene/routing contracts
        └── D2 discover-worlds lobby
              └── D3 campfire world + flagship table transition
                    └── D4 motion/accessibility/performance polish
```

Each diff targets at most 300 changed lines where practical and must be independently buildable and reviewable.

## 12. Progress Ledger

| Step | Status | Output | Verification |
|---|---|---|---|
| Design confirmation | complete | Two-level architecture and hybrid 2.5D direction confirmed in chat | Product/user confirmation |
| D1 shell/contracts | pending | — | `pnpm build` |
| D2 lobby | pending | — | build + screenshot QA |
| D3 campfire slice | pending | — | build + interaction QA |
| D4 polish | pending | — | build + responsive/accessibility QA |
| Integration review | pending | — | interface-only review across diffs |

## 13. Decision log

- 2026-08-26: The lobby and concrete table are separate spatial levels.
- 2026-08-26: The implementation uses a hybrid 2.5D/WebGL approach instead of full free-roam 3D.
- 2026-08-26: Only the campfire vertical slice receives full interior treatment in V1.
