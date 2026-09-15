import { useEffect, useId, useMemo, useRef, useState, type FormEvent } from 'react'
import { createPortal } from 'react-dom'
import { chatWithProfileAgent, type ProfileAgentMessageLike, type ProfileAgentResponseLike } from '../live/api'
import CharacterPortrait, { viewerCharacter } from '../live/CharacterPortrait'
import { VIEWER_ID } from '../live/identity'
import {
  buildAgentTagProfile,
  getTagProfile,
  saveTagProfile,
  type ProfileTag,
  type TagProfile,
} from './profileStore'
import './tagOnboarding.css'

const PERSPECTIVES = ['基于事实', '基于经验', '基于理论', '善于追问']
const MIN_MESSAGE_LENGTH = 12

interface TagOnboardingProps {
  open: boolean
  displayName: string
  required?: boolean
  fresh?: boolean
  onClose(): void
  onComplete(profile: TagProfile): void
}

function openingLine(displayName: string) {
  return `你好，${displayName}。先不用填表，像和刚认识的人一样聊聊：最近哪件事让你特别想找人坐下来谈谈？`
}

function visibleDraftTags(draft: ProfileAgentResponseLike | null): string[] {
  if (!draft) return []
  return [draft.role_tag, draft.experience_tag, ...draft.interest_tags, ...draft.perspective_tags]
    .map((item) => item.trim())
    .filter(Boolean)
    .slice(0, 7)
}

function perspectiveTag(label: string): ProfileTag {
  return { id: `perspective-user-${label}`, kind: 'perspective', label, visible: true }
}

export default function TagOnboarding({
  open,
  displayName,
  required = false,
  fresh = false,
  onClose,
  onComplete,
}: TagOnboardingProps) {
  const titleId = useId()
  const inputHintId = useId()
  const inputRef = useRef<HTMLTextAreaElement>(null)
  const [messages, setMessages] = useState<ProfileAgentMessageLike[]>([])
  const [input, setInput] = useState('')
  const [profile, setProfile] = useState<TagProfile | null>(null)
  const [draftProfile, setDraftProfile] = useState<ProfileAgentResponseLike | null>(null)
  const [pending, setPending] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!open) return
    const existing = fresh ? null : getTagProfile(displayName)
    setProfile(existing)
    setDraftProfile(null)
    setMessages(existing?.conversation ?? [{ role: 'agent', text: openingLine(displayName) }])
    setInput('')
    setPending(false)
    setError('')
    window.requestAnimationFrame(() => inputRef.current?.focus({ preventScroll: true }))
  }, [displayName, fresh, open])

  const userTurns = useMemo(() => messages.filter((message) => message.role === 'user').length, [messages])
  const draftTags = useMemo(() => visibleDraftTags(draftProfile), [draftProfile])
  const progress = profile ? 3 : userTurns >= 1 ? 2 : 1
  const inputLength = input.trim().length

  if (!open) return null

  const submitMessage = async (event: FormEvent) => {
    event.preventDefault()
    if (pending || profile) return
    const value = input.trim()
    if (value.length < MIN_MESSAGE_LENGTH) {
      return
    }
    const nextMessages: ProfileAgentMessageLike[] = [...messages, { role: 'user', text: value }]
    setMessages(nextMessages)
    setInput('')
    setError('')
    setPending(true)
    try {
      const response = await chatWithProfileAgent(VIEWER_ID, displayName, nextMessages)
      const completedMessages: ProfileAgentMessageLike[] = [...nextMessages, { role: 'agent', text: response.reply }]
      setMessages(completedMessages)
      setDraftProfile(response)
      if (response.ready) {
        setProfile(buildAgentTagProfile(displayName, response, completedMessages))
      } else {
        window.requestAnimationFrame(() => inputRef.current?.focus({ preventScroll: true }))
      }
    } catch (requestError) {
      const message = requestError instanceof Error ? requestError.message : '画像 Agent 暂时没有回应'
      setMessages(messages)
      setInput(value)
      setError(`${message}。你的原话已保留，直接再试一次。`)
    } finally {
      setPending(false)
    }
  }

  const togglePerspective = (label: string) => {
    setProfile((current) => {
      if (!current) return current
      const exists = current.tags.some((item) => item.kind === 'perspective' && item.label === label)
      const remaining = current.tags.filter((item) => !(item.kind === 'perspective' && item.label === label))
      const activeCount = remaining.filter((item) => item.kind === 'perspective').length
      if (exists && activeCount === 0) return current
      return { ...current, tags: exists ? remaining : [...remaining, perspectiveTag(label)] }
    })
  }

  const updateTag = (id: string, label: string) => {
    setProfile((current) => current ? {
      ...current,
      tags: current.tags.map((item) => item.id === id ? { ...item, label: label.slice(0, 22) } : item),
    } : current)
  }

  const toggleVisibility = (id: string) => {
    setProfile((current) => current ? {
      ...current,
      tags: current.tags.map((item) => item.id === id ? { ...item, visible: !item.visible } : item),
    } : current)
  }

  const restart = () => {
    setProfile(null)
    setDraftProfile(null)
    setMessages([{ role: 'agent', text: openingLine(displayName) }])
    setInput('')
    setError('')
    window.requestAnimationFrame(() => inputRef.current?.focus({ preventScroll: true }))
  }

  const finish = () => {
    if (!profile) return
    const next = { ...profile, updatedAt: new Date().toISOString() }
    saveTagProfile(next)
    onComplete(next)
  }

  return createPortal(
    <div className="tag-guide-root">
      {required
        ? <div className="tag-guide-scrim" aria-hidden="true" />
        : <button className="tag-guide-scrim" type="button" aria-label="稍后再设置" onClick={onClose} />}
      <section className="tag-guide" role="dialog" aria-modal="true" aria-labelledby={titleId}>
        <div className="tag-guide-landscape" aria-hidden="true" />
        <header className="tag-guide-head">
          <div className="tag-agent-mark" aria-hidden="true">桌</div>
          <div>
            <small>组一桌 · 一次安心的初次见面</small>
            <h2 id={titleId}>{profile ? '这是我刚刚听见的你' : `先聊两句，${displayName}`}</h2>
          </div>
          {!required && <button type="button" className="tag-guide-close" onClick={onClose} aria-label="关闭">×</button>}
        </header>

        <div className="tag-guide-main">
          <aside className="tag-agent-presence">
            <div className="tag-agent-scene">
              <i className="tag-agent-halo" aria-hidden="true" />
              <CharacterPortrait character="host" label="桌边 Agent 阿桌" className="tag-agent-hero" online />
            </div>
            <small>Agent · 你的桌边引路人</small>
            <h3>阿桌</h3>
            <p>“这里没有标准答案。慢慢说，我会先听懂你，再帮你找到值得聊的人。”</p>
            <div className="tag-safety-notes"><span>不评判</span><span>不催促</span><span>可修改</span></div>
          </aside>

          <div className="tag-dialog-column">
            <div className="tag-progress" aria-label="画像进度">
              {['听见你', '再懂一点', '为你找桌'].map((label, index) => (
                <div className={progress > index ? 'is-active' : ''} key={label}>
                  <span>{progress > index + 1 || profile ? '✓' : index + 1}</span>
                  <b>{label}</b>
                </div>
              ))}
            </div>

            <div className="tag-guide-body">
          {!profile ? (
            <>
              <div className="tag-conversation" aria-live="polite">
                {messages.map((message, index) => (
                  <div className={`tag-message is-${message.role}`} key={`${message.role}-${index}`}>
                    {message.role === 'agent' && <CharacterPortrait character="host" label="阿桌" className="tag-message-avatar" online />}
                    <div><small>{message.role === 'agent' ? '阿桌 · Agent' : '你'}</small><p>{message.text}</p></div>
                    {message.role === 'user' && <CharacterPortrait character={viewerCharacter()} label="你" className="tag-message-avatar" />}
                  </div>
                ))}
                {pending && (
                  <div className="tag-message is-agent is-typing">
                    <CharacterPortrait character="host" label="阿桌正在倾听" className="tag-message-avatar" online />
                    <div><small>阿桌 · Agent</small><p><i /><i /><i /><em>正在认真听你说</em></p></div>
                  </div>
                )}
              </div>

              {draftTags.length > 0 && (
                <aside className="tag-forming">
                  <span>匹配画像正在形成</span>
                  <div>{draftTags.map((label) => <b key={label}>{label}</b>)}</div>
                </aside>
              )}

              <form className="tag-compose" onSubmit={submitMessage}>
                <textarea
                  ref={inputRef}
                  value={input}
                  maxLength={280}
                  minLength={MIN_MESSAGE_LENGTH}
                  aria-describedby={inputHintId}
                  disabled={pending}
                  placeholder={userTurns === 0 ? '不用套话，说一件你真的在意的事……' : '顺着刚才的话继续说，你可以纠正 Agent 的理解……'}
                  onChange={(event) => { setInput(event.target.value); setError('') }}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter' && !event.shiftKey) {
                      event.preventDefault()
                      event.currentTarget.form?.requestSubmit()
                    }
                  }}
                />
                <button type="submit" disabled={pending || inputLength < MIN_MESSAGE_LENGTH}>
                  {pending ? '倾听中' : '发送'} <span aria-hidden="true">↗</span>
                </button>
              </form>
              <div className="tag-compose-meta">
                <span id={inputHintId} className={`tag-compose-guidance ${inputLength > 0 && inputLength < MIN_MESSAGE_LENGTH ? 'is-short' : ''}`}>
                  {inputLength >= MIN_MESSAGE_LENGTH ? `这句话够具体了 · ${inputLength} 字` : `至少 ${MIN_MESSAGE_LENGTH} 字，最好带一件真实经历 · ${inputLength}/${MIN_MESSAGE_LENGTH}`}
                </span>
                <span>{userTurns}/2 轮自由表达</span>
              </div>
              {error && <p className="tag-guide-error" role="alert"><b>阿桌暂时没接上</b>{error}</p>}
            </>
          ) : (
            <div className="tag-review">
              <div className="tag-insight-card">
                <CharacterPortrait character={viewerCharacter()} label="你的桌边形象" className="tag-profile-portrait" />
                <div><small>阿桌眼中的你</small>
                  <p>{profile.summary || `${profile.seatLabel}，愿意带着真实经历认识不同视角的人。`}</p>
                  <span>这只是我的理解，你随时可以修改。</span>
                </div>
              </div>

              <div className="tag-fields">
                {profile.tags.filter((item) => item.kind !== 'perspective').map((item) => (
                  <label key={item.id} className="tag-field">
                    <span>{item.kind === 'role' ? '此刻身份' : item.kind === 'experience' ? '真实经历' : '兴趣线索'}</span>
                    <input value={item.label} onChange={(event) => updateTag(item.id, event.target.value)} />
                    <button type="button" className={item.visible ? 'is-visible' : ''} onClick={() => toggleVisibility(item.id)}>
                      {item.visible ? '身份牌公开' : '仅参与匹配'}
                    </button>
                  </label>
                ))}
              </div>

              <div className="tag-perspectives">
                <span>我更常从这些角度加入讨论</span>
                <div>{PERSPECTIVES.map((label) => {
                  const selected = profile.tags.some((item) => item.kind === 'perspective' && item.label === label)
                  return <button type="button" className={selected ? 'is-selected' : ''} key={label} onClick={() => togglePerspective(label)}>{label}</button>
                })}</div>
              </div>

              <label className="tag-seat-label">
                <span>上桌后，我的身份牌</span>
                <input value={profile.seatLabel} maxLength={24} onChange={(event) => setProfile({ ...profile, seatLabel: event.target.value })} />
              </label>

              <div className="tag-match-rule">
                <b>接下来怎么匹配</b>
                <span>话题交集 × 视角互补 × 可分享的真实经历</span>
              </div>
              <div className="tag-guide-actions is-final">
                <button type="button" className="is-ghost" onClick={restart}>重新聊一次</button>
                <button type="button" onClick={finish}>确认画像，让 Agent 带我找桌 <span aria-hidden="true">→</span></button>
              </div>
            </div>
          )}
            </div>
          </div>
        </div>
        <footer><span>阿桌由阶跃星辰驱动</span><i />只有你确认的标签才会留下<i />不读取知乎私密数据</footer>
      </section>
    </div>,
    document.body,
  )
}
