export type WorldId = 'campfire' | 'valley' | 'workshop'

export interface WorldSummary {
  id: WorldId
  name: string
  atmosphere: string
  accent: string
  tables: TableSummary[]
}

export interface TableSummary {
  id: string
  worldId: WorldId
  hook: string
  seatedCount: number
  missingPerspective: string
}

const table = (
  id: string,
  worldId: WorldId,
  hook: string,
  seatedCount: number,
  missingPerspective: string,
): TableSummary => ({ id, worldId, hook, seatedCount, missingPerspective })

export const worlds: WorldSummary[] = [
  {
    id: 'campfire',
    name: '深夜篝火',
    atmosphere: '真诚、安静、安全，适合把话说深一点。',
    accent: '#FF9B42',
    tables: [
      table('leaving-the-city', 'campfire', '关于离开大城市这件事，他们已经聊了三天。', 4, '还缺一个真正离开过的人'),
      table('staying-in-the-city', 'campfire', '留在大城市，真的值得吗？', 3, '还缺一个决定留下来的人'),
      table('starting-again', 'campfire', '三十岁以后，重新开始意味着什么？', 2, '还缺一个已经重新开始的人'),
    ],
  },
  {
    id: 'valley',
    name: '瑞士山谷',
    atmosphere: '放松、漫游，暂时离现实远一点。',
    accent: '#A8CE84',
    tables: [
      table('first-solo-trip', 'valley', '第一次一个人旅行。', 3, '还缺一个刚刚独自出发的人'),
      table('learning-to-rest', 'valley', '为什么我们越来越不会休息？', 4, '还缺一个真正慢下来的人'),
      table('worth-the-trip', 'valley', '有哪些值得专程去吃的地方？', 2, '还缺一个会为味道出发的人'),
    ],
  },
  {
    id: 'workshop',
    name: '午后 Workshop',
    atmosphere: '创造、碰撞，把一个念头带到现实里。',
    accent: '#FFD28A',
    tables: [
      table('learning-to-code', 'workshop', 'AI 时代还要学编程吗？', 4, '还缺一个刚开始学习的人'),
      table('idea-to-product', 'workshop', '一个想法怎样变成产品？', 3, '还缺一个把产品做出来的人'),
      table('creative-drive', 'workshop', '怎样重新找回创造欲？', 3, '还缺一个重新开始创作的人'),
    ],
  },
]

export const findWorld = (id: WorldId) => worlds.find((world) => world.id === id)

export const findTable = (id: string) =>
  worlds.flatMap((world) => world.tables).find((table) => table.id === id)
