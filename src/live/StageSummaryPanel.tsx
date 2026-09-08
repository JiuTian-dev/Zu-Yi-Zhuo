import { useState } from 'react'
import type { StageSummaryFeedbackKindLike, StageSummaryLike } from './contract'

const TRIGGER_LABELS: Record<StageSummaryLike['trigger'], string> = {
  question_aligned: '问题已经对齐',
  disagreement_changed: '分歧发生变化',
  grounding_changed: '桌面来源发生变化',
  thread_advanced: '讨论推进了一步',
  stalled: '讨论暂时卡住',
  manual: '你主动请求',
  pre_close: '收桌前整理',
}

const FEEDBACK: Array<[StageSummaryFeedbackKindLike, string]> = [
  ['misrepresented', '这不准确'],
  ['missing_point', '漏掉了重点'],
  ['not_consensus', '还不是共识'],
  ['ready_to_advance', '可以继续推进'],
]

function Evidence({ text, evidence_turns, onEvidence }: { text: string; evidence_turns: number[]; onEvidence?: (turnId: number) => void }) {
  return <li>{text}<small>{evidence_turns.map((turnId) => <button key={turnId} type="button" className="evidence-link" onClick={() => onEvidence?.(turnId)}>跳到第 {turnId} 句</button>)}</small></li>
}

export default function StageSummaryPanel({
  summary,
  history,
  pending,
  participantId,
  onRequest,
  onFeedback,
  onEvidence,
}: {
  summary: StageSummaryLike | null
  history: StageSummaryLike[]
  pending: 'idle' | 'requested' | 'running' | 'failed'
  participantId?: string
  onRequest(): void
  onFeedback(kind: StageSummaryFeedbackKindLike, summary: StageSummaryLike): Promise<void>
  onEvidence?(turnId: number): void
}) {
  const [feedbackSent, setFeedbackSent] = useState<string | null>(null)
  const [historyOpen, setHistoryOpen] = useState(false)
  const [collapsed, setCollapsed] = useState(false)
  const canRequest = Boolean(participantId) && pending === 'idle'
  const sendFeedback = async (kind: StageSummaryFeedbackKindLike) => {
    if (!summary || feedbackSent) return
    await onFeedback(kind, summary)
    setFeedbackSent(kind)
  }

  return (
    <aside className="stage-summary-card" aria-live="polite">
      <div className="stage-summary-heading">
        <div><p className="panel-kicker">STAGE CHECKPOINT</p><h2>讨论阶段总结</h2></div>
        {summary && <span className="stage-summary-revision">第 {summary.revision} 版</span>}
        <button type="button" className="stage-summary-history-toggle" onClick={() => setCollapsed((open) => !open)} aria-expanded={!collapsed}>{collapsed ? '展开' : '收起'}</button>
      </div>
      {!collapsed && <>
      {pending === 'requested' && <p className="stage-summary-status">已收到请求，正在整理桌面…</p>}
      {pending === 'running' && <p className="stage-summary-status">主持 Agent 正在核对这段讨论…</p>}
      {pending === 'failed' && <p className="stage-summary-status is-error">这次整理没有完成，可以稍后再试。</p>}
      {!summary && pending === 'idle' && <p className="stage-summary-empty">让主持人把当前桌面整理成一张可继续使用的地图。</p>}
      {summary && (
        <>
          <p className="stage-summary-meta">{TRIGGER_LABELS[summary.trigger]} · 覆盖第 {summary.covered_turn_start}—{summary.covered_turn_end} 句</p>
          {summary.clarified.length > 0 && <section><h3>已经说清</h3><ul>{summary.clarified.map((item, index) => <Evidence key={`clarified-${index}`} {...item} onEvidence={onEvidence} />)}</ul></section>}
          {summary.disagreements.length > 0 && <section><h3>仍有分歧</h3><ul>{summary.disagreements.map((item, index) => <Evidence key={`disagreement-${index}`} text={item.text} evidence_turns={item.evidence_turns} onEvidence={onEvidence} />)}</ul></section>}
          {summary.missing.length > 0 && <section><h3>还缺什么</h3><ul>{summary.missing.map((item, index) => <Evidence key={`missing-${index}`} {...item} onEvidence={onEvidence} />)}</ul></section>}
          {summary.next_focus && <section><h3>下一步</h3><Evidence {...summary.next_focus} onEvidence={onEvidence} /></section>}
          {participantId && <div className="stage-summary-feedback" aria-label="校正这份总结">
            <span>这份总结贴近桌面吗？</span>
            <div>{FEEDBACK.map(([kind, label]) => <button key={kind} type="button" disabled={Boolean(feedbackSent)} className={feedbackSent === kind ? 'is-selected' : ''} onClick={() => void sendFeedback(kind)}>{feedbackSent === kind ? '已收到' : label}</button>)}</div>
          </div>}
        </>
      )}
      <div className="stage-summary-actions">
        <button type="button" className="stage-summary-request" onClick={onRequest} disabled={!canRequest} aria-busy={pending === 'requested' || pending === 'running'}>{pending === 'requested' || pending === 'running' ? '正在整理…' : '总结一下现在聊到哪里'}</button>
        {history.length > 1 && <button type="button" className="stage-summary-history-toggle" onClick={() => setHistoryOpen((open) => !open)} aria-expanded={historyOpen}>查看历史 {historyOpen ? '↑' : '↓'}</button>}
      </div>
      {historyOpen && <ol className="stage-summary-history">{history.slice().reverse().map((item) => <li key={`${item.summary_id}-${item.revision}`}><b>第 {item.revision} 版</b><span>{TRIGGER_LABELS[item.trigger]} · 第 {item.covered_turn_start}—{item.covered_turn_end} 句</span></li>)}</ol>}
      </>}
    </aside>
  )
}
