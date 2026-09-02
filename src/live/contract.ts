/** Mirrors backend Conversation Orchestrator contracts (specs/conversation-orchestrator.md). */

export type AgentActionName = 'SILENCE' | 'PASS' | 'PROBE' | 'REFRAME' | 'GROUND' | 'CLOSE'
export type TablePhase = 'opening' | 'explore' | 'tension' | 'deepen' | 'close'

export interface EvidenceStatementLike {
  text: string
  evidence_turns: number[]
}

export interface ParticipantStateLike {
  participant_id: string
  display_name: string
  role: string
  profile_shared: boolean
  engagement: string
  last_spoke_turn: number | null
}

export interface TableStateLike {
  table_id: string
  version: number
  core_question: string
  current_subquestion: string | null
  phase: TablePhase
  momentum: string
  close_readiness: string
  new_insights: EvidenceStatementLike[]
  consensus: EvidenceStatementLike[]
  disagreements: { text: string; disagreement_type: string; participant_ids: string[] }[]
  open_loops: { question: string; priority: string }[]
  participants: Record<string, ParticipantStateLike>
  conversation: { state: string; closed: boolean; safety_level: string }
}

export interface ServerMessageCommitted {
  type: 'message_committed'
  message: { message_id: string; participant_id: string; text: string; client_ts: unknown }
}

export interface ServerAgentAction {
  type: 'agent_action'
  action: AgentActionName
  target_participant_id: string | null
  text: string | null
  visual_hint: Record<string, unknown>
  evidence_turns: number[]
  state_version: number
  confidence: number
}

export interface ServerStateChanged {
  type: 'table_state_changed'
  phase: TablePhase
  momentum: string
  close_readiness: string
  state: TableStateLike
}

export interface ServerCloseStarted {
  type: 'close_started'
  table_id: string
  state_version: number
  reason: string
}

export interface SharedBaselineLike {
  core_question_before: string
  key_consensus: EvidenceStatementLike[]
  unresolved_disagreements: { text: string; disagreement_type: string }[]
  evolved_question: EvidenceStatementLike
  collective_next_steps: { item_type: string; text: string; is_commitment: boolean; owner_participant_id: string | null }[]
}

export interface PersonalCardLike {
  what_changed: EvidenceStatementLike[]
  your_contribution: EvidenceStatementLike[]
  worth_continuing_with: { participant_id: string; reason: string }[]
  suggested_next_actions: { item_type: string; text: string; is_commitment: boolean }[]
}

export interface ServerCloseReady {
  type: 'close_artifact_ready'
  table_id: string
  state_version: number
  shared_baseline: SharedBaselineLike
  personal_card: PersonalCardLike
}

export type ServerEvent =
  | ServerMessageCommitted
  | ServerAgentAction
  | ServerStateChanged
  | ServerCloseStarted
  | ServerCloseReady
  | { type: 'error'; code: string; detail: string }
  | { type: 'safety_enforced'; decision: { reason: string }; state: TableStateLike }
  | { type: 'participant_consent_changed'; participant_id: string; profile_shared: boolean }

export interface ClientHumanMessage {
  type: 'human_message'
  message_id: string
  participant_id: string
  text: string
  client_ts: number
}

export interface ClientRequestClose {
  type: 'request_close'
}

/** Public REST projections used by the entry, lobby and replay surfaces. */
export interface ParticipantSeedLike {
  participant_id: string
  display_name: string
  role: string
  declared_position: string
  relevant_experience: { text: string; source_ref: string }[]
  roundtable_invite_preference?: 'many' | 'few' | 'none'
}

export interface LobbyMemberLike {
  participant_id: string
  display_name: string
  role: string
}

export interface LobbyPreviewLike {
  table_id: string
  core_question: string
  current_subquestion: string | null
  phase: TablePhase
  mode: 'async' | 'sync'
  sync_expires_at?: number
  status: 'open' | 'soft_expired' | 'closed'
  state_version: number
  participant_count: number
  available_seats: number
  members: LobbyMemberLike[]
  role_gaps: string[]
  missing_perspective: string
  origin_signal_ids?: string[]
}

export interface LobbyFitPreviewLike {
  table_id: string
  participant_id: string
  eligible: boolean
  matched_role_gap: string | null
  reason: string
}

export interface ReplayMessageLike {
  turn_id: number
  participant_id: string
  text: string
  message_id?: string
  source_comment_id?: string
}

export interface ReplayInterventionLike {
  intervention_id: string
  action: AgentActionName
  target_participant_id: string | null
  text: string | null
  evidence_turns: number[]
  state_version: number
  confidence: number
  grounding_card?: { title: string; excerpt: string; source_ref: string; signal_id?: string }
  reflection?: { text: string; evidence_turns: number[] }
}

export interface ReplaySnapshotLike {
  version: number
  phase: TablePhase
  current_subquestion: string | null
  momentum: string
  close_readiness: string
}

export interface ReplayResponseLike {
  table_id: string
  messages: ReplayMessageLike[]
  snapshots: ReplaySnapshotLike[]
  interventions: ReplayInterventionLike[]
  comments: unknown[]
  comment_promotions: unknown[]
  source_signals: unknown[]
}
