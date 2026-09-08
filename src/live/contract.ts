/** Mirrors backend Conversation Orchestrator contracts (specs/conversation-orchestrator.md). */

export type AgentActionName = 'SILENCE' | 'PASS' | 'PROBE' | 'REFRAME' | 'GROUND' | 'CLOSE'
export type TablePhase = 'opening' | 'explore' | 'tension' | 'deepen' | 'close'
export type StageSummaryTriggerLike = 'question_aligned' | 'disagreement_changed' | 'grounding_changed' | 'thread_advanced' | 'stalled' | 'manual' | 'pre_close'
export type StageSummaryFeedbackKindLike = 'misrepresented' | 'missing_point' | 'not_consensus' | 'ready_to_advance'

export interface EvidenceStatementLike {
  text: string
  evidence_turns: number[]
}

export type StateLevelLike = 'high' | 'medium' | 'low'
export type SafetyLevelLike = 'normal' | 'elevated' | 'critical'
export type InvitationPreferenceLike = 'many' | 'few' | 'none'

export interface RelevantExperienceLike {
  text: string
  source_ref: string
}

export interface DisagreementLike extends EvidenceStatementLike {
  disagreement_type: string
  participant_ids: string[]
}

export interface OpenLoopLike {
  question: string
  priority: StateLevelLike
  evidence_turns: number[]
}

export interface ParticipantStateLike {
  participant_id: string
  display_name: string
  role: string
  roundtable_invite_preference: InvitationPreferenceLike
  profile_shared: boolean
  declared_position: string | null
  current_position: EvidenceStatementLike | null
  key_contributions: EvidenceStatementLike[]
  unused_relevant_experience: RelevantExperienceLike[]
  engagement: StateLevelLike
  last_spoke_turn: number | null
  good_pass_opportunity: boolean
}

export interface ConversationStateLike {
  state: string
  most_promising_thread: EvidenceStatementLike | null
  risk_flags: EvidenceStatementLike[]
  safety_level: SafetyLevelLike
  mode: 'async' | 'sync'
  sync_expires_at?: number
  closed: boolean
  soft_expired: boolean
  soft_expiry_reason?: string | null
}

export interface InterventionStateLike {
  reasons_to_speak: EvidenceStatementLike[]
  reasons_to_stay_silent: EvidenceStatementLike[]
  recommended_action: AgentActionName
  confidence: number
  last_action: AgentActionName
  last_agent_turn_id: string | null
  human_turns_since_last_intervention: number
}

export interface AgentPresenceLike {
  agent_id: string
  display_name: string
  role: string
  status: 'active' | 'paused' | 'closed'
}

export interface TableStateLike {
  table_id: string
  origin_table_id?: string | null
  origin_signal_ids?: string[]
  version: number
  core_question: string
  current_subquestion: string | null
  phase: TablePhase
  momentum: StateLevelLike
  close_readiness: StateLevelLike
  new_insights: EvidenceStatementLike[]
  consensus: EvidenceStatementLike[]
  disagreements: DisagreementLike[]
  open_loops: OpenLoopLike[]
  participants: Record<string, ParticipantStateLike>
  conversation: ConversationStateLike
  intervention: InterventionStateLike
  agent: AgentPresenceLike
  latest_stage_summary_id?: string | null
  latest_stage_summary_revision?: number | null
}

export interface StageSummaryLike {
  summary_id: string
  table_id: string
  revision: number
  status: 'published' | 'superseded'
  input_state_version: number
  published_state_version: number
  phase: TablePhase
  trigger: StageSummaryTriggerLike
  covered_turn_start: number
  covered_turn_end: number
  clarified: EvidenceStatementLike[]
  disagreements: DisagreementLike[]
  missing: EvidenceStatementLike[]
  next_focus: EvidenceStatementLike | null
  created_at: number
  model: string
  used_fallback: boolean
}

export interface StageSummaryFeedbackLike {
  feedback_id: string
  table_id: string
  summary_id: string
  summary_revision: number
  participant_id: string
  kind: StageSummaryFeedbackKindLike
  note: string | null
  evidence_turns: number[]
  status: 'open' | 'applied' | 'dismissed'
  created_at: number
}

export interface ServerMessageCommitted {
  type: 'message_committed'
  message: { message_id: string; participant_id: string; text: string; client_ts: unknown; turn_id?: number }
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

export interface ServerStageSummaryRequested {
  type: 'stage_summary_requested'
  table_id: string
  state_version: number
  request_id?: string
}

export interface ServerStageSummaryStarted {
  type: 'stage_summary_started'
  table_id: string
  input_state_version: number
  trigger: StageSummaryTriggerLike
}

export interface ServerStageSummaryPublished {
  type: 'stage_summary_published'
  summary: StageSummaryLike
}

export interface ServerStageSummaryFailed {
  type: 'stage_summary_failed'
  table_id: string
  input_state_version: number
  code: string
  detail: string
}

export interface ServerStageSummaryFeedback {
  type: 'stage_summary_feedback'
  feedback: StageSummaryFeedbackLike
}

export interface GroundingCardLike {
  title: string
  excerpt: string
  source_ref: string
  signal_id?: string
}

export type ServerEvent =
  | ServerMessageCommitted
  | ServerAgentAction
  | ServerStateChanged
  | ServerCloseStarted
  | ServerCloseReady
  | ServerStageSummaryRequested
  | ServerStageSummaryStarted
  | ServerStageSummaryPublished
  | ServerStageSummaryFailed
  | ServerStageSummaryFeedback
  | { type: 'grounding_card'; table_id: string; state_version: number; title: string; excerpt: string; source_ref: string; signal_id?: string }
  | { type: 'intervention_reflected'; record: ReplayInterventionLike }
  | { type: 'participant_added' | 'participant_left'; participant_id: string; state?: TableStateLike }
  | { type: 'table_mode_changed'; mode: 'async' | 'sync'; reason: string; state_version: number }
  | { type: 'table_closed'; state_version: number }
  | { type: 'safety_private_reminder'; participant_id: string; strike_count: number; text: string }
  | { type: 'safety_soft_intervention'; text: string; state_version: number }
  | { type: 'error'; code: string; detail: string; message_id?: string }
  | { type: 'safety_enforced'; decision: { reason: string }; state: TableStateLike }
  | { type: 'participant_consent_changed'; participant_id: string; profile_shared: boolean; state_version?: number }

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

export interface ClientRequestStageSummary {
  type: 'request_stage_summary'
  request_id?: string
}

/** Public REST projections used by the entry, lobby and replay surfaces. */
export interface ParticipantSeedLike {
  participant_id: string
  display_name: string
  role: string
  declared_position: string
  relevant_experience: { text: string; source_ref: string }[]
  roundtable_invite_preference?: 'many' | 'few' | 'none'
  public_signal_ids?: string[]
}

export interface PublicContentSignalLike {
  signal_id: string
  content_type: 'question' | 'answer' | 'article'
  title: string
  excerpt: string
  source_ref: string
  author_id: string
  author_name: string
  author_role?: string | null
  public_stance?: string | null
  engagement?: number
  visibility: 'public'
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

export type ActiveIntentRouteLike = 'clarify' | 'join_existing' | 'new_table'

export interface ActiveIntentTableCandidateLike {
  table_id: string
  core_question: string
  current_subquestion: string | null
  mode: 'async' | 'sync'
  participant_count: number
  available_seats: number
  reason: string
  origin_signal_ids?: string[]
  lobby?: LobbyPreviewLike | null
}

export interface ActiveIntentPreviewLike {
  normalized_question: string
  route: ActiveIntentRouteLike
  clarifying_question?: string | null
  candidates: ActiveIntentTableCandidateLike[]
}

export interface ActiveIntentSessionViewLike {
  session_id: string
  participant_id: string
  status: 'clarifying' | 'ready' | 'exhausted'
  messages: string[]
  turn_count: number
  max_turns: number
  remaining_turns: number
  preview: ActiveIntentPreviewLike
}

/** Cross-page handoff contracts. The homepage owns creation; this workline only emits a draft. */
export interface HomeToMatchContextLike {
  source: 'home_recommendation' | 'home_intent' | 'home_invitation' | 'home_return'
  initial_question?: string
  recommended_table_id?: string
  return_to_home?: string
}

export interface MatchToHomeDraftLike {
  kind: 'manual_create_draft'
  normalized_question: string
  clarification_messages: string[]
  no_match_reason: string
  source_session_id?: string
}

export interface OpenTableContextLike {
  table_id: string
  source: 'match' | 'home_create' | 'invitation'
  intent: 'listen' | 'join'
}

export interface MatchSeatLike {
  participant_id: string
  display_name: string
  role: string
}

export interface MatchReasonLike {
  participant_id: string
  reason: string
  evidence_terms: string[]
  evidence_signal_ids?: string[]
}

export interface MatchPlanLike {
  core_question: string
  selected: MatchSeatLike[]
  reasons: MatchReasonLike[]
  unmatched_participant_ids: string[]
  preview_token?: string | null
}

export interface MatchPreviewRequestLike {
  core_question: string
  candidates: ParticipantSeedLike[]
  table_size?: number
}

export interface ConfirmMatchRequestLike extends MatchPreviewRequestLike {
  table_id?: string
  origin_signal_ids?: string[]
  origin_signals?: PublicContentSignalLike[]
}

export interface CreateTableRequestLike {
  table_id?: string
  core_question: string
  participants: ParticipantSeedLike[]
  origin_signal_ids?: string[]
  origin_signals?: PublicContentSignalLike[]
}

export interface MatchedTableResponseLike {
  plan: MatchPlanLike
  state: TableStateLike
}

export interface RelationshipMemoryLike {
  table_id: string
  state_version: number
  core_question: string
  participant_id: string
  display_name: string
  reason: string
  evidence_turns: number[]
}

export interface ActionEchoEntryLike {
  table_id: string
  state_version: number
  core_question: string
  follow_up_index: number
  item_type: 'suggestion' | 'commitment'
  text: string
  evidence_turns: number[]
  status?: 'completed' | 'in_progress' | 'blocked' | 'dismissed' | null
  note?: string | null
}

export interface SavedTableItemLike {
  table_id: string
  lobby: LobbyPreviewLike
}

export interface ParticipantSavedTablesLike {
  participant_id: string
  total: number
  offset: number
  limit: number
  items: SavedTableItemLike[]
}

export type InvitationStatusLike = 'pending' | 'accepted' | 'declined'

export interface InvitationViewLike {
  invitation_id: string
  table_id: string
  participant_id: string
  display_name: string
  role: string
  reason: string
  status: InvitationStatusLike
}

export interface InvitationInboxItemLike {
  invitation: InvitationViewLike
  table: LobbyPreviewLike
  can_respond: boolean
  unavailable_reason?: string | null
}

export interface InvitationInboxResponseLike {
  participant_id: string
  items: InvitationInboxItemLike[]
  total: number
  offset: number
  limit: number
}

export interface InvitationResponseLike {
  invitation: InvitationViewLike
  state: TableStateLike | null
}

export interface JoinRequestViewLike {
  request_id: string
  table_id: string
  participant_id: string
  display_name: string
  role: string
  message?: string | null
  status: 'pending' | 'invited' | 'declined'
  invitation_id?: string | null
}

export interface JoinRequestApprovalLike {
  request: JoinRequestViewLike
  invitation: InvitationViewLike
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
  visual_hint: Record<string, unknown>
  evidence_turns: number[]
  state_version: number
  confidence: number
  reasons_to_speak: EvidenceStatementLike[]
  reasons_to_stay_silent: EvidenceStatementLike[]
  latency_ms: number
  model: string
  token_usage: { input_tokens: number; output_tokens: number }
  grounding_card?: GroundingCardLike
  outcome: EvidenceStatementLike | null
  reflection: EvidenceStatementLike | null
  reflection_effective?: boolean | null
}

export interface ReplaySourceSignalLike extends PublicContentSignalLike {}

/** `/replay.snapshots` contains privacy-projected full TableState snapshots. */
export interface ReplaySnapshotLike extends TableStateLike {}

export interface ReplayResponseLike {
  table_id: string
  messages: ReplayMessageLike[]
  snapshots: ReplaySnapshotLike[]
  interventions: ReplayInterventionLike[]
  comments: unknown[]
  comment_promotions: unknown[]
  source_signals: ReplaySourceSignalLike[]
  stage_summaries: StageSummaryLike[]
  summary_feedback: StageSummaryFeedbackLike[]
}

export interface InterventionReflectionLike {
  text: string
  evidence_turns: number[]
}
