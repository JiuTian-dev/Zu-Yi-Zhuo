import { ScrollScene, SmoothScrollbar, UseCanvas, type ScrollSceneChildProps } from '@14islands/r3f-scroll-rig'
import { useTexture } from '@react-three/drei'
import { useFrame, useThree } from '@react-three/fiber'
import { useEffect, useLayoutEffect, useMemo, useRef, useState, type MutableRefObject } from 'react'
import * as THREE from 'three'
import { galleryTables, type TableSummary } from './domain'
import type { AppPhase } from './domain'
import { type GalleryFlowTextureRef } from './GalleryFlow'
import './gallery.css'

export interface GalleryMediaRect { left: number; top: number; width: number; height: number }

interface GalleryProps {
  onEnter(table: TableSummary, rect: GalleryMediaRect): void
  enhanced: boolean
  flowTexture: GalleryFlowTextureRef
  phase: AppPhase
  restoreScrollY: number
  returnFocusId: string | null
}

interface SmoothScrollbarHandle {
  scrollTo(target: number, options?: { immediate?: boolean; force?: boolean }): void
}

const MAX_WHEEL_STEP = 360

const vertexShader = `varying vec2 vUv; void main(){vUv=uv;gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.);}`
const fragmentShader = `
  uniform sampler2D map, flowMap; uniform vec2 imageSize, planeSize, focus, resolution; varying vec2 vUv;
  void main(){
    float planeAspect=planeSize.x/planeSize.y, imageAspect=imageSize.x/imageSize.y;
    vec2 span=vec2(1.); if(planeAspect>imageAspect) span.y=imageAspect/planeAspect; else span.x=planeAspect/imageAspect;
    vec2 origin=clamp(focus-span*.5,vec2(0.),vec2(1.)-span);
    vec2 screenUv=gl_FragCoord.xy/resolution;
    vec4 encoded=texture2D(flowMap,clamp(screenUv,vec2(0.),vec2(1.)));
    vec2 localUv=vUv+vec2(encoded.r-encoded.g,encoded.b-encoded.a)*.065;
    vec2 sampleUv=clamp(origin+localUv*span,origin+span*.002,origin+span*.998);
    gl_FragColor=texture2D(map,sampleUv);
    #include <tonemapping_fragment>
    #include <colorspace_fragment>
  }`

function FlowPlaneMesh({ table, texture, scale, flowTexture }: {
  table: TableSummary; texture: THREE.Texture
  scale: ScrollSceneChildProps['scale']; flowTexture: GalleryFlowTextureRef
}) {
  const material = useRef<THREE.ShaderMaterial>(null)
  const { gl } = useThree()
  const drawingSize = useMemo(() => new THREE.Vector2(), [])
  const image = texture.image as { width?: number; height?: number }
  const uniforms = useMemo(() => ({
    map: { value: texture }, flowMap: { value: flowTexture.current },
    imageSize: { value: new THREE.Vector2(image.width ?? 16, image.height ?? 9) },
    planeSize: { value: new THREE.Vector2(scale[0], scale[1]) },
    focus: { value: new THREE.Vector2(table.coverFocus.x, 1 - table.coverFocus.y) },
    resolution: { value: drawingSize },
  }), [drawingSize, flowTexture, image.height, image.width, scale, table.coverFocus.x, table.coverFocus.y, texture])
  useFrame(() => {
    if (!material.current) return
    material.current.uniforms.flowMap.value = flowTexture.current
    material.current.uniforms.planeSize.value.set(scale[0], scale[1])
    gl.getDrawingBufferSize(drawingSize)
  })
  return <mesh scale={scale}><planeGeometry /><shaderMaterial ref={material} uniforms={uniforms} vertexShader={vertexShader} fragmentShader={fragmentShader} /></mesh>
}

function GalleryPlane({ table, track, flowTexture }: { table: TableSummary; track: MutableRefObject<HTMLElement>; flowTexture: GalleryFlowTextureRef }) {
  const texture = useTexture(table.sceneTexture)
  texture.colorSpace = THREE.SRGBColorSpace
  return (
    <ScrollScene track={track} inViewportMargin="35%">
      {({ scale }) => <FlowPlaneMesh table={table} texture={texture} scale={scale} flowTexture={flowTexture} />}
    </ScrollScene>
  )
}

function GalleryCard({ table, index, enhanced, forming, flowTexture, onEnter, onForming }: {
  table: TableSummary; index: number; enhanced: boolean
  forming: boolean; flowTexture: GalleryFlowTextureRef
  onEnter(table: TableSummary, rect: GalleryMediaRect): void; onForming(table: TableSummary): void
}) {
  const mediaRef = useRef<HTMLDivElement>(null!)
  const enter = () => {
    if (table.entryMode !== 'immersive') return onForming(table)
    const { left, top, width, height } = mediaRef.current.getBoundingClientRect()
    onEnter(table, { left, top, width, height })
  }
  return (
    <article className={`gallery-card card-${index + 1}`}>
      <div className="gallery-media" ref={mediaRef}>
        <img src={table.sceneTexture} alt={`${table.hook}的场景`} loading={index ? 'lazy' : 'eager'} style={{ objectPosition: `${table.coverFocus.x * 100}% ${table.coverFocus.y * 100}%` }} />
      </div>
      {enhanced && <UseCanvas><GalleryPlane table={table} track={mediaRef as MutableRefObject<HTMLElement>} flowTexture={flowTexture} /></UseCanvas>}
      <div className="gallery-copy">
        <p><span>{String(index + 1).padStart(2, '0')}</span>{table.worldId === 'valley' ? '瑞士山谷' : table.worldId === 'campfire' ? '深夜篝火' : '午后 Workshop'} · {table.seatedCount} 人已入席</p>
        <h2>{table.hook}</h2>
        <small>{table.missingPerspective}</small>
        <button type="button" data-table-id={table.id} onClick={enter}>
          {table.entryMode === 'immersive' ? '进入这桌' : forming ? '还在等合适的人' : '正在形成'} <i>↗</i>
        </button>
      </div>
    </article>
  )
}

export default function Gallery({ onEnter, enhanced, flowTexture, phase, restoreScrollY, returnFocusId }: GalleryProps) {
  const [forming, setForming] = useState<string | null>(null)
  const scrollbarRef = useRef<SmoothScrollbarHandle | null>(null)
  const galleryActive = phase === 'gallery'
  useEffect(() => {
    const previousPointerEvents = document.documentElement.style.pointerEvents
    document.documentElement.classList.add('gallery-mode'); document.body.classList.add('gallery-mode')
    return () => {
      document.documentElement.style.pointerEvents = previousPointerEvents
      document.documentElement.classList.remove('gallery-mode', 'js-smooth-scrollbar-enabled', 'js-smooth-scrollbar-disabled')
      document.body.classList.remove('gallery-mode', 'ScrollRig-scrollWrapper')
    }
  }, [])
  useEffect(() => {
    document.documentElement.classList.toggle('gallery-transition', !galleryActive)
    document.body.classList.toggle('gallery-transition', !galleryActive)
    return () => {
      document.documentElement.classList.remove('gallery-transition')
      document.body.classList.remove('gallery-transition')
    }
  }, [galleryActive])
  useLayoutEffect(() => {
    if (!galleryActive || !returnFocusId) return
    const restore = () => {
      window.scrollTo({ top: restoreScrollY, behavior: 'auto' })
      scrollbarRef.current?.scrollTo(restoreScrollY, { immediate: true, force: true })
    }
    restore()
    const selector = `button[data-table-id="${CSS.escape(returnFocusId)}"]`
    const frame = requestAnimationFrame(() => {
      restore()
      document.querySelector<HTMLButtonElement>(selector)?.focus({ preventScroll: true })
    })
    return () => cancelAnimationFrame(frame)
  }, [galleryActive, restoreScrollY, returnFocusId])
  return (
    <>
      {enhanced && galleryActive && <SmoothScrollbar ref={scrollbarRef} config={{
        duration: .72,
        wheelMultiplier: 1,
        virtualScroll: (data: { deltaX: number; deltaY: number; event: WheelEvent | TouchEvent }) => {
          if (data.event instanceof WheelEvent) {
            data.deltaX = THREE.MathUtils.clamp(data.deltaX, -MAX_WHEEL_STEP, MAX_WHEEL_STEP)
            data.deltaY = THREE.MathUtils.clamp(data.deltaY, -MAX_WHEEL_STEP, MAX_WHEEL_STEP)
          }
          return true
        },
      }} />}
      <main className={`gallery-page is-${phase} ${enhanced && galleryActive ? 'is-enhanced' : ''}`} inert={!galleryActive}>
        <header className="gallery-header"><b>组一桌</b><span>把值得聊的话，交给刚好在场的人</span><em>ZH · 2026</em></header>
        <section className="gallery-intro"><p>正在发生的桌</p><h1>有些答案，<br />不在任何一个人那里。</h1><span>向下走近一场真实交流</span></section>
        <section className="gallery-list" aria-label="正在发生的桌">
          {galleryTables.map((table, index) => <GalleryCard key={table.id} table={table} index={index} enhanced={enhanced && galleryActive} forming={forming === table.id} flowTexture={flowTexture} onEnter={onEnter} onForming={(item) => setForming(item.id)} />)}
        </section>
        <p className="forming-note" role="status" aria-live="polite">{forming ? '这张桌还在等待合适的人，形成后会从这里亮起来。' : ''}</p>
        <footer className="gallery-footer"><span>不是浏览内容，是遇见一桌人。</span><span>三张桌 · 一个正在发生</span></footer>
      </main>
    </>
  )
}
