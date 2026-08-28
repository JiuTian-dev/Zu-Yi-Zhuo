# 组一桌：Table First 沉浸式桌面体验

> Status: confirmed for implementation
> Last updated: 2026-08-26

<!-- CACHE ANCHOR: stable product decisions and contracts. Change rarely. -->

## 1. Objective

Build a desktop-first, responsive web prototype whose first impression is a specific conversation already happening inside a living world rather than an AI tool. The demo must prove one continuous vertical slice:

`打开具体桌的发现远景 → 靠近这桌 → 同场景镜头推进 → 坐到空席位置 → 进入讨论`

The discovery state should make users want to approach. The seated state should make them want to stay.

## 2. Product architecture

### State 1: Discover a specific table

- The homepage opens directly on one concrete table already in progress.
- The scene is that table's world skin, not a world-selection entrance.
- Scroll, wheel, drag or arrows switch to the next table; the environment changes with the table.
- Discovery responsibilities: topic, participants, missing perspective, recommendation and desire to approach.

### State 2: Seated at the same table

- The camera advances through the same scene without navigation or a page cut.
- The final camera position belongs to the meaningful empty seat.
- The table contains four human roles, one user seat, one Agent seat, live discussion cues and evolving question structure.
- Seated responsibilities: presence, conversation, facilitation, contribution and closure.

### Core boundary

- Do not add a lobby, world picker, server hall or intermediate table list.
- Switch tables, not worlds; the world follows the selected table.
- Discovery and seated views are camera states of one scene, not routes or pages.

## 3. Demo content contract

### Swiss prototype table

- Topic: 为什么我们越来越不会休息？
- State: 4 人已入席.
- Missing role: 这一桌，还缺一个真正停下来过的人。
- Primary action: 靠近这桌.

### Next discovery tables

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

The Agent is a restrained sixth-seat Table Host: a small ivory/warm-gray body with minimal eyes, no prominent mouth, a warm chest core and an incomplete circular halo. It sits opposite the viewer seat and uses posture, gaze, hand motion and light rather than mascot-like expression.

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
- Focusing a table shifts camera, color temperature, sound bed, and table labels together.
- Scroll, drag, arrow keys, and direct click can change the focused table.
- Reduced-motion mode replaces travel with short crossfades.

### Table entry

- Discovery UI recedes and blurs.
- Camera crosses a light/fog threshold.
- The depth-authored art surface resolves into a table-focused near-field composition.
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
- Single-page state contract: `discovering → approaching → seated`; later `switchingTable` moves directly between concrete tables.
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

Primary UI state is `selectedTable`, `experiencePhase`, `activeSpeaker`, and `motionPreference`. Scene components consume state but do not own table-switching decisions.

## 9. Non-goals

- Backend, authentication, real Zhihu integration, matchmaking, or live discussion.
- Full free-roam game controls.
- Complex digital-human animation.
- Three fully developed table interiors.
- Dashboard, card grid, ChatGPT-style transcript, points, levels, or AI iconography.

## 10. Acceptance criteria

- A first-time user immediately understands one concrete table is already happening.
- Switching changes the concrete table and its world together without exposing a world picker.
- Entering the table uses a continuous spatial transition rather than a hard page cut.
- The table contains four occupied seats and one semantically meaningful empty seat.
- A scene-native light visibly acts as host at least once.
- The experience is usable at 1440x900, 1920x1080, and 390x844.
- No critical console errors; production build succeeds.
- Keyboard and reduced-motion paths are verified.

<!-- END CACHE ANCHOR -->

## 10.1 Current visual implementation slice — Swiss valley

The first implemented visual proof is the confirmed Swiss-valley table hero rather than the complete lobby. It establishes the reusable rendering language before the other worlds are expanded.

- Art direction: Cozy Stylized Low-poly Diorama / 治愈系低模立体世界.
- Character direction: Stylized Miniature Adults / 轻卡通微缩成人, 4–4.5 heads tall, rounded forms, modern clothing, four occupied seats and one meaningful empty seat.
- Hero topic: 为什么我们越来越不会休息？
- Missing perspective: 还缺一个真正停下来过的人.
- Composition: alpine lake and mountain depth at left/center, table gathering at lower-right, coral tree framing the upper-right, explorer vehicle entering from lower-left.
- Rendering approach: a high-fidelity art plate is treated as a depth-aware WebGL world layer; Three.js owns pointer parallax, breathing camera, water glints, drifting petals, cloud haze, light motes and focus lighting. DOM owns exact typography and accessible controls.
- Interaction: pointer parallax, table focus, empty-seat reveal, scene sound toggle placeholder, and reduced-motion fallback.
- The image must remain useful if WebGL is unavailable; the DOM and art plate are the fallback.

## 10.2 Confirmed Plan B2 — depth-authored continuous scene

- The confirmed Swiss art plate remains the visual source of truth in both discovery and seated states; it must never become a blurred backdrop behind visibly cheaper geometry.
- A generated monocular depth map displaces a high-density WebGL surface so mountains, house, people, table and foreground foliage respond at different depths.
- Entry is one constrained camera move aimed at the empty seat: discovery UI recedes, depth parallax becomes more legible, the original miniature adults and table become dominant, and no hard scene cut occurs.
- The seated camera is close enough to read gestures and tabletop objects but remains constrained; no free-roam controls.
- Discussion UI is spatially anchored with restrained DOM overlays: active-speaker light, a material-like question card, a fifth-seat marker and a single bottom subtitle layer.
- Agent is a scene-native sixth-seat host rather than a floating deity, robot badge or tabletop ornament.
- No procedural placeholder people, green terrain disc, giant floating question ellipse or oversized glass panel is allowed.
- Reduced motion uses a short dissolve between the two camera compositions.

## 10.3 Confirmed Plan B3 — layered 2.5D actors and Table Host

- The complete Swiss art plate remains the discovery source of truth and the seated underlay, preventing generated asset drift from degrading the approved composition.
- Four visible people, the viewer seat and the Table Host each own an independent WebGL actor layer with a stable `seatId`; human actors additionally own a stable `userId`.
- Human layers use transparent pixel mattes derived from the approved plate. At rest they align exactly with the underlay; hover and speaker states affect only the selected actor layer.
- The Table Host is a separately rendered transparent actor placed at the north/rear sixth seat, between the orange and blue participants and directly opposite the empty viewer chair. Its lower body is hidden by the table edge.
- The Host halo, chest core, local light and moving question point are real-time Three.js elements. Body pose assets provide the first `SILENCE` and `PASS` actions.
- Entry may use a short petal/sun-glare occlusion while actor layers resolve, but cannot introduce a visible scene cut or replace the approved world with cheaper geometry.
- Initial action scope is `SILENCE` and `PASS`; `PROBE`, `REFRAME`, `GROUND` and `CLOSE` share the same state contract and are subsequent pose/sequence assets.

```ts
type AgentAction = 'SILENCE' | 'PASS' | 'PROBE' | 'REFRAME' | 'GROUND' | 'CLOSE'

interface SeatActor {
  seatId: string
  actorType: 'human' | 'viewer' | 'agent'
  userId?: string
  displayName: string
  role: string
  worldAnchor: [number, number, number]
  visualState: 'idle' | 'listening' | 'speaking'
}
```

## 11. Stacked diff topology

```text
main
  └── D1 project shell + typed scene/routing contracts
        └── D2 Swiss discovery art plate
              └── D3 Swiss depth-authored entry + seated state
                    └── D4 actor identity + layered human mattes
                          └── D5 Table Host SILENCE/PASS + spatial light
                                └── D6 table switching + motion/accessibility/performance polish
```

Each diff targets at most 300 changed lines where practical and must be independently buildable and reviewable.

## 12. Progress Ledger

| Step | Status | Output | Verification |
|---|---|---|---|
| Design confirmation | complete | Table First architecture and depth-authored 2.5D direction confirmed in chat | Product/user confirmation |
| D1 shell/contracts | complete | React/Vite shell, typed worlds and local routing | `pnpm build` |
| D2 Swiss valley visual slice | complete | Depth-aware WebGL hero, semantic empty-seat interaction, table panel and responsive layout | `pnpm build`; Playwright at 1440×900 and 390×844; zero console errors |
| D3 Swiss depth-authored entry | complete | Depth-displaced art surface, continuous table-focused camera entry and restrained spatial discussion UI | `pnpm build`; Playwright at 1440×900 and 390×844; zero console errors |
| D4 actor identity + layers | complete | Stable user/seat contracts, independent human hover/speaker layers and viewer seat | `pnpm build`; Playwright actor interaction QA at 1440×900; zero console errors |
| D5 Table Host | in progress | Sixth-seat Host with `SILENCE` and `PASS`, real-time halo/core/question point | build + action-state QA |
| D6 polish | pending | — | build + responsive/accessibility QA |
| Integration review | pending | — | interface-only review across diffs |

## 13. Decision log

- 2026-08-26: The lobby and concrete table are separate spatial levels.
- 2026-08-26: The implementation uses a hybrid 2.5D/WebGL approach instead of full free-roam 3D.
- 2026-08-26: Only one table vertical slice receives full interior treatment before the other scene skins are expanded.
- 2026-08-27: The Swiss-valley art plate is the first implemented visual proof; exact copy and controls remain accessible DOM while Three.js supplies depth, light and ambient motion.
- 2026-08-27: Product architecture corrected to Table First: no lobby or world-selection layer; users switch concrete tables and each table carries its scene skin.
- 2026-08-27: Plan B2 replaces the rejected procedural near field: one depth-authored art surface preserves the final image through discovery and seated camera states, with restrained spatial UI layered above it.
- 2026-08-28: Plan B3 confirmed: preserve the approved plate, add independent identity-bearing human matte layers, and place a separately rendered Table Host in the rear sixth seat with real-time light language.
