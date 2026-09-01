import { useFrame, useThree } from '@react-three/fiber'
import { useMemo, useRef } from 'react'
import * as THREE from 'three'
import { humanActors, tableHost, type ActorId } from './actors'

export type DioramaPhase = 'discovering' | 'approaching' | 'seated'

export interface DioramaProps {
  phase: DioramaPhase
  activeActorId: ActorId
  hoveredActorId: ActorId | null
  reducedMotion: boolean
}

/* ---------------------------------------------------------------- layout */

export const TABLE_POS = new THREE.Vector3(4.2, 0, 2.2)
const SEAT_RADIUS = 1.72
const SEAT_ANGLE: Record<string, number> = {
  'seat-south': 0,
  'seat-east': 60,
  'seat-northeast': 120,
  'seat-north': 180,
  'seat-northwest': 240,
  'seat-west': 300,
}
const seatPos = (seatId: string, radius = SEAT_RADIUS) => {
  const a = (SEAT_ANGLE[seatId] ?? 0) * (Math.PI / 180)
  return new THREE.Vector3(TABLE_POS.x + Math.sin(a) * radius, 0, TABLE_POS.z + Math.cos(a) * radius)
}
const seatOf = (id: ActorId | 'viewer'): string => {
  if (id === 'viewer') return 'seat-south'
  if (id === 'table-host') return tableHost.seatId
  return humanActors.find((actor) => actor.id === id)?.seatId ?? 'seat-north'
}
const accentOf = (id: ActorId | 'viewer'): string => {
  if (id === 'viewer') return '#ffd58c'
  if (id === 'table-host') return '#ddd6c4'
  return humanActors.find((actor) => actor.id === id)?.accent ?? '#c8b9a2'
}

/** Live screen anchors (percent) consumed by the DOM hotspot layer. */
export const actorAnchors: Partial<Record<ActorId | 'viewer', { x: number; y: number }>> = {}

/* ---------------------------------------------------------------- terrain */

const SHORE = (z: number) => 1.4 + Math.sin(z * 0.32) * 1.15

function Terrain() {
  const geometry = useMemo(() => {
    const geo = new THREE.PlaneGeometry(30, 22, 100, 76)
    geo.rotateX(-Math.PI / 2)
    const pos = geo.attributes.position as THREE.BufferAttribute
    const colors = new Float32Array(pos.count * 3)
    const grassA = new THREE.Color('#7fae6a')
    const grassB = new THREE.Color('#57844c')
    const sand = new THREE.Color('#c9b483')
    const hill = new THREE.Color('#6d9459')
    const color = new THREE.Color()
    const probe = new THREE.Vector3()
    for (let i = 0; i < pos.count; i += 1) {
      const x = pos.getX(i) + TABLE_POS.x
      const z = pos.getZ(i) + TABLE_POS.z
      const shore = SHORE(z)
      const inland = THREE.MathUtils.clamp((x - shore) / 3.2, 0, 1)
      let y: number
      if (inland <= 0) {
        y = -1.15
      } else {
        const roll = Math.sin(x * 0.55 + z * 0.4) * 0.16 + Math.cos(z * 0.62 - x * 0.3) * 0.12
        const hillLift = Math.max(0, (x - 12.5) * 0.42) + Math.max(0, (-z - 7.5) * 0.5)
        y = THREE.MathUtils.lerp(0.06, 0.42 + roll, inland) + hillLift
        probe.set(x, 0, z)
        const flat = 1 - THREE.MathUtils.smoothstep(TABLE_POS.distanceTo(probe), 2.1, 4.4)
        y = THREE.MathUtils.lerp(y, 0.12, flat)
      }
      pos.setX(i, x)
      pos.setZ(i, z)
      pos.setY(i, y)
      const n = (Math.sin(x * 1.7) + Math.cos(z * 2.1)) * 0.5 + 0.5
      color.copy(grassA).lerp(grassB, inland * 0.55 + n * 0.2)
      if (inland > 0 && y < 0.32) color.lerp(sand, 1 - THREE.MathUtils.clamp((y - 0.05) / 0.32, 0, 1))
      if (y > 1.1) color.lerp(hill, THREE.MathUtils.clamp((y - 1.1) / 1.6, 0, 1))
      colors[i * 3] = color.r
      colors[i * 3 + 1] = color.g
      colors[i * 3 + 2] = color.b
    }
    geo.setAttribute('color', new THREE.BufferAttribute(colors, 3))
    geo.computeVertexNormals()
    return geo
  }, [])
  return (
    <mesh geometry={geometry} receiveShadow>
      <meshStandardMaterial vertexColors roughness={0.95} metalness={0} />
    </mesh>
  )
}

/* ---------------------------------------------------------------- water */

const WATER_VERT = `
  uniform float uTime;
  uniform float uAmp;
  varying vec3 vWorld;
  varying float vWave;
  void main(){
    vec4 world = modelMatrix * vec4(position, 1.0);
    float w = sin(world.x * 1.25 + uTime * 1.15) * 0.05 + cos(world.z * 1.7 + uTime * 0.8) * 0.042;
    world.y += w * uAmp;
    vWave = w;
    vWorld = world.xyz;
    gl_Position = projectionMatrix * viewMatrix * world;
  }
`
const WATER_FRAG = `
  uniform float uTime;
  varying vec3 vWorld;
  varying float vWave;
  void main(){
    vec3 deep = vec3(0.196, 0.384, 0.443);
    vec3 shallow = vec3(0.424, 0.639, 0.616);
    float depth = clamp((vWorld.x + 2.0) / -14.0, 0.0, 1.0);
    vec3 col = mix(shallow, deep, depth);
    col += vWave * 0.35;
    float glint = step(0.985, fract(sin(dot(floor(vWorld.xz * 6.0), vec2(12.9898, 78.233))) * 43758.5453 + uTime * 0.6));
    col += glint * 0.35;
    float shore = smoothstep(-1.0, 2.4, vWorld.x);
    col = mix(col, vec3(0.83, 0.76, 0.58), shore * 0.55);
    gl_FragColor = vec4(col, 0.94);
    #include <tonemapping_fragment>
    #include <colorspace_fragment>
  }
`

function Water({ reducedMotion }: { reducedMotion: boolean }) {
  const material = useRef<THREE.ShaderMaterial>(null)
  const uniforms = useMemo(() => ({ uTime: { value: 0 }, uAmp: { value: reducedMotion ? 0 : 1 } }), [reducedMotion])
  useFrame(({ clock }) => {
    if (material.current) material.current.uniforms.uTime.value = clock.elapsedTime
  })
  return (
    <mesh position={[-8, -0.24, 1]} rotation={[-Math.PI / 2, 0, 0]} renderOrder={1}>
      <planeGeometry args={[44, 26, 72, 48]} />
      <shaderMaterial ref={material} uniforms={uniforms} vertexShader={WATER_VERT} fragmentShader={WATER_FRAG} transparent />
    </mesh>
  )
}

/* ---------------------------------------------------------------- sky */

const SKY_VERT = `
  varying vec3 vWorld;
  void main(){
    vWorld = (modelMatrix * vec4(position, 1.0)).xyz;
    gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
  }
`
const SKY_FRAG = `
  varying vec3 vWorld;
  void main(){
    float h = clamp(vWorld.y / 26.0 + 0.18, 0.0, 1.0);
    vec3 top = vec3(0.475, 0.639, 0.769);
    vec3 mid = vec3(0.741, 0.812, 0.792);
    vec3 horizon = vec3(0.898, 0.839, 0.686);
    vec3 col = h > 0.45 ? mix(mid, top, (h - 0.45) / 0.55) : mix(horizon, mid, h / 0.45);
    gl_FragColor = vec4(col, 1.0);
    #include <tonemapping_fragment>
    #include <colorspace_fragment>
  }
`

function SkyDome() {
  return (
    <mesh position={[2, 2, -6]} renderOrder={-1}>
      <sphereGeometry args={[56, 24, 16]} />
      <shaderMaterial vertexShader={SKY_VERT} fragmentShader={SKY_FRAG} side={THREE.BackSide} depthWrite={false} fog={false} />
    </mesh>
  )
}

/* ---------------------------------------------------------------- backdrop */

function BackdropPlate() {
  const texture = useMemo(() => {
    const tex = new THREE.TextureLoader().load('/assets/valley-world-clean.png')
    tex.colorSpace = THREE.SRGBColorSpace
    return tex
  }, [])
  return (
    <mesh position={[3, 7.4, -17.5]}>
      <planeGeometry args={[66, 26]} />
      <meshBasicMaterial map={texture} fog={false} />
    </mesh>
  )
}

/* ---------------------------------------------------------------- props */

function PineTree({ position, scale = 1 }: { position: [number, number, number]; scale?: number }) {
  return (
    <group position={position} scale={scale}>
      <mesh position={[0, 0.5, 0]} castShadow>
        <cylinderGeometry args={[0.14, 0.2, 1, 7]} />
        <meshStandardMaterial color="#6b4a30" roughness={1} />
      </mesh>
      {[0, 1, 2].map((tier) => (
        <mesh key={tier} position={[0, 1.15 + tier * 0.62, 0]} castShadow>
          <coneGeometry args={[0.92 - tier * 0.24, 0.95, 8]} />
          <meshStandardMaterial color={tier % 2 ? '#4f7d54' : '#5d8a52'} roughness={1} flatShading />
        </mesh>
      ))}
    </group>
  )
}

function BroadleafTree({ position, scale = 1 }: { position: [number, number, number]; scale?: number }) {
  return (
    <group position={position} scale={scale}>
      <mesh position={[0, 0.62, 0]} castShadow>
        <cylinderGeometry args={[0.12, 0.18, 1.24, 7]} />
        <meshStandardMaterial color="#74543a" roughness={1} />
      </mesh>
      <mesh position={[0.1, 1.7, -0.05]} castShadow>
        <icosahedronGeometry args={[0.95, 1]} />
        <meshStandardMaterial color="#79a862" roughness={1} flatShading />
      </mesh>
      <mesh position={[-0.42, 1.4, 0.2]} castShadow>
        <icosahedronGeometry args={[0.58, 1]} />
        <meshStandardMaterial color="#8cb874" roughness={1} flatShading />
      </mesh>
    </group>
  )
}

function Cabin() {
  return (
    <group position={[10.6, 0, -3.4]} rotation={[0, -0.5, 0]}>
      <mesh position={[0, 0.85, 0]} castShadow receiveShadow>
        <boxGeometry args={[2.6, 1.7, 2.2]} />
        <meshStandardMaterial color="#96755a" roughness={1} />
      </mesh>
      <mesh position={[0, 2.1, 0]} rotation={[0, Math.PI / 4, 0]} castShadow>
        <coneGeometry args={[2.05, 1.15, 4]} />
        <meshStandardMaterial color="#b0563f" roughness={1} flatShading />
      </mesh>
      <mesh position={[0, 0.62, 1.12]}>
        <boxGeometry args={[0.62, 0.95, 0.06]} />
        <meshStandardMaterial color="#5d4028" roughness={1} />
      </mesh>
      <mesh position={[0.88, 1.15, 1.12]}>
        <boxGeometry args={[0.52, 0.5, 0.05]} />
        <meshStandardMaterial color="#ffd28d" emissive="#ffb85c" emissiveIntensity={0.85} />
      </mesh>
    </group>
  )
}

function Dock() {
  const planks = [1.7, 0.95, 0.2, -0.55, -1.3]
  return (
    <group>
      {planks.map((x, index) => (
        <mesh key={x} position={[x, 0.07 + (index % 2) * 0.015, 5.7]} rotation={[0, index % 2 ? 0.02 : -0.02, 0]} receiveShadow castShadow>
          <boxGeometry args={[0.72, 0.07, 1.15]} />
          <meshStandardMaterial color="#9a744c" roughness={1} />
        </mesh>
      ))}
      {[1.55, -1.15].map((x) => (
        <mesh key={x} position={[x, -0.28, 6.12]}>
          <cylinderGeometry args={[0.07, 0.07, 0.9, 6]} />
          <meshStandardMaterial color="#6b4a30" roughness={1} />
        </mesh>
      ))}
    </group>
  )
}

function Rocks() {
  const rocks: Array<[number, number, number, number]> = [
    [2.4, 0.12, 6.9, 0.3],
    [1.1, 0.1, 7.6, 0.2],
    [6.6, 0.14, 5.9, 0.26],
    [0.4, 0.1, 3.4, 0.34],
    [8.9, 0.2, 6.4, 0.22],
  ]
  return (
    <group>
      {rocks.map(([x, y, z, s]) => (
        <mesh key={`${x}-${z}`} position={[x, y, z]} scale={[s, s * 0.7, s * 0.9]} castShadow>
          <icosahedronGeometry args={[1, 0]} />
          <meshStandardMaterial color="#98938a" roughness={1} flatShading />
        </mesh>
      ))}
    </group>
  )
}

function Lantern() {
  return (
    <group position={[3.05, 0, 4.75]}>
      <mesh position={[0, 0.55, 0]} castShadow>
        <cylinderGeometry args={[0.045, 0.06, 1.1, 6]} />
        <meshStandardMaterial color="#4c3a28" roughness={1} />
      </mesh>
      <mesh position={[0, 1.18, 0]}>
        <boxGeometry args={[0.24, 0.3, 0.24]} />
        <meshStandardMaterial color="#ffd28d" emissive="#ffb050" emissiveIntensity={1.1} />
      </mesh>
      <pointLight position={[0, 1.2, 0]} color="#ffc069" intensity={1.4} distance={5.5} decay={2} />
    </group>
  )
}

function Stool({ seatId, cushion, pulled = 0 }: { seatId: string; cushion: string; pulled?: number }) {
  const pos = seatPos(seatId, SEAT_RADIUS + pulled)
  return (
    <group position={[pos.x, 0, pos.z]}>
      <mesh position={[0, 0.24, 0]} castShadow>
        <cylinderGeometry args={[0.26, 0.22, 0.48, 10]} />
        <meshStandardMaterial color="#6f4527" roughness={1} />
      </mesh>
      <mesh position={[0, 0.5, 0]} castShadow>
        <cylinderGeometry args={[0.3, 0.28, 0.07, 12]} />
        <meshStandardMaterial color={cushion} roughness={0.9} />
      </mesh>
    </group>
  )
}

function TableSet() {
  return (
    <group position={[TABLE_POS.x, 0, TABLE_POS.z]}>
      <mesh position={[0, 0.06, 0]} receiveShadow>
        <cylinderGeometry args={[2.35, 2.5, 0.12, 24]} />
        <meshStandardMaterial color="#c9b483" roughness={1} />
      </mesh>
      <mesh position={[0, 0.72, 0]} castShadow receiveShadow>
        <cylinderGeometry args={[1.16, 1.02, 0.09, 20]} />
        <meshStandardMaterial color="#8a5a35" roughness={0.9} />
      </mesh>
      <mesh position={[0, 0.36, 0]} castShadow>
        <cylinderGeometry args={[0.13, 0.17, 0.68, 8]} />
        <meshStandardMaterial color="#6b4a30" roughness={1} />
      </mesh>
      <mesh position={[0, 0.75, 0]}>
        <cylinderGeometry args={[0.16, 0.2, 0.1, 10]} />
        <meshStandardMaterial color="#b0563f" roughness={0.9} />
      </mesh>
      {humanActors.concat(tableHost).map((actor) => (
        <Stool key={actor.id} seatId={actor.seatId} cushion={accentOf(actor.id)} />
      ))}
      <Stool seatId="seat-south" cushion="#ffd58c" pulled={0.24} />
    </group>
  )
}

/* ---------------------------------------------------------------- figures */

function SittingFigure({ seatId, accent, isHost = false }: { seatId: string; accent: string; isHost?: boolean }) {
  const pos = seatPos(seatId)
  const faceAngle = Math.atan2(TABLE_POS.x - pos.x, TABLE_POS.z - pos.z)
  return (
    <group position={[pos.x, 0, pos.z]} rotation={[0, faceAngle, 0]}>
      <mesh position={[0, 0.66, 0.03]} castShadow>
        <capsuleGeometry args={[0.21, 0.3, 4, 10]} />
        <meshStandardMaterial color={accent} roughness={0.85} />
      </mesh>
      <mesh position={[0, 1.09, 0]} castShadow>
        <sphereGeometry args={[0.165, 14, 12]} />
        <meshStandardMaterial color="#e6bd93" roughness={0.8} />
      </mesh>
      <mesh position={[0, 1.16, -0.045]}>
        <sphereGeometry args={[0.158, 12, 10, 0, Math.PI * 2, 0, Math.PI / 1.9]} />
        <meshStandardMaterial color={isHost ? '#e8e2d2' : '#4a3626'} roughness={1} />
      </mesh>
      {isHost && (
        <mesh position={[0, 0.78, 0.2]}>
          <sphereGeometry args={[0.05, 10, 8]} />
          <meshStandardMaterial color="#ffd17c" emissive="#ffb84d" emissiveIntensity={1.4} />
        </mesh>
      )}
    </group>
  )
}

function Figures({ activeActorId, hoveredActorId, reducedMotion, phase }:
  Pick<DioramaProps, 'activeActorId' | 'hoveredActorId' | 'reducedMotion' | 'phase'>) {
  const group = useRef<THREE.Group>(null)
  const speakerLight = useRef<THREE.PointLight>(null)
  const speakerRing = useRef<THREE.Mesh>(null)
  const orb = useRef<THREE.Mesh>(null)
  const orbLight = useRef<THREE.PointLight>(null)
  const halo = useRef<THREE.Mesh>(null)
  const target = useMemo(() => new THREE.Vector3(), [])
  const seeded = useMemo(() => humanActors.concat(tableHost).map((actor, index) => ({ actor, seed: index * 1.9 })), [])

  useFrame(({ clock }) => {
    const t = clock.elapsedTime
    const dt = 0.016
    if (group.current && !reducedMotion) {
      group.current.children.forEach((child, index) => {
        const figure = child.userData.figure ? child : null
        if (!figure) return
        figure.rotation.z = Math.sin(t * 0.9 + index * 1.9) * 0.02
        figure.position.y = Math.sin(t * 1.1 + index * 1.3) * 0.012
      })
    }
    const isHostActive = activeActorId === 'table-host'
    const activeId: ActorId | 'viewer' | null = isHostActive ? null : activeActorId
    const activePos = seatPos(seatOf(activeId ?? 'table-host'))
    if (speakerLight.current) {
      target.set(activePos.x, 1.35, activePos.z)
      speakerLight.current.position.lerp(target, 1 - Math.exp(-3.2 * dt))
      speakerLight.current.intensity = THREE.MathUtils.damp(speakerLight.current.intensity, activeId ? 2.4 : 1, 4, dt)
    }
    if (speakerRing.current) {
      const ringPos = seatPos(seatOf(hoveredActorId ?? (activeActorId === 'table-host' ? 'viewer' : activeActorId)))
      speakerRing.current.position.set(ringPos.x, 0.17, ringPos.z)
      const mat = speakerRing.current.material as THREE.MeshBasicMaterial
      mat.opacity = THREE.MathUtils.damp(mat.opacity, phase === 'seated' ? (hoveredActorId ? 0.75 : 0.42) : 0, 6, dt)
    }
    if (orb.current && orbLight.current) {
      const home = seatPos(tableHost.seatId)
      const goalId = isHostActive ? 'viewer' : activeActorId
      const goal = seatPos(seatOf(goalId))
      if (isHostActive || activeId) {
        target.set(goal.x, 1.12, goal.z)
      } else {
        target.set(home.x, 1.12, home.z)
      }
      orb.current.position.lerp(target, 1 - Math.exp(-3.4 * dt))
      const pulse = reducedMotion ? 1 : 1 + Math.sin(t * 1.35) * 0.06
      orb.current.scale.setScalar(pulse)
      orbLight.current.intensity = THREE.MathUtils.damp(orbLight.current.intensity, isHostActive ? 1.6 : activeId ? 1 : 0.6, 4, dt)
    }
    if (halo.current && !reducedMotion) halo.current.rotation.z = t * 0.25
  })

  const hostPos = seatPos(tableHost.seatId)

  return (
    <group ref={group}>
      {seeded.map(({ actor }) => (
        <group key={actor.id} userData={{ figure: true }}>
          <SittingFigure seatId={actor.seatId} accent={accentOf(actor.id)} isHost={actor.id === 'table-host'} />
          {actor.id === 'table-host' && (
            <mesh ref={halo} position={[hostPos.x, 1.56, hostPos.z]} rotation={[Math.PI / 2.3, 0, 0.4]}>
              <torusGeometry args={[0.3, 0.018, 8, 40, Math.PI * 1.6]} />
              <meshBasicMaterial color="#ffd782" transparent opacity={0.85} toneMapped={false} />
            </mesh>
          )}
        </group>
      ))}
      <mesh ref={speakerRing} rotation={[-Math.PI / 2, 0, 0]}>
        <ringGeometry args={[0.34, 0.42, 28]} />
        <meshBasicMaterial color="#ffd17c" transparent opacity={0} toneMapped={false} depthWrite={false} />
      </mesh>
      <pointLight ref={speakerLight} color="#ffd9a0" intensity={1} distance={4.6} decay={2} position={[hostPos.x, 1.35, hostPos.z]} />
      <mesh ref={orb} position={[hostPos.x, 1.12, hostPos.z]}>
        <sphereGeometry args={[0.055, 14, 12]} />
        <meshBasicMaterial color="#fff0bd" transparent opacity={0.95} toneMapped={false} />
        <pointLight ref={orbLight} color="#ffd176" intensity={1.2} distance={3.2} decay={2} />
      </mesh>
    </group>
  )
}

/* ---------------------------------------------------------------- anchors */

function AnchorProjector() {
  const { camera } = useThree()
  const frame = useRef(0)
  const projector = useMemo(() => new THREE.Vector3(), [])
  useFrame(() => {
    frame.current += 1
    if (frame.current % 5 !== 0) return
    const ids: Array<ActorId | 'viewer'> = ['shen-zhiyao', 'zhou-mo', 'lin-zhou', 'xu-qing', 'table-host', 'viewer']
    for (const id of ids) {
      const base = seatPos(seatOf(id))
      projector.set(base.x, id === 'viewer' ? 0.52 : 1.3, base.z)
      projector.project(camera)
      actorAnchors[id] = {
        x: (projector.x * 0.5 + 0.5) * 100,
        y: (-projector.y * 0.5 + 0.5) * 100,
      }
    }
  })
  return null
}

/* ---------------------------------------------------------------- scene */

export default function DioramaScene(props: DioramaProps) {
  return (
    <>
      <fog attach="fog" args={['#ddcfa9', 15, 42]} />
      <hemisphereLight color="#d8ecff" groundColor="#6b7d5a" intensity={0.85} />
      <directionalLight color="#cfe0ef" intensity={0.5} position={[-4, 5, 12]} />
      <directionalLight
        color="#ffe2b0"
        intensity={1.5}
        position={[7, 10, 5]}
        castShadow
        shadow-mapSize-width={1024}
        shadow-mapSize-height={1024}
        shadow-camera-left={-9}
        shadow-camera-right={9}
        shadow-camera-top={9}
        shadow-camera-bottom={-9}
        shadow-camera-near={1}
        shadow-camera-far={30}
      />
      <SkyDome />
      <BackdropPlate />
      <Terrain />
      <Water reducedMotion={props.reducedMotion} />
      <TableSet />
      <Dock />
      <Cabin />
      <Lantern />
      <PineTree position={[11.2, 0.2, 1.1]} scale={1.15} />
      <PineTree position={[13.6, 0.5, -1.2]} scale={0.95} />
      <PineTree position={[9.4, 0.15, -4.4]} scale={0.85} />
      <BroadleafTree position={[15.2, 0.6, 1.8]} scale={1.1} />
      <BroadleafTree position={[6.4, 0.1, -6.2]} scale={0.9} />
      <Rocks />
      <Figures {...props} />
      <AnchorProjector />
    </>
  )
}
