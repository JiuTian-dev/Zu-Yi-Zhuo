import { readFileSync } from 'node:fs'

// Local demo/preview gateway: credentials never enter VITE_* or the client bundle.
const topicCache = new Map()
let topicBusy = false
export default function zhihuTopics() {
  const install = (server) => {
    server.middlewares.use('/demo/zhihu-topics', async (req, res) => {
      res.setHeader('Content-Type', 'application/json; charset=utf-8')
      if (req.method !== 'GET') { res.statusCode = 405; res.end('{}'); return }
      const kind = new URL(req.url || '/', 'http://localhost').searchParams.get('topic') === 'city' ? 'city' : 'ai'
      const cached = topicCache.get(kind)
      if (cached && Date.now() - cached.time < 3600000) { res.end(JSON.stringify(cached.data)); return }
      if (topicBusy) { res.statusCode = 429; res.end('{"error":"请稍后重试"}'); return }
      topicBusy = true
      try {
        const secret = process.env.ZHIHU_ACCESS_SECRET || readFileSync(new URL('../backend/.env.zhihu.local', import.meta.url), 'utf8').match(/^ZHIHU_ACCESS_SECRET=(.+)$/m)?.[1]?.trim()
        if (!secret) throw new Error('configuration')
        const query = kind === 'city' ? '离开大城市' : 'AI 职业'
        const upstream = await fetch('https://developer.zhihu.com/api/v1/content/zhihu_search?' + new URLSearchParams({ Query: query, Count: '5' }), { headers: { Authorization: 'Bearer ' + secret, 'X-Request-Timestamp': String(Math.floor(Date.now() / 1000)) }, signal: AbortSignal.timeout(4500) })
        const payload = await upstream.json()
        if (!upstream.ok || payload.Code !== 0) throw new Error('upstream')
        const seen = new Set()
        const items = (payload.Data?.Items || []).flatMap((item) => {
          const match = item.Url?.match(/^https:\/\/www\.zhihu\.com\/question\/(\d+)/)
          if (!match || !item.Title || seen.has(match[1])) return []
          seen.add(match[1])
          return [{ title: item.Title.replace(/\s*-\s*知乎$/, ''), url: 'https://www.zhihu.com/question/' + match[1] }]
        }).slice(0, 3)
        const data = { items, source: '知乎开放平台', retrievedAt: new Date().toISOString() }
        topicCache.set(kind, { time: Date.now(), data })
        res.end(JSON.stringify(data))
      } catch {
        res.statusCode = 502
        res.end('{"error":"知乎检索暂不可用，请稍后重试"}')
      } finally { topicBusy = false }
    })
  }
  return { name: 'zhihu-public-topics', configureServer: install, configurePreviewServer: install }
}
