import { useFrame, useThree } from '@react-three/fiber'
import { useEffect, useMemo, useRef, type MutableRefObject } from 'react'
import * as THREE from 'three'

export type GalleryFlowTextureRef = MutableRefObject<THREE.Texture | null>

interface GalleryFlowProps {
  textureRef: GalleryFlowTextureRef
  reducedMotion?: boolean
}

const flowVertex = `varying vec2 vUv;void main(){vUv=uv;gl_Position=vec4(position.xy,0.,1.);}`
const flowFragment = `
  uniform sampler2D previous; uniform vec2 point; uniform vec2 velocity; uniform float decay; varying vec2 vUv;
  void main(){
    vec4 flow=max(texture2D(previous,vUv)*decay-vec4(.6/255.),vec4(0.));
    float splat=exp(-dot(vUv-point,vUv-point)/.0045);
    flow+=splat*vec4(max(velocity.x,0.),max(-velocity.x,0.),max(velocity.y,0.),max(-velocity.y,0.));
    gl_FragColor=clamp(flow,0.,1.);
  }`

export default function GalleryFlow({ textureRef, reducedMotion = false }: GalleryFlowProps) {
  const { gl } = useThree()
  const pointer = useRef({ x: .5, y: .5, px: .5, py: .5, time: 0, vx: 0, vy: 0, pending: false })
  const flow = useMemo(() => {
    const options: THREE.RenderTargetOptions = {
      format: THREE.RGBAFormat, type: THREE.UnsignedByteType,
      minFilter: THREE.LinearFilter, magFilter: THREE.LinearFilter,
      depthBuffer: false, stencilBuffer: false,
    }
    const scene = new THREE.Scene()
    const camera = new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 1)
    const geometry = new THREE.PlaneGeometry(2, 2)
    const read = new THREE.WebGLRenderTarget(128, 128, options)
    const write = new THREE.WebGLRenderTarget(128, 128, options)
    const material = new THREE.ShaderMaterial({
      vertexShader: flowVertex, fragmentShader: flowFragment,
      uniforms: {
        previous: { value: read.texture }, point: { value: new THREE.Vector2(.5, .5) },
        velocity: { value: new THREE.Vector2() }, decay: { value: 0 },
      },
      depthTest: false, depthWrite: false,
    })
    scene.add(new THREE.Mesh(geometry, material))
    return { scene, camera, geometry, material, read, write }
  }, [])

  useEffect(() => {
    const previousTarget = gl.getRenderTarget(), previousColor = gl.getClearColor(new THREE.Color()).clone()
    const previousAlpha = gl.getClearAlpha()
    gl.setClearColor(0x000000, 0)
    gl.setRenderTarget(flow.read); gl.clear(true, false, false)
    gl.setRenderTarget(flow.write); gl.clear(true, false, false)
    gl.setRenderTarget(previousTarget); gl.setClearColor(previousColor, previousAlpha)
    textureRef.current = flow.read.texture
    return () => {
      if (textureRef.current === flow.read.texture || textureRef.current === flow.write.texture) textureRef.current = null
      flow.read.dispose(); flow.write.dispose(); flow.material.dispose(); flow.geometry.dispose()
    }
  }, [flow, gl, textureRef])

  useEffect(() => {
    const stop = () => { pointer.current.pending = false; pointer.current.vx = 0; pointer.current.vy = 0 }
    const move = (event: PointerEvent) => {
      const now = performance.now(), x = event.clientX / innerWidth, y = 1 - event.clientY / innerHeight
      const dt = Math.max(8, now - pointer.current.time)
      if (pointer.current.time) {
        pointer.current.vx = THREE.MathUtils.clamp((x - pointer.current.px) * 16.67 / dt, -.1, .1)
        pointer.current.vy = THREE.MathUtils.clamp((y - pointer.current.py) * 16.67 / dt, -.1, .1)
        pointer.current.pending = true
      }
      Object.assign(pointer.current, { x, y, px: x, py: y, time: now })
    }
    const leave = (event: PointerEvent) => { if (!event.relatedTarget) stop() }
    window.addEventListener('pointermove', move, { passive: true }); window.addEventListener('pointerout', leave); window.addEventListener('blur', stop)
    return () => { window.removeEventListener('pointermove', move); window.removeEventListener('pointerout', leave); window.removeEventListener('blur', stop) }
  }, [])

  useFrame((_, delta) => {
    const previousTarget = gl.getRenderTarget(), previousAutoClear = gl.autoClear
    const impulse = !reducedMotion && pointer.current.pending
    flow.material.uniforms.previous.value = flow.read.texture
    flow.material.uniforms.point.value.set(pointer.current.x, pointer.current.y)
    flow.material.uniforms.velocity.value.set(impulse ? pointer.current.vx : 0, impulse ? pointer.current.vy : 0)
    flow.material.uniforms.decay.value = Math.exp(-delta * 5.2)
    pointer.current.pending = false
    gl.autoClear = false; gl.setRenderTarget(flow.write); gl.render(flow.scene, flow.camera)
    gl.setRenderTarget(previousTarget); gl.autoClear = previousAutoClear
    const next = flow.read; flow.read = flow.write; flow.write = next
    textureRef.current = flow.read.texture
  }, -100)
  return null
}
