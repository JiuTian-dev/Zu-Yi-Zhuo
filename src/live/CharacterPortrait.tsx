import { useEffect, useState } from 'react'
import * as THREE from 'three'
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js'
import { MeshoptDecoder } from 'three/addons/libs/meshopt_decoder.module.js'
import { getHomeAccount, type AvatarCharacter } from '../home/accountStore'
import './characterPortrait.css'
import { prepareCharacterShading } from './modelShading'

export type CharacterKey = 'host' | AvatarCharacter

const CHARACTER_MODELS: Record<CharacterKey, { url: string; fallback: string }> = {
  host: { url: '/scene/host-agent.glb', fallback: '桌' },
  blue: { url: '/scene/avatar-blue-hd.glb', fallback: '蓝' },
  orange: { url: '/scene/avatar-orange-hd.glb', fallback: '橙' },
  white: { url: '/scene/avatar-white-hd.glb', fallback: '白' },
  green: { url: '/scene/avatar-green-hd.glb', fallback: '绿' },
}

const portraitCache = new Map<CharacterKey, Promise<string>>()

async function renderPortrait(character: CharacterKey): Promise<string> {
  const canvas = document.createElement('canvas')
  canvas.width = 512
  canvas.height = 512
  const renderer = new THREE.WebGLRenderer({ canvas, alpha: true, antialias: true, preserveDrawingBuffer: true })
  renderer.setPixelRatio(1)
  renderer.setSize(512, 512, false)
  renderer.outputColorSpace = THREE.SRGBColorSpace
  renderer.toneMapping = THREE.ACESFilmicToneMapping
  renderer.toneMappingExposure = .92
  renderer.setClearColor(0x000000, 0)

  const scene = new THREE.Scene()
  scene.add(new THREE.HemisphereLight(0xfffaf1, 0x65756d, 1.4))
  const keyLight = new THREE.DirectionalLight(0xffefd9, 2.7)
  keyLight.position.set(-3, 5, 5)
  scene.add(keyLight)
  const rimLight = new THREE.DirectionalLight(0xc5e3ff, 1.6)
  rimLight.position.set(4, 2, -3)
  scene.add(rimLight)

  const loader = new GLTFLoader()
  loader.setMeshoptDecoder(MeshoptDecoder)
  const gltf = await loader.loadAsync(CHARACTER_MODELS[character].url)
  const model = gltf.scene
  prepareCharacterShading(model)
  if (character === 'host') {
    model.rotation.y = -.24
    model.rotation.z = -.035
  }
  model.updateMatrixWorld(true)
  const firstBox = new THREE.Box3().setFromObject(model)
  const firstSize = firstBox.getSize(new THREE.Vector3())
  const scale = 2.3 / Math.max(firstSize.y, .001)
  model.scale.setScalar(scale)
  model.updateMatrixWorld(true)
  const box = new THREE.Box3().setFromObject(model)
  const center = box.getCenter(new THREE.Vector3())
  model.position.set(-center.x, -box.min.y - .08, -center.z)
  scene.add(model)

  const camera = new THREE.PerspectiveCamera(28, 1, .1, 50)
  camera.position.set(0, character === 'host' ? 1.48 : 1.18, character === 'host' ? 4.25 : 5.05)
  camera.lookAt(0, character === 'host' ? 1.4 : 1.13, 0)
  renderer.render(scene, camera)
  const image = canvas.toDataURL('image/png')

  scene.traverse((child) => {
    if (!(child instanceof THREE.Mesh)) return
    child.geometry?.dispose()
    const materials = Array.isArray(child.material) ? child.material : [child.material]
    materials.forEach((material) => {
      for (const value of Object.values(material)) if (value instanceof THREE.Texture) value.dispose()
      material.dispose()
    })
  })
  renderer.dispose()
  return image
}

function portraitFor(character: CharacterKey): Promise<string> {
  const cached = portraitCache.get(character)
  if (cached) return cached
  const rendered = renderPortrait(character)
  portraitCache.set(character, rendered)
  return rendered
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
  const [image, setImage] = useState<string | null>(null)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    if (character === 'host') {
      setImage(null)
      setFailed(false)
      return
    }
    let active = true
    setImage(null)
    setFailed(false)
    void portraitFor(character).then((result) => {
      if (active) setImage(result)
    }).catch(() => {
      if (active) setFailed(true)
    })
    return () => { active = false }
  }, [character])

  return (
    <span className={`character-portrait is-${character} ${image || character === 'host' ? 'is-ready' : ''} ${className}`} aria-label={label} role="img">
      {character === 'host'
        ? <span className="character-agent-orb" aria-hidden="true"><span><i /><i /></span><b>桌</b></span>
        : image && !failed ? <img src={image} alt="" /> : <b aria-hidden="true">{CHARACTER_MODELS[character].fallback}</b>}
      {character === 'host' && <em className="character-agent-badge">Agent</em>}
      {online && <i aria-hidden="true" />}
    </span>
  )
}
