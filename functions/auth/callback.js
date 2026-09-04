/**
 * @origin OAUTH-CALLBACK-RELAY
 *
 * Cloudflare Pages owns the redirect URI already submitted to Zhihu. This
 * function forwards only the documented OAuth callback fields to the real
 * server-side coordinator. It never receives app_key or exchanges tokens.
 */

const FORWARDED_PARAMETERS = [
  'authorization_code',
  'state',
  'error',
  'error_description',
]

function callbackTarget(rawTarget) {
  if (typeof rawTarget !== 'string' || !rawTarget.trim()) return null
  try {
    const target = new URL(rawTarget)
    const local = target.hostname === 'localhost' || target.hostname === '127.0.0.1'
    if (target.protocol !== 'https:' && !(local && target.protocol === 'http:')) return null
    return target
  } catch {
    return null
  }
}

export function onRequestGet({ request, env }) {
  const target = callbackTarget(env.ZHIHU_OAUTH_BACKEND_CALLBACK_URL)
  if (!target) {
    return new Response('知乎授权回调尚未完成服务端配置。', {
      status: 503,
      headers: { 'Cache-Control': 'no-store' },
    })
  }

  const incoming = new URL(request.url)
  for (const name of FORWARDED_PARAMETERS) {
    const value = incoming.searchParams.get(name)
    if (value) target.searchParams.set(name, value)
  }

  if (!target.searchParams.has('authorization_code') && !target.searchParams.has('error')) {
    return new Response('知乎授权回调缺少必要参数。', {
      status: 400,
      headers: { 'Cache-Control': 'no-store' },
    })
  }

  return new Response(null, {
    status: 302,
    headers: {
      'Cache-Control': 'no-store',
      Location: target.toString(),
      'Referrer-Policy': 'no-referrer',
    },
  })
}
