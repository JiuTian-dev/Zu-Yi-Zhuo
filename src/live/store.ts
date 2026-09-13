import { useSyncExternalStore } from 'react'
import type { AgentActionName, SharedBaselineLike, PersonalCardLike, TablePhase, TableStateLike, GroundingCardLike, InterventionReflectionLike, StageSummaryLike, StageSummaryFeedbackLike, ParticipantResponseStatusLike } from './contract'

export interface LiveMessage {
  participantId: string
  text: string
  turnId?: number
  fromHost: boolean
  action: AgentActionName | null
  messageId?: string
  delivery?: 'pending' | 'committed' | 'failed'
  source?: 'human' | 'simulated'
  stateVersion?: number
}

export interface LiveStatus {
  status: 'idle' | 'connecting' | 'live' | 'mock' | 'error'
  phase: TablePhase | 'opening'
  coreQuestion: string | null
  subQuestion: string | null
  messages: LiveMessage[]
  speakingId: string | null
  hostAction: { action: AgentActionName; text: string | null; target: string | null } | null
  seatCount: number
  viewerJoined: boolean
  closeState: 'idle' | 'started' | 'ready'
  baseline: SharedBaselineLike | null
  personalCard: PersonalCardLike | null
  tableState: TableStateLike | null
  groundingCard: GroundingCardLike | null
  safetyNotice: string | null
  tableMode: 'async' | 'sync' | null
  latestReflection: InterventionReflectionLike | null
  latestSummary: StageSummaryLike | null
  summaryHistory: StageSummaryLike[]
  summaryFeedback: StageSummaryFeedbackLike[]
  summaryStatus: 'idle' | 'requested' | 'running' | 'failed'
  lastError: string | null
  responses: Record<string, ParticipantResponseStatusLike>
}

const initial: LiveStatus = {
  status: 'idle',
  phase: 'opening',
  coreQuestion: null,
  subQuestion: null,
  messages: [],
  speakingId: null,
  hostAction: null,
  seatCount: 4,
  viewerJoined: false,
  closeState: 'idle',
  baseline: null,
  personalCard: null,
  tableState: null,
  groundingCard: null,
  safetyNotice: null,
  tableMode: null,
  latestReflection: null,
  latestSummary: null,
  summaryHistory: [],
  summaryFeedback: [],
  summaryStatus: 'idle',
  lastError: null,
  responses: {},
}

let state: LiveStatus = initial
const listeners = new Set<() => void>()

export function getLiveState(): LiveStatus {
  return state
}

export function setLive(partial: Partial<LiveStatus>) {
  state = { ...state, ...partial }
  listeners.forEach((notify) => notify())
}

export function resetLive() {
  state = { ...initial, status: 'idle' }
  listeners.forEach((notify) => notify())
}

export function subscribeLive(notify: () => void): () => void {
  listeners.add(notify)
  return () => listeners.delete(notify)
}

export function useLive<T>(selector: (state: LiveStatus) => T): T {
  return useSyncExternalStore(subscribeLive, () => selector(state))
}

export function pushMessage(message: LiveMessage) {
  const next = [...state.messages, message].slice(-120)
  setLive({ messages: next, speakingId: message.participantId })
}

export function commitMessage(messageId: string, message: Omit<LiveMessage, 'messageId' | 'delivery'>) {
  const next = state.messages.filter((item) => item.messageId !== messageId)
  next.push({ ...message, messageId, delivery: 'committed' })
  setLive({ messages: next.slice(-120), speakingId: message.participantId })
}

export function markMessageFailed(messageId: string) {
  const next = state.messages.map((item) => item.messageId === messageId
    ? { ...item, delivery: 'failed' as const }
    : item)
  setLive({ messages: next })
}

export function markMessagePending(messageId: string) {
  const next = state.messages.map((item) => item.messageId === messageId
    ? { ...item, delivery: 'pending' as const }
    : item)
  setLive({ messages: next })
}
