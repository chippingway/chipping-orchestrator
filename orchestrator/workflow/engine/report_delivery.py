# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The report a finished developer run leaves, recorded before its code goes out.

The run is the only thing that can write this report, and it is gone the moment
the tick that ran it moves on. What happens next to the commit it made is not
quick and not certain: the size gate can freeze it for a human to adjudicate,
the push can fail, the process can die -- and on every one of those roads the
report exists nowhere but in the memory of a call that is about to return. So it
is recorded HERE, ahead of the gate and ahead of the push, where the only cost
of being wrong is a pinned write nothing reads.

What is recorded is the run's own half and no more. Which pull request the
report goes onto, on which branch, standing on which commit, is settled by the
publication that follows and is bound onto the record there. The requirements
revision is the exception and belongs to the run: it is the issue content this
session was actually handed, so a report held back by a failed push is still
stamped with the requirements it answers rather than with an edit it never saw.

A run that produced no report outcome records nothing at all, which is every
recovery a stage makes on its own behalf -- none of them ran a developer, and
the message they synthesize is the orchestrator's own. Their code still
publishes exactly as it did before, and a report an earlier run delivered is
still there to be bound onto the pull request that code reaches.

A report this build cannot record HOLDS the tick instead, parked for a human.
That is the one answer left: the record is what every later tick works from, so
a report that cannot be written is one nothing can publish -- and the run that
wrote it has ended, so nothing here can ask for a shorter one. Published
anyway, the work would reach review with no report and the record of what the
developer said would be gone. Held here, before the size gate and the push,
nothing is published at all: the commit stays in the worktree, the branch is
untouched, and a reply resumes the session that can write the report again.

What that resumed session comes back with is a report rather than a commit, and
`redelivers_an_owed_report` is what keeps it from being read as a question. An
issue owing a report was never waiting for code: the commits are already on the
branch, and a fresh report is exactly what the park asked for -- so the run that
brings one publishes through the ordinary seam, where its report replaces the
one nothing could deliver.

The route is the caller's, because a stage knows which road produced the run
and this owner cannot: it is recorded on the transaction so that whatever
finishes one -- here, or a poll later through the reconciliation -- closes the
bookkeeping of the road it came from.

The revision moves past every report this issue has already recorded, the
settled one and any transaction still outstanding, and the receipt is spelled
from it. That is what keeps a second report on the same commit a transaction of
its own: a retry finds its own comment by its receipt, so two reports sharing
one would leave the later one reading the earlier one's comment as its own
publication, edited beyond recognition.
"""
from __future__ import annotations

import logging
from pathlib import Path

from github.Issue import Issue

from orchestrator import config
from orchestrator.agents.models import AgentResult
from orchestrator.config import models as _config_models
from orchestrator.git.worktrees import creation as _worktree_creation
from orchestrator.github import client as _client, pinned_state as _pinned_state
from orchestrator.github.pull_request_reports import ReportLocation
from orchestrator.workflow.engine import (
    guards as _guards,
    prompt_delivery as _prompt_delivery,
    report_delivery_state as _delivery_state,
    report_outcome_models as _outcome_models,
    report_outcomes as _outcomes,
    report_record_state as _record_state,
    report_records as _records,
    report_settlement_state as _settlement,
)
from orchestrator.workflow.state import WorkflowLabel

log = logging.getLogger("orchestrator.workflow")

_PARK_REASON = "park_reason"

_AWAITING_HUMAN = "awaiting_human"

# What a report this workflow cannot get onto the pull request is parked
# under. One reason for both roads that take it -- a report that cannot be
# recorded before the push, and one that cannot be bound to the publication
# after it -- because both are answered the same way: the session that wrote
# the report is gone, so what clears either is a human, and a reply resumes a
# developer that can write the report again.
UNDELIVERABLE_REPORT = "report_undeliverable"

# How a transaction minted here is named. The revision is what makes it
# unique per issue, and the spelling is one the report header carries verbatim.
_RECEIPT = "issue-{issue}-report-{revision}"

_UNRECORDABLE_PARK = (
    "{mentions} this issue's developer run finished with a completion report "
    "this orchestrator cannot record on its pinned comment -- most likely one "
    "far past what a single comment holds -- so nothing was published: the "
    "commit is still in the worktree, the branch is untouched, and no pull "
    "request was opened. The report is recorded before any code goes out, "
    "because that record is the only thing a later tick could publish it "
    "from: a report that cannot be written is one this workflow has no way to "
    "put on a pull request, and publishing the code anyway would hand review "
    "an implementation with no report and no record of what the run said. "
    "Reply and the orchestrator resumes the session; the report it writes "
    "then is the one that gets published."
)


def owes_a_report(state: _pinned_state.PinnedState) -> bool:
    """Whether this issue still owes a pull request the report of a run.

    Both records, because the debt passes from one to the other and is
    discharged only at the end: a report a run delivered is owed until it is
    bound to a publication, and the transaction it becomes is owed until that
    publication carries it. A caller asking either alone would hand a reviewer
    an implementation whose report is sitting in the other.

    Asked of what the records CLAIM rather than of what they mean, so a record
    a hand edit truncated counts as a debt rather than as an issue that owes
    nothing. Neither claim is left unanswered: the binding parks a delivery it
    cannot read, and the reconciliation ahead of every handler parks a
    transaction it cannot -- both with the record untouched for whoever
    repairs or abandons it.
    """
    return (
        _delivery_state.carries_delivered_report(state)
        or _record_state.carries_pending_report(state)
    )


def recording_stops_the_tick(
    gh: _client.GitHubClient,
    issue: Issue,
    state: _pinned_state.PinnedState,
    agent_result: AgentResult,
    route: WorkflowLabel,
) -> bool:
    """Record what a finished run wrote, or hold the tick over what it wrote.

    True is a tick this owner ended: the run finished on a report and this
    build cannot record it, so the issue is parked and the caller publishes
    nothing. False is every other tick -- a run with no report outcome, which
    is every recovery a stage makes for itself and every session that came back
    with a question, and the ordinary run whose report is now on the pinned
    comment.

    The write is this owner's rather than the caller's, and that is the whole
    point of the step: what makes the report recoverable is that it is DURABLE
    before the size gate reads the candidate and before the push sends it, so
    a tick that dies anywhere past the call comes back to an issue that can
    still say what its developer reported.

    A record this build will not store HOLDS rather than waving the code
    through. The record is what every later tick would publish from, so a
    report that cannot be written is one nothing can ever put on a pull
    request -- and the run that wrote it has ended, so there is nobody left to
    ask for a shorter one. Held here the cost is bounded and visible: nothing
    is published, the commit is still in the worktree, and the notice says
    what happened. Published instead, the reviewer would be handed work with
    no report while the only copy of what the developer said went out of
    memory with the tick.
    """
    delivered = _delivered_report(gh, issue, state, agent_result, route)
    if delivered is None:
        return False
    if not _delivery_state.record_delivered_report(state, delivered):
        log.error(
            "issue=#%d wrote a developer report this build cannot record; "
            "publishing nothing and holding for a human", issue.number,
        )
        parks_an_undeliverable_report(
            gh, issue, state,
            _UNRECORDABLE_PARK.format(mentions=config.HITL_MENTIONS),
        )
        return True
    log.info(
        "issue=#%d recorded developer report revision %d before publishing "
        "the code it is about", issue.number, delivered.report_revision,
    )
    gh.write_pinned_state(issue, state)
    return False


def parks_an_undeliverable_report(
    gh: _client.GitHubClient,
    issue: Issue,
    state: _pinned_state.PinnedState,
    notice: str,
) -> None:
    """Announce a report this workflow cannot deliver, once, and hold it.

    Announced once per attempt, not once per issue. What is asked is whether
    this owner's park is still STANDING -- its reason on the comment and the
    issue still waiting on a human -- because that is the state a second
    notice would say nothing new about. A reply clears the waiting before the
    developer is resumed, so a report that fails to be delivered again is a
    fresh failure of a fresh attempt, and the human who asked for it hears
    about it.

    Its own reason, because that is the only thing that tells a later tick
    whose park it is standing over, and because the recovery is particular: a
    reply resumes the developer, which writes its report again. Nothing here
    retires it -- the resume that answers the reply is what clears the flags,
    exactly as it does for every other park on this stage.

    Public because both roads that cannot deliver a report take it: the
    recording above, before anything is published, and the binding after the
    push. Each words its own notice, since what the work is in the middle of
    differs; what they share is the flag, the reason, and the silence.
    """
    if state.get(_PARK_REASON) == UNDELIVERABLE_REPORT and state.get(_AWAITING_HUMAN):
        log.warning(
            "issue=#%d still owes a developer report this workflow cannot "
            "deliver; holding the tick without a second notice", issue.number,
        )
        return
    _guards._park_awaiting_human(
        gh, issue, state, notice, reason=UNDELIVERABLE_REPORT,
    )
    state.set(_PARK_REASON, UNDELIVERABLE_REPORT)
    gh.write_pinned_state(issue, state)


def redelivers_an_owed_report(
    spec: _config_models.RepoSpec,
    state: _pinned_state.PinnedState,
    agent_result: AgentResult,
    worktree: Path,
) -> bool:
    """Whether this run answers a report this issue owes rather than a question.

    The one road on which a run that committed nothing still has work to
    publish. A stage reads a head that did not move as a session that came
    back with a question, which is right for every ordinary run -- but an
    issue holding a report it could not deliver was never waiting for code:
    it was waiting for a report it could record and bind, and the commits the
    earlier run made are still on the branch with nothing published from them
    or nothing bound to them.

    Three readings, asked in the order that spends least. The DEBT says what
    the issue is waiting on, so a run that reports on an issue owing nothing
    is the ordinary no-commit reply its stage already knows how to read -- and
    asking it first is what keeps every other tick from paying for the two
    below. The OUTCOME says the developer considers the work finished, so a
    question, a disagreement, or a run that fell short is still a question:
    what supersedes an undeliverable report is another report and nothing
    else. And the BRANCH has to carry something, because what this licenses is
    a publication: a checkout with nothing ahead of base would push an empty
    branch and open a pull request with no diff in it.

    Spelled here rather than at either call site, because both roads a reply
    can take reach it -- the resume a park earns, and the drift resume an edit
    earns -- and a rule written twice is one that comes to differ.
    """
    if not owes_a_report(state):
        return False
    if isinstance(
        _outcomes._report_outcome_of_run(agent_result),
        _outcome_models._ReportRefusal,
    ):
        return False
    return _worktree_creation._has_new_commits(spec, worktree)


def _delivered_report(
    gh: _client.GitHubClient,
    issue: Issue,
    state: _pinned_state.PinnedState,
    agent_result: AgentResult,
    route: WorkflowLabel,
) -> _records.DeliveredReport | None:
    """The record one run's report outcome earns, or None where it earns none.

    None is every run that did not finish on a report: one that timed out, was
    interrupted, failed in its provider, exited nonzero, came back with a
    question, or reached for the contract and missed. None of those is a report
    anybody wrote, and recording one would publish a transcript under a header
    saying it is this issue's completion report.

    The requirements revision is read off the pinned baseline rather than
    computed here, because what is wanted is the revision the RUN was handed:
    the drift check ahead of the spawn is what put it there, and a human
    editing the issue while the agent worked leaves the current content one
    revision further on than anything this session ever saw.
    """
    carried = _carried_by_outcome(
        gh, _outcomes._report_outcome_of_run(agent_result),
    )
    if carried is None:
        return None
    revision = _next_revision(state)
    requirements = state.get(_prompt_delivery.PINNED_USER_CONTENT_HASH)
    return _records.DeliveredReport(
        receipt=_RECEIPT.format(issue=issue.number, revision=revision),
        report_revision=revision,
        route=route,
        requirements_revision=requirements if isinstance(requirements, str) else "",
        **carried,
    )


def _carried_by_outcome(
    gh: _client.GitHubClient, outcome: _outcome_models._ReportOutcome,
) -> dict | None:
    """What one report outcome contributes to a record, or None for no report.

    A READY report is a publication and carries its text. A VERIFIED one is an
    assertion about a report that is already somewhere, and carries the exact
    place and the digest read there -- nothing about it is believed here, and
    the transaction it becomes re-reads that location before anything settles.

    A verification naming another REPOSITORY is refused where it is read. The
    location is exact in both halves and still names a place anywhere on
    GitHub, and the publication it would be bound to is on this repository --
    so a record made from it would re-read somebody else's thread and settle
    on what it found there. Which pull request it names is bound and refused
    where the publication is known, since no pull request exists to compare it
    against yet.
    """
    if isinstance(outcome, _outcome_models._ReadyReport):
        return {"mode": _records.ReportMode.PUBLISH, "report": outcome.report}
    if not isinstance(outcome, _outcome_models._VerifiedReport):
        return None
    if not gh.is_own_repository(outcome.location.slug):
        log.error(
            "a developer verified a report on another repository (%s); "
            "recording no report for it", outcome.location.slug,
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


def _next_revision(state: _pinned_state.PinnedState) -> int:
    """The revision a report delivered now is: one past every recorded one.

    Both records are asked, and the outstanding transaction is the half that
    matters. A settlement replaces the current report, so a revision that did
    not move forward would put an older report on the pull request's own
    record of what it carries -- and a transaction still outstanding may
    already have posted its comment and lost the response, so a report minted
    at its revision would carry its receipt too and read that comment as its
    own, edited beyond recognition.

    A record nobody can read counts as nothing here, which is the same answer
    every reader in this domain gives it. Acting on such an issue at all is the
    reconciliation's question, and it parks one ahead of every handler.
    """
    recorded = (
        _settlement.read_current_report(state),
        _record_state.read_pending_report(state),
    )
    return 1 + max(
        (report.report_revision for report in recorded if report is not None),
        default=0,
    )
