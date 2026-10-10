# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The move a counted round owes `validating`, made recoverable across its relabel.

A label move and a pinned write cannot be one operation, so the order decides
what a crash between them costs. Moved first, a write that is then lost leaves
`validating` holding the head with the round never counted and the reviewer's
budget still the one the replaced head was reviewed under -- and nothing on
that stage reads a conflict receipt, so no later tick ever counts it. Written
first, whichever half fails leaves something a tick can finish.

So the round is written with the head it hands on, ahead of the relabel, and
that claim comes off in a write behind it. The round's audit event goes out
between the two, once the count it reports is down: a count write that never
landed has said nothing, and the tick that counts the round again behind the
receipt the push left is the one that reports it. A process ending between
that write and the event loses the event rather than sending it twice, since
no later tick can say whether it went out. A relabel that never landed leaves
the claim on `resolving_conflict`, and the next tick -- finding the branch in
sync and standing on that head -- makes the move without counting the round a
second time, ahead of every receipt, resume, and rebase. A claim about any
other head is dropped, since the branch it handed on is not the one this tick
reads -- but only where that is PROVED: a head nothing could prove holds the
tick with the claim in place, since read as no claim the branch would be
resolved again and the counted round counted, or capped, a second time. A
write behind the relabel that was lost leaves the claim on
`validating`, which retires it first thing (`_retires_the_claim`): reached
there, the move it was written for has been made. Left standing it would
outlive the review, the approval and the docs pass, and the next conflict
episode over that same head -- a base the branch no longer rebases onto
cleanly -- would read it as this one's unfinished move and hand the head
straight back to review with nothing resolved. The base refresh that opens
such an episode drops it in the write that routes the issue here, for an
issue it routes before `validating` ever ran.
"""
from __future__ import annotations

import logging
from pathlib import Path

from github.Issue import Issue

from orchestrator.git.measurement import commits as _measurement_commits
from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.late_split import formats as _formats, payloads as _payloads
from orchestrator.workflow.stages.conflicts import models as _models, state as _state
from orchestrator.workflow.state import WorkflowLabel

log = logging.getLogger("orchestrator.workflow")

# The revision a checkout's own head is named by.
_HEAD = "HEAD"


def _writes_the_count(ctx: _models._ConflictContext, sha: str | None) -> None:
    """Write the counted round and the head it hands on, ahead of the move it pays for.

    The caller has staged the round, and reports it once this returns. A
    round with no head to name hands on without a claim, since a claim
    nothing can be compared against could only ever be dropped.
    """
    if sha:
        ctx.state.set(_state._HANDED_SHA, sha)
    ctx.gh.write_pinned_state(ctx.issue, ctx.state)


def _moves_on(ctx: _models._ConflictContext) -> None:
    """Move the label the written round paid for, then drop the claim it was written with."""
    ctx.gh.set_workflow_label(ctx.issue, WorkflowLabel.VALIDATING)
    _retires_the_claim(ctx.gh, ctx.issue, ctx.state)


def _makes_the_owed_move(
    ctx: _models._ConflictContext, sync: _models._WorktreeSync,
) -> bool:
    """Make the move a counted round wrote down and never made; True where this tick ends on it.

    In sync with the remote and standing on the head the claim names, or not
    at all: the round is already counted, so all that is owed is the label,
    and only over the checkout the round handed on. A checkout PROVED to be
    elsewhere -- out of step with its remote, or on another commit -- drops
    the claim with the next write and lets the tick carry on, as does a claim
    too damaged to name a commit.

    A head nothing could prove is neither, and holds the tick with the claim
    in place. Dropped there, the tick would read the branch as one still to
    be resolved: the round already counted would be counted again by the
    no-op flip, or parked at the conflict cap that count reached, with its
    move never made. Held, the next tick that can prove the head makes it.
    """
    recorded = ctx.state.get(_state._HANDED_SHA)
    if recorded is None:
        return False
    handed = _payloads.as_hex(recorded, _formats.COMMIT_LENGTHS)
    if not handed or sync.ahead or sync.behind:
        ctx.state.set(_state._HANDED_SHA, None)
        return False
    proved = _measurement_commits._prove_candidate_commit(sync.worktree, _HEAD)
    if not proved.is_frozen:
        log.warning(
            "issue=#%d resolving_conflict: could not prove the head the round "
            "that handed %s on stands on; holding its move for a tick that can",
            ctx.issue.number, handed[:8],
        )
        return True
    if proved.sha != handed:
        log.error(
            "issue=#%d stands on %s rather than %s, the head its counted round "
            "handed on; dropping the move it owed",
            ctx.issue.number, proved.sha, handed,
        )
        ctx.state.set(_state._HANDED_SHA, None)
        return False
    log.info(
        "issue=#%d resolving_conflict: the round that handed %s on is counted "
        "and its move to validating never landed; making it",
        ctx.issue.number, handed[:8],
    )
    ctx.gh.set_workflow_label(ctx.issue, WorkflowLabel.VALIDATING)
    _retires_the_claim(ctx.gh, ctx.issue, ctx.state)
    return True


def _standing_on(
    ctx: _models._ConflictContext, worktree: Path, recorded: str,
) -> bool:
    """Whether this checkout is the commit a record names.

    Proved rather than read, because everything past it is a claim about one
    object id: a revision this host cannot peel is not a head that matches
    anything, and a host that never had the commit answers exactly that.
    """
    proved = _measurement_commits._prove_candidate_commit(worktree, _HEAD)
    if proved.is_frozen and proved.sha == recorded:
        return True
    log.error(
        "issue=#%d stands on %s rather than %s, the head this stage recorded; "
        "handing nothing on over it",
        ctx.issue.number, proved.sha or "an unreadable head", recorded,
    )
    return False


def _retires_the_claim(gh: GitHubClient, issue: Issue, state: PinnedState) -> None:
    """Drop the claim in a write of its own; a comment carrying none is left alone.

    Behind the move it was about, on this stage, and on `validating` before
    anything else that stage does, where the move has been made by the time
    it reads the comment.
    """
    if state.get(_state._HANDED_SHA) is None:
        return
    state.set(_state._HANDED_SHA, None)
    gh.write_pinned_state(issue, state)
