import { humanActors } from '../actors'
import type { ClientHumanMessage, ParticipantSeedLike, ServerEvent } from './contract'
import { BackendApiError, fetchCloseArtifacts, fetchLobby, fetchReplay, fetchTableState, previewLobbyFit, requestRaw, setProfileConsent, wsUrl } from './api'
import type { LobbyFitPreviewLike, LobbyPreviewLike, ReplayResponseLike } from './contract'
import { VIEWER_ID, viewerIdentity } from './identity'
import * as mock from './mock'
import { commitMessage, getLiveState, markMessageFailed, markMessagePending, pushMessage, resetLive, setLive, type LiveStatus } from './store'

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
  latestStateVersion: -1,
  reconnectAttempt: 0,
  reconnectTimer: null as number | null,
  intentionalCloses: new WeakSet<WebSocket>(),
}

let activeTableId = DEFAULT_TABLE_ID
const ensureRequests = new Map<string, Promise<string | null>>()

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
  display_name: viewerIdentity.displayName,
  role: viewerIdentity.role,
  declared_position: openingText.trim() || '一个正在尝试真正停下来的人',
  relevant_experience: openingText.trim()
    ? [{ text: openingText.trim(), source_ref: 'ui:viewer:opening' }]
    : [],
})

function trackSocket(socket: WebSocket) {
  runtime.sockets.add(socket)
  socket.addEventListener('close', () => runtime.sockets.delete(socket))
}

function closeSocket(socket: WebSocket | null) {
  if (!socket) return
  runtime.intentionalCloses.add(socket)
  socket.close()
}

function handleServerEvent(event: ServerEvent) {
  switch (event.type) {
    case 'message_committed':
      if (runtime.seenMessageIds.has(event.message.message_id)) return
      runtime.seenMessageIds.add(event.message.message_id)
      commitMessage(event.message.message_id, { participantId: event.message.participant_id, text: event.message.text, fromHost: false, action: null })
      break
    case 'agent_action':
      {
        const actionKey = `${event.state_version}:${event.action}:${event.target_participant_id ?? ''}:${event.text ?? ''}`
        if (runtime.seenActionKeys.has(actionKey)) return
        runtime.seenActionKeys.add(actionKey)
      }
      setLive({ hostAction: { action: event.action, text: event.text, target: event.target_participant_id }, speakingId: event.target_participant_id ?? 'table-host' })
      if (event.text) pushMessage({ participantId: 'table-host', text: event.text, fromHost: true, action: event.action })
      break
    case 'table_state_changed':
      applyTableState(event.state)
      break
    case 'grounding_card':
      setLive({ groundingCard: { title: event.title, excerpt: event.excerpt, source_ref: event.source_ref, signal_id: event.signal_id } })
      break
    case 'intervention_reflected':
      setLive({ latestReflection: event.record.reflection ?? null })
      break
    case 'participant_added':
    case 'participant_left':
      if (event.state) applyTableState(event.state)
      break
    case 'table_mode_changed':
      setLive({ tableMode: event.mode })
      break
    case 'safety_private_reminder':
    case 'safety_soft_intervention':
      setLive({ safetyNotice: event.text })
      break
    case 'safety_enforced':
      if (acceptStateVersion(event.state.version)) setLive({ tableState: event.state, phase: event.state.phase, subQuestion: event.state.current_subquestion, seatCount: Object.keys(event.state.participants).length, safetyNotice: event.decision.reason })
      break
    case 'error':
      setLive({ lastError: event.detail })
      break
    case 'participant_consent_changed':
      {
        const state = getLiveState().tableState
        if (state?.participants[event.participant_id] && event.state_version === undefined)
          setLive({ tableState: { ...state, participants: { ...state.participants, [event.participant_id]: { ...state.participants[event.participant_id], profile_shared: event.profile_shared } } } })
        else if (event.state_version !== undefined && state && event.state_version > state.version)
          setLive({ lastError: '收到授权变化，正在等待完整桌状态…' })
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

function openPuppet(tableId: string, participantId: string, mode: 'participant' | 'observer' = 'participant', generation = liveGeneration): Promise<WebSocket | null> {
  return new Promise((resolve) => {
    let settled = false
    let opened = false
    let socket: WebSocket
    try {
      const url = wsUrl(`/ws/tables/${encodeURIComponent(tableId)}?participant_id=${encodeURIComponent(participantId)}${mode === 'observer' ? '&viewer_mode=observer' : ''}`)
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
      closeSocket(socket)
      settle(null)
    }, 4000)
    socket.addEventListener('open', () => {
      opened = true
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
      if (!opened || runtime.intentionalCloses.has(socket) || generation !== liveGeneration) return
      if (mode === 'participant' && !runtime.viewerJoined) return
      scheduleReconnect(generation)
    })
    socket.addEventListener('error', () => settle(null))
  })
}

function scheduleReconnect(generation = liveGeneration) {
  if (generation !== liveGeneration || runtime.reconnectTimer !== null) return
  const delay = Math.min(8000, 500 * (2 ** runtime.reconnectAttempt))
  runtime.reconnectAttempt += 1
  setLive({ status: 'connecting', lastError: '实时连接中断，正在重连…' })
  const timer = window.setTimeout(async () => {
    runtime.timers.delete(timer)
    if (runtime.reconnectTimer === timer) runtime.reconnectTimer = null
    if (generation !== liveGeneration) return
    const mode = runtime.viewerJoined ? 'participant' : 'observer'
    const socket = await openPuppet(currentTableId(), VIEWER_ID, mode, generation)
    if (generation !== liveGeneration) return
    if (!socket) {
      scheduleReconnect(generation)
      return
    }
    if (mode === 'participant') runtime.viewerSocket = socket
    else runtime.observerSocket = socket
    runtime.reconnectAttempt = 0
    setLive({ status: 'live', lastError: null })
    await hydrateAfterReconnect()
  }, delay)
  runtime.reconnectTimer = timer
  runtime.timers.add(timer)
}

async function hydrateAfterReconnect() {
  try {
    const participantId = runtime.viewerJoined ? VIEWER_ID : undefined
    const state = await fetchTableState(currentTableId(), participantId)
    applyTableState(state)
    // The replay endpoint is the recovery boundary for history. The panel
    // fetches it on demand; this request warms the same server-side path after
    // a reconnect and lets a closed table restore its artifacts immediately.
    await fetchReplay(currentTableId(), participantId)
    if (state.conversation.closed && runtime.viewerJoined) await recoverCloseArtifacts(currentTableId(), VIEWER_ID)
  } catch (error) {
    setLive({ lastError: error instanceof Error ? error.message : '重连后的桌状态恢复失败' })
  }
}

function sendVia(socket: WebSocket, payload: ClientHumanMessage | { type: 'request_close' } | { type: 'request_nudge' }): boolean {
  if (socket.readyState !== WebSocket.OPEN) return false
  try {
    socket.send(JSON.stringify(payload))
    return true
  } catch {
    return false
  }
}

/** Runtime bookkeeping for the authoritative backend stream and explicit mock fallback. */
let liveGeneration = 0

function resetEventDedupe() {
  runtime.seenMessageIds.clear()
  runtime.seenActionKeys.clear()
  runtime.latestStateVersion = -1
  runtime.reconnectAttempt = 0
}

function acceptStateVersion(version: number): boolean {
  if (version <= runtime.latestStateVersion) return false
  runtime.latestStateVersion = version
  return true
}

function applyTableState(state: NonNullable<LiveStatus['tableState']>): boolean {
  if (!acceptStateVersion(state.version)) return false
  setLive({
    tableState: state,
    phase: state.phase,
    coreQuestion: state.core_question,
    subQuestion: state.current_subquestion,
    seatCount: Object.keys(state.participants).length,
    tableMode: state.conversation.mode ?? null,
  })
  return true
}

async function ensureTableInternal(tableId: string, coreQuestion: string, allowClosed: boolean): Promise<string | null> {
  let candidateTableId = tableId === DEFAULT_TABLE_ID && activeTableId !== DEFAULT_TABLE_ID ? activeTableId : tableId
  for (let attempt = 0; attempt < 2; attempt += 1) {
    const existing = await requestRaw(`/tables/${encodeURIComponent(candidateTableId)}`)
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
    if (existing.status !== 404 || import.meta.env.VITE_ALLOW_DEV_SEED !== 'true') {
      throw new BackendApiError(existing.status, existing.status === 404
        ? `找不到桌「${candidateTableId}」`
        : `桌状态请求失败（${existing.status}）`)
    }
    const created = await requestRaw('/tables', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ table_id: candidateTableId, core_question: coreQuestion, participants: actorSeeds() }),
    })
    if (created.ok || created.status === 409) {
      activeTableId = candidateTableId
      return candidateTableId
    }
    throw new BackendApiError(created.status, `创建桌失败（${created.status}）`)
  }
  return candidateTableId
}

export function ensureTable(tableId = DEFAULT_TABLE_ID, coreQuestion = DEFAULT_CORE_QUESTION, allowClosed = false): Promise<string | null> {
  const key = `${tableId}:${coreQuestion}:${allowClosed ? 'closed' : 'open'}`
  const inFlight = ensureRequests.get(key)
  if (inFlight) return inFlight
  const request = ensureTableInternal(tableId, coreQuestion, allowClosed)
  ensureRequests.set(key, request)
  void request.then(() => ensureRequests.delete(key), () => ensureRequests.delete(key))
  return request
}

export async function startLive(tableId = DEFAULT_TABLE_ID, coreQuestion = DEFAULT_CORE_QUESTION): Promise<void> {
  const generation = ++liveGeneration
  resetLive()
  resetEventDedupe()
  setLive({ status: 'connecting' })
  let readyTableId: string | null = null
  try {
    readyTableId = await ensureTable(tableId, coreQuestion, true)
  } catch (error) {
    if (generation !== liveGeneration) return
    if (error instanceof BackendApiError && error.status === 0) {
      mock.startMock()
    } else {
      setLive({ status: 'error', lastError: error instanceof Error ? error.message : '无法恢复这张桌' })
    }
    return
  }
  if (generation !== liveGeneration) return
  if (!readyTableId) {
    setLive({ status: 'error', lastError: '无法恢复这张桌' })
    return
  }
  let initialState: NonNullable<LiveStatus['tableState']>
  try {
    initialState = await fetchTableState(readyTableId)
  } catch (error) {
    if (generation !== liveGeneration) return
    if (error instanceof BackendApiError && error.status === 0) mock.startMock()
    else setLive({ status: 'error', lastError: error instanceof Error ? error.message : '无法读取这张桌的状态' })
    return
  }
  const stageSocket = await openPuppet(readyTableId, VIEWER_ID, 'observer')
  if (generation !== liveGeneration) return
  if (!stageSocket) {
    setLive({ status: 'error', lastError: '实时连接暂时没有建立，请稍后重试。' })
    return
  }
  setLive({ status: 'live', coreQuestion })
  runtime.observerSocket = stageSocket
  try {
    applyTableState(initialState)
    if (initialState.participants[VIEWER_ID]) {
      const participantSocket = await openPuppet(readyTableId, VIEWER_ID, 'participant')
      if (participantSocket && generation === liveGeneration) {
        closeSocket(runtime.observerSocket)
        runtime.observerSocket = null
        runtime.viewerJoined = true
        runtime.viewerSocket = participantSocket
        setLive({ viewerJoined: true })
      }
      if (initialState.conversation.closed) void recoverCloseArtifacts(readyTableId, VIEWER_ID)
    }
  } catch {
    // The observer stream remains authoritative if the initial REST refresh races it.
  }
}

export async function joinViewer(openingText = '', profileShared = false): Promise<{ ok: true } | { ok: false; error: string }> {
  if (runtime.viewerJoined) return { ok: true }
  if (getLiveState().status === 'mock') {
    runtime.viewerJoined = true
    setLive({ seatCount: 5, viewerJoined: true })
    if (openingText.trim()) mock.sendViewerMessage(openingText.trim())
    return { ok: true }
  }
  try {
    const response = await requestRaw(`/tables/${encodeURIComponent(currentTableId())}/participants`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(viewerSeed(openingText)),
    })
    if (!response.ok && response.status !== 409) {
      const body = await response.json().catch(() => null) as { detail?: string } | null
      return { ok: false, error: body?.detail || `入席请求失败（${response.status}）` }
    }
  } catch (error) {
    return { ok: false, error: error instanceof Error ? error.message : '后端暂时不可用' }
  }
  closeSocket(runtime.observerSocket)
  runtime.observerSocket = null
  const socket = await openPuppet(currentTableId(), VIEWER_ID, 'participant')
  if (!socket) return { ok: false, error: '实时连接暂时没有建立，请稍后重试。' }
  runtime.viewerJoined = true
  runtime.viewerSocket = socket
  setLive({ viewerJoined: true })
  try {
    applyTableState(await fetchTableState(currentTableId(), VIEWER_ID))
  } catch {
    // The participant socket remains the authoritative source if this refresh races it.
  }
  if (profileShared) {
    void setProfileConsent(currentTableId(), VIEWER_ID, true)
      .then(applyTableState)
      .catch((error) => setLive({ lastError: error instanceof Error ? error.message : '资料授权没有保存成功' }))
  }
  if (openingText.trim()) {
    sendViewerMessage(openingText.trim())
  }
  return { ok: true }
}

export function sendViewerMessage(text: string): boolean {
  const trimmed = text.trim()
  if (!trimmed) return false
  if (getLiveState().status === 'mock') {
    mock.sendViewerMessage(trimmed)
    return true
  }
  const messageId = `viewer-${Date.now()}-${++runtime.viewerMessageSeq}`
  const payload = {
    type: 'human_message' as const,
    message_id: messageId,
    participant_id: VIEWER_ID,
    text: trimmed,
    client_ts: Date.now(),
  }
  if (!runtime.viewerSocket || !sendVia(runtime.viewerSocket, payload)) {
    pushMessage({ participantId: VIEWER_ID, text: trimmed, fromHost: false, action: null, messageId, delivery: 'failed' })
    markMessageFailed(messageId)
    return false
  }
  pushMessage({ participantId: VIEWER_ID, text: trimmed, fromHost: false, action: null, messageId, delivery: 'pending' })
  return true
}

export function retryViewerMessage(messageId: string): boolean {
  const message = getLiveState().messages.find((item) => item.messageId === messageId)
  if (!message || !runtime.viewerSocket) return false
  const sent = sendVia(runtime.viewerSocket, {
    type: 'human_message',
    message_id: messageId,
    participant_id: VIEWER_ID,
    text: message.text,
    client_ts: Date.now(),
  })
  if (sent) markMessagePending(messageId)
  return sent
}

export function requestNudge(): boolean {
  if (getLiveState().status === 'mock') {
    mock.sendViewerMessage('我想听听主持人的下一步引导。')
    return true
  }
  return !!runtime.viewerSocket && sendVia(runtime.viewerSocket, { type: 'request_nudge' })
}

export function loadLobby(tableId = currentTableId()): Promise<LobbyPreviewLike> {
  return fetchLobby(tableId)
}

export function loadLobbyFit(tableId: string, participant = viewerSeed()): Promise<LobbyFitPreviewLike> {
  return previewLobbyFit(tableId, participant)
}

export function loadReplay(tableId = currentTableId(), participantId?: string): Promise<ReplayResponseLike> {
  return fetchReplay(tableId, participantId)
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
  if (runtime.reconnectTimer !== null) {
    window.clearTimeout(runtime.reconnectTimer)
    runtime.reconnectTimer = null
  }
  mock.stopMock()
  runtime.sockets.forEach((socket) => closeSocket(socket))
  runtime.sockets.clear()
  runtime.viewerSocket = null
  runtime.observerSocket = null
  runtime.viewerJoined = false
  setLive({ viewerJoined: false })
  resetEventDedupe()
}
