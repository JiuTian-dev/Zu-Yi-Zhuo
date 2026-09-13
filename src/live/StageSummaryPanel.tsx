import { useEffect, useRef, useState, type FormEvent } from 'react'
import { createPortal } from 'react-dom'
import type { StageSummaryLike } from './contract'

function SummaryItems({ title, items, onEvidence }: {
  title: string
  items: Array<{ text: string; evidence_turns: number[] }>
  onEvidence?: (turnId: number) => void
}) {
  if (items.length === 0) return null
  return (
    <section>
      <h3>{title}</h3>
      <ul>
        {items.map((item, index) => (
          <li key={`${title}-${index}`}>
            <span>{item.text}</span>
            {item.evidence_turns.length > 0 && <button type="button" className="summary-source" onClick={() => onEvidence?.(item.evidence_turns[0])}>原话</button>}
          </li>
        ))}
      </ul>
    </section>
  )
}

export default function StageSummaryPanel({
  open, summary, history, pending, participantId, onClose, onRequest, onFeedback, onEvidence,
}: {
  open: boolean
  summary: StageSummaryLike | null
  history: StageSummaryLike[]
  pending: 'idle' | 'requested' | 'running' | 'failed'
  participantId?: string
  onClose(): void
  onRequest(): void
  onFeedback(note: string, summary: StageSummaryLike): Promise<boolean>
  onEvidence?(turnId: number): void
}) {
  const [editing, setEditing] = useState(false)
  const [note, setNote] = useState('')
  const [sending, setSending] = useState(false)
  const [selectedRevision, setSelectedRevision] = useState<string | null>(null)
  const panelRef = useRef<HTMLElement>(null)
  const onCloseRef = useRef(onClose)
  onCloseRef.current = onClose
  const summaryKey = (item: StageSummaryLike) => `${item.summary_id}:${item.revision}`

  useEffect(() => {
    setEditing(false)
    setNote('')
    setSending(false)
    setSelectedRevision(summary ? summaryKey(summary) : null)
  }, [summary?.summary_id, summary?.revision])

  useEffect(() => {
    if (!open) return
    const opener = document.activeElement instanceof HTMLElement ? document.activeElement : null
    panelRef.current?.querySelector<HTMLButtonElement>('button')?.focus({ preventScroll: true })
    const onKey = (event: globalThis.KeyboardEvent) => {
      if (event.key === 'Escape') { event.preventDefault(); onCloseRef.current(); return }
      if (event.key !== 'Tab') return
      const fields = Array.from(panelRef.current?.querySelectorAll<HTMLElement>('button:not([disabled]), input:not([disabled]), summary, [tabindex="0"]') ?? []).filter((node) => node.getClientRects().length > 0)
      if (!fields.length) return
      const first = fields[0], last = fields[fields.length - 1]
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus() }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus() }
    }
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('keydown', onKey)
      if (opener?.isConnected) opener.focus({ preventScroll: true })
    }
  }, [open])

  if (!open) return null
  const canRequest = Boolean(participantId) && (pending === 'idle' || pending === 'failed')
  const displayedSummary = history.find((item) => summaryKey(item) === selectedRevision) ?? summary
  const viewingLatest = Boolean(displayedSummary && summary && summaryKey(displayedSummary) === summaryKey(summary))

  const submitFeedback = async (event: FormEvent) => {
    event.preventDefault()
    if (!summary || !note.trim() || sending) return
    setSending(true)
    const saved = await onFeedback(note.trim(), summary)
    setSending(false)
    if (saved) {
      setNote('')
      setEditing(false)
    }
  }

  return createPortal(
    <div className="summary-root">
    <div className="summary-veil" aria-hidden="true" onClick={onClose} />
    <aside ref={panelRef} className="summary-sheet" role="dialog" aria-modal="true" aria-labelledby="summary-title">
      <header>
        <h2 id="summary-title">阶段小结</h2>
        <button type="button" aria-label="关闭阶段小结" onClick={onClose}>×</button>
      </header>
      {(pending === 'requested' || pending === 'running') && <p className="summary-state">正在整理</p>}
      {pending === 'failed' && <p className="summary-state is-error">整理失败，请重试</p>}
      {displayedSummary ? (
        <div className="summary-content">
          <SummaryItems title="聊清楚了" items={displayedSummary.clarified} onEvidence={onEvidence} />
          <SummaryItems title="仍待讨论" items={[...displayedSummary.disagreements, ...displayedSummary.missing]} onEvidence={onEvidence} />
          {displayedSummary.next_focus && <SummaryItems title="接下来" items={[displayedSummary.next_focus]} onEvidence={onEvidence} />}
          {participantId && viewingLatest && !editing && <button type="button" className="summary-edit" onClick={() => setEditing(true)}>修改</button>}
          {participantId && editing && (
            <form className="summary-edit-form" onSubmit={submitFeedback}>
              <input value={note} onChange={(event) => setNote(event.target.value)} maxLength={240} autoFocus aria-label="修改阶段小结" />
              <button type="submit" disabled={!note.trim() || sending}>{sending ? '保存中' : '保存'}</button>
              <button type="button" onClick={() => setEditing(false)}>取消</button>
            </form>
          )}
          {history.length > 1 && <details className="summary-history"><summary>历史版本</summary><ol>{history.slice().reverse().map((item) => <li key={summaryKey(item)}><button type="button" aria-current={summaryKey(displayedSummary) === summaryKey(item) ? 'true' : undefined} onClick={() => { setEditing(false); setSelectedRevision(summaryKey(item)) }}>第 {item.revision} 版{item.next_focus ? `：${item.next_focus.text}` : ''}</button></li>)}</ol></details>}
        </div>
      ) : pending === 'idle' || pending === 'failed' ? (
        <button type="button" className="summary-generate" onClick={onRequest} disabled={!canRequest}>{pending === 'failed' ? '重新整理' : '生成小结'}</button>
      ) : null}
      {summary && (pending === 'idle' || pending === 'failed') && <button type="button" className="summary-regenerate" onClick={onRequest} disabled={!canRequest}>重新整理</button>}
    </aside>
    </div>, document.body,
  )
}
