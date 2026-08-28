export type WorldId = 'campfire' | 'valley' | 'workshop'
export type AppPhase = 'gallery' | 'expanding' | 'world' | 'collapsing'
export type TableStatus = 'live' | 'forming'
export type TableEntryMode = 'immersive' | 'preview'
export type TableTransitionPreset = 'valley' | 'cover-only'

export interface CoverFocus {
  x: number
  y: number
}

export interface WorldSummary {
  id: WorldId
  name: string
  atmosphere: string
  accent: string
  tables: TableSummary[]
}

interface TableSummaryBase {
  id: string
  worldId: WorldId
  hook: string
  seatedCount: number
  missingPerspective: string
}

type TableVisual = {
  sceneTexture: string
  coverFocus: CoverFocus
} & (
  | {
      status: 'live'
      entryMode: 'immersive'
      transitionPreset: 'valley'
      depthTexture: string
    }
  | {
      status: 'forming'
      entryMode: 'preview'
      transitionPreset: 'cover-only'
      depthTexture?: never
    }
)

export type TableSummary = TableSummaryBase & TableVisual

const table = (
  id: string,
  worldId: WorldId,
  hook: string,
  seatedCount: number,
  missingPerspective: string,
  visual: TableVisual,
): TableSummary => ({ id, worldId, hook, seatedCount, missingPerspective, ...visual })

const preview = (sceneTexture: string, coverFocus: CoverFocus): TableVisual => ({
  sceneTexture,
  status: 'forming',
  entryMode: 'preview',
  transitionPreset: 'cover-only',
  coverFocus,
})

export const worlds: WorldSummary[] = [
  {
    id: 'campfire',
    name: '深夜篝火',
    atmosphere: '真诚、安静、安全，适合把话说深一点。',
    accent: '#FF9B42',
    tables: [
      table('leaving-the-city', 'campfire', '关于离开大城市这件事，他们已经聊了三天。', 4, '还缺一个真正离开过的人', preview('/assets/valley-world-clean.png', { x: 0.67, y: 0.52 })),
      table('staying-in-the-city', 'campfire', '留在大城市，真的值得吗？', 3, '还缺一个决定留下来的人', preview('/assets/valley-world-clean.png', { x: 0.63, y: 0.48 })),
      table('starting-again', 'campfire', '三十岁以后，重新开始意味着什么？', 2, '还缺一个已经重新开始的人', preview('/assets/valley-world-clean.png', { x: 0.7, y: 0.55 })),
    ],
  },
  {
    id: 'valley',
    name: '瑞士山谷',
    atmosphere: '放松、漫游，暂时离现实远一点。',
    accent: '#A8CE84',
    tables: [
      table('first-solo-trip', 'valley', '第一次一个人旅行。', 3, '还缺一个刚刚独自出发的人', preview('/assets/valley-world-clean.png', { x: 0.36, y: 0.5 })),
      table('learning-to-rest', 'valley', '为什么我们越来越不会休息？', 4, '还缺一个真正慢下来的人', {
        sceneTexture: '/assets/valley-world-clean.png',
        depthTexture: '/assets/valley-world-depth.png',
        status: 'live',
        entryMode: 'immersive',
        transitionPreset: 'valley',
        coverFocus: { x: 0.67, y: 0.58 },
      }),
      table('worth-the-trip', 'valley', '有哪些值得专程去吃的地方？', 2, '还缺一个会为味道出发的人', preview('/assets/valley-world-clean.png', { x: 0.72, y: 0.46 })),
    ],
  },
  {
    id: 'workshop',
    name: '午后 Workshop',
    atmosphere: '创造、碰撞，把一个念头带到现实里。',
    accent: '#FFD28A',
    tables: [
      table('learning-to-code', 'workshop', 'AI 时代还要学编程吗？', 4, '还缺一个刚开始学习的人', preview('/assets/valley-world-clean.png', { x: 0.78, y: 0.5 })),
      table('idea-to-product', 'workshop', '一个想法怎样变成产品？', 3, '还缺一个把产品做出来的人', preview('/assets/valley-world-clean.png', { x: 0.76, y: 0.58 })),
      table('creative-drive', 'workshop', '怎样重新找回创造欲？', 3, '还缺一个重新开始创作的人', preview('/assets/valley-world-clean.png', { x: 0.72, y: 0.43 })),
    ],
  },
]

export const findWorld = (id: WorldId) => worlds.find((world) => world.id === id)

export const findTable = (id: string) =>
  worlds.flatMap((world) => world.tables).find((table) => table.id === id)

export const galleryTableIds = ['learning-to-rest', 'leaving-the-city', 'learning-to-code'] as const

export const galleryTables: TableSummary[] = galleryTableIds.map((id) => {
  const galleryTable = findTable(id)
  if (!galleryTable) throw new Error(`Gallery table not found: ${id}`)
  return galleryTable
})
