import { useEffect, useRef, useState, type CSSProperties } from 'react'
import { humanActors, tableHost, type ActorId } from './actors'
import TableSea, { type GalleryMediaRect } from './TableSea'
import Lobby from './Lobby'
import type { AppPhase, TableSummary } from './domain'
import { useLive } from './live/store'
import { currentTableId, joinViewer, requestClose, requestNudge, sendViewerMessage, startLive, stopLive } from './live/backend'
import ClosingCard from './live/ClosingCard'
import DiscussionPanel from './live/DiscussionPanel'
import type { LobbyFitPreviewLike, LobbyPreviewLike } from './live/contract'
import { loadLobby, loadLobbyFit, ensureTable, viewerSeed } from './live/backend'
import { fetchDiscovery, selectTable } from './live/api'
import { setAmbient, stopAmbient } from './audio/ambient'
import TableWorld from './TableWorld'

const turns = [...humanActors, tableHost]

// PRODUCT DOM — deliberately stable screen anchors; they are not 3D objects
// and never write camera or backend state.
const actorAnchors: Partial<Record<ActorId | 'viewer', { x: number; y: number }>> = {
  'shen-zhiyao': { x: 43, y: 42 },
  'zhou-mo': { x: 54, y: 35 },
  'lin-zhou': { x: 66, y: 44 },
  'xu-qing': { x: 61, y: 59 },
  'table-host': { x: 48, y: 28 },
  viewer: { x: 48, y: 76 },
}

const ACTION_LABELS: Record<string, string> = {
  PASS: '递话', PROBE: '追问', REFRAME: '换个角度', GROUND: '落在桌面', CLOSE: '收束',
}

const PHASE_LABELS: Record<string, string> = {
  opening: '开场', explore: '探索', tension: '张力', deepen: '深入', close: '收束',
}

type ExperiencePhase = 'discovering' | 'approaching' | 'seated'
function speakerName(participantId: string, members: Array<{ participant_id: string; display_name: string }>): string {
  if (participantId === 'table-host') return '圆桌主持'
  if (participantId === 'viewer') return '你'
  return members.find((member) => member.participant_id === participantId)?.display_name
    ?? turns.find((turn) => turn.id === participantId)?.displayName
    ?? participantId
}

function speakerRole(participantId: string, members: Array<{ participant_id: string; role: string }>): string {
  if (participantId === 'table-host') return 'Table Host'
  if (participantId === 'viewer') return '第五席'
  return members.find((member) => member.participant_id === participantId)?.role
    ?? turns.find((turn) => turn.id === participantId)?.role
    ?? '嘉宾'
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

function ValleyExperience({ onExit, appPhase, entryIntent, table, lobby, discovery }: { onExit(): void; appPhase: AppPhase; entryIntent: 'listen' | 'join' | null; table: TableSummary; lobby: LobbyPreviewLike | null; discovery: LobbyPreviewLike[] }) {
  const reducedMotion = useReducedMotion()
  const [phase, setPhase] = useState<ExperiencePhase>('discovering')
  const [joinOpen, setJoinOpen] = useState(false)
  const [joined, setJoined] = useState(false)
  const [seatDraft, setSeatDraft] = useState('')
  const [joinError, setJoinError] = useState(false)
  const [joinDismissed, setJoinDismissed] = useState(false)
  const [profileShared, setProfileShared] = useState(false)
  const [menuOpen, setMenuOpen] = useState(false)
  const [soundOn, setSoundOn] = useState(false)
  const [historyOpen, setHistoryOpen] = useState(false)
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
  const liveTableState = useLive((state) => state.tableState)
  const liveSeatCount = useLive((state) => state.seatCount)
  const liveViewerJoined = useLive((state) => state.viewerJoined)
  const liveTableMode = useLive((state) => state.tableMode)
  const groundingCard = useLive((state) => state.groundingCard)
  const safetyNotice = useLive((state) => state.safetyNotice)
  const latestReflection = useLive((state) => state.latestReflection)
  const tableMembers = liveTableState
    ? Object.values(liveTableState.participants).map((participant) => ({
      participant_id: participant.participant_id,
      display_name: participant.display_name,
      role: participant.role,
    }))
    : lobby?.members ?? humanActors.map((actor) => ({ participant_id: actor.id, display_name: actor.displayName, role: actor.role }))
  const roomTurns = tableMembers.map((member) => ({ ...member, id: member.participant_id, displayName: member.display_name, whyHere: '', quote: '', role: member.role }))
  const allTurns = [...roomTurns, { ...tableHost, participant_id: tableHost.id, display_name: tableHost.displayName }]

  useEffect(() => {
    void startLive(table.id, table.hook)
    return () => stopLive()
  }, [table.id, table.hook])

  useEffect(() => {
    let raf = 0
    const apply = () => {
      raf = requestAnimationFrame(apply)
      const root = experienceRef.current
      if (!root) return
      root.querySelectorAll<HTMLElement>('[data-anchor]').forEach((el) => {
        const id = (el.dataset.anchor || '') as ActorId | 'viewer'
        const anchor = actorAnchors[id]
        if (!anchor) return
        el.style.left = `${anchor.x}%`
        el.style.top = `${anchor.y}%`
        el.style.transform = 'translate(-50%, -50%)'
      })
    }
    raf = requestAnimationFrame(apply)
    return () => cancelAnimationFrame(raf)
  }, [])

  const focusOpenerFrom = (panelSelector: string, opener: HTMLButtonElement | null) => {
    const active = document.activeElement
    if (active instanceof HTMLElement && active.closest(panelSelector)) opener?.focus({ preventScroll: true })
  }
  const closeJoin = () => {
    focusOpenerFrom('.join-sheet', joinOpenerRef.current)
    setJoinDismissed(true)
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
    setJoinDismissed(false)
    setJoinOpen(true)
  }

  const confirmSeat = async () => {
    if (!seatDraft.trim()) {
      setJoinError(true)
      seatDraftRef.current?.focus({ preventScroll: true })
      return
    }
    const connected = await joinViewer(seatDraft, profileShared)
    if (!connected) {
      setJoinError(true)
      return
    }
    experienceRef.current?.focus({ preventScroll: true })
    setJoinError(false)
    setJoinOpen(false)
    setJoined(true)
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
    setHistoryOpen(false)
    setMenuOpen(false)
    setJoinDismissed(false)
    setPhase('discovering')
  }

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return
      if (historyOpen) setHistoryOpen(false)
      else if (joinOpen) closeJoin()
      else if (menuOpen) closeMenu()
      else resetDiscovery()
    }
    window.addEventListener('keydown', onKeyDown)
    return () => {
      window.removeEventListener('keydown', onKeyDown)
    }
  }, [historyOpen, joinOpen, menuOpen])

  useEffect(() => () => {
    if (timer.current !== null) window.clearTimeout(timer.current)
    stopAmbient()
  }, [])

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
    if (appPhase !== 'world' || entryIntent !== 'join') return
    if (phase === 'discovering') {
      // Entering from the lobby starts the same short camera approach; there
      // is no second scene and no vehicle/player state behind this transition.
      setPhase('approaching')
      timer.current = window.setTimeout(() => {
        setPhase('seated')
        timer.current = null
      }, reducedMotion ? 60 : 2350)
      return
    }
    if (phase !== 'seated') return
    if (joined || liveViewerJoined || joinOpen || joinDismissed) return
    setJoinError(false)
    setJoinOpen(true)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [appPhase, entryIntent, phase, reducedMotion, liveViewerJoined, joinOpen, joinDismissed, joined])

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
  const hasJoined = joined || liveViewerJoined
  const listening = entryIntent === 'listen' && !hasJoined
  const liveActive = liveStatus === 'live' || liveStatus === 'mock'
  const speakingTurn = liveActive && liveSpeaking ? allTurns.find((turn) => turn.id === liveSpeaking) ?? null : null
  const currentTurn = speakingTurn ?? allTurns[0]
  const lastLive = liveActive ? liveMessages[liveMessages.length - 1] ?? null : null
  return (
    <main ref={experienceRef} tabIndex={-1} inert={appPhase !== 'world'} aria-hidden={appPhase !== 'world'} className={`valley-experience app-${appPhase} phase-${phase} ${joinOpen ? 'has-join-open' : ''} ${listening ? 'is-listening' : ''}`}>
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
        <p className="eyebrow">{table.worldId === 'valley' ? '瑞士山谷' : table.worldId} · {liveStatus === 'live' || liveStatus === 'mock' ? liveStatus === 'mock' ? '演示状态' : `${liveSeatCount} 人已入席` : `${table.seatedCount} 人已入席`}</p>
        <h1 id="valley-title">{table.hook}</h1>
        <p className="missing-line">{table.missingPerspective}</p>
        <button className="approach-button" type="button" onClick={approachTable}><span>靠近这桌</span><span aria-hidden="true">↗</span></button>
      </section>

      <button className="seat-hotspot" type="button" data-anchor="viewer" aria-label="靠近湖边的空席" onClick={approachTable} disabled={phase !== 'discovering'}>
        <span className="seat-pulse" /><span className="seat-label"><b>第五席</b>等一个真正停下来过的人</span>
      </button>

      <div className="approach-cue" role="status" aria-live="polite"><span />镜头正在穿过湖边的光</div>

      <section className="seated-hud" aria-hidden={!seated} inert={!seated}>
        <button className="back-to-discovery" type="button" onClick={resetDiscovery}>←&nbsp;&nbsp;退回远景</button>
        <button className="history-button" type="button" onClick={() => setHistoryOpen(true)}>对话历史 <span>↗</span></button>
        <div className="discussion-state"><i />{liveActive ? `${PHASE_LABELS[livePhase] ?? '讨论'}进行中${liveTableMode === 'sync' ? ' · 同步桌' : ''}` : '讨论正在发生'}</div>
        {liveStatus === 'connecting' && <div className="live-badge" role="status">正在连接这张桌…</div>}
        {liveStatus === 'error' && <div className="live-badge is-error" role="status">实时连接中断，显示最后状态</div>}
        {(safetyNotice || liveHost?.text || groundingCard || latestReflection) && <aside className="runtime-notice-stack" aria-live="polite">
          {safetyNotice && <p className="is-safety"><b>安全边界</b>{safetyNotice}</p>}
          {liveHost?.text && <p><b>{ACTION_LABELS[liveHost.action] ?? liveHost.action}</b>{liveHost.text}</p>}
          {groundingCard && <p><b>来源卡 · {groundingCard.title}</b>{groundingCard.excerpt}<small>{groundingCard.source_ref}</small></p>}
          {latestReflection && <p><b>主持回响</b>{latestReflection.text}</p>}
        </aside>}

        <div className="actor-hotspots" aria-label="桌上成员">
          {tableMembers.filter((member) => member.participant_id !== 'viewer').map((member) => {
            const actor = humanActors.find((item) => item.id === member.participant_id)
            return (
            <button
              key={member.participant_id}
              className={`actor-hotspot ${actor?.hotspotClass ?? ''}`}
              type="button"
              data-anchor={member.participant_id}
              data-active={currentTurn.id === member.participant_id}
              aria-label={`查看${member.display_name}，${member.role}`}
            >
              <i />
              <span className="actor-profile"><small>{member.role}</small><b>{member.display_name}</b><em>{actor?.whyHere ?? '这张桌的参与者'}</em><strong>参与者 · {member.participant_id}</strong></span>
            </button>
            )
          })}
          <button
            className="actor-hotspot actor-host"
            type="button"
            data-anchor="table-host"
            data-active={currentTurn.id === tableHost.id}
            aria-label="查看圆桌主持"
          >
            <i />
            <span className="actor-profile"><small>第六席 · Table Host</small><b>圆桌主持</b><em>认真听，把问题递给此刻最值得说话的人。</em><strong>状态 · {currentTurn.id === tableHost.id ? 'PASS 递话' : 'SILENCE 听'}</strong></span>
          </button>
        </div>
        <div className="question-card">
          <p>{liveActive && liveSubQuestion ? liveSubQuestion : <>我们需要的是休息，<br />还是允许自己停下？</>}</p>
        </div>
        <button className="seat-marker" type="button" data-anchor="viewer" disabled={hasJoined} onClick={(event) => openJoin(event.currentTarget)}><i /><span><small>{listening ? '旁听中' : '第五席'}</small>{hasJoined ? '你已在这一席' : listening ? '这是你的位置 · 随时可坐' : '这是你的位置'}</span></button>

        <div className="conversation-dock">
          {liveActive && lastLive ? (
            liveMessages.slice(-2).map((message, index, list) => (
              <p key={`${message.participantId}-${liveMessages.length - list.length + index}`} className={index === list.length - 1 ? 'is-latest' : 'is-previous'}>
                <b className={message.fromHost ? 'host-name' : ''}>
                  {speakerName(message.participantId, tableMembers)}{message.action && ACTION_LABELS[message.action] ? ` · ${ACTION_LABELS[message.action]}` : ''}
                </b>
                “{message.text}”
              </p>
            ))
          ) : (
            <p>桌面正在等下一句真实表达。</p>
          )}
          <div>
            <span><b>{lastLive ? speakerName(lastLive.participantId, tableMembers) : '等待发言'}</b>{lastLive ? ` · ${speakerRole(lastLive.participantId, tableMembers)}` : ''}</span>
            <i>{liveActive ? '·' : '—'}</i>
          </div>
          {hasJoined && liveActive && (
            <form className="viewer-input" onSubmit={submitMessage}>
              <input value={messageDraft} onChange={(event) => setMessageDraft(event.target.value)} placeholder="把你的真实经历说给这桌听…" aria-label="对这桌发言" maxLength={140} />
              <button type="submit" disabled={!messageDraft.trim()}>说</button>
            </form>
          )}
          {liveActive && <button className="nudge-button" type="button" onClick={() => requestNudge()}>请主持人递个话</button>}
        </div>
        {hasJoined && liveActive && closeState === 'idle' && <button className="close-table-button" type="button" onClick={() => requestClose()}>收这桌 <span>→</span></button>}
        {closeState === 'started' && <div className="closing-progress" role="status">正在收桌…</div>}
        {closeState === 'ready' && liveBaseline && <ClosingCard baseline={liveBaseline} personalCard={livePersonalCard} onReturn={onExit} />}
        <DiscussionPanel open={historyOpen} tableId={currentTableId()} participantId={hasJoined ? 'viewer' : undefined} members={tableMembers} onClose={() => setHistoryOpen(false)} />
        <button className="join-table-button" type="button" disabled={hasJoined} onClick={(event) => openJoin(event.currentTarget)}><i />{hasJoined ? '已坐到第五席' : '坐到空席'} <span>{hasJoined ? '✓' : '→'}</span></button>
        {hasJoined && <div ref={joinedStatusRef} className="join-success" role="status" tabIndex={-1} aria-live="polite" data-visible="true">
          <small>第五席 · 已入席</small><span>你的真实经历，已经来到桌边。</span>
        </div>}
      </section>

      <aside className="join-sheet" aria-hidden={!joinOpen} inert={!joinOpen}>
        <button className="panel-close" type="button" aria-label="关闭入席邀请" onClick={closeJoin}>×</button>
        <p className="panel-kicker">第五席 · 正在等你</p>
        <h2>你不需要带来答案。<br />只需要带来真实经历。</h2>
        <div className="seat-profile"><p>桌上已经有自由职业、职场压力和心理恢复的视角，但还没有一个真正尝试停下来的人。</p></div>
        <label className="voice-preview"><span>入席后，你想先说什么？</span><textarea ref={seatDraftRef} value={seatDraft} aria-invalid={joinError} aria-describedby={joinError ? 'seat-draft-error' : undefined} onChange={(event) => { setSeatDraft(event.target.value); if (joinError) setJoinError(false) }} placeholder="也许是最近一次，你明明在休息却仍然感到内疚……" /></label>
        <label className="consent-check"><input type="checkbox" checked={profileShared} onChange={(event) => setProfileShared(event.target.checked)} /><span>允许这张桌看见我的角色与这段经历</span></label>
        {joinError && <p id="seat-draft-error" className="join-error" role="alert">先留下一句真实经历，再坐到桌边。</p>}
        <button className="confirm-seat" type="button" onClick={confirmSeat}>以真实经历入席 <span>→</span></button>
      </aside>

      <nav className={`table-menu ${menuOpen ? 'is-open' : ''}`} aria-label="正在发生的桌" aria-hidden={!menuOpen} inert={!menuOpen}>
        <p>后端桌单 · {discovery.length ? `${discovery.length} 张正在发生` : '当前桌已恢复'}</p>
        {discovery.length ? discovery.map((item) => (
          <button key={item.table_id} type="button" className={item.table_id === table.id ? 'active' : ''} onClick={item.table_id === table.id ? closeMenu : onExit}>
            <span>{item.phase === 'close' ? '正在收束' : item.mode === 'sync' ? '同步桌' : '开放桌'}</span>{item.core_question}
            <small>{item.participant_count} 人 · {item.table_id === table.id ? '当前桌' : '回到桌单选择'}</small>
          </button>
        )) : (
          <button type="button" className="active" onClick={closeMenu}><span>当前桌</span>{table.hook}<small>桌单正在同步</small></button>
        )}
      </nav>

      <footer className="scene-footer"><span>瑞士山谷</span><span>01 <i /> 03</span></footer>
    </main>
  )
}

interface TransitionSnapshot { table: TableSummary; rect: GalleryMediaRect }

const ROOM_SESSION_KEY = 'zuoyizhuo.active-room'

function readActiveRoom(): { table: TableSummary; intent: 'listen' | 'join' } | null {
  try {
    const parsed = JSON.parse(sessionStorage.getItem(ROOM_SESSION_KEY) ?? 'null') as { table?: TableSummary; intent?: 'listen' | 'join' } | null
    if (!parsed?.table?.id || !parsed.table.hook || (parsed.intent !== 'listen' && parsed.intent !== 'join')) return null
    return { table: parsed.table, intent: parsed.intent }
  } catch {
    return null
  }
}

function TransitionCover({ snapshot }: { snapshot: TransitionSnapshot }) {
  const style = {
    '--portal-left': `${snapshot.rect.left}px`, '--portal-top': `${snapshot.rect.top}px`,
    '--portal-width': `${snapshot.rect.width}px`, '--portal-height': `${snapshot.rect.height}px`,
  } as CSSProperties
  // PRODUCT TRANSITION — the persistent Bruno canvas stays mounted. There is
  // no screenshot/image fallback between discovery and the room.
  return <div className="transition-cover" style={style} aria-hidden="true" />
}
export default function App() {
  const activeRoom = readActiveRoom()
  const [appPhase, setAppPhase] = useState<AppPhase>(() => activeRoom ? 'world' : 'gallery')
  const [transition, setTransition] = useState<TransitionSnapshot | null>(null)
  const [lobbyTable, setLobbyTable] = useState<TableSummary | null>(() => activeRoom?.table ?? null)
  const [lobbyData, setLobbyData] = useState<LobbyPreviewLike | null>(null)
  const [lobbyFit, setLobbyFit] = useState<LobbyFitPreviewLike | null>(null)
  const [lobbyLoading, setLobbyLoading] = useState(false)
  const [discovery, setDiscovery] = useState<LobbyPreviewLike[] | null>(null)
  const [discoveryUnavailable, setDiscoveryUnavailable] = useState(false)
  const [entryIntent, setEntryIntent] = useState<'listen' | 'join' | null>(() => activeRoom?.intent ?? null)
  const transitionTimer = useRef<number | null>(null)
  const pendingRectRef = useRef<GalleryMediaRect | null>(null)
  const reducedMotion = useReducedMotion()
  useEffect(() => {
    void fetchDiscovery().then((items) => {
      setDiscovery(items)
      setDiscoveryUnavailable(false)
    }).catch(() => {
      setDiscovery([])
      setDiscoveryUnavailable(true)
    })
    return () => {
      if (transitionTimer.current !== null) window.clearTimeout(transitionTimer.current)
      document.documentElement.classList.remove('js-has-global-canvas', 'js-global-canvas-error')
    }
  }, [])
  useEffect(() => {
    if (appPhase !== 'world' || !lobbyTable) return
    let active = true
    void loadLobby(lobbyTable.id).then((preview) => {
      if (active && preview) setLobbyData(preview)
    })
    return () => { active = false }
  }, [appPhase, lobbyTable])
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
    setLobbyData(null)
    setLobbyFit(null)
    setLobbyLoading(true)
    setAppPhase('lobby')
    void (async () => {
      const ready = await ensureTable(table.id, table.hook)
      if (!ready) {
        setLobbyLoading(false)
        return
      }
      void selectTable(ready, 'viewer').catch(() => undefined)
      const [preview, fit] = await Promise.all([
        loadLobby(ready),
        loadLobbyFit(ready, viewerSeed()),
      ])
      setLobbyData(preview)
      setLobbyFit(fit)
      setLobbyLoading(false)
    })()
  }
  const closeLobby = () => {
    if (appPhase !== 'lobby') return
    setLobbyTable(null)
    setLobbyData(null)
    setLobbyFit(null)
    setAppPhase('gallery')
  }
  const startWorld = (intent: 'listen' | 'join') => {
    if (appPhase !== 'lobby' || !lobbyTable) return
    setEntryIntent(intent)
    sessionStorage.setItem(ROOM_SESSION_KEY, JSON.stringify({ table: lobbyTable, intent }))
    const viewportRect: GalleryMediaRect = { left: 0, top: 0, width: window.innerWidth, height: window.innerHeight }
    setTransition({ table: lobbyTable, rect: pendingRectRef.current ?? viewportRect })
    setAppPhase('expanding')
    schedulePhase('world', reducedMotion ? 180 : 1100)
  }
  const exitTable = () => {
    if (appPhase !== 'world') return
    if (document.activeElement instanceof HTMLElement) document.activeElement.blur()
    setEntryIntent(null)
    sessionStorage.removeItem(ROOM_SESSION_KEY)
    setLobbyTable(null)
    setLobbyData(null)
    setLobbyFit(null)
    setAppPhase('collapsing')
    schedulePhase('gallery', reducedMotion ? 160 : 450)
  }
  const showGallery = appPhase === 'gallery' || appPhase === 'lobby' || appPhase === 'expanding' || appPhase === 'collapsing'
  const showWorld = appPhase === 'expanding' || appPhase === 'world' || appPhase === 'collapsing'
  return (
    <>
      <TableWorld active />
      {showGallery && <TableSea phase={appPhase} returnFocusId={transition?.table.id ?? null} onEnter={openLobby} discovery={discovery} backendUnavailable={discoveryUnavailable} />}
      {showWorld && lobbyTable && <ValleyExperience table={lobbyTable} lobby={lobbyData} discovery={discovery ?? []} appPhase={appPhase} entryIntent={entryIntent} onExit={exitTable} />}
      {appPhase === 'lobby' && lobbyTable && <Lobby table={lobbyTable} lobby={lobbyData} fit={lobbyFit} loading={lobbyLoading} onClose={closeLobby} onListen={() => startWorld('listen')} onJoin={() => startWorld('join')} />}
      {appPhase === 'expanding' && transition && <><div className="transition-backdrop" aria-hidden="true" /><TransitionCover snapshot={transition} /></>}
    </>
  )
}
