import { useEffect, useRef, useState } from 'react'
import ValleyScene, { type ExperiencePhase } from './ValleyScene'

const turns = [
  { name: '沈知遥', role: '自由撰稿人', quote: '真正休息时，我会暂时放弃“有用”。' },
  { name: '周末', role: '产品经理', quote: '我不是没有时间，是不敢让时间空下来。' },
  { name: '林舟', role: '独立开发者', quote: '自由职业以后，我反而更不会下班了。' },
  { name: '许青', role: '心理咨询师', quote: '休息不是奖励，它原本就是生活的一部分。' },
  { name: '圆桌主持', role: '正在递话', quote: '如果不需要向任何人证明，你会怎么度过明天？' },
]

function useReducedMotion() {
  const [reduced, setReduced] = useState(false)
  useEffect(() => {
    const media = window.matchMedia('(prefers-reduced-motion: reduce)')
    const update = () => setReduced(media.matches)
    update()
    media.addEventListener('change', update)
    return () => media.removeEventListener('change', update)
  }, [])
  return reduced
}

function SoundIcon({ muted }: { muted: boolean }) {
  return <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 9v6h4l5 4V5L9 9H5Zm12 1c1 1.2 1 2.8 0 4m2-7c2.8 2.8 2.8 7.2 0 10" className={muted ? 'muted-wave' : ''} />{muted && <path d="m17 10 4 4m0-4-4 4" />}</svg>
}

export default function App() {
  const reducedMotion = useReducedMotion()
  const [phase, setPhase] = useState<ExperiencePhase>('discovering')
  const [activeSpeaker, setActiveSpeaker] = useState(0)
  const [joinOpen, setJoinOpen] = useState(false)
  const [muted, setMuted] = useState(true)
  const [menuOpen, setMenuOpen] = useState(false)
  const timer = useRef<number | null>(null)

  const resetDiscovery = () => {
    if (timer.current !== null) window.clearTimeout(timer.current)
    timer.current = null
    setJoinOpen(false)
    setMenuOpen(false)
    setPhase('discovering')
  }

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return
      if (joinOpen) setJoinOpen(false)
      else if (menuOpen) setMenuOpen(false)
      else resetDiscovery()
    }
    window.addEventListener('keydown', onKeyDown)
    return () => {
      window.removeEventListener('keydown', onKeyDown)
      if (timer.current !== null) window.clearTimeout(timer.current)
    }
  }, [joinOpen, menuOpen])

  useEffect(() => {
    if (phase !== 'seated' || reducedMotion) return
    const interval = window.setInterval(() => setActiveSpeaker((current) => (current + 1) % turns.length), 5200)
    return () => window.clearInterval(interval)
  }, [phase, reducedMotion])

  const approachTable = () => {
    if (phase !== 'discovering') return
    setMenuOpen(false)
    setPhase('approaching')
    timer.current = window.setTimeout(() => {
      setPhase('seated')
      timer.current = null
    }, reducedMotion ? 60 : 2350)
  }

  const seated = phase === 'seated'
  const currentTurn = turns[activeSpeaker]

  return (
    <main className={`valley-experience phase-${phase} ${joinOpen ? 'has-join-open' : ''}`}>
      <div className="art-fallback" aria-hidden="true" />
      <ValleyScene phase={phase} activeSpeaker={activeSpeaker} reducedMotion={reducedMotion} />
      <div className="world-grade" aria-hidden="true" />

      <header className="site-header">
        <button className="brand" type="button" onClick={resetDiscovery} aria-label="回到这张桌的远景">
          <span>组一桌</span><i /> <small>湖边这桌</small>
        </button>
        <div className="header-actions">
          <button className="icon-button" type="button" aria-label={muted ? '开启环境音' : '关闭环境音'} onClick={() => setMuted(!muted)}><SoundIcon muted={muted} /></button>
          <button className="icon-button menu-button" type="button" aria-label="打开桌单" aria-expanded={menuOpen} onClick={() => setMenuOpen(!menuOpen)}><span /><span /></button>
        </div>
      </header>

      <section className="hero-copy" aria-labelledby="valley-title">
        <p className="eyebrow">瑞士山谷 · 4 人已入席</p>
        <h1 id="valley-title">为什么我们<br />越来越不会休息？</h1>
        <p className="missing-line">这一桌，还缺一个真正停下来过的人。</p>
        <button className="approach-button" type="button" onClick={approachTable}><span>靠近这桌</span><span aria-hidden="true">↗</span></button>
      </section>

      <button className="seat-hotspot" type="button" aria-label="靠近湖边的空席" onClick={approachTable}>
        <span className="seat-pulse" /><span className="seat-label"><b>第五席</b>等一个真正停下来过的人</span>
      </button>

      <div className="approach-cue" role="status" aria-live="polite"><span />镜头正在穿过湖边的光</div>

      <section className="seated-hud" aria-hidden={!seated}>
        <button className="back-to-discovery" type="button" onClick={resetDiscovery}>←&nbsp;&nbsp;退回远景</button>
        <div className="discussion-state"><i />讨论正在发生 <span>04 / 05</span></div>

        <div className={`speaker-beacon beacon-${activeSpeaker}`} aria-hidden="true"><i /><span>{currentTurn.name}</span></div>
        <div className="agent-presence" aria-hidden="true"><i /><span>圆桌主持</span></div>
        <div className="question-card"><small>此刻的问题</small><p>我们需要的是休息，<br />还是允许自己停下？</p></div>
        <button className="seat-marker" type="button" onClick={() => setJoinOpen(true)}><i /><span><small>第五席</small>这是你的位置</span></button>

        <div className="conversation-dock" key={activeSpeaker}>
          <p>“{currentTurn.quote}”</p>
          <div><span><b>{currentTurn.name}</b> · {currentTurn.role}</span><i>{String(activeSpeaker + 1).padStart(2, '0')} / 05</i></div>
        </div>
        <button className="join-table-button" type="button" onClick={() => setJoinOpen(true)}><i />坐到空席 <span>→</span></button>
      </section>

      <aside className="join-sheet" aria-hidden={!joinOpen}>
        <button className="panel-close" type="button" aria-label="关闭入席邀请" onClick={() => setJoinOpen(false)}>×</button>
        <p className="panel-kicker">第五席 · 正在等你</p>
        <h2>你不需要带来答案。<br />只需要带来真实经历。</h2>
        <div className="seat-profile"><span>为什么是你</span><p>桌上已经有自由职业、职场压力和心理恢复的视角，但还没有一个真正尝试停下来的人。</p></div>
        <label className="voice-preview"><span>入席后，你想先说什么？</span><textarea placeholder="也许是最近一次，你明明在休息却仍然感到内疚……" /></label>
        <button className="confirm-seat" type="button">以真实经历入席 <span>→</span></button>
      </aside>

      <nav className={`table-menu ${menuOpen ? 'is-open' : ''}`} aria-label="正在发生的桌">
        <p>换一张正在发生的桌</p>
        <button type="button" className="active"><span>瑞士山谷</span>为什么我们越来越不会休息？</button>
        <button type="button" disabled><span>深夜篝火</span>关于离开大城市，他们已经聊了三天。<small>下一张</small></button>
        <button type="button" disabled><span>午后 Workshop</span>如果 AI 替你做一半工作，你会把时间还给什么？<small>下一张</small></button>
      </nav>

      <footer className="scene-footer"><span>移动鼠标 · 感受山谷的空间</span><span>01 <i /> 03</span></footer>
    </main>
  )
}
