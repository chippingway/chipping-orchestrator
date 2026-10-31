# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What the locked session's resume over a mid-implementation edit came back with, and what is made of it.

The disposition is wider than a normal run's because an edit has a fourth
possible answer. A fresh commit publishes, a commit-less timeout parks, a
question parks -- and a dev that replies "the existing work already satisfies
this" is ACKed rather than parked, which is what keeps a no-op edit from sitting
awaiting a human who has nothing left to say. That ACK also clears the
silent-park streak: the session answered, so it is not the poisoned one the
streak is counting.

A commit-less reply has one more reading, and it is the same one the ordinary
disposition makes: an issue still owing a report it could not deliver was never
waiting for code, so a run that comes back with a report publishes the commits
the branch already carries rather than parking as a question. A human's reply
to a park reaches the park's own resume rather than this road -- the drift
check measures a parked issue by what the park had already read -- so this
road meets that debt only where an edit came with the reply.

What the edit is recorded as answered by is the run: the frozen reading its
resume was handed (`drift`), settled here for every outcome that reached an
agent and for none that did not. A run that finished on its report is
captured as it returns (`drift_road`), and its report reaches the delivery as
that capture's transfer through the stage's own publication
(`candidate_recovery`); an `ACK:` or a question hands that report to nobody,
so either withdraws the capture first (`captured_report.withdraws_the_capture`),
and the reply answering the park is captured afresh rather than refused behind
it. A withdrawal that does not settle posts and parks nothing, its state
withheld. The dispatcher's recovery of a held capture answers it through this
same disposition (`captured_drift`), handed the reading reduced to the
revision the run was handed.
"""
from __future__ import annotations

from github.Issue import Issue

from orchestrator.config import models as _config_models
from orchestrator.git.verification import status as _worktree_status
from orchestrator.github import client as _client, pinned_state as _pinned_state
from orchestrator.workflow.engine import comments as _comments, guards as _guards
from orchestrator.workflow.stages.implementing import (
    candidate_recovery as _candidate_recovery,
    disposition as _disposition,
    models as _models,
    parks as _parks,
    session_read as _session_read,
)
from orchestrator.workflow.stages.implementing.captured_report import withdraws_the_capture
from orchestrator.workflow.stages.implementing.drift_models import _ImplementingDriftRun
from orchestrator.workflow.stages.implementing.state import _SILENT_PARK_COUNT


def _dispose_implementing_drift(
    gh: _client.GitHubClient,
    spec: _config_models.RepoSpec,
    issue: Issue,
    state: _pinned_state.PinnedState,
    drift: _ImplementingDriftRun,
) -> None:
    if (
        _guards._ignore_if_never_invoked(issue, drift.agent_result)
        or _guards._ignore_if_interrupted(issue, drift.agent_result)
        or drift.paused
    ):
        return
    # Every run that consumes nothing has returned by now, so what is left
    # read the prompt -- a timeout and a question included, since what the
    # park that follows says is wrong is the answer rather than the input.
    drift.delivery.settle(state)
    # A quota stop's commit publishes only over a tree provably clean, as on
    # the ordinary disposition: any other the publication seam would park
    # under a reason that refuses the bare continue the quota needs.
    held = (
        _session_read._is_session_limit(drift.agent_result)
        and not _worktree_status._worktree_status(drift.worktree).is_clean
    )
    if not held and drift.publishes(spec, state):
        _candidate_recovery._publish_committed_work(
            gh, spec, issue, state,
            _models._AgentWork(drift.agent_result, drift.worktree),
        )
    elif drift.agent_result.timed_out:
        _disposition._park_agent_timeout(gh, issue, state, _guards._ParkedRun(
            drift.agent_result, _guards._ROUTE_DEV_DRIFT_RESUME, before_sha=drift.before_sha,
        ))
    elif withdraws_the_capture(gh, issue, state, drift.agent_result):
        _answers_in_words(gh, issue, state, drift)
    gh.write_pinned_state(issue, state)


def _answers_in_words(
    gh: _client.GitHubClient, issue: Issue, state: _pinned_state.PinnedState, drift: _ImplementingDriftRun,
) -> None:
    """Post the session's `ACK:` that the existing work satisfies the edit, or park the question it asked instead.

    The ACK clears the silent-park streak: the session answered, so it is not
    the poisoned one the streak is counting.
    """
    ack_reason = drift.ack_reason()
    if not ack_reason:
        _parks._on_question(gh, issue, state, _guards._ParkedRun(
            drift.agent_result, _guards._ROUTE_DEV_DRIFT_RESUME, before_sha=drift.before_sha,
        ))
        return
    quoted = _session_read._as_blockquote(ack_reason)
    _comments._post_issue_comment(
        gh, issue, state,
        ":speech_balloon: dev session reports the existing "
        f"work satisfies the edit:\n\n{quoted}",
    )
    state.set(_SILENT_PARK_COUNT, 0)
