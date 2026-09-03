import { useEffect, useState } from 'react'
import { humanActors, tableHost } from '../actors'
import type { ReplayResponseLike } from './contract'
import { loadReplay } from './backend'
import { VIEWER_ID } from './identity'

const ACTION_LABELS: Record<string, string> = {
  PASS: '递话',
  PROBE: '追问',
  REFRAME: '换个角度',
  GROUND: '落在桌面',
  CLOSE: '收束',
  SILENCE: '安静听',
}

const PHASE_LABELS: Record<string, string> = {
  opening: '开场',
  explore: '探索',
  tension: '张力',
  deepen: '深入',
  close: '收束',
}

interface DiscussionPanelProps {
  open: boolean
  tableId: string
  participantId?: string
  members: Array<{ participant_id: string; display_name: string }>
  onClose(): void
}

function speakerName(participantId: string, members: Array<{ participant_id: string; display_name: string }>) {
  if (participantId === 'table-host') return tableHost.displayName
  if (participantId === VIEWER_ID) return '你'
  return members.find((member) => member.participant_id === participantId)?.display_name
    ?? humanActors.find((actor) => actor.id === participantId)?.displayName
    ?? participantId
}

export default function DiscussionPanel({ open, tableId, participantId, members, onClose }: DiscussionPanelProps) {
  const [replay, setReplay] = useState<ReplayResponseLike | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [reloadToken, setReloadToken] = useState(0)

  useEffect(() => {
    if (!open) return
    let active = true
    setLoading(true)
    setError(null)
    setReplay(null)
    void loadReplay(tableId, participantId).then((result) => {
      if (!active) return
      setReplay(result)
      setLoading(false)
    }).catch((reason) => {
      if (!active) return
      setReplay(null)
      setError(reason instanceof Error ? reason.message : '暂时取不到这张桌的历史')
      setLoading(false)
    })
    return () => { active = false }
  }, [open, participantId, reloadToken, tableId])

  useEffect(() => {
    if (!open) return
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [onClose, open])

  // PRODUCT DATA BOUNDARY — history is a replay projection, never a locally
  // fabricated copy of the live stream. If replay is unavailable, show the
  // explicit unavailable state below instead of silently mixing sources.
  const messages = replay?.messages ?? []

  if (!open) return null

  return (
    <div className="discussion-panel-root">
      <button className="discussion-panel-backdrop" type="button" aria-label="关闭讨论历史" onClick={onClose} />
      <section className="discussion-panel" role="dialog" aria-modal="true" aria-labelledby="discussion-panel-title">
        <header className="discussion-panel-header">
          <div>
            <p className="discussion-panel-kicker">桌面回放 · {tableId}</p>
            <h2 id="discussion-panel-title">这张桌，已经说过什么</h2>
          </div>
          <button className="discussion-panel-close" type="button" aria-label="关闭讨论历史" onClick={onClose}>×</button>
        </header>

        <div className="discussion-panel-stats" aria-live="polite">
          <span><b>{messages.length}</b> 条表达</span>
          <span><b>{replay?.interventions.length ?? 0}</b> 次主持介入</span>
          <span><b>{replay?.snapshots.length ?? 0}</b> 个状态节点</span>
        </div>

        {loading && <p className="discussion-panel-loading" role="status">正在从桌面回放取回历史…</p>}
        {!loading && error && (
          <p className="discussion-panel-loading" role="alert">
            {error} <button type="button" onClick={() => setReloadToken((value) => value + 1)}>重新读取</button>
          </p>
        )}
        {!loading && !error && !replay && <p className="discussion-panel-loading">暂时取不到这张桌的历史。</p>}

        <div className="discussion-panel-body">
          <div className="discussion-timeline" aria-label="真人表达历史">
            {messages.length === 0 && <p className="discussion-empty">这张桌还在等第一句话。</p>}
            {messages.map((message) => (
              <article className="discussion-entry" key={`${message.turn_id}-${message.participant_id}`}>
                <div className="discussion-entry-mark" aria-hidden="true"><span /></div>
                <div className="discussion-entry-copy">
                  <div className="discussion-entry-meta">
                    <b>{speakerName(message.participant_id, members)}</b>
                    <small>第 {message.turn_id} 轮</small>
                  </div>
                  <p>“{message.text}”</p>
                </div>
              </article>
            ))}
          </div>

          <aside className="discussion-panel-aside" aria-label="主持动作与问题进展">
            <section>
              <small className="discussion-aside-label">主持动作</small>
              {replay?.interventions.length ? replay.interventions.map((intervention) => (
                <article className="discussion-intervention" key={intervention.intervention_id}>
                  <div><b>{ACTION_LABELS[intervention.action] ?? intervention.action}</b><small>证据 · {intervention.evidence_turns.join('、')}</small></div>
                  {intervention.text && <p>{intervention.text}</p>}
                </article>
              )) : <p className="discussion-aside-empty">主持人还在听。</p>}
            </section>
            <section>
              <small className="discussion-aside-label">问题怎么走到这里</small>
              {replay?.snapshots.length ? replay.snapshots.map((snapshot) => (
                <div className="discussion-state-row" key={snapshot.version}>
                  <span>{String(snapshot.version).padStart(2, '0')}</span>
                  <p><b>{PHASE_LABELS[snapshot.phase] ?? snapshot.phase}</b>{snapshot.current_subquestion ?? '原始问题仍在桌面中央'}</p>
                </div>
              )) : <p className="discussion-aside-empty">状态节点将在第一轮表达后出现。</p>}
            </section>
          </aside>
        </div>

        <footer className="discussion-panel-footer">
          <span>历史只读 · 由这张桌的证据快照重建</span>
          <button type="button" onClick={onClose}>回到桌边 <i>→</i></button>
        </footer>
      </section>
    </div>
  )
}
