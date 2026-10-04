# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a tick that died mid-split left behind, and what the next one may do.

Respawning the decomposer is the one thing recovery must never do. A crashed
split has already opened real GitHub issues, and a second manifest would not
reproduce the first, so the children it creates land beside the orphans rather
than instead of them. Every path here therefore ends in finalize or park, and
the two persistent markers `split` writes are what tells them apart:
`expected_children_count` goes down before the first child is created, and
`children` grows after each one is.

Those same two markers are written by the late split transaction, which owns
them for as long as its generation is live -- so a live generation stops this
recovery outright rather than finalizing a split that has not finished
snapshotting, superseding, or recording what the remote is owed. The tick ends
having changed nothing, which is what leaves the transaction free to resume
from its own durable facts.

Equal counts mean the loop finished and only the label flip was lost, so the
parent finalizes to whatever the manifest asked for, posting the summary the
split owes first (`split_summary`). A split that met a child another poller on
this host held leaves this behind on purpose, that child unseeded. Fewer mean the loop
stopped short: the one child a crash can leave created and unrecorded is
adopted by its receipt (`split_receipts`), and anything short of that parks,
since the manifest that declared the rest is not kept to create them from.

Finalizing repairs every recorded child first, against the lineage the
parent's record proves (`ReplacementLineage.repair`): a missing parent link
or ancestry is seeded -- a child started without its ancestry would be read
by its size gate as a fresh root at depth 0 -- a lost consumer slot is
restored ahead of the seed, and the seeding write lifts the park the missing
seed earned. A lineage no longer proved, or a child this split cannot
recognize as its own (see `split_repair`), parks instead of
finalizing, which keeps every child of that split unstarted. A child another
poller on this host is writing is repaired under its own writer claim or not
at all: the recovery stops there without a park, and the next tick resumes it.
"""
from __future__ import annotations

import logging

from github.Issue import Issue

from orchestrator import config
from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import guards as _guards
from orchestrator.workflow.late_split import state as _late_state
from orchestrator.workflow.stages.decomposition import (
    child_claims as _child_claims,
    late_relabel as _late_relabel,
    replacement_lineage as _replacement_lineage,
    split_receipts as _split_receipts,
    split_repair as _split_repair,
    split_summary as _split_summary,
    state as _state,
)

log = logging.getLogger("orchestrator.workflow")


def _park_incomplete_decomposition(
    gh: GitHubClient,
    issue: Issue,
    state: PinnedState,
    expected,
    adoption: _split_receipts.Adoption,
) -> None:
    stranded = "" if adoption.stranded is None else f"; {adoption.stranded}"
    _guards._park_awaiting_human(
        gh, issue, state,
        f"{config.HITL_MENTIONS} decomposition crashed mid-way: "
        f"{len(adoption.children)} of {expected} children recorded{stranded} "
        "(an orphan child issue may exist on GitHub if the crash landed "
        "between `create_child_issue` returning and the parent state write "
        "of a split whose children carry no receipt); manual intervention "
        "needed (close any partial children and re-decompose, or finish "
        "creating the missing ones).",
        reason="decomposition_crash",
    )
    gh.write_pinned_state(issue, state)


def _repair_recovered_child(
    gh: GitHubClient,
    issue: Issue,
    state: PinnedState,
    child_number,
    lineage: _replacement_lineage.ReplacementLineage,
) -> bool:
    """Repair one recorded child under its own writer claim, or stop the recovery.

    The claim is taken in front of the read the repair decides on and held
    through its write, because both are the child's record. A child another
    poller on this host is writing is not one this tick may repair, and not
    one it may finalize past either -- so the recovery stops where it stands,
    parking nothing, and the next tick's recovery asks again. The children
    repaired before it carry exactly what they were owed.
    """
    try:
        with _child_claims.held_child(gh, issue.number, child_number) as held:
            if not held:
                return False
            refusal = _split_repair._seed_orphan_child_state(gh, issue, state, child_number, lineage)
    except Exception:
        log.exception(
            "issue=#%s could not repair orphan child #%s during "
            "decomposition recovery", issue.number, child_number,
        )
        _guards._park_awaiting_human(
            gh, issue, state,
            f"{config.HITL_MENTIONS} could not repair child #{child_number} "
            "during decomposition recovery (seed `parent_number`, and any "
            "late lineage it inherits, on its pinned state); manual "
            "intervention needed (check orchestrator logs).",
            reason="child_seed_failed",
        )
        gh.write_pinned_state(issue, state)
        return False
    if refusal is not None:
        _replacement_lineage.park_unproved(gh, issue, state, refusal)
        return False
    return True


def _repair_recovered_children(
    gh: GitHubClient, spec: config.RepoSpec, issue: Issue, state: PinnedState, children: list,
) -> bool:
    """Repair every recorded child, or park where their lineage is unproved.

    The lineage is asked before any child is touched, because a repair that
    seeded some children and then refused the rest would leave a split half
    one lineage and half none -- and the park that refusal takes is what keeps
    all of them from being finalized into the walk that starts them. A child
    whose own ancestry is refused stops the walk the same way; the children
    seeded before it carry exactly what they were owed either way.
    """
    lineage = _replacement_lineage.read_replacement_lineage(state, issue, spec)
    if lineage.refusal is not None:
        _replacement_lineage.park_unproved(gh, issue, state, lineage.refusal)
        return False
    return all(
        _repair_recovered_child(gh, issue, state, child_number, lineage)
        for child_number in children
    )


def _markers_not_ours(issue: Issue, state: PinnedState) -> bool:
    """Whether these split markers belong to another owner's decision.

    Two owners can hold them. A human holds them once the issue is parked
    awaiting one: it is stopped either way, and there is nothing for a
    recovery to add. The late split transaction holds them for as long as its
    generation is live, because it writes the same two markers and resumes
    from its own durable facts -- finalizing on its behalf would hand a parent
    on before its snapshot, its supersession, or what the remote is owed had
    been settled.
    """
    if _late_relabel._adjudication_is_live(
        _late_state.read_late_generation(state),
    ):
        log.info(
            "issue=#%s carries a live oversized candidate; leaving its split "
            "markers to the late transaction that wrote them",
            issue.number,
        )
        return True
    return bool(state.get(_state._AWAITING_HUMAN))


def _recover_stale_manifest(
    gh: GitHubClient, spec: config.RepoSpec, issue: Issue, state: PinnedState
) -> bool:
    """Half-finished decomposition recovery / stale manifest cleanup.

    Returns True when a recovery path took over and the caller must
    return; False when no manifest markers are present and the caller
    should proceed to spawn the decomposer.

    Two persistent markers signal a prior tick crashed mid-split:
      * `expected_children_count` is written BEFORE any child is created,
        so a SIGKILL after `create_child_issue` returns but before the
        parent records the new child number leaves the parent with this
        marker AND one child fewer recorded than exist on GitHub.
        Re-running the decomposer here would emit a different manifest and
        create duplicate children alongside the orphan, so the orphan is
        found by the receipt naming this split's attempt and that slice,
        and recorded.
      * `children` is written incrementally after each successful create +
        parent-state flush. Its presence covers a crash after at least one
        child was recorded.
    Either marker present without the parent label having flipped to
    `blocked` means we cannot safely respawn the decomposer. Branch by
    whether the recorded count matches expectations once any orphan is
    adopted: equal -> finalize to `blocked`; less, or an orphan that may not
    be adopted -> park awaiting human. Legacy state from a deploy that
    pre-dates `expected_children_count` still routes through the
    `children`-only branch and finalizes.
    """
    expected_raw = state.get("expected_children_count")
    children_recorded = state.get(_state._CHILDREN) or []
    if expected_raw is None and not children_recorded:
        return False
    if _markers_not_ours(issue, state):
        return True
    if expected_raw is not None and len(children_recorded) < int(expected_raw):
        adoption = _split_receipts.adopt_unrecorded(gh, spec, issue, state, children_recorded)
        if adoption.stranded is not None or len(adoption.children) < int(expected_raw):
            _park_incomplete_decomposition(gh, issue, state, expected_raw, adoption)
            return True
        children_recorded = adoption.children
    # Before finalizing to `blocked`, repair any child whose pinned
    # state was never seeded -- one a split left to this recovery because
    # another poller held it, or one a crash left. A SIGKILL between the
    # parent's incremental `children` write and the child-state write at
    # the LAST child satisfies `len(children) == expected_children_count`
    # but leaves that child orphaned: no `parent_number`, no late
    # ancestry, and likely already parked with `awaiting_human=True` by a
    # prior `_handle_blocked` tick that saw it as "unattributed blocked".
    # Without repair, the parent's later walk flips the orphan to
    # `ready`, but `_handle_implementing` reads the stale park and
    # sits waiting for a human reply that never comes -- and a size gate
    # that did reach it would mint it a fresh lineage at depth 0.
    if not _repair_recovered_children(gh, spec, issue, state, children_recorded):
        return True
    # The summary the split never posted -- one that left a held child to
    # this recovery deferred it on purpose, and a crash may have cut it off
    # -- goes out ahead of the label flip, as the split's own finalize posts
    # it, and only where the thread carries no receipt for this attempt.
    finalize_label = _split_summary.recovered(gh, issue, state, children_recorded)
    gh.set_workflow_label(issue, finalize_label)
    gh.write_pinned_state(issue, state)
    return True
