export type HumanActorId = 'shen-zhiyao' | 'zhou-mo' | 'lin-zhou' | 'xu-qing'
export type ActorId = HumanActorId | 'table-host' | 'viewer'
export type ActorType = 'human' | 'viewer' | 'agent'
export type VisualState = 'idle' | 'listening' | 'speaking'
export type AgentAction = 'SILENCE' | 'PASS' | 'PROBE' | 'REFRAME' | 'GROUND' | 'CLOSE'

export interface SeatActor {
  id: ActorId
  seatId: string
  actorType: ActorType
  userId?: string
  displayName: string
  role: string
  whyHere: string
  quote?: string
  accent: string
  plateCenter: readonly [number, number]
  plateRadius: readonly [number, number]
  hotspotClass: string
}

export const humanActors: SeatActor[] = [
  {
    id: 'shen-zhiyao', seatId: 'seat-west', actorType: 'human', userId: 'zhihu:people/shen-zhiyao',
    displayName: '沈知遥', role: '自由撰稿人', accent: '#e8dfca', hotspotClass: 'actor-west',
    whyHere: '在山里住了两年，正在重新理解“有用”以外的生活。',
    quote: '真正休息时，我会暂时放弃“有用”。', plateCenter: [0.515, 0.63], plateRadius: [0.055, 0.145],
  },
  {
    id: 'zhou-mo', seatId: 'seat-northwest', actorType: 'human', userId: 'zhihu:people/zhou-mo',
    displayName: '周末', role: '产品经理', accent: '#d87843', hotspotClass: 'actor-northwest',
    whyHere: '每天通勤三小时，他怀疑自己不是没有时间，而是不敢停下。',
    quote: '我不是没有时间，是不敢让时间空下来。', plateCenter: [0.58, 0.615], plateRadius: [0.05, 0.14],
  },
  {
    id: 'lin-zhou', seatId: 'seat-northeast', actorType: 'human', userId: 'zhihu:people/lin-zhou',
    displayName: '林舟', role: '独立开发者', accent: '#59698c', hotspotClass: 'actor-northeast',
    whyHere: '离开公司以后仍然不会下班，正在为工作重新划边界。',
    quote: '自由职业以后，我反而更不会下班了。', plateCenter: [0.675, 0.61], plateRadius: [0.052, 0.145],
  },
  {
    id: 'xu-qing', seatId: 'seat-east', actorType: 'human', userId: 'zhihu:people/xu-qing',
    displayName: '许青', role: '心理咨询师', accent: '#739d94', hotspotClass: 'actor-east',
    whyHere: '长期研究倦怠与恢复，她想把休息从奖励变回生活的一部分。',
    quote: '休息不是奖励，它原本就是生活的一部分。', plateCenter: [0.745, 0.65], plateRadius: [0.057, 0.16],
  },
]

export const tableHost: SeatActor = {
  id: 'table-host', seatId: 'seat-north', actorType: 'agent', displayName: '圆桌主持', role: 'Table Host',
  whyHere: '认真听，把问题递给此刻最值得说话的人。', accent: '#ffd17c', hotspotClass: 'actor-host',
  quote: '这个问题，我反而很想听听你。', plateCenter: [0.624, 0.59], plateRadius: [0.04, 0.09],
}

export const viewerSeat: SeatActor = {
  id: 'viewer', seatId: 'seat-south', actorType: 'viewer', displayName: '第五席', role: '等待入席',
  whyHere: '这一桌还缺一个真正尝试停下来的人。', accent: '#ffd58c', hotspotClass: 'actor-viewer',
  plateCenter: [0.49, 0.78], plateRadius: [0.07, 0.12],
}

export const actors = [...humanActors, tableHost, viewerSeat]
export const findActor = (id: ActorId) => actors.find((actor) => actor.id === id)
