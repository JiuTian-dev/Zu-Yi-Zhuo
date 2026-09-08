import { useEffect, useRef, useState, type CSSProperties } from 'react'
import { tableHost } from './actors'
import TableSea, { type GalleryMediaRect } from './TableSea'
import Lobby from './Lobby'
import type { AppPhase, TableSummary } from './domain'
import { useLive } from './live/store'
import { joinViewer, requestClose, requestNudge, requestStageSummary, retryViewerMessage, sendViewerMessage, startLive, stopLive, submitStageSummaryFeedbackFromViewer, viewerSeed } from './live/backend'
import { VIEWER_ID } from './live/identity'
import ClosingCard from './live/ClosingCard'
import DiscussionPanel from './live/DiscussionPanel'
import StageSummaryPanel from './live/StageSummaryPanel'
import IntentPanel from './live/IntentPanel'
import type { HomeToMatchContextLike, LobbyFitPreviewLike, LobbyPreviewLike, MatchToHomeDraftLike, OpenTableContextLike, StageSummaryFeedbackKindLike } from './live/contract'
import { loadLobby, loadLobbyFit, ensureTable } from './live/backend'
import { fetchDiscovery, fetchLobby, leaveTable, selectTable } from './live/api'
import { clearHomeContext, clearOpenTableContext, handoffMatchDraft, HOME_TO_MATCH_CONTEXT_EVENT, normalizeHomeToMatchContext, normalizeOpenTableContext, OPEN_TABLE_CONTEXT_EVENT, readHomeContext, readOpenTableContext } from './live/handoff'
import { setAmbient, stopAmbient } from './audio/ambient'
import TableWorld from './TableWorld'
import { projectTableAnchor, setDayCycleMode, setRuntimeInteraction, transitionTableCamera, type DayCycleMode } from './bruno-runtime/runtimeController'
import DrawerToggle from './DrawerToggle'

const ACTION_LABELS: Record<string, string> = {
  SILENCE: '安静听', PASS: '递话', PROBE: '追问', REFRAME: '换个角度', GROUND: '落在桌面', CLOSE: '收束',
}

const PHASE_LABELS: Record<string, string> = {
  opening: '开场', explore: '探索', tension: '张力', deepen: '深入', close: '收束',
}

type ExperiencePhase = 'discovering' | 'approaching' | 'seated'

const DAY_CYCLE_MODE_KEY = 'zuoyizhuo.scene-time-mode'

function readDayCycleMode(): DayCycleMode {
  try {
    const value = localStorage.getItem(DAY_CYCLE_MODE_KEY)
    return value === 'day' || value === 'night' ? value : 'auto'
  } catch {
    return 'auto'
  }
}

function tableSummaryFromLobby(lobby: LobbyPreviewLike): TableSummary {
  return {
    id: lobby.table_id,
    worldId: 'valley',
    hook: lobby.core_question,
    seatedCount: lobby.participant_count,
    missingPerspective: lobby.missing_perspective,
    recommendedBecause: lobby.role_gaps.length ? `这桌正在寻找：${lobby.role_gaps.join('、')}` : undefined,
    previewLines: lobby.members.slice(0, 3).map((member) => `${member.display_name} · ${member.role}`),
    status: lobby.status === 'open' ? 'live' : 'forming',
    entryMode: lobby.status === 'open' ? 'immersive' : 'preview',
    transitionPreset: lobby.status === 'open' ? 'valley' : 'cover-only',
  }
}
function speakerName(participantId: string, members: Array<{ participant_id: string; display_name: string }>, viewerParticipantId?: string): string {
  if (participantId === 'table-host') return '圆桌主持'
  if (participantId === viewerParticipantId) return '你'
  const member = members.find((item) => item.participant_id === participantId)
  if (!viewerParticipantId && member?.display_name === '你') return '第五席'
  return member?.display_name ?? participantId
}

function speakerRole(participantId: string, members: Array<{ participant_id: string; role: string }>, viewerParticipantId?: string): string {
  if (participantId === 'table-host') return 'Table Host'
  if (participantId === viewerParticipantId) return '第五席'
  return members.find((member) => member.participant_id === participantId)?.role ?? '嘉宾'
}

function sentence(text: string) {
  return text.replace(/[。.!！?？\s]+$/u, '')
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

function SettingsIcon() {
  return <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 8.2a3.8 3.8 0 1 0 0 7.6 3.8 3.8 0 0 0 0-7.6Zm8 3.8-2-.7a6.2 6.2 0 0 0-.6-1.5l.9-1.9-1.8-1.8-1.9.9a6.2 6.2 0 0 0-1.5-.6l-.7-2h-2.6l-.7 2a6.2 6.2 0 0 0-1.5.6l-1.9-.9L4.9 7.9l.9 1.9a6.2 6.2 0 0 0-.6 1.5l-2 .7v2.6l2 .7c.1.5.3 1 .6 1.5l-.9 1.9 1.8 1.8 1.9-.9c.5.3 1 .5 1.5.6l.7 2h2.6l.7-2c.5-.1 1-.3 1.5-.6l1.9.9 1.8-1.8-.9-1.9c.3-.5.5-1 .6-1.5l2-.7v-2.6Z" /></svg>
}

function ValleyExperience({ onExit, appPhase, entryIntent, table, lobby, discovery, initialJoined = false }: { onExit(): void; appPhase: AppPhase; entryIntent: 'listen' | 'join' | null; table: TableSummary; lobby: LobbyPreviewLike | null; discovery: LobbyPreviewLike[]; initialJoined?: boolean }) {
  const reducedMotion = useReducedMotion()
  const [phase, setPhase] = useState<ExperiencePhase>('discovering')
  const [joinOpen, setJoinOpen] = useState(false)
  const [seatDraft, setSeatDraft] = useState('')
  const [joinError, setJoinError] = useState<string | null>(null)
  const [joinDismissed, setJoinDismissed] = useState(false)
  const [profileShared, setProfileShared] = useState(false)
  const [menuOpen, setMenuOpen] = useState(false)
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [dayCycleMode, setDayCycleModeState] = useState<DayCycleMode>(readDayCycleMode)
  const [soundOn, setSoundOn] = useState(false)
  const [historyOpen, setHistoryOpen] = useState(false)
  const experienceRef = useRef<HTMLElement>(null!)
  const menuButtonRef = useRef<HTMLButtonElement>(null)
  const joinOpenerRef = useRef<HTMLButtonElement | null>(null)
  const joinPanelRef = useRef<HTMLElement>(null)
  const seatDraftRef = useRef<HTMLTextAreaElement>(null)
  const joinedStatusRef = useRef<HTMLDivElement>(null)
  const nudgeTimerRef = useRef<number | null>(null)
  const closeTimerRef = useRef<number | null>(null)
  const retryTimerRef = useRef<number | null>(null)
  const reopenClosingCardRef = useRef<HTMLButtonElement>(null)
  const [messageDraft, setMessageDraft] = useState('')
  const [joinPending, setJoinPending] = useState(false)
  const [nudgePending, setNudgePending] = useState(false)
  const [closePending, setClosePending] = useState(false)
  const [actionNotice, setActionNotice] = useState<string | null>(null)
  const [retryingMessageId, setRetryingMessageId] = useState<string | null>(null)
  const [selectedActorId, setSelectedActorId] = useState<string | null>(null)
  const [closingCardOpen, setClosingCardOpen] = useState(false)
  const [heroCollapsed, setHeroCollapsed] = useState(false)
  const [questionCollapsed, setQuestionCollapsed] = useState(false)
  const [conversationCollapsed, setConversationCollapsed] = useState(false)
  const [noticeCollapsed, setNoticeCollapsed] = useState(false)
  const [joinSuccessCollapsed, setJoinSuccessCollapsed] = useState(false)

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
  const liveError = useLive((state) => state.lastError)
  const latestReflection = useLive((state) => state.latestReflection)
  const latestSummary = useLive((state) => state.latestSummary)
  const summaryHistory = useLive((state) => state.summaryHistory)
  const summaryStatus = useLive((state) => state.summaryStatus)
  const tableMembers = liveTableState
    ? Object.values(liveTableState.participants).map((participant) => ({
      participant_id: participant.participant_id,
      display_name: participant.display_name,
      role: participant.role,
    }))
    : lobby?.members ?? []
  const roomTurns = tableMembers.map((member) => ({ ...member, id: member.participant_id, displayName: member.display_name, whyHere: '', quote: '', role: member.role }))
  const allTurns = [...roomTurns, { ...tableHost, participant_id: tableHost.id, display_name: tableHost.displayName }]
  const selectedActor = selectedActorId === tableHost.id
    ? { participant_id: tableHost.id, display_name: tableHost.displayName, role: tableHost.role, detail: tableHost.whyHere }
    : tableMembers.find((member) => member.participant_id === selectedActorId)
      ? { ...tableMembers.find((member) => member.participant_id === selectedActorId)!, detail: '这张桌的参与者' }
      : null

  useEffect(() => {
    void startLive(table.id, table.hook, initialJoined ? 'participant' : 'observer')
    return () => stopLive()
  }, [initialJoined, table.id, table.hook])

  useEffect(() => {
    let raf = 0
    const apply = () => {
      raf = requestAnimationFrame(apply)
      const root = experienceRef.current
      if (!root) return
      root.querySelectorAll<HTMLElement>('[data-anchor]').forEach((el) => {
        const anchor = projectTableAnchor(el.dataset.anchor || '')
        if (!anchor) {
          el.style.visibility = 'hidden'
          return
        }
        el.style.visibility = anchor.visible ? 'visible' : 'hidden'
        el.style.left = `${anchor.x}px`
        el.style.top = `${anchor.y}px`
        el.style.transform = 'translate(-50%, -50%)'
      })
    }
    raf = requestAnimationFrame(apply)
    return () => cancelAnimationFrame(raf)
  }, [])

  useEffect(() => {
    setRuntimeInteraction(!historyOpen && !joinOpen && !menuOpen && !settingsOpen && !closingCardOpen)
    return () => setRuntimeInteraction(true)
  }, [historyOpen, joinOpen, menuOpen, settingsOpen, closingCardOpen])

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
  const closeSettings = () => setSettingsOpen(false)
  const openJoin = (opener: HTMLButtonElement) => {
    if (liveViewerJoined || closeState !== 'idle') return
    joinOpenerRef.current = opener
    setJoinError(null)
    setJoinDismissed(false)
    setActionNotice(null)
    setJoinOpen(true)
  }

  const confirmSeat = async () => {
    if (joinPending) return
    if (!seatDraft.trim()) {
      setJoinError('先留下一句真实经历，再坐到桌边。')
      seatDraftRef.current?.focus({ preventScroll: true })
      return
    }
    setJoinPending(true)
    setJoinError(null)
    try {
      const result = await joinViewer(seatDraft, profileShared)
      if (!result.ok) {
        setJoinError(result.error)
        return
      }
      experienceRef.current?.focus({ preventScroll: true })
      // Keep the auto-open effect from racing the live store update. The
      // backend has already confirmed membership; this flag only closes the
      // current invitation surface and is reset when returning to discovery.
      setJoinDismissed(true)
      setJoinError(null)
      setJoinOpen(false)
      setActionNotice('你已入席，接下来可以把这段经历说给桌面听。')
      const stored = JSON.parse(sessionStorage.getItem(ROOM_SESSION_KEY) ?? '{}') as Record<string, unknown>
      sessionStorage.setItem(ROOM_SESSION_KEY, JSON.stringify({ ...stored, joined: true }))
    } finally {
      setJoinPending(false)
    }
  }

  const submitMessage = (event: { preventDefault(): void }) => {
    event.preventDefault()
    if (!hasJoined || !liveActive || closeState !== 'idle') return
    if (!sendViewerMessage(messageDraft)) return
    setMessageDraft('')
    setActionNotice('这句话已经递到桌面上。')
  }

  const retryMessage = (messageId: string) => {
    if (retryingMessageId) return
    const sent = retryViewerMessage(messageId)
    if (!sent) {
      setActionNotice('这句话还没有重新送达，请确认实时连接后再试。')
      return
    }
    setRetryingMessageId(messageId)
    setActionNotice('正在重新送达这句话…')
    if (retryTimerRef.current !== null) window.clearTimeout(retryTimerRef.current)
    retryTimerRef.current = window.setTimeout(() => {
      setRetryingMessageId((current) => current === messageId ? null : current)
      retryTimerRef.current = null
      setActionNotice('这句话暂时没有收到确认，可以稍后重试。')
    }, 6000)
  }

  const requestNudgeFromUi = () => {
    if (nudgePending || !hasJoined || !liveActive || closeState !== 'idle') return
    const sent = requestNudge()
    if (!sent) {
      setActionNotice('没有连上主持席，这次请求没有送达。')
      return
    }
    setNudgePending(true)
    setActionNotice('已把你的请求递给主持人。')
    if (nudgeTimerRef.current !== null) window.clearTimeout(nudgeTimerRef.current)
    nudgeTimerRef.current = window.setTimeout(() => {
      setNudgePending(false)
      nudgeTimerRef.current = null
    }, 2400)
  }

  const requestStageSummaryFromUi = () => {
    if (!hasJoined || !liveActive || closeState !== 'idle') return
    if (!requestStageSummary()) setActionNotice('总结请求暂时没有送达，请确认实时连接后再试。')
    else setActionNotice('已请主持 Agent 整理当前讨论。')
  }

  const sendSummaryFeedback = async (kind: StageSummaryFeedbackKindLike, summary: NonNullable<typeof latestSummary>) => {
    try {
      await submitStageSummaryFeedbackFromViewer(summary, kind)
      setActionNotice('已把你的校正反馈递给主持 Agent。')
    } catch (error) {
      setActionNotice(error instanceof Error ? error.message : '反馈暂时没有送达。')
    }
  }

  const focusSummaryEvidence = (turnId: number) => {
    const target = Array.from(document.querySelectorAll<HTMLElement>('[data-turn-id]')).find((item) => item.dataset.turnId === String(turnId))
    if (target) {
      target.scrollIntoView({ behavior: reducedMotion ? 'auto' : 'smooth', block: 'center' })
      target.focus({ preventScroll: true })
      return
    }
    setHistoryOpen(true)
    setActionNotice(`已打开对话历史，请查看第 ${turnId} 句。`)
  }

  const requestCloseFromUi = () => {
    if (closePending || !hasJoined || !liveActive || closeState !== 'idle') return
    const sent = requestClose()
    if (!sent) {
      setActionNotice('没有连上桌面，这次收桌请求没有送达。')
      return
    }
    setClosePending(true)
    setActionNotice('已请主持人整理这张桌的收桌卡。')
    if (closeTimerRef.current !== null) window.clearTimeout(closeTimerRef.current)
    closeTimerRef.current = window.setTimeout(() => {
      setClosePending(false)
      setActionNotice('暂时没有收到收桌确认，可以稍后重试。')
      closeTimerRef.current = null
    }, 5000)
  }

  const dismissClosingCard = () => {
    setClosingCardOpen(false)
    window.requestAnimationFrame(() => reopenClosingCardRef.current?.focus({ preventScroll: true }))
  }

  const resetDiscovery = () => {
    void transitionTableCamera({ mode: 'overview', reducedMotion })
    const active = document.activeElement
    if (active instanceof HTMLElement && active.closest('.join-sheet,.table-menu')) experienceRef.current?.focus({ preventScroll: true })
    setJoinOpen(false)
    setHistoryOpen(false)
    setMenuOpen(false)
    setSettingsOpen(false)
    setJoinDismissed(false)
    setHeroCollapsed(false)
    setQuestionCollapsed(false)
    setConversationCollapsed(false)
    setNoticeCollapsed(false)
    setJoinSuccessCollapsed(false)
    setPhase('discovering')
  }

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return
      if (historyOpen) setHistoryOpen(false)
      else if (joinOpen) closeJoin()
      else if (menuOpen) closeMenu()
      else if (settingsOpen) closeSettings()
      else resetDiscovery()
    }
    window.addEventListener('keydown', onKeyDown)
    return () => {
      window.removeEventListener('keydown', onKeyDown)
    }
  }, [historyOpen, joinOpen, menuOpen, settingsOpen])

  useEffect(() => {
    setDayCycleMode(dayCycleMode)
    try {
      localStorage.setItem(DAY_CYCLE_MODE_KEY, dayCycleMode)
    } catch {
      // The control remains usable when browser storage is unavailable.
    }
  }, [dayCycleMode])

  useEffect(() => () => {
    stopAmbient()
    if (nudgeTimerRef.current !== null) window.clearTimeout(nudgeTimerRef.current)
    if (closeTimerRef.current !== null) window.clearTimeout(closeTimerRef.current)
    if (retryTimerRef.current !== null) window.clearTimeout(retryTimerRef.current)
  }, [])

  useEffect(() => {
    if (!retryingMessageId) return
    const message = liveMessages.find((item) => item.messageId === retryingMessageId)
    if (message?.delivery === 'pending') return
    if (message?.delivery === 'failed') setActionNotice('这句话没有送达，可以再次重试。')
    setRetryingMessageId(null)
    if (retryTimerRef.current !== null) {
      window.clearTimeout(retryTimerRef.current)
      retryTimerRef.current = null
    }
  }, [liveMessages, retryingMessageId])

  useEffect(() => {
    if (closeState === 'ready') setClosingCardOpen(true)
    if (closeState === 'idle') setClosingCardOpen(false)
    if (closeState !== 'idle') {
      setClosePending(false)
      if (closeTimerRef.current !== null) {
        window.clearTimeout(closeTimerRef.current)
        closeTimerRef.current = null
      }
    }
  }, [closeState])

  useEffect(() => {
    if (!liveError) return
    setActionNotice(liveError)
    setNudgePending(false)
    if (nudgeTimerRef.current !== null) {
      window.clearTimeout(nudgeTimerRef.current)
      nudgeTimerRef.current = null
    }
  }, [liveError])

  useEffect(() => {
    if (!joinOpen) return
    const frame = window.requestAnimationFrame(() => seatDraftRef.current?.focus({ preventScroll: true }))
    return () => window.cancelAnimationFrame(frame)
  }, [joinOpen])

  useEffect(() => {
    if (!joinOpen) return
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== 'Tab' || !joinPanelRef.current) return
      const focusable = Array.from(joinPanelRef.current.querySelectorAll<HTMLElement>(
        'button:not([disabled]), input:not([disabled]), textarea:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])',
      ))
      if (focusable.length === 0) return
      const first = focusable[0]
      const last = focusable[focusable.length - 1]
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault()
        last.focus()
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault()
        first.focus()
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [joinOpen])

  useEffect(() => {
    if (liveViewerJoined) joinedStatusRef.current?.focus({ preventScroll: true })
  }, [liveViewerJoined])

  useEffect(() => {
    if (appPhase === 'world') experienceRef.current.focus({ preventScroll: true })
  }, [appPhase])

  const beginApproach = () => {
    if (phase !== 'discovering') return
    setMenuOpen(false)
    setPhase('approaching')
    void transitionTableCamera({ mode: 'approach', reducedMotion }).then(() => setPhase('seated'))
  }

  useEffect(() => {
    if (appPhase !== 'world' || entryIntent !== 'join') return
    if (phase === 'discovering') {
      beginApproach()
      return
    }
    if (phase !== 'seated') return
    // Wait for the requested participant/observer hydration to settle. If a
    // stale room session says "joined", opening the sheet before the backend
    // answers can race the real membership state and leave a false prompt.
    if (liveStatus !== 'live' && liveStatus !== 'mock') return
    if (liveViewerJoined || joinOpen || joinDismissed) return
    setJoinError(null)
    setJoinOpen(true)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [appPhase, entryIntent, phase, reducedMotion, liveStatus, liveViewerJoined, joinOpen, joinDismissed])

  const approachTable = () => {
    beginApproach()
  }

  const seated = phase === 'seated'
  // PRODUCT DATA BOUNDARY — cached room intent may request participant
  // hydration, but only the backend-confirmed live flag grants participant
  // controls. A stale session value must never reveal input or close actions.
  const hasJoined = liveViewerJoined
  const listening = entryIntent === 'listen' && !hasJoined
  const liveActive = liveStatus === 'live' || liveStatus === 'mock'
  const tableInteractive = hasJoined && liveActive && closeState === 'idle'
  const speakingTurn = liveActive && liveSpeaking ? allTurns.find((turn) => turn.id === liveSpeaking) ?? null : null
  const currentTurn = speakingTurn ?? allTurns[0]
  const lastLive = liveActive ? liveMessages[liveMessages.length - 1] ?? null : null
  return (
    <main ref={experienceRef} tabIndex={-1} inert={appPhase !== 'world' || historyOpen || closingCardOpen} aria-hidden={appPhase !== 'world' || historyOpen || closingCardOpen} className={`valley-experience app-${appPhase} phase-${phase} ${joinOpen ? 'has-join-open' : ''} ${listening ? 'is-listening' : ''}`}>
      <div className="world-grade" aria-hidden="true" />

      <header className="site-header">
        <button className="brand" type="button" onClick={phase === 'discovering' ? onExit : resetDiscovery} aria-label={phase === 'discovering' ? '回到桌单' : '回到这张桌的远景'}>
          <span>组一桌</span><i /> <small>湖边这桌</small>
        </button>
        <div className="header-actions">
          <button className={`icon-button ${soundOn ? '' : 'sound-unavailable'}`} type="button" aria-pressed={soundOn} aria-label={soundOn ? '关闭环境音' : '开启环境音'} title={soundOn ? '关闭环境音' : '开启环境音'} onClick={() => { const next = !soundOn; setSoundOn(next); setAmbient(next, 'valley') }}>
            <SoundIcon muted={!soundOn} />
          </button>
          <button className="icon-button settings-button" type="button" aria-label={settingsOpen ? '关闭场景设置' : '打开场景设置'} aria-expanded={settingsOpen} title="场景设置" onClick={() => { setSettingsOpen((current) => !current); setMenuOpen(false) }}>
            <SettingsIcon />
          </button>
          <button ref={menuButtonRef} className="icon-button menu-button" type="button" aria-label={menuOpen ? '关闭桌单' : '打开桌单'} aria-expanded={menuOpen} onClick={() => menuOpen ? closeMenu() : setMenuOpen(true)}><span /><span /></button>
        </div>
      </header>

      <aside className={`scene-settings ${settingsOpen ? 'is-open' : ''}`} aria-hidden={!settingsOpen} inert={!settingsOpen} role="dialog" aria-label="场景设置">
        <button className="scene-settings-close" type="button" aria-label="关闭场景设置" onClick={closeSettings}>×</button>
        <p className="scene-settings-kicker">SCENE SETTINGS</p>
        <h2>时间氛围</h2>
        <p className="scene-settings-intro">选择这一桌的光线。自动变化会在约 8 分钟内完成一轮昼夜。</p>
        <div className="scene-time-options" role="radiogroup" aria-label="昼夜模式">
          {([
            ['auto', '自动变化', '保留昼夜流动'],
            ['day', '一直白天', '清晰、温暖的山谷光'],
            ['night', '一直黑夜', '蓝紫色的夜间光'],
          ] as Array<[DayCycleMode, string, string]>).map(([value, label, detail]) => (
            <button key={value} type="button" role="radio" aria-checked={dayCycleMode === value} className={dayCycleMode === value ? 'is-selected' : ''} onClick={() => setDayCycleModeState(value)}>
              <span><b>{label}</b><small>{detail}</small></span><i aria-hidden="true" />
            </button>
          ))}
        </div>
      </aside>

      <section className={`hero-copy ${heroCollapsed ? 'is-collapsed' : ''}`} aria-labelledby="valley-title" inert={seated || phase === 'approaching'}>
        <DrawerToggle collapsed={heroCollapsed} label="主题卡" controlsId="valley-hero-content" onToggle={() => setHeroCollapsed((current) => !current)} />
        <div id="valley-hero-content" className="drawer-card-content" aria-hidden={heroCollapsed} inert={heroCollapsed}>
          <p className="eyebrow">{table.worldId === 'valley' ? '瑞士山谷' : table.worldId} · {liveStatus === 'live' || liveStatus === 'mock' ? liveStatus === 'mock' ? '演示状态' : `${liveSeatCount} 人已入席` : `${table.seatedCount} 人已入席`}</p>
          <h1 id="valley-title">{table.hook}</h1>
          <p className="missing-line">{table.missingPerspective}</p>
          <button className="approach-button" type="button" onClick={approachTable}><span>靠近这桌</span><span aria-hidden="true">↗</span></button>
        </div>
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
        {(safetyNotice || liveHost?.text || groundingCard || latestReflection || liveError || actionNotice) && <aside className={`runtime-notice-stack ${noticeCollapsed ? 'is-collapsed' : ''}`} aria-live="polite">
          <DrawerToggle collapsed={noticeCollapsed} label="桌边提示" controlsId="runtime-notice-content" onToggle={() => setNoticeCollapsed((current) => !current)} />
          <div id="runtime-notice-content" className="drawer-card-content" aria-hidden={noticeCollapsed} inert={noticeCollapsed}>
            {actionNotice && <p><b>桌边反馈</b>{actionNotice}</p>}
            {liveError && <p className="is-error"><b>桌面状态</b>{liveError}</p>}
            {safetyNotice && <p className="is-safety"><b>安全边界</b>{safetyNotice}</p>}
            {liveHost?.text && <p><b>{ACTION_LABELS[liveHost.action] ?? liveHost.action}</b>{liveHost.text}</p>}
            {groundingCard && <p><b>来源卡 · {groundingCard.title}</b>{groundingCard.excerpt}<small>{groundingCard.source_ref}</small></p>}
            {latestReflection && <p><b>主持回响</b>{latestReflection.text}</p>}
          </div>
        </aside>}

        <div className="actor-hotspots" aria-label="桌上成员">
          {tableMembers.filter((member) => member.participant_id !== VIEWER_ID).map((member) => {
            return (
            <button
              key={member.participant_id}
              className="actor-hotspot"
              type="button"
              data-anchor={member.participant_id}
              data-active={currentTurn.id === member.participant_id}
              data-selected={selectedActorId === member.participant_id}
              aria-pressed={selectedActorId === member.participant_id}
              aria-label={`查看${member.display_name}，${member.role}`}
              onClick={() => setSelectedActorId((current) => current === member.participant_id ? null : member.participant_id)}
            >
              <i />
              <span className="actor-profile"><small>{member.role}</small><b>{member.display_name}</b><em>这张桌的参与者</em><strong>参与者 · {member.participant_id}</strong></span>
            </button>
            )
          })}
          <button
            className="actor-hotspot actor-host"
            type="button"
            data-anchor="table-host"
            data-active={currentTurn.id === tableHost.id}
            data-selected={selectedActorId === tableHost.id}
            aria-pressed={selectedActorId === tableHost.id}
            aria-label="查看圆桌主持"
            onClick={() => setSelectedActorId((current) => current === tableHost.id ? null : tableHost.id)}
          >
            <i />
            <span className="actor-profile"><small>第六席 · Table Host</small><b>圆桌主持</b><em>认真听，把问题递给此刻最值得说话的人。</em><strong>状态 · {currentTurn.id === tableHost.id ? 'PASS 递话' : 'SILENCE 听'}</strong></span>
          </button>
        </div>
        {selectedActor && <aside className="actor-selection" role="status" aria-live="polite">
          <b>{selectedActor.display_name}</b><span>{selectedActor.role} · {selectedActor.detail}</span>
          <button type="button" onClick={() => setSelectedActorId(null)}>收起</button>
        </aside>}
        <div className={`question-card ${questionCollapsed ? 'is-collapsed' : ''}`}>
          <DrawerToggle collapsed={questionCollapsed} label="当前问题" controlsId="question-card-content" onToggle={() => setQuestionCollapsed((current) => !current)} />
          <div id="question-card-content" className="drawer-card-content" aria-hidden={questionCollapsed} inert={questionCollapsed}>
            <p>{liveActive && liveSubQuestion ? liveSubQuestion : lobby?.current_subquestion ?? table.hook}</p>
          </div>
        </div>
        <button className="seat-marker" type="button" data-anchor="viewer" disabled={hasJoined} onClick={(event) => openJoin(event.currentTarget)}><i /><span><small>{listening ? '旁听中' : '第五席'}</small>{hasJoined ? '你已在这一席' : listening ? '这是你的位置 · 随时可坐' : '这是你的位置'}</span></button>

        <div className={`conversation-dock ${conversationCollapsed ? 'is-collapsed' : ''}`}>
          <DrawerToggle collapsed={conversationCollapsed} label="对话" controlsId="conversation-dock-content" onToggle={() => setConversationCollapsed((current) => !current)} />
          <section id="conversation-dock-content" className="drawer-card-content" aria-hidden={conversationCollapsed} inert={conversationCollapsed}>
            {liveActive && lastLive ? (
              liveMessages.slice(-2).map((message, index, list) => (
                <p key={`${message.participantId}-${liveMessages.length - list.length + index}`} data-turn-id={message.turnId} className={index === list.length - 1 ? 'is-latest' : 'is-previous'}>
                  <b className={message.fromHost ? 'host-name' : ''}>
                    {speakerName(message.participantId, tableMembers, hasJoined ? VIEWER_ID : undefined)}{message.action && ACTION_LABELS[message.action] ? ` · ${ACTION_LABELS[message.action]}` : ''}
                  </b>
                  “{message.text}”
                  {message.delivery === 'pending' && <small className="message-delivery">正在送达</small>}
                  {message.delivery === 'failed' && message.messageId && <button className="message-retry" type="button" disabled={retryingMessageId === message.messageId} onClick={() => retryMessage(message.messageId!)}>{retryingMessageId === message.messageId ? '发送中' : '重试'}</button>}
                </p>
              ))
            ) : (
              <p>桌面正在等下一句真实表达。</p>
            )}
            <div>
              <span><b>{lastLive ? speakerName(lastLive.participantId, tableMembers, hasJoined ? VIEWER_ID : undefined) : '等待发言'}</b>{lastLive ? ` · ${speakerRole(lastLive.participantId, tableMembers, hasJoined ? VIEWER_ID : undefined)}` : ''}</span>
              <i>{liveActive ? '·' : '—'}</i>
            </div>
            {tableInteractive && (
              <form className="viewer-input" onSubmit={submitMessage}>
                <input value={messageDraft} onChange={(event) => setMessageDraft(event.target.value)} placeholder="把你的真实经历说给这桌听…" aria-label="对这桌发言" maxLength={140} />
                <button type="submit" disabled={!messageDraft.trim()}>说</button>
              </form>
            )}
            {tableInteractive && <button className="nudge-button" type="button" disabled={nudgePending} aria-busy={nudgePending} onClick={requestNudgeFromUi}>{nudgePending ? '请求已递达，等主持人回应…' : '请主持人递个话'}</button>}
          </section>
        </div>
        {tableInteractive && <button className="close-table-button" type="button" disabled={closePending} aria-busy={closePending} onClick={requestCloseFromUi}>{closePending ? '正在请主持人收桌…' : '收这桌'} <span>→</span></button>}
        {seated && <StageSummaryPanel summary={latestSummary} history={summaryHistory} pending={summaryStatus} participantId={hasJoined ? VIEWER_ID : undefined} onRequest={requestStageSummaryFromUi} onFeedback={sendSummaryFeedback} onEvidence={focusSummaryEvidence} />}
        {closeState === 'started' && <div className="closing-progress" role="status">正在收桌…</div>}
        {closeState === 'ready' && liveBaseline && closingCardOpen && <ClosingCard tableId={table.id} participantId={VIEWER_ID} baseline={liveBaseline} personalCard={livePersonalCard} onDismiss={dismissClosingCard} onReturn={onExit} />}
        {closeState === 'ready' && liveBaseline && !closingCardOpen && <button ref={reopenClosingCardRef} className="reopen-closing-card" type="button" onClick={() => setClosingCardOpen(true)}>打开收桌卡 <span>↗</span></button>}
        <DiscussionPanel open={historyOpen} tableId={table.id} participantId={hasJoined ? VIEWER_ID : undefined} members={tableMembers} onClose={() => setHistoryOpen(false)} closeState={closeState} baseline={liveBaseline} personalCard={livePersonalCard} />
        <button className="join-table-button" type="button" disabled={hasJoined || closeState !== 'idle'} onClick={(event) => openJoin(event.currentTarget)}><i />{hasJoined ? '已坐到第五席' : closeState !== 'idle' ? '这桌已收束' : '坐到空席'} <span>{hasJoined ? '✓' : '→'}</span></button>
        {hasJoined && <div ref={joinedStatusRef} className={`join-success ${joinSuccessCollapsed ? 'is-collapsed' : ''}`} role="status" tabIndex={-1} aria-live="polite" data-visible="true">
          <DrawerToggle collapsed={joinSuccessCollapsed} label="入席提示" controlsId="join-success-content" onToggle={() => setJoinSuccessCollapsed((current) => !current)} />
          <div id="join-success-content" className="drawer-card-content" aria-hidden={joinSuccessCollapsed} inert={joinSuccessCollapsed}>
            <small>第五席 · 已入席</small><span>你的真实经历，已经来到桌边。</span>
          </div>
        </div>}
      </section>

      <aside ref={joinPanelRef} className="join-sheet" aria-hidden={!joinOpen} inert={!joinOpen} role="dialog" aria-modal="true" aria-labelledby="join-sheet-title">
        <button className="panel-close" type="button" aria-label="关闭入席邀请" onClick={closeJoin} disabled={joinPending}>×</button>
        <p className="panel-kicker">第五席 · 正在等你</p>
        <h2 id="join-sheet-title">你不需要带来答案。<br />只需要带来真实经历。</h2>
        <div className="seat-profile"><p>{sentence(lobby?.missing_perspective ?? table.missingPerspective)}。这张桌现在需要你的真实经历，才能把问题继续往前推。</p></div>
        <label className="voice-preview"><span>入席后，你想先说什么？</span><textarea ref={seatDraftRef} value={seatDraft} aria-invalid={Boolean(joinError)} aria-describedby={joinError ? 'seat-draft-error' : undefined} onChange={(event) => { setSeatDraft(event.target.value); if (joinError) setJoinError(null) }} placeholder="说说你和这道问题的真实关系……" /></label>
        <label className="consent-check"><input type="checkbox" checked={profileShared} onChange={(event) => setProfileShared(event.target.checked)} /><span>允许这张桌看见我的角色与这段经历</span></label>
        {joinError && <p id="seat-draft-error" className="join-error" role="alert">{joinError}</p>}
        <button className="confirm-seat" type="button" disabled={joinPending} aria-busy={joinPending} onClick={confirmSeat}>{joinPending ? '正在确认这一席…' : '以真实经历入席'} <span>→</span></button>
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

    </main>
  )
}

interface TransitionSnapshot { table: TableSummary; rect: GalleryMediaRect }

const ROOM_SESSION_KEY = 'zuoyizhuo.active-room'

function readActiveRoom(): { table: TableSummary; intent: 'listen' | 'join'; joined: boolean } | null {
  try {
    const parsed = JSON.parse(sessionStorage.getItem(ROOM_SESSION_KEY) ?? 'null') as { table?: TableSummary; intent?: 'listen' | 'join'; joined?: boolean } | null
    if (!parsed?.table?.id || !parsed.table.hook || (parsed.intent !== 'listen' && parsed.intent !== 'join')) return null
    return { table: parsed.table, intent: parsed.intent, joined: parsed.joined === true }
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
  const [lobbyError, setLobbyError] = useState<string | null>(null)
  const [discovery, setDiscovery] = useState<LobbyPreviewLike[] | null>(null)
  const [discoveryUnavailable, setDiscoveryUnavailable] = useState(false)
  const [intentOpen, setIntentOpen] = useState(false)
  const [intentInitialQuestion, setIntentInitialQuestion] = useState('')
  const [homeContext, setHomeContext] = useState<HomeToMatchContextLike | null>(() => readHomeContext())
  const [openTableContext, setOpenTableContext] = useState<OpenTableContextLike | null>(() => readOpenTableContext())
  const [homeContextError, setHomeContextError] = useState<string | null>(null)
  const [lobbyInitialJoined, setLobbyInitialJoined] = useState(false)
  const [entryIntent, setEntryIntent] = useState<'listen' | 'join' | null>(() => activeRoom?.intent ?? null)
  const transitionTimer = useRef<number | null>(null)
  const pendingRectRef = useRef<GalleryMediaRect | null>(null)
  const discoveryRequestRef = useRef(0)
  const lobbyRequestRef = useRef(0)
  const reducedMotion = useReducedMotion()
  const liveStatus = useLive((state) => state.status)
  const liveTableState = useLive((state) => state.tableState)
  const refreshDiscovery = () => {
    const requestId = ++discoveryRequestRef.current
    setDiscovery(null)
    setDiscoveryUnavailable(false)
    void fetchDiscovery().then((items) => {
      if (requestId !== discoveryRequestRef.current) return
      setDiscovery(items)
    }).catch(() => {
      if (requestId !== discoveryRequestRef.current) return
      setDiscovery([])
      setDiscoveryUnavailable(true)
    })
  }

  useEffect(() => {
    refreshDiscovery()
    return () => {
      discoveryRequestRef.current += 1
      if (transitionTimer.current !== null) window.clearTimeout(transitionTimer.current)
      document.documentElement.classList.remove('js-has-global-canvas', 'js-global-canvas-error')
    }
  }, [])

  useEffect(() => {
    const onHomeContext = (event: Event) => {
      const context = normalizeHomeToMatchContext((event as CustomEvent<unknown>).detail)
      if (context) {
        setOpenTableContext(null)
        clearOpenTableContext()
        setHomeContext(context)
      }
    }
    const onOpenTableContext = (event: Event) => {
      const context = normalizeOpenTableContext((event as CustomEvent<unknown>).detail)
      if (context) {
        setHomeContext(null)
        clearHomeContext()
        setOpenTableContext(context)
      }
    }
    window.addEventListener(HOME_TO_MATCH_CONTEXT_EVENT, onHomeContext)
    window.addEventListener(OPEN_TABLE_CONTEXT_EVENT, onOpenTableContext)
    return () => {
      window.removeEventListener(HOME_TO_MATCH_CONTEXT_EVENT, onHomeContext)
      window.removeEventListener(OPEN_TABLE_CONTEXT_EVENT, onOpenTableContext)
    }
  }, [])

  useEffect(() => {
    if (appPhase !== 'world' || !lobbyTable || lobbyData || (liveStatus !== 'live' && liveStatus !== 'mock')) return
    let active = true
    void loadLobby(lobbyTable.id).then((preview) => {
      if (active) setLobbyData(preview)
    }).catch(() => undefined)
    return () => { active = false }
  }, [appPhase, liveStatus, lobbyData, lobbyTable])

  useEffect(() => {
    if (!liveTableState) return
    setLobbyData((current) => current ? {
      ...current,
      state_version: liveTableState.version,
      current_subquestion: liveTableState.current_subquestion,
      phase: liveTableState.phase,
      mode: liveTableState.conversation.mode ?? current.mode,
      status: liveTableState.conversation.closed ? 'closed' : current.status,
      participant_count: Object.keys(liveTableState.participants).length,
      available_seats: Math.max(0, 5 - Object.keys(liveTableState.participants).length),
      members: Object.values(liveTableState.participants).map((participant) => ({
        participant_id: participant.participant_id,
        display_name: participant.display_name,
        role: participant.role,
      })),
    } : current)
  }, [liveTableState])
  const schedulePhase = (phase: AppPhase, delay: number) => {
    if (transitionTimer.current !== null) window.clearTimeout(transitionTimer.current)
    transitionTimer.current = window.setTimeout(() => {
      setAppPhase(phase)
      transitionTimer.current = null
    }, delay)
  }
  const openLobby = (table: TableSummary, rect: GalleryMediaRect, initiallyJoined = false) => {
    if (appPhase !== 'gallery' || table.entryMode !== 'immersive') return
    pendingRectRef.current = rect
    setLobbyTable(table)
    setLobbyInitialJoined(initiallyJoined)
    setAppPhase('lobby')
    loadLobbyData(table)
  }
  const openLobbyById = async (tableId: string, initiallyJoined = false) => {
    const preview = await fetchLobby(tableId)
    if (preview.status !== 'open') throw new Error(preview.status === 'closed' ? '这张桌已经收束，暂时不能再次入席。' : '这张桌暂时暂停接收新席位。')
    openLobby(tableSummaryFromLobby(preview), { left: 0, top: 0, width: window.innerWidth, height: window.innerHeight }, initiallyJoined)
  }
  const openIntentTable = async (tableId: string) => {
    await openLobbyById(tableId)
    setIntentOpen(false)
    setIntentInitialQuestion('')
  }
  const openMatchedTable = async (tableId: string, initiallyJoined = false) => {
    await openLobbyById(tableId, initiallyJoined)
    setIntentOpen(false)
    setIntentInitialQuestion('')
  }
  useEffect(() => {
    if (!homeContext || appPhase !== 'gallery') return
    const context = homeContext
    setHomeContext(null)
    clearHomeContext()
    setHomeContextError(null)
    if (context.initial_question) setIntentInitialQuestion(context.initial_question)
    if (context.recommended_table_id) {
      void openLobbyById(context.recommended_table_id).catch((error) => {
        setHomeContextError(error instanceof Error ? error.message : '首页推荐的这张桌暂时无法打开')
      })
      return
    }
    if (context.initial_question) setIntentOpen(true)
  }, [appPhase, homeContext])
  useEffect(() => {
    if (!openTableContext || appPhase !== 'gallery') return
    const context = openTableContext
    setOpenTableContext(null)
    clearOpenTableContext()
    setHomeContextError(null)
    void openLobbyById(context.table_id).catch((error) => {
      setHomeContextError(error instanceof Error ? error.message : '这张桌暂时无法打开')
    })
  }, [appPhase, openTableContext])
  const returnMatchDraftToHome = (draft: MatchToHomeDraftLike): boolean => {
    const handedOff = handoffMatchDraft(draft)
    if (handedOff) {
      setIntentOpen(false)
      setIntentInitialQuestion('')
    }
    return handedOff
  }
  const closeIntent = () => {
    setIntentOpen(false)
    setIntentInitialQuestion('')
  }
  const dismissHomeContextError = () => setHomeContextError(null)
  const loadLobbyData = (table: TableSummary) => {
    const requestId = ++lobbyRequestRef.current
    setLobbyData(null)
    setLobbyFit(null)
    setLobbyError(null)
    setLobbyLoading(true)
    void (async () => {
      try {
        const ready = await ensureTable(table.id, table.hook)
        if (!ready) throw new Error('无法恢复这张桌')
        void selectTable(ready, VIEWER_ID).catch(() => undefined)
        const [preview, fit] = await Promise.all([
          loadLobby(ready),
          loadLobbyFit(ready, viewerSeed()),
        ])
        if (requestId !== lobbyRequestRef.current) return
        setLobbyData(preview)
        setLobbyFit(fit)
      } catch (error) {
        if (requestId !== lobbyRequestRef.current) return
        setLobbyError(error instanceof Error ? error.message : '暂时取不到这张桌的状态')
      } finally {
        if (requestId === lobbyRequestRef.current) setLobbyLoading(false)
      }
    })()
  }
  const retryLobby = () => {
    if (appPhase === 'lobby' && lobbyTable) loadLobbyData(lobbyTable)
  }
  const closeLobby = () => {
    if (appPhase !== 'lobby') return
    lobbyRequestRef.current += 1
    setLobbyTable(null)
    setLobbyData(null)
    setLobbyFit(null)
    setLobbyError(null)
    setLobbyInitialJoined(false)
    setAppPhase('gallery')
  }
  const startWorld = (intent: 'listen' | 'join', initiallyJoined = lobbyInitialJoined) => {
    if (appPhase !== 'lobby' || !lobbyTable) return
    setEntryIntent(intent)
    sessionStorage.setItem(ROOM_SESSION_KEY, JSON.stringify({ table: lobbyTable, intent, joined: initiallyJoined }))
    const viewportRect: GalleryMediaRect = { left: 0, top: 0, width: window.innerWidth, height: window.innerHeight }
    setTransition({ table: lobbyTable, rect: pendingRectRef.current ?? viewportRect })
    setAppPhase('expanding')
    schedulePhase('world', reducedMotion ? 180 : 1100)
  }
  const exitTable = () => {
    if (appPhase !== 'world') return
    if (lobbyTable && liveTableState?.participants[VIEWER_ID] && !liveTableState.conversation.closed) {
      void leaveTable(lobbyTable.id, VIEWER_ID).catch(() => undefined)
    }
    lobbyRequestRef.current += 1
    if (document.activeElement instanceof HTMLElement) document.activeElement.blur()
    setEntryIntent(null)
    sessionStorage.removeItem(ROOM_SESSION_KEY)
    setLobbyTable(null)
    setLobbyData(null)
    setLobbyFit(null)
    setLobbyError(null)
    setLobbyInitialJoined(false)
    setAppPhase('collapsing')
    schedulePhase('gallery', reducedMotion ? 160 : 450)
  }
  const showGallery = appPhase === 'gallery' || appPhase === 'lobby' || appPhase === 'expanding' || appPhase === 'collapsing'
  const showWorld = appPhase === 'expanding' || appPhase === 'world' || appPhase === 'collapsing'
  return (
    <>
      <TableWorld active />
      {showGallery && <TableSea phase={appPhase} returnFocusId={transition?.table.id ?? null} onEnter={openLobby} onOpenIntent={() => { setIntentInitialQuestion(''); setIntentOpen(true) }} discovery={discovery} loading={discovery === null} backendUnavailable={discoveryUnavailable} onRetry={refreshDiscovery} />}
      {homeContextError && <aside className="home-context-error" role="alert"><span>{homeContextError}</span><button type="button" onClick={dismissHomeContextError}>知道了</button></aside>}
      {showWorld && lobbyTable && <ValleyExperience table={lobbyTable} lobby={lobbyData} discovery={discovery ?? []} appPhase={appPhase} entryIntent={entryIntent} initialJoined={lobbyInitialJoined || (activeRoom?.joined ?? false)} onExit={exitTable} />}
      {appPhase === 'lobby' && lobbyTable && <Lobby table={lobbyTable} lobby={lobbyData} fit={lobbyFit} loading={lobbyLoading} error={lobbyError} onClose={closeLobby} onRetry={retryLobby} onListen={() => startWorld('listen')} onJoin={() => startWorld('join', lobbyInitialJoined || Boolean(lobbyData?.members.some((member) => member.participant_id === VIEWER_ID)))} />}
      {appPhase === 'expanding' && transition && <><div className="transition-backdrop" aria-hidden="true" /><TransitionCover snapshot={transition} /></>}
      <IntentPanel open={intentOpen} initialQuestion={intentInitialQuestion} onClose={closeIntent} onSelectTable={openIntentTable} onMatchConfirmed={(tableId) => openMatchedTable(tableId)} onReturnToHomeDraft={returnMatchDraftToHome} />
    </>
  )
}
