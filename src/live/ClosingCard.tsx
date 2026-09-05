import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { fetchActionEchoes, saveRelationship } from './api'
import type { ActionEchoEntryLike, PersonalCardLike, SharedBaselineLike } from './contract'

interface ClosingCardProps {
  tableId: string
  participantId: string
  baseline: SharedBaselineLike
  personalCard: PersonalCardLike | null
  onDismiss(): void
  onReturn(): void
}

export default function ClosingCard({ tableId, participantId, baseline, personalCard, onDismiss, onReturn }: ClosingCardProps) {
  const panelRef = useRef<HTMLElement>(null)
  const dismissButtonRef = useRef<HTMLButtonElement>(null)
  const onDismissRef = useRef(onDismiss)
  onDismissRef.current = onDismiss
  const [savedRelationships, setSavedRelationships] = useState<string[]>([])
  const [savingRelationship, setSavingRelationship] = useState<string | null>(null)
  const [relationshipError, setRelationshipError] = useState<string | null>(null)
  const [actionEchoes, setActionEchoes] = useState<ActionEchoEntryLike[]>([])
  const [actionEchoLoading, setActionEchoLoading] = useState(true)
  const [actionEchoError, setActionEchoError] = useState<string | null>(null)

  useEffect(() => {
    dismissButtonRef.current?.focus({ preventScroll: true })
    const onKeyDown = (event: KeyboardEvent) => {
      if (!panelRef.current) return
      if (event.key === 'Escape') {
        event.preventDefault()
        onDismissRef.current()
        return
      }
      if (event.key !== 'Tab') return
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
  }, [])

  useEffect(() => {
    let active = true
    setActionEchoLoading(true)
    setActionEchoError(null)
    void fetchActionEchoes(participantId).then((items) => {
      if (!active) return
      setActionEchoes(items.filter((item) => item.table_id === tableId))
    }).catch((reason) => {
      if (!active) return
      setActionEchoes([])
      setActionEchoError(reason instanceof Error ? reason.message : '暂时取不到这张桌的行动回响')
    }).finally(() => {
      if (active) setActionEchoLoading(false)
    })
    return () => { active = false }
  }, [participantId, tableId])

  const savePerson = async (relatedParticipantId: string) => {
    if (savingRelationship || savedRelationships.includes(relatedParticipantId)) return
    setSavingRelationship(relatedParticipantId)
    setRelationshipError(null)
    try {
      await saveRelationship(tableId, relatedParticipantId, participantId)
      setSavedRelationships((current) => [...current, relatedParticipantId])
    } catch (reason) {
      setRelationshipError(reason instanceof Error ? reason.message : '这段关系没有保存成功')
    } finally {
      setSavingRelationship(null)
    }
  }

  const actionStatusLabel = (status: ActionEchoEntryLike['status']) => {
    if (status === 'completed') return '已完成'
    if (status === 'in_progress') return '进行中'
    if (status === 'blocked') return '遇到阻碍'
    if (status === 'dismissed') return '已搁置'
    return '尚未回报'
  }

  if (typeof document === 'undefined') return null

  return createPortal(
    <div className="closing-root">
      <div className="closing-veil" role="presentation" aria-hidden="true" onClick={onDismiss} />
      <section className="closing-panel" ref={panelRef} tabIndex={-1} role="dialog" aria-modal="true" aria-labelledby="closing-card-title">
        <p className="closing-kicker">收桌 · 这一桌聊成了什么</p>
        <h2 className="closing-question" id="closing-card-title">
          <small>问题长成了这样</small>
          {baseline.evolved_question.text}
        </h2>

        <div className="closing-grid">
          <div className="closing-block">
            <small>共识</small>
            {baseline.key_consensus.length === 0 && <p className="closing-empty">这一桌还没有沉淀出共识。</p>}
            {baseline.key_consensus.map((item) => (
              <p key={item.text}>{item.text}</p>
            ))}
          </div>
          <div className="closing-block">
            <small>未解决的分歧</small>
            {baseline.unresolved_disagreements.length === 0 && <p className="closing-empty">没有留下悬而未决的分歧。</p>}
            {baseline.unresolved_disagreements.map((item) => (
              <p key={item.text}>{item.text}</p>
            ))}
          </div>
          {baseline.collective_next_steps.length > 0 && (
            <div className="closing-block">
              <small>桌上带走的行动</small>
              {baseline.collective_next_steps.map((item) => (
                <p key={item.text}>{item.is_commitment ? '✓ ' : ''}{item.text}</p>
              ))}
            </div>
          )}
        </div>

        {personalCard && (
          <div className="closing-personal">
            <p className="closing-personal-kicker">你的收桌卡 · 第五席</p>
            <div className="closing-grid">
              {personalCard.what_changed.length > 0 && (
                <div className="closing-block">
                  <small>你的变化</small>
                  {personalCard.what_changed.map((item) => <p key={item.text}>{item.text}</p>)}
                </div>
              )}
              {personalCard.your_contribution.length > 0 && (
                <div className="closing-block">
                  <small>你补上的视角</small>
                  {personalCard.your_contribution.map((item) => <p key={item.text}>{item.text}</p>)}
                </div>
              )}
              {personalCard.worth_continuing_with.length > 0 && (
                <div className="closing-block">
                  <small>值得继续聊的人</small>
                  {personalCard.worth_continuing_with.map((item) => (
                    <div className="closing-relationship" key={item.participant_id}>
                      <p>{item.reason}</p>
                      <button type="button" disabled={Boolean(savingRelationship) || savedRelationships.includes(item.participant_id)} onClick={() => void savePerson(item.participant_id)}>{savedRelationships.includes(item.participant_id) ? '已记住' : savingRelationship === item.participant_id ? '正在保存…' : '记住这个人'}</button>
                    </div>
                  ))}
                  {relationshipError && <em className="closing-inline-error" role="alert">{relationshipError}</em>}
                </div>
              )}
              {personalCard.suggested_next_actions.length > 0 && (
                <div className="closing-block">
                  <small>回响 · 接下来</small>
                  {personalCard.suggested_next_actions.map((item) => <p key={item.text}>{item.text}</p>)}
                </div>
              )}
            </div>
          </div>
        )}

        <div className="closing-action-echoes">
          <div className="closing-action-echoes-heading">
            <small>行动回响</small>
            <span>只显示这张桌留下的真实行动项</span>
          </div>
          {actionEchoLoading && <p className="closing-empty" role="status">正在读取行动回响…</p>}
          {!actionEchoLoading && actionEchoError && <p className="closing-empty" role="alert">{actionEchoError}</p>}
          {!actionEchoLoading && !actionEchoError && actionEchoes.length === 0 && <p className="closing-empty">这张桌暂时没有需要跟进的行动项。</p>}
          {!actionEchoLoading && !actionEchoError && actionEchoes.map((item) => (
            <div className="closing-action-echo" key={`${item.table_id}:${item.follow_up_index}`}>
              <div><small>{item.item_type === 'commitment' ? '承诺' : '建议'} · {actionStatusLabel(item.status)}</small><p>{item.text}</p></div>
              {item.note && <span>{item.note}</span>}
            </div>
          ))}
        </div>

        <div className="closing-echo">
          <span>这道问题长出了下一桌。</span>
          <div className="closing-actions">
            <button ref={dismissButtonRef} type="button" className="closing-dismiss" onClick={onDismiss}>先留在这张桌</button>
            <button type="button" onClick={onReturn}>回到桌单 <i>→</i></button>
          </div>
        </div>
      </section>
    </div>,
    document.body,
  )
}
