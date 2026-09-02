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
      // @ts-expect-error untyped table runtime JavaScript
      const { Game } = await import('./table-engine/Game/Game.js')
      if (cancelled) return
      gameRef.current = new Game()
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
      className="table-world-canvas"
      style={{ position: 'absolute', inset: 0, background: '#0a0f1c' }}
    >
      <canvas className="js-canvas" style={{ width: '100%', height: '100%', display: 'block' }} />
    </div>
  )
}
