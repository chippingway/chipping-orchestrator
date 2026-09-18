# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Committed work a recovery republishes, held where no report describes it.

Every recovery here republishes an EARLIER run's commits -- the restart shortcut
and each road answering a size-gate record -- with an `invoked=False` result
that records no report. So what describes the work is a debt still owed, or a
settled pair about THIS commit, branch and pull request, re-read where it
settled with the requirements before it vouches for anything; or the commit is
one a run that never COMPLETED left, owing none by design. Anything else is the
lost-write window the recording exists to close, held under
`report_undeliverable` before anything is measured, pushed or opened.
"""
from __future__ import annotations

from github.Issue import Issue

from orchestrator import config
from orchestrator.agents.models import AgentResult
from orchestrator.config import models as _config_models
from orchestrator.git.verification import probes as _verification_probes
from orchestrator.git.worktrees import naming as _naming
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
    models as _models,
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

    `invoked=False`: nothing produced it, so it records no report. The session
    travels so a pull request it opens still names the developer.
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
    state: PinnedState, work: _models._AgentWork, *, stranded: bool = False,
) -> None:
    """Remember the commit a run that never completed left, owing no report.

    For a process that ran and did not finish, and for the commit a timeout
    stranded that the quiet recovery hands on under a sentence of its own. The
    commit is the head the size gate goes on to measure; an unread head waives
    nothing.
    """
    outcome = _report_outcomes._report_outcome_of_run(work.agent_result)
    ran = work.agent_result.invoked and outcome in _report_delivery.INCOMPLETE_RUNS
    if stranded or ran:
        head = _verification_probes._head_sha(work.worktree)
        state.set(_state._INCOMPLETE_RUN_SHA, head or None)


def _holds_unreported_work(
    gh: GitHubClient,
    spec: _config_models.RepoSpec,
    issue: Issue,
    state: PinnedState,
    source_sha: str,
) -> bool:
    """Hold recovered work no standing report describes; True where it held.

    `source_sha` is the commit the recovery republishes: the head the restart
    shortcut found, or the candidate a gate record named.
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
        _naming._resolve_branch_name(state, spec, issue.number),
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

    The report where it settled, then the requirements afresh: an unread one
    holds silently, a definite refusal parks for a report-only reply.
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
