import { useEffect, useId, useRef, useState } from 'react'
import {
  getHomeAccount,
  logoutHomeAccount,
  subscribeHomeAccount,
  type HomeAccount,
} from './accountStore'

interface AccountMenuProps {
  onOpenProfile(): void
  onOpenLogin(): void
}

export default function AccountMenu({ onOpenProfile, onOpenLogin }: AccountMenuProps) {
  const [account, setAccount] = useState<HomeAccount>(() => getHomeAccount())
  const [menuOpen, setMenuOpen] = useState(false)
  const rootRef = useRef<HTMLDivElement>(null)
  const closeTimer = useRef(0)
  const menuId = useId()

  useEffect(() => {
    const sync = (next: HomeAccount) => setAccount({ ...next })
    const unsub = subscribeHomeAccount(sync)
    const onCustom = (event: Event) => {
      const detail = (event as CustomEvent<HomeAccount>).detail
      if (detail) sync(detail)
      else sync(getHomeAccount())
    }
    window.addEventListener('zuoyizhuo:home-account', onCustom)
    // Catch up in case login happened while this instance was briefly unsubscribed (HMR / remount).
    sync(getHomeAccount())
    return () => {
      unsub()
      window.removeEventListener('zuoyizhuo:home-account', onCustom)
    }
  }, [])

  useEffect(() => () => window.clearTimeout(closeTimer.current), [])

  useEffect(() => {
    if (!menuOpen) return
    const onPointer = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setMenuOpen(false)
    }
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setMenuOpen(false)
    }
    window.addEventListener('mousedown', onPointer)
    window.addEventListener('keydown', onKey)
    return () => {
      window.removeEventListener('mousedown', onPointer)
      window.removeEventListener('keydown', onKey)
    }
  }, [menuOpen])

  if (!account.loggedIn) {
    return (
      <div className="home-account is-guest" ref={rootRef}>
        <button className="home-login-btn" type="button" onClick={onOpenLogin}>
          登录/注册
        </button>
      </div>
    )
  }

  return (
    <div
      className={`home-account is-logged-in ${menuOpen ? 'is-open' : ''}`}
      ref={rootRef}
      onMouseEnter={() => {
        window.clearTimeout(closeTimer.current)
        setMenuOpen(true)
      }}
      onMouseLeave={() => {
        window.clearTimeout(closeTimer.current)
        closeTimer.current = window.setTimeout(() => setMenuOpen(false), 160)
      }}
    >
      <button
        className="home-avatar-btn"
        type="button"
        aria-expanded={menuOpen}
        aria-haspopup="menu"
        aria-controls={menuId}
        aria-label={`${account.displayName} · 个人主页`}
        onClick={() => setMenuOpen((open) => !open)}
        onFocus={() => setMenuOpen(true)}
      >
        {account.avatarUrl ? (
          <img src={account.avatarUrl} alt="" />
        ) : (
          <span className="home-avatar-fallback" style={{ background: `hsl(${account.avatarHue} 42% 48%)` }} aria-hidden="true">
            {account.avatarInitial}
          </span>
        )}
      </button>

      <div id={menuId} className="home-account-dropdown" role="menu" hidden={!menuOpen}>
        <div className="home-account-card">
          <span className="home-avatar-fallback is-lg" style={{ background: `hsl(${account.avatarHue} 42% 48%)` }} aria-hidden="true">
            {account.avatarInitial}
          </span>
          <div>
            <b>{account.displayName}</b>
            <small>个人主页</small>
          </div>
        </div>
        <button
          type="button"
          role="menuitem"
          onClick={() => {
            setMenuOpen(false)
            onOpenProfile()
          }}
        >
          个人中心
          <span aria-hidden="true">→</span>
        </button>
        <button
          type="button"
          role="menuitem"
          className="is-muted"
          onClick={() => {
            logoutHomeAccount()
            setMenuOpen(false)
          }}
        >
          退出登录
        </button>
      </div>
    </div>
  )
}
