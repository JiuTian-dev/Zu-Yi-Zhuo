import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import {
  appendActiveIntentTurn,
  confirmSourceMatch,
  createActiveIntentSession,
  fetchActiveIntentSourcePreview,
} from './api'
import type { ActiveIntentSessionViewLike, MatchPlanLike, MatchToHomeDraftLike } from './contract'
import { VIEWER_ID } from './identity'

const FRONTEND_INTENT_TURN_LIMIT = 3

interface IntentPanelProps {
  open: boolean
  initialQuestion?: string
  onClose(): void
  onSelectTable(tableId: string): Promise<void>
  onMatchConfirmed(tableId: string, question: string): Promise<void>
  onReturnToHomeDraft(draft: MatchToHomeDraftLike): boolean
}

function routeTitle(route: ActiveIntentSessionViewLike['preview']['route']) {
  if (route === 'join_existing') return '有一张桌正在聊这个'
  if (route === 'new_table') return '这道需求值得单独组一桌'
  return '先把你想聊的说清楚'
}

export default function IntentPanel({
  open,
  initialQuestion = '',
  onClose,
  onSelectTable,
  onMatchConfirmed,
  onReturnToHomeDraft,
}: IntentPanelProps) {
  const panelRef = useRef<HTMLElement>(null)
  const closeButtonRef = useRef<HTMLButtonElement>(null)
  const [draft, setDraft] = useState(initialQuestion)
  const [session, setSession] = useState<ActiveIntentSessionViewLike | null>(null)
  const [sourcePlan, setSourcePlan] = useState<MatchPlanLike | null>(null)
  const [loading, setLoading] = useState(false)
  const [sourceLoading, setSourceLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [sourceError, setSourceError] = useState<string | null>(null)
  const [selectionId, setSelectionId] = useState<string | null>(null)
  const [handoffError, setHandoffError] = useState<string | null>(null)
  const [copyState, setCopyState] = useState<'idle' | 'copied' | 'error'>('idle')

  useEffect(() => {
    if (!open) return
    setDraft(initialQuestion)
    setSession(null)
    setSourcePlan(null)
    setError(null)
    setSourceError(null)
    setSelectionId(null)
    setHandoffError(null)
    setCopyState('idle')
    window.requestAnimationFrame(() => closeButtonRef.current?.focus({ preventScroll: true }))
  }, [initialQuestion, open])

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
        'button:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
      ))
      if (!focusable.length) return
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

  const submit = async (event: { preventDefault(): void }) => {
    event.preventDefault()
    const message = draft.trim()
    if (!message || loading || sourceLoading) return
    if (session && session.turn_count >= FRONTEND_INTENT_TURN_LIMIT) {
      setError('这次需求已经澄清到上限，可以把它带回首页继续创建。')
      return
    }
    setLoading(true)
    setError(null)
    setSourceError(null)
    try {
      const next = session
        ? await appendActiveIntentTurn(VIEWER_ID, session.session_id, message)
        : await createActiveIntentSession(VIEWER_ID, message)
      setSession(next)
      setDraft('')
      setSourcePlan(null)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '暂时无法理解这段需求')
    } finally {
      setLoading(false)
    }
  }

  const searchPublicCandidates = async () => {
    if (!session || session.preview.route !== 'new_table' || sourceLoading) return
    setSourceLoading(true)
    setSourceError(null)
    try {
      const plan = await fetchActiveIntentSourcePreview(VIEWER_ID, session.session_id)
      setSourcePlan(plan)
    } catch (reason) {
      setSourcePlan(null)
      setSourceError(reason instanceof Error ? reason.message : '公开候选源暂时不可用')
    } finally {
      setSourceLoading(false)
    }
  }

  const confirmPublicPlan = async () => {
    if (!sourcePlan?.preview_token || sourceLoading) return
    setSourceLoading(true)
    setSourceError(null)
    try {
      const result = await confirmSourceMatch(sourcePlan.preview_token)
      await onMatchConfirmed(result.state.table_id, result.state.core_question)
    } catch (reason) {
      setSourceError(reason instanceof Error ? reason.message : '这组公开候选暂时无法组桌')
    } finally {
      setSourceLoading(false)
    }
  }

  const preview = session?.preview
  const canClarify = !session || session.turn_count < FRONTEND_INTENT_TURN_LIMIT
  const buildReturnDraft = (): MatchToHomeDraftLike | null => {
    if (!session) return null
    return {
      kind: 'manual_create_draft',
      normalized_question: session.preview.normalized_question,
      clarification_messages: session.messages,
      no_match_reason: session.preview.route === 'clarify'
        ? (session.preview.clarifying_question ?? '当前还没有足够信息找到合适的桌。')
        : '当前没有合适的正在发生的桌，也没有可确认的公开候选。',
      source_session_id: session.session_id,
    }
  }
  const returnDraft = () => {
    const draft = buildReturnDraft()
    if (!draft) return
    setHandoffError(null)
    setCopyState('idle')
    try {
      if (!onReturnToHomeDraft(draft)) {
        setHandoffError('暂时交接不了这次需求，内容还在当前窗口里。你可以复制后交给首页，或再试一次。')
      }
    } catch {
      setHandoffError('暂时交接不了这次需求，内容还在当前窗口里。你可以复制后交给首页，或再试一次。')
    }
  }
  const copyDraft = async () => {
    const draft = buildReturnDraft()
    if (!draft) return
    const text = [
      `需求：${draft.normalized_question}`,
      ...draft.clarification_messages.map((message, index) => `${index + 1}. ${message}`),
      `原因：${draft.no_match_reason}`,
    ].join('\n')
    try {
      await navigator.clipboard.writeText(text)
      setCopyState('copied')
    } catch {
      setCopyState('error')
    }
  }

  return createPortal(
    <div className="intent-root">
      <button className="intent-veil" type="button" aria-label="关闭需求入口" onClick={onClose} />
      <section className="intent-panel" ref={panelRef} role="dialog" aria-modal="true" aria-labelledby="intent-panel-title">
        <header className="intent-header">
          <div>
            <p className="intent-kicker">主动找桌 · 最多三轮澄清</p>
            <h2 id="intent-panel-title">你现在想找谁，聊什么？</h2>
          </div>
          <button ref={closeButtonRef} className="intent-close" type="button" aria-label="关闭需求入口" onClick={onClose}>×</button>
        </header>

        <div className="intent-body">
          <form className="intent-form" onSubmit={submit}>
            <label htmlFor="active-intent-input">先说你的真实需求</label>
            <textarea
              id="active-intent-input"
              value={draft}
              onChange={(event) => { setDraft(event.target.value); if (error) setError(null) }}
              placeholder="例如：我想找真正做过 AI 产品落地的人，聊聊为什么试点总停在演示阶段。"
              maxLength={1000}
              disabled={loading}
            />
            <div className="intent-form-footer">
              <small>{session ? `已澄清 ${session.turn_count}/${Math.min(session.max_turns, FRONTEND_INTENT_TURN_LIMIT)} 轮` : '不需要写得很完整，先把问题摆上桌。'}</small>
              <button type="submit" disabled={!draft.trim() || loading || sourceLoading || !canClarify}>{loading ? '正在理解…' : session ? '继续澄清' : '开始找桌'} <span>→</span></button>
            </div>
          </form>

          {(error || handoffError) && <p className="intent-error" role="alert">{error || handoffError}</p>}
          {handoffError && (
            <div className="intent-handoff-recovery">
              <button type="button" onClick={returnDraft}>再试一次</button>
              <button type="button" onClick={() => void copyDraft()}>{copyState === 'copied' ? '已复制' : copyState === 'error' ? '复制失败' : '复制这次需求'}</button>
            </div>
          )}

          {session && (
            <section className="intent-result" aria-live="polite">
              <div className="intent-result-heading">
                <div><small>当前判断</small><h3>{routeTitle(session.preview.route)}</h3></div>
                <span>{session.preview.normalized_question}</span>
              </div>

              {session.preview.route === 'clarify' && (
                <>
                  <p className="intent-clarify">{canClarify ? session.preview.clarifying_question : '这次需求已经达到澄清上限，先带回首页继续创建。'}</p>
                  {!canClarify && <button type="button" className="intent-primary" onClick={returnDraft}>带着需求回首页 <span>↗</span></button>}
                </>
              )}

              {session.preview.route === 'join_existing' && (
                <div className="intent-candidates">
                  {session.preview.candidates.map((candidate) => (
                    <article className="intent-candidate" key={candidate.table_id}>
                      <div>
                        <small>{candidate.participant_count} 人 · 还剩 {candidate.available_seats} 个空席</small>
                        <h4>{candidate.core_question}</h4>
                        <p>{candidate.reason}</p>
                      </div>
                      <button
                        type="button"
                        disabled={selectionId === candidate.table_id}
                        onClick={async () => {
                          setSelectionId(candidate.table_id)
                          try {
                            await onSelectTable(candidate.table_id)
                          } catch (reason) {
                            setError(reason instanceof Error ? reason.message : '暂时无法打开这张桌')
                            setSelectionId(null)
                          }
                        }}
                      >{selectionId === candidate.table_id ? '正在打开…' : '去桌边看看'} <span>↗</span></button>
                    </article>
                  ))}
                </div>
              )}

              {session.preview.route === 'new_table' && (
                <div className="intent-new-table">
                  <p>现在没有合适的正在发生的桌。你可以先看一次授权公开来源的候选，或者把这个需求带回首页，由你再次确认后创建；这里不会替你建桌。</p>
                  <div className="intent-new-actions">
                    <button type="button" onClick={searchPublicCandidates} disabled={sourceLoading}>{sourceLoading ? '正在查公开来源…' : '查公开候选'}</button>
                    <button type="button" className="intent-primary" onClick={returnDraft}>带着需求回首页 <span>↗</span></button>
                  </div>
                  {sourceError && <p className="intent-error" role="alert">{sourceError}</p>}
                  {sourcePlan && (
                    <div className="intent-plan">
                      <small>公开来源匹配 · {sourcePlan.selected.length} 位候选</small>
                      {sourcePlan.reasons.map((reason) => <p key={reason.participant_id}><b>{sourcePlan.selected.find((seat) => seat.participant_id === reason.participant_id)?.display_name ?? reason.participant_id}</b>{reason.reason}</p>)}
                      <button type="button" className="intent-primary" disabled={sourceLoading} onClick={confirmPublicPlan}>{sourceLoading ? '正在确认…' : '按这组公开候选确认匹配'} <span>→</span></button>
                    </div>
                  )}
                </div>
              )}

              <div className="intent-history" aria-label="本次需求上下文">
                {session.messages.map((message, index) => <span key={`${index}-${message}`}>{String(index + 1).padStart(2, '0')} {message}</span>)}
              </div>
            </section>
          )}
        </div>
      </section>
    </div>,
    document.body,
  )
}
