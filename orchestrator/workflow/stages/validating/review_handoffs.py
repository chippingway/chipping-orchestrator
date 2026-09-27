# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A persisted change request's handoff, whether its developer was launched, and the park where nobody can say.

The handoff (`hands_the_request_over`) is taken only while the subject the
verdict is about still stands, resolved again with the pinned comment read
first, since another road can settle a later report between the verdict's
write and this: feedback posted and handed on over it is about words the pull
request no longer carries, and the handoff's write would put the older report
records back over the newer. The feedback is posted next, and the one durable
copy of it is the id it lands as, so a post that failed or left no id relabels
and launches nothing and the verdict still waiting posts again on the next
tick. The records are read once more behind that post, the one request between
the recheck and the write, and only then is the verdict written as handed at
the lifetime agent-run count (`review_verdicts`), with the anchor, and the
issue relabelled to `workflow:fixing` -- so whichever request fails leaves a
verdict the next tick hands over without posting twice (`review_resume`). The
room that write needs was reserved when the verdict was recorded.

Only the writes behind the developer's run retire the verdict, so a handed one
still standing is a handoff whose developer's run wrote nothing, and what that
means is read off the ledger the launch charges before it spawns
(`run_circuit`), which records two phases durably and the end of neither.

Nothing charged past the handed count, or a charge still RESERVED, is a launch
that never spawned: the developer is OWED, and the same logical launch reuses
that reservation rather than paying twice. A charge whose phase is gone was
settled by a write behind a run that returned: the developer was LAUNCHED. A
charge STARTED is the one reading the ledger cannot settle, because the phase
goes down before the spawn: the process may have stopped short of it, or a
developer may have run and had its result discarded unwritten -- a live pause
does exactly that. The branch tells the two apart where the run committed: a
commit the pull request has not got is work a developer did, which the stage's
own bounce publishes, so that too is LAUNCHED. Anything else is UNFINISHED.

An unfinished launch is neither retried nor walked past. Handed to the
developer again it may pay for a second run over feedback one already
answered; walked past, the no-feedback bounce returns an unchanged head to
`workflow:validating` and a second reviewer re-reviews a round already
reviewed. So it parks under `agent_execution_failed` -- the verdict dropped,
the reviewer's feedback kept where it was posted -- and `/orchestrator
continue` on that park replays that feedback to a fresh developer session
through the stage's own replay anchor (`pending_fix_reviewer_comment_id`).
"""
from __future__ import annotations

import logging
from enum import StrEnum

from github.Issue import Issue

from orchestrator import config
from orchestrator.git.worktrees import paths as _worktree_paths
from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    guards as _guards,
    run_ledger_models as _run_ledger_models,
    run_ledger_values as _run_ledger_values,
)
from orchestrator.workflow.stages.implementing import parks as _implementing_parks
from orchestrator.workflow.stages.validating import (
    models as _models,
    requested_changes as _requested_changes,
    review_comment as _review_comment,
    review_coverage as _review_coverage,
    review_verdicts as _verdicts,
    state as _state,
    stranded as _stranded,
)
from orchestrator.workflow.state import WorkflowLabel

log = logging.getLogger("orchestrator.workflow")

_UNFINISHED_NOTICE = (
    "the developer launch this reviewer's change request was handed to "
    "started and left no result, so nothing says whether it ever ran, and the "
    "reviewer's feedback was not handed on a second time. Reply `/orchestrator "
    "continue` to hand that feedback to a fresh developer session."
)


def hands_the_request_over(
    gh: GitHubClient,
    spec: config.RepoSpec,
    issue: Issue,
    state: PinnedState,
    decision: _models._ReviewerDecision,
) -> None:
    """Hand a persisted change request to its developer, over the subject standing now.

    A subject that moved drops the verdict in a write composed over what the
    comment carries now, and a comment that will not read writes nothing, for
    the next tick to resolve again.
    """
    stands = _review_coverage._verdict_still_stands(gh, issue, state, decision.run.subject)
    if not stands:
        _drops_what_moved(gh, issue, state, stands)
        return
    context = _models._RequestedChanges(gh, spec, issue, state, decision)
    posted_over = dict(state.data)
    if not _requested_changes._post_reviewer_feedback(context):
        log.warning(
            "issue=#%s holding its reviewer's change request until the "
            "feedback is posted on the PR", issue.number,
        )
        return
    stood = _review_comment._records_stand(gh, issue, state, posted_over)
    if not stood:
        _drops_what_moved(gh, issue, state, stood)
        return
    _verdicts.hands_off(state, _run_ledger_values._runs_used(state))
    gh.write_pinned_state(issue, state)
    gh.set_workflow_label(issue, WorkflowLabel.FIXING)
    # Staged for the writes behind the run, never for the launch's charge,
    # which writes only its own fields.
    _verdicts.drops_the_verdict(state)
    _requested_changes._finish_requested_fix(context, _requested_changes._run_requested_fix(context))


def _drops_what_moved(gh: GitHubClient, issue: Issue, state: PinnedState, stood: bool | None) -> None:
    """Drop a verdict whose subject moved, over what the comment carries now; nothing where it will not read.

    A False reading has carried every record the comment moved onto `state`,
    so the write keeps the newer report rather than the one the verdict read.
    """
    if stood is None:
        return
    log.info(
        "issue=#%d the subject its reviewer's change request is about moved "
        "before it was handed over; dropping the verdict", issue.number,
    )
    _verdicts.drops_the_verdict(state)
    gh.write_pinned_state(issue, state)


class HandoffLaunch(StrEnum):
    """What the ledger and the branch say about a handed change request's developer."""

    OWED = "owed"
    LAUNCHED = "launched"
    UNFINISHED = "unfinished"


def handoff_launch(
    spec: config.RepoSpec,
    issue: Issue,
    state: PinnedState,
    returned: _verdicts.ReturnedVerdict,
) -> HandoffLaunch:
    """Whether `returned`'s developer is owed, was launched, or left nothing to say either way.

    A verdict never handed over is owed by definition. The branch is read only
    for a STARTED charge, the one reading the ledger cannot settle.
    """
    handed = returned.handed
    if handed is None or _run_ledger_values._runs_used(state) <= handed:
        return HandoffLaunch.OWED
    phase = _run_ledger_values._reservation(state)
    if phase is _run_ledger_models.RunPhase.RESERVED:
        return HandoffLaunch.OWED
    if phase is not _run_ledger_models.RunPhase.STARTED:
        return HandoffLaunch.LAUNCHED
    worktree = _worktree_paths._worktree_path(spec, issue.number)
    if _stranded._stranded_evidence(spec, worktree, state, issue).stranded:
        return HandoffLaunch.LAUNCHED
    return HandoffLaunch.UNFINISHED


def parks_an_unfinished_launch(
    gh: GitHubClient,
    issue: Issue,
    state: PinnedState,
    returned: _verdicts.ReturnedVerdict,
) -> None:
    """Park a handoff whose developer launch left no result, in one write."""
    _verdicts.drops_the_verdict(state)
    _guards._park_awaiting_human(
        gh,
        issue,
        state,
        f"{config.HITL_MENTIONS} {_UNFINISHED_NOTICE}",
        reason=_implementing_parks._PARK_EXECUTION_FAILED,
        agent_role="developer",
        review_round=returned.round_n,
        retry_count=_guards._safe_int(state.get("retry_count")),
        pr_number=_guards._safe_int(state.get("pr_number")),
        bounded=True,
    )
    # Re-set behind the guard, which clears whatever reason it found: the
    # continue command replays the reviewer's feedback only under this one.
    state.set(_state._PARK_REASON, _implementing_parks._PARK_EXECUTION_FAILED)
    gh.write_pinned_state(issue, state)
