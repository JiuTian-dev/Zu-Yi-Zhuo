import type { HomeToMatchContextLike, MatchToHomeDraftLike, OpenTableContextLike } from './contract'

export const HOME_TO_MATCH_CONTEXT_EVENT = 'zuoyizhuo:home-to-match-context'
const HOME_TO_MATCH_CONTEXT_KEY = 'zuoyizhuo:home-to-match-context'
export const OPEN_TABLE_CONTEXT_EVENT = 'zuoyizhuo:open-table-context'
const OPEN_TABLE_CONTEXT_KEY = 'zuoyizhuo:open-table-context'

/**
 * PRODUCT HANDOFF — matching page -> teammate-owned homepage.
 *
 * This boundary carries a draft only. It never creates a table and never
 * writes participant state. The homepage may listen for this event or read
 * the short-lived session value when the two shells are merged.
 */
export const MATCH_TO_HOME_DRAFT_EVENT = 'zuoyizhuo:match-to-home-draft'
const MATCH_TO_HOME_DRAFT_KEY = 'zuoyizhuo:match-to-home-draft'

const HOME_SOURCES = new Set<HomeToMatchContextLike['source']>([
  'home_recommendation',
  'home_intent',
  'home_invitation',
  'home_return',
])

/** Validate the small, non-sensitive payload shared by the teammate homepage. */
export function normalizeHomeToMatchContext(value: unknown): HomeToMatchContextLike | null {
  if (!value || typeof value !== 'object') return null
  const candidate = value as Record<string, unknown>
  if (typeof candidate.source !== 'string' || !HOME_SOURCES.has(candidate.source as HomeToMatchContextLike['source'])) return null
  const initialQuestion = typeof candidate.initial_question === 'string' ? candidate.initial_question.trim().slice(0, 1000) : undefined
  const recommendedTableId = typeof candidate.recommended_table_id === 'string' ? candidate.recommended_table_id.trim().slice(0, 160) : undefined
  const returnToHome = typeof candidate.return_to_home === 'string' ? candidate.return_to_home.trim().slice(0, 500) : undefined
  return {
    source: candidate.source as HomeToMatchContextLike['source'],
    ...(initialQuestion ? { initial_question: initialQuestion } : {}),
    ...(recommendedTableId ? { recommended_table_id: recommendedTableId } : {}),
    ...(returnToHome ? { return_to_home: returnToHome } : {}),
  }
}

/** The homepage may use this for same-shell or cross-shell navigation. */
export function handoffHomeContext(context: HomeToMatchContextLike): boolean {
  const normalized = normalizeHomeToMatchContext(context)
  if (!normalized) return false
  let persisted = true
  try {
    sessionStorage.setItem(HOME_TO_MATCH_CONTEXT_KEY, JSON.stringify(normalized))
  } catch {
    persisted = false
  }
  let dispatched = false
  try {
    window.dispatchEvent(new CustomEvent<HomeToMatchContextLike>(HOME_TO_MATCH_CONTEXT_EVENT, { detail: normalized }))
    dispatched = true
  } catch {
    // A cross-shell handoff can still be recovered from sessionStorage.
  }
  return dispatched || persisted
}

export function readHomeContext(): HomeToMatchContextLike | null {
  try {
    return normalizeHomeToMatchContext(JSON.parse(sessionStorage.getItem(HOME_TO_MATCH_CONTEXT_KEY) ?? 'null'))
  } catch {
    return null
  }
}

export function clearHomeContext() {
  try {
    sessionStorage.removeItem(HOME_TO_MATCH_CONTEXT_KEY)
  } catch {
    // Storage may be unavailable in a privacy-restricted browser. The event
    // path remains usable for a same-shell homepage.
  }
}

const TABLE_SOURCES = new Set<OpenTableContextLike['source']>(['match', 'home_create', 'invitation'])

export function normalizeOpenTableContext(value: unknown): OpenTableContextLike | null {
  if (!value || typeof value !== 'object') return null
  const candidate = value as Record<string, unknown>
  const tableId = typeof candidate.table_id === 'string' ? candidate.table_id.trim().slice(0, 160) : ''
  const source = candidate.source as OpenTableContextLike['source']
  const intent = candidate.intent as OpenTableContextLike['intent']
  if (!tableId || !TABLE_SOURCES.has(source) || (intent !== 'listen' && intent !== 'join')) return null
  return { table_id: tableId, source, intent }
}

/** The homepage or invitation inbox uses this to enter the shared Lobby. */
export function handoffOpenTable(context: OpenTableContextLike): boolean {
  const normalized = normalizeOpenTableContext(context)
  if (!normalized) return false
  let persisted = true
  try {
    sessionStorage.setItem(OPEN_TABLE_CONTEXT_KEY, JSON.stringify(normalized))
  } catch {
    persisted = false
  }
  let dispatched = false
  try {
    window.dispatchEvent(new CustomEvent<OpenTableContextLike>(OPEN_TABLE_CONTEXT_EVENT, { detail: normalized }))
    dispatched = true
  } catch {
    // A cross-shell handoff can still be recovered from sessionStorage.
  }
  return dispatched || persisted
}

export function readOpenTableContext(): OpenTableContextLike | null {
  try {
    return normalizeOpenTableContext(JSON.parse(sessionStorage.getItem(OPEN_TABLE_CONTEXT_KEY) ?? 'null'))
  } catch {
    return null
  }
}

export function clearOpenTableContext() {
  try {
    sessionStorage.removeItem(OPEN_TABLE_CONTEXT_KEY)
  } catch {
    // The same-shell event path does not depend on storage availability.
  }
}

export function handoffMatchDraft(draft: MatchToHomeDraftLike): boolean {
  let persisted = true
  try {
    sessionStorage.setItem(MATCH_TO_HOME_DRAFT_KEY, JSON.stringify(draft))
  } catch {
    persisted = false
  }
  let dispatched = false
  try {
    window.dispatchEvent(new CustomEvent<MatchToHomeDraftLike>(MATCH_TO_HOME_DRAFT_EVENT, { detail: draft }))
    dispatched = true
  } catch {
    // A cross-shell handoff can still be recovered from sessionStorage.
  }
  return dispatched || persisted
}

export function readMatchDraft(): MatchToHomeDraftLike | null {
  try {
    const value = JSON.parse(sessionStorage.getItem(MATCH_TO_HOME_DRAFT_KEY) ?? 'null') as MatchToHomeDraftLike | null
    return value?.kind === 'manual_create_draft' && Boolean(value.normalized_question) ? value : null
  } catch {
    return null
  }
}

export function clearMatchDraft() {
  sessionStorage.removeItem(MATCH_TO_HOME_DRAFT_KEY)
}
