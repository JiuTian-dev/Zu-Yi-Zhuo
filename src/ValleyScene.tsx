import { Sparkles, useTexture } from '@react-three/drei'
import { Canvas, useFrame, useThree } from '@react-three/fiber'
import { Suspense, useMemo, useRef } from 'react'
import * as THREE from 'three'

export type ExperiencePhase = 'discovering' | 'approaching' | 'seated'

interface ValleySceneProps {
  phase: ExperiencePhase
  activeSpeaker: number
  reducedMotion: boolean
}

const TABLE_FOCUS = new THREE.Vector3(2.55, -1.22, 0.18)

function DepthPlate({ phase, reducedMotion }: Pick<ValleySceneProps, 'phase' | 'reducedMotion'>) {
  const mesh = useRef<THREE.Mesh>(null)
  const [colorMap, depthMap] = useTexture(['/assets/valley-world-clean.png', '/assets/valley-world-depth.png'])
  colorMap.colorSpace = THREE.SRGBColorSpace
  colorMap.anisotropy = 8
  depthMap.colorSpace = THREE.NoColorSpace
  const uniforms = useMemo(() => ({
    colorMap: { value: colorMap },
    depthMap: { value: depthMap },
    depthScale: { value: 0.82 },
    depthBias: { value: -0.34 },
  }), [colorMap, depthMap])

  useFrame(({ clock }) => {
    if (!mesh.current || reducedMotion) return
    mesh.current.rotation.y = Math.sin(clock.elapsedTime * 0.22) * 0.006 * (phase === 'discovering' ? 1 : 0.35)
  })

  return (
    <mesh ref={mesh}>
      <planeGeometry args={[16.72, 9.41, 200, 112]} />
      <shaderMaterial
        uniforms={uniforms}
        vertexShader={`
          uniform sampler2D depthMap;
          uniform float depthScale;
          uniform float depthBias;
          varying vec2 vUv;
          void main() {
            vUv = uv;
            float depth = texture2D(depthMap, uv).r;
            vec3 displaced = position;
            displaced.z += depth * depthScale + depthBias;
            gl_Position = projectionMatrix * modelViewMatrix * vec4(displaced, 1.0);
          }
        `}
        fragmentShader={`
          uniform sampler2D colorMap;
          varying vec2 vUv;
          void main() {
            gl_FragColor = texture2D(colorMap, vUv);
            #include <tonemapping_fragment>
            #include <colorspace_fragment>
          }
        `}
      />
    </mesh>
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

function SceneContent(props: ValleySceneProps) {
  return (
    <>
      <CameraRig phase={props.phase} reducedMotion={props.reducedMotion} />
      <DepthPlate phase={props.phase} reducedMotion={props.reducedMotion} />
      <FloatingPetals phase={props.phase} reducedMotion={props.reducedMotion} />
      <Sparkles count={props.reducedMotion ? 8 : props.phase === 'seated' ? 34 : 18} position={[2.6, -1.15, 1.15]} scale={[4.4, 2.5, 1.5]} size={1.4} speed={props.reducedMotion ? 0 : 0.12} color="#ffe3a4" opacity={props.phase === 'seated' ? 0.34 : 0.12} />
    </>
  )
}

export default function ValleyScene(props: ValleySceneProps) {
  return (
    <Canvas className="valley-canvas" camera={{ position: [0, 0, 12.22], fov: 42, near: 0.1, far: 40 }} dpr={[1, 1.65]} gl={{ antialias: true, alpha: false, powerPreference: 'high-performance' }}>
      <color attach="background" args={['#779dba']} />
      <Suspense fallback={null}><SceneContent {...props} /></Suspense>
    </Canvas>
  )
}
