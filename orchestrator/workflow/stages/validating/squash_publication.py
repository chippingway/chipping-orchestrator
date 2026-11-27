# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Publish a fresh or recovered squash and settle any rollback against its pinned claim."""
from __future__ import annotations

from orchestrator.git.publication import models, planning, resume, rewrite
from orchestrator.workflow.late_split.collapses import LateCollapse
from orchestrator.workflow.stages.implementing import late_collapse_state, late_rewrite, late_squash_proof
from orchestrator.workflow.stages.implementing.late_gate_models import _Gate, _PublicationEntry

_UNREADABLE_COLLAPSE = (
    "this issue records a squash it may not have finished and the record of "
    "it is not one this build can read, so the branch cannot be told from one "
    "with nothing to squash"
)

_OFF_THE_RECEIPT = (
    "this issue's receipt proves only `{receipted}` already published, and no "
    "approval stands behind publishing anything else -- but the checkout "
    "stands on `{head}`, or the record of the squash no longer reads, so "
    "nothing here is the no-op that receipt allows"
)

_UNCONFIRMED_PUBLICATION = (
    "the pull request already carries `{squashed}` and the leased push that "
    "would have confirmed it did not go out; the branch is left standing on "
    "it rather than reset off work the remote has"
)


def _resumed_squash(
    gate: _Gate, branch: str, plan: planning._SquashPlan,
) -> models._SquashOutcome | None:
    """Finish a recorded rewrite before a one-commit branch can be handed on as complete."""
    recorded = late_collapse_state._recorded_collapse(gate.state)
    if gate.no_op_of and (recorded is None or plan.original_head != gate.no_op_of):
        return models._SquashOutcome(error=_OFF_THE_RECEIPT.format(
            receipted=gate.no_op_of, head=plan.original_head,
        ))
    if recorded is None:
        if late_collapse_state._claims_a_collapse(gate.state):
            return models._SquashOutcome(error=_UNREADABLE_COLLAPSE)
        return None
    return _outstanding_collapse(gate, branch, plan, recorded)


def _outstanding_collapse(
    gate: _Gate, branch: str, plan: planning._SquashPlan, recorded: LateCollapse,
) -> models._SquashOutcome | None:
    """A proved rewrite needs publication. An intact history can be squashed afresh."""
    refusal = resume._unprovable_claim(gate.worktree, recorded)
    if refusal:
        return models._SquashOutcome(error=refusal)
    if plan.count == 1 and plan.original_head != recorded.head:
        return _finished_collapse(gate, branch, plan.original_head, recorded)
    refusal = resume._unaccountable_branch(gate.worktree, plan, recorded)
    if refusal:
        return models._SquashOutcome(error=refusal)
    # The original history is still intact. The next squash may start afresh.
    late_collapse_state._forgets_the_collapse(gate.state)
    return None


def _finished_collapse(
    gate: _Gate, branch: str, squashed: str, recorded: LateCollapse,
) -> models._SquashOutcome:
    """Verify the local commit and re-enter publication on the recorded history."""
    refusal = resume._unrecovered_collapse(gate.worktree, recorded, squashed)
    if refusal:
        return models._SquashOutcome(error=refusal)
    entry = late_rewrite._resumed_entry(gate, recorded, squashed)
    if not entry.is_frozen:
        _restore_if_unowned(gate, squashed, recorded)
        return models._SquashOutcome(error=entry.refusal)
    return _published_squash(gate, branch, entry, squashed, recorded)


def _rewrite_and_publish(
    gate: _Gate, branch: str, plan: planning._SquashPlan, entry: _PublicationEntry,
) -> models._SquashOutcome:
    """Publish the commit made from the plan whose terms are already on the issue."""
    collapsed = LateCollapse(head=plan.original_head, base_sha=plan.base_sha, count=plan.count)
    try:
        squashed = rewrite._rewrite_squash(gate.spec, gate.issue.number, gate.worktree, plan)
    except rewrite._SquashResetError as error:
        late_collapse_state._forgets_the_collapse(gate.state)
        return models._SquashOutcome(error=str(error))
    except rewrite._SquashCommitError as error:
        _restore(gate, collapsed.head, error.step)
        return models._SquashOutcome(error=str(error))
    return _published_squash(gate, branch, entry, squashed, collapsed)


def _published_squash(
    gate: _Gate, branch: str, entry: _PublicationEntry, squashed: str, collapsed: LateCollapse,
) -> models._SquashOutcome:
    """Measure and publish the squash under its lease. The handoff still needs its count after a landing."""
    published = late_rewrite._publishes_rewrite(gate, branch, entry, squashed, collapsed)
    if published.held:
        _restore_if_unowned(gate, squashed, collapsed)
        return models._SquashOutcome(held=True)
    if published.landed:
        return models._SquashOutcome(success=True, sha=squashed, count=collapsed.count)

    # A crash after the push can leave the PR on the squash before a receipt is durable.
    if entry.published_sha == squashed or late_squash_proof._already_published(
        gate.state, collapsed.head, squashed, entry.pr_number,
    ):
        return models._SquashOutcome(error=_UNCONFIRMED_PUBLICATION.format(squashed=squashed))
    _restore(gate, collapsed.head, "force-push")
    return models._SquashOutcome(error=(
        "force-push with lease rejected (concurrent update on the "
        "remote, or lease violation); see orchestrator logs"
    ))


def _restore_if_unowned(gate: _Gate, squashed: str, collapsed: LateCollapse) -> None:
    """Leave a held squash with its owner, including a checkout that has moved past it."""
    if not late_squash_proof._rewrite_stands(gate, squashed):
        _restore(gate, collapsed.head, "a publication the size gate refused")


def _restore(gate: _Gate, head: str, reason: str) -> None:
    """Retire the abandoned publication debt only once Git has restored the original commits."""
    if rewrite._rollback_squash(gate.spec, gate.issue.number, gate.worktree, head, reason):
        late_rewrite._forgets_the_rollback(gate, head)
