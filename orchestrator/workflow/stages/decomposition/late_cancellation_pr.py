# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Release and close the pull request held by a cancelled late cycle.

The description is restored before its cancellation notice and closure.
The resource entry is persisted before reporting, and a final verification
prevents retirement beside a publication that changed during cleanup.
"""
from __future__ import annotations

import logging

from github.Issue import Issue

from orchestrator.github import (
    client as _client,
    pinned_state as _pinned_state,
)
from orchestrator.workflow.late_split import (
    models as _late_models,
)
from orchestrator.workflow.stages.decomposition import (
    late_cancellation_reading as _late_cancellation_reading,
    late_cancellation_state as _late_cancellation_state,
    late_cleanup as _late_cleanup,
    late_cleanup_state as _late_cleanup_state,
    late_hold_release as _late_hold_release,
)
from orchestrator.workflow.state import (
    stage_name,
)

log = logging.getLogger("orchestrator.workflow")


# Stamped on the notice a cancelled cycle leaves on the pull request it
# was holding, so a pass that repeats after a crash recognizes its own. Scoped
# to the cycle, which is the scope of a cancellation: a pull request outlives
# a cycle, and a restart mints a fresh one, so an unscoped marker would read a
# previous attempt's notice as this one's. An HTML comment, so it is invisible
# in the rendered thread.
_CANCELLED_MARKER = (
    "<!--orchestrator-late-cancellation:issue={issue}:cycle={cycle}-->"
)

_CANCELLED_NOTICE = (
    ":no_entry: **Cancelled.** Issue #{owner} was closed while its committed "
    "implementation was being adjudicated for size, so this pull request is "
    "closed without merging. Nothing further is published or created for that "
    "adjudication.\n\nReopening the issue does not resume it. The cancelled "
    "cycle settles what it already put on this repository and the issue ends "
    "on `rejected`, which an operator removes to authorize a fresh attempt."
    "\n\n{marker}"
)


def _reverified(
    gh: _client.GitHubClient,
    issue: Issue,
    state: _pinned_state.PinnedState,
    generation: _late_models.LateGeneration,
) -> _late_models.LateGeneration:
    """Ask the held PR again, on the far side of everything else owed.

    The terminal is the write that cannot be taken back: it takes the issue
    off every label the closed-owner sweep queries, so an owner that reaches
    it is one nothing revisits. The pull request was settled at the top of
    this pass and the record has said `reconciled` ever since -- but between
    the two stand a branch delete, a ref delete, and a fresh read of every
    recorded consumer, and a human who reopens the change inside them leaves
    the record saying one thing and the remote another. Retiring on the
    record would leave that change open under a cancelled cycle with nothing
    coming back for it.

    So the reading the terminal is taken on is one taken HERE, immediately
    before it. A pull request still where the earlier ask left it costs a
    fetch and a comment listing and moves nothing -- the notice is gated on
    this cycle's marker already on the thread, and one that is not open is
    left exactly as it is -- while one that is open again is closed again and
    an entry that could not be settled holds the terminal for the next visit.

    Only where nothing else is owed, which is the only visit whose terminal
    is actually due. An owner still holding a branch the remote will not
    delete is one the sweep is bringing back anyway, and the ask at the top
    of that next pass is the same ask.
    """
    if (
        _late_cancellation_reading._outstanding(generation)
        or _late_cancellation_reading._held_pull_request(generation) is None
    ):
        return generation
    return _plan_pr_settled(gh, issue, state, generation)


def _plan_pr_settled(
    gh: _client.GitHubClient,
    issue: Issue,
    state: _pinned_state.PinnedState,
    generation: _late_models.LateGeneration,
) -> _late_models.LateGeneration:
    """Take the hold off the pull request it marked, say why, and close it.

    Only the pull request this generation actually held -- the plan one where
    the cycle was entered before publication, and the implementation one the
    work is already on where it was entered past it. `pr_number` on the
    stage's own keys is whichever one the issue currently records and may name
    a change somebody else opened; the hold's record names the one this cycle
    marked, and closing anything else would end a change no adjudication ever
    touched.

    The hold comes off first, so a pull request that ends up closed is not
    also left carrying a "do not merge" notice forever. A release that failed
    on a still-open pull request stops the close: what that failure means is
    that the preserved description is not back where it belongs, and closing
    over it would settle the entry with a human's words still replaced.

    Run on EVERY visit, including one whose entry already reads `reconciled`.
    That entry records what an earlier visit did, and a pull request is not a
    thing that stays where it was put: a human can reopen one, and an owner
    the sweep is still visiting for a branch it cannot delete would otherwise
    reach `rejected` -- and leave the sweep for good -- beside a plan pull
    request that is open again under a cancelled cycle. Re-asking costs one
    fetch and one comment listing, and neither step repeats anything: the
    notice is gated on this cycle's own marker already on the thread, a pull
    request that is not open is left exactly as it is, and a description that
    is no longer this cycle's hold is not rewritten.

    What IS bounded is the record of it. The write and both sinks are behind a
    state that actually moved, because an entry saying what it already said is
    not news -- reporting it every visit would put one `late_cleanup` per
    cadence on an owner that is simply waiting for something else.
    """
    number = _late_cancellation_reading._held_pull_request(generation)
    if number is None:
        return generation
    released, reached = _reached(gh, issue, generation, number)
    settled = _late_cancellation_reading._plan_pr_entry(released, str(number))
    if settled is not None and settled.resource_state == reached:
        return released
    recorded = _late_cleanup_state._recorded(
        released, _late_cancellation_reading._PLAN_PR, str(number), reached,
    )
    _late_cancellation_state._persisted(gh, issue, state, recorded)
    _reported(gh, issue, recorded, str(number))
    return recorded


def _reached(
    gh: _client.GitHubClient,
    issue: Issue,
    generation: _late_models.LateGeneration,
    number: int,
) -> tuple[_late_models.LateGeneration, _late_models.LateResourceState]:
    """Release the hold, close the pull request, and say where that left it.

    The record travels back with the answer because the release is entitled to
    change it: what is written afterwards has to be written onto whatever the
    release left, not onto the copy this attempt started from.

    A release that failed stops the close rather than shortening it. The
    preserved description is the only copy of what the hold replaced, so a
    pull request closed while the hold is still on it is a human's words
    replaced for good.
    """
    release = _late_hold_release._release_hold(gh, issue, generation)
    if release.failed:
        return release.generation, _late_models.LateResourceState.FAILED
    if not _closed_over_notice(gh, issue, release.generation, number):
        return release.generation, _late_models.LateResourceState.FAILED
    return release.generation, _late_models.LateResourceState.RECONCILED


def _closed_over_notice(
    gh: _client.GitHubClient,
    issue: Issue,
    generation: _late_models.LateGeneration,
    number: int,
) -> bool:
    """Fetch the held pull request and hand it its cancellation.

    The fetch is guarded here rather than left to the helper, because a
    PyGithub pull request is lazy and the request that can fail is as likely
    to be this one as the write behind it -- and an exception escaping a
    cleanup pass would take the branch and the ref down with it, neither of
    which owes this pull request anything.

    Said at most once, proved from the thread the notice is on: the comment
    and the entry recording it cannot be made one operation, so a crash
    between them repeats this call, and the marker is what makes the repeat
    silent.
    """
    try:
        held = gh.get_pr(number)
    except Exception:
        log.exception(
            "issue=#%d could not read held PR #%d to close it",
            issue.number, number,
        )
        return False
    receipt = _cancelled_marker(issue, generation)
    return gh.supersede_pr(
        held,
        notice=_CANCELLED_NOTICE.format(owner=issue.number, marker=receipt),
        marker=receipt,
    )


def _cancelled_marker(
    issue: Issue, generation: _late_models.LateGeneration,
) -> str:
    """The receipt this cycle's cancellation notice carries."""
    return _CANCELLED_MARKER.format(
        issue=issue.number, cycle=generation.cycle_id,
    )


def _reported(
    gh: _client.GitHubClient,
    issue: Issue,
    generation: _late_models.LateGeneration,
    target: str,
) -> None:
    """Say on both sinks what this pass did to the held PR.

    Read back off the record rather than inferred from what GitHub said, for
    the reason every other obligation is: the entry is the only thing that
    carries both halves of an attempt that half-landed.
    """
    entry = _late_cancellation_reading._plan_pr_entry(generation, target)
    if entry is None:
        return
    _late_cleanup._emit_cleanup(
        gh, generation, entry, stage_name(gh.workflow_label(issue)),
    )
    if entry.resource_state != _late_models.LateResourceState.RECONCILED:
        log.warning(
            "issue=#%d could not close the PR its cancelled cycle held "
            "(%s); it is retried on every visit until it is",
            issue.number, target,
        )
