import { useEffect, useId, useRef, useState, type FormEvent } from 'react'
import { createPortal } from 'react-dom'
import { getHomeAccount, loginHomeDemo, type AvatarCharacter } from '../home/accountStore'
import CharacterPortrait from '../live/CharacterPortrait'
import LoginCharacterStage from './LoginCharacterStage'
import ZhihuConnectionPreview from '../home/ZhihuConnectionPreview'
import './login.css'

interface LoginPageProps {
  open: boolean
  required?: boolean
  onClose(): void
  onSuccess(): void
}

const ROLES: Array<{ character: AvatarCharacter; title: string; note: string }> = [
  { character: 'blue', title: '蓝色外套', note: '清爽，自在一点' },
  { character: 'orange', title: '橙色夹克', note: '带一点阳光出发' },
  { character: 'white', title: '奶白卫衣', note: '柔和，轻松一点' },
  { character: 'green', title: '绿色风衣', note: '把好奇心带上' },
]
const CAST_ORDER: AvatarCharacter[] = ['white', 'orange', 'green', 'blue']
const CAST_NAMES = ['林夏', '周砚', '程野']

export default function LoginPage({ open, required = false, onClose, onSuccess }: LoginPageProps) {
  const [selected, setSelected] = useState<AvatarCharacter>('blue')
  const [nickname, setNickname] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const titleId = useId()
  const nicknameId = useId()
  const dialogRef = useRef<HTMLElement>(null)
  const nicknameRef = useRef<HTMLInputElement>(null)
  const successTimer = useRef<number | null>(null)

  useEffect(() => {
    if (!open) return
    const current = getHomeAccount()
    setSelected(current.avatarCharacter ?? 'blue')
    setNickname(current.loggedIn && !/^(湖蓝|暖橙|雾白|松绿|桌边)旅人$/.test(current.displayName) ? current.displayName : '')
    setError('')
    setBusy(false)
    const frame = window.requestAnimationFrame(() => {
      dialogRef.current?.focus({ preventScroll: true })
      dialogRef.current?.scrollTo({ top: 0 })
    })
    return () => {
      window.cancelAnimationFrame(frame)
      if (successTimer.current !== null) window.clearTimeout(successTimer.current)
    }
  }, [open])

  useEffect(() => {
    if (!open) return
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && !required && !busy) {
        event.preventDefault()
        onClose()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [busy, onClose, open, required])

  if (!open) return null

  const enter = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (busy) return
    const name = nickname.trim()
    if (!name) {
      setError('先告诉大家怎么称呼你吧。')
      nicknameRef.current?.focus()
      return
    }
    setBusy(true)
    setError('')
    loginHomeDemo(name, selected)
    successTimer.current = window.setTimeout(onSuccess, 280)
  }

  return createPortal(
    <div className={'login-overlay ' + (busy ? 'is-success' : '')} role="presentation">
      {!required && <button className="login-scrim" type="button" aria-label="关闭登录窗口" disabled={busy} onClick={onClose} />}
      <section ref={dialogRef} tabIndex={-1} className="login-experience" role="dialog" aria-modal="true" aria-labelledby={titleId}>
        <div className="login-lake" aria-hidden="true" />
        <header className="login-topbar">
          <div className="login-lockup"><i>桌</i><span><b>组一桌</b><small>从一个真实的你开始</small></span></div>
          <p>选个形象，留个昵称，就能出发</p>
          {!required && <button type="button" aria-label="关闭" disabled={busy} onClick={onClose}>×</button>}
        </header>
        <div className="login-body">
          <div className="login-left">
            <div className="login-hero-copy">
              <p>一场相遇，从认识你开始</p>
              <h1 id={titleId}>从湖边出发，<br />遇见值得聊的人。</h1>
              <blockquote>形象由你选，名字由你定。<br />至于你的故事，留给阿桌慢慢听。</blockquote>
            </div>
            <form className="login-role-panel" onSubmit={enter}>
              <div className="login-role-heading"><span>01</span><h2>选一个喜欢的样子</h2><small>不预设你的性格</small></div>
              <div className="login-role-grid" role="group" aria-label="选择人物形象">
                {ROLES.map((role) => (
                  <button key={role.character}
                    type="button" className={selected === role.character ? 'is-selected' : ''}
                    aria-pressed={selected === role.character} disabled={busy} onClick={() => setSelected(role.character)}>
                    <CharacterPortrait character={role.character} label={role.title} className="login-role-avatar" />
                    <span><b>{role.title}</b><small>{role.note}</small></span>
                    <i aria-hidden="true">{selected === role.character ? '✓' : '+'}</i>
                  </button>
                ))}
              </div>
              <div className="login-nickname-heading"><span>02</span><label htmlFor={nicknameId}>大家怎么称呼你？</label></div>
              <div className={'login-nickname-field ' + (error ? 'has-error' : '')}>
                <input ref={nicknameRef} id={nicknameId} name="nickname" value={nickname} maxLength={24}
                  autoComplete="nickname" placeholder="起一个你喜欢的昵称" disabled={busy}
                  aria-invalid={Boolean(error)} aria-describedby={nicknameId + '-hint'}
                  onChange={(event) => { setNickname(event.target.value); setError('') }} />
                <span>{nickname.length}/24</span>
              </div>
              <p id={nicknameId + '-hint'} className="login-nickname-hint" role={error ? 'alert' : undefined}>
                {error || '只用昵称就好，进入后也可以修改。'}
              </p>
              <button className="login-enter" type="submit" disabled={busy}>
                <span>{busy ? '欢迎你，' + nickname.trim() : '就这样，去组一桌'}</span><b aria-hidden="true">→</b>
              </button>
              <p className="login-local-note">无需密码 · 昵称和形象保存在当前浏览器</p>
            </form>
            <ZhihuConnectionPreview light />
          </div>
          <aside className="login-right" aria-label="人物形象展示">
            <div className="login-scene-caption"><span>湖边已经留好位置</span><p>带上你自己，就够了。</p></div>
            <div className="login-cast-art">
              <LoginCharacterStage selected={selected} />
            </div>
            <p className="login-model-note">实时 3D · 拖动转身，选择你的样子</p>
            <div className="login-cast-legend" aria-live="polite">
              <span className="is-you">你 · {nickname.trim() || '等待你的昵称'}</span>
              <p>另外三位，由阿桌来介绍</p>
              <div>{CAST_ORDER.filter((character) => character !== selected).map((character, index) => (
                <span key={character}><CharacterPortrait character={character} label={CAST_NAMES[index]} />{CAST_NAMES[index]}</span>
              ))}</div>
              <small>演示桌友 · 形象自动顺延，不会与你重复</small>
            </div>
          </aside>
        </div>
      </section>
    </div>, document.body,
  )
}
