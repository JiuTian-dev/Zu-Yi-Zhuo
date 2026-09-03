import { readFileSync, existsSync } from 'node:fs'
import { resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = fileURLToPath(new URL('..', import.meta.url))
const read = (file) => readFileSync(resolve(root, file), 'utf8')
const failures = []
const expect = (condition, message) => {
  if (!condition) failures.push(message)
}

const game = read('src/bruno-runtime/Game/Game.js')
const app = read('src/App.tsx')
const lobby = read('src/Lobby.tsx')
const replay = read('src/live/DiscussionPanel.tsx')
const backend = read('src/live/backend.ts')
const tableWorld = read('src/TableWorld.tsx')
const vite = read('vite.config.ts')

expect(!game.includes('Respawns'), 'Game.js still references the removed Respawns system')
expect(!game.includes('respawnsReferences.glb'), 'Game.js still loads the removed respawn asset')
expect(!app.includes('actorAnchors'), 'App.tsx still owns fixed percentage actor anchors')
expect(!app.includes('humanActors'), 'App.tsx still falls back to fixture participants')
expect(!lobby.includes('humanActors'), 'Lobby.tsx still falls back to fixture participants')
expect(replay.includes('createPortal'), 'DiscussionPanel is not rendered through a Portal')
expect(replay.includes('aria-modal="true"'), 'DiscussionPanel is missing modal semantics')
expect(replay.includes('sourceSignals'), 'DiscussionPanel does not project replay source signals')
expect(backend.includes("DEFAULT_TABLE_ID = 'learning-to-rest'"), 'frontend default table id is not aligned with the seeded backend table')
expect(backend.includes('viewerIdentity.observerId'), 'observer WebSocket does not use a separate observer identity')
expect(tableWorld.match(/className="bruno-runtime-canvas"/g)?.length === 1, 'TableWorld must mount exactly one Bruno canvas shell')
expect(vite.includes('strictPort: true') && vite.includes('port: 5174'), 'Vite dev server port is not fixed to 5174')
expect(existsSync(resolve(root, 'src/experience/ORIGIN.md')), 'source map is missing at the spec path src/experience/ORIGIN.md')
expect(existsSync(resolve(root, 'src/bruno-runtime/REMOVAL-MANIFEST.md')), 'removal manifest is missing')

if (failures.length) {
  console.error(failures.map((failure) => `FAIL: ${failure}`).join('\n'))
  process.exit(1)
}

console.log('frontend verification passed: runtime boundary, backend identity, replay overlay, single canvas, and dev server invariants')
