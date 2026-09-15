import { useEffect, useState } from 'react'
import './zhihuConnectionPreview.css'

const EXAMPLES = [
  { question: '离开大城市，是逃避还是重新选择生活？', tags: ['职业选择', '生活方式', '迁居经历'], perspectives: ['有迁居经历的人', '关注职业机会的人', '研究城市生活的人'], reason: '围绕同一个生活选择，用亲历、职业和城市视角补充彼此的信息。', outcome: '聊清自己想改变什么，带走判断依据，也找到愿意继续聊的桌友。' },
  { question: 'AI 时代，专业判断会被替代吗？', tags: ['AI 与工作', '专业成长', '责任边界'], perspectives: ['一线使用 AI 的人', '了解技术边界的人', '关注专业责任的人'], reason: '不只匹配相同态度，让使用经验、技术能力和责任边界在同一桌被看见。', outcome: '区分可交给 AI 的任务和需要人负责的判断，留下分歧与下一次讨论的问题。' },
]

/** Local illustrative data only; no Zhihu request, authorization, or account access. */
export default function ZhihuConnectionPreview({ light = false }: { light?: boolean }) {
  const [selected, setSelected] = useState(0)
  const [open, setOpen] = useState(false)
  const [topics, setTopics] = useState<Array<{ title: string; url: string }>>([])
  const [status, setStatus] = useState('')
  useEffect(() => {
    if (!open) return
    const controller = new AbortController()
    setTopics([])
    setStatus('正在检索知乎问题…')
    fetch('/demo/zhihu-topics?topic=' + (selected === 0 ? 'city' : 'ai'), { signal: controller.signal })
      .then(async (response) => { if (!response.ok) throw new Error(); return response.json() })
      .then((data) => { setTopics(data.items || []); setStatus(data.items?.length ? '来源：知乎开放平台 · 结果缓存 1 小时' : '暂未检索到相关问题，请换一个方向。') })
      .catch(() => { if (!controller.signal.aborted) setStatus('知乎检索暂不可用，请收起后重新展开重试。') })
    return () => controller.abort()
  }, [open, selected])
  const example = EXAMPLES[selected]
  return (
    <details className={'zhihu-connection' + (light ? ' is-light' : '')} onToggle={(event) => setOpen(event.currentTarget.open)}>
      <summary>
        <span className="zhihu-connection-mark" aria-hidden="true">知</span>
        <span><b>从知乎话题，到一桌同路人</b><small>自动检索相关问题 · 查看原文</small></span>
        <em>知乎问题</em><i aria-hidden="true">＋</i>
      </summary>
      <div className="zhihu-connection-body">
        <p>赛道一 · 灵魂匹配局：社区连接与兴趣社交</p>
        <small>选择讨论方向，检索知乎真实问题；下方组桌建议由本产品预设，不代表知乎推荐或真实用户已入席。</small>
        <div className="zhihu-example-choices" role="group" aria-label="选择检索方向">
          {EXAMPLES.map((item, index) => <button key={item.question} type="button" aria-pressed={selected === index} onClick={() => setSelected(index)}>{item.question}</button>)}
        </div>
        <div className="zhihu-source-results" aria-live="polite"><small>{status}</small>{topics.map((topic) => <a key={topic.url} href={topic.url} target="_blank" rel="noopener noreferrer">{topic.title}<span>知乎原文 ↗</span></a>)}</div>
        <div className="zhihu-example-result" aria-live="polite">
          <div className="zhihu-example-tags">{example.tags.map((tag) => <span key={tag}>{tag}</span>)}</div>
          <b>组桌思路 · 你 + 三种互补视角</b>
          <ol>{example.perspectives.map((perspective) => <li key={perspective}>{perspective}</li>)}</ol>
          <p><strong>为什么同桌：</strong>{example.reason}</p>
          <p><strong>不止聊完：</strong>{example.outcome}</p>
        </div>
        <p className="zhihu-connection-demo">仅检索公开内容，不读取你的知乎账号、不修改标签或创建桌子。主 Demo 仍从“先让阿桌认识我”开始。</p>
      </div>
    </details>
  )
}
