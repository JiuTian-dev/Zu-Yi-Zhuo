import { useEffect, useRef, useState } from 'react'
import ValleyScene from './ValleyScene'

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
  return muted ? (
    <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 9v6h4l5 4V5L9 9H5Zm12.2.8 3.6 3.6m0-3.6-3.6 3.6" /></svg>
  ) : (
    <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 9v6h4l5 4V5L9 9H5Zm12 1c1 1.2 1 2.8 0 4m2-7c2.8 2.8 2.8 7.2 0 10" /></svg>
  )
}

export default function App() {
  const reducedMotion = useReducedMotion()
  const [focused, setFocused] = useState(false)
  const [seatOpen, setSeatOpen] = useState(false)
  const [muted, setMuted] = useState(true)
  const [menuOpen, setMenuOpen] = useState(false)
  const approachTimer = useRef<number | null>(null)

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        if (approachTimer.current !== null) window.clearTimeout(approachTimer.current)
        setSeatOpen(false)
        setMenuOpen(false)
        setFocused(false)
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => {
      window.removeEventListener('keydown', onKeyDown)
      if (approachTimer.current !== null) window.clearTimeout(approachTimer.current)
    }
  }, [])

  const approachTable = () => {
    if (approachTimer.current !== null) window.clearTimeout(approachTimer.current)
    setFocused(true)
    approachTimer.current = window.setTimeout(() => {
      setSeatOpen(true)
      approachTimer.current = null
    }, reducedMotion ? 0 : 650)
  }

  return (
    <main className={`valley-experience ${focused ? 'is-focused' : ''} ${seatOpen ? 'has-seat-open' : ''}`}>
      <div className="art-fallback" aria-hidden="true" />
      <ValleyScene focused={focused} reducedMotion={reducedMotion} />
      <div className="world-grade" aria-hidden="true" />

      <header className="site-header">
        <button className="brand" type="button" onClick={() => { setFocused(false); setSeatOpen(false) }}>
          <span className="brand-mark">组一桌</span>
          <span className="brand-place">瑞士山谷</span>
        </button>
        <div className="header-actions">
          <button className="icon-button" type="button" aria-label={muted ? '开启环境音' : '关闭环境音'} onClick={() => setMuted(!muted)}>
            <SoundIcon muted={muted} />
          </button>
          <button className="icon-button menu-button" type="button" aria-label="打开世界菜单" aria-expanded={menuOpen} onClick={() => setMenuOpen(!menuOpen)}>
            <span /><span />
          </button>
        </div>
      </header>

      <section className="hero-copy" aria-labelledby="valley-title">
        <p className="eyebrow"><span /> 湖边 · 4 人已入席</p>
        <h1 id="valley-title">为什么我们<br />越来越不会休息？</h1>
        <p className="missing-line">这一桌，还缺一个<br />真正停下来过的人。</p>
        <button className="approach-button" type="button" onClick={approachTable}>
          <span>靠近这桌</span><span aria-hidden="true">↗</span>
        </button>
      </section>

      <button
        className="seat-hotspot"
        type="button"
        aria-label="查看这一桌的空席"
        aria-expanded={seatOpen}
        onClick={() => { setFocused(true); setSeatOpen(!seatOpen) }}
      >
        <span className="seat-pulse" />
        <span className="seat-label"><b>空席</b>等一个真正停下来过的人</span>
      </button>

      <aside className="table-panel" aria-hidden={!seatOpen}>
        <button className="panel-close" type="button" aria-label="关闭桌子详情" onClick={() => setSeatOpen(false)}>×</button>
        <p className="panel-kicker">正在形成的桌 · 04 / 05</p>
        <h2>他们带来了四种<br />不同的生活节奏。</h2>
        <ul className="people-list">
          <li><i className="avatar cream" /><span><b>沈知遥</b>自由撰稿人 · 在山里住了两年</span></li>
          <li><i className="avatar rust" /><span><b>周末</b>互联网产品经理 · 每天通勤三小时</span></li>
          <li><i className="avatar indigo" /><span><b>林舟</b>独立开发者 · 正在重新安排工作</span></li>
          <li><i className="avatar teal" /><span><b>许青</b>心理咨询师 · 研究倦怠与恢复</span></li>
        </ul>
        <div className="why-you">
          <span>为什么可能是你</span>
          <p>他们谈过效率、自由和逃离，但还没人真正试过停下来。</p>
        </div>
        <button className="sit-button" type="button">坐下来听听 <span>→</span></button>
      </aside>

      <nav className={`world-menu ${menuOpen ? 'is-open' : ''}`} aria-label="世界菜单">
        <p>发现世界</p>
        <button type="button" className="active"><span>01</span> 瑞士山谷</button>
        <button type="button" disabled><span>02</span> 深夜篝火 <small>即将开放</small></button>
        <button type="button" disabled><span>03</span> 午后 Workshop <small>即将开放</small></button>
      </nav>

      <footer className="scene-footer">
        <span>移动鼠标，看看这片山谷</span>
        <span className="world-index">01 <i /> 03</span>
      </footer>
    </main>
  )
}
