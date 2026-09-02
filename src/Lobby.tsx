import { useEffect, useRef } from 'react'
import { humanActors, tableHost } from './actors'
import { worldLabel, type TableSummary } from './domain'
import type { LobbyFitPreviewLike, LobbyPreviewLike } from './live/contract'

interface LobbyProps {
  table: TableSummary
  onClose(): void
  onListen(): void
  onJoin(): void
  lobby: LobbyPreviewLike | null
  fit: LobbyFitPreviewLike | null
  loading: boolean
}

export default function Lobby({ table, onClose, onListen, onJoin, lobby, fit, loading }: LobbyProps) {
  const panelRef = useRef<HTMLElement>(null)
  const title = lobby?.core_question ?? table.hook
  const missingPerspective = lobby?.missing_perspective ?? table.missingPerspective
  const members = lobby?.members ?? humanActors.map((actor) => ({ participant_id: actor.id, display_name: actor.displayName, role: actor.role }))
  const viewerAlreadySeated = members.some((member) => member.participant_id === 'viewer')
  const hasOpenSeat = lobby ? lobby.available_seats > 0 : true

  useEffect(() => {
    panelRef.current?.focus({ preventScroll: true })
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [onClose])

  return (
    <div className="lobby-root">
      <div className="lobby-backdrop" aria-hidden="true" onClick={onClose} />
      <section className="lobby" ref={panelRef} tabIndex={-1} role="dialog" aria-modal="true" aria-label={`${table.hook} 的桌边预览`}>
        <button className="lobby-close" type="button" aria-label="关闭桌边预览" onClick={onClose}>×</button>
        <p className="lobby-kicker">{worldLabel(table.worldId)} · {lobby?.status === 'open' || table.status === 'live' ? '正在发生' : '正在形成'}</p>
        <h2 className="lobby-title">{title}</h2>

        <div className="lobby-context" aria-live="polite">
          <span><small>现在聊到</small>{lobby?.current_subquestion ?? '问题刚刚摆上桌面'}</span>
          <span><small>空席</small>{lobby ? `${lobby.available_seats} 个` : '1 个 · 还缺一个视角'}</span>
        </div>

        <div className="lobby-members" aria-label="桌上的成员">
          {members.map((member) => {
            const actor = humanActors.find((item) => item.id === member.participant_id)
            return (
            <div key={member.participant_id} className="lobby-member">
              <i style={{ background: actor?.accent ?? '#9ec5a7' }} aria-hidden="true" />
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

        <div className="lobby-actions">
          <button className="lobby-listen" type="button" onClick={onListen} disabled={loading || lobby?.status === 'closed'}>先在旁边听听</button>
          <button className="lobby-join" type="button" onClick={onJoin} disabled={loading || lobby?.status === 'closed' || lobby?.available_seats === 0 || viewerAlreadySeated}>{viewerAlreadySeated ? '已在这一席' : '坐下来看看'} <span>{viewerAlreadySeated ? '✓' : '→'}</span></button>
        </div>

      </section>
    </div>
  )
}
