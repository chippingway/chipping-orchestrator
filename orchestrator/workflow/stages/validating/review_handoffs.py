# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A persisted change request's handoff to the developer it owes.

The handoff (`hands_the_request_over`) is taken only while the subject the
verdict is about still stands, resolved again with the pinned comment read
behind it, since another road can settle a later report between the verdict's
write and this: feedback posted and handed on over it is about words the pull
request no longer carries, and the handoff's write would put the older report
records back over the newer. The feedback is posted next, and the one durable
copy of it is the id it lands as, so a post that failed or left no id relabels
and launches nothing, and the verdict is left waiting, never handed, for
whatever finishes it to post again. A post GitHub accepted and whose response
was lost reads the same way, since a feedback post carries no receipt to find
it by, so that retry leaves the feedback on the pull request twice. The whole
subject is held to what stands once more behind that post, the one request
between the recheck and the write -- a push landing during it is as much a
subject nobody reviewed -- and only then is the verdict written as handed at
the lifetime agent-run count (`review_verdicts.hands_off`), with the anchor,
and the issue relabelled to `workflow:fixing`, so whichever request fails
leaves a verdict whose feedback is already posted and anchored. The room that
write and the launch's charge need was reserved when the verdict was recorded.

The relabel is a request too, so the subject is held once more right before
the developer is launched (`launches_the_developer`, the one entry every road
that launches a handed request's developer takes), and a moved one drops the
verdict and its anchor. Only the writes behind the developer's run retire the
verdict, since its drop is staged ahead of the launch, whose charge writes only
its own fields.

A verdict already handed is finished by a later tick from that write on: its
feedback is posted and anchored, so it is never posted again, and the relabel
and the launch are what a tick that died on them left owed -- unless the run
ledger was charged past the count it was handed at, which is the developer
already launched and only that verdict to retire (`_hands_it_off`).
"""
from __future__ import annotations

import logging

from github.Issue import Issue

from orchestrator import config
from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import run_ledger_values as _run_ledger_values
from orchestrator.workflow.stages.validating import (
    models as _models,
    requested_changes as _requested_changes,
    review_coverage as _review_coverage,
    review_verdicts as _verdicts,
)
from orchestrator.workflow.state import WorkflowLabel

log = logging.getLogger("orchestrator.workflow")


def hands_the_request_over(
    gh: GitHubClient,
    spec: config.RepoSpec,
    issue: Issue,
    state: PinnedState,
    decision: _models._ReviewerDecision,
) -> None:
    """Hand a persisted change request to its developer, over the subject standing now.

    A subject proved to have moved drops the verdict in a write composed over
    what the comment carries now; a comment or a subject that will not read
    writes nothing, holding the verdict for the next tick to resolve again.
    The verdict this road holds is the one the state in hand carries as it
    starts, so a verdict another road put in its place meanwhile is never the
    one it drops. One already handed resumes where that handoff stopped
    (`_hands_it_off`) rather than posting its feedback again.
    """
    owned = _verdicts.read_returned_verdict(state)
    stands = _review_coverage._verdict_still_stands(gh, issue, state, decision.run.subject)
    if not stands:
        drops_what_moved(gh, issue, state, stands, (owned, None))
        return
    context = _models._RequestedChanges(gh, spec, issue, state, decision)
    if not _hands_it_off(context, owned):
        return
    gh.set_workflow_label(issue, WorkflowLabel.FIXING)
    launches_the_developer(context)


def launches_the_developer(context: _models._RequestedChanges) -> None:
    """Launch the developer a handed change request owes, over the subject standing as it is launched.

    Every request before this one -- a relabel above all -- is long enough for
    another road to push or to settle a later report, and the run's own writes
    are composed over the state in hand: launched over the older records, the
    developer would answer words the pull request no longer carries and its
    writes would put those records back over the newer. So the subject is held
    to what stands once more, the comment read again behind it, and a moved one
    drops the request -- its anchor with it -- in a write that keeps the newer
    records, launching nothing. Otherwise the drop is staged ahead of the
    launch, whose charge writes only its own fields, so only the writes behind
    the run retire the verdict.
    """
    gh, issue, state = context.gh, context.issue, context.state
    owned = _verdicts.read_returned_verdict(state)
    stands = _review_coverage._verdict_still_stands(gh, issue, state, context.decision.run.subject)
    if not stands:
        drops_what_moved(gh, issue, state, stands, (owned, None))
        return
    _verdicts.drops_the_verdict(state, only=owned)
    _requested_changes._finish_requested_fix(context, _requested_changes._run_requested_fix(context))


def drops_what_moved(
    gh: GitHubClient, issue: Issue, state: PinnedState, stood: bool | None, owned: tuple,
) -> None:
    """Drop a request whose subject moved, over what the comment carries now; nothing where it will not read.

    A False reading has carried every record the comment moved onto `state`,
    so the write keeps the newer report rather than the one the verdict read
    -- and a verdict another road put in place of this road's, which is that
    road's to finish. `owned` is the verdict this road holds and the anchor of
    the feedback it posted for it, if any: only those are dropped. The
    feedback's anchor goes with this road's verdict, since it names words
    about a subject nobody is handing on, and a later park's retry replaying
    them would hand a developer a review of work the pull request no longer
    carries; an anchor another road wrote beside its own verdict stays.
    """
    if stood is None:
        return
    verdict, posted = owned
    log.info(
        "issue=#%d the subject its reviewer's change request is about moved "
        "before it was handed over; dropping the verdict", issue.number,
    )
    dropped = _verdicts.drops_the_verdict(state, only=verdict)
    anchor = state.get(_verdicts._FEEDBACK_ANCHOR)
    if anchor is not None and (dropped or anchor == posted):
        state.set(_verdicts._FEEDBACK_ANCHOR, None)
    gh.write_pinned_state(issue, state)


def _hands_it_off(context: _models._RequestedChanges, owned: _verdicts.ReturnedVerdict) -> bool:
    """Hand the verdict off behind its posted feedback, or find where that handoff got to; whether the launch is owed.

    A verdict already handed has its feedback posted and anchored, so it is
    not posted again: the relabel or the launch behind that write is what a
    tick that died on it left owed. The lifetime agent-run count it was
    handed at says which -- a charge past it is the developer already
    launched, whose run is the fixing stage's to answer, so that verdict is
    retired rather than handed to a second developer.
    """
    gh, issue, state = context.gh, context.issue, context.state
    if owned.handed is None:
        if not _posts_the_feedback(context, owned):
            return False
        _verdicts.hands_off(state, _run_ledger_values._runs_used(state))
        gh.write_pinned_state(issue, state)
        return True
    if _run_ledger_values._runs_used(state) <= owned.handed:
        log.info(
            "issue=#%d resumes the handoff of its reviewer's change request, "
            "already posted and anchored", issue.number,
        )
        return True
    log.info(
        "issue=#%d the developer its reviewer's change request was handed to "
        "was already launched; retiring the verdict", issue.number,
    )
    _verdicts.drops_the_verdict(state, only=owned)
    gh.write_pinned_state(issue, state)
    return False


def _posts_the_feedback(context: _models._RequestedChanges, owned) -> bool:
    """Post the reviewer's feedback and hold the subject to what stands behind it; whether the handoff goes on.

    The post is a request of its own, long enough for a push or a later
    report to land; the records are read against the comment the post was
    made over, so the anchor it staged is not mistaken for another road's.
    """
    posted_over = dict(context.state.data)
    if not _requested_changes._post_reviewer_feedback(context):
        log.warning(
            "issue=#%s holding its reviewer's change request until the "
            "feedback is posted on the PR", context.issue.number,
        )
        return False
    posted = context.state.get(_verdicts._FEEDBACK_ANCHOR)
    stood = _review_coverage._verdict_still_stands(
        context.gh, context.issue, context.state, context.decision.run.subject, posted_over,
    )
    if not stood:
        drops_what_moved(context.gh, context.issue, context.state, stood, (owned, posted))
    return bool(stood)
