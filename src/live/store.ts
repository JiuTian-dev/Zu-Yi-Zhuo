import { useSyncExternalStore } from 'react'
import type { AgentActionName, SharedBaselineLike, PersonalCardLike, TablePhase } from './contract'

export interface LiveMessage {
  participantId: string
  text: string
  fromHost: boolean
  action: AgentActionName | null
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
  closeState: 'idle' | 'started' | 'ready'
  baseline: SharedBaselineLike | null
  personalCard: PersonalCardLike | null
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
  closeState: 'idle',
  baseline: null,
  personalCard: null,
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
  const next = [...state.messages, message].slice(-30)
  setLive({ messages: next, speakingId: message.participantId })
}
