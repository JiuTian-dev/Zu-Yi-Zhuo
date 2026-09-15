import { getHomeAccount, type AvatarCharacter } from '../home/accountStore'
import './characterPortrait.css'

export type CharacterKey = 'host' | AvatarCharacter

const CHARACTER_PORTRAITS: Record<AvatarCharacter, string> = {
  blue: '/scene/portrait-blue.webp',
  orange: '/scene/portrait-orange.webp',
  white: '/scene/portrait-white.webp',
  green: '/scene/portrait-green.webp',
}

const CHARACTER_ORDER: AvatarCharacter[] = ['white', 'orange', 'green', 'blue']

export function viewerCharacter(): AvatarCharacter {
  return getHomeAccount().avatarCharacter ?? 'blue'
}

export function demoCharacterForIndex(index: number): AvatarCharacter {
  const selected = viewerCharacter()
  return CHARACTER_ORDER.filter((character) => character !== selected)[index] ?? selected
}

export function characterForPerson(displayName: string, participantId?: string, viewerId?: string): CharacterKey {
  if (participantId && viewerId && participantId === viewerId) return viewerCharacter()
  if (participantId === 'table-host' || participantId === 'roundtable-agent' || displayName.includes('主持')) return 'host'
  if (displayName.includes('林夏')) return demoCharacterForIndex(0)
  if (displayName.includes('周砚')) return demoCharacterForIndex(1)
  if (displayName.includes('程野')) return demoCharacterForIndex(2)
  return viewerCharacter()
}

export default function CharacterPortrait({ character, label, className = '', online = false }: {
  character: CharacterKey
  label: string
  className?: string
  online?: boolean
}) {
  return (
    <span className={`character-portrait is-${character} is-ready ${className}`} aria-label={label} role="img">
      {character === 'host'
        ? <span className="character-agent-art-frame" aria-hidden="true">
            <img className="character-agent-art" src="/scene/azhuo-agent-v2.png" alt="" decoding="async" />
          </span>
        : <img src={CHARACTER_PORTRAITS[character]} alt="" decoding="async" />}
      {character === 'host' && <em className="character-agent-badge">Agent</em>}
      {online && <i aria-hidden="true" />}
    </span>
  )
}
