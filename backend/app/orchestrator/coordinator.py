"""Code-controlled planning boundary for the in-table specialist graph."""

from dataclasses import dataclass

from app.domain import StageSummaryTrigger
from app.orchestrator.checkpoint import CheckpointDecision, CheckpointPolicy
from app.orchestrator.context import AgentContext


@dataclass(frozen=True)
class CoordinatorPlan:
    input_state_version: int
    run_fast_path: bool
    checkpoint: CheckpointDecision
    specialist_roles: tuple[str, ...]


class TableRunCoordinator:
    """Plans bounded work only; persistence and WebSocket wiring remain explicit later tasks."""

    def __init__(self, checkpoint_policy: CheckpointPolicy | None = None) -> None:
        self.checkpoint_policy = checkpoint_policy or CheckpointPolicy()

    def plan(
        self,
        context: AgentContext,
        *,
        semantic_trigger: StageSummaryTrigger | None = None,
        pre_close: bool = False,
        manual_checkpoint: bool = False,
    ) -> CoordinatorPlan:
        checkpoint = self.checkpoint_policy.evaluate(
            context.delta_turns,
            latest_summary=context.latest_summary,
            semantic_trigger=semantic_trigger,
            pre_close=pre_close,
            manual_requested=manual_checkpoint,
        )
        roles = ["content_analyst", "participation_analyst", "facilitation_strategist"]
        if checkpoint.trigger is not None:
            roles.extend(("stage_summarizer", "summary_verifier"))
        return CoordinatorPlan(
            input_state_version=context.input_state_version,
            run_fast_path=bool(context.delta_turns),
            checkpoint=checkpoint,
            specialist_roles=tuple(roles) if context.delta_turns else (),
        )
