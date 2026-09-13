import { useEffect, useMemo, useState, type CSSProperties } from 'react'
import { galleryTables, type AppPhase, type TableSummary } from './domain'
import type { LobbyPreviewLike } from './live/contract'
import DrawerToggle from './DrawerToggle'
import './table-discovery.css'

export interface GalleryMediaRect { left: number; top: number; width: number; height: number }

interface TableSeaProps {
  onEnter(table: TableSummary, rect: GalleryMediaRect): void
  onOpenIntent(): void
  onOpenDemo?(): void
  phase: AppPhase
  returnFocusId: string | null
  discovery?: LobbyPreviewLike[] | null
  backendUnavailable?: boolean
  loading?: boolean
  onRetry?(): void
}

/**
 * PRODUCT DOM — table discovery only.
 *
 * The previous implementation mounted a second R3F “sea” with low-poly
 * tables. That made the entry and the table room two unrelated worlds. The
 * Bruno runtime is now persistent underneath this layer; this component is
 * deliberately DOM-only and only selects a backend table.
 */
export default function TableSea({ onEnter, onOpenIntent, onOpenDemo, phase, returnFocusId, discovery = [], backendUnavailable = false, loading = false, onRetry }: TableSeaProps) {
  const tables = useMemo(() => {
    // PRODUCT DATA BOUNDARY — an empty successful discovery response means
    // there are no tables. Static fixtures are only allowed in the explicit
    // backend-unavailable path.
    if (loading) return []
    if (backendUnavailable) return galleryTables
    return (discovery ?? []).map((lobby): TableSummary => {
      const common = {
        id: lobby.table_id,
        worldId: 'valley' as const,
        hook: lobby.core_question,
        seatedCount: lobby.participant_count,
        missingPerspective: lobby.missing_perspective || (lobby.available_seats > 0 ? `还剩 ${lobby.available_seats} 个空席` : '这桌正在进行中'),
        recommendedBecause: lobby.role_gaps[0] ? `这桌正在寻找：${lobby.role_gaps.join('、')}` : undefined,
        previewLines: lobby.members.slice(0, 3).map((member) => `${member.display_name} · ${member.role}`),
      }
      return lobby.status === 'closed'
        ? { ...common, status: 'forming', entryMode: 'preview', transitionPreset: 'cover-only' }
        : { ...common, status: 'live', entryMode: 'immersive', transitionPreset: 'valley' }
    })
  }, [backendUnavailable, discovery, loading])

  const [activeIndex, setActiveIndex] = useState(0)
  const [copyCollapsed, setCopyCollapsed] = useState(false)
  const [tableListCollapsed, setTableListCollapsed] = useState(false)
  const activeTable = tables[Math.min(activeIndex, Math.max(0, tables.length - 1))] ?? null

  useEffect(() => {
    document.documentElement.classList.add('sea-mode')
    document.body.classList.add('sea-mode')
    return () => {
      document.documentElement.classList.remove('sea-mode')
      document.body.classList.remove('sea-mode')
    }
  }, [])

  useEffect(() => {
    const index = returnFocusId ? tables.findIndex((table) => table.id === returnFocusId) : -1
    if (index >= 0) setActiveIndex(index)
  }, [returnFocusId, tables])

  useEffect(() => {
    setActiveIndex((current) => tables.length ? Math.min(current, tables.length - 1) : 0)
  }, [tables.length])

  const choose = (index: number) => setActiveIndex(index)
  const enter = (event: React.MouseEvent<HTMLButtonElement>) => {
    if (phase !== 'gallery' || !activeTable || activeTable.entryMode !== 'immersive') return
    const rect = event.currentTarget.getBoundingClientRect()
    onEnter(activeTable, { left: rect.left, top: rect.top, width: rect.width, height: rect.height })
  }

  const hidden = phase === 'expanding' || phase === 'collapsing'
  return (
    <main
      className={`sea-page product-entry ${hidden ? 'is-transitioning' : ''}`}
      style={{ '--sea-accent': '#a8ce84' } as CSSProperties}
      aria-label="匹配页：正在发生的桌"
    >
      <div className="sea-vignette" aria-hidden="true" />
      <header className="sea-header">
        <div className="sea-brand"><b>组一桌</b><span>把值得聊的话，交给刚好在场的人</span></div>
        <div className="sea-header-actions">
          {onOpenDemo && <button type="button" className="demo-entry-trigger" onClick={onOpenDemo}>模拟体验</button>}
          <button type="button" onClick={onOpenIntent}>我想找一桌 <span>→</span></button>
          <em>ZH · 2026</em>
        </div>
      </header>

      <section className="sea-discovery" data-ui-interactive>
        <p className="sea-kicker"><span>{tables.length ? String(activeIndex + 1).padStart(2, '0') : '—'}</span> 正在发生</p>
        <div className={`sea-copy ${copyCollapsed ? 'is-collapsed' : ''}`}>
          <DrawerToggle collapsed={copyCollapsed} label="问题卡" controlsId="sea-copy-content" onToggle={() => setCopyCollapsed((current) => !current)} />
          <div id="sea-copy-content" className="drawer-card-content" aria-hidden={copyCollapsed} inert={copyCollapsed}>
            {loading ? <>
              <h1>正在把桌单接到湖边</h1>
              <p className="sea-missing" role="status">正在读取后端最新状态…</p>
            </> : activeTable ? <>
              <h1>{activeTable.hook}</h1>
              <p className="sea-missing">{activeTable.missingPerspective}</p>
              {activeTable.recommendedBecause && <p className="sea-recommend">{activeTable.recommendedBecause}</p>}
              <button className="sea-cta" type="button" onClick={enter} disabled={activeTable.entryMode !== 'immersive'}>
                <span>{activeTable.entryMode === 'immersive' ? '坐下来看看' : '这桌暂未开放'}</span><i>→</i>
              </button>
            </> : <>
              <h1>还没有正在发生的桌</h1>
              <p className="sea-missing">等一张桌准备好，再从这里坐下来。</p>
            </>}
          </div>
        </div>
      </section>

      <nav className={`sea-table-list ${tableListCollapsed ? 'is-collapsed' : ''}`} aria-label="选择一张桌" data-ui-interactive>
        <DrawerToggle collapsed={tableListCollapsed} label="桌单" controlsId="sea-table-list-content" onToggle={() => setTableListCollapsed((current) => !current)} />
        <div id="sea-table-list-content" className="sea-table-list-content" aria-hidden={tableListCollapsed} inert={tableListCollapsed}>
          {tables.map((table, index) => (
            <button key={table.id} type="button" className={index === activeIndex ? 'is-active' : ''} onClick={() => choose(index)}>
              <span>{String(index + 1).padStart(2, '0')}</span>
              <b>{table.hook || table.id}</b>
              <small>{table.seatedCount} 人 · {table.entryMode === 'immersive' ? '进行中' : '稍后开放'}</small>
            </button>
          ))}
        </div>
      </nav>

      {backendUnavailable && <p className="sea-backend-note" role="status">后端暂不可用 · 当前为演示桌单 {onRetry && <button type="button" onClick={onRetry}>重新连接</button>}</p>}
    </main>
  )
}
