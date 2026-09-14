/** @origin HOME — demo friends roster + local chat threads for profile sidebar. */

export interface FriendProfile {
  id: string
  displayName: string
  avatarHue: number
  avatarInitial: string
  status: 'online' | 'away' | 'offline'
  motto: string
}

export interface ChatMessage {
  id: string
  from: 'me' | 'friend'
  text: string
  at: number
}

const FRIENDS: FriendProfile[] = [
  { id: 'blue', displayName: '蓝衣桌友', avatarHue: 205, avatarInitial: '蓝', status: 'online', motto: '今晚还在湖边吗' },
  { id: 'girl', displayName: '白衣桌友', avatarHue: 320, avatarInitial: '白', status: 'online', motto: '想听你上次那桌的收束' },
  { id: 'orange', displayName: '橙衣桌友', avatarHue: 28, avatarInitial: '橙', status: 'away', motto: '稍后再看那桌记得叫我' },
  { id: 'green', displayName: '绿衣桌友', avatarHue: 148, avatarInitial: '绿', status: 'offline', motto: '明天再聊也不迟' },
]

const THREADS_KEY = 'zuoyizhuo.demo-friend-threads'

type ThreadMap = Record<string, ChatMessage[]>

function readThreads(): ThreadMap {
  try {
    const raw = localStorage.getItem(THREADS_KEY)
    if (!raw) return seedThreads()
    const parsed = JSON.parse(raw) as ThreadMap
    return parsed && typeof parsed === 'object' ? parsed : seedThreads()
  } catch {
    return seedThreads()
  }
}

function seedThreads(): ThreadMap {
  const now = Date.now()
  return {
    blue: [
      { id: 'b1', from: 'friend', text: '你也到湖边了？', at: now - 1000 * 60 * 40 },
      { id: 'b2', from: 'me', text: '刚坐下，风有点凉。', at: now - 1000 * 60 * 38 },
    ],
    girl: [
      { id: 'g1', from: 'friend', text: '那桌收束卡你看了吗', at: now - 1000 * 60 * 90 },
    ],
    orange: [],
    green: [
      { id: 'n1', from: 'friend', text: '我先下了，明天继续。', at: now - 1000 * 60 * 200 },
    ],
  }
}

function writeThreads(map: ThreadMap) {
  try {
    localStorage.setItem(THREADS_KEY, JSON.stringify(map))
  } catch {
    // Demo chat still works in-memory.
  }
}

let threads = readThreads()
const listeners = new Set<() => void>()

function emit() {
  for (const listener of listeners) listener()
}

export function getFriends(): FriendProfile[] {
  return FRIENDS.map((friend) => ({ ...friend }))
}

export function getFriend(id: string): FriendProfile | undefined {
  return FRIENDS.find((friend) => friend.id === id)
}

export function getThread(friendId: string): ChatMessage[] {
  return [...(threads[friendId] ?? [])]
}

export function subscribeFriendThreads(listener: () => void): () => void {
  listeners.add(listener)
  listener()
  return () => { listeners.delete(listener) }
}

export function sendFriendMessage(friendId: string, textRaw: string): ChatMessage | null {
  const text = textRaw.trim()
  if (!text || !getFriend(friendId)) return null
  const message: ChatMessage = {
    id: `m-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
    from: 'me',
    text: text.slice(0, 500),
    at: Date.now(),
  }
  threads = {
    ...threads,
    [friendId]: [...(threads[friendId] ?? []), message],
  }
  writeThreads(threads)
  emit()

  // Light demo reply so the QQ window feels alive.
  window.setTimeout(() => {
    const friend = getFriend(friendId)
    if (!friend) return
    const reply: ChatMessage = {
      id: `r-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
      from: 'friend',
      text: pickReply(friend.displayName),
      at: Date.now(),
    }
    threads = {
      ...threads,
      [friendId]: [...(threads[friendId] ?? []), reply],
    }
    writeThreads(threads)
    emit()
  }, 700 + Math.random() * 900)

  return message
}

function pickReply(name: string): string {
  const lines = [
    '收到，我这边也在。',
    '好，等会儿桌边见。',
    '嗯，慢慢说就行。',
    `${name.slice(0, 1)}…我刚看到消息。`,
    '先搁这儿，我去倒杯水。',
  ]
  return lines[Math.floor(Math.random() * lines.length)]!
}
