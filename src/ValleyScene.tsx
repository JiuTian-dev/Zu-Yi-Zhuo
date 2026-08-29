import { Sparkles, useTexture } from '@react-three/drei'
import { Canvas, useFrame, useThree } from '@react-three/fiber'
import { Suspense, useMemo, useRef } from 'react'
import * as THREE from 'three'
import { humanActors, type ActorId, type AgentAction, type SeatActor } from './actors'

export type ExperiencePhase = 'discovering' | 'approaching' | 'seated'

export interface ValleySceneProps {
  phase: ExperiencePhase
  activeActorId: ActorId
  hoveredActorId: ActorId | null
  reducedMotion: boolean
}

const TABLE_FOCUS = new THREE.Vector3(2.55, -1.22, 0.18)
const PLATE_WIDTH = 16.72
const PLATE_HEIGHT = 9.41
const PLATE_ASPECT = PLATE_WIDTH / PLATE_HEIGHT
const PLATE_OVERSCAN = 1.1

function usePlateScale(): [number, number, number] {
  const { size } = useThree()
  const aspectScale = Math.max(PLATE_OVERSCAN, (size.width / Math.max(size.height, 1) / PLATE_ASPECT) * PLATE_OVERSCAN)
  return [aspectScale, aspectScale, 1]
}

type DepthStratum = 'far' | 'middle' | 'near'

const DEPTH_STRATA: Array<{ id: DepthStratum; renderOrder: number }> = [
  { id: 'far', renderOrder: 0 },
  { id: 'middle', renderOrder: 1 },
  { id: 'near', renderOrder: 2 },
]

const DEPTH_VERTEX_SHADER = `
  uniform sampler2D depthMap;
  uniform float depthScale;
  uniform float depthBias;
  varying vec2 vUv;
  varying float vDepth;
  void main() {
    vUv = uv;
    vDepth = texture2D(depthMap, uv).r;
    float edgeDistance = min(min(uv.x, 1.0 - uv.x), min(uv.y, 1.0 - uv.y));
    float edgeLock = smoothstep(0.0, 0.1, edgeDistance);
    vec3 displaced = position;
    displaced.z += (vDepth * depthScale + depthBias) * edgeLock;
    gl_Position = projectionMatrix * modelViewMatrix * vec4(displaced, 1.0);
  }
`

const DEPTH_FRAGMENT_SHADER = `
  uniform sampler2D colorMap;
  uniform float stratum;
  varying vec2 vUv;
  varying float vDepth;
  void main() {
    // Two separated feather ranges keep the three weights complementary:
    // far = 1-a, middle = a*(1-b), near = b. Because a reaches 1.0
    // before b starts, the visible contribution remains exactly one.
    float a = smoothstep(0.30, 0.46, vDepth);
    float b = smoothstep(0.62, 0.78, vDepth);
    float farWeight = 1.0 - a;
    float middleWeight = a * (1.0 - b);
    float nearWeight = b;
    float weight = stratum < 0.5
      ? farWeight
      : stratum < 1.5 ? middleWeight : nearWeight;
    vec4 color = texture2D(colorMap, vUv);
    gl_FragColor = vec4(color.rgb, 1.0);
    #include <tonemapping_fragment>
    #include <colorspace_fragment>
    // Additive compositing happens in output color space. Premultiply each
    // stratum after conversion so complementary weights reconstruct one plate.
    gl_FragColor = vec4(gl_FragColor.rgb * weight, weight);
  }
`

function DepthStratumPlate({
  colorMap,
  depthMap,
  stratum,
  renderOrder,
}: {
  colorMap: THREE.Texture
  depthMap: THREE.Texture
  stratum: DepthStratum
  renderOrder: number
}) {
  const uniforms = useMemo(() => ({
    colorMap: { value: colorMap },
    depthMap: { value: depthMap },
    depthScale: { value: 0.82 },
    depthBias: { value: -0.34 },
    stratum: { value: stratum === 'far' ? 0 : stratum === 'middle' ? 1 : 2 },
  }), [colorMap, depthMap, stratum])

  return (
    <mesh renderOrder={renderOrder}>
      <planeGeometry args={[PLATE_WIDTH, PLATE_HEIGHT, 200, 112]} />
      <shaderMaterial
        uniforms={uniforms}
        vertexShader={DEPTH_VERTEX_SHADER}
        fragmentShader={DEPTH_FRAGMENT_SHADER}
        transparent
        blending={THREE.CustomBlending}
        blendEquation={THREE.AddEquation}
        blendSrc={THREE.OneFactor}
        blendDst={THREE.OneFactor}
        blendEquationAlpha={THREE.AddEquation}
        blendSrcAlpha={THREE.OneFactor}
        blendDstAlpha={THREE.OneFactor}
        depthTest={false}
        depthWrite={false}
      />
    </mesh>
  )
}

function DepthPlate({ phase, reducedMotion }: Pick<ValleySceneProps, 'phase' | 'reducedMotion'>) {
  const group = useRef<THREE.Group>(null)
  const plateScale = usePlateScale()
  const [colorMap, depthMap] = useTexture(['/assets/valley-world-clean.png', '/assets/valley-world-depth.png'])
  colorMap.colorSpace = THREE.SRGBColorSpace
  colorMap.anisotropy = 8
  depthMap.colorSpace = THREE.NoColorSpace
  useFrame(({ clock }) => {
    if (!group.current || reducedMotion) return
    group.current.rotation.y = Math.sin(clock.elapsedTime * 0.22) * 0.006 * (phase === 'discovering' ? 1 : 0.35)
  })

  return (
    <group ref={group} scale={plateScale}>
      {DEPTH_STRATA.map((layer) => (
        <DepthStratumPlate
          key={layer.id}
          colorMap={colorMap}
          depthMap={depthMap}
          stratum={layer.id}
          renderOrder={layer.renderOrder}
        />
      ))}
    </group>
  )
}

function CameraRig({ phase, reducedMotion }: Pick<ValleySceneProps, 'phase' | 'reducedMotion'>) {
  const { camera, pointer, size } = useThree()
  const lookAt = useRef(new THREE.Vector3())
  const position = useMemo(() => new THREE.Vector3(), [])
  const targetLook = useMemo(() => new THREE.Vector3(), [])

  useFrame(({ clock }, delta) => {
    const mobile = size.width < 760
    const close = phase !== 'discovering'
    const drift = reducedMotion ? 0 : Math.sin(clock.elapsedTime * 0.18) * 0.025
    if (close) {
      position.set(mobile ? 2.2 : 2.82, mobile ? -0.9 : -1.18, mobile ? 8.15 : 6.35)
      targetLook.copy(TABLE_FOCUS)
    } else {
      position.set(0, 0, 12.22)
      targetLook.set(0, 0, 0)
    }
    if (!reducedMotion) {
      position.x += pointer.x * (close ? 0.1 : 0.18) + drift
      position.y += pointer.y * (close ? 0.045 : 0.09)
      targetLook.x += pointer.x * (close ? 0.045 : 0.08)
      targetLook.y += pointer.y * (close ? 0.025 : 0.045)
    }
    const speed = reducedMotion ? 18 : phase === 'approaching' ? 1.25 : close ? 2.8 : 3.2
    camera.position.x = THREE.MathUtils.damp(camera.position.x, position.x, speed, delta)
    camera.position.y = THREE.MathUtils.damp(camera.position.y, position.y, speed, delta)
    camera.position.z = THREE.MathUtils.damp(camera.position.z, position.z, speed, delta)
    lookAt.current.lerp(targetLook, 1 - Math.exp(-speed * delta))
    camera.lookAt(lookAt.current)
  })
  return null
}

function FloatingPetals({ phase, reducedMotion }: Pick<ValleySceneProps, 'phase' | 'reducedMotion'>) {
  const group = useRef<THREE.Group>(null)
  const petals = useMemo(() => Array.from({ length: 20 }, (_, index) => ({
    x: -7 + ((index * 43) % 100) / 100 * 14,
    y: -4 + ((index * 29) % 100) / 100 * 8,
    z: 0.35 + ((index * 17) % 100) / 100 * 1.25,
    speed: 0.05 + (index % 4) * 0.018,
    size: 0.018 + (index % 3) * 0.008,
  })), [])

  useFrame((_, delta) => {
    if (!group.current || reducedMotion) return
    group.current.children.forEach((child, index) => {
      child.position.x -= petals[index].speed * delta
      child.position.y -= petals[index].speed * 0.22 * delta
      child.rotation.z += delta * 0.22
      if (child.position.x < -7.4) child.position.x = 7.4
      if (child.position.y < -4.4) child.position.y = 4.4
    })
  })

  return (
    <group ref={group}>
      {petals.map((petal, index) => (
        <mesh key={index} position={[petal.x, petal.y, petal.z]} rotation={[0, 0, index]}>
          <circleGeometry args={[petal.size, 5]} />
          <meshBasicMaterial color={index % 3 === 0 ? '#ffd28f' : '#ff8f91'} transparent opacity={phase === 'seated' ? 0.55 : 0.32} depthWrite={false} toneMapped={false} />
        </mesh>
      ))}
    </group>
  )
}

function HumanMatte({ actor, active, hovered }: { actor: SeatActor; active: boolean; hovered: boolean }) {
  const material = useRef<THREE.ShaderMaterial>(null)
  const plateScale = usePlateScale()
  const [colorMap, depthMap] = useTexture(['/assets/valley-world-clean.png', '/assets/valley-world-depth.png'])
  colorMap.colorSpace = THREE.SRGBColorSpace
  depthMap.colorSpace = THREE.NoColorSpace
  const uniforms = useMemo(() => ({
    colorMap: { value: colorMap }, depthMap: { value: depthMap },
    center: { value: new THREE.Vector2(...actor.plateCenter) },
    radius: { value: new THREE.Vector2(...actor.plateRadius) },
    accent: { value: new THREE.Color(actor.accent) }, strength: { value: 0 },
  }), [actor, colorMap, depthMap])

  useFrame((_, delta) => {
    if (!material.current) return
    material.current.uniforms.strength.value = THREE.MathUtils.damp(
      material.current.uniforms.strength.value,
      hovered ? 0.34 : active ? 0.2 : 0,
      7,
      delta,
    )
  })

  return (
    <mesh position={[0, 0, 0.012]} scale={plateScale} renderOrder={2}>
      <planeGeometry args={[PLATE_WIDTH, PLATE_HEIGHT, 200, 112]} />
      <shaderMaterial
        ref={material}
        uniforms={uniforms}
        transparent
        depthWrite={false}
        vertexShader={`
          uniform sampler2D depthMap;
          varying vec2 vUv;
          void main(){
            vUv=uv;
            vec3 p=position;
            p.z += texture2D(depthMap,uv).r*.82-.34;
            gl_Position=projectionMatrix*modelViewMatrix*vec4(p,1.0);
          }
        `}
        fragmentShader={`
          uniform sampler2D colorMap;
          uniform vec2 center;
          uniform vec2 radius;
          uniform vec3 accent;
          uniform float strength;
          varying vec2 vUv;
          void main(){
            vec2 d=(vUv-center)/radius;
            float matte=1.0-smoothstep(.72,1.0,dot(d,d));
            vec4 base=texture2D(colorMap,vUv);
            vec3 lit=mix(base.rgb,accent,.22);
            gl_FragColor=vec4(lit,matte*strength);
            #include <tonemapping_fragment>
            #include <colorspace_fragment>
          }
        `}
      />
    </mesh>
  )
}

function HumanMattes({ activeActorId, hoveredActorId, phase }: Pick<ValleySceneProps, 'activeActorId' | 'hoveredActorId' | 'phase'>) {
  if (phase !== 'seated') return null
  return <>{humanActors.map((actor) => <HumanMatte key={actor.id} actor={actor} active={activeActorId === actor.id} hovered={hoveredActorId === actor.id} />)}</>
}

function TableHost({ phase, action, hovered, reducedMotion }: {
  phase: ExperiencePhase
  action: AgentAction
  hovered: boolean
  reducedMotion: boolean
}) {
  const group = useRef<THREE.Group>(null)
  const silenceMaterial = useRef<THREE.SpriteMaterial>(null)
  const passMaterial = useRef<THREE.SpriteMaterial>(null)
  const haloMaterial = useRef<THREE.MeshBasicMaterial>(null)
  const coreMaterial = useRef<THREE.MeshBasicMaterial>(null)
  const orbMaterial = useRef<THREE.MeshBasicMaterial>(null)
  const orbLight = useRef<THREE.PointLight>(null)
  const orb = useRef<THREE.Mesh>(null)
  const visibility = useRef(0)
  const [silenceMap, passMap] = useTexture([
    '/assets/actors/table-host-silence.png',
    '/assets/actors/table-host-pass.png',
  ])
  silenceMap.colorSpace = THREE.SRGBColorSpace
  passMap.colorSpace = THREE.SRGBColorSpace
  const orbHome = useMemo(() => new THREE.Vector3(0.28, -0.18, 0.08), [])
  const orbTarget = useMemo(() => new THREE.Vector3(1.25, -0.08, 0.16), [])

  useFrame(({ clock }, delta) => {
    if (!group.current || !silenceMaterial.current || !passMaterial.current || !haloMaterial.current || !coreMaterial.current || !orbMaterial.current || !orbLight.current || !orb.current) return
    const present = phase === 'seated' ? 1 : phase === 'approaching' ? 0.42 : 0
    visibility.current = THREE.MathUtils.damp(visibility.current, present, 4.8, delta)
    const passing = action === 'PASS' ? 1 : 0
    silenceMaterial.current.opacity = visibility.current * (1 - passing)
    passMaterial.current.opacity = visibility.current * passing
    const pulse = reducedMotion ? 1 : 1 + Math.sin(clock.elapsedTime * 1.35) * 0.035
    group.current.position.y = -1.04 + (reducedMotion ? 0 : Math.sin(clock.elapsedTime * 0.72) * 0.008)
    group.current.scale.setScalar(0.96 + passing * 0.035)
    haloMaterial.current.opacity = visibility.current * (hovered ? 0.98 : passing ? 0.92 : 0.66)
    coreMaterial.current.opacity = visibility.current * (passing ? 1 : 0.72)
    orbMaterial.current.opacity = visibility.current * (passing ? 0.96 : 0.34)
    orbLight.current.intensity = visibility.current * (passing ? 1.1 : 0.2)
    orb.current.scale.setScalar(pulse * (passing ? 1 : 0.62))
    orb.current.position.lerp(passing ? orbTarget : orbHome, 1 - Math.exp(-3.8 * delta))
  })

  return (
    <group ref={group} position={[2.14, -1.04, 0.28]} renderOrder={5}>
      <mesh position={[0, 0.26, -0.008]} rotation={[0, 0, -0.28]}>
        <ringGeometry args={[0.255, 0.278, 72, 1, 0.2, Math.PI * 1.72]} />
        <meshBasicMaterial ref={haloMaterial} color="#ffd782" transparent opacity={0} depthWrite={false} toneMapped={false} />
      </mesh>
      <sprite position={[0, -0.08, 0]} scale={[0.72, 0.84, 1]}>
        <spriteMaterial ref={silenceMaterial} map={silenceMap} transparent opacity={0} depthWrite={false} alphaTest={0.06} toneMapped={false} />
      </sprite>
      <sprite position={[0.05, -0.08, 0.002]} scale={[0.78, 0.84, 1]}>
        <spriteMaterial ref={passMaterial} map={passMap} transparent opacity={0} depthWrite={false} alphaTest={0.06} toneMapped={false} />
      </sprite>
      <mesh position={[0, -0.17, 0.012]}>
        <ringGeometry args={[0.048, 0.063, 48]} />
        <meshBasicMaterial ref={coreMaterial} color="#ffe09a" transparent opacity={0} depthWrite={false} toneMapped={false} />
      </mesh>
      <mesh ref={orb} position={orbHome} renderOrder={7}>
        <sphereGeometry args={[0.035, 20, 16]} />
        <meshBasicMaterial ref={orbMaterial} color="#fff0bd" transparent opacity={0} depthWrite={false} toneMapped={false} />
        <pointLight ref={orbLight} color="#ffd176" intensity={0} distance={1.4} decay={2} />
      </mesh>
    </group>
  )
}

export function ValleySceneContent(props: ValleySceneProps) {
  const hostAction: AgentAction = props.activeActorId === 'table-host' ? 'PASS' : 'SILENCE'
  return (
    <>
      <CameraRig phase={props.phase} reducedMotion={props.reducedMotion} />
      <DepthPlate phase={props.phase} reducedMotion={props.reducedMotion} />
      <HumanMattes activeActorId={props.activeActorId} hoveredActorId={props.hoveredActorId} phase={props.phase} />
      <TableHost phase={props.phase} action={hostAction} hovered={props.hoveredActorId === 'table-host'} reducedMotion={props.reducedMotion} />
      <FloatingPetals phase={props.phase} reducedMotion={props.reducedMotion} />
      <Sparkles count={props.reducedMotion ? 8 : props.phase === 'seated' ? 34 : 18} position={[2.6, -1.15, 1.15]} scale={[4.4, 2.5, 1.5]} size={1.4} speed={props.reducedMotion ? 0 : 0.12} color="#ffe3a4" opacity={props.phase === 'seated' ? 0.34 : 0.12} />
    </>
  )
}

export default function ValleyScene(props: ValleySceneProps) {
  return (
    <Canvas
      className="valley-canvas"
      camera={{ position: [0, 0, 12.22], fov: 42, near: 0.1, far: 40 }}
      dpr={[1, 1.65]}
      gl={{ antialias: true, alpha: true, premultipliedAlpha: false, powerPreference: 'high-performance' }}
      onCreated={({ gl }) => gl.setClearColor(0x000000, 0)}
    >
      <Suspense fallback={null}><ValleySceneContent {...props} /></Suspense>
    </Canvas>
  )
}
