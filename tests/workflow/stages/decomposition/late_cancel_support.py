# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""One closed snapshot owner, and the pass that ends its cycle.

Shared by the modules that ask what a cancellation costs: what the ending
settles and in which order, what the reading its terminal is written on has to
be taken after, and what the correction of a terminal written too early can
leave behind. They drive the real cleanup sweep and the real umbrella walk,
since half of what a closed owner's cases are about is the routing -- a closed
owner reaches its ledger through the sweep and never through the stage handler
its label names.
"""
from __future__ import annotations

from dataclasses import replace

from orchestrator.workflow.late_split import state as _late_state
from orchestrator.workflow.late_split.models import LateResourceState
from orchestrator.workflow.late_split.phases import LatePhase
from orchestrator.workflow.stages.decomposition import late_hold as _late_hold
from orchestrator.workflow.state import WorkflowLabel
from tests.workflow.fixtures import _PatchedWorkflowMixin
from tests.workflow.stages.decomposition.late_cleanup_support import (
    DECOMPOSING,
    LABEL_BLOCKED,
    LABEL_DONE,
    PARENT_NUMBER,
    OwnerSeed,
    SeededUmbrella,
    resource_states,
    split_umbrella,
)
from tests.workflow.stages.decomposition.late_test_support import (
    PLAN_PR_BODY,
    PLAN_PR_NUMBER,
    seed_plan_pr,
)

# An obligation the branch-and-ref reading walks straight past: a plan-PR
# entry under a number the hold's own record no longer names.
_STRAY_PLAN_PR = ({"kind": "plan_pr", "target": "99", "state": "failed"},)

_RESOURCES = "late_resources"


class ClosedOwnerCase(_PatchedWorkflowMixin):
    """One closed snapshot owner, and the pass that ends its cycle."""

    def _closed_owner(
        self,
        *,
        phase: LatePhase = LatePhase.CLEANING_UP,
        owed: LateResourceState = LateResourceState.RECONCILED,
        snapshot: LateResourceState | None = LateResourceState.RETAINED,
        child_closed: bool = True,
    ) -> SeededUmbrella:
        """A snapshot owner a human closed, with the ledger under test."""
        return split_umbrella(
            owed,
            snapshot=snapshot,
            child_label=LABEL_DONE if child_closed else LABEL_BLOCKED,
            owner=OwnerSeed(
                label=DECOMPOSING,
                closed=True,
                child_closed=child_closed,
                phase=phase,
            ),
        )

    def _holding_plan_pr(
        self, seeded: SeededUmbrella, preserved: bool = True, **pr_fields,
    ) -> None:
        """Give this owner the open plan PR its cycle marked and preserved.

        `preserved=False` is the damaged record rather than a partial one:
        the identity and the description it displaced are written as ONE
        thing, so a number standing without a body is a hold nothing here can
        show it ever took.
        """
        github = seeded.github
        state = github.read_pinned_state(seeded.parent)
        holding = replace(
            _late_state.read_late_generation(state),
            plan_pr_number=PLAN_PR_NUMBER,
            plan_pr_body=PLAN_PR_BODY if preserved else None,
        )
        _late_state.write_late_generation(state, holding)
        github.seed_state(PARENT_NUMBER, **state.data)
        pr_fields.setdefault("body", _late_hold._hold_body(holding))
        seed_plan_pr(github, **pr_fields)

    def _swept(self, seeded: SeededUmbrella, *sweep_args, **answers):
        """Run one cleanup sweep over this closed owner."""
        return seeded.swept(self, *sweep_args, **answers)

    def _pinned(self, seeded: SeededUmbrella) -> dict:
        """What the owner's pinned comment records right now."""
        return seeded.github.pinned_data(PARENT_NUMBER)

    def _states(self, seeded: SeededUmbrella) -> dict:
        """What the owner's ledger now says about each obligation."""
        return resource_states(seeded.github)

    def _labels(self, seeded: SeededUmbrella) -> list:
        """Every workflow label this pass wrote on the owner."""
        return seeded.github.label_history

    def _events_named(
        self, seeded: SeededUmbrella, family: str, resource: str | None = None,
    ) -> list:
        """Every record of one family both sinks were handed.

        Narrowed to one resource where the family carries several, which the
        cleanup family does: a pass settles a branch, a ref, and a held plan
        pull request under it.
        """
        return [
            record for record in seeded.github.recorded_events
            if record.get("event") == family
            and resource in (None, record.get("resource"))
        ]


def settled_umbrella() -> SeededUmbrella:
    """An open umbrella owing one branch, whose only child has ended."""
    return split_umbrella(
        LateResourceState.PENDING,
        owner=OwnerSeed(label=WorkflowLabel.UMBRELLA, closed=False),
    )


def umbrella_owing_a_stray_plan_pr() -> SeededUmbrella:
    """An umbrella the reclamation clears and the terminal still cannot.

    A plan-PR entry under a number the hold's own record no longer names is
    an obligation the branch-and-ref reading walks straight past, so the
    umbrella settles, reaches its terminal, and only the ending's own wider
    reading holds it.
    """
    seeded = split_umbrella(
        None, owner=OwnerSeed(label=WorkflowLabel.UMBRELLA, closed=False),
    )
    seeded.github.seed_state(PARENT_NUMBER, **{
        **seeded.github.pinned_data(PARENT_NUMBER),
        _RESOURCES: list(_STRAY_PLAN_PR),
    })
    return seeded
