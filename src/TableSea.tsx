import { UseCanvas } from '@14islands/r3f-scroll-rig'
import { EffectComposer, Bloom } from '@react-three/postprocessing'
import { useFrame, useThree } from '@react-three/fiber'
import gsap from 'gsap'
import { useEffect, useMemo, useRef, useLayoutEffect, useState, type CSSProperties } from 'react'
import * as THREE from 'three'
import { galleryTables, worldLabel, type AppPhase, type TableSummary } from './domain'
import './gallery.css'

export interface GalleryMediaRect { left: number; top: number; width: number; height: number }

interface TableSeaProps {
  onEnter(table: TableSummary, rect: GalleryMediaRect): void
  enhanced: boolean
  phase: AppPhase
  returnFocusId: string | null
}

/* ------------------------------------------------------------- themes */

type ThemeId = 'campfire' | 'valley' | 'workshop' | 'rooftop' | 'bookstore' | 'pier' | 'snow' | 'forest' | 'cafe' | 'rain' | 'autumn' | 'desert' | 'lake'

interface ThemeDef {
  label: string
  lamp: string          // the warm core (bloom-lit)
  rim: string           // accent ring / halo
  ground: string        // disc base color
  feature: 'fire' | 'house' | 'camping' | 'shelf' | 'lamps' | 'canoe'
}

const THEMES: Record<ThemeId, ThemeDef> = {
  campfire: { label: '深夜篝火', lamp: '#ff9a3c', rim: '#F2A65A', ground: '#241f1a', feature: 'fire' },
  valley: { label: '瑞士山谷', lamp: '#ffcf8a', rim: '#A8CE84', ground: '#1c2a20', feature: 'house' },
  workshop: { label: '午后工坊', lamp: '#ffd28d', rim: '#FFD28A', ground: '#2a2118', feature: 'house' },
  rooftop: { label: '天台夜色', lamp: '#ffe3a0', rim: '#b9c4ff', ground: '#1b2030', feature: 'lamps' },
  bookstore: { label: '书店一角', lamp: '#ffd7b0', rim: '#ffc9a0', ground: '#251c16', feature: 'shelf' },
  pier: { label: '海边栈桥', lamp: '#a8e8ff', rim: '#8fd4e8', ground: '#16242e', feature: 'canoe' },
  snow: { label: '雪山木屋', lamp: '#cfe6ff', rim: '#bcd6ff', ground: '#1e2430', feature: 'house' },
  forest: { label: '森林火堆', lamp: '#ffb37a', rim: '#ff9b42', ground: '#1b241c', feature: 'fire' },
  cafe: { label: '咖啡馆', lamp: '#ffd9a8', rim: '#e8c9a0', ground: '#241d18', feature: 'shelf' },
  rain: { label: '雨檐下', lamp: '#9fb8e0', rim: '#a8c0e8', ground: '#1a2028', feature: 'lamps' },
  autumn: { label: '秋日庭院', lamp: '#ffc98a', rim: '#ffb37a', ground: '#241d12', feature: 'lamps' },
  desert: { label: '沙漠帐篷', lamp: '#e8b06a', rim: '#ffcf8a', ground: '#26190f', feature: 'camping' },
  lake: { label: '湖边垂钓', lamp: '#9ac6b8', rim: '#7fd4a8', ground: '#16242a', feature: 'canoe' },
}

const CORE_IDS = ['learning-to-rest', 'leaving-the-city', 'learning-to-code']

interface Ent {
  theme: ThemeId
  accent: string
  table: TableSummary
  pos: THREE.Vector3
  index: number
}

const entries: Ent[] = (() => {
  const core = galleryTables.filter((t) => CORE_IDS.includes(t.id))
  const decoThemes: ThemeId[] = ['rooftop', 'bookstore', 'pier', 'snow', 'forest', 'cafe', 'rain', 'autumn', 'desert', 'lake']
  const decoTables: TableSummary[] = decoThemes.map((theme, i) => ({
    id: `deco-${theme}`,
    worldId: 'valley',
    hook: '',
    seatedCount: 2 + ((i * 2) % 3),
    missingPerspective: '',
    sceneTexture: '/assets/valley-world-clean.png',
    status: 'forming',
    entryMode: 'preview',
    transitionPreset: 'cover-only',
    coverFocus: { x: 0.5, y: 0.5 },
  }))
  // spiral rings: ring radii with jittered angles (organic, not a grid)
  const ringSpecs = [
    { count: 5, radius: 4.6, phase: 0 },
    { count: 5, radius: 8.6, phase: 0.55 },
    { count: 3, radius: 12.4, phase: 1.3 },
  ]
  const positions: THREE.Vector3[] = []
  ringSpecs.forEach((ring) => {
    for (let i = 0; i < ring.count; i += 1) {
      const a = ring.phase + (i / ring.count) * Math.PI * 2 + (Math.sin(i * 7.3) * 0.12)
      const r = ring.radius + Math.sin(i * 3.1) * 0.7
      positions.push(new THREE.Vector3(Math.cos(a) * r, Math.sin(a * 2 + i) * 0.04, Math.sin(a) * r))
    }
  })
  const all = [
    ...core.map((table, i) => ({ theme: ['valley', 'campfire', 'workshop'][i] as ThemeId, table })),
    ...decoThemes.map((theme, i) => ({ theme, table: decoTables[i] })),
  ]
  return all.map((entry, index) => ({
    theme: entry.theme,
    accent: THEMES[entry.theme].rim,
    table: entry.table,
    pos: positions[index] ?? new THREE.Vector3((index - 6) * 3.2, 0, 0),
    index,
  }))
})()

const isCore = (entry: Ent) => entry.table.entryMode === 'immersive'

/** shared mutable state between canvas and DOM (portals freeze props) */
const seaState = { index: 0, orbit: 0, drag: false, lastPointer: 0 }
const seaGlow = { x: 0.5, y: 0.4, on: false }

/* ------------------------------------------------------------- assets */

let radialGlowTexture: THREE.CanvasTexture | null = null
function getRadialGlow(): THREE.CanvasTexture {
  if (radialGlowTexture) return radialGlowTexture
  const canvas = document.createElement('canvas')
  canvas.width = 128
  canvas.height = 128
  const ctx = canvas.getContext('2d')
  if (ctx) {
    const g = ctx.createRadialGradient(64, 64, 4, 64, 64, 62)
    g.addColorStop(0, 'rgba(255,255,255,1)')
    g.addColorStop(0.35, 'rgba(255,255,255,0.35)')
    g.addColorStop(1, 'rgba(255,255,255,0)')
    ctx.fillStyle = g
    ctx.fillRect(0, 0, 128, 128)
  }
  radialGlowTexture = new THREE.CanvasTexture(canvas)
  return radialGlowTexture
}

function FogPlane({ position, opacity, color }: { position: [number, number, number]; opacity: number; color: string }) {
  const mat = useRef<THREE.MeshBasicMaterial>(null)
  useFrame(({ clock }) => {
    if (mat.current) mat.current.opacity = opacity + Math.sin(clock.elapsedTime * 0.16 + position[0]) * 0.045
  })
  return (
    <mesh position={position} rotation={[-Math.PI / 2, 0, 0]} renderOrder={4}>
      <planeGeometry args={[44, 44, 1, 1]} />
      <meshBasicMaterial ref={mat} color={color} transparent opacity={opacity} depthWrite={false} blending={THREE.AdditiveBlending} toneMapped={false} />
    </mesh>
  )
}

function GroundSea() {
  const geo = useMemo(() => {
    const g = new THREE.PlaneGeometry(120, 120)
    g.rotateX(-Math.PI / 2)
    return g
  }, [])
  return (
    <mesh geometry={geo} position={[0, -0.9, 0]}>
      <meshBasicMaterial color="#050911" />
    </mesh>
  )
}

function StarDust() {
  const [positions, colors] = useMemo(() => {
    const n = 640
    const p = new Float32Array(n * 3)
    const c = new Float32Array(n * 3)
    for (let i = 0; i < n; i += 1) {
      const r = 4 + Math.random() * 26
      const a = Math.random() * Math.PI * 2
      p[i * 3] = Math.cos(a) * r
      p[i * 3 + 1] = 0.4 + Math.random() * 4.4
      p[i * 3 + 2] = Math.sin(a) * r
      const warm = Math.random() < 0.4
      const b = 0.5 + Math.random() * 0.5
      c[i * 3] = warm ? 1.0 * b : 0.6 * b
      c[i * 3 + 1] = warm ? 0.82 * b : 0.72 * b
      c[i * 3 + 2] = warm ? 0.5 * b : 1.0 * b
    }
    return [p, c]
  }, [])
  return (
    <points>
      <bufferGeometry>
        <bufferAttribute attach="attributes-position" args={[positions, 3]} count={positions.length / 3} />
        <bufferAttribute attach="attributes-color" args={[colors, 3]} count={colors.length / 3} />
      </bufferGeometry>
      <pointsMaterial size={0.042} vertexColors transparent opacity={0.75} sizeAttenuation depthWrite={false} toneMapped={false} />
    </points>
  )
}

function SkyDome() {
  return (
    <mesh position={[0, 0, 0]} renderOrder={-1}>
      <sphereGeometry args={[48, 24, 16]} />
      <meshBasicMaterial color="#0a0f1c" side={THREE.BackSide} fog={false} />
    </mesh>
  )
}

/* ------------------------------------------------------------- mini world */

function MiniTable() {
  return (
    <group>
      <mesh position={[0, 0.16, 0]}>
        <cylinderGeometry args={[0.16, 0.13, 0.05, 10]} />
        <meshStandardMaterial color="#7a5a38" roughness={0.9} />
      </mesh>
      <mesh position={[0, 0.08, 0]}>
        <cylinderGeometry args={[0.04, 0.05, 0.14, 6]} />
        <meshStandardMaterial color="#4c3a26" roughness={1} />
      </mesh>
    </group>
  )
}

function MiniPeople({ count = 4 }: { count?: number }) {
  return (
    <group>
      {Array.from({ length: count }, (_, i) => {
        const a = i * 2.1
        return (
          <group key={i} position={[Math.cos(a) * 0.22, 0, Math.sin(a) * 0.22]} rotation={[0, a + Math.PI, 0]}>
            <mesh position={[0, 0.08, 0]}>
              <capsuleGeometry args={[0.035, 0.06, 3, 8]} />
              <meshStandardMaterial color="#9a8a74" roughness={0.9} />
            </mesh>
            <mesh position={[0, 0.17, 0]}>
              <sphereGeometry args={[0.038, 8, 8]} />
              <meshStandardMaterial color="#c9a47e" roughness={0.8} />
            </mesh>
          </group>
        )
      })}
    </group>
  )
}

function MiniFire({ color }: { color: string }) {
  const glow = useRef<THREE.Mesh>(null)
  useFrame(({ clock }) => {
    if (!glow.current) return
    const k = 1 + Math.sin(clock.elapsedTime * 9.2) * 0.1 + Math.sin(clock.elapsedTime * 23.7) * 0.06
    glow.current.scale.setScalar(k)
  })
  return (
    <group>
      <mesh position={[0, 0.02, 0]}>
        <cylinderGeometry args={[0.16, 0.13, 0.06, 8]} />
        <meshStandardMaterial color="#33302a" roughness={1} />
      </mesh>
      <mesh ref={glow} position={[0, 0.14, 0]}>
        <sphereGeometry args={[0.06, 8, 8]} />
        <meshStandardMaterial color={color} emissive={color} emissiveIntensity={2.6} toneMapped={false} />
      </mesh>
    </group>
  )
}

function MiniHouse({ roof = '#a05a42', glow = '#ffcf8a' }: { roof?: string; glow?: string }) {
  return (
    <group>
      <mesh position={[0.34, 0.2, -0.15]} castShadow>
        <boxGeometry args={[0.4, 0.3, 0.32]} />
        <meshStandardMaterial color="#6a5340" roughness={1} />
      </mesh>
      <mesh position={[0.34, 0.5, -0.15]} rotation={[0, Math.PI / 4, 0]} castShadow>
        <coneGeometry args={[0.4, 0.22, 4]} />
        <meshStandardMaterial color={roof} roughness={1} flatShading />
      </mesh>
      <mesh position={[0.45, 0.24, 0.01]}>
        <boxGeometry args={[0.07, 0.08, 0.02]} />
        <meshStandardMaterial color={glow} emissive={glow} emissiveIntensity={2.2} toneMapped={false} />
      </mesh>
    </group>
  )
}

function MiniTree({ position, color = '#3f5d46' }: { position: [number, number, number]; color?: string }) {
  return (
    <group position={position}>
      <mesh position={[0, 0.16, 0]}>
        <cylinderGeometry args={[0.03, 0.045, 0.26, 6]} />
        <meshStandardMaterial color="#3c2c1e" roughness={1} />
      </mesh>
      <mesh position={[0, 0.42, 0]}>
        <coneGeometry args={[0.18, 0.34, 7]} />
        <meshStandardMaterial color={color} roughness={1} flatShading />
      </mesh>
    </group>
  )
}

function MiniLamps({ color }: { color: string }) {
  return (
    <group>
      {[0.44, -0.44].map((z) => (
        <group key={z} position={[0, 0, z]}>
          <mesh position={[0, 0.16, 0]}>
            <cylinderGeometry args={[0.008, 0.01, 0.32, 5]} />
            <meshStandardMaterial color="#55402c" roughness={1} />
          </mesh>
          <mesh position={[0, 0.34, 0]}>
            <sphereGeometry args={[0.03, 6, 6]} />
            <meshStandardMaterial color={color} emissive={color} emissiveIntensity={2.4} toneMapped={false} />
          </mesh>
        </group>
      ))}
    </group>
  )
}

function MiniCanoe() {
  return (
    <group>
      <mesh position={[0.2, 0.03, 0]}>
        <boxGeometry args={[0.18, 0.03, 0.06]} />
        <meshStandardMaterial color="#7a5a38" roughness={1} />
      </mesh>
      <mesh position={[0.3, 0.2, 0]}>
        <cylinderGeometry args={[0.008, 0.008, 0.18, 5]} />
        <meshStandardMaterial color="#55402c" roughness={1} />
      </mesh>
    </group>
  )
}

function MiniWorld({ def, theme, focused }: { def: ThemeDef; theme: ThemeId; focused: boolean }) {
  const glow = useRef<THREE.Sprite>(null)
  const group = useRef<THREE.Group>(null)

  useFrame(({ clock }) => {
    if (!group.current) return
    group.current.position.y = Math.sin(clock.elapsedTime * 0.42 + def.ground.charCodeAt(0)) * 0.045
    if (glow.current) {
      const mat = glow.current.material as THREE.SpriteMaterial
      mat.opacity = THREE.MathUtils.damp(mat.opacity, focused ? 0.9 : 0.34, 4, 0.016)
      glow.current.scale.setScalar(THREE.MathUtils.damp(glow.current.scale.x, focused ? 4.6 : 3.0, 4, 0.016))
    }
  })

  const lampColor = new THREE.Color(def.lamp)
  return (
    <group ref={group}>
      <mesh position={[0, -0.06, 0]}>
        <cylinderGeometry args={[1.12, 1.32, 0.14, 20]} />
        <meshStandardMaterial color={def.ground} roughness={0.95} />
      </mesh>
      <mesh position={[0, 0.045, 0]}>
        <cylinderGeometry args={[1.12, 1.12, 0.02, 20]} />
        <meshStandardMaterial color={def.ground} roughness={1} emissive={lampColor} emissiveIntensity={focused ? 0.32 : 0.15} toneMapped={false} />
      </mesh>
      <mesh position={[0, 0.06, 0]} rotation={[-Math.PI / 2, 0, 0]}>
        <ringGeometry args={[1.05, 1.1, 28]} />
        <meshBasicMaterial color={def.rim} transparent opacity={focused ? 0.36 : 0.12} toneMapped={false} depthWrite={false} />
      </mesh>
      <group scale={1.22}>
      <MiniTable />
      <MiniPeople count={def.feature === 'fire' ? 5 : def.feature === 'house' || def.feature === 'shelf' ? 5 : 4} />
      {def.feature === 'fire' && <MiniFire color={def.lamp} />}
      {def.feature === 'house' && <MiniHouse roof={theme === 'snow' ? '#dde6f2' : undefined} glow={def.lamp} />}
      {def.feature === 'camping' && <MiniFire color={def.lamp} />}
      {def.feature === 'shelf' && <MiniHouse roof="#5a4534" glow={def.lamp} />}
      {def.feature === 'lamps' && <MiniLamps color={def.lamp} />}
      {def.feature === 'canoe' && <MiniCanoe />}
      </group>
      <MiniTree position={[0.52, 0, 0.44]} color={theme === 'autumn' ? '#8a5a30' : theme === 'snow' ? '#42586e' : '#3f5d46'} />
      <MiniTree position={[-0.6, 0, -0.28]} color="#37503f" />
      <sprite ref={glow} position={[0, 0.3, 0]} scale={[2.4, 2.4, 1]}>
        <spriteMaterial map={getRadialGlow()} color={def.lamp} transparent opacity={0.34} depthWrite={false} blending={THREE.AdditiveBlending} toneMapped={false} />
      </sprite>
      <pointLight position={[0, 0.9, 0]} color={def.lamp} intensity={focused ? 2.2 : 0.85} distance={4.2} decay={2} />
    </group>
  )
}

/* ------------------------------------------------------------- camera + scene */

function SeaCamera() {
  const { camera } = useThree()
  const lookAt = useRef(new THREE.Vector3())
  const focusPoint = useMemo(() => entries[seaState.index].pos.clone(), [])
  const current = useMemo(() => new THREE.Vector3(), [])
  const tween = useRef<gsap.core.Tween | null>(null)

  const moveTo = (index: number) => {
    tween.current?.kill()
    const next = entries[index]?.pos.clone() ?? focusPoint
    tween.current = gsap.to(focusPoint, { x: next.x, y: next.y, z: next.z, duration: 1.35, ease: 'power3.inOut' })
  }

  useEffect(() => () => { tween.current?.kill() }, [])
  useEffect(() => { moveTo(seaState.index) }, [])

  useFrame(({ clock, pointer }, delta) => {
    const entry = entries[seaState.index]
    if (!entry) return
    // slow auto-orbit + drag input
    if (!seaState.drag) seaState.orbit += delta * 0.05
    const r = 3.9
    const height = 2.05 + Math.sin(clock.elapsedTime * 0.24) * 0.16
    const angle = seaState.orbit
    current.set(
      focusPoint.x + Math.cos(angle) * r + pointer.x * 0.42,
      focusPoint.y + height + pointer.y * 0.22,
      focusPoint.z + Math.sin(angle) * r,
    )
    const l = 3.4
    camera.position.x = THREE.MathUtils.damp(camera.position.x, current.x, l, delta)
    camera.position.y = THREE.MathUtils.damp(camera.position.y, current.y, l, delta)
    camera.position.z = THREE.MathUtils.damp(camera.position.z, current.z, l, delta)
    lookAt.current.lerp(focusPoint.clone().add(new THREE.Vector3(0, 0.35, 0)), 1 - Math.exp(-5 * delta))
    camera.lookAt(lookAt.current)
    const projected = focusPoint.clone().add(new THREE.Vector3(0, 0.55, 0)).project(camera)
    seaGlow.x = projected.x * 0.5 + 0.5
    seaGlow.y = -projected.y * 0.5 + 0.5
    seaGlow.on = Math.abs(projected.x) < 1.2 && Math.abs(projected.y) < 1.2
  })
  return null
}

function SeaWorld() {
  const renderCounter = useMemo(() => ({ v: 0 }), [])
  useFrame(() => { renderCounter.v += 1 })
  return (
    <>
      <color attach="background" args={['#070b14']} />
      <fog attach="fog" args={['#0a0f1c', 7, 34]} />
      <SkyDome />
      <GroundSea />
      <StarDust />
      <FogPlane position={[0, -0.62, 0]} opacity={0.34} color="#3a4668" />
      <FogPlane position={[0, -0.74, 0]} opacity={0.26} color="#2c3a5c" />
      <hemisphereLight color="#4a5d9e" groundColor="#0d1220" intensity={0.5} />
      <directionalLight color="#a8bee8" intensity={0.22} position={[5, 9, 3]} />
      <ambientLight intensity={0.1} />
      {entries.map((entry) => (
        <group key={entry.index} position={[entry.pos.x, entry.pos.y, entry.pos.z]}>
          <MiniWorld def={THEMES[entry.theme]} theme={entry.theme} focused={entry.index === seaState.index} />
        </group>
      ))}
      <SeaCamera />
      <EffectComposer multisampling={0}>
        <Bloom mipmapBlur intensity={1.15} luminanceThreshold={0.82} luminanceSmoothing={0.24} radius={0.55} />
      </EffectComposer>
    </>
  )
}

/* ------------------------------------------------------------- DOM shell */

export default function TableSea({ onEnter, enhanced, phase, returnFocusId }: TableSeaProps) {
  const [index, setIndex] = useState(seaState.index)
  const cooldown = useRef(0)
  const mainRef = useRef<HTMLElement>(null)
  const glowRef = useRef<HTMLDivElement>(null)
  const seaActive = phase === 'gallery' || phase === 'lobby'
  const focused = entries[index] ?? entries[0]

  const switchTo = (target: number) => {
    if (!seaActive || target < 0 || target >= entries.length) return
    if (Date.now() < cooldown.current) return
    cooldown.current = Date.now() + 1100
    seaState.index = target
    setIndex(target)
  }

  useEffect(() => {
    document.documentElement.classList.add('sea-mode'); document.body.classList.add('sea-mode')
    return () => {
      document.documentElement.classList.remove('sea-mode', 'gallery-transition')
      document.body.classList.remove('sea-mode', 'gallery-transition')
    }
  }, [])
  useEffect(() => {
    document.documentElement.classList.toggle('gallery-transition', phase !== 'gallery' && phase !== 'lobby')
    document.body.classList.toggle('gallery-transition', phase !== 'gallery' && phase !== 'lobby')
  }, [phase])

  // pointer orbit drag
  useEffect(() => {
    if (!seaActive) return
    const down = (event: PointerEvent) => { seaState.drag = true; seaState.lastPointer = event.clientX }
    const move = (event: PointerEvent) => {
      if (!seaState.drag) return
      seaState.orbit += (event.clientX - seaState.lastPointer) * 0.004
      seaState.lastPointer = event.clientX
    }
    const up = () => { seaState.drag = false }
    window.addEventListener('pointerdown', down)
    window.addEventListener('pointermove', move)
    window.addEventListener('pointerup', up)
    return () => {
      window.removeEventListener('pointerdown', down)
      window.removeEventListener('pointermove', move)
      window.removeEventListener('pointerup', up)
    }
  }, [seaActive])

  const onWheel = (event: React.WheelEvent) => {
    if (!seaActive) return
    if (Math.abs(event.deltaY) > 40) switchTo(index + (event.deltaY > 0 ? 1 : -1))
  }
  const onKey = (event: React.KeyboardEvent) => {
    if (event.key === 'ArrowRight' || event.key === 'ArrowDown') switchTo(index + 1)
    else if (event.key === 'ArrowLeft' || event.key === 'ArrowUp') switchTo(index - 1)
  }

  useLayoutEffect(() => {
    if (phase !== 'gallery' || !returnFocusId) return
    const btn = document.querySelector<HTMLElement>(`[data-table-id="${CSS.escape(returnFocusId)}"]`)
    btn?.focus({ preventScroll: true })
  }, [phase, returnFocusId])

  useEffect(() => {
    let raf = 0
    const apply = () => {
      raf = requestAnimationFrame(apply)
      const el = glowRef.current
      if (!el) return
      el.style.left = `${seaGlow.x * 100}%`
      el.style.top = `${seaGlow.y * 100}%`
      el.style.opacity = seaGlow.on ? '1' : '0'
    }
    raf = requestAnimationFrame(apply)
    return () => cancelAnimationFrame(raf)
  }, [])

  const enter = () => {
    if (!isCore(focused) || !seaActive) return
    onEnter(focused.table, { left: 0, top: 0, width: window.innerWidth, height: window.innerHeight })
  }
  const theme = THEMES[focused.theme]
  const style = { '--sea-accent': theme.rim } as CSSProperties

  return (
    <main ref={mainRef} className={`sea-page ${enhanced ? 'is-enhanced' : ''}`} style={style} role="region" aria-label="正在发生的桌海" tabIndex={-1} onWheel={onWheel} onKeyDown={onKey} inert={!seaActive}>
      <div className="sea-vignette" aria-hidden="true" />
      <div ref={glowRef} className="sea-focus-glow" aria-hidden="true" />
      {enhanced && seaActive && <UseCanvas><SeaWorld /></UseCanvas>}

      <header className="sea-header">
        <div className="sea-brand"><b>组一桌</b><span>把值得聊的话，交给刚好在场的人</span></div>
        <em>ZH · 2026</em>
      </header>

      <section className="sea-copy" aria-live="polite">
        <p className="sea-kicker"><span>{String(index + 1).padStart(2, '0')}</span>{theme.label}</p>
        {isCore(focused) ? (
          <>
            <h2>{focused.table.hook}</h2>
            <p className="sea-missing">{focused.table.missingPerspective}</p>
            {focused.table.recommendedBecause && <p className="sea-recommend">{focused.table.recommendedBecause}</p>}
            <button className="sea-cta" type="button" data-table-id={focused.table.id} onClick={enter} disabled={!seaActive}>坐下来看看 <i>→</i></button>
          </>
        ) : (
          <>
            <h2>{theme.label}</h2>
            <p className="sea-missing">正在等合适的人坐进来。</p>
          </>
        )}
      </section>

      <footer className="sea-footer">
        <span>{theme.label}</span>
        <div className="sea-dots">
          {entries.map((entry, dot) => (
            <button key={entry.index} type="button" className={dot === index ? 'is-active' : ''} aria-label={THEMES[entry.theme].label} onClick={() => switchTo(dot)} disabled={!seaActive} />
          ))}
        </div>
        <span>{String(index + 1).padStart(2, '0')} / {String(entries.length).padStart(2, '0')}</span>
      </footer>
    </main>
  )
}
