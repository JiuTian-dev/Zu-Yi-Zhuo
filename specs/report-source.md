# Lusion-style Table Gallery Research

> Audience: 组一桌前端实现团队  
> Date: 2026-08-29  
> Scope: DOM × single WebGL canvas × shader interaction × card-to-world transition

## Executive answer

The production-safe architecture is a progressively enhanced DOM gallery backed by one application-level WebGL canvas. DOM owns layout, copy, semantics and focus; WebGL owns card imagery, pointer flow, image depth and the continuous transition into the existing valley world. The selected card plane remains mounted while its rectangle animates from the DOM card bounds to the viewport, then crossfades into the existing depth-authored valley scene at a matched discovery camera.

Use `@14islands/r3f-scroll-rig` as the reusable synchronization skeleton rather than rebuilding DOM tracking, visibility observation and shared-canvas lifecycle. The product is expected to grow beyond three cards, so its `GlobalCanvas`, `SmoothScrollbar`, `ScrollScene` and tracker primitives reduce long-term integration risk. Our code still owns the table shader, transition choreography, seated-world state and Agent contracts.

## Evidence and decisions

### One canvas, DOM proxy elements

- Lusion's own MIT-licensed WebGL Scroll Sync demo uses one renderer, one fullscreen/overscanned canvas and DOM image containers whose bounds are converted into shader uniforms. Source: [Lusion WebGL Scroll Sync](https://github.com/lusionltd/WebGL-Scroll-Sync).
- Three.js documents the same virtual-canvas pattern and warns that multiple contexts duplicate resources and hit browser context limits. Source: [Three.js: Multiple Canvases, Multiple Scenes](https://threejs.org/manual/en/multiple-scenes.html).
- Decision: capable desktop mounts one `GlobalCanvas`/renderer with two scenes and two cameras. Gallery cards use `ScrollScene` with the rig-managed camera; the valley is rendered through an R3F portal with its existing independent perspective camera. During expansion both scenes render to separate targets and a transition pass composites them; after world takeover the gallery tracker and pass pause.
- `r3f-scroll-rig` provides one shared `GlobalCanvas`, DOM tracking, viewport culling and Lenis integration while keeping React/R3F/Three as peer dependencies. Source: [r3f-scroll-rig official repository](https://github.com/14islands/r3f-scroll-rig).

### Scroll synchronization

- Lusion documents the rAF/native-scroll desynchronization problem. Its mitigation is an absolutely positioned canvas that scrolls with the document, plus 25% vertical overscan or framebuffer edge blending. Source: [Lusion WebGL Scroll Sync README](https://github.com/lusionltd/WebGL-Scroll-Sync#readme).
- Lenis exposes animated scroll, velocity, ResizeObserver integration and reduced-motion behavior for WebGL scroll synchronization. Source: [Lenis official repository](https://github.com/darkroomengineering/lenis).
- Decision: use the rig's `SmoothScrollbar`/Lenis path on fine-pointer desktop and its tracker primitives for card bounds. Touch uses native scroll and disables pointer flow.

### Pointer flow and displacement

- Lusion's private homepage shader is not published. A Three.js community inspection identifies the visible cursor response as a post-process/2D displacement applied to WebGL imagery only; treat this as informed observation, not an official implementation disclosure. Source: [Three.js forum analysis](https://discourse.threejs.org/t/mouse-effet-at-the-top-of-three-js-like-on-https-lusion-co/57385).
- The OGL author's official flowmap example computes pointer velocity, eases it, writes it into a flow texture and offsets image UVs with the RG velocity channels. Source: [OGL mouse flowmap example](https://github.com/oframe/ogl/blob/master/examples/mouse-flowmap.html).
- Decision: a shared 128–256 px RGBA8 ping-pong flow target drives all visible gallery planes. Each plane converts the global pointer to local UV before sampling. Avoid float textures and full-resolution simulation.

### Card-to-world transition

- GSAP Flip records an element's viewport bounds, applies the new layout, then animates the inverse transform; its React guidance requires stable `data-flip-id` values and waiting for committed layout. Source: [GSAP Flip documentation](https://gsap.com/docs/v3/Plugins/Flip/).
- Three.js provides scene transition primitives using two scenes/render targets and a transition factor. Source: [Three.js RenderTransitionPass](https://threejs.org/docs/pages/RenderTransitionPass.html).
- Decision: DOM title/chrome use GSAP; the tracked WebGL plane expands from its measured bounds while remaining under the gallery camera. At 70% expansion, a matched valley discovery render target fades in through an explicit transition pass; the gallery target pauses only after the match is visually stable.

### Performance and accessibility

- R3F recommends on-demand rendering when a scene is idle and explicit invalidation when animation occurs. Source: [R3F scaling performance](https://r3f.docs.pmnd.rs/advanced/scaling-performance).
- MDN recommends replacing large scale/pan motion when `prefers-reduced-motion` is active. Source: [MDN prefers-reduced-motion](https://developer.mozilla.org/en-US/docs/Web/CSS/Reference/At-rules/%40media/prefers-reduced-motion).
- Decision: gallery uses continuous frames only while scrolling, hovering, transitioning, while flow energy remains above epsilon, or while ambient scene motion is visible. Reduced-motion uses an opacity dissolve; mobile uses native `<img>` fallbacks and a short full-screen crossfade.

## Visual direction

- Canvas Paper `#EEF0F5`: quiet cool editorial ground that supports the alpine palette.
- Carbon `#111315`: primary gallery text.
- Moss `#315246`: status and focus color.
- Cloud `#747A82`: metadata.
- World Light `#FFF9E9`: transition bridge into the existing valley interface.
- Gallery typography: modern Chinese sans for titles and metadata; the immersive world retains the existing restrained serif.
- Signature: the image is a portal. No glass cards, gradients, shadows or decorative badges compete with the WebGL behavior.

## MVP stopping point

1. One real Swiss table and two data-backed "forming" cards.
2. Single global canvas and exact DOM-plane registration.
3. Pointer flow plus restrained depth parallax on desktop.
4. Swiss card expands into the current valley discovery state without a hard cut.
5. Existing approach, seated, actor and Table Host behavior remains functional.
6. Desktop, mobile, keyboard, reduced-motion and WebGL-fallback checks pass.

## Limitations

- Lusion's production homepage source and exact displacement shader are proprietary; the implementation reproduces the interaction class, not private code.
- The user-provided campfire and Workshop art are placeholders until their final clean plates are selected.
- Exact continuous visual matching depends on the gallery cover crop and valley discovery camera using the same cover-fit contract.
