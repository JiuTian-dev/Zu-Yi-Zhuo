import { useEffect, useRef, useState } from 'react'
import { getHomeAccount, type AvatarCharacter } from './accountStore'
import './lakeModelStage.css'
import { prepareCharacterShading } from '../live/modelShading'

type SceneState = 'loading' | 'ready' | 'error'

const MODEL_URLS: Record<AvatarCharacter, string> = {
  blue: '/scene/avatar-blue-hd.glb', orange: '/scene/avatar-orange-hd.glb',
  white: '/scene/avatar-white-hd.glb', green: '/scene/avatar-green-hd.glb',
}
const CHARACTER_ORDER: AvatarCharacter[] = ['white', 'orange', 'green', 'blue']
const POSITIONS = [
  [-.92, 0, -.68], [.92, 0, -.68], [-1.08, 0, .66], [1.08, 0, .66],
] as const

/** A grounded lakeside composition using the supplied character and SUV GLBs. */
export default function LakeModelStage() {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const [state, setState] = useState<SceneState>('loading')
  const viewer = getHomeAccount().avatarCharacter ?? 'blue'
  const tableCharacters = CHARACTER_ORDER.filter((character) => character !== viewer)
  const people = [
    ...tableCharacters.map((character, index) => ({ url: MODEL_URLS[character], name: ['林夏', '周砚', '程野'][index], position: POSITIONS[index] })),
    { url: MODEL_URLS[viewer], name: '你', position: POSITIONS[3] },
  ]

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    let disposed = false
    let frame = 0
    setState('loading')

    void (async () => {
      try {
        const THREE = await import('three')
        const [{ GLTFLoader }, { OrbitControls }, { MeshoptDecoder }, { DRACOLoader }] = await Promise.all([
          import('three/addons/loaders/GLTFLoader.js'),
          import('three/addons/controls/OrbitControls.js'),
          import('three/addons/libs/meshopt_decoder.module.js'),
          import('three/addons/loaders/DRACOLoader.js'),
        ])
        if (disposed) return

        const scene = new THREE.Scene()
        const camera = new THREE.OrthographicCamera(-3.4, 3.4, 2.1, -2.1, .1, 100)
        camera.position.set(0, 4.6, 8.8)
        camera.lookAt(-.35, .62, 0)

        const renderer = new THREE.WebGLRenderer({ canvas, alpha: true, antialias: true, powerPreference: 'high-performance' })
        renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.65))
        renderer.outputColorSpace = THREE.SRGBColorSpace
        renderer.toneMapping = THREE.ACESFilmicToneMapping
        renderer.toneMappingExposure = 1
        renderer.shadowMap.enabled = true
        renderer.shadowMap.type = THREE.PCFSoftShadowMap

        scene.add(new THREE.HemisphereLight(0xe9f5ff, 0x443526, 2.1))
        const sun = new THREE.DirectionalLight(0xfff1d2, 3.2)
        sun.position.set(-3, 6, 5)
        sun.castShadow = true
        sun.shadow.mapSize.set(1024, 1024)
        sun.shadow.camera.left = -4
        sun.shadow.camera.right = 4
        sun.shadow.camera.top = 4
        sun.shadow.camera.bottom = -4
        sun.shadow.normalBias = .025
        scene.add(sun)

        const stage = new THREE.Group()
        scene.add(stage)

        const ground = new THREE.Mesh(
          new THREE.CylinderGeometry(2.28, 2.32, .12, 80),
          new THREE.MeshStandardMaterial({ color: 0xa79772, roughness: .96 }),
        )
        ground.position.set(-.3, -.07, 0)
        ground.receiveShadow = true
        stage.add(ground)

        // Individual boards give the shared floor a readable scale and depth.
        const seamMaterial = new THREE.MeshStandardMaterial({ color: 0x7e7158, roughness: 1 })
        for (let z = -2.08; z <= 2.08; z += .26) {
          const width = 2 * Math.sqrt(2.28 ** 2 - z ** 2)
          const seam = new THREE.Mesh(new THREE.BoxGeometry(width, .004, .012), seamMaterial)
          seam.position.set(-.3, -.007, z)
          stage.add(seam)
        }

        const tableTop = new THREE.Mesh(
          new THREE.CylinderGeometry(.72, .72, .08, 48),
          new THREE.MeshStandardMaterial({ color: 0x825033, roughness: .72 }),
        )
        tableTop.position.y = .64
        tableTop.castShadow = true
        tableTop.receiveShadow = true
        stage.add(tableTop)
        const tableLeg = new THREE.Mesh(
          new THREE.CylinderGeometry(.09, .14, .59, 24),
          new THREE.MeshStandardMaterial({ color: 0x38291f, roughness: .85 }),
        )
        tableLeg.position.y = .295
        tableLeg.castShadow = true
        stage.add(tableLeg)

        const loader = new GLTFLoader()
        loader.setMeshoptDecoder(MeshoptDecoder)
        const draco = new DRACOLoader()
        draco.setDecoderPath('/assets/bruno-runtime/draco/')
        loader.setDRACOLoader(draco)

        const placeModel = (model: Awaited<ReturnType<typeof loader.loadAsync>>, targetHeight: number, position: readonly [number, number, number]) => {
          const raw = model.scene
          raw.updateMatrixWorld(true)
          const firstBox = new THREE.Box3().setFromObject(raw)
          const height = Math.max(firstBox.getSize(new THREE.Vector3()).y, .001)
          raw.scale.setScalar(targetHeight / height)
          raw.updateMatrixWorld(true)
          const box = new THREE.Box3().setFromObject(raw)
          const center = box.getCenter(new THREE.Vector3())
          raw.position.set(-center.x, -box.min.y, -center.z)
          const pivot = new THREE.Group()
          pivot.add(raw)
          pivot.position.set(...position)
          if (Math.abs(position[0]) + Math.abs(position[2]) > .01) {
            // A local Y rotation keeps feet level even if the stage is translated.
            pivot.rotation.y = Math.atan2(-position[0], -position[2])
          }
          raw.traverse((node) => {
            if (node instanceof THREE.Mesh) {
              node.castShadow = true
              node.receiveShadow = true
            }
          })
          stage.add(pivot)
          return { pivot, raw }
        }

        const loadedPeople = await Promise.all(people.map(async (person) => ({
          person,
          gltf: await loader.loadAsync(person.url),
        })))
        if (disposed) {
          renderer.dispose()
          return
        }
        loadedPeople.forEach(({ person, gltf }) => {
          prepareCharacterShading(gltf.scene)
          placeModel(gltf, 1.4, person.position)
        })

        // A warm, abstract table spirit reads as an Agent without the uncanny valley
        // of another humanoid face competing with the four real participant avatars.
        const host = new THREE.Group()
        const glowMaterial = new THREE.MeshStandardMaterial({ color: 0xf5f2c9, emissive: 0x91b765, emissiveIntensity: .42, roughness: .55 })
        const hostBody = new THREE.Mesh(new THREE.SphereGeometry(.27, 40, 28), glowMaterial)
        hostBody.position.y = .39
        const hostBase = new THREE.Mesh(new THREE.CylinderGeometry(.18, .24, .12, 32), new THREE.MeshStandardMaterial({ color: 0x8ea66f, roughness: .8 }))
        hostBase.position.y = .12
        const eyeMaterial = new THREE.MeshBasicMaterial({ color: 0x315849 })
        for (const x of [-.075, .075]) {
          const eye = new THREE.Mesh(new THREE.SphereGeometry(.022, 16, 12), eyeMaterial)
          eye.position.set(x, .425, .252)
          host.add(eye)
        }
        host.add(hostBody, hostBase)
        host.position.set(0, 0, -1.3)
        hostBody.castShadow = true
        stage.add(host)

        const halo = new THREE.Mesh(
          new THREE.TorusGeometry(.26, .012, 12, 48),
          new THREE.MeshBasicMaterial({ color: 0xc7f06c, transparent: true, opacity: .7 }),
        )
        halo.rotation.x = Math.PI / 2
        halo.position.set(0, .012, -1.3)
        stage.add(halo)

        // The vehicle is decorative: render the people immediately and add it later.
        // Waiting for this 4 MB asset previously delayed the entire scene becoming ready.
        void loader.loadAsync('/scene/arrival-suv.glb').then((carGltf) => {
          if (disposed) {
            return
          }
          const car = placeModel(carGltf, .64, [-1.92, 0, .05])
          car.pivot.rotation.y = -.38
        }).catch(() => { /* The social scene remains complete without the parked SUV. */ })

        const controls = new OrbitControls(camera, canvas)
        controls.target.set(-.35, .62, 0)
        controls.enablePan = false
        controls.enableZoom = false
        controls.minPolarAngle = 1.04
        controls.maxPolarAngle = 1.2
        controls.minAzimuthAngle = -.28
        controls.maxAzimuthAngle = .28
        controls.autoRotate = false
        controls.enableDamping = true
        controls.dampingFactor = .05

        const resize = () => {
          const rect = canvas.getBoundingClientRect()
          renderer.setSize(Math.max(1, rect.width), Math.max(1, rect.height), false)
          const aspect = Math.max(1, rect.width) / Math.max(1, rect.height)
          const height = Math.max(3.75, 6.25 / aspect)
          camera.left = -height * aspect / 2
          camera.right = height * aspect / 2
          camera.top = height / 2
          camera.bottom = -height / 2
          camera.updateProjectionMatrix()
        }
        const observer = new ResizeObserver(resize)
        observer.observe(canvas)
        resize()

        const render = (time: number) => {
          if (disposed) return
          host.position.y = Math.sin(time * .0018) * .025
          halo.rotation.z = time * .00025
          controls.update()
          renderer.render(scene, camera)
          frame = window.requestAnimationFrame(render)
        }
        frame = window.requestAnimationFrame(render)
        setState('ready')

        const cleanup = () => {
          draco.dispose()
          observer.disconnect()
          controls.dispose()
          scene.traverse((node) => {
            const mesh = node as typeof node & { geometry?: { dispose(): void }; material?: { dispose(): void } | Array<{ dispose(): void }> }
            mesh.geometry?.dispose()
            if (Array.isArray(mesh.material)) mesh.material.forEach((material) => material.dispose())
            else mesh.material?.dispose()
          })
          renderer.dispose()
        }
        canvas.dataset.cleanupId = String(registerCleanup(cleanup))
      } catch (reason) {
        console.error('[LakeModelStage] failed to prepare supplied GLBs', reason)
        if (!disposed) setState('error')
      }
    })()

    return () => {
      disposed = true
      window.cancelAnimationFrame(frame)
      runCleanup(Number(canvas.dataset.cleanupId))
    }
  }, [viewer])

  return (
    <section className={`lake-model-stage is-${state}`} aria-label="瑞士湖边三维组局场景">
      <canvas ref={canvasRef} aria-label="可拖动查看四位人物、桌边 Agent 与抵达车辆的三维模型" />
      <div className="lake-model-stage-head">
        <span><i /> 湖边 · 等你入席</span>
        <em>{state === 'ready' ? '拖动观察' : state === 'error' ? '静态场景' : '正在载入人物'}</em>
      </div>
      <div className="lake-model-seat-labels" aria-hidden="true">
        <span>林夏 · 亲历</span><span>周砚 · 机会</span><span>程野 · 结构</span><span>你 · 真实立场</span>
      </div>
      {state === 'error' && <img src="/scene/swiss-lake.jpg" alt="湖边圆桌合影，三维场景暂时不可用" />}
    </section>
  )
}

const cleanups = new Map<number, () => void>()
let cleanupSequence = 0

function registerCleanup(cleanup: () => void) {
  cleanupSequence += 1
  cleanups.set(cleanupSequence, cleanup)
  return cleanupSequence
}

function runCleanup(id: number) {
  const cleanup = cleanups.get(id)
  cleanup?.()
  cleanups.delete(id)
}
