/** @origin HOME — local demo account for the homepage shell (not Zhihu OAuth). */

export interface HomeAccount {
  loggedIn: boolean
  displayName: string
  /** Stable hue for generated avatar when no photo URL. */
  avatarHue: number
  avatarInitial: string
  /** Optional remote/local avatar; empty uses generated color disc. */
  avatarUrl: string
}

export interface AuthResult {
  ok: boolean
  message: string
  account?: HomeAccount
}

interface DemoCredential {
  account: string
  password: string
  displayName: string
}

const STORAGE_KEY = 'zuoyizhuo.home-account'
const CREDS_KEY = 'zuoyizhuo.demo-credentials'
const SESSION_FLAG = 'zuoyizhuo.home-account-session'

const GUEST: HomeAccount = {
  loggedIn: false,
  displayName: '',
  avatarHue: 168,
  avatarInitial: '桌',
  avatarUrl: '',
}

type Listener = (account: HomeAccount) => void

const listeners = new Set<Listener>()

function hashHue(seed: string): number {
  let hash = 0
  for (let i = 0; i < seed.length; i += 1) hash = (hash * 31 + seed.charCodeAt(i)) % 360
  return hash
}

function normalizeAccount(raw: string): string {
  return raw.trim().toLowerCase()
}

function readCredentials(): DemoCredential[] {
  try {
    const raw = localStorage.getItem(CREDS_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw) as DemoCredential[]
    return Array.isArray(parsed) ? parsed.filter((item) => item && typeof item.account === 'string') : []
  } catch {
    return []
  }
}

function writeCredentials(list: DemoCredential[]) {
  try {
    localStorage.setItem(CREDS_KEY, JSON.stringify(list))
  } catch {
    // Demo auth still works in-memory for the session.
  }
}

function accountFromName(displayName: string): HomeAccount {
  const name = displayName.trim().slice(0, 24) || '桌边旅人'
  return {
    loggedIn: true,
    displayName: name,
    avatarHue: hashHue(name),
    avatarInitial: name.slice(0, 1),
    avatarUrl: '',
  }
}

function readStored(): HomeAccount {
  try {
    if (sessionStorage.getItem(SESSION_FLAG) === 'guest') return { ...GUEST }
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return { ...GUEST }
    const parsed = JSON.parse(raw) as Partial<HomeAccount>
    if (!parsed || typeof parsed !== 'object' || parsed.loggedIn !== true) return { ...GUEST }
    const displayName = typeof parsed.displayName === 'string' && parsed.displayName.trim()
      ? parsed.displayName.trim().slice(0, 24)
      : '桌边旅人'
    return {
      loggedIn: true,
      displayName,
      avatarHue: typeof parsed.avatarHue === 'number' ? parsed.avatarHue : hashHue(displayName),
      avatarInitial: (typeof parsed.avatarInitial === 'string' && parsed.avatarInitial)
        ? parsed.avatarInitial.slice(0, 1)
        : displayName.slice(0, 1),
      avatarUrl: typeof parsed.avatarUrl === 'string' ? parsed.avatarUrl : '',
    }
  } catch {
    return { ...GUEST }
  }
}

function writeStored(account: HomeAccount, remember = true) {
  try {
    if (!account.loggedIn) {
      localStorage.removeItem(STORAGE_KEY)
      sessionStorage.removeItem(SESSION_FLAG)
      return
    }
    // Always clear the explicit guest lock before writing a session.
    sessionStorage.removeItem(SESSION_FLAG)
    localStorage.setItem(STORAGE_KEY, JSON.stringify(account))
    if (!remember) {
      sessionStorage.setItem(SESSION_FLAG, '1')
    }
  } catch {
    // Session UI still works if storage is unavailable.
  }
}

let current = readStored()
let credentialCache = readCredentials()

/** Local UI test: start as logged-in. Set false when finished testing. */
const FORCE_DEMO_LOGGED_IN = false

if (FORCE_DEMO_LOGGED_IN && !current.loggedIn) {
  current = accountFromName('测试桌友')
  writeStored(current, true)
}

function emit() {
  const snapshot = { ...current }
  for (const listener of listeners) listener(snapshot)
  try {
    window.dispatchEvent(new CustomEvent('zuoyizhuo:home-account', { detail: snapshot }))
  } catch {
    // Non-browser / early boot.
  }
}

export function getHomeAccount(): HomeAccount {
  return current
}

export function subscribeHomeAccount(listener: Listener): () => void {
  listeners.add(listener)
  listener(current)
  return () => { listeners.delete(listener) }
}

/** Demo login only — never claims Zhihu identity or stores OAuth tokens. */
export function loginHomeDemo(displayName: string): HomeAccount {
  current = accountFromName(displayName)
  writeStored(current, true)
  emit()
  return current
}

export function registerDemoAccount(accountRaw: string, password: string, remember = true): AuthResult {
  const account = normalizeAccount(accountRaw)
  if (!account) return { ok: false, message: '请填写账号' }
  if (password.length < 4) return { ok: false, message: '密码至少 4 位' }
  if (credentialCache.some((item) => item.account === account)) {
    return { ok: false, message: '这个账号已经注册过了，请直接登录' }
  }
  const displayName = accountRaw.trim().slice(0, 24)
  const next: DemoCredential = { account, password, displayName }
  credentialCache = [...credentialCache, next]
  writeCredentials(credentialCache)
  current = accountFromName(displayName)
  writeStored(current, remember)
  emit()
  return { ok: true, message: '注册成功', account: { ...current } }
}

export function loginWithCredentials(accountRaw: string, password: string, remember = true): AuthResult {
  const account = normalizeAccount(accountRaw)
  if (!account) return { ok: false, message: '请填写账号' }

  // Demo: any non-empty account logs in; password is ignored.
  void password
  try { sessionStorage.removeItem(SESSION_FLAG) } catch { /* ignore */ }
  const found = credentialCache.find((item) => item.account === account)
  const displayName = found?.displayName || accountRaw.trim().slice(0, 24)
  current = accountFromName(displayName)
  writeStored(current, remember)
  emit()
  return { ok: true, message: '登录成功', account: { ...current } }
}

export function logoutHomeAccount(): HomeAccount {
  current = { ...GUEST }
  writeStored(current)
  try { sessionStorage.setItem(SESSION_FLAG, 'guest') } catch { /* ignore */ }
  emit()
  return current
}

/** Soft color discs used as preset avatars when no photo is uploaded. */
export const AVATAR_PRESETS = [
  { id: 'pine', hue: 158, label: '松青' },
  { id: 'lake', hue: 198, label: '湖蓝' },
  { id: 'dusk', hue: 28, label: '暮橙' },
  { id: 'rose', hue: 340, label: '暮蔷' },
  { id: 'moss', hue: 88, label: '苔绿' },
  { id: 'plum', hue: 278, label: '岩紫' },
] as const

export function updateHomeDisplayName(displayNameRaw: string): AuthResult {
  if (!current.loggedIn) return { ok: false, message: '请先登录' }
  const displayName = displayNameRaw.trim().slice(0, 24)
  if (!displayName) return { ok: false, message: '请填写显示名' }
  current = {
    ...current,
    displayName,
    avatarInitial: displayName.slice(0, 1),
    avatarHue: current.avatarUrl ? current.avatarHue : hashHue(displayName),
  }
  writeStored(current, true)
  emit()
  return { ok: true, message: '显示名已更新', account: { ...current } }
}

export function updateHomeAvatar(options: { avatarUrl?: string; avatarHue?: number }): AuthResult {
  if (!current.loggedIn) return { ok: false, message: '请先登录' }
  const nextUrl = typeof options.avatarUrl === 'string' ? options.avatarUrl : current.avatarUrl
  const nextHue = typeof options.avatarHue === 'number' ? options.avatarHue : current.avatarHue
  current = {
    ...current,
    avatarUrl: nextUrl,
    avatarHue: nextHue,
    avatarInitial: current.displayName.slice(0, 1) || '桌',
  }
  writeStored(current, true)
  emit()
  return { ok: true, message: '头像已更新', account: { ...current } }
}

export function clearHomeAvatarPhoto(): AuthResult {
  return updateHomeAvatar({ avatarUrl: '' })
}
