import { useEffect, useState, type FormEvent } from 'react'
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
  const [selectedRevision, setSelectedRevision] = useState<number | null>(null)

  useEffect(() => {
    setEditing(false)
    setNote('')
    setSending(false)
    setSelectedRevision(summary?.revision ?? null)
  }, [summary?.summary_id, summary?.revision])

  if (!open) return null
  const canRequest = Boolean(participantId) && (pending === 'idle' || pending === 'failed')
  const displayedSummary = history.find((item) => item.revision === selectedRevision) ?? summary
  const viewingLatest = displayedSummary?.revision === summary?.revision

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

  return (
    <aside className="summary-sheet" role="dialog" aria-modal="true" aria-labelledby="summary-title">
      <header>
        <h2 id="summary-title">阶段小结</h2>
        <button type="button" aria-label="关闭阶段小结" onClick={onClose}>×</button>
      </header>
      {(pending === 'requested' || pending === 'running') && <p className="summary-state">正在整理</p>}
      {pending === 'failed' && <p className="summary-state is-error">整理失败，请重试</p>}
      {displayedSummary ? (
        <div className="summary-content">
          <SummaryItems title="已经确认" items={displayedSummary.clarified} onEvidence={onEvidence} />
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
          {history.length > 1 && <details className="summary-history"><summary>历史版本</summary><ol>{history.slice().reverse().map((item) => <li key={`${item.summary_id}-${item.revision}`}><button type="button" aria-current={displayedSummary.revision === item.revision ? 'true' : undefined} onClick={() => { setEditing(false); setSelectedRevision(item.revision) }}>第 {item.revision} 版{item.next_focus ? `：${item.next_focus.text}` : ''}</button></li>)}</ol></details>}
        </div>
      ) : pending === 'idle' || pending === 'failed' ? (
        <button type="button" className="summary-generate" onClick={onRequest} disabled={!canRequest}>{pending === 'failed' ? '重新整理' : '生成小结'}</button>
      ) : null}
      {summary && pending === 'idle' && <button type="button" className="summary-regenerate" onClick={onRequest} disabled={!canRequest}>重新整理</button>}
    </aside>
  )
}
