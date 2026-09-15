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

const DEFAULT_FRIENDS: FriendProfile[] = [
  { id: 'blue', displayName: '蓝衣桌友', avatarHue: 205, avatarInitial: '蓝', status: 'online', motto: '今晚还在湖边吗' },
  { id: 'girl', displayName: '白衣桌友', avatarHue: 320, avatarInitial: '白', status: 'online', motto: '想听你上次那桌的收束' },
  { id: 'orange', displayName: '橙衣桌友', avatarHue: 28, avatarInitial: '橙', status: 'away', motto: '稍后再看那桌记得叫我' },
  { id: 'green', displayName: '绿衣桌友', avatarHue: 148, avatarInitial: '绿', status: 'offline', motto: '明天再聊也不迟' },
]

const THREADS_KEY = 'zuoyizhuo.demo-friend-threads'
const CONNECTIONS_KEY = 'zuoyizhuo.demo-table-friends'

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
let connectedFriends = readConnectedFriends()
const listeners = new Set<() => void>()

function readConnectedFriends(): FriendProfile[] {
  try {
    const raw = localStorage.getItem(CONNECTIONS_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw) as FriendProfile[]
    return Array.isArray(parsed)
      ? parsed.filter((friend) => friend && typeof friend.id === 'string' && typeof friend.displayName === 'string').slice(0, 12)
      : []
  } catch {
    return []
  }
}

function writeConnectedFriends() {
  try {
    localStorage.setItem(CONNECTIONS_KEY, JSON.stringify(connectedFriends))
  } catch {
    // The connection remains available in memory for this demo session.
  }
}

function emit() {
  for (const listener of listeners) listener()
}

export function getFriends(): FriendProfile[] {
  return [...connectedFriends, ...DEFAULT_FRIENDS.filter((friend) => !connectedFriends.some((item) => item.id === friend.id))]
    .map((friend) => ({ ...friend }))
}

export function getFriend(id: string): FriendProfile | undefined {
  return getFriends().find((friend) => friend.id === id)
}

export function connectDemoFriend(person: { id: string; displayName: string; role: string }): FriendProfile {
  const id = `table-${person.id}`
  const existing = connectedFriends.find((friend) => friend.id === id)
  if (existing) return { ...existing }
  const hues = [24, 158, 204, 328]
  const friend: FriendProfile = {
    id,
    displayName: person.displayName,
    avatarHue: hues[connectedFriends.length % hues.length]!,
    avatarInitial: person.displayName.slice(0, 1) || '友',
    status: 'online',
    motto: `从“离开大城市”那桌认识 · ${person.role}`,
  }
  connectedFriends = [friend, ...connectedFriends]
  writeConnectedFriends()
  if (!(threads[id]?.length)) {
    threads = {
      ...threads,
      [id]: [{
        id: `hello-${Date.now()}`,
        from: 'friend',
        text: '刚才那桌很有意思。关于“判断之后谁来承担后果”，我还想听听你的经历。要不要下次继续？',
        at: Date.now(),
      }],
    }
    writeThreads(threads)
  }
  emit()
  return { ...friend }
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
