/** @origin HOME — profile-5–inspired spotlight personal center (approx, no Pro license). */

import { useEffect, useId, useRef, useState, type CSSProperties, type ChangeEvent, type FormEvent } from 'react'
import AccountMenu from './AccountMenu'
import {
  AVATAR_PRESETS,
  clearHomeAvatarPhoto,
  getHomeAccount,
  logoutHomeAccount,
  subscribeHomeAccount,
  updateHomeAvatar,
  updateHomeDisplayName,
  type HomeAccount,
} from './accountStore'
import { loadParticipatedHistory, loadSavedHistory, type ProfileHistoryItem } from './profileHistory'
import campScene from '../assets/home-camp.jpg'
import './home.css'

const sceneStyle = { '--home-camp-image': `url(${campScene})` } as CSSProperties

export interface ProfilePageProps {
  onBack(): void
  onEnterMatch(): void
  onOpenTable(tableId: string): void
}

type ProfileTab = 'saved' | 'participated'

function AvatarFace({ account, className = '' }: { account: HomeAccount; className?: string }) {
  if (account.avatarUrl) {
    return <img className={className} src={account.avatarUrl} alt="" />
  }
  return (
    <span
      className={`${className} home-avatar-fallback`}
      style={{ background: `hsl(${account.avatarHue} 42% 48%)` }}
      aria-hidden="true"
    >
      {account.avatarInitial}
    </span>
  )
}

export default function ProfilePage({ onBack, onEnterMatch, onOpenTable }: ProfilePageProps) {
  const [account, setAccount] = useState<HomeAccount>(() => getHomeAccount())
  const [tab, setTab] = useState<ProfileTab>('saved')
  const [editingName, setEditingName] = useState(false)
  const [nameDraft, setNameDraft] = useState('')
  const [avatarOpen, setAvatarOpen] = useState(false)
  const [saved, setSaved] = useState<ProfileHistoryItem[]>([])
  const [participated, setParticipated] = useState<ProfileHistoryItem[]>([])
  const [participatedDemo, setParticipatedDemo] = useState(false)
  const [listError, setListError] = useState<string | null>(null)
  const [loadingLists, setLoadingLists] = useState(true)
  const [toast, setToast] = useState('')
  const fileRef = useRef<HTMLInputElement>(null)
  const nameFieldId = useId()
  const tabsId = useId()

  useEffect(() => {
    const sync = (next: HomeAccount) => setAccount({ ...next })
    const unsub = subscribeHomeAccount(sync)
    const onCustom = (event: Event) => {
      const detail = (event as CustomEvent<HomeAccount>).detail
      sync(detail ?? getHomeAccount())
    }
    window.addEventListener('zuoyizhuo:home-account', onCustom)
    sync(getHomeAccount())
    return () => {
      unsub()
      window.removeEventListener('zuoyizhuo:home-account', onCustom)
    }
  }, [])

  useEffect(() => {
    if (!account.loggedIn) onBack()
  }, [account.loggedIn, onBack])

  useEffect(() => {
    let cancelled = false
    setLoadingLists(true)
    void Promise.all([loadSavedHistory(), loadParticipatedHistory()]).then(([savedResult, participatedResult]) => {
      if (cancelled) return
      setSaved(savedResult.items)
      setParticipated(participatedResult.items)
      setParticipatedDemo(participatedResult.usingDemo)
      setListError(savedResult.error || participatedResult.error)
      setLoadingLists(false)
    })
    return () => { cancelled = true }
  }, [])

  if (!account.loggedIn) return null

  const flash = (message: string) => {
    setToast(message)
    window.setTimeout(() => setToast(''), 2200)
  }

  const startEditName = () => {
    setNameDraft(account.displayName)
    setEditingName(true)
  }

  const submitName = (event: FormEvent) => {
    event.preventDefault()
    const result = updateHomeDisplayName(nameDraft)
    if (!result.ok) {
      flash(result.message)
      return
    }
    setEditingName(false)
    flash('显示名已更新')
  }

  const onPickFile = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    event.target.value = ''
    if (!file || !file.type.startsWith('image/')) {
      flash('请选择图片文件')
      return
    }
    if (file.size > 1.5 * 1024 * 1024) {
      flash('图片请小于 1.5MB（演示本地存储）')
      return
    }
    const reader = new FileReader()
    reader.onload = () => {
      const url = typeof reader.result === 'string' ? reader.result : ''
      const result = updateHomeAvatar({ avatarUrl: url })
      flash(result.ok ? '头像已更新' : result.message)
      setAvatarOpen(false)
    }
    reader.readAsDataURL(file)
  }

  const activeList = tab === 'saved' ? saved : participated
  const savedCount = saved.length
  const participatedCount = participated.length

  const openItem = (item: ProfileHistoryItem) => {
    if (item.source === 'demo') {
      flash('演示条目 · 正式参与记录接好后端后可打开')
      return
    }
    void onOpenTable(item.tableId)
  }

  return (
    <main className="home-page home-profile" style={sceneStyle} aria-label="个人中心">
      <div className="home-scene" aria-hidden="true">
        <div className="home-scene-image" role="img" aria-label="露营湖边场景" />
        <div className="home-scene-veil is-profile-spot" />
      </div>

      <header className="home-topbar">
        <div className="home-topbar-spacer" />
        <AccountMenu onOpenProfile={() => undefined} onOpenLogin={onBack} />
      </header>

      <div className="profile-spot">
        <section className="profile-spot-card" aria-labelledby="profile-title">
          <div className="profile-spot-glow" aria-hidden="true" />

          <div className="profile-spot-toolbar">
            <button className="profile-spot-back" type="button" onClick={onBack}>
              ← 返回首页
            </button>
          </div>

          <div className="profile-spot-hero">
            <button
              type="button"
              className="profile-spot-avatar-btn"
              aria-label="更换头像"
              onClick={() => setAvatarOpen((open) => !open)}
            >
              <AvatarFace account={account} className="profile-spot-avatar" />
              <span className="profile-spot-avatar-edit">换头像</span>
            </button>

            <div className="profile-spot-identity">
              {editingName ? (
                <form className="profile-spot-name-form" onSubmit={submitName}>
                  <label className="profile-sr-only" htmlFor={nameFieldId}>显示名</label>
                  <input
                    id={nameFieldId}
                    value={nameDraft}
                    maxLength={24}
                    autoFocus
                    onChange={(event) => setNameDraft(event.target.value)}
                  />
                  <button type="submit">保存</button>
                  <button type="button" className="is-ghost" onClick={() => setEditingName(false)}>取消</button>
                </form>
              ) : (
                <>
                  <h1 id="profile-title">{account.displayName}</h1>
                  <p className="profile-spot-bio">演示账户 · 正式知乎登录接入后会替换此处身份</p>
                  <div className="profile-spot-actions">
                    <button type="button" onClick={startEditName}>改显示名</button>
                    <button type="button" onClick={() => setAvatarOpen(true)}>改头像</button>
                    <button
                      type="button"
                      className="is-muted"
                      onClick={() => {
                        logoutHomeAccount()
                        onBack()
                      }}
                    >
                      退出登录
                    </button>
                  </div>
                </>
              )}
            </div>
          </div>

          {avatarOpen && (
            <div className="profile-spot-avatar-panel" role="region" aria-label="选择头像">
              <p>预设色块</p>
              <div className="profile-spot-presets">
                {AVATAR_PRESETS.map((preset) => (
                  <button
                    key={preset.id}
                    type="button"
                    className="profile-spot-preset"
                    style={{ background: `hsl(${preset.hue} 42% 48%)` }}
                    aria-label={preset.label}
                    onClick={() => {
                      updateHomeAvatar({ avatarUrl: '', avatarHue: preset.hue })
                      flash(`已选用「${preset.label}」`)
                      setAvatarOpen(false)
                    }}
                  >
                    {account.displayName.slice(0, 1)}
                  </button>
                ))}
              </div>
              <div className="profile-spot-upload-row">
                <button type="button" onClick={() => fileRef.current?.click()}>上传图片</button>
                {account.avatarUrl && (
                  <button
                    type="button"
                    className="is-ghost"
                    onClick={() => {
                      clearHomeAvatarPhoto()
                      flash('已去掉上传头像')
                    }}
                  >
                    清除图片
                  </button>
                )}
                <button type="button" className="is-ghost" onClick={() => setAvatarOpen(false)}>收起</button>
              </div>
              <input ref={fileRef} type="file" accept="image/*" hidden onChange={onPickFile} />
            </div>
          )}

          <ul className="profile-spot-stats" aria-label="概览">
            <li>
              <b>{savedCount}</b>
              <span>稍后再看</span>
            </li>
            <li>
              <b>{participatedCount}</b>
              <span>参与过的桌</span>
            </li>
            <li>
              <button type="button" onClick={onEnterMatch}>
                <b>去匹配</b>
                <span>正在发生的桌</span>
              </button>
            </li>
          </ul>

          <div className="profile-spot-tabs" role="tablist" aria-labelledby={tabsId}>
            <span id={tabsId} className="profile-sr-only">历史分区</span>
            <button
              type="button"
              role="tab"
              aria-selected={tab === 'saved'}
              className={tab === 'saved' ? 'is-active' : ''}
              onClick={() => setTab('saved')}
            >
              稍后再看
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={tab === 'participated'}
              className={tab === 'participated' ? 'is-active' : ''}
              onClick={() => setTab('participated')}
            >
              参与过的桌
              {participatedDemo && <em>演示</em>}
            </button>
          </div>

          <div className="profile-spot-list" role="tabpanel">
            {loadingLists && <p className="profile-spot-empty">正在读取你的桌边记录…</p>}
            {!loadingLists && listError && tab === 'saved' && saved.length === 0 && (
              <p className="profile-spot-empty" role="status">{listError}</p>
            )}
            {!loadingLists && activeList.length === 0 && (
              <p className="profile-spot-empty">
                {tab === 'saved'
                  ? '你主动留下的桌会出现在这里。'
                  : '坐过或旁听过的桌会出现在这里。'}
              </p>
            )}
            {!loadingLists && activeList.map((item) => (
              <button
                key={`${item.source}-${item.tableId}`}
                type="button"
                className="profile-spot-row"
                onClick={() => openItem(item)}
              >
                <span className="profile-spot-row-copy">
                  <b>{item.title}</b>
                  <span>{item.note}</span>
                  <small>{item.meta}{item.source === 'demo' ? ' · 演示' : ''}</small>
                </span>
                <span className="profile-spot-row-go" aria-hidden="true">→</span>
              </button>
            ))}
          </div>
        </section>
      </div>

      {toast && <p className="profile-spot-toast" role="status">{toast}</p>}
    </main>
  )
}
