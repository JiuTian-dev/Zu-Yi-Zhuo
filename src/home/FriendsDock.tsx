/** @origin HOME — Codex-like friends rail + QQ-style chat popups on profile. */

import { useEffect, useRef, useState, type CSSProperties, type FormEvent } from 'react'
import {
  getFriend,
  getFriends,
  getThread,
  sendFriendMessage,
  subscribeFriendThreads,
  type ChatMessage,
  type FriendProfile,
} from './friendsStore'
import './friends.css'

interface OpenChat {
  friendId: string
  minimized: boolean
  z: number
  left: number
  top: number
}

function FriendAvatar({ friend, size = 40 }: { friend: FriendProfile; size?: number }) {
  return (
    <span
      className="friends-avatar"
      style={{
        width: size,
        height: size,
        background: `hsl(${friend.avatarHue} 42% 48%)`,
      }}
      aria-hidden="true"
    >
      {friend.avatarInitial}
    </span>
  )
}

function formatTime(at: number) {
  return new Date(at).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
}

function QqChatWindow({
  friend,
  messages,
  minimized,
  z,
  left,
  top,
  dockIndex,
  onClose,
  onMinimize,
  onFocus,
  onSend,
}: {
  friend: FriendProfile
  messages: ChatMessage[]
  minimized: boolean
  z: number
  left: number
  top: number
  dockIndex: number
  onClose(): void
  onMinimize(): void
  onFocus(): void
  onSend(text: string): void
}) {
  const [draft, setDraft] = useState('')
  const scroller = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const node = scroller.current
    if (!node || minimized) return
    node.scrollTop = node.scrollHeight
  }, [messages, minimized])

  const submit = (event: FormEvent) => {
    event.preventDefault()
    if (!draft.trim()) return
    onSend(draft)
    setDraft('')
  }

  if (minimized) {
    const dockStyle = { left: 88 + dockIndex * 148, zIndex: z } as CSSProperties
    return (
      <button
        type="button"
        className="qq-chat-dock"
        style={dockStyle}
        onClick={onMinimize}
      >
        <FriendAvatar friend={friend} size={28} />
        <span>{friend.displayName}</span>
      </button>
    )
  }

  return (
    <div
      className="qq-chat-window"
      style={{ left, top, zIndex: z }}
      onMouseDown={onFocus}
      role="dialog"
      aria-label={`与 ${friend.displayName} 聊天`}
    >
      <header className="qq-chat-titlebar">
        <FriendAvatar friend={friend} size={28} />
        <div className="qq-chat-title-copy">
          <b>{friend.displayName}</b>
          <small>{friend.status === 'online' ? '在线' : friend.status === 'away' ? '离开' : '离线'}</small>
        </div>
        <div className="qq-chat-title-actions">
          <button type="button" aria-label="最小化" onClick={onMinimize}>—</button>
          <button type="button" aria-label="关闭" onClick={onClose}>×</button>
        </div>
      </header>

      <div className="qq-chat-body" ref={scroller}>
        {messages.length === 0 && (
          <p className="qq-chat-empty">还没有消息，打个招呼吧。</p>
        )}
        {messages.map((message) => (
          <div
            key={message.id}
            className={`qq-chat-bubble-row ${message.from === 'me' ? 'is-me' : 'is-friend'}`}
          >
            {message.from === 'friend' && <FriendAvatar friend={friend} size={32} />}
            <div className="qq-chat-bubble">
              <p>{message.text}</p>
              <time dateTime={new Date(message.at).toISOString()}>{formatTime(message.at)}</time>
            </div>
          </div>
        ))}
      </div>

      <form className="qq-chat-composer" onSubmit={submit}>
        <textarea
          rows={2}
          placeholder="输入消息，Enter 发送"
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter' && !event.shiftKey) {
              event.preventDefault()
              if (draft.trim()) {
                onSend(draft)
                setDraft('')
              }
            }
          }}
        />
        <button type="submit">发送</button>
      </form>
    </div>
  )
}

export default function FriendsDock() {
  const [open, setOpen] = useState(false)
  const [friends] = useState(() => getFriends())
  const [, setTick] = useState(0)
  const [chats, setChats] = useState<OpenChat[]>([])
  const zCounter = useRef(40)

  useEffect(() => subscribeFriendThreads(() => setTick((value) => value + 1)), [])

  useEffect(() => {
    if (!open) return
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open])

  const openChat = (friendId: string) => {
    zCounter.current += 1
    setChats((current) => {
      const existing = current.find((chat) => chat.friendId === friendId)
      if (existing) {
        return current.map((chat) => (
          chat.friendId === friendId
            ? { ...chat, minimized: false, z: zCounter.current }
            : chat
        ))
      }
      const index = current.length
      // Center of viewport, slight offset when multiple windows are open.
      const width = Math.min(480, typeof window !== 'undefined' ? window.innerWidth - 32 : 480)
      const height = Math.min(620, typeof window !== 'undefined' ? window.innerHeight - 56 : 620)
      const left = Math.max(12, (window.innerWidth - width) / 2 + (index % 3) * 28)
      const top = Math.max(24, (window.innerHeight - height) / 2 + (index % 3) * 24)
      return [
        ...current,
        {
          friendId,
          minimized: false,
          z: zCounter.current,
          left,
          top,
        },
      ]
    })
  }

  const minimizedChats = chats.filter((chat) => chat.minimized)

  return (
    <>
      <div className={`friends-dock ${open ? 'is-open' : ''}`}>
        <button
          type="button"
          className="friends-rail-btn"
          aria-expanded={open}
          aria-controls="friends-sidebar"
          onClick={() => setOpen((value) => !value)}
        >
          <span className="friends-rail-icon" aria-hidden="true" />
          <span>好友</span>
        </button>

        <aside
          id="friends-sidebar"
          className="friends-sidebar"
          aria-hidden={!open}
          aria-label="好友列表"
        >
          <header className="friends-sidebar-head">
            <div>
              <b>好友</b>
              <small>演示名单 · 本地聊天</small>
            </div>
            <button type="button" aria-label="收起侧栏" onClick={() => setOpen(false)}>收起</button>
          </header>

          <ul className="friends-list">
            {friends.map((friend) => (
              <li key={friend.id}>
                <button type="button" className="friends-list-item" onClick={() => openChat(friend.id)}>
                  <span className="friends-list-avatar-wrap">
                    <FriendAvatar friend={friend} size={42} />
                    <i className={`friends-status is-${friend.status}`} aria-hidden="true" />
                  </span>
                  <span className="friends-list-copy">
                    <b>{friend.displayName}</b>
                    <span>{friend.motto}</span>
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </aside>

        {open && (
          <button
            type="button"
            className="friends-scrim"
            aria-label="关闭好友侧栏"
            onClick={() => setOpen(false)}
          />
        )}
      </div>

      {chats.map((chat) => {
        const friend = getFriend(chat.friendId)
        if (!friend) return null
        const dockIndex = minimizedChats.findIndex((item) => item.friendId === chat.friendId)
        return (
          <QqChatWindow
            key={chat.friendId}
            friend={friend}
            messages={getThread(chat.friendId)}
            minimized={chat.minimized}
            z={chat.z}
            left={chat.left}
            top={chat.top}
            dockIndex={Math.max(0, dockIndex)}
            onClose={() => setChats((current) => current.filter((item) => item.friendId !== chat.friendId))}
            onMinimize={() => {
              zCounter.current += 1
              setChats((current) => current.map((item) => (
                item.friendId === chat.friendId
                  ? { ...item, minimized: !item.minimized, z: zCounter.current }
                  : item
              )))
            }}
            onFocus={() => {
              zCounter.current += 1
              setChats((current) => current.map((item) => (
                item.friendId === chat.friendId ? { ...item, z: zCounter.current } : item
              )))
            }}
            onSend={(text) => { sendFriendMessage(chat.friendId, text) }}
          />
        )
      })}
    </>
  )
}
