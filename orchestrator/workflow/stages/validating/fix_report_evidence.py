# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a report with no code in it has to prove, and what its refusal owes.

A fix round that answers the reviewer in words alone publishes onto a head it
does not push, so that head is the whole of what it stakes: proved wrong, the
report describes work no reviewer will ever read. The disposition beside this
owner cannot prove it, because "this run committed nothing publishable" is the
same answer it gives a checkout nobody could read, a fetch that failed, a
divergence git refused and a remote that moved -- and each of those may be a
branch carrying a commit the pull request has not got.

So the reading is taken here, affirmatively and on both halves: the branch
standing exactly where its remote is, and the code-publication receipt naming
that same commit on the pull request the report would go onto. Short of all of
it the round is parked with the debt recorded and the report unwritten, since a
record made over an unproved head is one no reconciliation could ever settle
honestly.

The consumed-input write sits here beside them because it is the same kind of
obligation, owed by every park rather than by one: a park is durable the moment
it is taken, so the input the run's prompt delivered has to be in that write
rather than in a caller's afterwards.
"""
from __future__ import annotations

from pathlib import Path

from github.Issue import Issue

from orchestrator import config
from orchestrator.config import models as _config_models
from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    report_consumed_values as _consumed,
    report_delivery as _report_delivery,
)
from orchestrator.workflow.stages.implementing import (
    late_publication_state as _late_publication_state,
)
from orchestrator.workflow.stages.validating import (
    models as _models,
    state as _state,
    stranded as _stranded,
)

# Why a report alone is refused over a head nothing could prove. Its own notice
# rather than the engine's: what is missing here is not the report but the
# evidence that the pull request carries the work the report is about.
_UNPROVED_HEAD_PARK = (
    "{mentions} this issue's developer answered the reviewer in its completion "
    "report alone, with no repository change -- and this orchestrator cannot "
    "prove the pull request is standing on the work that report describes. "
    "Either the branch, its remote, or the checkout could not be read, or the "
    "branch is carrying a commit the pull request has not got. Nothing was "
    "published and nothing was recorded: the branch and the pull request are "
    "exactly as they were. A report published onto a head no reviewer will see "
    "is no answer to the review, so the round is held here instead. Reply and "
    "the orchestrator resumes the session; the report it writes then is the "
    "one that gets published, and any commit the branch is carrying goes out "
    "through the ordinary measurement with it."
)


def _proves_the_published_head(
    spec: _config_models.RepoSpec,
    issue: Issue,
    state: PinnedState,
    worktree: Path,
) -> bool:
    """Whether the head a report alone would go onto is proved, affirmatively.

    Two readings, and both have to have HAPPENED. The BRANCH is proved to be
    standing exactly where its remote is -- a clean tree, a local head, a tip,
    the two equal -- which is what says the pull request is not short of a
    commit somebody committed and never pushed. And the code-publication
    RECEIPT is proved to name that same commit on the pull request this report
    would be about, which is what says the head the branch agrees on is the
    head the pull request carries rather than one that merely looks like it.

    Nothing here is inferred from an absence. The disposition's own answer --
    this run committed nothing publishable -- is the same answer it gives a
    checkout nobody could read, a fetch that failed, a divergence git refused
    and a remote that moved, so a report taken on that answer alone would be
    published over work no reviewer is going to see.

    Asked of a CHECKOUT rather than of a run, because what it is about is a
    checkout rather than a session: the disposition holds the run and the
    worktree it ran in, and everything it proves is about where that worktree
    stands. One caller only -- the `fixing` stage answers the same question
    for itself, over a pull request it reads AFRESH rather than over this
    receipt, which is persistent and on a tick that pushed nothing names an
    older round's commit.
    """
    head = _stranded._stranded_evidence(spec, worktree, state, issue).in_sync
    if not head:
        return False
    published = _late_publication_state._published_pull_request(state)
    if not published or published != _late_publication_state._recorded_pull_request(state):
        return False
    return _late_publication_state._published_commit(state) == head


def _parks_the_unproved_head(
    gh: GitHubClient,
    issue: Issue,
    state: PinnedState,
    run: _models._DevFixRun,
) -> str:
    """Hold a report whose head nothing could prove, and record the debt.

    The report is not recorded, because a record made here is one the
    reconciliation would have to settle against a commit nobody proved: bound
    to the receipt's head it would describe work the branch may be ahead of,
    and bound to nothing it would never settle at all. The debt goes down
    instead, which is what reads the reply to this park as the answer to the
    report it asked for -- and the commit under it, where there is one, reaches
    the pull request the way every other candidate does once the reading that
    refused can be taken.
    """
    state.set(_report_delivery.OWED_REPORT, True)
    _report_delivery.parks_an_undeliverable_report(
        gh, issue, state,
        _UNPROVED_HEAD_PARK.format(mentions=config.HITL_MENTIONS),
        consumed=run.handed.watermarks,
    )
    return _state._OUTCOME_PARKED


def _consumes_the_delivered(
    state: PinnedState, run: _models._DevFixRun,
) -> None:
    """Record what this run's prompt delivered, ahead of a park's own write.

    Forward only, and taken before the park rather than after it: the park is
    durable the moment it is posted and written, and a process dying between
    that write and a caller's own would leave the issue awaiting a human over
    input still marked unread -- which the next tick reads as fresh feedback
    and resumes the developer on again.

    Empty for every caller that settles what it delivered for itself; the fix
    loop's resume hands the pairs here because the road where the report IS the
    handover may not record them until that report lands.
    """
    _consumed.advance_consumed(state, run.handed.watermarks)
