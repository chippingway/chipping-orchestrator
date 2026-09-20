# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The completion report a requirements-drift resume hands back, recorded first.

An edit landing once a pull request is open resumes the developer instead of
re-deciding the work, and what that session hands back is a report as well as,
perhaps, a commit. The report is the reviewer's only account of what the
resumed session did, and the session is gone the moment the tick moves on -- so
it is recorded on the pinned comment ahead of the size gate and the push, as an
initial implementation's is, and stamped with the requirements revision the
drift check handed the resume rather than with whatever the issue says by the
time publication succeeds.

A run that committed is held to the report contract: committed work with no
report parks for the reply that resumes the session to write one. A run that
committed nothing is held to it only where it wrote a report anyway -- the
drift prompt asks for one whenever the report has to change -- and that report
goes onto the head the pull request already carries, needing no new commit, once
the tree is proved to carry nothing that head does not.
A commit stranded by an earlier run that never completed owes no report, so a
reply publishing it with an `ACK:` publishes the code alone. One the issue
already owes a report for is the other way round: an earlier run committed it
and parked for want of a report, so it stays unpublished until a reply brings
one, and anything else the reply says is read as a reply with nothing to
publish.

Nothing is bound here. What happens to the report once it is recorded -- bound
to the publication and settled, `report_settlement`'s, asked by the caller once
its own bookkeeping is written, or held in front of the reviewer until it is,
`report_hold`'s -- follows the relabel on `in_review`, so no settled report ever
stands beside a label still claiming the approval it made stale.
"""
from __future__ import annotations

from github.Issue import Issue

from orchestrator import config
from orchestrator.agents.models import AgentResult
from orchestrator.git.verification import status as _worktree_status
from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    guards as _guards,
    report_delivery as _report_delivery,
    report_delivery_state as _delivery_state,
    report_outcome_models as _outcome_models,
    report_outcomes as _outcomes,
    report_record_state as _record_state,
)
from orchestrator.workflow.stages.implementing import checkout_parks as _checkout_parks
from orchestrator.workflow.stages.validating import models as _models, state as _state

_REPORTS = (_outcome_models._ReadyReport, _outcome_models._VerifiedReport)

# Why a run that did not finish leaves its commit where it is. The engine's
# own notice speaks for a developer that finished and declined to report, and
# would tell this human their session wrote something it never did.
_UNFINISHED_PARK = (
    "{mentions} this issue's developer resume left committed work on the "
    "branch and did not finish -- a nonzero exit, a provider refusal, or a "
    "launch nothing invoked -- so no completion report of that work exists. "
    "Nothing was published: whatever this run committed is still in the "
    "worktree, the branch is untouched, and the pull request still stands on "
    "the commit it already carried. Work an edit to this issue earns reaches "
    "the pull request with the report of it or not at all, because a reviewer "
    "handed a commit nobody described has no account of what was done and no "
    "session left to ask. Reply and the orchestrator resumes the session; the "
    "report it writes then is the one that gets published, and it publishes "
    "this commit with it."
)


def _reports(agent_result: AgentResult) -> bool:
    """Whether a run closed on one of the two report outcomes."""
    return isinstance(_outcomes._report_outcome_of_run(agent_result), _REPORTS)


def _owes_the_undescribed(state: PinnedState) -> None:
    """Record that this road is holding commits no report describes.

    Both flags, because they answer different readers. The debt is what the
    review hold and the resume that reads a reply as the report it asked for
    ask; the undescribed-work flag is what says these particular commits are
    the ones nothing accounts for, so a record an EARLIER run left cannot be
    mistaken for their description.
    """
    state.set(_report_delivery.UNREPORTED_WORK, True)
    state.set(_report_delivery.OWED_REPORT, True)


def _records_the_run(
    gh: GitHubClient,
    issue: Issue,
    state: PinnedState,
    run: _models._DevFixRun,
) -> bool:
    """Record the report a drift resume wrote, ahead of the gate; True where held.

    True where nothing may be published. A report this run wrote is recorded
    and the gate reads the candidate behind it; a report this build cannot
    record parks, as it does on every road.

    A run that wrote NO usable report publishes nothing at all, and that
    holds whether or not the run finished. The engine leaves an incomplete
    run alone -- a nonzero exit, a provider refusal, a launch nothing invoked
    are failures other roads answer, and on the roads it serves nothing is
    published either way -- but this road publishes, and a commit it pushed
    for such a run would reach the reviewer with no account of it anywhere
    and no session left to ask. So the failure is parked as the missing
    report it also is, and the reply that answers it resumes the session,
    which writes the report and publishes the work with it.
    """
    if _report_delivery.recording_stops_the_tick(
        gh, issue, state, run.agent_result, run.handed,
    ):
        return True
    if _reports(run.agent_result):
        return False
    _owes_the_undescribed(state)
    _report_delivery.parks_an_undeliverable_report(
        gh, issue, state,
        _UNFINISHED_PARK.format(mentions=config.HITL_MENTIONS),
    )
    return True


def _withholds_the_stranded(state: PinnedState, run: _models._DevFixRun) -> bool:
    """Whether a commit an earlier run stranded stays unpublished, and owed.

    This road is the only one that publishes such a commit, and it may only
    publish it under a report that describes it -- so a reply that brings
    none withholds it, whatever became of the run that left it. Which run
    that was decides nothing: what the pull request would come to carry is a
    commit nothing on it describes either way.

    The debt goes down with the refusal rather than a park, because the reply
    that earned it keeps its own road -- an `ACK:` is still an answer to the
    edit, a question is still a question -- and it is the review hold behind
    them that asks a human for the report the work is missing. Withheld with
    no debt, the commit would sit in the checkout with nothing saying the
    pull request is short of it.

    A reply that IS a report publishes it, since a report written over the
    branch as it stands describes that commit as well as anything this run
    added.
    """
    if run.handed is None or not run.stranded_head:
        return False
    if _reports(run.agent_result):
        return False
    _owes_the_undescribed(state)
    return True


def _owes_an_unrecorded_report(state: PinnedState) -> bool:
    """Whether the issue owes a report no record of this issue's describes.

    Work a COMPLETED run committed and nobody described is the first reading,
    and it is the only one that survives a record left by an EARLIER run: that
    record is an account of the branch before those commits, so publishing
    them under it would settle a report of work it never saw and send the
    reviewer the whole branch under it. It is retired by a report written over
    the branch as it stands, which is what the reply to its park brings.

    The debt an undeliverable-report park leaves with nothing recorded at all
    is the other: a flag, or the park's own reason, and no record to publish
    from. Records are asked as CLAIMS, so one nobody can read is still a
    record -- parked by the owner that reads it -- and not this.

    The undescribed-work flag answers for itself, ahead of the debt it is
    normally written beside. Only a report written over the branch as it
    stands retires it, and that report retires the debt in the same write --
    so a flag standing without one says an owner cleared the debt over a
    report about some earlier head, and the commits it never saw are
    undescribed whatever the comment says is owed.
    """
    if state.get(_report_delivery.UNREPORTED_WORK):
        return True
    if not _report_delivery.owes_a_report(state):
        return False
    return not (
        _delivery_state.carries_delivered_report(state)
        or _record_state.carries_pending_report(state)
    )


def _records_a_report_alone(
    gh: GitHubClient,
    issue: Issue,
    state: PinnedState,
    run: _models._DevFixRun,
) -> str:
    """Record the report of a resume that committed nothing, and say how.

    `reported` once it is recorded, whether or not it settles later: the
    reviewer is held until it does, so the caller routes the head exactly as
    it routes an `ACK:`, and binds the report itself.

    The tree is PROVED clean first, as every publication's is. A report of a
    checkout carrying loose work describes something the pull request does
    not carry, and recorded anyway it could never settle -- the
    reconciliation defers on a dirty checkout for good -- so the run parks on
    the tree the way a commit would, with nothing recorded but the debt, and
    the reply that answers the park resumes the session to finish the work and
    report again.
    """
    tree = _worktree_status._worktree_status(run.worktree)
    if not tree.is_clean:
        # The debt outlives the tree park, which names the loose files rather
        # than the report: this run DID report, and refusing to record it
        # leaves the pull request owed one all the same. Recorded here, the
        # reply that answers the park is read as the answer to the report it
        # asked for, and the write below carries it.
        state.set(_report_delivery.OWED_REPORT, True)
        _checkout_parks._on_unpublishable_tree(
            gh, issue, state,
            _guards._ParkedRun(run.agent_result, _guards._ROUTE_DEV_DRIFT_RESUME),
            tree,
        )
        return _state._OUTCOME_PARKED
    if _records_the_run(gh, issue, state, run):
        return _state._OUTCOME_PARKED
    state.set("silent_park_count", 0)
    return _state._OUTCOME_REPORTED
