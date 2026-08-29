import { GlobalCanvas, UseCanvas, ViewportScrollScene } from '@14islands/r3f-scroll-rig'
import { Suspense, useEffect, useRef, useState, type MutableRefObject } from 'react'
import * as THREE from 'three'
import ValleyScene, { ValleySceneContent, type ExperiencePhase, type ValleySceneProps } from './ValleyScene'
import { humanActors, tableHost, type ActorId } from './actors'
import Gallery from './Gallery'
import GalleryFlow, { type GalleryFlowTextureRef } from './GalleryFlow'
import type { AppPhase, TableSummary } from './domain'

const turns = [...humanActors, tableHost]
const zeroFlowTexture = new THREE.DataTexture(new Uint8Array([0, 0, 0, 0]), 1, 1, THREE.RGBAFormat, THREE.UnsignedByteType)
zeroFlowTexture.needsUpdate = true

function canEnhance() {
  if (!matchMedia('(pointer:fine)').matches || matchMedia('(prefers-reduced-motion: reduce)').matches) return false
  const canvas = document.createElement('canvas')
  const context = canvas.getContext('webgl2', { failIfMajorPerformanceCaveat: true }) ?? canvas.getContext('webgl')
  if (!context) return false
  context.getExtension('WEBGL_lose_context')?.loseContext()
  return true
}

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

interface ValleyCanvasPortalProps extends ValleySceneProps {
  track: MutableRefObject<HTMLElement>
}

function ValleyCanvasPortal({ track, ...sceneProps }: ValleyCanvasPortalProps) {
  return (
    <ViewportScrollScene
      track={track}
      visible
      hideOffscreen={false}
      camera={{ position: [0, 0, 12.22], fov: 42, near: .1, far: 40 }}
    >
      {() => <Suspense fallback={null}><ValleySceneContent {...sceneProps} /></Suspense>}
    </ViewportScrollScene>
  )
}

function ValleyExperience({ onExit, enhanced }: { onExit(): void; enhanced: boolean }) {
  const reducedMotion = useReducedMotion()
  const [phase, setPhase] = useState<ExperiencePhase>('discovering')
  const [activeSpeaker, setActiveSpeaker] = useState(0)
  const [hoveredActorId, setHoveredActorId] = useState<ActorId | null>(null)
  const [joinOpen, setJoinOpen] = useState(false)
  const [muted, setMuted] = useState(true)
  const [menuOpen, setMenuOpen] = useState(false)
  const timer = useRef<number | null>(null)
  const experienceRef = useRef<HTMLElement>(null!)

  const resetDiscovery = () => {
    if (timer.current !== null) window.clearTimeout(timer.current)
    timer.current = null
    if (document.activeElement instanceof HTMLElement) document.activeElement.blur()
    setJoinOpen(false)
    setMenuOpen(false)
    setHoveredActorId(null)
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
  const sceneProps: ValleySceneProps = { phase, activeActorId: currentTurn.id, hoveredActorId, reducedMotion }

  return (
    <main ref={experienceRef} className={`valley-experience phase-${phase} ${enhanced ? 'is-enhanced' : ''} ${joinOpen ? 'has-join-open' : ''}`}>
      <div className="art-fallback" aria-hidden="true" />
      {enhanced
        ? <UseCanvas {...sceneProps} track={experienceRef}><ValleyCanvasPortal track={experienceRef} {...sceneProps} /></UseCanvas>
        : <ValleyScene {...sceneProps} />}
      <div className="world-grade" aria-hidden="true" />

      <header className="site-header">
        <button className="brand" type="button" onClick={phase === 'discovering' ? onExit : resetDiscovery} aria-label={phase === 'discovering' ? '回到桌单' : '回到这张桌的远景'}>
          <span>组一桌</span><i /> <small>湖边这桌</small>
        </button>
        <div className="header-actions">
          <button className="icon-button" type="button" aria-label={muted ? '开启环境音' : '关闭环境音'} onClick={() => setMuted(!muted)}><SoundIcon muted={muted} /></button>
          <button className="icon-button menu-button" type="button" aria-label="打开桌单" aria-expanded={menuOpen} onClick={() => setMenuOpen(!menuOpen)}><span /><span /></button>
        </div>
      </header>

      <section className="hero-copy" aria-labelledby="valley-title" inert={seated || phase === 'approaching'}>
        <p className="eyebrow">瑞士山谷 · 4 人已入席</p>
        <h1 id="valley-title">为什么我们<br />越来越不会休息？</h1>
        <p className="missing-line">这一桌，还缺一个真正停下来过的人。</p>
        <button className="approach-button" type="button" onClick={approachTable}><span>靠近这桌</span><span aria-hidden="true">↗</span></button>
      </section>

      <button className="seat-hotspot" type="button" aria-label="靠近湖边的空席" onClick={approachTable} disabled={phase !== 'discovering'}>
        <span className="seat-pulse" /><span className="seat-label"><b>第五席</b>等一个真正停下来过的人</span>
      </button>

      <div className="approach-cue" role="status" aria-live="polite"><span />镜头正在穿过湖边的光</div>

      <section className="seated-hud" aria-hidden={!seated} inert={!seated}>
        <button className="back-to-discovery" type="button" onClick={resetDiscovery}>←&nbsp;&nbsp;退回远景</button>
        <div className="discussion-state"><i />讨论正在发生 <span>04 / 05</span></div>

        <div className="actor-hotspots" aria-label="桌上成员">
          {humanActors.map((actor) => (
            <button
              key={actor.id}
              className={`actor-hotspot ${actor.hotspotClass}`}
              type="button"
              data-active={currentTurn.id === actor.id}
              aria-label={`查看${actor.displayName}，${actor.role}`}
              onMouseEnter={() => setHoveredActorId(actor.id)}
              onMouseLeave={() => setHoveredActorId(null)}
              onFocus={() => setHoveredActorId(actor.id)}
              onBlur={() => setHoveredActorId(null)}
            >
              <i />
              <span className="actor-profile"><small>{actor.role}</small><b>{actor.displayName}</b><em>{actor.whyHere}</em><strong>知乎用户 · {actor.userId?.split('/').at(-1)}</strong></span>
            </button>
          ))}
          <button
            className="actor-hotspot actor-host"
            type="button"
            data-active={currentTurn.id === tableHost.id}
            aria-label="查看圆桌主持"
            onMouseEnter={() => setHoveredActorId(tableHost.id)}
            onMouseLeave={() => setHoveredActorId(null)}
            onFocus={() => setHoveredActorId(tableHost.id)}
            onBlur={() => setHoveredActorId(null)}
          >
            <i />
            <span className="actor-profile"><small>第六席 · Table Host</small><b>圆桌主持</b><em>认真听，把问题递给此刻最值得说话的人。</em><strong>状态 · {currentTurn.id === tableHost.id ? 'PASS 递话' : 'SILENCE 听'}</strong></span>
          </button>
        </div>
        <div className="question-card"><small>此刻的问题</small><p>我们需要的是休息，<br />还是允许自己停下？</p></div>
        <button className="seat-marker" type="button" onClick={() => setJoinOpen(true)}><i /><span><small>第五席</small>这是你的位置</span></button>

        <div className="conversation-dock" key={activeSpeaker}>
          <p>“{currentTurn.quote}”</p>
          <div><span><b>{currentTurn.displayName}</b> · {currentTurn.role}</span><i>{String(activeSpeaker + 1).padStart(2, '0')} / 05</i></div>
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

export default function App() {
  const [appPhase, setAppPhase] = useState<AppPhase>('gallery')
  const [enhanced, setEnhanced] = useState(false)
  const flowTexture = useRef<THREE.Texture | null>(zeroFlowTexture) as GalleryFlowTextureRef
  useEffect(() => {
    setEnhanced(canEnhance())
    return () => document.documentElement.classList.remove('js-has-global-canvas', 'js-global-canvas-error')
  }, [])
  const enterTable = (table: TableSummary) => {
    if (table.entryMode === 'immersive') setAppPhase('world')
  }
  return (
    <>
      {enhanced && <GlobalCanvas dpr={[1, 1.5]} gl={{ alpha: true, antialias: true }} onError={() => setEnhanced(false)}>{appPhase === 'gallery' && <GalleryFlow textureRef={flowTexture} />}</GlobalCanvas>}
      {appPhase === 'gallery'
        ? <Gallery onEnter={enterTable} enhanced={enhanced} flowTexture={flowTexture} />
        : <ValleyExperience enhanced={enhanced} onExit={() => setAppPhase('gallery')} />}
    </>
  )
}
