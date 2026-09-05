import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import {
  fetchActionEchoes,
  fetchInvitationInbox,
  fetchRelationshipMemory,
  fetchSavedTables,
  respondInvitation,
} from './api'
import type {
  ActionEchoEntryLike,
  InvitationInboxItemLike,
  ParticipantSavedTablesLike,
  RelationshipMemoryLike,
} from './contract'
import { VIEWER_ID } from './identity'

/**
 * HOME-OWNED ACCOUNT SURFACE — kept as an integration module for the
 * teammate-owned homepage. It is intentionally not mounted by the matching
 * page or the table room.
 */

interface RelationshipPanelProps {
  open: boolean
  onClose(): void
  onRevisit(tableId: string): Promise<void>
}

export default function RelationshipPanel({ open, onClose, onRevisit }: RelationshipPanelProps) {
  const panelRef = useRef<HTMLElement>(null)
  const closeButtonRef = useRef<HTMLButtonElement>(null)
  const [memories, setMemories] = useState<RelationshipMemoryLike[]>([])
  const [echoes, setEchoes] = useState<ActionEchoEntryLike[]>([])
  const [savedTables, setSavedTables] = useState<ParticipantSavedTablesLike | null>(null)
  const [invitations, setInvitations] = useState<InvitationInboxItemLike[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [pendingInvitation, setPendingInvitation] = useState<string | null>(null)

  const load = () => {
    setLoading(true)
    setError(null)
    void Promise.all([
      fetchRelationshipMemory(VIEWER_ID),
      fetchActionEchoes(VIEWER_ID),
      fetchSavedTables(VIEWER_ID),
      fetchInvitationInbox(VIEWER_ID),
    ]).then(([nextMemories, nextEchoes, nextSaved, nextInvitations]) => {
      setMemories(nextMemories)
      setEchoes(nextEchoes)
      setSavedTables(nextSaved)
      setInvitations(nextInvitations.items)
    }).catch((reason) => {
      setError(reason instanceof Error ? reason.message : '暂时取不到你的桌边回响')
    }).finally(() => setLoading(false))
  }

  useEffect(() => {
    if (!open) return
    load()
    window.requestAnimationFrame(() => closeButtonRef.current?.focus({ preventScroll: true }))
  }, [open])

  useEffect(() => {
    if (!open) return
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') { event.preventDefault(); onClose(); return }
      if (event.key !== 'Tab' || !panelRef.current) return
      const focusable = Array.from(panelRef.current.querySelectorAll<HTMLElement>('button:not([disabled]), [href], [tabindex]:not([tabindex="-1"])'))
      if (!focusable.length) return
      const first = focusable[0]
      const last = focusable[focusable.length - 1]
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus() }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus() }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [onClose, open])

  if (!open || typeof document === 'undefined') return null

  const revisit = async (tableId: string) => {
    setError(null)
    try {
      await onRevisit(tableId)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '这张桌暂时不能重新打开')
    }
  }

  const respond = async (item: InvitationInboxItemLike, accept: boolean) => {
    const key = `${item.invitation.table_id}:${item.invitation.invitation_id}`
    if (pendingInvitation) return
    setPendingInvitation(key)
    setError(null)
    try {
      await respondInvitation(item.invitation.table_id, item.invitation.invitation_id, VIEWER_ID, accept)
      if (accept) await onRevisit(item.invitation.table_id)
      else load()
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '邀请状态没有更新成功')
    } finally {
      setPendingInvitation(null)
    }
  }

  return createPortal(
    <div className="relationship-root">
      <button className="intent-veil" type="button" aria-label="关闭我的回响" onClick={onClose} />
      <section className="relationship-panel intent-panel" ref={panelRef} role="dialog" aria-modal="true" aria-labelledby="relationship-title">
        <header className="intent-header">
          <div><p className="intent-kicker">你的桌边回响 · 后端记录</p><h2 id="relationship-title">有些相遇，不该只发生一次</h2></div>
          <button ref={closeButtonRef} className="intent-close" type="button" aria-label="关闭我的回响" onClick={onClose}>×</button>
        </header>
        <div className="relationship-body">
          {loading && <p className="relationship-state" role="status">正在从你的账户记录里取回回响…</p>}
          {error && <p className="intent-error" role="alert">{error} <button type="button" onClick={load}>重新读取</button></p>}
          {!loading && !error && (
            <>
              <section className="relationship-section">
                <div className="relationship-section-title"><span>值得继续聊的人 <small>来自已收束桌的证据</small></span></div>
                {memories.length ? memories.map((memory) => (
                  <article className="relationship-item" key={`${memory.table_id}:${memory.participant_id}`}>
                    <div><small>{memory.core_question}</small><h3>{memory.display_name}</h3><p>{memory.reason}</p><em>依据第 {memory.evidence_turns.join('、')} 轮</em></div>
                    <button type="button" onClick={() => void revisit(memory.table_id)}>再次遇见 <span>↗</span></button>
                  </article>
                )) : <p className="relationship-empty">收束一张桌之后，这里会留下真正有证据的关系提醒。</p>}
              </section>

              <section className="relationship-section">
                <div className="relationship-section-title"><span>行动回响 <small>来自收桌卡</small></span></div>
                {echoes.length ? echoes.map((echo) => (
                  <article className="relationship-item" key={`${echo.table_id}:${echo.follow_up_index}`}>
                    <div><small>{echo.item_type === 'commitment' ? '承诺' : '建议'} · {echo.status ?? '未反馈'}</small><h3>{echo.text}</h3>{echo.note && <p>{echo.note}</p>}</div>
                    <button type="button" onClick={() => void revisit(echo.table_id)}>回到这桌 <span>↗</span></button>
                  </article>
                )) : <p className="relationship-empty">桌面留下行动之后，它的状态会在这里持续。</p>}
              </section>

              <section className="relationship-section">
                <div className="relationship-section-title"><span>收到的邀请 <small>{invitations.length} 条</small></span></div>
                {invitations.length ? invitations.map((item) => {
                  const key = `${item.invitation.table_id}:${item.invitation.invitation_id}`
                  return <article className="relationship-item" key={key}>
                    <div><small>{item.table.core_question}</small><h3>{item.invitation.display_name} 邀请你入席</h3><p>{item.invitation.reason}</p></div>
                    {item.can_respond ? <div className="relationship-actions"><button type="button" disabled={Boolean(pendingInvitation)} onClick={() => void respond(item, false)}>拒绝</button><button type="button" className="intent-primary" disabled={Boolean(pendingInvitation)} onClick={() => void respond(item, true)}>{pendingInvitation === key ? '处理中…' : '接受并去桌边'} <span>→</span></button></div> : <small className="relationship-muted">{item.unavailable_reason ?? '邀请已失效'}</small>}
                  </article>
                }) : <p className="relationship-empty">暂时没有待处理邀请。</p>}
              </section>

              <section className="relationship-section">
                <div className="relationship-section-title"><span>稍后再看 <small>你主动保存的桌</small></span></div>
                {savedTables?.items.length ? savedTables.items.map((item) => <article className="relationship-item" key={item.table_id}><div><small>{item.lobby.participant_count} 人 · {item.lobby.status}</small><h3>{item.lobby.core_question}</h3><p>{item.lobby.missing_perspective}</p></div><button type="button" onClick={() => void revisit(item.table_id)}>打开桌边 <span>↗</span></button></article>) : <p className="relationship-empty">这里会放你明确想稍后再看的桌。</p>}
              </section>
            </>
          )}
        </div>
        <footer className="relationship-footer"><span>只显示这个浏览器会话所属账户的记录</span><button type="button" onClick={onClose}>回到桌单 <i>→</i></button></footer>
      </section>
    </div>,
    document.body,
  )
}
