# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Whether the work a late record still owes a push for has already ended.

The reconciliation that runs ahead of every stage ends in a PUSH -- the reading
it takes does, and the debt road beside it exists to make one -- while the
terminal that drains finished work runs inside the stage handler, which is
BEHIND it. So an ending that reaches the orchestrator between the crash and the
recovery is the way work would otherwise land on a pull request nobody can
merge: a branch force-moved onto an issue somebody closed, or onto a pull
request a human already merged or turned down.

Two facts, because an issue's own flag shows only one of them. The OBJECT the
tick opened with says whether a human closed the issue. The PULL REQUEST the
record names says the other half -- a merge leaves the issue open until a stage
terminal reads it, and a close without a merge leaves it open for good -- and
there is nowhere for this push to land in either case. The gate below refuses
to freeze an entry against a terminal pull request, so without this the road
would end in `late_measurement_failed`: a human parked over a publication that
is finished.

Read fail-OPEN, which is the direction every reading whose alternative is
stranding an issue is read in: a remote that would not answer says nothing
about whether the work is over, so the tick falls through to the road that
takes its own reading and parks with the reason it fails for. The same fact
asked immediately before a PUSH is read the other way round, by
`late_publication`, because what falling through costs there is a branch
nothing can put back.

Asked BEHIND the record questions rather than at the reconciliation's door,
and that is a cost rather than a preference: the pull-request half is a
request, and this owner is consulted ahead of every stage on every poll. Read
at the door it would cost one request per issue per tick, and the only ticks
its answer can change are the ones that have something left to reconcile --
every one of which is behind that point.

What a caller does with True is hand the tick back, which costs nothing: the
stage's own terminal is the next thing that runs, and it marks the issue `done`
or `rejected` with the record, the branch and the debt left exactly as they
stand for it to drain.

The reconciliation asks one more thing at the same point
(`_answered_ahead`): every road it takes acts on the issue's branch and the
checkout at its path, so work that has not ended over a record or a checkout
no live work may use holds the tick with nothing parked or pushed.
"""
from __future__ import annotations

import logging

from github.Issue import Issue

from orchestrator.config import models as _config_models
from orchestrator.github.client import GitHubClient
from orchestrator.github.issues import issue_is_closed
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.late_split import payloads as _payloads
from orchestrator.workflow.stages.implementing import (
    late_overflow as _overflow,
    state as _state,
    worktree as _dev_worktree,
)

log = logging.getLogger("orchestrator.workflow")


def _work_has_ended(
    gh: GitHubClient, issue: Issue, state: PinnedState,
) -> bool:
    """Whether anything a push could still join is left, or the tick hands back.

    The issue is asked first because it costs nothing and the answer is
    already in hand; the pull request is the request, and it is spent only
    where the free reading did not already settle it.
    """
    if issue_is_closed(issue):
        log.info(
            "issue=#%d is closed; leaving whatever its record still owes to "
            "the stage terminal rather than publishing onto an issue nobody "
            "wants",
            issue.number,
        )
        return True
    if not _overflow._PublicationReading.is_over(
        gh, _payloads.as_identity(state.get(_state._PR_NUMBER)),
    ):
        return False
    log.info(
        "issue=#%d records a pull request that has merged or been closed; "
        "leaving whatever its record still owes to the stage terminal rather "
        "than publishing onto work nobody can merge",
        issue.number,
    )
    return True


def _answered_ahead(
    gh: GitHubClient, spec: _config_models.RepoSpec, issue: Issue, state: PinnedState,
) -> bool | None:
    """What the reconciliation answers before taking any road: False, True, or None where a road is taken.

    False over work that has ended (`_work_has_ended`), for the stage terminal
    to drain whatever the record pins -- its teardown keeps a branch that is
    not the issue's current one. True over a record naming no branch live work
    may use, or a tree at the issue's path not proven the issue's own
    (`worktree._refuses_live_work`), which holds the tick with nothing parked,
    posted, measured, or pushed, since every road behind this acts on that
    branch and that checkout.
    """
    if _work_has_ended(gh, issue, state):
        return False
    if _dev_worktree._refuses_live_work(spec, issue, state):
        return True
    return None
