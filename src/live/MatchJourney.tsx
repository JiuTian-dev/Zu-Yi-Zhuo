import { useEffect, useMemo, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import * as THREE from 'three'
import { DRACOLoader } from 'three/addons/loaders/DRACOLoader.js'
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js'
import type { TagProfile } from '../onboarding/profileStore'
import type { DemoCaseLike } from './contract'
import './matchJourney.css'

const ROUTE_DURATION = 9_000
const PHASES = [
  { at: 0, eyebrow: '01 · 理解你', title: '把刚才的表达，变成找人的线索', note: '不是按相似度复制一个你，而是先确认你能带来什么。' },
  { at: 2_300, eyebrow: '02 · 补齐视角', title: '正在寻找能让讨论向前走的人', note: '保留话题交集，同时引入经验、技术与理论的差异。' },
  { at: 5_100, eyebrow: '03 · 前往桌边', title: '匹配完成，Agent 正在带你抵达', note: '到桌以后，你可以先围观，也可以带着身份牌加入。' },
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
  const bodyMaterial = new THREE.MeshStandardMaterial({ color: 0xf0d0a1, roughness: .7 })
  const glassMaterial = new THREE.MeshStandardMaterial({ color: 0x325952, roughness: .25, metalness: .15 })
  const body = new THREE.Mesh(new THREE.BoxGeometry(1.7, .38, 3.1), bodyMaterial)
  body.position.y = .48
  const cabin = new THREE.Mesh(new THREE.BoxGeometry(1.45, .55, 1.45), glassMaterial)
  cabin.position.set(0, .88, -.2)
  car.add(body, cabin)
  const wheelMaterial = new THREE.MeshStandardMaterial({ color: 0x182422, roughness: .9 })
  for (const x of [-.86, .86]) for (const z of [-.92, .92]) {
    const wheel = new THREE.Mesh(new THREE.CylinderGeometry(.29, .29, .18, 16), wheelMaterial)
    wheel.rotation.z = Math.PI / 2
    wheel.position.set(x, .32, z)
    car.add(wheel)
  }
  car.scale.setScalar(.7)
  return car
}

function makeRoad(curve: THREE.CatmullRomCurve3) {
  const segments = 90
  const width = 1.35
  const positions: number[] = []
  const indices: number[] = []
  for (let index = 0; index <= segments; index += 1) {
    const t = index / segments
    const point = curve.getPointAt(t)
    const tangent = curve.getTangentAt(t).normalize()
    const side = new THREE.Vector3(-tangent.z, 0, tangent.x).multiplyScalar(width)
    positions.push(point.x + side.x, .025, point.z + side.z)
    positions.push(point.x - side.x, .025, point.z - side.z)
    if (index < segments) {
      const base = index * 2
      indices.push(base, base + 1, base + 2, base + 1, base + 3, base + 2)
    }
  }
  const geometry = new THREE.BufferGeometry()
  geometry.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3))
  geometry.setIndex(indices)
  geometry.computeVertexNormals()
  return new THREE.Mesh(geometry, new THREE.MeshStandardMaterial({ color: 0xd8d3c2, roughness: 1, transparent: true, opacity: .9 }))
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
  const vehicleReady = useRef(false)
  const [phase, setPhase] = useState(0)
  const [elapsed, setElapsed] = useState(0)
  const [vehicleLoaded, setVehicleLoaded] = useState(false)

  const tags = useMemo(() => profile?.tags.filter((tag) => tag.visible).map((tag) => tag.label).slice(0, 5) ?? [], [profile])
  arriveHandler.current = onArrive

  useEffect(() => {
    if (!open) return
    arrived.current = false
    vehicleReady.current = false
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
      const waitedForVehicle = reduced || vehicleReady.current || current >= duration + 3_500
      if (current >= duration && waitedForVehicle && !arrived.current) {
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
    scene.add(makeRoad(curve))
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
    loader.load('/scene/arrival-suv.glb', (gltf) => {
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
      vehicleReady.current = true
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

  if (!open) return null
  const activePhase = PHASES[phase]
  const progress = Math.min(100, (elapsed / ROUTE_DURATION) * 100)
  const goNow = () => {
    if (arrived.current || pending) return
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
          <div className="match-journey-model-note">{vehicleLoaded ? '你的 3D SUV · 自动驾驶中' : '3D SUV 正在载入'}</div>
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
          <button type="button" disabled={pending} onClick={goNow}>{pending ? '正在打开桌边空间…' : error ? '重新连接这桌' : '直接抵达'}</button>
        </div>
      </footer>
    </div>,
    document.body,
  )
}
