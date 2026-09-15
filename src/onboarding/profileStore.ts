/** Local-only profile produced by the pre-match guide for the competition demo. */

export type ProfileTagKind = 'role' | 'experience' | 'interest' | 'perspective'

export interface ProfileTag {
  id: string
  kind: ProfileTagKind
  label: string
  visible: boolean
}

export interface TagProfile {
  version: 1
  ownerKey: string
  displayName: string
  answers: {
    role: string
    experience: string
    interests: string
  }
  conversation: Array<{ role: 'agent' | 'user'; text: string }>
  tags: ProfileTag[]
  seatLabel: string
  summary?: string
  source?: 'agent' | 'local-rules'
  updatedAt: string
}

export interface AgentProfileDraft {
  summary: string
  role_tag: string
  experience_tag: string
  interest_tags: string[]
  perspective_tags: string[]
  seat_label: string
}

const STORAGE_KEY = 'zuoyizhuo.tag-profiles.v1'

function ownerKey(displayName: string): string {
  return displayName.trim().toLocaleLowerCase()
}

function readAll(): Record<string, TagProfile> {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return {}
    const parsed = JSON.parse(raw) as Record<string, TagProfile>
    return parsed && typeof parsed === 'object' ? parsed : {}
  } catch {
    return {}
  }
}

function compactLabel(value: string, fallback: string, limit = 14): string {
  const firstClause = value.split(/[，,。；;\n]/, 1)[0] ?? value
  const cleaned = firstClause
    .replace(/^(?:我(?:目前)?是|目前是|我?目前在做|我在做|我?从事|比较关注|我喜欢|喜欢)\s*(?:一名|一个)?\s*/, '')
    .replace(/\s+/g, ' ')
    .trim()
  return (cleaned || fallback).slice(0, limit)
}

function splitLabels(value: string, fallback: string): string[] {
  const labels = value
    .split(/[、,，/；;。\n]+/)
    .map((item) => compactLabel(item, '', 12))
    .filter(Boolean)
  return (labels.length ? labels : [fallback]).slice(0, 3)
}

function tag(kind: ProfileTagKind, label: string, index: number): ProfileTag {
  return { id: `${kind}-${index}-${label}`, kind, label, visible: true }
}

export function buildTagProfile(
  displayName: string,
  answers: TagProfile['answers'],
  perspectives: string[],
): TagProfile {
  const role = compactLabel(answers.role, '桌边参与者')
  const experience = compactLabel(answers.experience, '愿意分享真实经历')
  const interests = splitLabels(answers.interests, '开放话题')
  const tags: ProfileTag[] = [
    tag('role', role, 0),
    tag('experience', experience, 0),
    ...interests.map((label, index) => tag('interest', label, index)),
    ...perspectives.map((label, index) => tag('perspective', label, index)),
  ]
  const prompts = [
    '你现在主要在做什么？可以说职业、专业或此刻的身份。',
    '你愿意带到桌上的一段真实经历是什么？',
    '你最近最感兴趣，或者最想找人聊的问题是什么？',
  ]
  const responses = [answers.role, answers.experience, answers.interests]
  return {
    version: 1,
    ownerKey: ownerKey(displayName),
    displayName,
    answers,
    conversation: prompts.flatMap((text, index) => [
      { role: 'agent' as const, text },
      { role: 'user' as const, text: responses[index] },
    ]),
    tags,
    seatLabel: role,
    summary: `${role}，带着${experience}来寻找不同视角。`,
    source: 'local-rules',
    updatedAt: new Date().toISOString(),
  }
}

export function buildAgentTagProfile(
  displayName: string,
  draft: AgentProfileDraft,
  conversation: Array<{ role: 'agent' | 'user'; text: string }>,
): TagProfile {
  const role = compactLabel(draft.role_tag, '桌边参与者', 18)
  const experience = compactLabel(draft.experience_tag, '愿意分享真实经历', 22)
  const interests = draft.interest_tags.map((value) => compactLabel(value, '', 18)).filter(Boolean).slice(0, 3)
  const perspectives = draft.perspective_tags.map((value) => compactLabel(value, '', 18)).filter(Boolean).slice(0, 2)
  const safeInterests = interests.length ? interests : ['开放话题']
  const safePerspectives = perspectives.length ? perspectives : ['基于经验']
  const tags: ProfileTag[] = [
    tag('role', role, 0),
    tag('experience', experience, 0),
    ...safeInterests.map((label, index) => tag('interest', label, index)),
    ...safePerspectives.map((label, index) => tag('perspective', label, index)),
  ]
  return {
    version: 1,
    ownerKey: ownerKey(displayName),
    displayName,
    answers: {
      role,
      experience,
      interests: safeInterests.join('、'),
    },
    conversation: conversation.slice(-8),
    tags,
    seatLabel: compactLabel(draft.seat_label, role, 20),
    summary: draft.summary.trim().slice(0, 120),
    source: 'agent',
    updatedAt: new Date().toISOString(),
  }
}

export function getTagProfile(displayName: string): TagProfile | null {
  const profile = readAll()[ownerKey(displayName)]
  if (!profile || profile.version !== 1) return null
  return profile
}

export function saveTagProfile(profile: TagProfile): void {
  try {
    const profiles = readAll()
    profiles[profile.ownerKey] = profile
    localStorage.setItem(STORAGE_KEY, JSON.stringify(profiles))
    window.dispatchEvent(new CustomEvent('zuoyizhuo:tag-profile', { detail: profile }))
  } catch {
    // The current page can still use the returned profile when storage is blocked.
  }
}

export function buildMatchPrompt(profile: TagProfile): string {
  const perspectives = profile.tags
    .filter((item) => item.kind === 'perspective' && item.visible)
    .map((item) => item.label)
  const interests = profile.tags
    .filter((item) => item.kind === 'interest' && item.visible)
    .map((item) => item.label)
  const topic = interests.length ? interests.join('、') : profile.answers.interests
  const angle = perspectives.length ? `，希望听到${perspectives.join('、')}的不同看法` : ''
  return `我想围绕${topic}找真人深入聊聊。我会以${profile.seatLabel}的身份参与${angle}。`.slice(0, 120)
}
