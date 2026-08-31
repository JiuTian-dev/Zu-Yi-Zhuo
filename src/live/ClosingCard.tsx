import type { PersonalCardLike, SharedBaselineLike } from './contract'

interface ClosingCardProps {
  baseline: SharedBaselineLike
  personalCard: PersonalCardLike | null
  onReturn(): void
}

export default function ClosingCard({ baseline, personalCard, onReturn }: ClosingCardProps) {
  return (
    <div className="closing-root" role="dialog" aria-modal="true" aria-label="收桌卡">
      <div className="closing-veil" aria-hidden="true" />
      <section className="closing-panel">
        <p className="closing-kicker">收桌 · 这一桌聊成了什么</p>
        <h2 className="closing-question">
          <small>问题长成了这样</small>
          {baseline.evolved_question.text}
        </h2>

        <div className="closing-grid">
          <div className="closing-block">
            <small>共识</small>
            {baseline.key_consensus.length === 0 && <p className="closing-empty">这一桌还没有沉淀出共识。</p>}
            {baseline.key_consensus.map((item) => (
              <p key={item.text}>{item.text}</p>
            ))}
          </div>
          <div className="closing-block">
            <small>未解决的分歧</small>
            {baseline.unresolved_disagreements.length === 0 && <p className="closing-empty">没有留下悬而未决的分歧。</p>}
            {baseline.unresolved_disagreements.map((item) => (
              <p key={item.text}>{item.text}</p>
            ))}
          </div>
          {baseline.collective_next_steps.length > 0 && (
            <div className="closing-block">
              <small>桌上带走的行动</small>
              {baseline.collective_next_steps.map((item) => (
                <p key={item.text}>{item.is_commitment ? '✓ ' : ''}{item.text}</p>
              ))}
            </div>
          )}
        </div>

        {personalCard && (
          <div className="closing-personal">
            <p className="closing-personal-kicker">你的收桌卡 · 第五席</p>
            <div className="closing-grid">
              {personalCard.what_changed.length > 0 && (
                <div className="closing-block">
                  <small>你的变化</small>
                  {personalCard.what_changed.map((item) => <p key={item.text}>{item.text}</p>)}
                </div>
              )}
              {personalCard.your_contribution.length > 0 && (
                <div className="closing-block">
                  <small>你补上的视角</small>
                  {personalCard.your_contribution.map((item) => <p key={item.text}>{item.text}</p>)}
                </div>
              )}
              {personalCard.worth_continuing_with.length > 0 && (
                <div className="closing-block">
                  <small>值得继续聊的人</small>
                  {personalCard.worth_continuing_with.map((item) => (
                    <p key={item.participant_id}>{item.reason}</p>
                  ))}
                </div>
              )}
              {personalCard.suggested_next_actions.length > 0 && (
                <div className="closing-block">
                  <small>回响 · 接下来</small>
                  {personalCard.suggested_next_actions.map((item) => <p key={item.text}>{item.text}</p>)}
                </div>
              )}
            </div>
          </div>
        )}

        <div className="closing-echo">
          <span>这道问题长出了下一桌。</span>
          <button type="button" onClick={onReturn}>回到正在发生的桌 <i>→</i></button>
        </div>
      </section>
    </div>
  )
}
