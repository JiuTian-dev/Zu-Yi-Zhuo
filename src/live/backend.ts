import { humanActors } from '../actors'
import type { ClientHumanMessage, ServerEvent } from './contract'
import * as mock from './mock'
import { getLiveState, pushMessage, resetLive, setLive } from './store'

export const VIEWER_ID = 'viewer'

const runtime = {
  sockets: new Set<WebSocket>(),
  timers: new Set<number>(),
  viewerSocket: null as WebSocket | null,
  viewerJoined: false,
  reopenCount: 0,
}

let activeTableId = 'valley-learning-to-rest'

export function currentTableId(): string {
  return activeTableId
}

function actorSeeds() {
  return humanActors.map((actor) => ({
    participant_id: actor.id,
    display_name: actor.displayName,
    role: actor.role,
    declared_position: actor.quote ?? actor.whyHere,
    relevant_experience: [{ text: actor.whyHere, source_ref: `seed:${actor.id}:experience` }],
  }))
}

const viewerSeed = () => ({
  participant_id: VIEWER_ID,
  display_name: '你',
  role: '第五席',
  declared_position: '一个正在尝试真正停下来的人',
  relevant_experience: [],
})

async function fetchWithTimeout(url: string, init?: RequestInit, ms = 3000): Promise<Response> {
  const controller = new AbortController()
  const timer = window.setTimeout(() => controller.abort(), ms)
  try {
    return await fetch(url, { ...init, signal: controller.signal })
  } finally {
    window.clearTimeout(timer)
  }
}

function wsUrl(tableId: string, participantId: string): string {
  const scheme = location.protocol === 'https:' ? 'wss' : 'ws'
  return `${scheme}://${location.host}/ws/tables/${tableId}?participant_id=${encodeURIComponent(participantId)}`
}

function trackSocket(socket: WebSocket) {
  runtime.sockets.add(socket)
  socket.addEventListener('close', () => runtime.sockets.delete(socket))
}

function handleServerEvent(event: ServerEvent) {
  switch (event.type) {
    case 'message_committed':
      pushMessage({ participantId: event.message.participant_id, text: event.message.text, fromHost: false, action: null })
      break
    case 'agent_action':
      setLive({ hostAction: { action: event.action, text: event.text, target: event.target_participant_id } })
      if (event.text) pushMessage({ participantId: 'table-host', text: event.text, fromHost: true, action: event.action })
      break
    case 'table_state_changed':
      setLive({
        phase: event.state.phase,
        coreQuestion: event.state.core_question,
        subQuestion: event.state.current_subquestion,
        seatCount: Object.keys(event.state.participants).length,
      })
      break
    case 'close_started':
      setLive({ closeState: 'started' })
      break
    case 'close_artifact_ready':
      setLive({ closeState: 'ready', baseline: event.shared_baseline, personalCard: event.personal_card })
      break
    default:
      break
  }
}

async function ensureTable(): Promise<string | null> {
  let tableId = `valley-learning-to-rest${runtime.reopenCount ? `-${runtime.reopenCount}` : ''}`
  for (let attempt = 0; attempt < 2; attempt += 1) {
    try {
      const existing = await fetchWithTimeout(`/tables/${tableId}`)
      if (existing.ok) {
        const state = await existing.json()
        if (state.conversation?.closed) {
          runtime.reopenCount += 1
          tableId = `valley-learning-to-rest-${runtime.reopenCount}`
          continue
        }
        activeTableId = tableId
        return tableId
      }
      const created = await fetchWithTimeout('/tables', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ table_id: tableId, core_question: '为什么我们越来越不会休息？', participants: actorSeeds() }),
      })
      if (created.ok || created.status === 409) {
        activeTableId = tableId
        return tableId
      }
      return null
    } catch {
      return null
    }
  }
  return tableId
}

function openPuppet(tableId: string, participantId: string): Promise<boolean> {
  return new Promise((resolve) => {
    let settled = false
    let socket: WebSocket
    try {
      socket = new WebSocket(wsUrl(tableId, participantId))
    } catch {
      resolve(false)
      return
    }
    const settle = (result: boolean) => {
      if (settled) return
      settled = true
      window.clearTimeout(timer)
      resolve(result)
    }
    const timer = window.setTimeout(() => {
      socket.close()
      settle(false)
    }, 4000)
    socket.addEventListener('open', () => {
      trackSocket(socket)
      settle(true)
    })
    socket.addEventListener('message', (raw) => {
      try {
        handleServerEvent(JSON.parse(raw.data) as ServerEvent)
      } catch {
        /* ignore malformed frames */
      }
    })
    socket.addEventListener('close', () => {
      settle(false)
      if (participantId !== humanActors[0].id) return
      if (getHealthy()) return
      if (getLiveState().status === 'live') setLive({ status: 'error' })
    })
    socket.addEventListener('error', () => settle(false))
  })
}

function getHealthy(): boolean {
  return [...runtime.sockets].some((socket) => socket.readyState === WebSocket.OPEN)
}

function sendVia(socket: WebSocket, payload: ClientHumanMessage | { type: 'request_close' }): boolean {
  if (socket.readyState !== WebSocket.OPEN) return false
  socket.send(JSON.stringify(payload))
  return true
}

/** Scripted valley-topic conversation that drives the deterministic backend host. */
const SCRIPT: Array<{ id: string; text: string; waitMs: number }> = [
  { id: 'shen-zhiyao', text: '上个月我给自己排了三天「什么都不做」，结果每天都在焦虑这三天被浪费了。', waitMs: 4200 },
  { id: 'zhou-mo', text: '我不敢让时间空下来，一空下来就觉得自己正在被淘汰。', waitMs: 5200 },
  { id: 'lin-zhou', text: '自由职业之后没人给我下班的概念，我反而怀念被迫休息的日子。', waitMs: 5200 },
  { id: 'xu-qing', text: '你们说的都是「停下来之后的内疚」，这其实是把价值感绑在了产出上。', waitMs: 5600 },
  { id: 'zhou-mo', text: '所以问题不是没时间休息，而是停下来的时候，我什么都不是？', waitMs: 5600 },
  { id: 'shen-zhiyao', text: '可能吧，可我就是靠产出获得安全感的，放下它我不知道自己是谁。', waitMs: 5600 },
  { id: 'xu-qing', text: '休息不是从工作里偷来的时间，它本来就是生活的默认状态，是我们把它变成了奖励。', waitMs: 5600 },
  { id: 'lin-zhou', text: '如果把它当默认状态，我第一件要改的就是把「回消息」从休息日的义务里删掉。', waitMs: 5400 },
]

let liveGeneration = 0

export async function startLive(): Promise<void> {
  const generation = ++liveGeneration
  resetLive()
  setLive({ status: 'connecting' })
  const tableId = await ensureTable()
  if (generation !== liveGeneration) return
  if (!tableId) {
    const { startMock } = await import('./mock')
    if (generation !== liveGeneration) return
    startMock()
    return
  }
  const [first, ...rest] = humanActors
  const stageOk = await openPuppet(tableId, first.id)
  if (generation !== liveGeneration) return
  if (!stageOk) {
    const { startMock } = await import('./mock')
    if (generation !== liveGeneration) return
    startMock()
    return
  }
  setLive({ status: 'live', coreQuestion: '为什么我们越来越不会休息？' })
  for (const actor of rest) {
    void openPuppet(tableId, actor.id)
  }
  let index = 0
  const step = () => {
    if (index >= SCRIPT.length) return
    const line = SCRIPT[index]
    index += 1
    const socket = [...runtime.sockets].find((candidate) => candidate.readyState === WebSocket.OPEN)
    if (socket) sendVia(socket, { type: 'human_message', message_id: `script-${tableId}-${index}`, participant_id: line.id, text: line.text, client_ts: Date.now() })
    runtime.timers.add(window.setTimeout(step, line.waitMs))
  }
  runtime.timers.add(window.setTimeout(step, 2600))
}

export async function joinViewer(): Promise<boolean> {
  if (runtime.viewerJoined) return true
  if (getLiveState().status === 'mock') {
    runtime.viewerJoined = true
    setLive({ seatCount: 5 })
    return true
  }
  try {
    const response = await fetchWithTimeout(`/tables/${currentTableId()}/participants`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(viewerSeed()),
    })
    if (!response.ok && response.status !== 409) return false
  } catch {
    return false
  }
  runtime.viewerJoined = true
  const socket = new WebSocket(wsUrl(currentTableId(), VIEWER_ID))
  socket.addEventListener('message', (raw) => {
    try {
      handleServerEvent(JSON.parse(raw.data) as ServerEvent)
    } catch {
      /* ignore */
    }
  })
  trackSocket(socket)
  runtime.viewerSocket = socket
  return true
}

export function sendViewerMessage(text: string): boolean {
  const trimmed = text.trim()
  if (!trimmed) return false
  if (getLiveState().status === 'mock') {
    mock.sendViewerMessage(trimmed)
    return true
  }
  return !!runtime.viewerSocket && sendVia(runtime.viewerSocket, {
    type: 'human_message',
    message_id: `viewer-${Date.now()}`,
    participant_id: VIEWER_ID,
    text: trimmed,
    client_ts: Date.now(),
  })
}

export function requestClose(): boolean {
  if (getLiveState().status === 'mock') {
    mock.requestClose()
    return true
  }
  return !!runtime.viewerSocket && sendVia(runtime.viewerSocket, { type: 'request_close' })
}

export function stopLive() {
  liveGeneration += 1
  runtime.timers.forEach((timer) => window.clearTimeout(timer))
  runtime.timers.clear()
  mock.stopMock()
  runtime.sockets.forEach((socket) => socket.close())
  runtime.sockets.clear()
  runtime.viewerSocket = null
  runtime.viewerJoined = false
}
