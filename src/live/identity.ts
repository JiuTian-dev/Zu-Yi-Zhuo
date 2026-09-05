/** @origin BACKEND-ADAPTER — session identity boundary for the local client. */

export interface AccountSession {
  participantId: string
  observerId: string
  displayName: string
  role: string
  provider: 'guest' | 'zhihu'
  authenticated: boolean
}

const SESSION_ID_KEY = 'zuoyizhuo.session-identity'

function sessionId() {
  try {
    const stored = sessionStorage.getItem(SESSION_ID_KEY)
    if (stored) return stored
    const generated = `guest-${crypto.randomUUID().slice(0, 12)}`
    sessionStorage.setItem(SESSION_ID_KEY, generated)
    return generated
  } catch {
    return `guest-${Math.random().toString(36).slice(2, 14)}`
  }
}

export const VIEWER_ID = sessionId()

export const viewerIdentity: AccountSession = {
  participantId: VIEWER_ID,
  observerId: `observer-${VIEWER_ID.replace(/^guest-/, '')}`,
  // The UI resolves this session back to “你”; the backend-facing label must
  // stay meaningful to other observers instead of leaking a self-relative label.
  displayName: '第五席',
  role: '第五席',
  provider: 'guest',
  authenticated: false,
} as const

/**
 * The OAuth cutover can replace this adapter without changing product
 * components. Until Zhihu opens the service, guest identity is explicit and
 * never presented as an authenticated Zhihu account.
 */
export function getAccountSession(): AccountSession {
  return viewerIdentity
}
