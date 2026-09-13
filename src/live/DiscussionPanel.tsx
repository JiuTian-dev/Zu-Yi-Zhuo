import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import type { PersonalCardLike, ReplayResponseLike, ReplaySourceSignalLike, SharedBaselineLike } from './contract'
import { loadReplay } from './backend'

interface DiscussionPanelProps {
  open: boolean
  tableId: string
  participantId?: string
  members: Array<{ participant_id: string; display_name: string; role?: string }>
  closeState?: 'idle' | 'started' | 'ready'
  baseline?: SharedBaselineLike | null
  personalCard?: PersonalCardLike | null
  focusTurnId?: number | null
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
  return signal.title || signal.excerpt || signal.signal_id || '桌面来源信号'
}

export default function DiscussionPanel({
  open,
  tableId,
  participantId,
  members,
  closeState = 'idle',
  baseline = null,
  personalCard = null,
  focusTurnId = null,
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

  useEffect(() => {
    if (!open || loading || !replay || !focusTurnId || !panelRef.current) return
    const target = panelRef.current.querySelector<HTMLElement>(`[data-turn-id="${focusTurnId}"]`)
    if (!target) return
    target.scrollIntoView({ behavior: 'smooth', block: 'center' })
    target.focus({ preventScroll: true })
  }, [focusTurnId, loading, open, replay])

  if (!open || typeof document === 'undefined') return null

  // PRODUCT DATA BOUNDARY — history is a replay projection, never a locally
  // fabricated copy of the live stream. If replay is unavailable, show the
  // explicit unavailable state below instead of silently mixing sources.
  const messages = replay?.messages ?? []
  const sourceSignals = replay?.source_signals ?? []

  return createPortal(
    <div className="discussion-panel-root">
      <div className="discussion-panel-backdrop" role="presentation" aria-hidden="true" onClick={onClose} />
      <section
        className="discussion-panel"
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="discussion-panel-title"
      >
        <header className="discussion-panel-header">
          <h2 id="discussion-panel-title">讨论依据</h2>
          <button ref={closeButtonRef} className="discussion-panel-close" type="button" aria-label="关闭讨论历史" onClick={onClose}>×</button>
        </header>

        {loading && <p className="discussion-panel-loading" role="status">正在从桌面回放取回历史…</p>}
        {!loading && error && (
          <p className="discussion-panel-loading" role="alert">
            {error} <button type="button" onClick={() => setReloadToken((value) => value + 1)}>重新读取</button>
          </p>
        )}
        {!loading && !error && !replay && <p className="discussion-panel-loading">暂时取不到这张桌的历史。</p>}

        {!loading && !error && replay && <div className="discussion-panel-body">
          <div className="discussion-timeline" aria-label="真人表达历史">
            {messages.length === 0 && <p className="discussion-empty">这张桌还在等第一句话。</p>}
            {messages.map((message, index) => (
              <article className="discussion-entry" data-turn-id={message.turn_id} tabIndex={message.turn_id === focusTurnId ? -1 : undefined} key={message.message_id ?? `${message.turn_id}-${message.participant_id}-${index}`}>
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

          {(sourceSignals.length > 0 || baseline || personalCard) && <aside className="discussion-panel-aside" aria-label="讨论来源">
            {sourceSignals.length > 0 && <section>
              <small className="discussion-aside-label">桌面来源</small>
              {sourceSignals.map((signal, index) => (
                <article className="discussion-source" key={signal.signal_id ?? `${signal.source_ref}-${index}`}>
                  <b>{signalTitle(signal)}</b>
                  {signal.source_ref && <small>{signal.source_ref}</small>}
                </article>
              ))}
            </section>}

            {(baseline || personalCard) && (
              <section className="discussion-close-summary">
                <small className="discussion-aside-label">收桌卡</small>
                {baseline && <p><b>共同底稿</b>{baseline.evolved_question.text}</p>}
                {personalCard && personalCard.what_changed.length > 0 && <p><b>你的变化</b>{personalCard.what_changed[0].text}</p>}
              </section>
            )}
          </aside>}
        </div>}
      </section>
    </div>,
    document.body,
  )
}
