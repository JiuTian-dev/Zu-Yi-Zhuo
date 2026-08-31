import type { AgentActionName, TablePhase } from './contract'
import { pushMessage, resetLive, setLive } from './store'

/** Mock driver used when the backend is unreachable: same event shapes, fully local. */

const SCRIPT: Array<{ id: string; text: string; waitMs: number }> = [
  { id: 'shen-zhiyao', text: '上个月我给自己排了三天「什么都不做」，结果每天都在焦虑这三天被浪费了。', waitMs: 4200 },
  { id: 'zhou-mo', text: '我不敢让时间空下来，一空下来就觉得自己正在被淘汰。', waitMs: 5200 },
  { id: 'lin-zhou', text: '自由职业之后没人给我下班的概念，我反而怀念被迫休息的日子。', waitMs: 5200 },
  { id: 'xu-qing', text: '你们说的都是「停下来之后的内疚」，这其实是把价值感绑在了产出上。', waitMs: 5600 },
  { id: 'zhou-mo', text: '所以问题不是没时间休息，而是停下来的时候，我什么都不是？', waitMs: 5600 },
  { id: 'shen-zhiyao', text: '可能吧，可我就是靠产出获得安全感的，放下它我不知道自己是谁。', waitMs: 5600 },
  { id: 'xu-qing', text: '休息不是从工作里偷来的时间，它本来就是生活的默认状态，是我们把它变成了奖励。', waitMs: 5600 },
  { id: 'lin-zhou', text: '如果把它当默认状态，我第一件要改的就是把「回消息」从休息日的义务里删掉。', waitMs: 5400 },
]

const HOST_BEATS: Record<number, { action: AgentActionName; text: string }> = {
  3: { action: 'PROBE', text: '是什么让「什么都不做」变得这么难？' },
  5: { action: 'REFRAME', text: '如果把「有用」先放下，你害怕失去的是什么？' },
  6: { action: 'PASS', text: '这个问题，我想先递给刚提到边界的人。' },
  7: { action: 'GROUND', text: '把「回消息从义务里删掉」记在桌面上了，这就是一个可验证的起点。' },
}

const PHASE_TIMELINE: Record<number, { phase: TablePhase; subQuestion: string | null }> = {
  2: { phase: 'explore', subQuestion: null },
  4: { phase: 'tension', subQuestion: '停下来的时候，你的价值感来自哪里？' },
  6: { phase: 'deepen', subQuestion: '允许自己停下之后，你想先拿回什么？' },
}

let timers: number[] = []

function clearTimers() {
  timers.forEach((timer) => window.clearTimeout(timer))
  timers = []
}

function hostBeat(key: number) {
  const beat = HOST_BEATS[key]
  if (!beat) return
  setLive({ hostAction: { action: beat.action, text: beat.text, target: beat.action === 'PASS' ? 'lin-zhou' : null } })
  pushMessage({ participantId: 'table-host', text: beat.text, fromHost: true, action: beat.action })
}

export function startMock() {
  clearTimers()
  resetLive()
  setLive({
    status: 'mock',
    coreQuestion: '为什么我们越来越不会休息？',
    phase: 'opening',
    seatCount: 4,
  })
  SCRIPT.forEach((line, index) => {
    timers.push(window.setTimeout(() => {
      pushMessage({ participantId: line.id, text: line.text, fromHost: false, action: null })
      const timeline = PHASE_TIMELINE[index]
      if (timeline) setLive({ phase: timeline.phase, subQuestion: timeline.subQuestion })
      window.setTimeout(() => hostBeat(index), 1500)
    }, 2600 + SCRIPT.slice(0, index).reduce((sum, item) => sum + item.waitMs, 0)))
  })
}

export function stopMock() {
  clearTimers()
}

export function sendViewerMessage(text: string) {
  pushMessage({ participantId: 'viewer', text, fromHost: false, action: null })
  timers.push(window.setTimeout(() => {
    setLive({ hostAction: { action: 'PROBE', text: '能再多说一句那天的感受吗？', target: 'viewer' } })
    pushMessage({ participantId: 'table-host', text: '能再多说一句那天的感受吗？', fromHost: true, action: 'PROBE' })
  }, 2400))
}

export function requestClose() {
  setLive({ closeState: 'started' })
  timers.push(window.setTimeout(() => {
    setLive({
      closeState: 'ready',
      baseline: {
        core_question_before: '为什么我们越来越不会休息？',
        key_consensus: [
          { text: '休息的障碍不是时间，而是停下时的内疚感。', evidence_turns: [2, 4] },
          { text: '把休息从奖励变回默认状态，需要具体边界而不是决心。', evidence_turns: [6, 7] },
        ],
        unresolved_disagreements: [
          { text: '产出带来的安全感是否可以与休息共存，仍未达成一致。', disagreement_type: 'value_conflict' },
        ],
        evolved_question: { text: '允许自己停下来之后，你想先拿回什么？', evidence_turns: [7] },
        collective_next_steps: [
          { item_type: 'commitment', text: '休息日把「回消息」从义务里删掉。', is_commitment: true, owner_participant_id: 'lin-zhou' },
        ],
      },
      personalCard: {
        what_changed: [
          { text: '你把「休息 = 奖励」识别成了自己的默认假设。', evidence_turns: [4] },
        ],
        your_contribution: [
          { text: '你的入席让这一桌补上了「真正尝试停下来的人」。', evidence_turns: [1] },
        ],
        worth_continuing_with: [
          { participant_id: 'xu-qing', reason: '她正在研究倦怠与恢复，和你的处境最相关。' },
        ],
        suggested_next_actions: [
          { item_type: 'suggestion', text: '下周挑一天，试一次「无义务休息日」。', is_commitment: false },
        ],
      },
    })
  }, 1400))
}
