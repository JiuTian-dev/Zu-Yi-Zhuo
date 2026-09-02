import { humanActors } from '../actors'
import type { ClientHumanMessage, ParticipantSeedLike, ServerEvent } from './contract'
import { fetchCloseArtifacts, fetchLobby, fetchReplay, fetchTableState, previewLobbyFit, setProfileConsent } from './api'
import type { LobbyFitPreviewLike, LobbyPreviewLike, ReplayResponseLike } from './contract'
import * as mock from './mock'
import { getLiveState, pushMessage, resetLive, setLive, type LiveStatus } from './store'

export const VIEWER_ID = 'viewer'
const DEFAULT_TABLE_ID = 'valley-learning-to-rest'
const DEFAULT_CORE_QUESTION = '为什么我们越来越不会休息？'

const runtime = {
  sockets: new Set<WebSocket>(),
  timers: new Set<number>(),
  viewerSocket: null as WebSocket | null,
  observerSocket: null as WebSocket | null,
  viewerJoined: false,
  reopenCount: 0,
  viewerMessageSeq: 0,
  seenMessageIds: new Set<string>(),
  seenActionKeys: new Set<string>(),
  seenStateVersions: new Set<number>(),
}

let activeTableId = DEFAULT_TABLE_ID

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

export const viewerSeed = (openingText = ''): ParticipantSeedLike => ({
  participant_id: VIEWER_ID,
  display_name: '你',
  role: '第五席',
  declared_position: openingText.trim() || '一个正在尝试真正停下来的人',
  relevant_experience: openingText.trim()
    ? [{ text: openingText.trim(), source_ref: 'ui:viewer:opening' }]
    : [],
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
  const mode = participantId === VIEWER_ID ? '&viewer_mode=observer' : ''
  return `${scheme}://${location.host}/ws/tables/${encodeURIComponent(tableId)}?participant_id=${encodeURIComponent(participantId)}${mode}`
}

function trackSocket(socket: WebSocket) {
  runtime.sockets.add(socket)
  socket.addEventListener('close', () => runtime.sockets.delete(socket))
}

function handleServerEvent(event: ServerEvent) {
  switch (event.type) {
    case 'message_committed':
      if (runtime.seenMessageIds.has(event.message.message_id)) return
      runtime.seenMessageIds.add(event.message.message_id)
      pushMessage({ participantId: event.message.participant_id, text: event.message.text, fromHost: false, action: null })
      break
    case 'agent_action':
      {
        const actionKey = `${event.state_version}:${event.action}:${event.target_participant_id ?? ''}:${event.text ?? ''}`
        if (runtime.seenActionKeys.has(actionKey)) return
        runtime.seenActionKeys.add(actionKey)
      }
      setLive({ hostAction: { action: event.action, text: event.text, target: event.target_participant_id } })
      if (event.text) pushMessage({ participantId: 'table-host', text: event.text, fromHost: true, action: event.action })
      break
    case 'table_state_changed':
      if (runtime.seenStateVersions.has(event.state.version)) return
      runtime.seenStateVersions.add(event.state.version)
      setLive({
        tableState: event.state,
        phase: event.state.phase,
        coreQuestion: event.state.core_question,
        subQuestion: event.state.current_subquestion,
        seatCount: Object.keys(event.state.participants).length,
      })
      break
    case 'grounding_card':
      setLive({ groundingCard: { title: event.title, excerpt: event.excerpt, source_ref: event.source_ref, signal_id: event.signal_id } })
      break
    case 'intervention_reflected':
      setLive({ latestReflection: event.record.reflection ?? null })
      break
    case 'participant_added':
    case 'participant_left':
      if (event.state) setLive({ tableState: event.state, seatCount: Object.keys(event.state.participants).length })
      break
    case 'table_mode_changed':
      setLive({ tableMode: event.mode })
      break
    case 'safety_private_reminder':
    case 'safety_soft_intervention':
      setLive({ safetyNotice: event.text })
      break
    case 'safety_enforced':
      setLive({ tableState: event.state, phase: event.state.phase, subQuestion: event.state.current_subquestion, seatCount: Object.keys(event.state.participants).length, safetyNotice: event.decision.reason })
      break
    case 'error':
      setLive({ lastError: event.detail })
      break
    case 'participant_consent_changed':
      {
        const state = getLiveState().tableState
        if (state?.participants[event.participant_id])
          setLive({ tableState: { ...state, participants: { ...state.participants, [event.participant_id]: { ...state.participants[event.participant_id], profile_shared: event.profile_shared } } } })
      }
      break
    case 'close_started':
      setLive({ closeState: 'started' })
      break
    case 'close_artifact_ready':
      setLive({ closeState: 'ready', baseline: event.shared_baseline, personalCard: event.personal_card })
      break
    case 'table_closed':
      setLive({ closeState: 'started' })
      void recoverCloseArtifacts(activeTableId, VIEWER_ID)
      break
    default:
      break
  }
}

async function recoverCloseArtifacts(tableId: string, participantId: string) {
  try {
    const artifacts = await fetchCloseArtifacts(tableId, participantId)
    setLive({
      closeState: 'ready',
      baseline: artifacts.shared_baseline as LiveStatus['baseline'],
      personalCard: artifacts.personal_card as LiveStatus['personalCard'],
    })
  } catch {
    // The live close event remains the first source. Recovery is best effort
    // because a viewer may not be a member and therefore cannot read a card.
  }
}

function openPuppet(tableId: string, participantId: string, mode: 'participant' | 'observer' = 'participant'): Promise<WebSocket | null> {
  return new Promise((resolve) => {
    let settled = false
    let socket: WebSocket
    try {
      const scheme = location.protocol === 'https:' ? 'wss' : 'ws'
      const url = `${scheme}://${location.host}/ws/tables/${encodeURIComponent(tableId)}?participant_id=${encodeURIComponent(participantId)}${mode === 'observer' ? '&viewer_mode=observer' : ''}`
      socket = new WebSocket(url)
    } catch {
      resolve(null)
      return
    }
    const settle = (result: WebSocket | null) => {
      if (settled) return
      settled = true
      window.clearTimeout(timer)
      resolve(result)
    }
    const timer = window.setTimeout(() => {
      socket.close()
      settle(null)
    }, 4000)
    socket.addEventListener('open', () => {
      trackSocket(socket)
      settle(socket)
    })
    socket.addEventListener('message', (raw) => {
      try {
        handleServerEvent(JSON.parse(raw.data) as ServerEvent)
      } catch {
        /* ignore malformed frames */
      }
    })
    socket.addEventListener('close', () => {
      settle(null)
      if (mode !== 'participant') return
      if (getHealthy()) return
      if (getLiveState().status === 'live') setLive({ status: 'error' })
    })
    socket.addEventListener('error', () => settle(null))
  })
}

function getHealthy(): boolean {
  return [...runtime.sockets].some((socket) => socket.readyState === WebSocket.OPEN)
}

function sendVia(socket: WebSocket, payload: ClientHumanMessage | { type: 'request_close' } | { type: 'request_nudge' }): boolean {
  if (socket.readyState !== WebSocket.OPEN) return false
  socket.send(JSON.stringify(payload))
  return true
}

/** Runtime bookkeeping for the authoritative backend stream and explicit mock fallback. */
let liveGeneration = 0

function resetEventDedupe() {
  runtime.seenMessageIds.clear()
  runtime.seenActionKeys.clear()
  runtime.seenStateVersions.clear()
}

function applyTableState(state: NonNullable<LiveStatus['tableState']>) {
  setLive({
    tableState: state,
    phase: state.phase,
    coreQuestion: state.core_question,
    subQuestion: state.current_subquestion,
    seatCount: Object.keys(state.participants).length,
    tableMode: state.conversation.mode ?? null,
  })
}

export async function ensureTable(tableId = DEFAULT_TABLE_ID, coreQuestion = DEFAULT_CORE_QUESTION, allowClosed = false): Promise<string | null> {
  let candidateTableId = tableId === DEFAULT_TABLE_ID && activeTableId !== DEFAULT_TABLE_ID ? activeTableId : tableId
  for (let attempt = 0; attempt < 2; attempt += 1) {
    try {
      const existing = await fetchWithTimeout(`/tables/${candidateTableId}`)
      if (existing.ok) {
        const state = await existing.json()
        if (state.conversation?.closed && !allowClosed) {
          runtime.reopenCount += 1
          candidateTableId = `${tableId}-${runtime.reopenCount}`
          continue
        }
        activeTableId = candidateTableId
        return candidateTableId
      }
      const created = await fetchWithTimeout('/tables', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ table_id: candidateTableId, core_question: coreQuestion, participants: actorSeeds() }),
      })
      if (created.ok || created.status === 409) {
        activeTableId = candidateTableId
        return candidateTableId
      }
      return null
    } catch {
      return null
    }
  }
  return candidateTableId
}

export async function startLive(tableId = DEFAULT_TABLE_ID, coreQuestion = DEFAULT_CORE_QUESTION): Promise<void> {
  const generation = ++liveGeneration
  resetLive()
  resetEventDedupe()
  setLive({ status: 'connecting' })
  const readyTableId = await ensureTable(tableId, coreQuestion, true)
  if (generation !== liveGeneration) return
  if (!readyTableId) {
    if (generation !== liveGeneration) return
    mock.startMock()
    return
  }
  const stageSocket = await openPuppet(readyTableId, VIEWER_ID, 'observer')
  if (generation !== liveGeneration) return
  if (!stageSocket) {
    if (generation !== liveGeneration) return
    mock.startMock()
    return
  }
  setLive({ status: 'live', coreQuestion })
  runtime.observerSocket = stageSocket
  try {
    const state = await fetchTableState(readyTableId)
    applyTableState(state)
    if (state.participants[VIEWER_ID]) {
      const participantSocket = await openPuppet(readyTableId, VIEWER_ID, 'participant')
      if (participantSocket && generation === liveGeneration) {
        runtime.observerSocket?.close()
        runtime.observerSocket = null
        runtime.viewerJoined = true
        runtime.viewerSocket = participantSocket
        setLive({ viewerJoined: true })
      }
      if (state.conversation.closed) void recoverCloseArtifacts(readyTableId, VIEWER_ID)
    }
  } catch {
    // The observer stream remains authoritative if the initial REST refresh races it.
  }
}

export async function joinViewer(openingText = '', profileShared = false): Promise<boolean> {
  if (runtime.viewerJoined) return true
  if (getLiveState().status === 'mock') {
    runtime.viewerJoined = true
    setLive({ seatCount: 5, viewerJoined: true })
    if (openingText.trim()) mock.sendViewerMessage(openingText.trim())
    return true
  }
  try {
    const response = await fetchWithTimeout(`/tables/${currentTableId()}/participants`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(viewerSeed(openingText)),
    })
    if (!response.ok && response.status !== 409) return false
  } catch {
    return false
  }
  runtime.observerSocket?.close()
  runtime.observerSocket = null
  const socket = await openPuppet(currentTableId(), VIEWER_ID, 'participant')
  if (!socket) return false
  runtime.viewerJoined = true
  runtime.viewerSocket = socket
  setLive({ viewerJoined: true })
  try {
    applyTableState(await fetchTableState(currentTableId(), VIEWER_ID))
  } catch {
    // The participant socket remains the authoritative source if this refresh races it.
  }
  if (profileShared) void setProfileConsent(currentTableId(), VIEWER_ID, true).then(applyTableState).catch(() => undefined)
  if (openingText.trim()) {
    sendViewerMessage(openingText.trim())
  }
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
    message_id: `viewer-${Date.now()}-${++runtime.viewerMessageSeq}`,
    participant_id: VIEWER_ID,
    text: trimmed,
    client_ts: Date.now(),
  })
}

export function requestNudge(): boolean {
  if (getLiveState().status === 'mock') {
    mock.sendViewerMessage('我想听听主持人的下一步引导。')
    return true
  }
  return !!runtime.viewerSocket && sendVia(runtime.viewerSocket, { type: 'request_nudge' })
}

export async function loadLobby(tableId = currentTableId()): Promise<LobbyPreviewLike | null> {
  try {
    return await fetchLobby(tableId)
  } catch {
    return null
  }
}

export async function loadLobbyFit(tableId: string, participant = viewerSeed()): Promise<LobbyFitPreviewLike | null> {
  try {
    return await previewLobbyFit(tableId, participant)
  } catch {
    return null
  }
}

export async function loadReplay(tableId = currentTableId(), participantId?: string): Promise<ReplayResponseLike | null> {
  try {
    return await fetchReplay(tableId, participantId)
  } catch {
    return null
  }
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
  runtime.observerSocket = null
  runtime.viewerJoined = false
  setLive({ viewerJoined: false })
  resetEventDedupe()
}
