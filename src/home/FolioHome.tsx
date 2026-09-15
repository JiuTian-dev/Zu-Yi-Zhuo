import AccountMenu from './AccountMenu'
import ZhihuConnectionPreview from './ZhihuConnectionPreview'
import LakeModelStage from './LakeModelStage'
import CharacterPortrait, { demoCharacterForIndex, viewerCharacter } from '../live/CharacterPortrait'
import './folioHome.css'

interface FolioHomeProps {
  onOpenProfile(): void
  onEnterMatch(): void
  onOpenLogin(): void
  onPreciseMatch(): void
  onHostTable(): void
  onOpenDemo?(): void
}

const demoSeats = [
  { name: '林夏', role: '迁居亲历' },
  { name: '周砚', role: '职业机会' },
  { name: '程野', role: '城市结构' },
]

/**
 * PRODUCT HOME — establish the product thesis before showing its 3D world.
 * The interactive world remains part of discovery and the room itself; the
 * first screen gives a judge one clear, complete path through the product.
 */
export default function FolioHome({
  onOpenProfile,
  onEnterMatch,
  onOpenLogin,
  onPreciseMatch,
  onHostTable,
  onOpenDemo,
}: FolioHomeProps) {
  return (
    <main className="folio-home" aria-label="组一桌首页">

      <header className="folio-home-chrome">
        <div className="folio-home-brand-lockup">
          <span className="folio-home-mark" aria-hidden="true">桌</span>
          <p className="folio-home-brand">组一桌</p>
          <span className="folio-home-edition">知乎黑客松 · 赛道一</span>
        </div>
        <AccountMenu onOpenProfile={onOpenProfile} onOpenLogin={onOpenLogin} />
      </header>

      <div className="folio-home-layout">
        <section className="folio-home-hero">
          <p className="folio-home-kicker"><i />湖边会客厅 · 留一个位置给你</p>
          <h1>来，组一桌。<br /><span>聊点真正在意的。</span></h1>
          <p className="folio-home-lede">
            带着你的经历，也带着没想明白的问题。
            阿桌帮你遇见不同视角的人，把一次聊天变成值得继续的相遇。
          </p>


          <div className="folio-home-actions">
            <button className="folio-primary-action" type="button" onClick={onOpenDemo} disabled={!onOpenDemo}>
              <span>{onOpenDemo ? '先让阿桌认识我' : '阿桌正在准备桌子…'}</span>
              <b aria-hidden="true">↗</b>
            </button>
            <button className="folio-secondary-action" type="button" onClick={onPreciseMatch}>带着我的问题找一桌</button>
          </div>

          <p className="folio-home-chat-note">阿桌 · Agent 组局助手　/　你决定哪些标签留下来</p>
          <ol className="folio-value-chain" aria-label="产品工作流程">
            <li><span>01</span><b>认识你</b><small>对话生成身份与兴趣标签</small></li>
            <li><span>02</span><b>补齐一桌</b><small>话题相交，视角互补</small></li>
            <li><span>03</span><b>留下关系</b><small>总结、桌友与下一次相遇</small></li>
          </ol>
          <ZhihuConnectionPreview />
        </section>

        <section className="folio-first-scene" aria-label="首屏实时三维场景">
          <LakeModelStage />
          <p><span>LIVE 3D</span> 湖边的这一桌，给你留了一个位置。</p>
        </section>

        <aside className="folio-demo-card" aria-label="评委体验桌预览">
          <div className="folio-demo-card-content">
            <div className="folio-demo-card-head">
              <span>阿桌为你留了一桌</span>
              <em>演示桌 · 虚构桌友</em>
            </div>
            <p className="folio-demo-question">离开大城市，<br />是逃避还是重新选择生活？</p>

            <div className="folio-demo-seats">
              <div className="folio-demo-seat is-viewer"><CharacterPortrait character={viewerCharacter()} label="你选择的角色" className="folio-seat-portrait" /><span><b>你的位置</b><small>带着真实的自己入桌</small></span></div>
              {demoSeats.map((seat, index) => (
                <div className="folio-demo-seat" key={seat.name}>
                  <CharacterPortrait character={demoCharacterForIndex(index)} label={seat.name} className="folio-seat-portrait" />
                  <span><b>{seat.name}</b><small>{seat.role}</small></span>
                </div>
              ))}
            </div>

            <div className="folio-demo-outcome">
              <span>这桌不是为了投票</span>
              <p>把“走还是留”推进为：<strong>你真正想离开的，是城市，还是一种失去掌控的生活？</strong></p>
            </div>

            <button className="folio-card-action" type="button" onClick={onOpenDemo} disabled={!onOpenDemo}>
              完整体验一次相遇 <span aria-hidden="true">→</span>
            </button>
          </div>
        </aside>
      </div>

      <footer className="folio-home-footer">
        <p><span>真人</span>提供事实、经验与立场 <i /> <span>Agent</span>负责发现差异、递话与记录</p>
        <nav aria-label="其他入口">
          <button type="button" onClick={onEnterMatch}>浏览正在发生的桌</button>
          <button type="button" onClick={onHostTable}>自己开一桌</button>
        </nav>
      </footer>
    </main>
  )
}
