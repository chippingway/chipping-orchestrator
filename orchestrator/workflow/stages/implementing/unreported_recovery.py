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

Neither on the comment is the window the recording exists to close -- a pinned
write that failed, a restart inside it -- or a run that never completed. Either
way the session that could say what the commits do has ended, and published
they would reach review undescribed. So the work is held under
`report_undeliverable` before anything is measured, pushed or opened, and a
reply resumes a developer that can write the report.
"""
from __future__ import annotations

from github.Issue import Issue

from orchestrator import config
from orchestrator.agents.models import AgentResult
from orchestrator.config import models as _config_models
from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    report_delivery as _report_delivery,
    report_locations as _report_locations,
)
from orchestrator.workflow.stages.implementing import (
    late_publication_state as _late_publication_state,
    session_read as _session_read,
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


def _holds_unreported_work(
    gh: GitHubClient,
    spec: _config_models.RepoSpec,
    issue: Issue,
    state: PinnedState,
    source_sha: str,
) -> bool:
    """Park recovered work no recorded report describes; True where it parked.

    `source_sha` is the commit the recovery is about to republish: the head
    the restart shortcut found, or the candidate a gate record named. A caller
    that could name none is asking about nothing, and no settlement answers it.
    """
    if _report_delivery.owes_a_report(state):
        return False
    if _report_locations.settled_the_publication(
        state, spec.slug,
        _late_publication_state._published_pull_request(state),
        source_sha,
    ):
        return False
    _report_delivery.parks_an_undeliverable_report(
        gh, issue, state, _report_delivery.UNRECOVERED_PARK.format(
            mentions=config.HITL_MENTIONS,
        ),
    )
    return True
