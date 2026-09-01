import { useGLTF } from '@react-three/drei'
import { applyBrunoStyle } from './brunoMaterial'
import { useMemo, type ReactNode } from 'react'
import * as THREE from 'three'

/** Load a GLB and auto-fit it: normalize to `height`, rest on ground, center
 *  in XZ, so placement is deterministic without knowing authored sizes. */
export function GltfFit({ src, height, position = [0, 0, 0], rotation = [0, 0, 0], tint, xz = true }: {
  src: string
  height: number
  position?: [number, number, number]
  rotation?: [number, number, number]
  tint?: string
  xz?: boolean
}) {
  const { scene } = useGLTF(src)
  const prepared = useMemo(() => {
    const clone = scene.clone(true)
    const box = new THREE.Box3().setFromObject(clone)
    const size = box.getSize(new THREE.Vector3())
    const center = box.getCenter(new THREE.Vector3())
    const scale = height / Math.max(size.y, 1e-4)
    clone.traverse((object) => {
      const mesh = object as THREE.Mesh
      if ((mesh as THREE.Mesh).isMesh) {
        mesh.castShadow = true
        mesh.receiveShadow = false
        const material = mesh.material as THREE.MeshStandardMaterial | undefined
        if (material && tint) {
          material.emissive = new THREE.Color(tint)
          material.emissiveIntensity = 0.32
        }
        if (material) applyBrunoStyle(material)
      }
    })
    const holder = new THREE.Group()
    clone.scale.setScalar(scale)
    clone.position.set(
      (xz ? -center.x : 0) * scale,
      -box.min.y * scale,
      (xz ? -center.z : 0) * scale,
    )
    holder.add(clone)
    return holder
  }, [scene, height, tint, xz])
  return (
    <group position={position} rotation={rotation}>
      <primitive object={prepared} />
    </group>
  )
}

export function SeaModelProvider({ children }: { children: ReactNode }) {
  return <>{children}</>
}

export const SEA_MODEL_PATHS = [
  '/assets/sea/campfire.glb',
  '/assets/sea/cabin.glb',
  '/assets/sea/lamp.glb',
  '/assets/sea/skyline.glb',
  '/assets/sea/umbrella.glb',
  '/assets/sea/bookshelf.glb',
  '/assets/sea/pier.glb',
  '/assets/sea/canoe.glb',
  '/assets/sea/pine.glb',
  '/assets/sea/fire.glb',
  '/assets/sea/cafe.glb',
  '/assets/sea/autumn-tree.glb',
  '/assets/sea/tent.glb',
  '/assets/sea/fishing-rod.glb',
  '/assets/sea/lantern.glb',
  '/assets/sea/kenney/campfire_logs.glb',
  '/assets/sea/kenney/grass.glb',
  '/assets/sea/kenney/grass_large.glb',
  '/assets/sea/kenney/log.glb',
  '/assets/sea/kenney/log_stack.glb',
  '/assets/sea/kenney/rock_smallA.glb',
  '/assets/sea/kenney/rock_smallB.glb',
  '/assets/sea/kenney/rock_tallA.glb',
  '/assets/sea/kenney/tree_small.glb',
]
