import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from 'react'
import type { ParticipantResponseStatusLike, StageSummaryLike } from './contract'
import type { LiveMessage } from './store'

interface ConversationSurfaceProps {
  messages: LiveMessage[]
  summary: StageSummaryLike | null
  summaryPending: boolean
  canSend: boolean
  draft: string
  retryingMessageId: string | null
  viewerId?: string
  responses: ParticipantResponseStatusLike[]
  onRetryResponse(): void
  onTyping(active: boolean): void
  speakerName(participantId: string): string
  onDraftChange(value: string): void
  onSend(): void
  onRetry(messageId: string): void
  onOpenSummary(): void
}

export default function ConversationSurface({ messages, summary, summaryPending, canSend, draft,
  retryingMessageId, viewerId, responses, onRetryResponse, onTyping, speakerName, onDraftChange, onSend, onRetry, onOpenSummary }: ConversationSurfaceProps) {
  const streamRef = useRef<HTMLDivElement>(null)
  const composerRef = useRef<HTMLTextAreaElement>(null)
  const [followingLatest, setFollowingLatest] = useState(true)
  const [unreadCount, setUnreadCount] = useState(0)
  const previousMessageCount = useRef(messages.length)

  const scrollToLatest = (behavior: ScrollBehavior = 'smooth') => {
    const stream = streamRef.current
    if (!stream) return
    stream.scrollTo({ top: stream.scrollHeight, behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : behavior })
    setFollowingLatest(true)
    setUnreadCount(0)
  }

  useEffect(() => {
    const added = Math.max(0, messages.length - previousMessageCount.current)
    previousMessageCount.current = messages.length
    if (!added) return
    if (followingLatest) window.requestAnimationFrame(() => scrollToLatest('smooth'))
    else setUnreadCount((current) => current + added)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [messages.length, followingLatest])

  useEffect(() => {
    const field = composerRef.current
    if (!field) return
    field.style.height = '0px'
    field.style.height = `${Math.min(field.scrollHeight, 132)}px`
  }, [draft])

  useEffect(() => {
    if (followingLatest) streamRef.current?.scrollTo({ top: streamRef.current.scrollHeight, behavior: 'auto' })
  }, [summary?.summary_id, summary?.revision, summaryPending, followingLatest])

  const submit = (event?: FormEvent) => {
    event?.preventDefault()
    if (!canSend || !draft.trim()) return
    onSend()
  }

  const onComposerKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key !== 'Enter' || event.shiftKey || event.nativeEvent.isComposing) return
    event.preventDefault()
    submit()
  }

  const summaryAfterTurn = summary?.covered_turn_end
  let summaryRendered = false
  const renderSummary = () => {
    if (summaryRendered || (!summary && !summaryPending)) return null
    summaryRendered = true
    return <button className="conversation-summary" type="button" onClick={onOpenSummary}>
      <span>{summaryPending ? '正在整理' : '阶段小结'}</span>
      {summary?.clarified[0] && <strong>{summary.clarified[0].text}</strong>}
      {summary?.next_focus && <small>{summary.next_focus.text}</small>}
    </button>
  }

  return <section className="conversation-surface" aria-label="桌内聊天">
    <div ref={streamRef} className="conversation-stream" onScroll={(event) => {
      const node = event.currentTarget
      const atBottom = node.scrollHeight - node.scrollTop - node.clientHeight < 36
      setFollowingLatest(atBottom)
      if (atBottom) setUnreadCount(0)
    }}>
      {messages.length === 0 && <p className="conversation-empty">从你真正想说的地方开始。</p>}
      {messages.map((message, index) => {
        const showSummaryAfter = Boolean(summaryAfterTurn && message.turnId === summaryAfterTurn)
        return <div key={message.messageId ?? `${message.participantId}-${message.turnId ?? index}`}>
          <article className={`conversation-message ${message.fromHost ? 'is-host' : ''} ${message.participantId === viewerId ? 'is-self' : ''}`} data-turn-id={message.turnId} tabIndex={message.turnId ? -1 : undefined}>
            <header>{speakerName(message.participantId)}</header>
            <p>{message.text}</p>
            {message.delivery === 'pending' && <small>发送中</small>}
            {message.delivery === 'failed' && message.messageId && <button type="button" onClick={() => onRetry(message.messageId!)} disabled={retryingMessageId === message.messageId}>{retryingMessageId === message.messageId ? '重试中' : '重新发送'}</button>}
          </article>
          {showSummaryAfter && renderSummary()}
        </div>
      })}
      {!summaryRendered && renderSummary()}
    </div>
    {!followingLatest && unreadCount > 0 && <button className="conversation-unread" type="button" onClick={() => scrollToLatest()}>{unreadCount} 条新消息</button>}
    <div className="conversation-response" role="status" aria-live="polite" aria-atomic="true">
      {responses.some((response) => response.status === 'thinking') ? <>
        <span className="response-dots" aria-hidden="true"><i /><i /><i /></span>
        <span>{responses.filter((response) => response.status === 'thinking').map((response) => speakerName(response.participant_id)).join('、')}正在输入</span>
      </> : responses.some((response) => response.status === 'failed') ? <>
        <span>暂时没接上</span><button type="button" onClick={onRetryResponse} disabled={!canSend}>重试</button>
      </> : summaryPending ? <><span className="response-dots" aria-hidden="true"><i /><i /><i /></span><span>正在整理小结</span></> : null}
    </div>
    {canSend && <form className="conversation-composer" onSubmit={submit}>
      <textarea ref={composerRef} value={draft} onChange={(event) => { onDraftChange(event.target.value); onTyping(Boolean(event.target.value.trim())) }} onBlur={() => onTyping(false)} onKeyDown={onComposerKeyDown} placeholder="说点什么" aria-label="对这桌发言" rows={1} maxLength={1000} />
      <button type="submit" aria-label="发送" disabled={!draft.trim()}>发送</button>
    </form>}
  </section>
}
