import { useEffect, useMemo, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import * as THREE from 'three'
import { DRACOLoader } from 'three/addons/loaders/DRACOLoader.js'
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js'
import { RoundedBoxGeometry } from 'three/addons/geometries/RoundedBoxGeometry.js'
import type { TagProfile } from '../onboarding/profileStore'
import type { DemoCaseLike } from './contract'
import './matchJourney.css'

const ROUTE_DURATION = 6_800
const PHASES = [
  { at: 0, eyebrow: '01 · 理解你', title: '把刚才的表达，变成找人的线索', note: '不是按相似度复制一个你，而是先确认你能带来什么。' },
  { at: 1_800, eyebrow: '02 · 补齐视角', title: '正在寻找能让讨论向前走的人', note: '保留话题交集，同时引入经验、技术与理论的差异。' },
  { at: 4_000, eyebrow: '03 · 前往桌边', title: '匹配完成，Agent 正在带你抵达', note: '桌边空间正在准备，即使 3D 资源较慢也不会阻塞入桌。' },
]

interface MatchJourneyProps {
  open: boolean
  profile: TagProfile | null
  demoCase: DemoCaseLike
  pending: boolean
  error: string | null
  onArrive(): void
  onBack(): void
}

function makeFallbackCar() {
  const car = new THREE.Group()
  const bodyMaterial = new THREE.MeshStandardMaterial({ color: 0xc9623e, roughness: .48, metalness: .08 })
  const trimMaterial = new THREE.MeshStandardMaterial({ color: 0x263d39, roughness: .56, metalness: .12 })
  const glassMaterial = new THREE.MeshStandardMaterial({ color: 0x5e8d8c, roughness: .18, metalness: .18 })
  const lightMaterial = new THREE.MeshStandardMaterial({ color: 0xfff0bb, emissive: 0xffd47d, emissiveIntensity: .8, roughness: .3 })
  const body = new THREE.Mesh(new RoundedBoxGeometry(1.72, .46, 3.08, 5, .16), bodyMaterial)
  body.position.y = .53
  const hood = new THREE.Mesh(new RoundedBoxGeometry(1.54, .22, .9, 4, .12), bodyMaterial)
  hood.position.set(0, .78, .96)
  const cabin = new THREE.Mesh(new RoundedBoxGeometry(1.46, .66, 1.55, 5, .16), glassMaterial)
  cabin.position.set(0, .93, -.22)
  const roof = new THREE.Mesh(new RoundedBoxGeometry(1.5, .12, 1.68, 4, .06), bodyMaterial)
  roof.position.set(0, 1.27, -.24)
  const bumper = new THREE.Mesh(new RoundedBoxGeometry(1.46, .14, .12, 3, .04), trimMaterial)
  bumper.position.set(0, .43, 1.57)
  car.add(body, hood, cabin, roof, bumper)
  for (const x of [-.51, .51]) {
    const lamp = new THREE.Mesh(new RoundedBoxGeometry(.3, .14, .045, 3, .035), lightMaterial)
    lamp.position.set(x, .62, 1.62)
    car.add(lamp)
  }
  for (const x of [-.55, .55]) {
    const rail = new THREE.Mesh(new THREE.CylinderGeometry(.025, .025, 1.45, 10), trimMaterial)
    rail.rotation.x = Math.PI / 2
    rail.position.set(x, 1.39, -.23)
    car.add(rail)
  }
  const wheelMaterial = new THREE.MeshStandardMaterial({ color: 0x182422, roughness: .9 })
  const hubMaterial = new THREE.MeshStandardMaterial({ color: 0xc5bca4, roughness: .45, metalness: .38 })
  for (const x of [-.86, .86]) for (const z of [-.92, .92]) {
    const wheel = new THREE.Mesh(new THREE.CylinderGeometry(.29, .29, .18, 16), wheelMaterial)
    wheel.rotation.z = Math.PI / 2
    wheel.position.set(x, .32, z)
    car.add(wheel)
    const hub = new THREE.Mesh(new THREE.CylinderGeometry(.13, .13, .185, 16), hubMaterial)
    hub.rotation.z = Math.PI / 2
    hub.position.set(x, .32, z)
    car.add(hub)
  }
  car.scale.setScalar(.7)
  return car
}

function makeRoad(curve: THREE.CatmullRomCurve3, width: number, color: number, y: number) {
  const segments = 90
  const positions: number[] = []
  const indices: number[] = []
  for (let index = 0; index <= segments; index += 1) {
    const t = index / segments
    const point = curve.getPointAt(t)
    const tangent = curve.getTangentAt(t).normalize()
    const side = new THREE.Vector3(-tangent.z, 0, tangent.x).multiplyScalar(width)
    positions.push(point.x + side.x, y, point.z + side.z)
    positions.push(point.x - side.x, y, point.z - side.z)
    if (index < segments) {
      const base = index * 2
      indices.push(base, base + 1, base + 2, base + 1, base + 3, base + 2)
    }
  }
  const geometry = new THREE.BufferGeometry()
  geometry.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3))
  geometry.setIndex(indices)
  geometry.computeVertexNormals()
  return new THREE.Mesh(geometry, new THREE.MeshStandardMaterial({ color, roughness: .94 }))
}

function makeRouteScenery() {
  const scenery = new THREE.Group()
  const trunkGeometry = new THREE.CylinderGeometry(.045, .065, .34, 7)
  const crownGeometry = new THREE.ConeGeometry(.28, .72, 9)
  const trunkMaterial = new THREE.MeshStandardMaterial({ color: 0x665440, roughness: 1 })
  const crownMaterial = new THREE.MeshStandardMaterial({ color: 0x315f4d, roughness: .95 })
  const treePositions = [
    [-6.4, -1.6, .9], [-5.9, -.5, 1.15], [-5.2, 3.6, .85], [-3.8, 3.5, 1.08],
    [-2.8, -2.6, .85], [-1.6, -3.4, 1.18], [.1, 2.7, .82], [2.5, 2.4, 1.1],
    [3.4, .9, .84], [4.1, -1.8, 1.2], [3.2, -4.4, .88], [2.6, -5.5, 1.05],
  ] as const
  const trunks = new THREE.InstancedMesh(trunkGeometry, trunkMaterial, treePositions.length)
  const crowns = new THREE.InstancedMesh(crownGeometry, crownMaterial, treePositions.length)
  const dummy = new THREE.Object3D()
  treePositions.forEach(([x, z, scale], index) => {
    dummy.position.set(x, .17 * scale, z)
    dummy.scale.setScalar(scale)
    dummy.updateMatrix()
    trunks.setMatrixAt(index, dummy.matrix)
    dummy.position.set(x, .69 * scale, z)
    dummy.updateMatrix()
    crowns.setMatrixAt(index, dummy.matrix)
  })
  trunks.instanceMatrix.needsUpdate = true
  crowns.instanceMatrix.needsUpdate = true
  scenery.add(trunks, crowns)

  const water = new THREE.Mesh(
    new THREE.CircleGeometry(3.3, 48),
    new THREE.MeshStandardMaterial({ color: 0x6ea5a0, roughness: .38, transparent: true, opacity: .5 }),
  )
  water.rotation.x = -Math.PI / 2
  water.scale.y = .55
  water.position.set(4.3, .015, 3.2)
  scenery.add(water)
  return scenery
}

function disposeObject(object: THREE.Object3D) {
  object.traverse((child) => {
    if (!(child instanceof THREE.Mesh)) return
    child.geometry?.dispose()
    const materials = Array.isArray(child.material) ? child.material : [child.material]
    materials.forEach((material) => material.dispose())
  })
}

export default function MatchJourney({ open, profile, demoCase, pending, error, onArrive, onBack }: MatchJourneyProps) {
  const canvas = useRef<HTMLCanvasElement>(null)
  const stage = useRef<HTMLDivElement>(null)
  const arrived = useRef(false)
  const arriveHandler = useRef(onArrive)
  const [phase, setPhase] = useState(0)
  const [elapsed, setElapsed] = useState(0)
  const [vehicleLoaded, setVehicleLoaded] = useState(false)

  const tags = useMemo(() => profile?.tags.filter((tag) => tag.visible).map((tag) => tag.label).slice(0, 5) ?? [], [profile])
  arriveHandler.current = onArrive

  useEffect(() => {
    if (!open) return
    arrived.current = false
    setPhase(0)
    setElapsed(0)
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    const duration = reduced ? 2_200 : ROUTE_DURATION
    const startedAt = performance.now()
    const ticker = window.setInterval(() => {
      const current = performance.now() - startedAt
      setElapsed(Math.min(current, duration))
      if (!reduced) setPhase(current >= PHASES[2].at ? 2 : current >= PHASES[1].at ? 1 : 0)
      else setPhase(current >= 1_000 ? 2 : 0)
      // Entering the table must never depend on a decorative GLB finishing its download.
      if (current >= duration && !arrived.current) {
        arrived.current = true
        window.clearInterval(ticker)
        arriveHandler.current()
      }
    }, 90)
    return () => window.clearInterval(ticker)
  }, [open])

  useEffect(() => {
    if (!open || !canvas.current || !stage.current) return
    const canvasElement = canvas.current
    const stageElement = stage.current
    let renderer: THREE.WebGLRenderer
    try {
      renderer = new THREE.WebGLRenderer({ canvas: canvasElement, antialias: true, alpha: true, powerPreference: 'high-performance' })
    } catch {
      return
    }
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.7))
    renderer.outputColorSpace = THREE.SRGBColorSpace
    renderer.toneMapping = THREE.ACESFilmicToneMapping
    renderer.toneMappingExposure = 1.05

    const scene = new THREE.Scene()
    scene.fog = new THREE.FogExp2(0xdde9df, .047)
    const camera = new THREE.PerspectiveCamera(36, 1, .1, 100)
    camera.position.set(0, 7.4, 11.2)
    camera.lookAt(.2, 0, -1.2)
    scene.add(new THREE.HemisphereLight(0xf2f8e9, 0x49695d, 2.6))
    const sun = new THREE.DirectionalLight(0xfff2d1, 3.1)
    sun.position.set(-4, 8, 6)
    scene.add(sun)

    const ground = new THREE.Mesh(
      new THREE.CircleGeometry(18, 64),
      new THREE.MeshStandardMaterial({ color: 0x8da88f, roughness: 1, transparent: true, opacity: .72 }),
    )
    ground.rotation.x = -Math.PI / 2
    ground.position.y = -.03
    scene.add(ground)

    const curve = new THREE.CatmullRomCurve3([
      new THREE.Vector3(-5.7, 0, 4.1),
      new THREE.Vector3(-4.1, 0, 1.9),
      new THREE.Vector3(-1.2, 0, 1.2),
      new THREE.Vector3(1.5, 0, -.7),
      new THREE.Vector3(1.1, 0, -4.8),
    ], false, 'catmullrom', .34)
    scene.add(makeRoad(curve, 1.56, 0xa3b297, .014))
    scene.add(makeRoad(curve, 1.28, 0x56625e, .028))
    scene.add(makeRouteScenery())
    const guidePoints = curve.getPoints(80).map((point) => point.clone().setY(.045))
    const guide = new THREE.Line(
      new THREE.BufferGeometry().setFromPoints(guidePoints),
      new THREE.LineDashedMaterial({ color: 0xfff9d8, dashSize: .26, gapSize: .18, transparent: true, opacity: .82 }),
    )
    guide.computeLineDistances()
    scene.add(guide)

    const tableMaterial = new THREE.MeshStandardMaterial({ color: 0xf6ead0, roughness: .86 })
    const ringMaterial = new THREE.MeshBasicMaterial({ color: 0xe5b96d, transparent: true, opacity: .8 })
    const table = new THREE.Group()
    const top = new THREE.Mesh(new THREE.CylinderGeometry(1.08, 1.08, .12, 32), tableMaterial)
    top.position.y = .68
    const stem = new THREE.Mesh(new THREE.CylinderGeometry(.13, .22, .68, 16), tableMaterial)
    stem.position.y = .32
    const ring = new THREE.Mesh(new THREE.RingGeometry(1.35, 1.48, 48), ringMaterial)
    ring.rotation.x = -Math.PI / 2
    ring.position.y = .04
    table.add(top, stem, ring)
    table.position.set(1.1, 0, -5.2)
    scene.add(table)

    const decoyMaterial = new THREE.MeshBasicMaterial({ color: 0xe8e9db, transparent: true, opacity: .5 })
    for (const position of [new THREE.Vector3(-4.9, .03, -3.1), new THREE.Vector3(5.1, .03, -.7)]) {
      const decoy = new THREE.Mesh(new THREE.RingGeometry(.42, .58, 32), decoyMaterial)
      decoy.rotation.x = -Math.PI / 2
      decoy.position.copy(position)
      scene.add(decoy)
    }

    const carRoot = new THREE.Group()
    const fallback = makeFallbackCar()
    carRoot.add(fallback)
    scene.add(carRoot)
    const loader = new GLTFLoader()
    const dracoLoader = new DRACOLoader()
    dracoLoader.setDecoderPath('/assets/bruno-runtime/draco/')
    dracoLoader.preload()
    loader.setDRACOLoader(dracoLoader)
    let cancelled = false
    loader.load('/scene/arrival-suv-lite.glb', (gltf) => {
      if (cancelled) return
      const model = gltf.scene
      const box = new THREE.Box3().setFromObject(model)
      const size = box.getSize(new THREE.Vector3())
      const center = box.getCenter(new THREE.Vector3())
      const scale = 2.45 / Math.max(size.x, size.z, .001)
      model.scale.setScalar(scale)
      model.position.set(-center.x * scale, -box.min.y * scale, -center.z * scale)
      carRoot.remove(fallback)
      disposeObject(fallback)
      carRoot.add(model)
      setVehicleLoaded(true)
    }, undefined, () => setVehicleLoaded(false))

    const clock = new THREE.Clock()
    let animationFrame = 0
    const resize = () => {
      const { width, height } = stageElement.getBoundingClientRect()
      if (!width || !height) return
      renderer.setSize(width, height, false)
      camera.aspect = width / height
      camera.updateProjectionMatrix()
    }
    const observer = new ResizeObserver(resize)
    observer.observe(stageElement)
    resize()
    const animate = () => {
      const seconds = clock.getElapsedTime()
      const t = Math.min(seconds / (ROUTE_DURATION / 1000), 1)
      const eased = 1 - Math.pow(1 - t, 3)
      const position = curve.getPointAt(eased)
      const tangent = curve.getTangentAt(Math.min(eased + .002, 1)).normalize()
      carRoot.position.copy(position)
      carRoot.position.y = .06 + Math.sin(seconds * 5) * .012
      carRoot.rotation.y = Math.atan2(tangent.x, tangent.z)
      ring.scale.setScalar(1 + Math.sin(seconds * 2.2) * .09)
      ringMaterial.opacity = .62 + Math.sin(seconds * 2.2) * .16
      renderer.render(scene, camera)
      animationFrame = window.requestAnimationFrame(animate)
    }
    animate()

    return () => {
      cancelled = true
      dracoLoader.dispose()
      observer.disconnect()
      window.cancelAnimationFrame(animationFrame)
      disposeObject(scene)
      renderer.dispose()
    }
  }, [open])

  useEffect(() => {
    // A failed request must unlock the retry button. Previously `arrived` stayed true,
    // making the visible "重新连接" action a no-op.
    if (error) arrived.current = false
  }, [error])

  if (!open) return null
  const activePhase = PHASES[phase]
  const progress = Math.min(100, (elapsed / ROUTE_DURATION) * 100)
  const goNow = () => {
    if (pending) return
    arrived.current = true
    arriveHandler.current()
  }

  return createPortal(
    <div className="match-journey-root">
      <div className="match-journey-photo" aria-hidden="true" />
      <header className="match-journey-head">
        <div className="match-journey-brand"><span>桌</span><div><b>组一桌</b><small>MATCH ROUTE</small></div></div>
        <div className="match-journey-status"><i />桌边 Agent 正在带路</div>
        <button type="button" onClick={onBack} disabled={pending}>返回修改</button>
      </header>

      <main className="match-journey-main">
        <section className="match-journey-copy" aria-live="polite">
          <p>{activePhase.eyebrow}</p>
          <h2>{activePhase.title}</h2>
          <span>{activePhase.note}</span>
          <div className="match-journey-tags">
            <small>从你的表达出发</small>
            {tags.map((tag) => <b key={tag}>#{tag}</b>)}
          </div>
        </section>

        <section ref={stage} className="match-journey-stage" aria-label="SUV 自动驶向匹配桌的三维路线">
          <canvas ref={canvas} />
          <div className="match-journey-map">
            <span className="is-table-one">桌 18</span>
            <span className="is-table-two">桌 27</span>
            <span className="is-table-target">城市与生活选择 <b>最佳匹配</b></span>
          </div>
          <div className="match-journey-model-note">{vehicleLoaded ? '精细 3D SUV · 自动驾驶中' : '轻量 3D SUV · 已经出发'}</div>
        </section>
      </main>

      <footer className="match-journey-footer">
        <div className="match-journey-route">
          {['理解你的真实需要', '补齐桌上不同视角', '抵达可继续认识的一桌'].map((label, index) => (
            <div className={phase >= index ? 'is-active' : ''} key={label}><i>{phase > index ? '✓' : index + 1}</i><span>{label}</span></div>
          ))}
          <em><i style={{ width: `${progress}%` }} /></em>
        </div>
        <div className="match-journey-action">
          <p><b>{demoCase.topic}</b><span>3 位预置演示桌友 · 桌上发言由模型实时生成</span></p>
          {error && <strong role="alert">{error}</strong>}
          <button type="button" disabled={pending} onClick={goNow}>{pending ? '正在打开桌边空间…' : error ? '再试一次，直接入桌' : phase === 2 ? '立即入桌' : '直接抵达'}</button>
        </div>
      </footer>
    </div>,
    document.body,
  )
}
