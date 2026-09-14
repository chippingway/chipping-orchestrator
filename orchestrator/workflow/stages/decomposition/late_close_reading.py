# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Read owner closure, cycle identity, receipt evidence, and completed cleanup.

A cycle being retired can still own an observed close. Unreadable owners
keep their observations until a later pass establishes where the ending stands.
"""
from __future__ import annotations

import logging

from github.Issue import Issue

from orchestrator.config import models as _config_models
from orchestrator.github import (
    client as _client,
    comments as _github_comments,
    issues as _issues,
    pinned_state as _pinned_state,
)
from orchestrator.workflow.engine import (
    retiring_cycles as _retiring_cycles,
)
from orchestrator.workflow.late_split import (
    models as _late_models,
    state as _late_state,
)
from orchestrator.workflow.stages.decomposition import (
    late_cancellation_reading as _late_cancellation_reading,
)
from orchestrator.workflow.state import (
    WorkflowLabel,
)

log = logging.getLogger("orchestrator.workflow")


# The receipt a poll leaves on the thread for the close it could hand to no
# worker. Scoped to the cycle, because that is the scope of a cancellation: an
# operator who authorizes a restart gets a fresh cycle, and an unscoped receipt
# would end that one too, for a close that happened before it existed.
_OBSERVED_CLOSE_MARKER = (
    "<!--orchestrator-late-close-observed:issue={issue}:cycle={cycle}-->"
)

# The labels that bring a tick back to a CLOSED issue -- the two an
# adjudication runs under and the two an interrupted ending can be left on.
# Nothing else does, so an ending still owed is reachable by wearing one of
# them or by the in-memory observation, and by nothing at all once it wears
# neither.
_SWEPT_LABELS = frozenset(_issues.CLEANUP_ROUTE_LABELS)


def _cleanup_settled(
    gh: _client.GitHubClient, spec: _config_models.RepoSpec, issue_number: int,
) -> bool:
    """Whether the ending a cleanup pass was routed for is actually over.

    What the dispatcher asks before it drops the close a cleanup was carrying,
    and the reason it has to ask at all: a pass can return having finished
    nothing. A consumer that is live again holds the ref, a remote that
    refuses a delete holds the branch, a held pull request a human reopened
    holds itself, and the terminal write is one more request that can be
    declined -- each of them leaves the pass returning normally with the
    ending still owed.

    Held only where nothing ELSE would come back, though, because the reading
    is not the only route: the closed sweep queries the two labels an
    adjudication runs under AND the two an interrupted ending can be left on,
    so an owner still wearing any of the four is one a later tick reaches on
    the sweep's own cadence -- which is the budget an operator set. Holding a
    reading over it would buy nothing and cost a cleanup pass per tick for as
    long as the ending is owed, and an ending can be owed for a very long
    time: a consumer that is live again keeps the ref until somebody ends it.

    What it covers is the label OUTSIDE all four, which is where a hand
    relabel or a terminal correction can leave an owner mid-ending. The sweep
    repairs that label where it can, so what the reading is really holding is
    the pass whose repair GitHub refused -- and there it is the only route
    left, until the process carrying it exits.

    An owner that is OPEN again is settled rather than held, and that is not
    the same as finished. The sweep may act externally on nobody's reopened
    issue -- it marks the cancellation and stops -- so holding the reading
    would route the owner back to a pass that is forbidden to advance it,
    every tick, forever. What the mark buys instead is the dispatcher's own
    guard, which is durable, owns a reopened cancelled owner, and reconciles
    it from the next tick.

    Fail-closed on a read that did not answer. The reading is the one thing
    this path exists to keep, and a request that failed establishes nothing
    about the ending -- so it keeps the observation and the next tick asks
    again, which costs one cleanup pass over an owner that may owe nothing.
    """
    try:
        reading = _owner_reading(gh, issue_number)
    except Exception:
        log.exception(
            "repo=%s issue=#%d could not be read back after its cleanup "
            "pass; holding the observation, since nothing establishes the "
            "ending finished", spec.slug, issue_number,
        )
        return False
    issue, state = reading
    if not _issues.issue_is_closed(issue):
        return True
    if gh.workflow_label(issue) in _SWEPT_LABELS:
        return True
    return _ending_is_over(gh, issue, state)


def _owner_reading(
    gh: _client.GitHubClient, issue_number: int,
) -> tuple[Issue, _pinned_state.PinnedState]:
    """The issue and the record a question about its ending is asked of.

    One reading rather than two, because the two answers have to agree: an
    owner refetched before the record and judged against a record written
    after it would be told about a close, a settlement, or a terminal that
    belongs to the other half.
    """
    issue = gh.get_issue(issue_number)
    return issue, gh.read_pinned_state(issue)


def _ending_is_over(
    gh: _client.GitHubClient, issue: Issue, state: _pinned_state.PinnedState,
) -> bool:
    """Whether one closed owner's record shows nothing of its cycle left.

    Three things in the order they become true, because a pass that stopped
    at any of them left the next one work to do: the cancellation is marked,
    every obligation the ledger holds is settled, and the terminal that says
    so is on the issue. The last is asked of GitHub rather than of the record
    -- the label is the write that takes an owner out of the sweep, and it is
    the one step of the ending that leaves no trace in the pinned comment.

    Asked only of an owner outside every swept label, so `rejected` is not
    the only label it can answer True for -- an ending whose terminal write
    GitHub refused stays on the label it had, which is what brings the next
    pass.

    A record with no cycle at all is over by definition: an umbrella the
    initial decomposer made never had one, and a retirement that dropped one
    is an ending that already ran.
    """
    generation = _late_state.read_late_generation(state)
    if not generation.is_present:
        return True
    if not generation.cancelled or _late_cancellation_reading._outstanding(generation):
        return False
    return gh.workflow_label(issue) == WorkflowLabel.REJECTED


def _ending_cycle(
    spec: _config_models.RepoSpec,
    issue_number: int,
    generation: _late_models.LateGeneration,
) -> int | None:
    """Which cycle a close observed now would end on this issue, if any.

    The record's own answer, and -- for the one window where the record has
    none -- the cycle a worker on this very issue is retiring RIGHT NOW. That
    window is an authorized settlement's last write: the identity comes off the
    record and the barrier that would answer a latched close stands behind
    it, so a reading taken in between would be called spent against a record
    whose worker is still holding the question open.

    It is what makes the durable half survive that write at all. A receipt is
    scoped to a cycle and a retired record has none to scope it to, so an
    observation made in the window would be latched in memory and written
    down nowhere -- exactly the shape a restart takes away entirely.

    None for a cycle already marked over as well as for no cycle at all:
    the ending is already on the record and the sweep its label names is
    what runs it, so the reading buys nothing a later pass has not got.
    """
    if generation.cancelled:
        return None
    if generation.is_present:
        return generation.cycle_id
    return _retiring_cycles.cycle_being_retired(spec.slug, issue_number)


def _observed_close_marker(issue_number: int, cycle_id: int) -> str:
    """The receipt one cycle's observed close is stamped with."""
    return _OBSERVED_CLOSE_MARKER.format(issue=issue_number, cycle=cycle_id)


def _carries_observed_close(
    gh: _client.GitHubClient, issue: Issue, marker: str,
) -> bool:
    """Whether this cycle's own close receipt is already on the thread.

    Walked whole rather than from a watermark: the receipt is posted by a
    poll rather than by a stage, so no watermark this mode keeps was moved
    past it and one bounded by any of them could start above it.
    """
    return _github_comments.carries_own_marker(
        gh.comments_after(issue, None),
        marker,
        bot_login=getattr(gh, "_bot_login", None),
    )


def _owns_a_live_cycle(
    gh: _client.GitHubClient, spec: _config_models.RepoSpec, issue_number: int,
) -> bool | None:
    """Whether this issue's record carries a cycle a close would end, or None.

    Asked for a CLOSED issue whose submit was refused, and only then: the
    cleanup route establishes the same thing from the label, and this
    establishes it from the record for the one window where no label says it.
    A read on a path that runs when a worker is already holding the issue is
    a read this orchestrator can afford.

    Taken only where the receipt above is not being written from a read of
    its own, which is the repeat case -- a poll whose thread already carries
    the receipt, or one another poll is posting right now. The first pass
    answers this from the read it wrote the receipt with, so the two never
    disagree about the same record.

    Three answers rather than two, and the third is what keeps the reading
    safe. False is the record positively saying there is nothing to end -- no
    cycle, or one already marked -- and a record whose cycle a worker is
    retiring right now is not saying that at all, so the retirement window is
    part of the question. None is a read that established NOTHING, which is
    not the same claim, and the caller keeps the observation it latched
    rather than dropping it on a request that failed.
    """
    try:
        state = gh.read_pinned_state(gh.get_issue(issue_number))
    except Exception:
        log.exception(
            "repo=%s issue=#%d could not be read for a late cycle a close "
            "would end; keeping the observation the poll took",
            spec.slug, issue_number,
        )
        return None
    return _ending_cycle(
        spec, issue_number, _late_state.read_late_generation(state),
    ) is not None
