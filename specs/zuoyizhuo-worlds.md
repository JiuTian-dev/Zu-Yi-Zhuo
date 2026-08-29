# 组一桌：Table First 沉浸式桌面体验

> Status: confirmed for gallery-to-world implementation
> Last updated: 2026-08-29

<!-- CACHE ANCHOR: stable product decisions and contracts. Change rarely. -->

## 1. Objective

Build a desktop-first, responsive web prototype whose first impression is an editorial gallery of concrete conversations already happening, rather than an AI tool or a world picker. The demo must prove one continuous vertical slice:

`看到正在发生的桌 → 卡片成为全屏世界 → 同场景镜头推进 → 坐到空席位置 → 进入讨论`

The discovery state should make users want to approach. The seated state should make them want to stay.

## 2. Product architecture

### State 0: Browse concrete tables

- The homepage is a Lusion-like editorial gallery of concrete `TableCard` units.
- Cards represent tables, never abstract worlds; the scene is only the table's cover and world skin.
- DOM owns titles, status, missing perspective, keyboard focus and document layout.
- One shared WebGL canvas owns all card images, pointer displacement, image depth and transitions.
- The first release has one complete Swiss table plus two data-backed forming-table previews.

### State 1: Discover the selected table

- Clicking the Swiss card expands that exact visual surface to the viewport without a route cut.
- Gallery chrome recedes while the selected title and image keep spatial continuity.
- The full-screen result is the existing valley discovery camera, not a separate detail page.
- Discovery responsibilities remain topic, participants, missing perspective and desire to approach.

### State 2: Seated at the same table

- The camera advances through the same scene without navigation or a page cut after the card-to-world handoff.
- The final camera position belongs to the meaningful empty seat.
- The table contains four human roles, one user seat, one Agent seat, live discussion cues and evolving question structure.
- Seated responsibilities: presence, conversation, facilitation, contribution and closure.

### Core boundary

- Do not add a lobby, world picker, server hall or explorable table map.
- The gallery is a product index of tables, not an intermediate world-selection layer.
- Select tables, not worlds; the world follows the selected table.
- Gallery, discovery and seated states share one application and one WebGL canvas, not routes or page cuts.

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
- Single first-screen job: make one concrete table feel like a living portal worth entering.

### Palette

- Canvas Paper: `#EEF0F5`
- Carbon: `#111315`
- Moss: `#315246`
- Cloud: `#747A82`
- Fire Gold: `#FFD28A`
- World Light: `#FFF9E9`

### Typography

- Gallery display and interface role: a modern Chinese sans stack (`Inter`, `Noto Sans SC`, `Microsoft YaHei`) with large, restrained regular-weight titles.
- Immersive-world emotional role: the existing Chinese serif stack (`Noto Serif SC`, `Source Han Serif SC`, `Songti SC`).
- Utility labels use modest tracking and no techno-style all-caps decoration.

### Gallery signature

The card image is the portal: its picture has weight, flow and depth, then becomes the full-screen world. The surrounding layout stays quiet—no glass card shells, large shadows, decorative gradients or badges.

### World signature

The Agent is a restrained sixth-seat Table Host: a small ivory/warm-gray body with minimal eyes, no prominent mouth, a warm chest core and an incomplete circular halo. It sits opposite the viewer seat and uses posture, gaze, hand motion and light rather than mascot-like expression.

### Composition risk

The outside product uses a deliberately editorial, light two-column grid while the inside world remains cinematic and immersive. The contrast communicates “browse tables outside; inhabit one conversation inside” without making either layer feel like a SaaS dashboard.

## 5. Motion contract

### Gallery entrance

1. Header and “正在发生的桌” appear on Canvas Paper.
2. The Swiss table card resolves first; secondary forming cards follow with a short stagger.
3. Image planes remain still until pointer or scroll energy is present.
4. Copy stays normal DOM and never receives the displacement effect.

### Gallery card response

- Pointer velocity writes a soft trail into one shared, low-resolution flow texture.
- Visible WebGL planes sample that flow in local UV space for restrained drag and recovery.
- Swiss foreground depth moves most, people/table less, mountains least.
- Scroll velocity may add a small vertical smear, capped below the pointer effect.
- Keyboard focus uses a stable outline and subtle static lift; it does not require pointer motion.

### Card-to-world entry

1. Capture the selected card and title bounds.
2. Fade and translate non-selected gallery DOM away.
3. Animate the selected WebGL plane from card bounds to viewport bounds; border radius reaches zero late in the move.
4. Crossfade to the full valley discovery composition while both use the same cover-fit crop.
5. Reveal world chrome; preserve the existing explicit “靠近这桌” action before the seated camera move.
6. Reduced-motion replaces steps 2–4 with a short opacity dissolve.

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

- Keyboard can focus tables, enter the selected table, approach the seat, and return to the gallery.
- Focus rings are visible but visually integrated.
- `prefers-reduced-motion` disables camera sweeps, strong parallax, and long staged delays.
- Audio is muted by default and requires an explicit toggle.
- Mobile keeps the hierarchy but reduces post-processing and pointer-dependent effects.
- If WebGL is unavailable, a composed visual fallback preserves navigation and copy.

## 7. Technical architecture

- Vite + React + TypeScript.
- Capable desktop mounts one application-level React Three Fiber renderer through `@14islands/r3f-scroll-rig` `GlobalCanvas`; capability detection happens before mount, so mobile, reduced-capability and WebGL-failure paths stay DOM-only and never create a context.
- The renderer owns two explicit scenes and cameras: gallery cards use `ScrollScene` with the rig-managed camera; `ValleyScene` renders through an R3F portal with its existing independent perspective camera and never creates a second Canvas.
- A shared RGBA8 ping-pong flow target runs at 128–256 px; no float-texture requirement.
- The rig's `SmoothScrollbar` supplies Lenis-backed desktop wheel smoothing and a shared scroll clock; touch remains native.
- GSAP coordinates DOM chrome and WebGL uniform transitions. The WebGL plane rect is authoritative for image continuity.
- CSS modules or scoped plain CSS for typography and interface layers.
- Application state is distinct from the existing scene state: `AppPhase = gallery | expanding | world | collapsing`, while `ExperiencePhase = discovering | approaching | seated` remains owned by the active world.
- Legal edges are `gallery → expanding → world/discovering → world/approaching → world/seated`; returning from any world phase uses `collapsing → gallery`.
- In gallery mode only the gallery pass runs. During expansion the gallery scene and world scene render into separate targets, then a transition pass composites them before DOM UI. In world mode the gallery tracker/pass pauses and only the valley pass runs. The capable-desktop `GlobalCanvas` mounts once, stays transparent, and disposes table textures only when their data leaves the registry.
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
  sceneTexture: string
  depthTexture?: string
  status: 'live' | 'forming'
  entryMode: 'immersive' | 'preview'
  transitionPreset: 'valley' | 'cover-only'
  coverFocus: { x: number; y: number }
}
```

Primary UI state is `selectedTable`, `appPhase`, `experiencePhase`, `activeActorId`, and `motionPreference`. Scene components consume state but do not own table-switching decisions. `forming/preview` cards may focus and animate but cannot enter the immersive world.

Every card and its destination world use the same CSS-cover contract: `coverScale = max(targetRect.width / sourceWidth, targetRect.height / sourceHeight)` with `coverFocus` applied before cropping. During expansion, crop math uses the interpolated target rect every frame; the gallery shader and valley discovery plate share the identical source aspect, focus point and UV-offset formula so expansion cannot jump.

## 9. Non-goals

- Backend, authentication, real Zhihu integration, matchmaking, or live discussion.
- Full free-roam game controls.
- Complex digital-human animation.
- Three fully developed table interiors.
- Dashboard, infinite social feed, ChatGPT-style transcript, points, levels, or AI iconography.
- Pixel-identical copying of Lusion's private shader or brand presentation.

## 10. Acceptance criteria

- A first-time user immediately understands the gallery items are concrete conversations already happening.
- The gallery can render one live table and two forming tables entirely from typed data.
- Enhanced desktop uses one WebGL context and keeps card media aligned with its DOM card while scrolling; mobile/reduced-capability paths may use semantic `<img>` fallbacks without creating a WebGL context.
- Pointer movement creates restrained local image displacement on desktop without distorting DOM text.
- Entering the Swiss table expands the selected card to the existing valley discovery state without a hard page cut or visible crop jump.
- The table contains four occupied seats and one semantically meaningful empty seat.
- A scene-native light visibly acts as host at least once.
- The experience is usable at 1440x900, 1920x1080, and 390x844.
- No critical console errors; production build succeeds.
- Keyboard and reduced-motion paths are verified.

<!-- END CACHE ANCHOR -->

## 10.1 Current visual implementation slice — Swiss valley

The first implemented visual proof is the confirmed Swiss-valley table hero rather than a multi-world map. It establishes the reusable rendering language before the other worlds are expanded.

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

## 10.4 Confirmed Plan B4 — seamless overscan and local layered depth

- The opaque WebGL clear color must never be visible. The approved Swiss plate remains a CSS `cover` safety plate beneath a transparent Canvas.
- Discovery framing uses aspect-aware overscan with a minimum 7% safety margin. Ultra-wide, 16:9, 4:3 and mobile ratios must not expose any canvas clear color.
- Depth displacement fades to zero across the outer 10% of UV space so the image boundary remains visually flat even while the center retains depth.
- The world is locally separated into soft, mutually exclusive depth strata: far sky/mountains, middle valley/buildings and near lake/tree/table. Feathered thresholds must sum to approximately one to prevent brightness seams.
- The strata may use the approved color/depth plate as a first visual proof. Any revealed pixel falls through to the original safety plate; later inpainted background extensions can replace individual strata without changing the runtime contract.
- Camera motion stays constrained. The purpose of depth is to make the table feel spatial, not to demonstrate free-look reconstruction.

## 11. Stacked diff topology

```text
main
  └── D1 project shell + typed scene/routing contracts
        └── D2 Swiss discovery art plate
              └── D3 Swiss depth-authored entry + seated state
                    └── D4 actor identity + layered human mattes
                          └── D5 Table Host SILENCE/PASS + spatial light
                                └── D6.1 transparent safety plate + aspect overscan + edge lock
                                      └── D6.2 soft local depth strata + responsive tuning
                                            └── D7 superseded by confirmed gallery architecture
                                                  └── D8.0 research + gallery contracts
                                                        └── D8.1 scroll-rig compatibility + global canvas + DOM card registry
                                                              └── D8.2 shared pointer flow + card depth
                                                                    └── D8.3 Swiss card-to-world handoff
                                                                          └── D8.4 responsive, fallback + final polish
                                                                                └── D9.1 world viewport + gallery scroll-state repair
                                                                                      └── D9.2 optimized Table Host GLB asset
                                                                                            └── D9.3 hybrid GLB Host + runtime light language
                                                                                                  └── D9.4 interaction/performance integration QA
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
| D5 Table Host | complete | Sixth-seat Host with `SILENCE` and `PASS`, real-time halo/core/question point and depth-aware table placement | `pnpm build`; Playwright SILENCE/PASS QA at 1440×900 and seated QA at 390×844; zero new console errors |
| D6.1 seamless frame | complete | Transparent canvas, original-art safety plate, aspect-aware overscan and edge displacement falloff | `pnpm build`; Playwright edge QA at 21:9, 16:9, 4:3 and 390×844; zero console errors |
| D6.2 local depth strata | complete | Soft far/middle/near layers with complementary additive feathering and restrained camera parallax | `pnpm build`; Playwright discovery/seated QA at 1440×900 and 390×844; zero console errors |
| D7 old switching/polish | superseded | Replaced by the confirmed gallery-to-world architecture | Product/user confirmation |
| D8.0 research/contracts | complete | Lusion/Three.js evidence, updated states, table visual contract and diff topology | Checkpoint review PASS; `git diff --check`; architecture commit |
| D8.1a scroll-rig contracts | complete | Installed scroll-rig 8.15.0; added discriminated table visuals and the typed three-table gallery selection | `pnpm build`; dependency/peer audit; checkpoint review PASS |
| D8.1b global gallery shell | complete | Added editorial DOM grid, capability gate, temporary gallery GlobalCanvas and exact ScrollScene card-plane registration | `pnpm build`; Playwright 1440×900 + entry/preview paths; zero console errors; checkpoint review PASS |
| D8.2 pointer flow/depth | complete | Shared 128px RGBA8 velocity flow texture, screen-space UV displacement and restrained recovery across all gallery planes | `pnpm build`; pointer/scroll Playwright QA; zero console errors; checkpoint review fixes verified |
| D8.3a world content extraction | complete | Exported the Swiss R3F content without changing its existing standalone Canvas wrapper or behavior | `pnpm build`; `git diff --check`; three-line extraction diff |
| D8.3b persistent renderer | complete | Lifted GlobalCanvas to the app shell and renders the Swiss world through an independent ViewportScrollScene camera while preserving DOM fallback | gallery→world→gallery Playwright path; one persistent canvas node; zero console errors; flow paused in world |
| D8.3c card-to-world motion | complete | Added guarded expanding/collapsing phases, card-rect portal motion, paper reveal mask, delayed world chrome and keyboard focus handoff | complete Playwright pointer/keyboard/reduced-motion paths; one canvas identity; zero console errors |
| D8.3d cover-match calibration | complete | Center-matched the immersive card to the Swiss discovery camera and eased the full-screen plate to the world's 1.1 overscan before reveal | 790ms/1000ms frame comparison; centered transform; one canvas; zero console errors |
| D8.4 responsive/fallback | complete | Touch/native scroll, reduced motion, keyboard focus, DOM-only WebGL failure path and mobile layout | iPhone 15 gallery→world Canvas count 0; desktop Canvas count 1; keyboard/reduced-motion paths; zero console errors |
| D8 integration review | complete | Domain, gallery, shared flow, persistent renderer, Valley viewport, transition state, focus and fallback contracts connected end to end | Integration review PASS; `pnpm build`; tracked worktree clean |
| D9 design confirmation | complete | User confirmed Plan 1: repair the world-entry defects, then use an optimized GLB body with the existing real-time halo/core/question light | Product/user confirmation and supplied GLB audit |
| D9.1 world/scroll repair | complete | World fixed across all active phases; gallery scroll/focus restored through the smooth-scroll owner; wheel step bounded; inactive UI isolated from pointer input | `pnpm build`; Playwright at 1440×900 and 2559×1529: single viewport/Canvas, 0px return error, 520px wheel→360px, console errors 0 |
| D9.2 optimized Host asset | complete | Added reproducible source→2K WebP→skinning-safe simplify→meshopt pipeline and 1.10 MB web derivative; source hash unchanged | 79,902 triangles; 49 joints; 1 skinned mesh; Armature 1s/147 channels; glTF validate 0 errors |
| D9.3 hybrid GLB Host | complete | Optimized skinned GLB now owns the sixth-seat body and embedded idle; the incomplete halo, chest core, question orb, hover and SILENCE/PASS staging remain real-time Three.js layers, with a local sprite fallback | `pnpm build`; normal GLB 200 with zero console errors; abort path preserves the seated world/Host contract; no raw source request |
| D9.4 integration QA | complete | Removed misleading/dead controls, added a local 05/05 join demo with focus-safe feedback, honest unavailable-audio state and functional current-table menu; verified responsive, fallback and scroll-return paths | `pnpm build`; Playwright 1440×900, 2559×1529, 390×844 and reduced-motion; 0px gallery return error; console errors 0 |
| Integration review | complete | D6.1 safety frame remains below D6.2 strata; actor mattes and Table Host preserve their existing contracts | build + discovery/entry/seated interface audit |

## 13. Decision log

- 2026-08-26: The lobby and concrete table are separate spatial levels. Superseded by the 2026-08-29 Table First editorial-gallery decision.
- 2026-08-26: The implementation uses a hybrid 2.5D/WebGL approach instead of full free-roam 3D.
- 2026-08-26: Only one table vertical slice receives full interior treatment before the other scene skins are expanded.
- 2026-08-27: The Swiss-valley art plate is the first implemented visual proof; exact copy and controls remain accessible DOM while Three.js supplies depth, light and ambient motion.
- 2026-08-27: Product architecture corrected to Table First: no lobby or world-selection layer; users switch concrete tables and each table carries its scene skin.
- 2026-08-27: Plan B2 replaces the rejected procedural near field: one depth-authored art surface preserves the final image through discovery and seated camera states, with restrained spatial UI layered above it.
- 2026-08-28: Plan B3 confirmed: preserve the approved plate, add independent identity-bearing human matte layers, and place a separately rendered Table Host in the rear sixth seat with real-time light language.
- 2026-08-28: Plan B4 confirmed: remove single-sheet edge exposure with a transparent same-art safety plate and aspect overscan, then split only the visually valuable far/middle/near depth bands.
- 2026-08-29: Product architecture expanded from direct-to-table to a Table First editorial gallery. Cards are concrete tables, not world choices; one global WebGL canvas turns the selected card into the existing immersive scene.
- 2026-08-29: Lusion-style behavior means DOM/WebGL synchronization, pointer-flow displacement and continuous card-to-world motion; it does not mean copying Lusion's brand or private shader source.
- 2026-08-29: D9 Plan 1 confirmed. The supplied Host GLB becomes the sixth-seat body only after web optimization; the existing Three.js halo, core, local light and question point remain the brand/state layer. The raw source GLB is immutable.
- 2026-08-29: World UI and the persistent Canvas must share viewport coordinates. Gallery scroll is captured before entry, the world stays fixed for expanding/world/collapsing, and the captured position is restored only after the gallery tracker remounts.

## 14. D9 confirmed repair and GLB integration contract

### Cache anchor addendum

- Reproduced defect: a gallery card can be entered while the document retains a non-zero smooth-scroll position. The fixed shared Canvas then renders the world in viewport coordinates while the world DOM/safety plate renders in document coordinates, producing the duplicated upper/lower Swiss scene shown by the user.
- The world root is viewport-fixed during `expanding`, `world`, and `collapsing`; body/document scroll cannot move any world layer.
- Entry captures the gallery scroll position before its smooth-scroll controller unmounts. Return remounts the gallery, restores that position through the scroll owner, and then focuses the source table without forcing a second scroll.
- A normal wheel gesture must not skip an entire featured table. Smooth scrolling keeps inertia but uses near-1:1 input distance with a bounded maximum step.
- Inactive discovery/seated/join/menu controls must be both visually hidden and non-interactive; no invisible hotspot may intercept the pointer.
- The source GLB at `3D/5c8a94ea-b4d5-4f7d-aed7-b94cd6f0a81b.glb` is never overwritten. A derived web asset is generated under `public/assets/actors/`.
- Raw audit baseline: 46,947,728 bytes; 282,671 uploaded vertices; approximately 470,012 triangles; one 8192×8192 PNG texture; 49-joint skin; one 1-second clip. Raw minimum texture allocation is approximately 358 MB and is not production-safe.
- Web derivative target: no more than 80k triangles where visual comparison permits, 2K texture, GPU texture compression when tool support is deterministic, mesh compression, retained skin and idle clip, and a practical transfer target below 8 MB.
- The GLB owns the Host silhouette, skinning and embedded idle motion. Three.js continues to own visibility staging, incomplete halo, chest core, question orb, local light, hover and AgentAction transitions.
- `SILENCE` uses the embedded idle clip plus restrained listening motion. `PASS` uses an additive parent/bone gesture and the existing question-orb travel until a dedicated authored PASS clip exists. Other AgentAction values keep the stable contract but do not invent exaggerated animation.
- Loading failure, low-capability mode and reduced-motion mode retain the current transparent sprite Host as a fallback.

### D9 acceptance criteria

- Entering the Swiss table from any gallery scroll position produces exactly one full-viewport scene with no horizontal seam or duplicate art plate.
- Returning restores the source card within 8 px of its prior viewport position and gives visible focus without jumping to the top.
- One 520 px wheel input cannot advance more than one featured-card interval.
- The optimized Host occupies the rear sixth seat, remains visually behind the table edge, and preserves the approved human/empty-seat composition.
- The Host can be identified and hovered independently as `table-host`; SILENCE and PASS remain visibly distinct.
- No raw 8K texture or 44.8 MB GLB is requested by the browser.
- Production build passes; desktop uses one Canvas, fallback/mobile uses zero or the explicitly supported low-cost path; no console or network errors are introduced.
