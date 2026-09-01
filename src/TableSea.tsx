import { UseCanvas } from '@14islands/r3f-scroll-rig'
import { useGLTF } from '@react-three/drei'
import { EffectComposer, Bloom } from '@react-three/postprocessing'
import { useFrame, useThree } from '@react-three/fiber'
import gsap from 'gsap'
import { Suspense, useEffect, useMemo, useRef, useLayoutEffect, useState, type CSSProperties } from 'react'
import * as THREE from 'three'
import { galleryTables, worldLabel, type AppPhase, type TableSummary } from './domain'
import { GltfFit, SEA_MODEL_PATHS } from './sea/models'
import { SeaGrass } from './sea/seaGrass'
import { applyBrunoStyle, updateBrunoShared } from './sea/brunoMaterial'
import './gallery.css'

export interface GalleryMediaRect { left: number; top: number; width: number; height: number }

for (const path of SEA_MODEL_PATHS) useGLTF.preload(path)

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
  // one continent: clusters spread over a large organic field
  const clump = [
    [0, 0], [0.55, 0.35], [-0.5, 0.4], [0.5, -0.42], [-0.55, -0.35],
    [0, 0.62], [0.62, 0], [-0.62, 0], [0, -0.62], [0.35, 0.35],
    [-0.35, 0.35], [0.35, -0.35], [-0.35, -0.35],
  ]
  const positions = clump.map(([x, z], i) => {
    const a2 = (i * 2.399963) // golden angle spiral jitter
    return new THREE.Vector3(
      x * 12 + Math.sin(a2) * 1.7,
      0,
      z * 12 + Math.cos(a2) * 1.7,
    )
  })
  const all = [
    ...core.map((table, i) => ({ theme: ['valley', 'campfire', 'workshop'][i] as ThemeId, table })),
    ...decoThemes.map((theme, i) => ({ theme, table: decoTables[i] })),
  ]
  return all.map((entry, index) => {
    const base = positions[index] ?? new THREE.Vector3((index - 6) * 3.2, 0, 0)
    return {
      theme: entry.theme,
      accent: THEMES[entry.theme].rim,
      table: entry.table,
      pos: new THREE.Vector3(base.x, groundHeight(base.x, base.z) + 0.08, base.z),
      index,
    }
  })
})()

const isCore = (entry: Ent) => entry.table.entryMode === 'immersive'

/** shared mutable state between canvas and DOM (portals freeze props) */
const seaState = { index: 0, orbit: 0.85, drag: false, lastPointer: 0 }
const seaGlow = { x: 0.5, y: 0.4, on: false }
const clusterY = (x: number, z: number) => 0.1

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

function groundHeight(x: number, z: number): number {
  const n =
    Math.sin(x * 0.16) * Math.cos(z * 0.14) * 0.9 +
    Math.sin(x * 0.05 + z * 0.07) * 1.4 +
    Math.cos(x * 0.31 - z * 0.24) * 0.3
  const edge = THREE.MathUtils.smoothstep(Math.sqrt(x * x + z * z), 20, 30)
  return n - 1.1 - edge * 2.4
}

function SeaTerrain() {
  const geometry = useMemo(() => {
    const geo = new THREE.PlaneGeometry(78, 78, 130, 130)
    geo.rotateX(-Math.PI / 2)
    const pos = geo.attributes.position as THREE.BufferAttribute
    const colors = new Float32Array(pos.count * 3)
    const grassA = new THREE.Color('#79a86d')
    const grassB = new THREE.Color('#5d8a55')
    const sand = new THREE.Color('#c9b98a')
    const rock = new THREE.Color('#8e98a8')
    const color = new THREE.Color()
    for (let i = 0; i < pos.count; i += 1) {
      const x = pos.getX(i)
      const z = pos.getZ(i)
      const y = groundHeight(x, z)
      pos.setY(i, y)
      const n = (Math.sin(x * 1.3) + Math.cos(z * 1.7)) * 0.5 + 0.5
      color.copy(grassA).lerp(grassB, n * 0.55)
      if (y > 0.25) color.lerp(rock, THREE.MathUtils.clamp((y - 0.25) / 2.0, 0, 0.75))
      if (y < -0.4) color.lerp(sand, THREE.MathUtils.clamp((-0.4 - y) / 0.7, 0, 1))
      colors[i * 3] = color.r
      colors[i * 3 + 1] = color.g
      colors[i * 3 + 2] = color.b
    }
    geo.setAttribute('color', new THREE.BufferAttribute(colors, 3))
    geo.computeVertexNormals()
    return geo
  }, [])
  const terrainMaterial = useMemo(() => {
    const material = new THREE.MeshLambertMaterial({ vertexColors: true, flatShading: true })
    applyBrunoStyle(material)
    return material
  }, [])
  return (
    <mesh geometry={geometry} material={terrainMaterial} receiveShadow>
    </mesh>
  )
}

function SeaWater() {
  const mat = useRef<THREE.ShaderMaterial>(null)
  const uniforms = useMemo(() => ({ uTime: { value: 0 } }), [])
  useFrame(({ clock }) => {
    if (mat.current) mat.current.uniforms.uTime.value = clock.elapsedTime
  })
  return (
    <mesh position={[-7, -0.52, -6]} rotation={[-Math.PI / 2, 0, 0]} scale={[18, 12, 1]}>
      <planeGeometry args={[1, 1, 48, 32]} />
      <shaderMaterial
        ref={mat}
        uniforms={uniforms}
        transparent
        vertexShader="uniform float uTime; varying vec3 vW; void main(){ vec4 w = modelMatrix * vec4(position,1.); w.y += sin(w.x*1.3+uTime*1.2)*0.03 + cos(w.z*1.7+uTime*0.9)*0.025; vW = w.xyz; gl_Position = projectionMatrix * viewMatrix * w; }"
        fragmentShader="uniform float uTime; varying vec3 vW; void main(){ vec3 deep = vec3(0.28,0.5,0.62); vec3 shallow = vec3(0.55,0.72,0.74); float d = clamp((vW.y + 0.7) / 1.2, 0.0, 1.0); vec3 c = mix(deep, shallow, d); c += 0.03 * sin(vW.x*6.0 + uTime*2.1); gl_FragColor = vec4(c, 0.92); #include <tonemapping_fragment> #include <colorspace_fragment> }"
      />
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
      <pointsMaterial size={0.042} vertexColors transparent opacity={0.35} sizeAttenuation depthWrite={false} toneMapped={false} />
    </points>
  )
}

function Pollen() {
  const ref = useRef<THREE.Points>(null)
  const [positions] = useMemo(() => {
    const n = 240
    const arr = new Float32Array(n * 3)
    for (let i = 0; i < n; i += 1) {
      const a = Math.random() * Math.PI * 2
      const r = 2 + Math.random() * 18
      arr[i * 3] = Math.cos(a) * r
      arr[i * 3 + 1] = 0.2 + Math.random() * 3.6
      arr[i * 3 + 2] = Math.sin(a) * r
    }
    return [arr]
  }, [])
  useFrame(({ clock }) => {
    if (!ref.current) return
    ref.current.rotation.y = clock.elapsedTime * 0.012
  })
  return (
    <points ref={ref}>
      <bufferGeometry>
        <bufferAttribute attach="attributes-position" args={[positions, 3]} count={positions.length / 3} />
      </bufferGeometry>
      <pointsMaterial size={0.05} color="#fff2cf" transparent opacity={0.55} sizeAttenuation depthWrite={false} toneMapped={false} />
    </points>
  )
}

function SkyDome() {
  const uniforms = useMemo(() => ({}), [])
  return (
    <mesh position={[0, 0, 0]} renderOrder={-1}>
      <sphereGeometry args={[54, 28, 18]} />
      <shaderMaterial
        uniforms={uniforms}
        side={THREE.BackSide}
        depthWrite={false}
        fog={false}
        vertexShader="varying vec3 vWorld; void main(){ vWorld = (modelMatrix * vec4(position,1.)).xyz; gl_Position = projectionMatrix * modelViewMatrix * vec4(position,1.); }"
        fragmentShader={`varying vec3 vWorld;
        void main(){
          float h = clamp(vWorld.y / 30.0 + 0.18, 0.0, 1.0);
          vec3 top = vec3(0.30, 0.52, 0.78);
          vec3 mid = vec3(0.52, 0.70, 0.84);
          vec3 horizon = vec3(0.96, 0.78, 0.55);
          vec3 warm = vec3(0.99, 0.85, 0.60);
          vec3 col = h > 0.5 ? mix(mid, top, (h - 0.5) / 0.5) : mix(mix(warm, horizon, smoothstep(0.0, 0.14, h)), mid, h / 0.5);
          gl_FragColor = vec4(col, 1.0);
          #include <tonemapping_fragment>
          #include <colorspace_fragment>
        }`}
      />
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
      glow.current.scale.setScalar(THREE.MathUtils.damp(glow.current.scale.x, focused ? 9.4 : 6.2, 4, 0.016))
    }
  })

  const lampColor = new THREE.Color(def.lamp)
  return (
    <group ref={group}>
      <mesh position={[0, 0.02, 0]} receiveShadow>
        <circleGeometry args={[2.55, 26]} />
        <meshStandardMaterial color={def.ground} roughness={1} emissive={lampColor} emissiveIntensity={focused ? 0.5 : 0.3} toneMapped={false} />
      </mesh>
      <mesh position={[0, 0.04, 0]} rotation={[-Math.PI / 2, 0, 0]}>
        <ringGeometry args={[2.4, 2.5, 32]} />
        <meshBasicMaterial color={def.rim} transparent opacity={focused ? 0.3 : 0.1} toneMapped={false} depthWrite={false} />
      </mesh>
      <group scale={2.45}>
      <MiniTable />
      <MiniPeople count={def.feature === 'fire' ? 5 : def.feature === 'house' || def.feature === 'shelf' ? 5 : 4} />
      {theme === 'campfire' && (<>
        <GltfFit src="/assets/sea/campfire.glb" height={0.18} position={[0.1, 0.02, 0.15]} tint="#ff8a2a" />
        <GltfFit src="/assets/sea/kenney/campfire_logs.glb" height={0.1} position={[-0.05, 0.02, 0.1]} tint="#ffb37a" />
      </>)}
      {theme === 'valley' && (<>
        <GltfFit src="/assets/sea/cabin.glb" height={0.52} position={[-0.42, 0.02, -0.42]} rotation={[0, 0.6, 0]} tint="#ffcf8a" />
        <GltfFit src="/assets/sea/pine.glb" height={0.44} position={[0.55, 0.02, 0.6]} rotation={[0, 2.1, 0]} />
      </>)}
      {theme === 'workshop' && (<>
        <GltfFit src="/assets/sea/cabin.glb" height={0.5} position={[-0.48, 0.02, -0.35]} rotation={[0, 1.2, 0]} tint="#ffd28d" />
        <GltfFit src="/assets/sea/lamp.glb" height={0.32} position={[0.5, 0.02, 0.52]} tint="#ffd28d" />
      </>)}
      {theme === 'rooftop' && (<>
        <GltfFit src="/assets/sea/skyline.glb" height={0.58} position={[-0.15, 0.02, -0.3]} rotation={[0, -0.5, 0]} tint="#b9c4ff" />
        <GltfFit src="/assets/sea/umbrella.glb" height={0.34} position={[0.52, 0.02, 0.5]} rotation={[0, 1.4, 0]} tint="#b9c4ff" />
      </>)}
      {theme === 'bookstore' && (<>
        <GltfFit src="/assets/sea/bookshelf.glb" height={0.55} position={[-0.55, 0.02, 0.1]} rotation={[0, 1.57, 0]} tint="#ffd7b0" />
        <GltfFit src="/assets/sea/lamp.glb" height={0.3} position={[0.55, 0.02, 0.2]} tint="#ffc9a0" />
      </>)}
      {theme === 'pier' && (<>
        <GltfFit src="/assets/sea/pier.glb" height={0.16} position={[0, 0.02, -0.3]} rotation={[0, 1.5, 0]} tint="#8fd4e8" />
        <GltfFit src="/assets/sea/canoe.glb" height={0.12} position={[0.2, 0.02, 0.4]} rotation={[0, -0.8, 0]} tint="#8fd4e8" />
      </>)}
      {theme === 'snow' && (<>
        <GltfFit src="/assets/sea/cabin.glb" height={0.5} position={[-0.35, 0.02, -0.45]} rotation={[0, 0.4, 0]} tint="#bcd6ff" />
        <GltfFit src="/assets/sea/pine.glb" height={0.42} position={[0.6, 0.02, 0.5]} rotation={[0, 3.4, 0]} tint="#cfe6ff" />
      </>)}
      {theme === 'forest' && (<>
        <GltfFit src="/assets/sea/fire.glb" height={0.16} position={[0.05, 0.02, 0.1]} tint="#ff8a2a" />
        <GltfFit src="/assets/sea/pine.glb" height={0.46} position={[0.55, 0.02, 0.62]} rotation={[0, 1.1, 0]} />
        <GltfFit src="/assets/sea/pine.glb" height={0.34} position={[-0.62, 0.02, -0.4]} rotation={[0, 4.2, 0]} />
      </>)}
      {theme === 'cafe' && (<>
        <GltfFit src="/assets/sea/cafe.glb" height={0.5} position={[-0.45, 0.02, -0.4]} rotation={[0, 1.1, 0]} tint="#ffd9a8" />
        <GltfFit src="/assets/sea/umbrella.glb" height={0.3} position={[0.55, 0.02, 0.48]} rotation={[0, 2.6, 0]} tint="#e8c9a0" />
      </>)}
      {theme === 'rain' && (<>
        <GltfFit src="/assets/sea/lamp.glb" height={0.34} position={[0.42, 0.02, 0.5]} tint="#9fb8e0" />
        <GltfFit src="/assets/sea/lantern.glb" height={0.12} position={[-0.42, 0.02, 0.56]} tint="#a8c0e8" />
      </>)}
      {theme === 'autumn' && (<>
        <GltfFit src="/assets/sea/autumn-tree.glb" height={0.52} position={[0.3, 0.02, 0.2]} rotation={[0, 1.8, 0]} tint="#ffc98a" />
        <GltfFit src="/assets/sea/kenney/log_stack.glb" height={0.1} position={[-0.55, 0.02, -0.42]} tint="#ffb37a" />
      </>)}
      {theme === 'desert' && (<>
        <GltfFit src="/assets/sea/tent.glb" height={0.4} position={[-0.35, 0.02, -0.3]} rotation={[0, 0.7, 0]} tint="#e8b06a" />
        <GltfFit src="/assets/sea/kenney/rock_smallA.glb" height={0.1} position={[0.6, 0.02, 0.42]} />
      </>)}
      {theme === 'lake' && (<>
        <GltfFit src="/assets/sea/canoe.glb" height={0.13} position={[0.3, 0.02, 0.3]} rotation={[0, -1.2, 0]} tint="#9ac6b8" />
        <GltfFit src="/assets/sea/fishing-rod.glb" height={0.05} position={[0.15, 0.04, 0.42]} rotation={[0, 3.6, 0]} tint="#9ac6b8" />
        <GltfFit src="/assets/sea/lantern.glb" height={0.11} position={[-0.62, 0.02, 0.2]} tint="#9ac6b8" />
      </>)}
      {(['campfire', 'valley', 'snow', 'forest', 'desert', 'lake'] as ThemeId[]).includes(theme) && (<>
        <GltfFit src="/assets/sea/kenney/grass.glb" height={0.06} position={[0.72, 0.02, -0.42]} />
        <GltfFit src="/assets/sea/kenney/rock_smallB.glb" height={0.07} position={[-0.72, 0.02, -0.2]} />
      </>)}
      {(['valley', 'workshop', 'cafe', 'snow', 'autumn'] as ThemeId[]).includes(theme) && (
        <GltfFit src="/assets/sea/kenney/fence_simple.glb" height={0.3} position={[-0.85, 0.02, 0.78]} rotation={[0, 0.9, 0]} />
      )}
      {(['campfire', 'forest', 'desert', 'lake'] as ThemeId[]).includes(theme) && (
        <GltfFit src="/assets/sea/kenney/flower_redA.glb" height={0.1} position={[0.9, 0.02, -0.75]} rotation={[0, 1.4, 0]} />
      )}
      {theme === 'valley' && <GltfFit src="/assets/sea/kenney/flower_yellowA.glb" height={0.09} position={[-0.95, 0.02, 0.55]} rotation={[0, 2.2, 0]} />}
      {theme === 'bookstore' && <GltfFit src="/assets/sea/kenney/flower_purpleA.glb" height={0.09} position={[0.9, 0.02, 0.5]} rotation={[0, 0.6, 0]} />}
      {theme === 'forest' && <GltfFit src="/assets/sea/kenney/mushroom_redGroup.glb" height={0.12} position={[-0.9, 0.02, 0.7]} />}
      {theme === 'pier' && <GltfFit src="/assets/sea/kenney/lily_small.glb" height={0.06} position={[0.2, 0.02, 1.1]} />}
      <GltfFit src="/assets/sea/kenney/grass.glb" height={0.09} position={[0.6, 0.02, 0.95]} />
      <GltfFit src="/assets/sea/kenney/grass_large.glb" height={0.12} position={[-0.6, 0.02, -0.95]} rotation={[0, 2.9, 0]} />
      </group>
      <sprite ref={glow} position={[0, 0.62, 0]} scale={[5.2, 5.2, 1]}>
        <spriteMaterial map={getRadialGlow()} color={def.lamp} transparent opacity={0.34} depthWrite={false} blending={THREE.AdditiveBlending} toneMapped={false} />
      </sprite>
      <pointLight position={[0, 1.9, 0]} color={def.lamp} intensity={focused ? 4.6 : 1.7} distance={8.5} decay={2} />
    </group>
  )
}

/* ------------------------------------------------------------- camera + scene */

function SeascapeScatter() {
  const spots = useMemo(() => {
    type Spot = { x: number; z: number; kind: number; s: number; rot: number }
    const out: Spot[] = []
    const nearCluster = (x: number, z: number) => entries.some((e) => Math.hypot(e.pos.x - x, e.pos.z - z) < 3.4)
    for (let i = 0; i < 150; i += 1) {
      const a = i * 2.399963
      const r = 4 + (i % 23) / 23 * 22
      const x = Math.cos(a) * r
      const z = Math.sin(a) * r
      if (nearCluster(x, z)) continue
      if (groundHeight(x, z) < -0.45) continue
      if (groundHeight(x, z) > 2.6) continue
      out.push({ x, z, kind: i % 10, s: 0.7 + ((i * 13) % 10) / 18, rot: (i * 1.7) % (Math.PI * 2) })
    }
    return out
  }, [])
  return (
    <group>
      {spots.map((sp, i) => (
        <group key={i} position={[sp.x, groundHeight(sp.x, sp.z) + 0.02, sp.z]} rotation={[0, sp.rot, 0]} scale={sp.s}>
          {sp.kind < 4 && <GltfFit src="/assets/sea/pine.glb" height={1.1} />}
          {sp.kind === 4 && <GltfFit src="/assets/sea/autumn-tree.glb" height={1.2} />}
          {sp.kind === 5 && <GltfFit src="/assets/sea/kenney/tree_small.glb" height={0.9} />}
          {sp.kind === 6 && <GltfFit src="/assets/sea/kenney/rock_smallB.glb" height={0.3} />}
          {sp.kind === 7 && <GltfFit src="/assets/sea/kenney/grass_large.glb" height={0.25} />}
          {sp.kind === 8 && <GltfFit src="/assets/sea/kenney/flower_yellowA.glb" height={0.18} />}
          {sp.kind === 9 && <GltfFit src="/assets/sea/kenney/flower_redA.glb" height={0.18} />}
        </group>
      ))}
    </group>
  )
}

function TravelOrb() {
  const orb = useRef<THREE.Mesh>(null)
  const light = useRef<THREE.PointLight>(null)
  useFrame((_, delta) => {
    if (!orb.current || !light.current) return
    const entry = entries[seaState.index]
    if (!entry) return
    const k = 1 - Math.exp(-2.2 * delta)
    orb.current.position.lerp(new THREE.Vector3(entry.pos.x, entry.pos.y + 1.5, entry.pos.z), k)
    light.current.position.copy(orb.current.position)
  })
  return (
    <>
      <mesh ref={orb}>
        <sphereGeometry args={[0.12, 12, 10]} />
        <meshBasicMaterial color="#fff4d8" toneMapped={false} />
      </mesh>
      <pointLight ref={light} color="#ffe3a4" intensity={3.2} distance={10} decay={2} />
    </>
  )
}

function SeaCamera({ focusPoint }: { focusPoint: THREE.Vector3 }) {
  const { camera } = useThree()
  const lookAt = useRef(new THREE.Vector3())
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
    const r = 6.8
    const height = 2.6 + Math.sin(clock.elapsedTime * 0.24) * 0.16
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
    lookAt.current.lerp(focusPoint.clone().add(new THREE.Vector3(0, 0.85, 0)), 1 - Math.exp(-5 * delta))
    camera.lookAt(lookAt.current)
    const projected = focusPoint.clone().add(new THREE.Vector3(0, 0.55, 0)).project(camera)
    seaGlow.x = projected.x * 0.5 + 0.5
    seaGlow.y = -projected.y * 0.5 + 0.5
    seaGlow.on = Math.abs(projected.x) < 1.2 && Math.abs(projected.y) < 1.2
  })
  return null
}

function SeaWorld() {
  const focusPoint = useMemo(() => entries[seaState.index].pos.clone(), [])
  useFrame(({ clock }) => {
    updateBrunoShared(clock.elapsedTime)
  })
  return (
    <>
      <color attach="background" args={['#070b14']} />
      <fog attach="fog" args={['#aebcc8', 12, 46]} />
      <SkyDome />
      <SeaTerrain />
      <SeaWater />
      <StarDust />
      <Pollen />
      <SeascapeScatter />
      <FogPlane position={[0, -0.62, 0]} opacity={0.3} color="#cdd8e4" />
      <FogPlane position={[0, -0.74, 0]} opacity={0.24} color="#bccadb" />
      <hemisphereLight color="#d8e8f8" groundColor="#8a9278" intensity={1.05} />
      <directionalLight
        color="#ffe8bd"
        intensity={1.55}
        position={[9, 14, 7]}
        castShadow
        shadow-mapSize-width={1024}
        shadow-mapSize-height={1024}
        shadow-camera-left={-16}
        shadow-camera-right={16}
        shadow-camera-top={16}
        shadow-camera-bottom={-16}
        shadow-camera-near={2}
        shadow-camera-far={38}
      />
      <directionalLight color="#ffcf9e" intensity={0.28} position={[-7, 8, -5]} />
      <ambientLight intensity={0.22} />
      <Suspense fallback={null}>
        {entries.map((entry) => (
          <group key={entry.index} position={[entry.pos.x, entry.pos.y, entry.pos.z]}>
            <MiniWorld def={THEMES[entry.theme]} theme={entry.theme} focused={entry.index === seaState.index} />
          </group>
        ))}
      </Suspense>
      <TravelOrb />
      {false && <SeaGrass focus={focusPoint as any} wind={0.35} />}
      <SeaCamera focusPoint={focusPoint} />
      <EffectComposer multisampling={0}>
        <Bloom mipmapBlur intensity={0.9} luminanceThreshold={0.75} luminanceSmoothing={0.22} radius={0.5} />
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

  if (!seaActive) return null

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
