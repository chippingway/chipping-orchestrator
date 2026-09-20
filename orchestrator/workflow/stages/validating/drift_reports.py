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


def _reports(agent_result: AgentResult) -> bool:
    """Whether a run closed on one of the two report outcomes."""
    return isinstance(_outcomes._report_outcome_of_run(agent_result), _REPORTS)


def _records_the_run(
    gh: GitHubClient,
    issue: Issue,
    state: PinnedState,
    run: _models._DevFixRun,
) -> bool:
    """Record the report a drift resume wrote, ahead of the gate; True where held.

    A commit this run made is held to the contract, so a run that completed
    without a usable report parks rather than publishing undescribed work. A
    commit stranded by an earlier run is not this run's to describe, so it is
    recorded only where this run reported anyway.
    """
    if run.stranded_head and not _reports(run.agent_result):
        return False
    return _report_delivery.recording_stops_the_tick(
        gh, issue, state, run.agent_result, run.handed,
    )


def _withholds_the_stranded(state: PinnedState, run: _models._DevFixRun) -> bool:
    """Whether a stranded commit stays unpublished for want of its report.

    Only where the issue owes a report nothing recorded -- an earlier run
    committed this work and parked with no report of it -- and this reply is
    not one. Published anyway, the debt would ride under code nobody
    described, and the review behind it would be handed that code.
    """
    if run.handed is None or not run.stranded_head:
        return False
    return _owes_an_unrecorded_report(state) and not _reports(run.agent_result)


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
    """
    if not _report_delivery.owes_a_report(state):
        return False
    if state.get(_report_delivery.UNREPORTED_WORK):
        return True
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
