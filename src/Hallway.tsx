import { UseCanvas } from '@14islands/r3f-scroll-rig'
import { useTexture } from '@react-three/drei'
import { useFrame, useThree } from '@react-three/fiber'
import gsap from 'gsap'
import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import * as THREE from 'three'
import { galleryTables, type TableSummary } from './domain'
import type { AppPhase } from './domain'
import { type GalleryFlowTextureRef } from './GalleryFlow'
import './gallery.css'

export interface GalleryMediaRect { left: number; top: number; width: number; height: number }

interface HallwayProps {
  onEnter(table: TableSummary, rect: GalleryMediaRect): void
  enhanced: boolean
  flowTexture: GalleryFlowTextureRef
  phase: AppPhase
  returnFocusId: string | null
}

const worldLabel = (worldId: TableSummary['worldId']) =>
  worldId === 'valley' ? '瑞士山谷' : worldId === 'campfire' ? '深夜篝火' : '午后 Workshop'

const SWITCH_COOLDOWN_MS = 1050
const WHEEL_STEP_THRESHOLD = 90

/** Shared mutable state for the canvas subtree: UseCanvas portals may not
 *  re-render on parent updates, so table switches travel outside React. */
const hallwayState = { index: 0 }

const backdropVertex = `varying vec2 vUv; void main(){vUv=uv;gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.);}`
const backdropFragment = `
  uniform sampler2D mapA, mapB, flowMap; uniform vec2 focusA, focusB, imageSize, planeSize, resolution;
  uniform float progress; varying vec2 vUv;
  vec4 samplePlate(sampler2D map, vec2 focus, vec2 uv, float zoom){
    float planeAspect=planeSize.x/planeSize.y, imageAspect=imageSize.x/imageSize.y;
    vec2 span=vec2(1.); if(planeAspect>imageAspect) span.y=imageAspect/planeAspect; else span.x=planeAspect/imageAspect;
    span/=zoom;
    vec2 origin=clamp(focus-span*.5,vec2(0.),vec2(1.)-span);
    vec2 screenUv=gl_FragCoord.xy/resolution;
    vec4 encoded=texture2D(flowMap,clamp(screenUv,vec2(0.),vec2(1.)));
    vec2 localUv=uv+vec2(encoded.r-encoded.g,encoded.b-encoded.a)*.05;
    vec2 sampleUv=clamp(origin+localUv*span,origin+span*.002,origin+span*.998);
    return texture2D(map,sampleUv);
  }
  void main(){
    float eased=progress*progress*(3.-2.*progress);
    vec4 a=samplePlate(mapA,focusA,vUv,1.+eased*.045);
    vec4 b=samplePlate(mapB,focusB,vUv,1.+(1.-eased)*.045);
    vec4 c=mix(a,b,smoothstep(0.,1.,eased));
    gl_FragColor=c;
    #include <tonemapping_fragment>
    #include <colorspace_fragment>
  }`

function HallwayBackdrop({ tables, flowTexture, reducedMotion }: {
  tables: TableSummary[]
  flowTexture: GalleryFlowTextureRef
  reducedMotion: boolean
}) {
  const material = useRef<THREE.ShaderMaterial>(null)
  const { viewport, gl } = useThree()
  const drawingSize = useMemo(() => new THREE.Vector2(), [])
  const urls = useMemo(() => [...new Set(tables.map((table) => table.sceneTexture))], [tables])
  const loaded = useTexture(urls)
  const textureMap = useMemo(() => {
    const list = Array.isArray(loaded) ? loaded : [loaded]
    return new Map(urls.map((url, i) => [url, list[i]]))
  }, [loaded, urls])

  const shown = useRef(0)
  const progress = useRef({ value: 0 })
  const tween = useRef<gsap.core.Tween | null>(null)

  const uniforms = useMemo(() => {
    const start = tables[0]
    return {
      mapA: { value: textureMap.get(start.sceneTexture) },
      mapB: { value: textureMap.get(start.sceneTexture) },
      focusA: { value: new THREE.Vector2(start.coverFocus.x, 1 - start.coverFocus.y) },
      focusB: { value: new THREE.Vector2(start.coverFocus.x, 1 - start.coverFocus.y) },
      imageSize: { value: new THREE.Vector2(1672, 941) },
      planeSize: { value: new THREE.Vector2(1, 1) },
      resolution: { value: drawingSize },
      flowMap: { value: flowTexture.current },
      progress: { value: 0 },
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [drawingSize, flowTexture, textureMap])

  useEffect(() => {
    for (const texture of textureMap.values()) texture.colorSpace = THREE.SRGBColorSpace
  }, [textureMap])

  useEffect(() => () => { tween.current?.kill() }, [])

  useFrame(() => {
    if (!material.current) return
    const u = material.current.uniforms
    material.current.uniforms.planeSize.value.set(viewport.width, viewport.height)
    material.current.uniforms.flowMap.value = flowTexture.current
    gl.getDrawingBufferSize(drawingSize)

    if (shown.current === hallwayState.index) return
    const target = tables[hallwayState.index]
    if (!target) return
    shown.current = hallwayState.index
    tween.current?.kill()
    u.mapB.value = textureMap.get(target.sceneTexture)
    u.focusB.value.set(target.coverFocus.x, 1 - target.coverFocus.y)
    const swap = () => {
      u.mapA.value = u.mapB.value
      u.focusA.value.copy(u.focusB.value)
      progress.current.value = 0
      u.progress.value = 0
    }
    if (reducedMotion) {
      progress.current.value = 1
      u.progress.value = 1
      swap()
    } else {
      tween.current = gsap.to(progress.current, {
        value: 1, duration: .95, ease: 'power2.inOut',
        onUpdate: () => { u.progress.value = progress.current.value },
        onComplete: swap,
      })
    }
  })

  return (
    <mesh scale={[viewport.width, viewport.height, 1]}>
      <planeGeometry />
      <shaderMaterial ref={material} uniforms={uniforms} vertexShader={backdropVertex} fragmentShader={backdropFragment} />
    </mesh>
  )
}

export default function Hallway({ onEnter, enhanced, flowTexture, phase, returnFocusId }: HallwayProps) {
  const [index, setIndex] = useState(0)
  const [forming, setForming] = useState(false)
  const mediaRef = useRef<HTMLDivElement>(null!)
  const cooldown = useRef(0)
  const wheelDelta = useRef(0)
  const galleryActive = phase === 'gallery'
  const featured = galleryTables[index]
  const prev = index > 0 ? galleryTables[index - 1] : null
  const next = index < galleryTables.length - 1 ? galleryTables[index + 1] : null
  const reducedMotion = useMemo(
    () => window.matchMedia('(prefers-reduced-motion: reduce)').matches, [],
  )

  useEffect(() => {
    document.documentElement.classList.add('hallway-mode'); document.body.classList.add('hallway-mode')
    return () => {
      document.documentElement.classList.remove('hallway-mode', 'gallery-transition')
      document.body.classList.remove('hallway-mode', 'gallery-transition')
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

  const switchTo = (target: number) => {
    if (!galleryActive || target < 0 || target >= galleryTables.length) return
    if (Date.now() < cooldown.current) return
    cooldown.current = Date.now() + SWITCH_COOLDOWN_MS
    setForming(false)
    hallwayState.index = target
    setIndex(target)
  }

  useEffect(() => {
    if (!galleryActive) return
    const onWheel = (event: WheelEvent) => {
      wheelDelta.current = THREE.MathUtils.clamp(wheelDelta.current + event.deltaY, -240, 240)
      if (Math.abs(wheelDelta.current) >= WHEEL_STEP_THRESHOLD) {
        switchTo(index + (wheelDelta.current > 0 ? 1 : -1))
        wheelDelta.current = 0
      }
    }
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'ArrowRight' || event.key === 'ArrowDown') switchTo(index + 1)
      else if (event.key === 'ArrowLeft' || event.key === 'ArrowUp') switchTo(index - 1)
    }
    window.addEventListener('wheel', onWheel, { passive: true })
    window.addEventListener('keydown', onKey)
    return () => {
      window.removeEventListener('wheel', onWheel)
      window.removeEventListener('keydown', onKey)
      wheelDelta.current = 0
    }
  }, [galleryActive, index])

  useLayoutEffect(() => {
    if (!galleryActive || !returnFocusId) return
    const frame = requestAnimationFrame(() => {
      document.querySelector<HTMLButtonElement>(`button[data-table-id="${CSS.escape(returnFocusId)}"]`)
        ?.focus({ preventScroll: true })
    })
    return () => cancelAnimationFrame(frame)
  }, [galleryActive, returnFocusId])

  const enter = () => {
    if (featured.entryMode !== 'immersive') {
      setForming(true)
      return
    }
    const { left, top, width, height } = mediaRef.current.getBoundingClientRect()
    onEnter(featured, { left, top, width, height })
  }

  return (
    <main className={`hallway-page is-${phase} ${enhanced ? 'is-enhanced' : ''}`} data-world={featured.worldId} inert={!galleryActive}>
      <div className="hallway-veil" aria-hidden="true" />
      {enhanced && galleryActive && <UseCanvas><HallwayBackdrop tables={galleryTables} flowTexture={flowTexture} reducedMotion={reducedMotion} /></UseCanvas>}

      <header className="hallway-header">
        <div className="hallway-brand"><b>组一桌</b><span>把值得聊的话，交给刚好在场的人</span></div>
        <em>ZH · 2026</em>
      </header>

      <button className={`hallway-beacon hallway-beacon-prev ${prev ? '' : 'is-edge'}`} type="button" onClick={() => switchTo(index - 1)} disabled={!prev || !galleryActive}>
        {prev && <><i data-world={prev.worldId} /><span><small>{worldLabel(prev.worldId)} · {prev.seatedCount} 人</small><b>{prev.hook}</b></span></>}
      </button>
      <button className={`hallway-beacon hallway-beacon-next ${next ? '' : 'is-edge'}`} type="button" onClick={() => switchTo(index + 1)} disabled={!next || !galleryActive}>
        {next && <><i data-world={next.worldId} /><span><small>{worldLabel(next.worldId)} · {next.seatedCount} 人</small><b>{next.hook}</b></span></>}
      </button>

      <section className="hallway-featured" aria-labelledby="hallway-title">
        <div className="hallway-copy">
          <p className="hallway-kicker"><span>{String(index + 1).padStart(2, '0')}</span>{worldLabel(featured.worldId)} · {featured.seatedCount} 人已入席</p>
          <h1 id="hallway-title">{featured.hook}</h1>
          <p className="hallway-missing">{featured.missingPerspective}</p>
          {featured.recommendedBecause && (
            <p className="hallway-recommend"><small>为什么想到你</small>{featured.recommendedBecause}</p>
          )}
          <button className="hallway-cta" type="button" data-table-id={featured.id} onClick={enter} disabled={!galleryActive}>
            {featured.entryMode === 'immersive' ? '坐下来看看' : forming ? '还在等合适的人' : '正在形成'} <i>→</i>
          </button>
          <p className="hallway-forming" role="status" aria-live="polite">{forming && featured.entryMode !== 'immersive' ? '这张桌还在等待合适的人，形成后会从这里亮起来。' : ''}</p>
        </div>
        <div className="hallway-thumb" ref={mediaRef} aria-hidden="true">
          <img src={featured.sceneTexture} alt="" style={{ objectPosition: `${featured.coverFocus.x * 100}% ${featured.coverFocus.y * 100}%` }} />
        </div>
      </section>

      <footer className="hallway-footer">
        <span>滚轮或 ← → 切换下一桌</span>
        <div className="hallway-dots">
          {galleryTables.map((table, dot) => (
            <button key={table.id} type="button" className={dot === index ? 'is-active' : ''} aria-label={`第 ${dot + 1} 桌：${table.hook}`} onClick={() => switchTo(dot)} disabled={!galleryActive} />
          ))}
        </div>
        <span>{String(index + 1).padStart(2, '0')} / {String(galleryTables.length).padStart(2, '0')}</span>
      </footer>
      <div className="sr-only" role="status" aria-live="polite">当前主桌：{featured.hook}，{worldLabel(featured.worldId)}，{featured.seatedCount} 人已入席</div>
    </main>
  )
}
