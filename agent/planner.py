"""Planner — strategic (milestone) + tactical (per-step) planning."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any
from uuid import uuid4


class MilestoneStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    SKIPPED = "skipped"
    BLOCKED = "blocked"


@dataclass
class Milestone:
    id: str = field(default_factory=lambda: str(uuid4()))
    description: str = ""
    depends_on: list[str] = field(default_factory=list)
    status: MilestoneStatus = MilestoneStatus.PENDING
    estimated_turns: int = 3
    user_visible: bool = True


@dataclass
class StrategicPlan:
    id: str = field(default_factory=lambda: str(uuid4()))
    goal: str = ""
    milestones: list[Milestone] = field(default_factory=list)

    @property
    def current_milestone(self) -> Milestone | None:
        for m in self.milestones:
            if m.status == MilestoneStatus.IN_PROGRESS:
                return m
        return None

    @property
    def progress(self) -> dict:
        total = len(self.milestones)
        completed = sum(1 for m in self.milestones if m.status == MilestoneStatus.COMPLETED)
        return {"completed": completed, "total": total, "percent": completed / total * 100 if total > 0 else 0}

    def next_pending(self) -> Milestone | None:
        for m in self.milestones:
            if m.status == MilestoneStatus.PENDING:
                return m
        return None


@dataclass
class TacticalStep:
    """A single action within a milestone."""
    plan_reasoning: str = ""
    tools_to_call: list[dict[str, Any]] = field(default_factory=list)
    message_to_user: str = ""
    is_complete: bool = False


class Planner:
    """Two-level planner: strategic (what milestones) + tactical (what tools to call).

    In this architecture, the LLM ( API) does the actual planning reasoning.
    The Planner class provides the data structures and state management while the
    Agent loop invokes the LLM for the reasoning itself.
    """

    def create_strategic_plan(
        self,
        goal: str,
        milestones: list[dict],
    ) -> StrategicPlan:
        """Create a strategic plan from milestone definitions."""
        plan = StrategicPlan(goal=goal)
        for i, m_def in enumerate(milestones):
            plan.milestones.append(Milestone(
                description=m_def.get("description", f"Step {i+1}"),
                depends_on=m_def.get("depends_on", []),
                estimated_turns=m_def.get("estimated_turns", 3),
                user_visible=m_def.get("user_visible", True),
            ))
        if plan.milestones:
            plan.milestones[0].status = MilestoneStatus.IN_PROGRESS
        return plan

    def advance_milestone(self, plan: StrategicPlan, current_id: str, next_id: str) -> StrategicPlan:
        """Mark current milestone complete, start the next one."""
        for m in plan.milestones:
            if m.id == current_id:
                m.status = MilestoneStatus.COMPLETED
            elif m.id == next_id:
                m.status = MilestoneStatus.IN_PROGRESS
        return plan

    def skip_milestone(self, plan: StrategicPlan, milestone_id: str) -> StrategicPlan:
        """Skip a milestone (user requested)."""
        for m in plan.milestones:
            if m.id == milestone_id and m.status == MilestoneStatus.PENDING:
                m.status = MilestoneStatus.SKIPPED
        return plan

    def block_milestone(self, plan: StrategicPlan, milestone_id: str, reason: str) -> StrategicPlan:
        """Mark a milestone as blocked."""
        for m in plan.milestones:
            if m.id == milestone_id:
                m.status = MilestoneStatus.BLOCKED
                m.description += f" [BLOCKED: {reason}]"
        return plan
