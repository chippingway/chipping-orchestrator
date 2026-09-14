# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Read the obligations that keep a cancelled late cycle from ending or restarting.

Opaque ledgers and unprovable pull-request holds remain outstanding.
Restart requires both the cleanup obligations and the domain ledger to settle.
"""
from __future__ import annotations

from orchestrator.workflow.late_split import (
    models as _late_models,
    restart as _restart,
)
from orchestrator.workflow.stages.decomposition import (
    late_cleanup_reading as _late_cleanup_reading,
)

_PLAN_PR = _late_models.LateResourceKind.PLAN_PR

# How a still-owed held pull request is named in the line that says what a
# closed owner is waiting on. The ledger's own targets are bare identifiers,
# and a bare number beside a branch and a ref would not say what it was.
_OWED_PLAN_PR = "held PR #{0}"

# The same, for the one shape no pass can settle: a number with no
# preserved description beside it, which is a hold nothing can prove and
# a human has to repair.
_UNPROVABLE_HOLD = "held PR #{0} (no preserved description)"


def _still_owed(generation: _late_models.LateGeneration) -> bool:
    """Whether this cycle still holds something on the remote.

    The half of `_ending_is_over` that costs no request, asked on its own by
    the pass that decides whether an owner may be allowed to leave the sweep:
    what a terminal is withheld for is exactly what a label the sweep queries
    has to keep the issue reachable for.
    """
    return generation.is_present and bool(_outstanding(generation))


def _held_pull_request(generation: _late_models.LateGeneration) -> int | None:
    """The held pull request this pass may act on, if there is one.

    Both halves of the hold or neither. The number alone is not a hold this
    generation can prove it took: the identity and the description it
    displaced are written as ONE thing, so a record carrying the first and
    not the second is damaged rather than partial -- and acting on it would
    comment on and close a pull request nothing here ever marked, which for a
    number a human typed is somebody else's change. The release in front of
    this refuses such a record silently, having no copy to put back, so
    without this the close would run behind a no-op that proved nothing.
    `_unprovable_hold` is what holds the terminal for the repair instead.

    None while the RESOURCE ledger is opaque too, for the reason nothing else
    is reclaimed there: the typed view is a projection of the entries this
    binary could read and the write puts the verbatim copy back, so an
    outcome recorded against it would be dropped at the next write and the
    pull request acted on again forever. What holds the terminal in that case
    is the opaque ledger itself, which the reclamation owner already reports.
    """
    if _late_cleanup_reading._unwritable(generation) or _unprovable_hold(generation):
        return None
    return generation.plan_pr_number


def _unprovable_hold(generation: _late_models.LateGeneration) -> bool:
    """Whether this record names a PR it cannot show it ever held."""
    return (
        generation.plan_pr_number is not None
        and generation.plan_pr_body is None
    )


def _owed_plan_pr(generation: _late_models.LateGeneration) -> tuple[str, ...]:
    """Every held pull request this cancellation has still to settle.

    What the terminal is held by, and a different question from what the pass
    ACTS on. Acting takes the hold's own record, since releasing one means
    knowing which pull request this cycle marked; being owed takes the LEDGER,
    because that is where an obligation lives once it is written. The two can
    disagree -- a supersession that failed leaves an entry behind, and the
    number beside it is a field a later write can clear or a hand edit can
    damage -- and only the ledger's answer may decide a terminal. An entry
    left behind by a `rejected` owner is a pull request nothing revisits, and
    it is also what makes a restart refuse the fresh cycle that terminal is
    supposed to authorize: restart counts every unreconciled resource as owed,
    and it is right to.

    A record naming a pull request it cannot show it held is owed too, and it
    is the one entry here nothing can settle: the description that hold
    displaced is the only copy there was, so no later pass may put it back or
    close over it. It holds the terminal until a human repairs the record,
    which is the answer that neither closes somebody else's change nor
    quietly forgets a pull request this cycle may really have marked.

    Empty while the RESOURCE ledger is opaque only because the reclamation
    owner already blocks on that outright, and its answer names it.
    """
    if _late_cleanup_reading._unwritable(generation):
        return ()
    owed = tuple(
        _OWED_PLAN_PR.format(entry.target)
        for entry in generation.resources
        if entry.kind == _PLAN_PR
        and entry.resource_state != _late_models.LateResourceState.RECONCILED
    )
    if not _unprovable_hold(generation):
        return owed
    return owed + (_UNPROVABLE_HOLD.format(generation.plan_pr_number),)


def _outstanding(generation: _late_models.LateGeneration) -> tuple[str, ...]:
    """Everything this cancellation may not leave the remote holding.

    The reclamation owner's own reading of the branch and the ref, plus the
    held pull request that owner never sees: a cycle cancelled before its
    split landed is the one case where one is still open, since
    every path that reaches an umbrella superseded it on the way.

    What it names is what this ending ACTS on and reports, which is why it is
    a list of names. Whether anything at all is still owed is the wider
    question `_unsettled` asks.
    """
    return _late_cleanup_reading._blocking(generation) + _owed_plan_pr(generation)


def _unsettled(generation: _late_models.LateGeneration) -> bool:
    """Whether anything this cancellation took on is owed by any reading.

    Two readings, because neither contains the other and an obligation either
    one counts is one nobody is coming back for once the issue has left this
    owner. What the ending lists is the branch, the ref, and the plan pull
    request -- including the one it can name and cannot prove it ever held.
    What the domain's own settled-ledger answer adds is a child receipt, which
    is none of those three, and a consumer ledger this binary could not type.

    It is the question a DISPATCH is decided by rather than the one a terminal
    is: an unlabeled owner is let past this guard into ordinary work only over
    a cycle that owes nothing at all, and the restart beside it authorizes a
    fresh cycle on exactly the same reading -- so no state falls between the
    two, and neither can hand an issue to a stage handler over an obligation
    the other was holding.
    """
    if _outstanding(generation):
        return True
    return not _restart.obligations_settled(generation)


def _plan_pr_entry(
    generation: _late_models.LateGeneration, target: str,
) -> _late_models.LateResource | None:
    """The ledger entry this pass just wrote for the held PR.

    None where the update could not be applied at all, which the recording
    helper already logged: there is nothing to report about an obligation the
    record does not carry.
    """
    for entry in generation.resources:
        if entry.kind == _PLAN_PR and entry.target == target:
            return entry
    return None
