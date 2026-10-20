# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""End an interrupted auto-rebase attempt whose pull request is over.

Eligibility's open-PR gate hands this owner every anchored attempt whose pull
request merged or closed. What it ends is the whole handoff, in one write: the
attempt, the debt the gate recorded for a push no terminal pull request can
receive, and the permission beside it -- settled from the head the pull request
ended on where that head is the rewrite the permission names, and dropped on
the rollback's own rule everywhere else.

That write is the attempt's checkpoint (`checkpoints._lands_the_checkpoint`),
and nothing is written ahead of it -- a settled transfer's overdue report
included -- until the comment, read afresh, still spells the attempt and its
evidence as the tick last confirmed them (`checkpoints._still_owns_the_attempt`).
A comment that does not, or a write that did not land, ends nothing: the
comment stands as it is for the next tick to read.
"""
from __future__ import annotations

from orchestrator.git.base_sync import attempts, checkpoints
from orchestrator.git.base_sync.models import (
    _AutoRebaseContext,
    _AutoRebaseRecoveryContext,
)


def _retires_the_terminal_handoff(
    context: _AutoRebaseContext | _AutoRebaseRecoveryContext,
    published: str,
) -> bool:
    """Settle or drop what an attempt owed a pull request that is over; whether the write ending it landed.

    Cleared one at a time, the records that stay are what stop the issue
    finishing: the reconciliation ahead of every handler reads a standing debt
    as a commit the pull request never received, cannot enter a publication
    that is over, and parks -- so the stage that would finalize the merge never
    runs. So the debt goes whatever it is leased to, since beside a pinned
    anchor it can only be this attempt's own.

    A terminal pull request does not say the attempt's push never happened,
    though. A permission whose rewrite is the head the pull request ended on
    is a push that landed with its receipt lost, and the merge carried it away:
    dropped, the verdict stays on the commit the rewrite replaced and the one
    that shipped is covered by nothing. So that transfer settles exactly as a
    landed push settles it, with the receipt beside the move, and the record
    it owes the sinks is made once the whole of it is durable: behind a write
    that landed, and not behind one refused or never confirmed, whose proof the
    comment then still carries for the dispatcher's reconciliation to report
    once a later tick reads it there (`late_reconcile`). A settlement an earlier
    tick made and never reported is reported first, on the same terms.
    """
    # Lazy for the reason every upward reach in this package is: the debt,
    # the settlement, and the record it owes sit in the workflow layer above.
    from orchestrator.workflow.stages.implementing import (
        late_approval_state as _late_approval_state,
        late_records as _records,
        late_transfer_telemetry as _transfer_telemetry,
    )
    if not checkpoints._still_owns_the_attempt(
        context.gh, context.issue, context.state, "ending the handoff of a pull request that is over",
    ):
        return False
    gate = _records._gate(
        context.gh, context.spec, context.issue, context.state,
        context.worktree,
    )
    _transfer_telemetry._reports_a_settled_transfer(gate)
    rotation = _settles_or_drops(
        gate, published, str(context.pending_pre_rebase_sha or ""),
        context.pr_number,
    )
    _late_approval_state._forget_approval(context.state)
    attempts._clears_the_attempt(context.state)
    if not checkpoints._lands_the_checkpoint(context.gh, context.issue, context.state, "ending the handoff"):
        return False
    _transfer_telemetry._reports_the_transfer(gate, rotation)
    return True


def _settles_or_drops(gate, published: str, anchor: str, pr_number: int):
    """Stage what the permission beside a terminal attempt becomes.

    Settled where the pull request shipped the rewrite this attempt's permission
    names, with the receipt that says so leased to the anchor its push was made
    from. Otherwise dropped where the rollback would drop it -- an outstanding
    record this build can read whole, made over this anchor -- and left
    standing everywhere else, since a group nobody can check is the only account
    of how the exemption came to name what it names.
    """
    # Lazy for the same reason as the caller's reach above.
    from orchestrator.workflow.stages.implementing import (
        late_publication_state as _late_publication_state,
        late_rotation as _rotation,
        late_transfer as _transfer,
    )
    rotation = _rotation._settles_a_merged_transfer(
        gate, published, anchor, pr_number,
    )
    if rotation.staged:
        _late_publication_state._record_publication(
            gate.state, published, anchor, pr_number,
        )
    else:
        _transfer._abandoned_authorization(gate, anchor)
    return rotation
