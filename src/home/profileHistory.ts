/** @origin HOME — demo/real history helpers for personal center lists. */

import { fetchSavedTables } from '../live/api'
import type { LobbyPreviewLike, SavedTableItemLike } from '../live/contract'
import { VIEWER_ID } from '../live/identity'

export type HistorySource = 'live' | 'demo'

export interface ProfileHistoryItem {
  tableId: string
  title: string
  note: string
  meta: string
  source: HistorySource
}

const DEMO_PARTICIPATED: ProfileHistoryItem[] = [
  {
    tableId: 'demo-participated-rest',
    title: '为什么我们越来越不会休息？',
    note: '你以旁听/入席留下过痕迹（演示）',
    meta: '演示 · 已收束',
    source: 'demo',
  },
  {
    tableId: 'demo-participated-leave',
    title: '关于离开一座城市之后',
    note: '这桌还缺一个真正停下来过的人（演示）',
    meta: '演示 · 进行中',
    source: 'demo',
  },
]

function lobbyToSavedItem(item: SavedTableItemLike): ProfileHistoryItem {
  const lobby = item.lobby
  return {
    tableId: item.table_id,
    title: lobby.core_question,
    note: lobby.missing_perspective || lobby.current_subquestion || '稍后再看',
    meta: `${lobby.participant_count} 人 · ${lobby.status === 'closed' ? '已收束' : '进行中'}`,
    source: 'live',
  }
}

function lobbyToParticipated(lobby: LobbyPreviewLike): ProfileHistoryItem {
  return {
    tableId: lobby.table_id,
    title: lobby.core_question,
    note: lobby.missing_perspective || '你曾在这桌旁听或入席',
    meta: `${lobby.participant_count} 人 · ${lobby.status === 'closed' ? '已收束' : '进行中'}`,
    source: 'live',
  }
}

/** Prefer real saved-tables API; empty list is valid (not demo). */
export async function loadSavedHistory(): Promise<{ items: ProfileHistoryItem[]; error: string | null }> {
  try {
    const data = await fetchSavedTables(VIEWER_ID)
    return { items: (data.items ?? []).map(lobbyToSavedItem), error: null }
  } catch (reason) {
    return {
      items: [],
      error: reason instanceof Error ? reason.message : '暂时取不到稍后再看',
    }
  }
}

/**
 * Participated tables: try relationship-memory / discovery-adjacent signals later.
 * Today: no dedicated API — attempt saved-tables empty path then demo fallback when empty/fail,
 * per product decision (live first, demo when unavailable; drop demo when backend ships).
 */
export async function loadParticipatedHistory(): Promise<{
  items: ProfileHistoryItem[]
  error: string | null
  usingDemo: boolean
}> {
  // Placeholder live probe: reuse relationship memory table ids when present.
  try {
    const { fetchRelationshipMemory } = await import('../live/api')
    const memories = await fetchRelationshipMemory(VIEWER_ID)
    if (Array.isArray(memories) && memories.length > 0) {
      const items = memories.map((memory) => ({
        tableId: memory.table_id,
        title: memory.core_question || memory.display_name,
        note: memory.reason || '来自已收束桌的痕迹',
        meta: `依据第 ${(memory.evidence_turns ?? []).join('、') || '—'} 轮`,
        source: 'live' as const,
      }))
      return { items, error: null, usingDemo: false }
    }
    // Empty successful response → still show demo so the section isn't barren pre-backend.
    return { items: DEMO_PARTICIPATED, error: null, usingDemo: true }
  } catch (reason) {
    return {
      items: DEMO_PARTICIPATED,
      error: reason instanceof Error ? reason.message : '暂时取不到参与记录',
      usingDemo: true,
    }
  }
}

export { lobbyToParticipated }
