import { useEffect, useRef } from 'react'

/**
 * Mounts the project table runtime. The runtime owns only the round-table
 * world; React owns the surrounding HUD and conversation controls.
 */
export default function TableWorld({ active }: { active: boolean }) {
  const holder = useRef<HTMLDivElement>(null)
  const gameRef = useRef<{ destroy?: () => void } | null>(null)

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
        if (!cancelled) holder.current?.setAttribute('data-runtime-state', 'ready')
      } catch {
        if (!cancelled) holder.current?.setAttribute('data-runtime-state', 'error')
      }
    })()
    return () => {
      cancelled = true
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
