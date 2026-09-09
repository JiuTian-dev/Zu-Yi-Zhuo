import { spawn } from 'node:child_process'
import { fileURLToPath } from 'node:url'
import path from 'node:path'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const backendRoot = path.join(root, 'backend')
const frontendPort = process.env.DEV_FRONTEND_PORT ?? '5174'
const backendPort = process.env.DEV_BACKEND_PORT ?? '8000'
const command = process.platform === 'win32' ? 'pnpm.cmd' : 'pnpm'
const python = process.platform === 'win32' ? 'py.exe' : 'python3'
const children = []
let stopping = false

function start(label, executable, args, cwd, env = {}) {
  const child = spawn(executable, args, {
    cwd,
    env: { ...process.env, ...env },
    stdio: 'inherit',
    windowsHide: false,
  })
  children.push(child)
  child.once('error', (error) => {
    console.error(`[${label}] ${error.message}`)
    stop(1)
  })
  child.once('exit', (code, signal) => {
    if (stopping) return
    const result = code ?? (signal ? 1 : 0)
    console.log(`[${label}] 已退出 (${result})，正在关闭另一项服务。`)
    stop(result)
  })
  return child
}

function stop(code = 0) {
  if (stopping) return
  stopping = true
  for (const child of children) {
    if (!child.killed) child.kill()
  }
  setTimeout(() => process.exit(code), 300)
}

process.once('SIGINT', () => stop(0))
process.once('SIGTERM', () => stop(0))

console.log(`前端: http://127.0.0.1:${frontendPort}/`)
console.log(`后端: http://127.0.0.1:${backendPort}/`)

start('backend', python, [
  '-m', 'uvicorn', 'app.main:app',
  '--host', '127.0.0.1',
  '--port', backendPort,
], backendRoot, { PYTHONPATH: '.' })

const frontendExecutable = process.platform === 'win32' ? (process.env.ComSpec ?? 'cmd.exe') : command
const frontendArgs = process.platform === 'win32'
  ? ['/d', '/s', '/c', command, 'dev', '--host', '127.0.0.1', '--port', frontendPort]
  : ['dev', '--host', '127.0.0.1', '--port', frontendPort]
start('frontend', frontendExecutable, frontendArgs, root)
