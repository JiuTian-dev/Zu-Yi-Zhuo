import { useEffect, useRef, useState } from 'react'
import { tableHost } from './actors'
import { worldLabel, type TableSummary } from './domain'
import type { LobbyFitPreviewLike, LobbyPreviewLike } from './live/contract'
import { VIEWER_ID } from './live/identity'
import { saveTableForLater } from './live/api'

interface LobbyProps {
  table: TableSummary
  onClose(): void
  onListen(): void
  onJoin(): void
  onRetry(): void
  lobby: LobbyPreviewLike | null
  fit: LobbyFitPreviewLike | null
  loading: boolean
  error?: string | null
}

export default function Lobby({ table, onClose, onListen, onJoin, onRetry, lobby, fit, loading, error = null }: LobbyProps) {
  const panelRef = useRef<HTMLElement>(null)
  const openerRef = useRef<HTMLElement | null>(null)
  const onCloseRef = useRef(onClose)
  const [saveState, setSaveState] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle')
  onCloseRef.current = onClose
  const title = lobby?.core_question ?? table.hook
  const missingPerspective = lobby?.missing_perspective ?? table.missingPerspective
  // PRODUCT DATA BOUNDARY — member rows only come from the backend lobby
  // projection. An unavailable lobby is shown as an error, never as fixture
  // participants that look like real people.
  const members = lobby?.members ?? []
  const viewerAlreadySeated = members.some((member) => member.participant_id === VIEWER_ID)
  const hasOpenSeat = Boolean(lobby && lobby.available_seats > 0)
  const lobbyStateLabel = loading
    ? '正在同步'
    : lobby?.status === 'open'
      ? '正在发生'
      : lobby?.status === 'soft_expired'
        ? '已暂停'
        : lobby?.status === 'closed'
          ? '已收束'
          : '等待同步'
  const canEnter = !loading && !error && lobby?.status === 'open'
  const canJoinOrEnter = canEnter && (viewerAlreadySeated || hasOpenSeat)

  useEffect(() => {
    setSaveState('idle')
  }, [lobby?.table_id])

  const saveForLater = async () => {
    if (saveState === 'saving' || saveState === 'saved' || !lobby) return
    setSaveState('saving')
    try {
      await saveTableForLater(VIEWER_ID, lobby.table_id)
      setSaveState('saved')
    } catch {
      setSaveState('error')
    }
  }

  useEffect(() => {
    openerRef.current = document.activeElement instanceof HTMLElement ? document.activeElement : null
    panelRef.current?.focus({ preventScroll: true })
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault()
        onCloseRef.current()
        return
      }
      if (event.key !== 'Tab' || !panelRef.current) return
      const focusable = Array.from(panelRef.current.querySelectorAll<HTMLElement>(
        'button:not([disabled]), [href], input:not([disabled]), textarea:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])',
      ))
      if (focusable.length === 0) return
      const first = focusable[0]
      const last = focusable[focusable.length - 1]
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault()
        last.focus()
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault()
        first.focus()
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => {
      window.removeEventListener('keydown', onKeyDown)
      openerRef.current?.focus({ preventScroll: true })
    }
  }, [])

  return (
    <div className="lobby-root">
      <div className="lobby-backdrop" role="presentation" aria-hidden="true" onClick={onClose} />
      <section className="lobby" ref={panelRef} tabIndex={-1} role="dialog" aria-modal="true" aria-label={`${table.hook} 的桌边预览`}>
        <button className="lobby-close" type="button" aria-label="关闭桌边预览" onClick={onClose}>×</button>
        <p className="lobby-kicker">{worldLabel(table.worldId)} · {lobbyStateLabel}</p>
        <h2 className="lobby-title">{title}</h2>

        <div className="lobby-context" aria-live="polite">
          <span><small>现在聊到</small>{lobby?.current_subquestion ?? '问题刚刚摆上桌面'}</span>
            <span><small>空席</small>{loading ? '读取中…' : lobby ? `${lobby.available_seats} 个` : '—'}</span>
        </div>

        <div className="lobby-members" aria-label="桌上的成员">
          {members.map((member) => {
            return (
            <div key={member.participant_id} className="lobby-member">
              <i style={{ background: `hsl(${(member.participant_id.length * 29) % 360} 38% 58%)` }} aria-hidden="true" />
              <span><b>{member.display_name}</b><small>{member.role}</small></span>
            </div>
            )
          })}
          <div className="lobby-member">
            <i style={{ background: tableHost.accent }} aria-hidden="true" />
            <span><b>{tableHost.displayName}</b><small>{tableHost.role}</small></span>
          </div>
          {hasOpenSeat && !viewerAlreadySeated && <div className="lobby-member is-empty">
            <i aria-hidden="true" />
            <span><b>第五席 · 空着</b><small>{missingPerspective}</small></span>
          </div>}
        </div>

        {table.previewLines && table.previewLines.length > 0 && (
          <div className="lobby-preview">
            {table.previewLines.map((line) => <p key={line}>{line}</p>)}
          </div>
        )}

        {(fit?.reason || table.recommendedBecause) && (
          <div className="lobby-recommend">
            <small>为什么想到你</small>
            <p>{fit?.reason ?? table.recommendedBecause}</p>
          </div>
        )}

        {loading && <p className="lobby-loading" role="status">正在把这张桌的最新状态接过来…</p>}
        {error && <p className="lobby-error" role="alert">{error} <button type="button" onClick={onRetry}>重新读取</button></p>}

        <div className="lobby-actions">
          <button className="lobby-save" type="button" onClick={() => void saveForLater()} disabled={!canEnter || saveState === 'saving' || saveState === 'saved'}>{saveState === 'saving' ? '保存中…' : saveState === 'saved' ? '已保存' : '稍后再看'}</button>
          <button className="lobby-listen" type="button" onClick={onListen} disabled={!canEnter}>先在旁边听听</button>
          <button className="lobby-join" type="button" onClick={onJoin} disabled={!canJoinOrEnter}>{loading ? '正在同步…' : viewerAlreadySeated ? '进入这张桌' : hasOpenSeat ? '坐下来看看' : '这桌已满'} <span>{viewerAlreadySeated ? '↗' : '→'}</span></button>
        </div>
        {saveState === 'error' && <p className="lobby-save-error" role="status">暂时没保存上，再试一次。</p>}

      </section>
    </div>
  )
}
