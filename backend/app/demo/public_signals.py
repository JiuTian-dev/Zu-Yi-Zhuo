"""Synthetic but contract-valid public signals for the first-entry demo."""

from app.domain import ContentSignal


flagship_public_signals: tuple[ContentSignal, ...] = (
    ContentSignal(
        signal_id="demo-public-question",
        content_type="question",
        title="AI Agent 真正进入企业后，最先卡住的是什么？",
        excerpt="模型已经能完成不少任务，但企业仍在争论技术、采购和责任边界。",
        source_ref="demo:public:question",
        author_id="public-questioner",
        author_name="公开提问者",
        author_role="产品负责人",
        public_stance="企业需要先回答价值和责任，而不是只追逐模型参数。",
        engagement=980,
    ),
    ContentSignal(
        signal_id="demo-public-architecture",
        content_type="answer",
        title="企业 Agent 的技术落地为什么仍然困难？",
        excerpt="真实系统会遇到延迟、权限、评估和数据边界，模型能力只是其中一环。",
        source_ref="demo:public:architecture",
        author_id="public-architect",
        author_name="公开架构师",
        author_role="AI 架构师",
        public_stance="技术成熟度和可追溯性仍是上线前的首要门槛。",
        engagement=760,
    ),
    ContentSignal(
        signal_id="demo-public-procurement",
        content_type="answer",
        title="企业为什么迟迟不愿意采购 Agent？",
        excerpt="采购流程不仅看效果，还要明确预算、责任归属和供应商承诺。",
        source_ref="demo:public:procurement",
        author_id="public-buyer",
        author_name="公开采购负责人",
        author_role="企业采购负责人",
        public_stance="采购责任链是经常被技术讨论掩盖的隐性瓶颈。",
        engagement=690,
    ),
    ContentSignal(
        signal_id="demo-public-safety",
        content_type="article",
        title="Agent 上线前必须说清楚的安全边界",
        excerpt="权限、审计和失败回退决定了一个 Agent 能否进入真实组织。",
        source_ref="demo:public:safety",
        author_id="public-security",
        author_name="公开安全研究者",
        author_role="安全研究者",
        public_stance="没有可追溯证据和权限边界，能力越强反而越难上线。",
        engagement=520,
    ),
)


__all__ = ("flagship_public_signals",)
