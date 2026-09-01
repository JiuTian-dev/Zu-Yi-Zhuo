import { useEffect, useRef } from 'react'

/**
 * Mounts the vendored folio-2025 engine (MIT, Bruno Simon) rendering our
 * table meadow through his material/lighting/grass systems.
 */
export default function BrunoTable({ active }: { active: boolean }) {
  const holder = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!active || !holder.current) return
    let cancelled = false
    void (async () => {
      // @ts-expect-error untyped vendored JS engine (MIT, folio-2025)
      const { Game } = await import('./bruno/Game/Game.js')
      if (cancelled) return
      new Game()
    })()
    return () => {
      cancelled = true
    }
  }, [active])

  return (
    <div
      ref={holder}
      className="bruno-game"
      style={{ position: 'absolute', inset: 0, background: '#0a0f1c' }}
    >
      <canvas className="js-canvas" style={{ width: '100%', height: '100%', display: 'block' }} />
    </div>
  )
}
