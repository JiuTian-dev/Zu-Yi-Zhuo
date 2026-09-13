import { useEffect, useRef } from 'react'
import { createPortal } from 'react-dom'
import type { DemoCaseLike } from './contract'

export default function DemoEntry({ demoCase, pending, error, onStart, onClose }: {
  demoCase: DemoCaseLike
  pending: boolean
  error: string | null
  onStart(): void
  onClose(): void
}) {
  const panel = useRef<HTMLElement>(null)
  const close = useRef(onClose)
  close.current = onClose
  useEffect(() => {
    const opener = document.activeElement instanceof HTMLElement ? document.activeElement : null
    panel.current?.querySelector<HTMLButtonElement>('[data-start-demo]')?.focus()
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') { event.preventDefault(); close.current(); return }
      if (event.key !== 'Tab') return
      const buttons = Array.from(panel.current?.querySelectorAll<HTMLButtonElement>('button:not([disabled])') ?? [])
      const first = buttons[0], last = buttons.at(-1)
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus() }
      if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus() }
    }
    window.addEventListener('keydown', onKey)
    return () => { window.removeEventListener('keydown', onKey); opener?.focus({ preventScroll: true }) }
  }, [])

  return createPortal(<div className="demo-entry-root">
    <div className="demo-entry-veil" aria-hidden="true" onClick={onClose} />
    <section ref={panel} className="demo-entry" role="dialog" aria-modal="true" aria-labelledby="demo-topic">
      <button type="button" className="demo-entry-close" aria-label="关闭模拟体验" onClick={onClose}>×</button>
      <h2 id="demo-topic">{demoCase.topic}</h2>
      <ul>{demoCase.participants.map((person) => <li key={person.persona_id}><strong>{person.display_name}</strong><span>{person.description}</span></li>)}</ul>
      <p className="demo-disclosure">你与三位虚构桌友、一位主持人参与。桌友由模型模拟，经历为虚构。</p>
      {error && <p className="demo-error" role="alert">{error}</p>}
      <button data-start-demo type="button" className="demo-start" disabled={pending || !demoCase.available} aria-busy={pending} onClick={onStart}>{pending ? '准备中' : error ? '重试' : '开始体验'}</button>
    </section>
  </div>, document.body)
}
