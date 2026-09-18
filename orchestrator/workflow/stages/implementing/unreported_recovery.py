# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Committed work a recovery republishes, held where no report describes it.

Every recovery on this stage republishes commits an EARLIER tick's developer
made: the restart shortcut over a worktree that already carries them, and each
road that answers a record the size gate left -- an approved commit, a frozen
candidate, a measurement park retried, a checkout put back, an authorized
rollback. No developer runs on any of them, so the result they hand the
publication seam is the orchestrator's own sentence, `invoked=False`, and
records no report. What describes the work is on the pinned comment or nowhere.

The report is recorded before the size gate and before the push, so on the
comment it is one of two things: a debt still owed -- a delivery waiting for a
pull request, or a transaction waiting for its comment -- or a settled pair
about THIS commit on the pull request the receipt says it was pushed onto,
which is what a publication whose relabel did not land leaves behind. A
settlement is never cleared, so any other pair is about other work.

And a settled pair is a record of one moment. The report it names can have been
edited or deleted since, and the issue can have moved under the requirements it
answered -- so before a settlement lets the work past, the report is re-read
where it settled and the requirements are read again. A reading nobody could
take holds the tick without a word, since the next one is as likely to succeed.
A definite answer that the report is not what settled is a publication a human
has to repair, and it parks with the work where it is.

The one commit owed no report at all is the one a run left when it did not
COMPLETE: a timeout, a provider refusal, a nonzero exit. Such a run records
nothing by design and its commit publishes as it always has, so the publication
seam remembers which commit it was -- and a recovery republishing exactly that
commit later, a measurement retried or an approval paid, is answered by that
record rather than held for a report nothing was ever going to write.

Nothing on the comment otherwise is the window the recording exists to close --
a pinned write that failed, a restart inside it. The session that could say
what the commits do has ended, and published they would reach review
undescribed. So the work is held under
`report_undeliverable` before anything is measured, pushed or opened, and a
reply resumes a developer that can write the report.
"""
from __future__ import annotations

from pathlib import Path

from github.Issue import Issue

from orchestrator import config
from orchestrator.agents.models import AgentResult
from orchestrator.config import models as _config_models
from orchestrator.git.verification import probes as _verification_probes
from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.github.pull_request_reports import ReportPresence
from orchestrator.workflow.engine import (
    report_delivery as _report_delivery,
    report_evidence as _report_evidence,
    report_locations as _report_locations,
    report_outcomes as _report_outcomes,
    report_publishing as _report_publishing,
    report_records as _records,
)
from orchestrator.workflow.stages.implementing import (
    late_publication_state as _late_publication_state,
    session_read as _session_read,
    state as _state,
)

_MOVED_SETTLEMENT_PARK = (
    "{mentions} this issue's branch carries committed work whose developer "
    "report already settled on PR #{pr}, and that report no longer stands as "
    "it settled: {detail}. Nothing was published: the commit is still in the "
    "worktree and the pull request stands as it is, because handing this on "
    "would send a reviewer a report that is not the one recorded. Reply and "
    "the orchestrator resumes the session; the report it writes then is the "
    "one that gets published, and it needs no new commit to deliver it."
)

# What the notice says about each way a settled report can have moved.
_MOVED_REPORT = "it is gone from where it settled, or reads differently there"

_MOVED_REQUIREMENTS = (
    "the issue's requirements have moved since the run that wrote it"
)


def _recovery_result(state: PinnedState, message: str) -> AgentResult:
    """The result a recovery hands the publication seam in place of a run's.

    Nothing produced it, which is what `invoked=False` says and why it records
    no report: the sentence is the orchestrator's own. The session travels so
    the pull request it may open still names the developer whose work it is.
    """
    return AgentResult(
        session_id=_session_read._read_dev_session(state)[-1],
        last_message=message,
        exit_code=0,
        timed_out=False,
        stdout="",
        stderr="",
        invoked=False,
    )


def _waives_an_incomplete_run(
    state: PinnedState, agent_result: AgentResult, worktree: Path,
) -> None:
    """Remember the commit a run that never completed left, owing no report.

    Asked of every result the publication seam is handed once its report
    reading is done, and answering only for a process that really ran and did
    not finish: a recovery's own sentence was never a run, and a run that
    finished either recorded a report or was held for one. The commit is the
    checkout's head, which is what the size gate goes on to measure; a head
    that cannot be read waives nothing, so a later recovery is held instead.
    """
    if not agent_result.invoked:
        return
    outcome = _report_outcomes._report_outcome_of_run(agent_result)
    if outcome not in _report_delivery.INCOMPLETE_RUNS:
        return
    head = _verification_probes._head_sha(worktree)
    state.set(_state._INCOMPLETE_RUN_SHA, head or None)


def _holds_unreported_work(
    gh: GitHubClient,
    spec: _config_models.RepoSpec,
    issue: Issue,
    state: PinnedState,
    source_sha: str,
) -> bool:
    """Hold recovered work no standing report describes; True where it held.

    Held is parked, for a report nothing recorded or a settled one that has
    moved -- or a tick that simply stops, where the settled report could not
    be re-read. `source_sha` is the commit the recovery is about to republish:
    the head the restart shortcut found, or the candidate a gate record named.
    A caller that could name none is asking about nothing, and no settlement
    answers it.
    """
    if _report_delivery.owes_a_report(state):
        return False
    # Compared, never parsed: the commit a recovery proved is the one thing a
    # value here can match, so a hand edit or a truncation waives nothing.
    if source_sha and state.get(_state._INCOMPLETE_RUN_SHA) == source_sha:
        return False
    settled = _report_locations.settled_publication(
        state, spec.slug,
        _late_publication_state._published_pull_request(state),
        source_sha,
    )
    if settled is not None:
        return _holds_a_moved_settlement(gh, issue, state, settled)
    _report_delivery.parks_an_undeliverable_report(
        gh, issue, state, _report_delivery.UNRECOVERED_PARK.format(
            mentions=config.HITL_MENTIONS,
        ),
    )
    return True


def _holds_a_moved_settlement(
    gh: GitHubClient,
    issue: Issue,
    state: PinnedState,
    settled: _records.CurrentReport,
) -> bool:
    """Hold a settled report that no longer stands; True where it held.

    The report first, where it settled, then the requirements over an issue
    read afresh. Either reading nobody could take holds silently; either
    definite refusal parks, once, under the reason every undeliverable report
    takes -- which is also what makes the reply that answers it publish the
    commits already on the branch.
    """
    presence = _report_publishing.still_carries(gh, state, settled)
    if presence is ReportPresence.UNCONFIRMED:
        return True
    edited = None
    if presence is ReportPresence.PRESENT:
        edited = _report_evidence.fresh_requirements_verdict(
            gh, issue, state, settled,
        )
        if edited is None:
            return False
        if edited.holds:
            return True
    _report_delivery.parks_an_undeliverable_report(
        gh, issue, state, _MOVED_SETTLEMENT_PARK.format(
            mentions=config.HITL_MENTIONS,
            pr=settled.subject.pr_number,
            detail=_MOVED_REPORT if edited is None else _MOVED_REQUIREMENTS,
        ),
    )
    return True
