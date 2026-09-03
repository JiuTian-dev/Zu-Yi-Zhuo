import { useEffect, useRef } from 'react'
import { useLive } from './live/store'
import { VIEWER_ID } from './live/identity'
import { attachRuntime, detachRuntime } from './bruno-runtime/runtimeController'

/**
 * Mounts the project table runtime. The runtime owns only the round-table
 * world; React owns the surrounding HUD and conversation controls.
 */
export default function TableWorld({ active }: { active: boolean }) {
  const holder = useRef<HTMLDivElement>(null)
  const gameRef = useRef<{ destroy?: () => void; sceneBridge?: { apply?: (projection: unknown) => void }; cameraOrbit?: { setEnabled?: (enabled: boolean) => void } } | null>(null)
  const tableState = useLive((state) => state.tableState)
  const hostAction = useLive((state) => state.hostAction)
  const speakingId = useLive((state) => state.speakingId)
  const closeState = useLive((state) => state.closeState)

  useEffect(() => {
    const game = gameRef.current
    game?.sceneBridge?.apply?.({ tableState, hostAction, speakingId, closeState, viewerId: VIEWER_ID })
  }, [closeState, hostAction, speakingId, tableState])

  useEffect(() => {
    if (!active || !holder.current) return
    let cancelled = false
    void (async () => {
      // @ts-expect-error Bruno runtime is intentionally kept as a JS rendering island.
      const { Game } = await import('./bruno-runtime/Game/Game.js')
      if (cancelled) return
      const game = new Game()
      gameRef.current = game
      try {
        await game.ready
        if (!cancelled) {
          attachRuntime(game)
          holder.current?.setAttribute('data-runtime-state', 'ready')
          game.sceneBridge?.apply?.({ tableState, hostAction, speakingId, closeState, viewerId: VIEWER_ID })
        }
      } catch {
        if (!cancelled) holder.current?.setAttribute('data-runtime-state', 'error')
      }
    })()
    return () => {
      cancelled = true
      if (gameRef.current) detachRuntime(gameRef.current)
      gameRef.current?.destroy?.()
      gameRef.current = null
    }
  }, [active])

  return (
    <div
      ref={holder}
      className="bruno-runtime-canvas"
      data-runtime-state="loading"
      style={{ position: 'fixed', inset: 0, zIndex: 0, background: '#0a0f1c' }}
    >
      <canvas className="js-canvas" style={{ width: '100%', height: '100%', display: 'block' }} />
    </div>
  )
}
