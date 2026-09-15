import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { connectDemoFriend } from '../home/friendsStore'
import { fetchActionEchoes, saveRelationship } from './api'
import type { ActionEchoEntryLike, PersonalCardLike, SharedBaselineLike } from './contract'
import CharacterPortrait, { characterForPerson, viewerCharacter } from './CharacterPortrait'

interface ClosingCardProps {
  tableId: string
  participantId: string
  baseline: SharedBaselineLike
  personalCard: PersonalCardLike | null
  simulatedParticipantIds?: string[]
  tableMembers?: Array<{ participant_id: string; display_name: string; role: string }>
  onReturnLabel?: string
  onDismiss(): void
  onReturn(): void
}

export default function ClosingCard({ tableId, participantId, baseline, personalCard, simulatedParticipantIds = [], tableMembers = [], onReturnLabel = '回到桌单', onDismiss, onReturn }: ClosingCardProps) {
  const panelRef = useRef<HTMLElement>(null)
  const dismissButtonRef = useRef<HTMLButtonElement>(null)
  const onDismissRef = useRef(onDismiss)
  onDismissRef.current = onDismiss
  const [savedRelationships, setSavedRelationships] = useState<string[]>([])
  const [savingRelationship, setSavingRelationship] = useState<string | null>(null)
  const [relationshipError, setRelationshipError] = useState<string | null>(null)
  const [demoConnections, setDemoConnections] = useState<string[]>([])
  const [actionEchoes, setActionEchoes] = useState<ActionEchoEntryLike[]>([])
  const [actionEchoLoading, setActionEchoLoading] = useState(true)
  const [actionEchoError, setActionEchoError] = useState<string | null>(null)
  const continuingWith = personalCard?.worth_continuing_with.filter((item) => !simulatedParticipantIds.includes(item.participant_id)) ?? []
  const simulatedPeople = tableMembers.filter((member) => simulatedParticipantIds.includes(member.participant_id))

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

  const connectPerson = (person: (typeof simulatedPeople)[number]) => {
    connectDemoFriend({ id: person.participant_id, displayName: person.display_name, role: person.role })
    setDemoConnections((current) => current.includes(person.participant_id) ? current : [...current, person.participant_id])
  }

  if (typeof document === 'undefined') return null

  return createPortal(
    <div className="closing-root">
      <div className="closing-veil" role="presentation" aria-hidden="true" onClick={onDismiss} />
      <section className="closing-panel" ref={panelRef} tabIndex={-1} role="dialog" aria-modal="true" aria-labelledby="closing-card-title">
        <header className="closing-hero">
          <div className="closing-cast" aria-label="本桌成员">
            <CharacterPortrait character="host" label="阿桌" className="closing-cast-avatar" online />
            {simulatedPeople.slice(0, 3).map((person) => <CharacterPortrait
              key={person.participant_id}
              character={characterForPerson(person.display_name, person.participant_id, participantId)}
              label={person.display_name}
              className="closing-cast-avatar"
            />)}
            <CharacterPortrait character={viewerCharacter()} label="你" className="closing-cast-avatar is-you" />
          </div>
          <h2 className="closing-question" id="closing-card-title">
            <small>这一桌没有结束，它变成了一个更好的问题</small>
            {baseline.evolved_question.text}
          </h2>
          <p>阿桌已把讨论里的共识、分歧与关系线索整理成一张可带走的桌后卡。</p>
        </header>

        <div className="closing-grid">
          {baseline.key_consensus.length > 0 && <div className="closing-block">
            <small>聊清楚了</small>
            {baseline.key_consensus.map((item) => (
              <p key={item.text}>{item.text}</p>
            ))}
          </div>}
          {baseline.unresolved_disagreements.length > 0 && <div className="closing-block">
            <small>未解决的分歧</small>
            {baseline.unresolved_disagreements.map((item) => (
              <p key={item.text}>{item.text}</p>
            ))}
          </div>}
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
            <div className="closing-personal-title">
              <CharacterPortrait character={viewerCharacter()} label="你" className="closing-personal-avatar" />
              <p><span className="closing-personal-kicker">阿桌写给你的桌后回信</span><strong>你不是来证明答案，而是给讨论补上了一个位置。</strong></p>
            </div>
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
              {continuingWith.length > 0 && (
                <div className="closing-block">
                  <small>值得继续聊的人</small>
                  {continuingWith.map((item) => (
                    <div className="closing-relationship" key={item.participant_id}>
                      <p>{item.reason}</p>
                      {!simulatedParticipantIds.includes(item.participant_id) && <button type="button" disabled={Boolean(savingRelationship) || savedRelationships.includes(item.participant_id)} onClick={() => void savePerson(item.participant_id)}>{savedRelationships.includes(item.participant_id) ? '已记住' : savingRelationship === item.participant_id ? '正在保存…' : '记住这个人'}</button>}
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

        {simulatedPeople.length > 0 && <section className="closing-social-result">
          <div className="closing-social-heading">
            <p><small>一次好讨论的社交结果</small><strong>不是互关，而是知道为什么还想再见</strong></p>
            <span>{demoConnections.length ? `${demoConnections.length} 位新桌友` : '选择一位继续认识'}</span>
          </div>
          <div className="closing-social-people">
            {simulatedPeople.map((person) => {
              const connected = demoConnections.includes(person.participant_id)
              const reason = person.display_name === '林夏'
                ? '她把离开之后真实获得的陪伴与必须承担的代价都说清楚了。'
                : person.display_name === '周砚'
                  ? '他提醒你：城市也是关系和机会网络，选择可以先做低成本试验。'
                  : '他帮你把“勇敢或逃避”拆成了掌控感、支持系统与可逆性。'
              return <article key={person.participant_id}>
                <CharacterPortrait character={characterForPerson(person.display_name, person.participant_id, participantId)} label={person.display_name} className="closing-person-avatar" online />
                <div><b>{person.display_name}</b><small>{person.role}</small><p>{reason}</p></div>
                <button type="button" className={connected ? 'is-connected' : ''} onClick={() => connectPerson(person)} disabled={connected}>
                  {connected ? '已成为桌友' : '继续认识'}
                </button>
              </article>
            })}
          </div>
          {demoConnections.length > 0 && <p className="closing-social-proof" role="status">关系已带回首页“好友”栏，并收到一条继续讨论的消息。</p>}
        </section>}

        {(actionEchoLoading || actionEchoError || actionEchoes.length > 0) && <div className="closing-action-echoes">
          <div className="closing-action-echoes-heading">
            <small>行动回响</small>
          </div>
          {actionEchoLoading && <p className="closing-empty" role="status">正在读取行动回响…</p>}
          {!actionEchoLoading && actionEchoError && <p className="closing-empty" role="alert">{actionEchoError}</p>}
          {!actionEchoLoading && !actionEchoError && actionEchoes.map((item) => (
            <div className="closing-action-echo" key={`${item.table_id}:${item.follow_up_index}`}>
              <div><small>{item.item_type === 'commitment' ? '承诺' : '建议'} · {actionStatusLabel(item.status)}</small><p>{item.text}</p></div>
              {item.note && <span>{item.note}</span>}
            </div>
          ))}
        </div>}

        <div className="closing-echo">
          <div className="closing-actions">
            <button ref={dismissButtonRef} type="button" className="closing-dismiss" onClick={onDismiss}>关闭</button>
            <button type="button" onClick={onReturn}>{onReturnLabel}</button>
          </div>
        </div>
      </section>
    </div>,
    document.body,
  )
}
