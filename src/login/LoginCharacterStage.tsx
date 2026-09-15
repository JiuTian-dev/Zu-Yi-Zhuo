import { useEffect, useRef, useState } from 'react'
import type { AvatarCharacter } from '../home/accountStore'
import { prepareCharacterShading } from '../live/modelShading'

const CHARACTERS: AvatarCharacter[] = ['blue', 'orange', 'white', 'green']

/** Real GLBs: the chosen character steps forward while the other three stay visible. */
export default function LoginCharacterStage({ selected }: { selected: AvatarCharacter }) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const selectedRef = useRef(selected)
  const [ready, setReady] = useState(false)
  const [failed, setFailed] = useState(false)
  selectedRef.current = selected

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    let cancelled = false
    let frame = 0
    let dispose = () => {}
    void (async () => {
      const THREE = await import('three')
      const [{ GLTFLoader }, { MeshoptDecoder }, { OrbitControls }, { RoomEnvironment }] = await Promise.all([
        import('three/addons/loaders/GLTFLoader.js'),
        import('three/addons/libs/meshopt_decoder.module.js'),
        import('three/addons/controls/OrbitControls.js'),
        import('three/addons/environments/RoomEnvironment.js'),
      ])
      if (cancelled) return
      const renderer = new THREE.WebGLRenderer({ canvas, alpha: true, antialias: true })
      renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
      renderer.outputColorSpace = THREE.SRGBColorSpace
      renderer.toneMapping = THREE.ACESFilmicToneMapping
      renderer.toneMappingExposure = .88
      renderer.shadowMap.enabled = true
      renderer.shadowMap.type = THREE.PCFSoftShadowMap
      const scene = new THREE.Scene()
      const studio = new RoomEnvironment()
      const pmrem = new THREE.PMREMGenerator(renderer)
      const environment = pmrem.fromScene(studio, .06)
      studio.dispose()
      pmrem.dispose()
      scene.environment = environment.texture
      scene.environmentIntensity = .32
      scene.add(new THREE.HemisphereLight(0xfffaf4, 0x8e998c, 1.35))
      const light = new THREE.DirectionalLight(0xfff4e8, 1.65)
      light.position.set(-3, 5, 6)
      light.castShadow = true
      light.shadow.mapSize.set(1024, 1024)
      Object.assign(light.shadow.camera, { left: -4, right: 4, top: 4, bottom: -4, near: .1, far: 20 })
      light.shadow.normalBias = .035
      light.shadow.radius = 3
      scene.add(light)
      const rim = new THREE.DirectionalLight(0xd5e9ff, .85)
      rim.position.set(3, 4, -3)
      scene.add(rim)
      const floor = new THREE.Mesh(new THREE.PlaneGeometry(14, 10), new THREE.ShadowMaterial({ opacity: .18 }))
      floor.rotation.x = -Math.PI / 2
      floor.position.y = -.015
      floor.receiveShadow = true
      scene.add(floor)
      const camera = new THREE.OrthographicCamera(-2.8, 2.8, 1.8, -1.8, .1, 50)
      camera.position.set(0, 2.5, 9)
      const controls = new OrbitControls(camera, canvas)
      controls.target.set(0, 1.1, 0)
      controls.enablePan = false
      controls.enableZoom = false
      controls.enableDamping = true
      controls.minAzimuthAngle = -.22
      controls.maxAzimuthAngle = .22
      controls.minPolarAngle = 1.36
      controls.maxPolarAngle = 1.48
      const resize = () => {
        const { width, height } = canvas.getBoundingClientRect()
        const aspect = Math.max(1, width) / Math.max(1, height)
        const span = Math.max(2.55, 4.45 / aspect)
        camera.left = -span * aspect / 2
        camera.right = span * aspect / 2
        camera.top = span / 2
        camera.bottom = -span / 2
        camera.updateProjectionMatrix()
        renderer.setSize(Math.max(1, width), Math.max(1, height), false)
      }
      const observer = new ResizeObserver(resize)
      observer.observe(canvas)
      resize()
      const disposeObject = (root: InstanceType<typeof THREE.Object3D>) => {
        root.traverse((node) => {
          if (!(node instanceof THREE.Mesh)) return
          node.geometry.dispose()
          const materials = Array.isArray(node.material) ? node.material : [node.material]
          materials.forEach((material) => {
            for (const value of Object.values(material)) if (value instanceof THREE.Texture) value.dispose()
            material.dispose()
          })
        })
      }
      dispose = () => { observer.disconnect(); controls.dispose(); light.shadow.dispose(); environment.dispose(); disposeObject(scene); renderer.dispose() }
      const loader = new GLTFLoader()
      loader.setMeshoptDecoder(MeshoptDecoder)
      const figures = await Promise.all(CHARACTERS.map(async (character, index) => {
        const gltf = await loader.loadAsync('/scene/avatar-' + character + '-hd.glb')
        if (cancelled) { disposeObject(gltf.scene); return null }
        const model = gltf.scene
        prepareCharacterShading(model)
        model.traverse((node) => { if (node instanceof THREE.Mesh) { node.castShadow = true; node.receiveShadow = true } })
        model.updateMatrixWorld(true)
        const box = new THREE.Box3().setFromObject(model)
        const scale = 1.8 / Math.max(box.getSize(new THREE.Vector3()).y, .001)
        const center = box.getCenter(new THREE.Vector3())
        model.scale.setScalar(scale)
        model.position.set(-center.x * scale, -box.min.y * scale, -center.z * scale)
        const pivot = new THREE.Group()
        pivot.position.x = (index - 1.5) * 1.03
        pivot.add(model)
        scene.add(pivot)
        const shadow = new THREE.Mesh(new THREE.CircleGeometry(.34, 40), new THREE.MeshBasicMaterial({ color: 0x365746, transparent: true, opacity: .12, depthWrite: false }))
        shadow.rotation.x = -Math.PI / 2
        shadow.scale.set(1.2, .65, 1)
        shadow.position.set(pivot.position.x, -.01, 0)
        scene.add(shadow)
        return { character, pivot, shadow }
      }))
      if (cancelled) return
      const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches
      let last = performance.now()
      const scaleTarget = new THREE.Vector3()
      const draw = (time: number) => {
        if (cancelled) return
        const blend = reduced ? 1 : 1 - Math.exp(-Math.min((time - last) / 1000, .05) * 9)
        last = time
        figures.forEach((figure) => {
          if (!figure) return
          const active = figure.character === selectedRef.current
          const scale = active ? 1.12 : .98
          figure.pivot.scale.lerp(scaleTarget.setScalar(scale), blend)
          figure.pivot.position.z += ((active ? .38 : -.08) - figure.pivot.position.z) * blend
          const idle = reduced ? 0 : Math.sin(time * .0007 + CHARACTERS.indexOf(figure.character)) * .035
          figure.pivot.rotation.y += ((active ? -.12 : -figure.pivot.position.x * .085) + idle - figure.pivot.rotation.y) * blend
          figure.shadow.position.z = figure.pivot.position.z
        })
        controls.update()
        renderer.render(scene, camera)
        frame = requestAnimationFrame(draw)
      }
      frame = requestAnimationFrame(draw)
      setReady(true)
    })().catch((error) => {
      if (cancelled) return
      cancelled = true
      dispose()
      console.error('[LoginCharacterStage]', error)
      setFailed(true)
    })
    return () => { cancelled = true; cancelAnimationFrame(frame); dispose() }
  }, [])

  return <div className={'login-characters ' + (ready ? 'is-ready' : '')}>
    {!ready && <img src="/scene/login-cast.png" alt="四位可选择的人物形象" />}
    <canvas ref={canvasRef} aria-label="四位人物的 3D 预览，选中的人物站在前排，可拖动查看" />
    <span className="login-3d-hint">{failed ? '3D 暂不可用 · 当前为形象合照' : ready ? 'LIVE 3D · 高清人物' : '正在载入高清 3D 人物…'}</span>
  </div>
}
