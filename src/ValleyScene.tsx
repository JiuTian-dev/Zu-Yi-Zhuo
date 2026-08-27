import { Sparkles, useTexture } from '@react-three/drei'
import { Canvas, useFrame, useThree } from '@react-three/fiber'
import { Suspense, useMemo, useRef } from 'react'
import * as THREE from 'three'

interface ValleySceneProps {
  focused: boolean
  reducedMotion: boolean
}

const ART_ASPECT = 16 / 9

function makeGlowTexture() {
  const canvas = document.createElement('canvas')
  canvas.width = 256
  canvas.height = 256
  const context = canvas.getContext('2d')!
  const gradient = context.createRadialGradient(128, 128, 0, 128, 128, 128)
  gradient.addColorStop(0, 'rgba(255, 220, 150, .62)')
  gradient.addColorStop(0.32, 'rgba(255, 190, 115, .2)')
  gradient.addColorStop(1, 'rgba(255, 180, 100, 0)')
  context.fillStyle = gradient
  context.fillRect(0, 0, 256, 256)
  return new THREE.CanvasTexture(canvas)
}

function WorldPlate({ focused, reducedMotion }: ValleySceneProps) {
  const texture = useTexture('/assets/valley-world-clean.png')
  const group = useRef<THREE.Group>(null)
  const { viewport, pointer } = useThree()

  texture.colorSpace = THREE.SRGBColorSpace
  texture.minFilter = THREE.LinearFilter

  const plateSize = useMemo(() => {
    const viewportAspect = viewport.width / viewport.height
    if (viewportAspect > ART_ASPECT) {
      return [viewport.width, viewport.width / ART_ASPECT] as const
    }
    return [viewport.height * ART_ASPECT, viewport.height] as const
  }, [viewport.height, viewport.width])

  useFrame(({ clock }, delta) => {
    if (!group.current) return
    const targetX = reducedMotion ? 0 : pointer.x * -0.075
    const targetY = reducedMotion ? 0 : pointer.y * -0.045
    group.current.position.x = THREE.MathUtils.damp(group.current.position.x, targetX, 3.6, delta)
    group.current.position.y = THREE.MathUtils.damp(group.current.position.y, targetY, 3.6, delta)
    const focusScale = focused ? 1.055 : 1
    const breath = reducedMotion ? 0 : Math.sin(clock.elapsedTime * 0.24) * 0.002
    const scale = THREE.MathUtils.damp(group.current.scale.x, focusScale + breath, 2.4, delta)
    group.current.scale.setScalar(scale)
  })

  return (
    <group ref={group}>
      <mesh position={[0, 0, 0]}>
        <planeGeometry args={[plateSize[0] * 1.025, plateSize[1] * 1.025]} />
        <meshBasicMaterial map={texture} toneMapped={false} />
      </mesh>
    </group>
  )
}

function Atmosphere({ focused, reducedMotion }: ValleySceneProps) {
  const glowTexture = useMemo(makeGlowTexture, [])
  const glow = useRef<THREE.Sprite>(null)
  const petalGroup = useRef<THREE.Group>(null)

  const petals = useMemo(
    () => Array.from({ length: 16 }, (_, index) => ({
      x: 2.7 + ((index * 37) % 100) / 100 * 3.8,
      y: 1.1 - ((index * 53) % 100) / 100 * 3.8,
      scale: 0.012 + (index % 4) * 0.005,
      speed: 0.14 + (index % 5) * 0.035,
    })),
    [],
  )

  useFrame(({ clock }, delta) => {
    if (glow.current) {
      const material = glow.current.material as THREE.SpriteMaterial
      const targetOpacity = focused ? 0.34 : 0.12
      material.opacity = THREE.MathUtils.damp(material.opacity, targetOpacity, 3, delta)
      const pulse = reducedMotion ? 1 : 1 + Math.sin(clock.elapsedTime * 1.1) * 0.035
      glow.current.scale.set(2.6 * pulse, 2.6 * pulse, 1)
    }
    if (petalGroup.current && !reducedMotion) {
      petalGroup.current.children.forEach((child, index) => {
        child.position.x -= petals[index].speed * delta
        child.position.y -= petals[index].speed * 0.35 * delta
        child.rotation.z += delta * 0.45
        if (child.position.x < -4.5) child.position.x = 5.5
        if (child.position.y < -3.3) child.position.y = 2.8
      })
    }
  })

  return (
    <>
      <sprite ref={glow} position={[2.35, -1.1, 0.35]} scale={[2.6, 2.6, 1]}>
        <spriteMaterial map={glowTexture} transparent opacity={0.12} depthWrite={false} blending={THREE.AdditiveBlending} />
      </sprite>
      <Sparkles
        count={reducedMotion ? 12 : 32}
        position={[-1.55, -1.05, 0.3]}
        scale={[5.2, 0.8, 0.1]}
        size={1.2}
        speed={reducedMotion ? 0 : 0.12}
        color="#eaffff"
        opacity={focused ? 0.6 : 0.36}
      />
      <group ref={petalGroup}>
        {petals.map((petal, index) => (
          <mesh key={index} position={[petal.x, petal.y, 0.45]} rotation={[0, 0, index * 0.7]}>
            <circleGeometry args={[petal.scale, 5]} />
            <meshBasicMaterial color={index % 3 === 0 ? '#ffd079' : '#ff7d88'} transparent opacity={0.72} depthWrite={false} />
          </mesh>
        ))}
      </group>
    </>
  )
}

export default function ValleyScene(props: ValleySceneProps) {
  return (
    <Canvas
      className="valley-canvas"
      orthographic
      camera={{ position: [0, 0, 10], zoom: 100 }}
      dpr={[1, 1.6]}
      gl={{ antialias: true, alpha: true, powerPreference: 'high-performance' }}
    >
      <Suspense fallback={null}>
        <WorldPlate {...props} />
        <Atmosphere {...props} />
      </Suspense>
    </Canvas>
  )
}
