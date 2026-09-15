import { useEffect, useRef } from 'react'
import { createPortal } from 'react-dom'
import type { TagProfile } from '../onboarding/profileStore'
import type { DemoCaseLike } from './contract'
import CharacterPortrait, { demoCharacterForIndex } from './CharacterPortrait'

export default function DemoEntry({ demoCase, profile, pending, error, onStart, onClose }: {
  demoCase: DemoCaseLike
  profile?: TagProfile | null
  pending: boolean
  error: string | null
  onStart(): void
  onClose(): void
}) {
  const panel = useRef<HTMLElement>(null)
  const close = useRef(onClose)
  close.current = onClose
  useEffect(() => {
    // Warm the short-lived route assets while the judge reads the match proof.
    // The journey can still start immediately with its authored lightweight car.
    void fetch('/scene/arrival-suv-lite.glb', { cache: 'force-cache' }).catch(() => undefined)
    void fetch('/assets/bruno-runtime/draco/draco_wasm_wrapper.js', { cache: 'force-cache' }).catch(() => undefined)
    void fetch('/assets/bruno-runtime/draco/draco_decoder.wasm', { cache: 'force-cache' }).catch(() => undefined)
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

  const visibleTags = profile?.tags.filter((tag) => tag.visible).slice(0, 5) ?? []

  return createPortal(<div className="demo-entry-root">
    <div className="demo-entry-veil" aria-hidden="true" onClick={onClose} />
    <section ref={panel} className="demo-entry" role="dialog" aria-modal="true" aria-labelledby="demo-topic">
      <button type="button" className="demo-entry-close" aria-label="关闭模拟体验" onClick={onClose}>×</button>
      <p className="demo-entry-kicker">可解释匹配 · AGENT 已完成本轮组局</p>
      <h2 id="demo-topic">{demoCase.topic}</h2>
      {profile && <section className="demo-match-proof" aria-label="本次匹配依据">
        <div className="demo-match-agent">
          <CharacterPortrait character="host" label="阿桌" className="demo-match-agent-avatar" online />
          <p><small>阿桌不是随机拼桌。刚才的对话让我理解了</small><strong>{profile.seatLabel}</strong></p>
          <em>匹配完成</em>
        </div>
        {profile.summary && <blockquote>{profile.summary}</blockquote>}
        <p className="demo-match-tags">{visibleTags.map((tag) => <span key={tag.id}>#{tag.label}</span>)}</p>
        <ol>
          <li><i>01</i><b>实时理解</b><span>画像来自刚才的自由对话</span></li>
          <li><i>02</i><b>互补组局</b><span>亲历、机会、结构共同入席</span></li>
          <li><i>03</i><b>关系沉淀</b><span>共识与值得认识的人都会留下</span></li>
        </ol>
      </section>}
      <h3 className="demo-candidates-title">三种不同视角，已经在湖边等你</h3>
      <ul className="demo-candidate-list">{demoCase.participants.map((person, index) => <li key={person.persona_id}>
        <CharacterPortrait character={demoCharacterForIndex(index)} label={person.display_name} className="demo-person-portrait" online />
        <div>
          <small>预置演示桌友 · {['亲历视角', '机会视角', '结构视角'][index] ?? '互补视角'}</small>
          <strong>{person.display_name}</strong>
          <span>{person.description}</span>
        </div>
      </li>)}</ul>
      <p className="demo-disclosure"><b>演示边界透明：</b>候选人预置用于无人在线时也能完成评审；上桌后的发言由阶跃星辰实时生成，虚构经历会明确标注。</p>
      {error && <p className="demo-error" role="alert">{error}</p>}
      <button data-start-demo type="button" className="demo-start" disabled={pending || !demoCase.available} aria-busy={pending} onClick={onStart}>{pending ? '正在邀请三位桌友…' : error ? '重试' : '让 Agent 开车带我过去'} <span aria-hidden="true">→</span></button>
    </section>
  </div>, document.body)
}
