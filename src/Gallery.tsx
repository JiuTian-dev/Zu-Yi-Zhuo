import { GlobalCanvas, ScrollScene, SmoothScrollbar, UseCanvas } from '@14islands/r3f-scroll-rig'
import { useTexture } from '@react-three/drei'
import { useEffect, useRef, useState, type MutableRefObject } from 'react'
import * as THREE from 'three'
import { galleryTables, type TableSummary } from './domain'
import './gallery.css'

interface GalleryProps { onEnter(table: TableSummary): void }

const vertexShader = `varying vec2 vUv; void main(){vUv=uv;gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.);}`
const fragmentShader = `
  uniform sampler2D map; uniform vec2 imageSize; uniform vec2 planeSize; uniform vec2 focus; varying vec2 vUv;
  void main(){
    float planeAspect=planeSize.x/planeSize.y, imageAspect=imageSize.x/imageSize.y;
    vec2 span=vec2(1.); if(planeAspect>imageAspect) span.y=imageAspect/planeAspect; else span.x=planeAspect/imageAspect;
    vec2 origin=clamp(focus-span*.5,vec2(0.),vec2(1.)-span);
    gl_FragColor=texture2D(map,origin+vUv*span);
    #include <tonemapping_fragment>
    #include <colorspace_fragment>
  }`

function GalleryPlane({ table, track }: { table: TableSummary; track: MutableRefObject<HTMLElement> }) {
  const texture = useTexture(table.sceneTexture)
  texture.colorSpace = THREE.SRGBColorSpace
  const image = texture.image as { width?: number; height?: number }
  return (
    <ScrollScene track={track} inViewportMargin="35%">
      {({ scale }) => (
        <mesh scale={scale}>
          <planeGeometry />
          <shaderMaterial
            uniforms={{
              map: { value: texture },
              imageSize: { value: new THREE.Vector2(image.width ?? 16, image.height ?? 9) },
              planeSize: { value: new THREE.Vector2(scale[0], scale[1]) },
              focus: { value: new THREE.Vector2(table.coverFocus.x, 1 - table.coverFocus.y) },
            }}
            vertexShader={vertexShader}
            fragmentShader={fragmentShader}
          />
        </mesh>
      )}
    </ScrollScene>
  )
}

function GalleryCard({ table, index, enhanced, forming, onEnter, onForming }: {
  table: TableSummary; index: number; enhanced: boolean
  forming: boolean; onEnter(table: TableSummary): void; onForming(table: TableSummary): void
}) {
  const mediaRef = useRef<HTMLDivElement>(null!)
  return (
    <article className={`gallery-card card-${index + 1}`}>
      <div className="gallery-media" ref={mediaRef}>
        <img src={table.sceneTexture} alt={`${table.hook}的场景`} loading={index ? 'lazy' : 'eager'} style={{ objectPosition: `${table.coverFocus.x * 100}% ${table.coverFocus.y * 100}%` }} />
      </div>
      {enhanced && <UseCanvas><GalleryPlane table={table} track={mediaRef as MutableRefObject<HTMLElement>} /></UseCanvas>}
      <div className="gallery-copy">
        <p><span>{String(index + 1).padStart(2, '0')}</span>{table.worldId === 'valley' ? '瑞士山谷' : table.worldId === 'campfire' ? '深夜篝火' : '午后 Workshop'} · {table.seatedCount} 人已入席</p>
        <h2>{table.hook}</h2>
        <small>{table.missingPerspective}</small>
        <button type="button" onClick={() => table.entryMode === 'immersive' ? onEnter(table) : onForming(table)}>
          {table.entryMode === 'immersive' ? '进入这桌' : forming ? '还在等合适的人' : '正在形成'} <i>↗</i>
        </button>
      </div>
    </article>
  )
}

function canEnhance() {
  if (!matchMedia('(pointer:fine)').matches || matchMedia('(prefers-reduced-motion: reduce)').matches) return false
  const canvas = document.createElement('canvas')
  const context = canvas.getContext('webgl2', { failIfMajorPerformanceCaveat: true }) ?? canvas.getContext('webgl')
  if (!context) return false
  context.getExtension('WEBGL_lose_context')?.loseContext()
  return true
}

export default function Gallery({ onEnter }: GalleryProps) {
  const [enhanced, setEnhanced] = useState(false)
  const [forming, setForming] = useState<string | null>(null)
  useEffect(() => {
    const previousPointerEvents = document.documentElement.style.pointerEvents
    document.documentElement.classList.add('gallery-mode'); document.body.classList.add('gallery-mode')
    setEnhanced(canEnhance())
    return () => {
      document.documentElement.style.pointerEvents = previousPointerEvents
      document.documentElement.classList.remove('gallery-mode', 'js-has-global-canvas', 'js-global-canvas-error', 'js-smooth-scrollbar-enabled', 'js-smooth-scrollbar-disabled')
      document.body.classList.remove('gallery-mode', 'ScrollRig-scrollWrapper')
    }
  }, [])
  return (
    <>
      {/* D8.1b boundary: this canvas exists only in gallery until the shared portal renderer lands. */}
      {enhanced && <><GlobalCanvas dpr={[1, 1.5]} gl={{ alpha: true, antialias: true }} onError={() => setEnhanced(false)} /><SmoothScrollbar config={{ duration: 1.15 }} /></>}
      <main className={`gallery-page ${enhanced ? 'is-enhanced' : ''}`}>
        <header className="gallery-header"><b>组一桌</b><span>把值得聊的话，交给刚好在场的人</span><em>ZH · 2026</em></header>
        <section className="gallery-intro"><p>正在发生的桌</p><h1>有些答案，<br />不在任何一个人那里。</h1><span>向下走近一场真实交流</span></section>
        <section className="gallery-list" aria-label="正在发生的桌">
          {galleryTables.map((table, index) => <GalleryCard key={table.id} table={table} index={index} enhanced={enhanced} forming={forming === table.id} onEnter={onEnter} onForming={(item) => setForming(item.id)} />)}
        </section>
        <p className="forming-note" role="status" aria-live="polite">{forming ? '这张桌还在等待合适的人，形成后会从这里亮起来。' : ''}</p>
        <footer className="gallery-footer"><span>不是浏览内容，是遇见一桌人。</span><span>三张桌 · 一个正在发生</span></footer>
      </main>
    </>
  )
}
