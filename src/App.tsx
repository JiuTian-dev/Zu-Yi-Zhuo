import { GlobalCanvas, UseCanvas, ViewportScrollScene } from '@14islands/r3f-scroll-rig'
import { Suspense, useEffect, useRef, useState, type CSSProperties, type MutableRefObject } from 'react'
import * as THREE from 'three'
import { ValleySceneContent, type ExperiencePhase, type ValleySceneProps } from './ValleyScene'
import { humanActors, tableHost, type ActorId } from './actors'
import Hallway, { type GalleryMediaRect } from './Hallway'
import Lobby from './Lobby'
import GalleryFlow, { type GalleryFlowTextureRef } from './GalleryFlow'
import type { AppPhase, TableSummary } from './domain'
import { useLive } from './live/store'
import { joinViewer, requestClose, sendViewerMessage, startLive, stopLive } from './live/backend'
import ClosingCard from './live/ClosingCard'
import { setAmbient, stopAmbient } from './audio/ambient'

const turns = [...humanActors, tableHost]

const ACTION_LABELS: Record<string, string> = {
  PASS: '递话', PROBE: '追问', REFRAME: '换个角度', GROUND: '落在桌面', CLOSE: '收束',
}

const PHASE_LABELS: Record<string, string> = {
  opening: '开场', explore: '探索', tension: '张力', deepen: '深入', close: '收束',
}

function speakerName(participantId: string): string {
  if (participantId === 'table-host') return '圆桌主持'
  if (participantId === 'viewer') return '你'
  return turns.find((turn) => turn.id === participantId)?.displayName ?? participantId
}

function speakerRole(participantId: string): string {
  if (participantId === 'table-host') return 'Table Host'
  if (participantId === 'viewer') return '第五席'
  return turns.find((turn) => turn.id === participantId)?.role ?? '嘉宾'
}
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

function ValleyExperience({ onExit, enhanced, appPhase, entryIntent }: { onExit(): void; enhanced: boolean; appPhase: AppPhase; entryIntent: 'listen' | 'join' | null }) {
  const reducedMotion = useReducedMotion()
  const [phase, setPhase] = useState<ExperiencePhase>('discovering')
  const [activeSpeaker, setActiveSpeaker] = useState(0)
  const [hoveredActorId, setHoveredActorId] = useState<ActorId | null>(null)
  const [joinOpen, setJoinOpen] = useState(false)
  const [joined, setJoined] = useState(false)
  const [seatDraft, setSeatDraft] = useState('')
  const [joinError, setJoinError] = useState(false)
  const [menuOpen, setMenuOpen] = useState(false)
  const [soundOn, setSoundOn] = useState(false)
  const timer = useRef<number | null>(null)
  const experienceRef = useRef<HTMLElement>(null!)
  const menuButtonRef = useRef<HTMLButtonElement>(null)
  const joinOpenerRef = useRef<HTMLButtonElement | null>(null)
  const seatDraftRef = useRef<HTMLTextAreaElement>(null)
  const joinedStatusRef = useRef<HTMLDivElement>(null)
  const [messageDraft, setMessageDraft] = useState('')

  const liveStatus = useLive((state) => state.status)
  const liveMessages = useLive((state) => state.messages)
  const liveSpeaking = useLive((state) => state.speakingId)
  const liveHost = useLive((state) => state.hostAction)
  const livePhase = useLive((state) => state.phase)
  const liveSubQuestion = useLive((state) => state.subQuestion)
  const closeState = useLive((state) => state.closeState)
  const liveBaseline = useLive((state) => state.baseline)
  const livePersonalCard = useLive((state) => state.personalCard)

  useEffect(() => {
    void startLive()
    return () => stopLive()
  }, [])

  const focusOpenerFrom = (panelSelector: string, opener: HTMLButtonElement | null) => {
    const active = document.activeElement
    if (active instanceof HTMLElement && active.closest(panelSelector)) opener?.focus({ preventScroll: true })
  }
  const closeJoin = () => {
    focusOpenerFrom('.join-sheet', joinOpenerRef.current)
    setJoinOpen(false)
  }
  const closeMenu = () => {
    focusOpenerFrom('.table-menu', menuButtonRef.current)
    setMenuOpen(false)
  }
  const openJoin = (opener: HTMLButtonElement) => {
    if (joined) return
    joinOpenerRef.current = opener
    setJoinError(false)
    setJoinOpen(true)
  }

  const confirmSeat = () => {
    if (!seatDraft.trim()) {
      setJoinError(true)
      seatDraftRef.current?.focus({ preventScroll: true })
      return
    }
    experienceRef.current?.focus({ preventScroll: true })
    setJoinError(false)
    setJoinOpen(false)
    setJoined(true)
    void joinViewer()
  }

  const submitMessage = (event: { preventDefault(): void }) => {
    event.preventDefault()
    if (!sendViewerMessage(messageDraft)) return
    setMessageDraft('')
  }

  const resetDiscovery = () => {
    if (timer.current !== null) window.clearTimeout(timer.current)
    timer.current = null
    const active = document.activeElement
    if (active instanceof HTMLElement && active.closest('.join-sheet,.table-menu')) experienceRef.current?.focus({ preventScroll: true })
    setJoinOpen(false)
    setMenuOpen(false)
    setHoveredActorId(null)
    setPhase('discovering')
  }

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return
      if (joinOpen) closeJoin()
      else if (menuOpen) closeMenu()
      else resetDiscovery()
    }
    window.addEventListener('keydown', onKeyDown)
    return () => {
      window.removeEventListener('keydown', onKeyDown)
    }
  }, [joinOpen, menuOpen])

  useEffect(() => () => {
    if (timer.current !== null) window.clearTimeout(timer.current)
    stopAmbient()
  }, [])

  useEffect(() => {
    if (phase !== 'seated' || reducedMotion) return
    const interval = window.setInterval(() => setActiveSpeaker((current) => (current + 1) % turns.length), 5200)
    return () => window.clearInterval(interval)
  }, [phase, reducedMotion])

  useEffect(() => {
    if (!joinOpen) return
    const frame = window.requestAnimationFrame(() => seatDraftRef.current?.focus({ preventScroll: true }))
    return () => window.cancelAnimationFrame(frame)
  }, [joinOpen])

  useEffect(() => {
    if (joined) joinedStatusRef.current?.focus({ preventScroll: true })
  }, [joined])

  useEffect(() => {
    if (appPhase === 'world') experienceRef.current.focus({ preventScroll: true })
  }, [appPhase])

  useEffect(() => {
    if (appPhase !== 'world' || phase !== 'seated' || entryIntent !== 'join') return
    if (joined || joinOpen) return
    setJoinError(false)
    setJoinOpen(true)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [appPhase, phase])

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
  const listening = entryIntent === 'listen' && !joined
  const liveActive = liveStatus === 'live' || liveStatus === 'mock'
  const speakingTurn = liveActive && liveSpeaking ? turns.find((turn) => turn.id === liveSpeaking) ?? null : null
  const currentTurn = speakingTurn ?? turns[activeSpeaker]
  const lastLive = liveActive ? liveMessages[liveMessages.length - 1] ?? null : null
  const sceneProps: ValleySceneProps = { phase, activeActorId: currentTurn.id, hoveredActorId, reducedMotion }

  return (
    <main ref={experienceRef} tabIndex={-1} inert={appPhase !== 'world'} aria-hidden={appPhase !== 'world'} className={`valley-experience app-${appPhase} phase-${phase} ${enhanced ? 'is-enhanced' : ''} ${joinOpen ? 'has-join-open' : ''} ${listening ? 'is-listening' : ''}`}>
      <div className="art-fallback" aria-hidden="true" />
      {enhanced && <UseCanvas {...sceneProps} track={experienceRef}><ValleyCanvasPortal track={experienceRef} {...sceneProps} /></UseCanvas>}
      {!enhanced && seated && <img className="dom-host-fallback" src="/assets/actors/table-host-silence.png" alt="" aria-hidden="true" />}
      <div className="world-grade" aria-hidden="true" />

      <header className="site-header">
        <button className="brand" type="button" onClick={phase === 'discovering' ? onExit : resetDiscovery} aria-label={phase === 'discovering' ? '回到桌单' : '回到这张桌的远景'}>
          <span>组一桌</span><i /> <small>湖边这桌</small>
        </button>
        <div className="header-actions">
          <button className={`icon-button ${soundOn ? '' : 'sound-unavailable'}`} type="button" aria-pressed={soundOn} aria-label={soundOn ? '关闭环境音' : '开启环境音'} title={soundOn ? '关闭环境音' : '开启环境音'} onClick={() => { const next = !soundOn; setSoundOn(next); setAmbient(next, 'valley') }}>
            <SoundIcon muted={!soundOn} />
          </button>
          <button ref={menuButtonRef} className="icon-button menu-button" type="button" aria-label={menuOpen ? '关闭桌单' : '打开桌单'} aria-expanded={menuOpen} onClick={() => menuOpen ? closeMenu() : setMenuOpen(true)}><span /><span /></button>
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
        <div className="discussion-state"><i />{liveActive ? `${PHASE_LABELS[livePhase] ?? '讨论'}进行中` : '讨论正在发生'} <span>{liveActive ? `${String(liveMessages.length).padStart(2, '0')} 条` : joined ? '05 / 05' : '04 / 05'}</span></div>
        {liveStatus === 'connecting' && <div className="live-badge" role="status">正在连接这张桌…</div>}
        {liveStatus === 'error' && <div className="live-badge is-error" role="status">实时连接中断，显示最后状态</div>}

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
        <div className="question-card">
          <small>{liveActive && liveSubQuestion ? '问题 · 推进中' : '此刻的问题'}</small>
          <p>{liveActive && liveSubQuestion ? liveSubQuestion : <>我们需要的是休息，<br />还是允许自己停下？</>}</p>
        </div>
        <button className="seat-marker" type="button" disabled={joined} onClick={(event) => openJoin(event.currentTarget)}><i /><span><small>{listening ? '旁听中' : '第五席'}</small>{joined ? '你已在这一席' : listening ? '这是你的位置 · 随时可坐' : '这是你的位置'}</span></button>

        <div className="conversation-dock">
          {liveActive && lastLive ? (
            liveMessages.slice(-2).map((message, index, list) => (
              <p key={`${message.participantId}-${liveMessages.length - list.length + index}`} className={index === list.length - 1 ? 'is-latest' : 'is-previous'}>
                <b className={message.fromHost ? 'host-name' : ''}>
                  {speakerName(message.participantId)}{message.action && ACTION_LABELS[message.action] ? ` · ${ACTION_LABELS[message.action]}` : ''}
                </b>
                “{message.text}”
              </p>
            ))
          ) : (
            <p key={activeSpeaker}>“{currentTurn.quote}”</p>
          )}
          <div>
            <span><b>{lastLive ? speakerName(lastLive.participantId) : currentTurn.displayName}</b> · {lastLive ? speakerRole(lastLive.participantId) : currentTurn.role}</span>
            <i>{liveActive ? `${String(liveMessages.length).padStart(2, '0')} 条发言` : `${String(activeSpeaker + 1).padStart(2, '0')} / 05`}</i>
          </div>
          {joined && liveActive && (
            <form className="viewer-input" onSubmit={submitMessage}>
              <input value={messageDraft} onChange={(event) => setMessageDraft(event.target.value)} placeholder="把你的真实经历说给这桌听…" aria-label="对这桌发言" maxLength={140} />
              <button type="submit" disabled={!messageDraft.trim()}>说</button>
            </form>
          )}
        </div>
        {liveActive && closeState === 'idle' && <button className="close-table-button" type="button" onClick={() => requestClose()}>收这桌 <span>→</span></button>}
        {closeState === 'started' && <div className="closing-progress" role="status">正在收桌 · 沉淀共识与分歧…</div>}
        {closeState === 'ready' && liveBaseline && <ClosingCard baseline={liveBaseline} personalCard={livePersonalCard} onReturn={onExit} />}
        <button className="join-table-button" type="button" disabled={joined} onClick={(event) => openJoin(event.currentTarget)}><i />{joined ? '已坐到第五席' : '坐到空席'} <span>{joined ? '✓' : '→'}</span></button>
        {joined && <div ref={joinedStatusRef} className="join-success" role="status" tabIndex={-1} aria-live="polite" data-visible="true">
          <small>第五席 · 已入席</small><span>你的真实经历，已经来到桌边。</span>
        </div>}
      </section>

      <aside className="join-sheet" aria-hidden={!joinOpen} inert={!joinOpen}>
        <button className="panel-close" type="button" aria-label="关闭入席邀请" onClick={closeJoin}>×</button>
        <p className="panel-kicker">第五席 · 正在等你</p>
        <h2>你不需要带来答案。<br />只需要带来真实经历。</h2>
        <div className="seat-profile"><span>为什么是你</span><p>桌上已经有自由职业、职场压力和心理恢复的视角，但还没有一个真正尝试停下来的人。</p></div>
        <label className="voice-preview"><span>入席后，你想先说什么？</span><textarea ref={seatDraftRef} value={seatDraft} aria-invalid={joinError} aria-describedby={joinError ? 'seat-draft-error' : undefined} onChange={(event) => { setSeatDraft(event.target.value); if (joinError) setJoinError(false) }} placeholder="也许是最近一次，你明明在休息却仍然感到内疚……" /></label>
        {joinError && <p id="seat-draft-error" className="join-error" role="alert">先留下一句真实经历，再坐到桌边。</p>}
        <button className="confirm-seat" type="button" onClick={confirmSeat}>以真实经历入席 <span>→</span></button>
      </aside>

      <nav className={`table-menu ${menuOpen ? 'is-open' : ''}`} aria-label="正在发生的桌" aria-hidden={!menuOpen} inert={!menuOpen}>
        <p>换一张正在发生的桌</p>
        <button type="button" className="active" onClick={closeMenu}><span>瑞士山谷</span>为什么我们越来越不会休息？</button>
        <button type="button" disabled><span>深夜篝火</span>关于离开大城市，他们已经聊了三天。<small>下一张</small></button>
        <button type="button" disabled><span>午后 Workshop</span>如果 AI 替你做一半工作，你会把时间还给什么？<small>下一张</small></button>
      </nav>

      <footer className="scene-footer"><span>移动鼠标 · 感受山谷的空间</span><span>01 <i /> 03</span></footer>
    </main>
  )
}

interface TransitionSnapshot { table: TableSummary; rect: GalleryMediaRect }

function TransitionCover({ snapshot }: { snapshot: TransitionSnapshot }) {
  const style = {
    '--portal-left': `${snapshot.rect.left}px`, '--portal-top': `${snapshot.rect.top}px`,
    '--portal-width': `${snapshot.rect.width}px`, '--portal-height': `${snapshot.rect.height}px`,
  } as CSSProperties
  return <div className="transition-cover" style={style} aria-hidden="true"><img src={snapshot.table.sceneTexture} alt="" style={{ objectPosition: `${snapshot.table.coverFocus.x * 100}% ${snapshot.table.coverFocus.y * 100}%` }} /></div>
}

export default function App() {
  const [appPhase, setAppPhase] = useState<AppPhase>('gallery')
  const [enhanced, setEnhanced] = useState(false)
  const [transition, setTransition] = useState<TransitionSnapshot | null>(null)
  const [lobbyTable, setLobbyTable] = useState<TableSummary | null>(null)
  const [entryIntent, setEntryIntent] = useState<'listen' | 'join' | null>(null)
  const flowTexture = useRef<THREE.Texture | null>(zeroFlowTexture) as GalleryFlowTextureRef
  const transitionTimer = useRef<number | null>(null)
  const pendingRectRef = useRef<GalleryMediaRect | null>(null)
  const reducedMotion = useReducedMotion()
  useEffect(() => {
    setEnhanced(canEnhance())
    return () => {
      if (transitionTimer.current !== null) window.clearTimeout(transitionTimer.current)
      document.documentElement.classList.remove('js-has-global-canvas', 'js-global-canvas-error')
    }
  }, [])
  const schedulePhase = (phase: AppPhase, delay: number) => {
    if (transitionTimer.current !== null) window.clearTimeout(transitionTimer.current)
    transitionTimer.current = window.setTimeout(() => {
      setAppPhase(phase)
      transitionTimer.current = null
    }, delay)
  }
  const openLobby = (table: TableSummary, rect: GalleryMediaRect) => {
    if (appPhase !== 'gallery' || table.entryMode !== 'immersive') return
    pendingRectRef.current = rect
    setLobbyTable(table)
    setAppPhase('lobby')
  }
  const closeLobby = () => {
    if (appPhase !== 'lobby') return
    setLobbyTable(null)
    setAppPhase('gallery')
  }
  const startWorld = (intent: 'listen' | 'join') => {
    if (appPhase !== 'lobby' || !lobbyTable) return
    setEntryIntent(intent)
    const viewportRect: GalleryMediaRect = { left: 0, top: 0, width: window.innerWidth, height: window.innerHeight }
    setTransition({ table: lobbyTable, rect: pendingRectRef.current ?? viewportRect })
    setAppPhase('expanding')
    schedulePhase('world', reducedMotion ? 180 : 1100)
  }
  const exitTable = () => {
    if (appPhase !== 'world') return
    if (document.activeElement instanceof HTMLElement) document.activeElement.blur()
    setEntryIntent(null)
    setLobbyTable(null)
    setAppPhase('collapsing')
    schedulePhase('gallery', reducedMotion ? 160 : 450)
  }
  const showGallery = appPhase === 'gallery' || appPhase === 'lobby' || appPhase === 'expanding' || appPhase === 'collapsing'
  const showWorld = appPhase === 'expanding' || appPhase === 'world' || appPhase === 'collapsing'
  return (
    <>
      {enhanced && <GlobalCanvas dpr={[1, 1.5]} gl={{ alpha: true, antialias: true }} onError={() => setEnhanced(false)}>{(appPhase === 'gallery' || appPhase === 'lobby') && <GalleryFlow textureRef={flowTexture} />}</GlobalCanvas>}
      {showGallery && <Hallway phase={appPhase} returnFocusId={transition?.table.id ?? null} onEnter={openLobby} enhanced={enhanced} flowTexture={flowTexture} />}
      {showWorld && <ValleyExperience appPhase={appPhase} enhanced={enhanced} entryIntent={entryIntent} onExit={exitTable} />}
      {appPhase === 'lobby' && lobbyTable && <Lobby table={lobbyTable} onClose={closeLobby} onListen={() => startWorld('listen')} onJoin={() => startWorld('join')} />}
      {appPhase === 'expanding' && transition && <><div className="transition-backdrop" aria-hidden="true" /><TransitionCover snapshot={transition} /></>}
    </>
  )
}
