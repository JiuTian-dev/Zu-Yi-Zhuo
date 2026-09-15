import { useEffect, useRef, useState } from 'react'
import { getLiveState, useLive } from './live/store'
import { VIEWER_ID } from './live/identity'
import { attachRuntime, detachRuntime } from './bruno-runtime/runtimeController'

type RuntimeGame = {
  destroy?: () => void
  sceneBridge?: { apply?: (projection: unknown) => void }
  cameraOrbit?: { setEnabled?: (enabled: boolean) => void }
  ready?: Promise<unknown>
  rendering?: { renderer?: { setAnimationLoop?: (fn: null | ((t: number) => void)) => void }; render?: () => void }
  ticker?: { update?: (t: number) => void }
}

/**
 * Mounts the project table runtime once for the app shell.
 * Home↔match only toggles visibility — remounting WebGPU after destroy is unreliable.
 */
export default function TableWorld({ active }: { active: boolean }) {
  const [started, setStarted] = useState(active)
  useEffect(() => {
    if (active) setStarted(true)
  }, [active])
  return started ? <TableWorldRuntime active={active} /> : null
}

function TableWorldRuntime({ active }: { active: boolean }) {
  const holder = useRef<HTMLDivElement>(null)
  const gameRef = useRef<RuntimeGame | null>(null)
  const tableState = useLive((state) => state.tableState)
  const hostAction = useLive((state) => state.hostAction)
  const speakingId = useLive((state) => state.speakingId)
  const closeState = useLive((state) => state.closeState)

  useEffect(() => {
    const game = gameRef.current
    if (!active || !game) return
    game.sceneBridge?.apply?.({ tableState, hostAction, speakingId, closeState, viewerId: VIEWER_ID })
  }, [active, closeState, hostAction, speakingId, tableState])

  // Create once; destroy only when this component unmounts (leave app / full reload).
  useEffect(() => {
    const host = holder.current
    if (!host) return
    const canvas = host.querySelector('canvas.js-canvas') as HTMLCanvasElement | null
    if (!canvas) {
      host.setAttribute('data-runtime-state', 'error')
      return
    }

    let cancelled = false
    let game: RuntimeGame | null = null

    void (async () => {
      // @ts-expect-error Bruno runtime is intentionally kept as a JS rendering island.
      const { Game } = await import('./bruno-runtime/Game/Game.js')
      if (cancelled) return
      const instance = new Game({ domElement: host, canvasElement: canvas }) as RuntimeGame
      game = instance
      gameRef.current = instance
      try {
        await instance.ready
        if (cancelled || !host.isConnected) {
          try { instance.destroy?.() } catch { /* ignore */ }
          if (gameRef.current === instance) gameRef.current = null
          return
        }
        attachRuntime(instance)
        host.setAttribute('data-runtime-state', 'ready')
        const latest = getLiveState()
        instance.sceneBridge?.apply?.({
          tableState: latest.tableState,
          hostAction: latest.hostAction,
          speakingId: latest.speakingId,
          closeState: latest.closeState,
          viewerId: VIEWER_ID,
        })
        // If we booted while home was showing, park the loop until match is active.
        if (!host.dataset.keepAliveActive) {
          try { instance.rendering?.renderer?.setAnimationLoop?.(null) } catch { /* ignore */ }
          instance.cameraOrbit?.setEnabled?.(false)
        }
      } catch (reason) {
        console.error('[TableWorld] runtime failed', reason)
        if (!cancelled) host.setAttribute('data-runtime-state', 'error')
        try { instance.destroy?.() } catch { /* ignore */ }
        if (gameRef.current === instance) gameRef.current = null
      }
    })()

    return () => {
      cancelled = true
      const current = gameRef.current ?? game
      if (current) detachRuntime(current)
      try { current?.destroy?.() } catch { /* ignore */ }
      if (gameRef.current === current) gameRef.current = null
    }
  }, [])

  // Home↔match: show/hide + pause/resume without tearing down WebGPU.
  useEffect(() => {
    const host = holder.current
    const game = gameRef.current
    if (host) host.dataset.keepAliveActive = active ? '1' : ''
    if (!game?.rendering?.renderer) return

    if (active) {
      try {
        game.rendering.renderer.setAnimationLoop?.((elapsedTime: number) => {
          game.ticker?.update?.(elapsedTime)
        })
      } catch { /* ignore */ }
      game.cameraOrbit?.setEnabled?.(true)
      const latest = getLiveState()
      game.sceneBridge?.apply?.({
        tableState: latest.tableState,
        hostAction: latest.hostAction,
        speakingId: latest.speakingId,
        closeState: latest.closeState,
        viewerId: VIEWER_ID,
      })
    } else {
      try { game.rendering.renderer.setAnimationLoop?.(null) } catch { /* ignore */ }
      game.cameraOrbit?.setEnabled?.(false)
    }
  }, [active])

  return (
    <div
      ref={holder}
      className="bruno-runtime-canvas"
      data-runtime-state="loading"
      aria-hidden={!active}
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: active ? 0 : -1,
        background: '#0a0f1c',
        visibility: active ? 'visible' : 'hidden',
        pointerEvents: active ? 'auto' : 'none',
      }}
    >
      <canvas className="js-canvas" style={{ width: '100%', height: '100%', display: 'block' }} />
    </div>
  )
}
