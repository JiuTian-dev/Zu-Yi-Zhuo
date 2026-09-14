import { useEffect, useId, useRef, useState, type FormEvent } from 'react'
import { createPortal } from 'react-dom'
import AnimatedCharacters, { CHARACTER_HIT_TARGETS, type CharacterMood } from './AnimatedCharacters'
import {
  loginWithCredentials,
  registerDemoAccount,
} from '../home/accountStore'
import './login.css'

interface LoginPageProps {
  open: boolean
  onClose(): void
  onSuccess(): void
}

type AuthMode = 'login' | 'register'

export default function LoginPage({ open, onClose, onSuccess }: LoginPageProps) {
  const [mode, setMode] = useState<AuthMode>('login')
  const [account, setAccount] = useState('')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [remember, setRemember] = useState(true)
  const [accountFocused, setAccountFocused] = useState(false)
  const [mood, setMood] = useState<CharacterMood>('idle')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [singingId, setSingingId] = useState<string | null>(null)
  const titleId = useId()
  const dialogRef = useRef<HTMLDivElement>(null)
  const closeButtonRef = useRef<HTMLButtonElement>(null)
  const clickTimer = useRef(0)
  const lastClickId = useRef<string | null>(null)

  useEffect(() => {
    if (!open) return
    setMode('login')
    setAccount('')
    setPassword('')
    setConfirm('')
    setShowPassword(false)
    setRemember(true)
    setAccountFocused(false)
    setMood('idle')
    setError('')
    setBusy(false)
    setSingingId(null)
    const frame = window.requestAnimationFrame(() => closeButtonRef.current?.focus({ preventScroll: true }))
    return () => window.cancelAnimationFrame(frame)
  }, [open])

  useEffect(() => {
    if (!open) return
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault()
        onClose()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose, open])

  useEffect(() => () => window.clearTimeout(clickTimer.current), [])

  if (!open) return null

  const triggerSing = (id: string) => {
    setSingingId(id)
    window.setTimeout(() => setSingingId((current) => (current === id ? null : current)), 900)
  }

  const onCharacterPointer = (id: string) => {
    window.clearTimeout(clickTimer.current)
    if (lastClickId.current === id) {
      lastClickId.current = null
      triggerSing('all')
      return
    }
    lastClickId.current = id
    clickTimer.current = window.setTimeout(() => {
      lastClickId.current = null
      triggerSing(id)
    }, 280)
  }

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    setError('')
    setBusy(true)
    setMood('idle')

    await new Promise((resolve) => window.setTimeout(resolve, 280))

    if (mode === 'register') {
      if (password.length < 4) {
        setError('密码至少 4 位')
        setMood('sad')
        setBusy(false)
        return
      }
      if (password !== confirm) {
        setError('两次输入的密码不一致')
        setMood('sad')
        setBusy(false)
        return
      }
      const result = registerDemoAccount(account, password, remember)
      if (!result.ok) {
        setError(result.message)
        setMood('sad')
        setBusy(false)
        return
      }
      setMood('happy')
      setBusy(false)
      window.setTimeout(() => onSuccess(), 700)
      return
    }

    const result = loginWithCredentials(account, password, remember)
    if (!result.ok) {
      setError(result.message)
      setMood('sad')
      setBusy(false)
      return
    }
    setMood('happy')
    setBusy(false)
    window.setTimeout(() => onSuccess(), 700)
  }

  return createPortal(
    <div className="login-overlay" role="presentation">
      <button className="login-scrim" type="button" aria-label="关闭登录窗口" onClick={onClose} />
      <div
        ref={dialogRef}
        className="login-window"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
      >
        <header className="login-window-bar">
          <div className="login-window-dots" aria-hidden="true">
            <span />
            <span />
            <span />
          </div>
          <p className="login-window-title">组一桌 · 登录</p>
          <button
            ref={closeButtonRef}
            className="login-window-close"
            type="button"
            aria-label="关闭"
            onClick={onClose}
          >
            ×
          </button>
        </header>

        <div className="login-page">
          <section className="login-stage" aria-label="角色舞台">
            <p className="login-brand">组一桌</p>
            <div className="login-stage-cast">
              <AnimatedCharacters
                mood={mood}
                accountFocused={accountFocused}
                showPassword={showPassword}
                passwordLength={password.length}
                singingId={singingId}
              />
              <div className="login-hit-layer">
                {CHARACTER_HIT_TARGETS.map((target) => (
                  <button
                    key={target.id}
                    type="button"
                    className={`login-hit login-hit-${target.id}`}
                    aria-label={`${target.label}：单击唱歌，双击齐唱`}
                    onClick={() => onCharacterPointer(target.id)}
                  />
                ))}
              </div>
            </div>
            <p className="login-stage-note">眼睛会跟着你 · 点角色会唱歌</p>
          </section>

          <section className="login-panel">
            <div className="login-card">
              <header className="login-card-head">
                <h1 id={titleId}>{mode === 'login' ? '欢迎回来' : '加入桌边'}</h1>
                <p>{mode === 'login' ? '请填写你的账号信息' : '创建一个演示账号，稍后再换成正式登录'}</p>
              </header>

              <form className="login-form" onSubmit={submit} noValidate>
                <label className="login-field">
                  <span>账号</span>
                  <input
                    type="text"
                    name="account"
                    autoComplete="username"
                    placeholder="邮箱或昵称"
                    value={account}
                    maxLength={48}
                    onChange={(event) => setAccount(event.target.value)}
                    onFocus={() => {
                      setAccountFocused(true)
                      if (mood === 'idle') setMood('curious')
                    }}
                    onBlur={() => {
                      setAccountFocused(false)
                      if (mood === 'curious') setMood('idle')
                    }}
                    required
                  />
                </label>

                <label className="login-field">
                  <span>密码</span>
                  <span className="login-password-wrap">
                    <input
                      type={showPassword ? 'text' : 'password'}
                      name="password"
                      autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
                      placeholder="至少 4 位"
                      value={password}
                      maxLength={64}
                      onChange={(event) => setPassword(event.target.value)}
                      required
                    />
                    <button
                      className="login-eye-toggle"
                      type="button"
                      aria-label={showPassword ? '隐藏密码' : '显示密码'}
                      onClick={() => setShowPassword((open) => !open)}
                    >
                      {showPassword ? (
                        <svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true"><path fill="currentColor" d="M12 6a9.8 9.8 0 0 1 9.5 6 9.8 9.8 0 0 1-19 0A9.8 9.8 0 0 1 12 6Zm0 2a7.8 7.8 0 0 0-7.3 4A7.8 7.8 0 0 0 12 16a7.8 7.8 0 0 0 7.3-4A7.8 7.8 0 0 0 12 8Zm0 1.5A2.5 2.5 0 1 1 9.5 12 2.5 2.5 0 0 1 12 9.5Z"/></svg>
                      ) : (
                        <svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true"><path fill="currentColor" d="M3.3 2.3 21 20l-1.4 1.4-3.1-3.1A11.5 11.5 0 0 1 12 18c-5 0-9.3-3.1-11-7.5a12.4 12.4 0 0 1 4.6-5.3L2 3.7 3.3 2.3ZM12 8a4 4 0 0 1 4 4c0 .5-.1 1-.3 1.4l-5.1-5.1c.4-.2.9-.3 1.4-.3Zm0-2c1.2 0 2.3.3 3.3.7l-1.6 1.6A5.9 5.9 0 0 0 12 8a6 6 0 0 0-6 6c0 .6.1 1.1.2 1.6L4.4 17A11.6 11.6 0 0 1 1 12.5C2.7 8.1 7 5 12 5c1.1 0 2.2.2 3.2.5L13.6 7A6 6 0 0 0 12 6.9Z"/></svg>
                      )}
                    </button>
                  </span>
                </label>

                {mode === 'register' && (
                  <label className="login-field">
                    <span>确认密码</span>
                    <input
                      type={showPassword ? 'text' : 'password'}
                      name="confirm"
                      autoComplete="new-password"
                      placeholder="再输入一次"
                      value={confirm}
                      maxLength={64}
                      onChange={(event) => setConfirm(event.target.value)}
                      required
                    />
                  </label>
                )}

                <div className="login-row">
                  <label className="login-check">
                    <input
                      type="checkbox"
                      checked={remember}
                      onChange={(event) => setRemember(event.target.checked)}
                    />
                    <span>30 天内保持登录</span>
                  </label>
                  {mode === 'login' && (
                    <button
                      className="login-text-link"
                      type="button"
                      onClick={() => setError('演示模式暂未开通找回密码，请直接注册一个新账号。')}
                    >
                      忘记密码？
                    </button>
                  )}
                </div>

                {error && (
                  <p className="login-error" role="alert">{error}</p>
                )}

                <button className="login-submit" type="submit" disabled={busy}>
                  {busy ? '请稍候…' : mode === 'login' ? '登录' : '注册并进入'}
                </button>
              </form>

              <p className="login-switch">
                {mode === 'login' ? (
                  <>
                    还没有账号？
                    <button
                      type="button"
                      onClick={() => {
                        setMode('register')
                        setError('')
                        setMood('idle')
                      }}
                    >
                      去注册
                    </button>
                  </>
                ) : (
                  <>
                    已有账号？
                    <button
                      type="button"
                      onClick={() => {
                        setMode('login')
                        setError('')
                        setMood('idle')
                      }}
                    >
                      去登录
                    </button>
                  </>
                )}
              </p>
              <p className="login-footnote">演示登录 · 正式知乎账号尚未开放</p>
            </div>
          </section>
        </div>
      </div>
    </div>,
    document.body,
  )
}
