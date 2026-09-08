import type {
  ActionEchoEntryLike,
  ActiveIntentSessionViewLike,
  LobbyFitPreviewLike,
  LobbyPreviewLike,
  ConfirmMatchRequestLike,
  CreateTableRequestLike,
  MatchPreviewRequestLike,
  MatchPlanLike,
  MatchedTableResponseLike,
  ParticipantSavedTablesLike,
  ParticipantSeedLike,
  RelationshipMemoryLike,
  ReplayResponseLike,
  SavedTableItemLike,
  TableStateLike,
  InvitationInboxResponseLike,
  InvitationResponseLike,
  JoinRequestApprovalLike,
  JoinRequestViewLike,
  StageSummaryFeedbackKindLike,
  StageSummaryFeedbackLike,
  StageSummaryLike,
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
      credentials: 'include',
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

/** Shared match adapter. The caller must render the returned plan before confirmation. */
export function previewMatch(payload: MatchPreviewRequestLike) {
  return requestJson<MatchPlanLike>('/matches/preview', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

/** Explicitly confirms a server-generated MatchPlan; this is not manual table creation. */
export function confirmMatch(payload: ConfirmMatchRequestLike) {
  return requestJson<MatchedTableResponseLike>('/matches/confirm', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export function createTable(
  coreQuestion: string,
  participants: ParticipantSeedLike[],
  tableId?: string,
  provenance: Pick<CreateTableRequestLike, 'origin_signal_ids' | 'origin_signals'> = {},
) {
  return requestJson<TableStateLike>('/tables', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      table_id: tableId,
      core_question: coreQuestion,
      participants,
      ...provenance,
    } satisfies CreateTableRequestLike),
  })
}

export function createInvitation(tableId: string, inviterId: string, candidate: ParticipantSeedLike, reason: string) {
  return requestJson<{
    invitation_id: string
    table_id: string
    participant_id: string
    display_name: string
    role: string
    reason: string
    status: 'pending' | 'accepted' | 'declined'
  }>(
    `/tables/${encodeURIComponent(tableId)}/invitations${query({ inviter_id: inviterId })}`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ candidate, reason }),
    },
  )
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

export function requestStageSummary(tableId: string, participantId: string) {
  return requestJson<{ table_id: string; accepted: boolean; state_version: number }>(
    `/tables/${encodeURIComponent(tableId)}/stage-summaries/request${query({ participant_id: participantId })}`,
    { method: 'POST' },
  )
}

export function submitStageSummaryFeedback(
  tableId: string,
  summary: StageSummaryLike,
  participantId: string,
  kind: StageSummaryFeedbackKindLike,
  note?: string,
  evidenceTurns: number[] = [],
) {
  return requestJson<StageSummaryFeedbackLike>(
    `/tables/${encodeURIComponent(tableId)}/stage-summaries/${encodeURIComponent(summary.summary_id)}/feedback${query({ participant_id: participantId, summary_revision: summary.revision })}`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ kind, note: note?.trim() || undefined, evidence_turns: evidenceTurns }),
    },
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

export function createActiveIntentSession(participantId: string, message: string, limit = 5) {
  return requestJson<ActiveIntentSessionViewLike>(
    `/participants/${encodeURIComponent(participantId)}/intent-sessions${query({ viewer_id: participantId })}`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message, limit }),
    },
  )
}

export function appendActiveIntentTurn(participantId: string, sessionId: string, message: string, replaceContext = false) {
  return requestJson<ActiveIntentSessionViewLike>(
    `/participants/${encodeURIComponent(participantId)}/intent-sessions/${encodeURIComponent(sessionId)}/turns${query({ viewer_id: participantId })}`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message, replace_context: replaceContext }),
    },
  )
}

export function fetchActiveIntentSourcePreview(participantId: string, sessionId: string, tableSize = 4, limit = 20) {
  return requestJson<MatchPlanLike>(
    `/participants/${encodeURIComponent(participantId)}/intent-sessions/${encodeURIComponent(sessionId)}/source-preview${query({ viewer_id: participantId })}`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ table_size: tableSize, limit }),
    },
  )
}

export function confirmSourceMatch(previewToken: string, tableId?: string) {
  return requestJson<MatchedTableResponseLike>('/matches/source-confirm', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ preview_token: previewToken, table_id: tableId }),
  })
}

export function fetchRelationshipMemory(participantId: string) {
  return requestJson<RelationshipMemoryLike[]>(
    `/participants/${encodeURIComponent(participantId)}/relationship-memory${query({ viewer_id: participantId })}`,
  )
}

export function fetchActionEchoes(participantId: string) {
  return requestJson<ActionEchoEntryLike[]>(
    `/participants/${encodeURIComponent(participantId)}/action-echoes${query({ viewer_id: participantId })}`,
  )
}

export function fetchSavedTables(participantId: string) {
  return requestJson<ParticipantSavedTablesLike>(
    `/participants/${encodeURIComponent(participantId)}/saved-tables${query({ viewer_id: participantId })}`,
  )
}

export function fetchInvitationInbox(participantId: string) {
  return requestJson<InvitationInboxResponseLike>(
    `/participants/${encodeURIComponent(participantId)}/invitations${query({ viewer_id: participantId })}`,
  )
}

export function respondInvitation(tableId: string, invitationId: string, participantId: string, accept: boolean) {
  return requestJson<InvitationResponseLike>(
    `/tables/${encodeURIComponent(tableId)}/invitations/${encodeURIComponent(invitationId)}/respond${query({ participant_id: participantId })}`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ accept }),
    },
  )
}

export function saveTableForLater(participantId: string, tableId: string) {
  return requestJson<SavedTableItemLike>(
    `/participants/${encodeURIComponent(participantId)}/saved-tables/${encodeURIComponent(tableId)}${query({ viewer_id: participantId })}`,
    { method: 'PUT' },
  )
}

export function removeSavedTable(participantId: string, tableId: string) {
  return requestRaw(
    `/participants/${encodeURIComponent(participantId)}/saved-tables/${encodeURIComponent(tableId)}${query({ viewer_id: participantId })}`,
    { method: 'DELETE' },
  ).then((response) => {
    if (!response.ok) throw new BackendApiError(response.status)
  })
}

export function createJoinRequest(tableId: string, participant: ParticipantSeedLike, message?: string) {
  const requestId = `${tableId}:join:${participant.participant_id}`
  return requestJson<JoinRequestViewLike>(
    `/tables/${encodeURIComponent(tableId)}/join-requests${query({ participant_id: participant.participant_id })}`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ request_id: requestId, candidate: participant, message }),
    },
  )
}

export function fetchJoinRequests(tableId: string, participantId: string) {
  return requestJson<JoinRequestViewLike[]>(
    `/tables/${encodeURIComponent(tableId)}/join-requests${query({ participant_id: participantId })}`,
  )
}

export function approveJoinRequest(tableId: string, requestId: string, participantId: string, reason: string) {
  return requestJson<JoinRequestApprovalLike>(
    `/tables/${encodeURIComponent(tableId)}/join-requests/${encodeURIComponent(requestId)}/approve${query({ participant_id: participantId })}`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ reason }),
    },
  )
}

export function declineJoinRequest(tableId: string, requestId: string, participantId: string) {
  return requestJson<JoinRequestViewLike>(
    `/tables/${encodeURIComponent(tableId)}/join-requests/${encodeURIComponent(requestId)}/decline${query({ participant_id: participantId })}`,
    { method: 'POST' },
  )
}

export function saveRelationship(tableId: string, relatedParticipantId: string, participantId: string) {
  return requestJson<{ event_id: string; event_type: string }>(
    `/tables/${encodeURIComponent(tableId)}/relationships/${encodeURIComponent(relatedParticipantId)}/save${query({ participant_id: participantId })}`,
    { method: 'POST' },
  )
}
