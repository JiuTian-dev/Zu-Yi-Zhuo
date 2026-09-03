# Removed from the production path

These capabilities belonged to the upstream game/portfolio experience and
are intentionally outside 组一桌's product boundary.

- Vehicle and driving: `PhysicsVehicle`, `VisualVehicle`, player movement,
  keyboard/gamepad input, tracks and physics wireframes.
- Gameplay: explosions, crates, fireballs, lightning, tornado, zones,
  interactive points, achievements, easter eggs and notifications.
- Portfolio shell: title, menu, overlays, maps, projects, social links,
  personal/portfolio copy and the original multiplayer server/whispers.
- Respawn asset: `Game/Respawns.js` and `public/assets/bruno-runtime/respawnsReferences.glb`.
  The product uses the explicit `Game/tableAnchors.js` table coordinate instead.

Removal means four things are true: no import, no runtime instantiation, no
asset load, and no product entry point. The original source remains available
only through the upstream baseline commit and the repository history.
