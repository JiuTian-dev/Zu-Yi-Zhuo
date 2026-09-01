import { Sparkles } from '@react-three/drei'
import { Canvas, useFrame, useThree } from '@react-three/fiber'
import { Suspense, useMemo, useRef } from 'react'
import * as THREE from 'three'
import DioramaScene, { type DioramaProps } from './Diorama'

export type ExperiencePhase = DioramaProps['phase']
export type ValleySceneProps = DioramaProps

const CAMERA_TARGETS: Record<ExperiencePhase, { pos: [number, number, number]; look: [number, number, number] }> = {
  discovering: { pos: [9.2, 3.9, 13.2], look: [4.6, 0.8, 1.4] },
  approaching: { pos: [6.3, 2.5, 8.8], look: [4.2, 0.85, 2.2] },
  seated: { pos: [5.05, 1.55, 6.35], look: [4.05, 0.85, 2.0] },
}

function CameraRig({ phase, reducedMotion }: Pick<ValleySceneProps, 'phase' | 'reducedMotion'>) {
  const { camera } = useThree()
  const lookAt = useRef(new THREE.Vector3())
  const target = useMemo(() => new THREE.Vector3(), [])
  const position = useMemo(() => new THREE.Vector3(), [])

  useFrame(({ clock, pointer }, delta) => {
    const stage = CAMERA_TARGETS[phase]
    const drift = reducedMotion ? 0 : Math.sin(clock.elapsedTime * 0.18) * 0.05
    position.set(...stage.pos)
    target.set(...stage.look)
    if (!reducedMotion) {
      const parallax = phase === 'discovering' ? 1 : 0.55
      position.x += pointer.x * 0.4 * parallax + drift
      position.y += pointer.y * 0.2 * parallax
      target.x += pointer.x * 0.16 * parallax
      target.y += pointer.y * 0.1 * parallax
    }
    const speed = reducedMotion ? 18 : phase === 'approaching' ? 1.15 : phase === 'seated' ? 2.6 : 3.1
    camera.position.x = THREE.MathUtils.damp(camera.position.x, position.x, speed, delta)
    camera.position.y = THREE.MathUtils.damp(camera.position.y, position.y, speed, delta)
    camera.position.z = THREE.MathUtils.damp(camera.position.z, position.z, speed, delta)
    lookAt.current.lerp(target, 1 - Math.exp(-speed * delta))
    camera.lookAt(lookAt.current)
  })
  return null
}

function FloatingPetals({ reducedMotion }: Pick<ValleySceneProps, 'reducedMotion'>) {
  const group = useRef<THREE.Group>(null)
  const petals = useRef(
    Array.from({ length: 18 }, (_, index) => ({
      x: -6 + ((index * 43) % 100) / 100 * 12,
      y: 0.4 + ((index * 29) % 100) / 100 * 3.4,
      z: 2 + ((index * 17) % 100) / 100 * 6,
      speed: 0.12 + (index % 4) * 0.05,
      size: 0.03 + (index % 3) * 0.012,
    })),
  ).current

  useFrame((_, delta) => {
    if (!group.current || reducedMotion) return
    group.current.children.forEach((child, index) => {
      child.position.x -= petals[index].speed * delta
      child.position.y -= petals[index].speed * 0.18 * delta
      child.rotation.z += delta * 0.3
      if (child.position.x < -7) child.position.x = 6.2
      if (child.position.y < -0.4) child.position.y = 4
    })
  })

  return (
    <group ref={group}>
      {petals.map((petal, index) => (
        <mesh key={index} position={[petal.x, petal.y, petal.z]} rotation={[0, 0, index]}>
          <circleGeometry args={[petal.size, 5]} />
          <meshBasicMaterial color={index % 3 === 0 ? '#ffd28f' : '#ff8f91'} transparent opacity={0.5} depthWrite={false} toneMapped={false} />
        </mesh>
      ))}
    </group>
  )
}

export function ValleySceneContent(props: ValleySceneProps) {
  return (
    <>
      <CameraRig phase={props.phase} reducedMotion={props.reducedMotion} />
      <DioramaScene {...props} />
      <FloatingPetals reducedMotion={props.reducedMotion} />
      <Sparkles
        count={props.reducedMotion ? 10 : props.phase === 'seated' ? 40 : 22}
        position={[3.4, 1.4, 3.4]}
        scale={[5, 2.4, 4]}
        size={1.6}
        speed={props.reducedMotion ? 0 : 0.14}
        color="#ffe3a4"
        opacity={props.phase === 'seated' ? 0.4 : 0.16}
      />
    </>
  )
}

export default function ValleyScene(props: ValleySceneProps) {
  return (
    <Canvas
      className="valley-canvas"
      camera={{ position: [9.2, 3.9, 13.2], fov: 42, near: 0.1, far: 90 }}
      dpr={[1, 1.65]}
      shadows
      gl={{ antialias: true, alpha: true, powerPreference: 'high-performance' }}
      onCreated={({ gl }) => gl.setClearColor(0x000000, 0)}
    >
      <Suspense fallback={null}><ValleySceneContent {...props} /></Suspense>
    </Canvas>
  )
}
