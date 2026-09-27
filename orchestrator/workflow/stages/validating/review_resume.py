# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Finish a reviewer's verdict an earlier tick persisted and never disposed of.

A returned reviewer's verdict is persisted before its evidence is published
or the verdict acted on (`review_disposition`), so a tick that ended in
between -- a post GitHub never confirmed, a reuse whose proof could not be
read, a process that died -- leaves the verdict on the pinned comment. The next
tick finishes it here, ahead of the round-cap check and the spawn, and runs no
reviewer at all: the one that returned was charged for its run, its usage and
session were written with the verdict, and the round it ran as is the one the
verdict names. By the time this runs the dispatcher has reconciled the
evidence the verdict claims -- published and settled it, or held the tick
before any handler -- so what is left is the disposition itself.

A verdict is finished only while the subject it was about still stands. The
subject is resolved again exactly as the round resolved it -- the pull
request's head, the settled report re-read at its location, and the issue's
requirements read afresh -- and has to be the one the verdict records: a push,
a new report, an edited report, or an edit of the issue in the meantime is
work nobody reviewed, so the verdict is dropped and this very tick goes on to
hand a fresh reviewer the subject as it stands, or to refuse it. A reading
that could not be taken ends the tick with nothing written, for the next one
to ask again.

Nor is a verdict finished on a tick an awaiting-human park was cleared into:
that reply bought a fresh round of its own, and the round's writes drop the
verdict the park outlived. One this build cannot read is dropped the same way,
since a verdict nobody can read back is one nobody can act on.
"""
from __future__ import annotations

import logging

from github.Issue import Issue

from orchestrator.agents.models import AgentResult
from orchestrator.config import models as _config_models
from orchestrator.git.worktrees import creation as _worktree_creation, naming as _naming
from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import review_subjects as _review_subjects
from orchestrator.workflow.stages.validating import (
    models as _models,
    review_comment as _review_comment,
    review_coverage as _review_coverage,
    review_disposition as _disposition,
    review_report as _review_report,
    review_verdicts as _verdicts,
)

log = logging.getLogger("orchestrator.workflow")

_PR_NUMBER = "pr_number"

# The run a resumed verdict is finished under: no process was invoked for it,
# and nothing a disposition reads comes from its output -- the feedback a
# change request hands on is the persisted verdict's own.
_RESUMED_RUN = AgentResult(
    session_id=None,
    last_message="",
    exit_code=0,
    timed_out=False,
    stdout="",
    stderr="",
    invoked=False,
)


def resumes_a_returned_verdict(
    gh: GitHubClient,
    spec: _config_models.RepoSpec,
    issue: Issue,
    state: PinnedState,
    parked: _models._AwaitingValidation | None,
) -> bool:
    """Finish the verdict this issue has waiting; True where this tick is over.

    False where there is none to finish, and where one is dropped for the
    round about to run: the drop is staged, and that round's writes carry it.
    """
    if state.get(_verdicts.RETURNED_VERDICT) is None:
        return False
    returned = _verdicts.read_returned_verdict(state)
    if parked is not None or returned is None:
        log.info(
            "issue=#%d drops the reviewer verdict it had waiting: %s",
            issue.number,
            "it will not read" if returned is None else "a reply bought a fresh round",
        )
        _verdicts.drops_the_verdict(state)
        return False
    return _finishes(gh, spec, issue, state, returned)


def _finishes(
    gh: GitHubClient,
    spec: _config_models.RepoSpec,
    issue: Issue,
    state: PinnedState,
    returned: _verdicts.ReturnedVerdict,
) -> bool:
    """Act on `returned` over the subject standing now; False where it was dropped for a round."""
    readable, subject = _standing_subject(gh, issue, state)
    if not readable:
        return True
    if subject is None or subject.recorded() != returned.subject:
        log.info(
            "issue=#%d the subject its waiting reviewer verdict is about no "
            "longer stands; dropping it for a fresh review", issue.number,
        )
        _verdicts.drops_the_verdict(state)
        return False
    resolved_over = _review_comment._resolved_over(gh, issue, state)
    if resolved_over is None:
        return True
    run = _models._ReviewerRun(
        wt=_worktree_creation._ensure_worktree(
            spec, issue.number,
            branch=_naming._resolve_branch_name(state, spec, issue.number),
        ),
        round_n=returned.round_n,
        pr_number=state.get(_PR_NUMBER),
        agent_result=_RESUMED_RUN,
        delivery=None,
        subject=subject,
        resolved_over=resolved_over,
    )
    _disposition.acts_on_the_verdict(gh, spec, issue, state, _disposition.VerdictInHand(
        _models._ReviewerDecision(run, returned.verdict, returned.feedback),
        returned.evidence,
    ))
    return True


def _standing_subject(
    gh: GitHubClient, issue: Issue, state: PinnedState,
) -> tuple[bool, _review_subjects.ReviewSubject | None]:
    """Whether the subject could be read, and the one standing now, or None refused.

    Resolved as the round resolved it, over requirements read from the issue
    afresh, since the issue in hand was fetched before anything else this
    tick asked.
    """
    requirements = _review_coverage._fresh_requirements(gh, issue, state)
    if requirements is None:
        return False, None
    subject, refusal = _review_report._reads_the_subject(
        gh, issue, state, state.get(_PR_NUMBER), requirements,
    )
    return subject is not None or bool(refusal), subject
