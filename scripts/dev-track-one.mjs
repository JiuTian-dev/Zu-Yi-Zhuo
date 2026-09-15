import { fileURLToPath } from 'node:url'
import path from 'node:path'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')

if (process.env.ENABLE_TRACK_ONE_DEMO === undefined) process.env.ENABLE_TRACK_ONE_DEMO = '1'
if (process.env.MAX_TABLE_PARTICIPANTS === undefined) process.env.MAX_TABLE_PARTICIPANTS = '4'
if (process.env.TABLE_REPOSITORY_PATH === undefined) {
  process.env.TABLE_REPOSITORY_PATH = path.join(root, '.demo-data', 'tables.json')
}

await import('./dev-stack.mjs')
