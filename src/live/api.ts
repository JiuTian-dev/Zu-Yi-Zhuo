import type {
  LobbyFitPreviewLike,
  LobbyPreviewLike,
  ParticipantSeedLike,
  ReplayResponseLike,
  TableStateLike,
} from './contract'

const API_TIMEOUT_MS = 4500
const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? '').replace(/\/+$/, '')

export function apiUrl(path: string): string {
  return `${API_BASE_URL}${path}`
}

export function wsUrl(path: string): string {
  const configured = (import.meta.env.VITE_WS_BASE_URL ?? '').replace(/\/+$/, '')
  if (configured) return `${configured}${path}`
  const scheme = location.protocol === 'https:' ? 'wss' : 'ws'
  return `${scheme}://${location.host}${path}`
}

export class BackendApiError extends Error {
  readonly status: number

  constructor(status: number, message = status === 0 ? '后端暂时不可用' : `请求失败（${status}）`) {
    super(message)
    this.name = 'BackendApiError'
    this.status = status
  }
}

export async function requestRaw(path: string, init?: RequestInit, timeoutMs = API_TIMEOUT_MS): Promise<Response> {
  const controller = new AbortController()
  const timer = window.setTimeout(() => controller.abort(), timeoutMs)
  try {
    return await fetch(apiUrl(path), {
      ...init,
      headers: { Accept: 'application/json', ...(init?.headers ?? {}) },
      signal: controller.signal,
    })
  } catch (error) {
    if (error instanceof BackendApiError) throw error
    throw new BackendApiError(0)
  } finally {
    window.clearTimeout(timer)
  }
}

async function requestJson<T>(path: string, init?: RequestInit, timeoutMs = API_TIMEOUT_MS): Promise<T> {
  try {
    const response = await requestRaw(path, init, timeoutMs)
    if (!response.ok) {
      const body = await response.json().catch(() => null) as { detail?: string } | null
      throw new BackendApiError(response.status, body?.detail || undefined)
    }
    return await response.json() as T
  } catch (error) {
    if (error instanceof BackendApiError) throw error
    throw new BackendApiError(0)
  }
}

function query(params: Record<string, string | number | undefined>) {
  const search = new URLSearchParams()
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined) search.set(key, String(value))
  })
  const suffix = search.toString()
  return suffix ? `?${suffix}` : ''
}

export function fetchDiscovery(limit = 20) {
  return requestJson<LobbyPreviewLike[]>(`/tables/discovery?limit=${limit}`)
}

export function fetchLobby(tableId: string) {
  return requestJson<LobbyPreviewLike>(`/tables/${encodeURIComponent(tableId)}/lobby`)
}

export function fetchTableState(tableId: string, participantId?: string) {
  return requestJson<TableStateLike>(
    `/tables/${encodeURIComponent(tableId)}${query({ participant_id: participantId })}`,
  )
}

export function selectTable(tableId: string, participantId: string) {
  return requestJson<{ event_id: string; event_type: string }>(
    `/tables/${encodeURIComponent(tableId)}/select${query({ participant_id: participantId })}`,
    { method: 'POST' },
  )
}

export function previewLobbyFit(tableId: string, participant: ParticipantSeedLike) {
  return requestJson<LobbyFitPreviewLike>(
    `/tables/${encodeURIComponent(tableId)}/lobby-fit${query({ participant_id: participant.participant_id })}`,
    { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(participant) },
  )
}

export function createTable(tableId: string, coreQuestion: string, participants: ParticipantSeedLike[]) {
  return requestJson<TableStateLike>('/tables', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ table_id: tableId, core_question: coreQuestion, participants }),
  })
}

export function addParticipant(tableId: string, participant: ParticipantSeedLike, inviterId?: string) {
  return requestJson<TableStateLike>(
    `/tables/${encodeURIComponent(tableId)}/participants${query({ inviter_id: inviterId })}`,
    { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(participant) },
  )
}

export function setProfileConsent(tableId: string, participantId: string, profileShared: boolean) {
  return requestJson<TableStateLike>(
    `/tables/${encodeURIComponent(tableId)}/participants/${encodeURIComponent(participantId)}/consent${query({ viewer_id: participantId })}`,
    { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ profile_shared: profileShared }) },
  )
}

export function leaveTable(tableId: string, participantId: string) {
  return requestJson<TableStateLike>(
    `/tables/${encodeURIComponent(tableId)}/participants/${encodeURIComponent(participantId)}/leave${query({ viewer_id: participantId })}`,
    { method: 'POST' },
  )
}

export function fetchReplay(tableId: string, participantId?: string) {
  return requestJson<ReplayResponseLike>(
    `/tables/${encodeURIComponent(tableId)}/replay${query({ participant_id: participantId })}`,
  )
}

export function fetchCloseArtifacts(tableId: string, participantId: string) {
  return requestJson<{
    table_id: string
    state_version: number
    shared_baseline: unknown
    personal_card: unknown
  }>(`/tables/${encodeURIComponent(tableId)}/close-artifacts${query({ participant_id: participantId })}`)
}
