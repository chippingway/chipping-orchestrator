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

A change request handed to `workflow:fixing` is finished there instead
(`finishes_a_handed_request`), where the relabel that handed it landed and the
developer launch behind it did not: the feedback is already on the pull
request, so the developer is launched on it and nothing is posted twice. The
lifetime ledger and the branch say whether that launch happened
(`review_handoffs`): a verdict whose developer was launched is dropped wherever
it is found, since the run it owed happened, and one whose launch STARTED and
left nothing to account for parks on `fixing` rather than paying for a second
developer or a second reviewer. On `workflow:validating`, where only a relabel
from outside brings a handed verdict back, an unfinished launch is dropped like
a finished one and the round runs.

Nor is a verdict finished on a tick an awaiting-human park was cleared into:
that reply bought a fresh round of its own, and the round's writes drop the
verdict the park outlived. One this build cannot read is dropped the same way,
since a verdict nobody can read back is one nobody can act on.

No live reviewer round persists a verdict yet (`review_disposition`), so both
hooks answer only a record an issue already carries.
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
    requested_changes as _requested_changes,
    review_comment as _review_comment,
    review_coverage as _review_coverage,
    review_disposition as _disposition,
    review_handoffs as _handoffs,
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
    if parked is not None or returned is None or _handoffs.handoff_launch(
        spec, issue, state, returned,
    ) is not _handoffs.HandoffLaunch.OWED:
        log.info(
            "issue=#%d drops the reviewer verdict it had waiting: it will not "
            "read, a reply bought a fresh round, or its developer was launched",
            issue.number,
        )
        _verdicts.drops_the_verdict(state)
        return False
    held, run = _resumed_run(gh, spec, issue, state, returned)
    if run is None:
        return held
    _disposition.acts_on_the_verdict(gh, spec, issue, state, _disposition.VerdictInHand(
        _models._ReviewerDecision(run, returned.verdict, returned.feedback),
        returned.evidence,
    ))
    return True


def finishes_a_handed_request(
    gh: GitHubClient,
    spec: _config_models.RepoSpec,
    issue: Issue,
    state: PinnedState,
) -> bool:
    """On `workflow:fixing`, launch the developer a handed change request never reached.

    True where this tick is over: the developer was handed the feedback, a
    launch nobody can account for was parked (`review_handoffs`), or a reading
    could not be taken. False where there is nothing to hand -- no verdict, one
    never handed, or one whose developer was launched, which is dropped -- and
    where its subject moved, dropping it for the round that reviews the
    subject as it stands; the stage's own road runs then.
    """
    returned = _verdicts.read_returned_verdict(state)
    if returned is None or returned.handed is None:
        return False
    launch = _handoffs.handoff_launch(spec, issue, state, returned)
    if launch is _handoffs.HandoffLaunch.UNFINISHED:
        _handoffs.parks_an_unfinished_launch(gh, issue, state, returned)
        return True
    if launch is _handoffs.HandoffLaunch.LAUNCHED:
        _verdicts.drops_the_verdict(state)
        gh.write_pinned_state(issue, state)
        return False
    held, run = _resumed_run(gh, spec, issue, state, returned)
    if run is None:
        if not held:
            gh.write_pinned_state(issue, state)
        return held
    log.info(
        "issue=#%d hands the change request its relabel never delivered to "
        "the developer, without a second reviewer", issue.number,
    )
    context = _models._RequestedChanges(gh, spec, issue, state, _models._ReviewerDecision(
        run, returned.verdict, returned.feedback,
    ))
    _verdicts.drops_the_verdict(state)
    _requested_changes._finish_requested_fix(
        context, _requested_changes._run_requested_fix(context),
    )
    return True


def _resumed_run(
    gh: GitHubClient,
    spec: _config_models.RepoSpec,
    issue: Issue,
    state: PinnedState,
    returned: _verdicts.ReturnedVerdict,
) -> tuple[bool, _models._ReviewerRun | None]:
    """The run `returned` is finished as over the subject standing now, or why none.

    `(False, run)` where the subject stands; `(True, None)` where a reading
    could not be taken, which holds the tick; `(False, None)` where the
    subject moved, with the verdict's drop staged.
    """
    readable, subject = _standing_subject(gh, issue, state)
    if not readable:
        return True, None
    if subject is None or subject.recorded() != returned.subject:
        log.info(
            "issue=#%d the subject its waiting reviewer verdict is about no "
            "longer stands; dropping it for a fresh review", issue.number,
        )
        _verdicts.drops_the_verdict(state)
        return False, None
    resolved_over = _review_comment._resolved_over(gh, issue, state)
    if resolved_over is None:
        return True, None
    return False, _models._ReviewerRun(
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
