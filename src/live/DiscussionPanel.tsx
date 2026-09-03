import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import type { PersonalCardLike, ReplayResponseLike, ReplaySourceSignalLike, SharedBaselineLike } from './contract'
import { loadReplay } from './backend'

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
  members: Array<{ participant_id: string; display_name: string; role?: string }>
  closeState?: 'idle' | 'started' | 'ready'
  baseline?: SharedBaselineLike | null
  personalCard?: PersonalCardLike | null
  onClose(): void
}

function speakerName(participantId: string, members: DiscussionPanelProps['members'], viewerParticipantId?: string) {
  if (participantId === 'table-host') return '圆桌主持'
  if (participantId === viewerParticipantId) return '你'
  const member = members.find((item) => item.participant_id === participantId)
  if (!viewerParticipantId && member?.display_name === '你') return member.role ?? '第五席'
  return member?.display_name ?? participantId
}

function signalTitle(signal: ReplaySourceSignalLike) {
  return signal.title ?? signal.summary ?? signal.excerpt ?? signal.signal_id ?? '桌面来源信号'
}

export default function DiscussionPanel({
  open,
  tableId,
  participantId,
  members,
  closeState = 'idle',
  baseline = null,
  personalCard = null,
  onClose,
}: DiscussionPanelProps) {
  const panelRef = useRef<HTMLElement>(null)
  const closeButtonRef = useRef<HTMLButtonElement>(null)
  const openerRef = useRef<HTMLElement | null>(null)
  const wasOpenRef = useRef(false)
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
    if (typeof document === 'undefined') return
    if (open && !wasOpenRef.current) {
      openerRef.current = document.activeElement instanceof HTMLElement ? document.activeElement : null
      window.requestAnimationFrame(() => closeButtonRef.current?.focus({ preventScroll: true }))
    }
    if (!open && wasOpenRef.current) {
      openerRef.current?.focus({ preventScroll: true })
      openerRef.current = null
    }
    wasOpenRef.current = open
  }, [open])

  useEffect(() => {
    if (!open) return
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault()
        onClose()
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
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [onClose, open])

  if (!open || typeof document === 'undefined') return null

  // PRODUCT DATA BOUNDARY — history is a replay projection, never a locally
  // fabricated copy of the live stream. If replay is unavailable, show the
  // explicit unavailable state below instead of silently mixing sources.
  const messages = replay?.messages ?? []
  const interventions = replay?.interventions ?? []
  const snapshots = replay?.snapshots ?? []
  const sourceSignals = replay?.source_signals ?? []
  const comments = replay?.comments ?? []
  const promotions = replay?.comment_promotions ?? []

  return createPortal(
    <div className="discussion-panel-root">
      <button className="discussion-panel-backdrop" type="button" aria-label="关闭讨论历史" onClick={onClose} />
      <section
        className="discussion-panel"
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="discussion-panel-title"
      >
        <header className="discussion-panel-header">
          <div>
            <p className="discussion-panel-kicker">桌面回放 · {tableId}</p>
            <h2 id="discussion-panel-title">这张桌，已经说过什么</h2>
          </div>
          <button ref={closeButtonRef} className="discussion-panel-close" type="button" aria-label="关闭讨论历史" onClick={onClose}>×</button>
        </header>

        <div className="discussion-panel-stats" aria-live="polite">
          <span><b>{messages.length}</b> 条表达</span>
          <span><b>{interventions.length}</b> 次主持介入</span>
          <span><b>{snapshots.length}</b> 个状态节点</span>
          <span><b>{sourceSignals.length}</b> 条来源</span>
        </div>

        {closeState !== 'idle' && (
          <div className={`discussion-close-banner is-${closeState}`} role="status">
            {closeState === 'ready' ? '这张桌已经收束，收桌卡也已准备好。' : '主持人正在整理这张桌的收桌卡。'}
          </div>
        )}

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
            {messages.map((message, index) => (
              <article className="discussion-entry" key={message.message_id ?? `${message.turn_id}-${message.participant_id}-${index}`}>
                <div className="discussion-entry-mark" aria-hidden="true"><span /></div>
                <div className="discussion-entry-copy">
                  <div className="discussion-entry-meta">
                    <b>{speakerName(message.participant_id, members, participantId)}</b>
                    <small>第 {message.turn_id} 轮{message.source_comment_id ? ' · 来自评论' : ''}</small>
                  </div>
                  <p>“{message.text}”</p>
                </div>
              </article>
            ))}
          </div>

          <aside className="discussion-panel-aside" aria-label="主持动作与问题进展">
            <section>
              <small className="discussion-aside-label">主持动作</small>
              {interventions.length ? interventions.map((intervention) => (
                <article className="discussion-intervention" key={intervention.intervention_id}>
                  <div><b>{ACTION_LABELS[intervention.action] ?? intervention.action}</b><small>证据 · {intervention.evidence_turns.join('、') || '—'}</small></div>
                  {intervention.text && <p>{intervention.text}</p>}
                  {intervention.grounding_card && <div className="discussion-grounding"><small>{intervention.grounding_card.title}</small><p>{intervention.grounding_card.excerpt}</p><em>{intervention.grounding_card.source_ref}</em></div>}
                  {intervention.reflection && <p className="discussion-reflection">回应：{intervention.reflection.text}</p>}
                </article>
              )) : <p className="discussion-aside-empty">主持人还在听。</p>}
            </section>

            <section>
              <small className="discussion-aside-label">问题怎么走到这里</small>
              {snapshots.length ? snapshots.map((snapshot) => (
                <div className="discussion-state-row" key={snapshot.version}>
                  <span>{String(snapshot.version).padStart(2, '0')}</span>
                  <p><b>{PHASE_LABELS[snapshot.phase] ?? snapshot.phase}</b>{snapshot.current_subquestion ?? '原始问题仍在桌面中央'}</p>
                </div>
              )) : <p className="discussion-aside-empty">状态节点将在第一轮表达后出现。</p>}
            </section>

            <section>
              <small className="discussion-aside-label">桌面来源</small>
              {sourceSignals.length ? sourceSignals.map((signal, index) => (
                <article className="discussion-source" key={signal.signal_id ?? `${signal.source_ref}-${index}`}>
                  <b>{signalTitle(signal)}</b>
                  {signal.source_ref && <small>{signal.source_ref}</small>}
                </article>
              )) : <p className="discussion-aside-empty">这张桌没有附带公开来源。</p>}
              {(comments.length > 0 || promotions.length > 0) && <small className="discussion-activity-count">评论 {comments.length} · 被提到 {promotions.length}</small>}
            </section>

            {(baseline || personalCard) && (
              <section className="discussion-close-summary">
                <small className="discussion-aside-label">收桌卡</small>
                {baseline && <p><b>共同底稿</b>{baseline.evolved_question.text}</p>}
                {personalCard && personalCard.what_changed.length > 0 && <p><b>你的变化</b>{personalCard.what_changed[0].text}</p>}
              </section>
            )}
          </aside>
        </div>

        <footer className="discussion-panel-footer">
          <span>历史只读 · 由这张桌的证据快照重建</span>
          <button type="button" onClick={onClose}>回到桌边 <i>→</i></button>
        </footer>
      </section>
    </div>,
    document.body,
  )
}
