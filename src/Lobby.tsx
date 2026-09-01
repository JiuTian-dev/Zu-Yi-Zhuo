import { useEffect, useRef } from 'react'
import { humanActors, tableHost } from './actors'
import { worldLabel, type TableSummary } from './domain'

interface LobbyProps {
  table: TableSummary
  onClose(): void
  onListen(): void
  onJoin(): void
}

export default function Lobby({ table, onClose, onListen, onJoin }: LobbyProps) {
  const panelRef = useRef<HTMLElement>(null)

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
        <p className="lobby-kicker">{worldLabel(table.worldId)} · {table.status === 'live' ? '正在发生' : '正在形成'}</p>
        <h2 className="lobby-title">{table.hook}</h2>

        <div className="lobby-members" aria-label="桌上的成员">
          {humanActors.map((actor) => (
            <div key={actor.id} className="lobby-member">
              <i style={{ background: actor.accent }} aria-hidden="true" />
              <span><b>{actor.displayName}</b><small>{actor.role}</small></span>
            </div>
          ))}
          <div className="lobby-member">
            <i style={{ background: tableHost.accent }} aria-hidden="true" />
            <span><b>{tableHost.displayName}</b><small>{tableHost.role}</small></span>
          </div>
          <div className="lobby-member is-empty">
            <i aria-hidden="true" />
            <span><b>第五席 · 空着</b><small>{table.missingPerspective}</small></span>
          </div>
        </div>

        {table.previewLines && table.previewLines.length > 0 && (
          <div className="lobby-preview">
            {table.previewLines.map((line) => <p key={line}>{line}</p>)}
          </div>
        )}

        {table.recommendedBecause && (
          <div className="lobby-recommend">
            <p>{table.recommendedBecause}</p>
          </div>
        )}

        <div className="lobby-actions">
          <button className="lobby-listen" type="button" onClick={onListen}>先在旁边听听</button>
          <button className="lobby-join" type="button" onClick={onJoin}>坐下来看看 <span>→</span></button>
        </div>

      </section>
    </div>
  )
}
