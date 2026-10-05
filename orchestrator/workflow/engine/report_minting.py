# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The record one finished run's report outcome earns, minted before it is recorded.

What is minted is the run's own half and no more. Which pull request the report
goes onto, on which branch, standing on which commit, is settled by the
publication that follows and is bound onto the record there. The requirements
revision is the exception and belongs to the run: it is the issue content this
session was actually handed, so a report held back by a failed push is still
stamped with the requirements it answers rather than with an edit it never saw.

The revision moves past every report this issue has already recorded -- the
settled one, any transaction still outstanding, and any delivery still waiting
to be bound -- and the receipt is spelled from it. That is what keeps a second
report on the same commit a transaction of its own: a retry finds its own
comment by its receipt, so two reports sharing one would leave the later one
reading the earlier one's comment as its own publication, edited beyond
recognition.

All of it is minted from the records the tick holds, which is why recording it
is a guarded commit decided on those very records (`report_delivery`): a record
another road wrote since the tick read them refuses the write, so a revision is
never minted past a comment that has moved on.
"""
from __future__ import annotations

import logging

from github.Issue import Issue

from orchestrator.agents.models import AgentResult
from orchestrator.github import client as _client, pinned_state as _pinned_state
from orchestrator.github.pull_request_reports import ReportLocation
from orchestrator.workflow.engine import (
    prompt_delivery as _prompt_delivery,
    report_delivery_state as _delivery_state,
    report_outcome_models as _outcome_models,
    report_outcomes as _outcomes,
    report_record_state as _record_state,
    report_records as _records,
    report_settlement_state as _settlement,
)

log = logging.getLogger("orchestrator.workflow")

# The records a report is minted from: every report record its revision moves
# past and its superseded bookkeeping is carried from, and the requirements
# baseline it is stamped with where its run named none. Recording one is decided
# on exactly these, so a record minted from a reading that has since moved is
# never written.
MINTED_FROM = frozenset((
    _records.DELIVERED_REPORT, _records.PENDING_REPORT, _records.CURRENT_REPORT,
    _prompt_delivery.PINNED_USER_CONTENT_HASH,
))

# How a transaction minted here is named. The revision is what makes it
# unique per issue, and the spelling is one the report header carries verbatim.
_RECEIPT = "issue-{issue}-report-{revision}"


def delivered_report(
    gh: _client.GitHubClient,
    issue: Issue,
    state: _pinned_state.PinnedState,
    agent_result: AgentResult,
    handed: _records.HandedRun,
) -> _records.DeliveredReport | None:
    """The record one run's report outcome earns, or None where it earns none.

    None is every run that did not finish on a report: one that timed out, was
    interrupted, failed in its provider, exited nonzero, came back with a
    question, or reached for the contract and missed. None of those is a report
    anybody wrote, and recording one would publish a transcript under a header
    saying it is this issue's completion report.

    The bookkeeping and the consumed input the caller froze travel with it
    unread: what this owner knows about them is that the write which settles
    the report is the one that has to apply them, because on a road with no
    size gate behind it nothing else closes the round, and feedback a round
    answered may not be recorded as read until the report answering it lands.

    They travel with what this record SUPERSEDES as well, and that is why the
    merge is here rather than at a caller. A record still outstanding is a
    handover nothing confirmed, so none of what it owes has been written
    anywhere -- and this record replaces it: the delivery is dropped by the
    write that records this one, and the transaction by the binding behind it.
    Minted on the caller's pairs alone, a report that supersedes an unsettled
    one publishes and closes only its own road's bookkeeping, leaving a round
    nobody spent, bookmarks nobody cleared, and feedback a developer already
    answered reading as fresh. Carried, the one write that settles this report
    closes both handovers, which is the same exactly-once the frozen pair buys
    a replay.

    The settled report is not superseded by any of this: it is what the pull
    request already carries, and what it owed was written by the settlement
    that put it there.

    The requirements revision is the one the RUN was handed, never one
    computed here: a human editing the issue while the agent worked leaves the
    current content one revision further on than anything this session ever
    saw. A caller that snapshotted it names it on the `HandedRun` it passes;
    otherwise it is read off the pinned baseline the drift check ahead of the
    spawn put there.

    The revision moves past every report this issue has already recorded: the
    settled one, any transaction still outstanding, and any delivery still
    waiting to be bound. A settlement replaces the current report, so a
    revision that did not move forward would put an older report on the pull
    request's own record of what it carries -- and a transaction still
    outstanding may already have posted its comment and lost the response, so
    a report minted at its revision would carry its receipt too and read that
    comment as its own, edited beyond recognition. The delivery is the third
    for the road that overwrites one: the reply a park earns brings a report
    rather than a commit, and minted at the revision the record it replaces
    already used it would take that record's receipt with it. A record nobody
    can read counts as nothing here, which is the same answer every reader in
    this domain gives it.
    """
    carried = _carried_by_outcome(
        gh, _outcomes._report_outcome_of_run(agent_result),
    )
    if carried is None:
        return None
    # The records this one replaces, oldest first: a transaction is bound
    # before any delivery standing beside it, since the binding drops the
    # delivery it came from in the write that records it.
    superseded = tuple(outstanding for outstanding in (
        _record_state.read_pending_report(state),
        _delivery_state.read_delivered_report(state),
    ) if outstanding is not None)
    revision = 1 + max(
        (report.report_revision for report in (
            _settlement.read_current_report(state), *superseded,
        ) if report is not None),
        default=0,
    )
    requirements = handed.requirements_revision or state.get(
        _prompt_delivery.PINNED_USER_CONTENT_HASH,
    )
    return _records.DeliveredReport(
        receipt=_RECEIPT.format(issue=issue.number, revision=revision),
        report_revision=revision,
        route=handed.route,
        requirements_revision=requirements if isinstance(requirements, str) else "",
        spends=_carried_on(
            [record.spends for record in superseded], handed.spends,
        ),
        watermarks=_carried_on(
            [record.watermarks for record in superseded], handed.watermarks,
        ),
        **carried,
    )


def _carried_on(superseded: list, handed: tuple) -> tuple:
    """One value per field, over every record a new one supersedes.

    The pairs are ``((field, value), ...)`` and each field is written once, so
    the merge is a mapping filled in the order it is handed: a field an
    outstanding record names and this run names again keeps THIS run's reading
    of it. Every one of these pairs was computed against a comment the
    superseded record wrote nothing to, so the later value already accounts for
    whatever the earlier one would have closed.

    The watermarks need no such care -- they are applied as a forward-only
    ratchet -- but they are merged through the same rule, because one rule over
    one shape is what keeps the two halves from drifting apart.
    """
    carried: dict = {}
    for pairs in (*superseded, handed):
        carried.update(pairs)
    return tuple(carried.items())


def _carried_by_outcome(
    gh: _client.GitHubClient, outcome: _outcome_models._ReportOutcome,
) -> dict | None:
    """What one report outcome contributes to a record, or None for no report.

    A READY report is a publication and carries its text. A VERIFIED one is an
    assertion about a report that is already somewhere, and carries the exact
    place and the digest read there -- nothing about it is believed here, and
    the transaction it becomes re-reads that location before anything settles.

    A verification this owner cannot hold against THIS repository is refused
    where it is read. The location is exact in both halves and still names a
    place anywhere on GitHub, and the publication it would be bound to is on
    this repository -- so a record made from it would re-read somebody else's
    thread and settle on what it found there. Which pull request it names is
    bound and refused where the publication is known, since no pull request
    exists to compare it against yet.

    That comparison is the one reading on this road that leaves the process:
    it completes a repository PyGithub may hold only a URL for, so it can fail
    the way any request can. Raised, it would leave a finished run's report
    neither recorded nor parked -- the tick would die carrying the only copy
    of what the developer said, with the commit in a worktree nothing has said
    anything about. So a reading nobody could take answers the same as one that
    named another repository: no record, and the run held for a human, which is
    the one road from here that loses nothing.
    """
    if isinstance(outcome, _outcome_models._ReadyReport):
        return {"mode": _records.ReportMode.PUBLISH, "report": outcome.report}
    if not isinstance(outcome, _outcome_models._VerifiedReport):
        return None
    try:
        own_repository = gh.is_own_repository(outcome.location.slug)
    except Exception:
        log.exception(
            "could not hold a verified report's repository (%s) against this "
            "one; recording no report for it", outcome.location.slug,
        )
        return None
    if not own_repository:
        log.error(
            "a developer verified a report this orchestrator cannot hold "
            "against its own repository (%s); recording no report for it",
            outcome.location.slug,
        )
        return None
    return {
        "mode": _records.ReportMode.VERIFY,
        "location": ReportLocation(
            pr_number=outcome.location.pull_number,
            comment_id=outcome.location.comment_id,
        ),
        "content_revision": outcome.revision,
    }
