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
