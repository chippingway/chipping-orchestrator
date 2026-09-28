# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A persisted verdict handed on: a change request to the developer it owes, an approval to the approval arc.

Either is reached only right behind the disposition proving the verdict still
carried, its subject standing, and its evidence settled (`review_disposition`),
through `hands_the_verdict_on`. An approval goes to the approval arc only where
the evidence it relies on proves valid (`unverified_approvals`), and its
refusal otherwise is handed back for the disposition to park. A change
request's handoff (`hands_the_request_over`) starts with the feedback post.
The one durable copy of that feedback is the id it lands as, so a post that
failed, left no id, or found no pull request to go on relabels and launches
nothing, and the verdict is left
waiting, never handed, for whatever finishes it to post again. A post GitHub
accepted and whose response was lost reads the same way, since a feedback post
carries no receipt to find it by, so that retry leaves the feedback on the
pull request twice. The whole subject is held to what stands once more behind
that post, the comment read behind it -- a push or a later report landing
during it is a subject nobody reviewed, and the handoff's write would put the
older report records back over the newer -- and only then is the verdict
written as handed at the lifetime agent-run count
(`review_verdicts.hands_off`), with the anchor, and the issue relabelled to
`workflow:fixing`, so whichever request fails leaves a verdict whose feedback
is already posted and anchored. The room that write and the launch's charge
need was reserved when the verdict was recorded.

The relabel is a request too, so the subject is held once more right before
the developer is launched (`launches_the_developer`, the one entry every road
that launches a handed request's developer takes), and a moved one drops the
verdict and its anchor. So is the run ledger: a charge past the count the
request was handed at, landed behind the relabel, is the developer it owes
already launched by another road, and the verdict is retired rather than
handed to a second developer. Only the writes behind the developer's run
retire the verdict otherwise, since its drop is staged ahead of the launch,
whose charge writes only its own fields.

A verdict already handed is finished by a later tick from that write on: its
feedback is posted and anchored, so it is never posted again, and the relabel
and the launch are what a tick that died on them left owed -- unless the run
ledger was charged past the count it was handed at, which is the developer
already launched and only that verdict to retire (`_hands_it_off`). Either
launch is made only behind the feedback anchor the handoff was written beside:
the fixing stage clears it with the round's other bookmarks, and without it no
failed run can replay the feedback, so a handoff that lost it is held, with
nothing relabelled, launched, or written (`_launch_stands`).
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
    unverified_approvals as _unverified,
)
from orchestrator.workflow.state import WorkflowLabel

log = logging.getLogger("orchestrator.workflow")


def hands_the_verdict_on(
    gate, decision: _models._ReviewerDecision, claim: _verdicts.EvidenceClaim | None,
) -> str | None:
    """Hand a persisted verdict on over `gate`, built on its run's checkout; an approval's refusal, if any.

    A change request goes to its developer and answers "". An approval
    relying on `claim` answers as `unverified_approvals.approves` does: ""
    where the approval arc took it, None where the proof of its evidence could
    not be read, and otherwise why it may not be acted on.
    """
    if decision.verdict == _verdicts.CHANGES_REQUESTED:
        hands_the_request_over(gate.gh, gate.spec, gate.issue, gate.state, decision)
        return ""
    return _unverified.approves(gate, decision.run, claim)


def hands_the_request_over(
    gh: GitHubClient,
    spec: config.RepoSpec,
    issue: Issue,
    state: PinnedState,
    decision: _models._ReviewerDecision,
) -> None:
    """Hand a persisted change request to its developer, for a caller that has just held it to what stands.

    The verdict this road holds is the one the state in hand carries as it
    starts, so a verdict another road put in its place meanwhile is never the
    one it drops. One already handed resumes where that handoff stopped
    (`_hands_it_off`) rather than posting its feedback again.
    """
    context = _models._RequestedChanges(gh, spec, issue, state, decision)
    if not _hands_it_off(context, _verdicts.read_returned_verdict(state)):
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
    records, launching nothing. That reading carries the run ledger too, and a
    charge past the count the request was handed at is its developer already
    launched by another road meanwhile, and an anchor it no longer carries is
    a handoff held (`_launch_stands`). Otherwise the drop is staged ahead of
    the launch, whose charge writes only its own fields, so only the writes
    behind the run retire the verdict.
    """
    gh, issue, state = context.gh, context.issue, context.state
    owned = _verdicts.read_returned_verdict(state)
    stands = _review_coverage._verdict_still_stands(
        gh, issue, state, context.decision.run.subject.recorded(), dict(state.data),
    )
    if not stands:
        drops_what_moved(gh, issue, state, stands, (owned, None))
        return
    if not _launch_stands(gh, issue, state, owned):
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
    tick that died on it left owed, where it is still owed at all
    (`_launch_stands`).
    """
    gh, issue, state = context.gh, context.issue, context.state
    if owned.handed is None:
        if not _posts_the_feedback(context, owned):
            return False
        _verdicts.hands_off(state, _run_ledger_values._runs_used(state))
        gh.write_pinned_state(issue, state)
        return True
    if not _launch_stands(gh, issue, state, owned):
        return False
    log.info(
        "issue=#%d resumes the handoff of its reviewer's change request, "
        "already posted and anchored", issue.number,
    )
    return True


def _launch_stands(
    gh: GitHubClient, issue: Issue, state: PinnedState, owned: _verdicts.ReturnedVerdict | None,
) -> bool:
    """Whether the launch a handed request owes is still this road's to make, retiring or holding it where not.

    The run ledger charged past the count the request was handed at is that
    developer's launch, whoever made it -- a tick that died behind it, or
    another road behind this one's relabel -- and its run is the fixing
    stage's to answer, so the verdict is retired, over the comment as `state`
    last carried it, rather than handed to a second developer. And the launch
    is made only behind the feedback anchor the handoff was written beside:
    it is the one durable copy of the feedback a failed run's `/orchestrator
    continue` replays, and the fixing stage clears it with the round's other
    bookmarks, so a handoff that lost it is held -- nothing relabelled,
    launched, or written, the verdict left waiting as it was -- rather than
    handing a developer a review no failed run could replay.
    """
    handed = None if owned is None else owned.handed
    if handed is not None and _run_ledger_values._runs_used(state) > handed:
        log.info(
            "issue=#%d the developer its reviewer's change request was handed to "
            "was already launched; retiring the verdict", issue.number,
        )
        _verdicts.drops_the_verdict(state, only=owned)
        gh.write_pinned_state(issue, state)
        return False
    if state.get(_verdicts._FEEDBACK_ANCHOR) is None:
        log.warning(
            "issue=#%d its reviewer's change request no longer carries the "
            "feedback anchor it was handed beside; holding the handoff rather "
            "than launching a developer no failed run could replay it to",
            issue.number,
        )
        return False
    return True


def _posts_the_feedback(context: _models._RequestedChanges, owned) -> bool:
    """Post the reviewer's feedback and hold the subject to what stands behind it; whether the handoff goes on.

    Only a post identified by the id it landed as goes on: that id is the
    anchor the handoff is written beside, so no pull request to post on, a
    post that failed, and one that left no id all hold the verdict unhanded.
    The post is a request of its own, long enough for a push or a later
    report to land; the records are read against the comment the post was
    made over, so the anchor it staged is not mistaken for another road's.
    """
    posted_over = dict(context.state.data)
    posted = _requested_changes._post_reviewer_feedback(context)
    if posted is None:
        log.warning(
            "issue=#%s holding its reviewer's change request until the "
            "feedback is posted on the PR", context.issue.number,
        )
        return False
    stood = _review_coverage._verdict_still_stands(
        context.gh, context.issue, context.state, context.decision.run.subject.recorded(), posted_over,
    )
    if not stood:
        drops_what_moved(context.gh, context.issue, context.state, stood, (owned, posted))
    return bool(stood)
