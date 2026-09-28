# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a report refresh's run left, recorded and settled or parked.

The run was asked for one thing: a fresh, complete report of the head this
orchestrator rewrote the pull request onto, with nothing committed and nothing
left in the checkout. So the checkout is read first, since it is the part of
the answer the report cannot vouch for: a run that committed, or left loose
work, handed back a report of something the pull request does not carry. That
parks, and commits it made are recorded as work no report describes, so the
reply that answers the park is held to a report written over the branch as it
stands.

A report READY for publication is the only answer that pays. It is recorded
through the same delivery every developer report goes through -- stamped with
the requirements the refresh froze, and with no round or feedback riding on it,
since answering a rewrite answers nobody's words -- and then bound to the
publication the receipt names and settled through the reconciliation, whose
receipt is what lets a lost post response or an interrupted settlement finish
on a later tick without a second comment. Before anything is recorded the pull
request's head and the requirements are read again: a head somebody moved, or
an issue edited, while the agent was out makes the report one about a world
that is gone, so it is dropped unrecorded and the next tick asks its own road
-- the reviewer road's refusal of a head the debt does not explain, or the
drift resume that answers the edit.

A report VERIFIED where it already stood is refused. The report the pull
request carried when the rewrite landed is the account of the head before it,
so accepting a pointer to it would carry that account forward on nobody's
proof -- which is the one thing the debt exists to stop. A timeout parks the
same way, rather than taking the transient park a fix round's timeout takes:
that park clears itself once the branch reads level, and the debt behind it
would put the refresh straight back out on the next tick, one timeout after
another.

Everything else a finished run can leave -- a question, a silent exit, a quota
stop, a provider refusal, an unfinished command -- is an agent failure, and
takes the park that failure always takes (`implementing/parks.py`), so the
session-rotation streak and `/orchestrator continue` behave exactly as on
every other developer road. An unfinished command is read ahead of the message:
a run whose tool step was still active when it ended -- what the AGY recovery
behind the resume hands back once its one retry is spent -- verified nothing it
claims, so a report block it wrote is no report, and it parks as the execution
failure it is rather than being published and settled. The debt of the report rides that park as
`developer_report_owed`, and that is what makes the reply to it a report
rather than a question: `awaiting_resume` reads a reply as the report a park
owes wherever that flag stands, and its report pays the debt when it settles.
"""
from __future__ import annotations

import logging
from pathlib import Path

from orchestrator.agents.models import AgentResult
from orchestrator.git.verification import probes as _verification_probes, status as _worktree_status
from orchestrator.workflow.engine import (
    guards as _guards,
    report_delivery as _report_delivery,
    report_outcome_models as _outcome_models,
    report_outcomes as _outcomes,
    report_records as _records,
)
from orchestrator.workflow.stages.implementing import parks as _dev_parks
from orchestrator.workflow.stages.validating import (
    report_refresh_models as _models,
    report_settlement as _settlement,
    review_report as _review_report,
)
from orchestrator.workflow.state import WorkflowLabel

log = logging.getLogger("orchestrator.workflow")

# Why a checkout is not the clean rewritten head, in the words either notice
# below quotes.
_OFF_THE_HEAD = "it stands on another commit"

_LOOSE_WORK = "it carries uncommitted work the pull request does not"

_LEFT_THE_HEAD = (
    "the developer run asked only for a report of `{head}`, the head this "
    "orchestrator rebased the pull request onto, did not leave the checkout "
    "as it found it: {detail}"
)

_TIMED_OUT = (
    "the developer run asked for a fresh report of `{head}`, the head this "
    "orchestrator rebased the pull request onto, timed out before it wrote one"
)

_VERIFIED = (
    "the developer run asked for a fresh report of `{head}`, the head this "
    "orchestrator rebased the pull request onto, verified a report already on "
    "the pull request instead -- and the report standing there when the "
    "rebase landed is about the head before it, so carrying it forward would "
    "describe another commit"
)


def _checkout_refusal(worktree: Path, head: str) -> str | None:
    """Why the checkout is not a clean `head`: "" where it is, None where nobody could read it.

    The HEAD first and the tree behind it, each a reading that can fail, and
    one nobody could take holds rather than refuses: the next tick is as
    likely to read it.
    """
    standing = _verification_probes._head_sha(worktree)
    if not standing:
        return None
    if standing != head:
        return _OFF_THE_HEAD
    tree = _worktree_status._worktree_status(worktree)
    if not tree.readable:
        return None
    return _LOOSE_WORK if tree.paths else ""


def _disposes_the_refresh(
    refresh: _models._ReportRefresh, worktree: Path, agent_result: AgentResult,
) -> None:
    """Record and settle the fresh report the run wrote, or park what it left instead.

    Called for a run that finished, in the order the module note gives: the
    timeout, then the checkout, and only then the outcome the run ended on --
    which a run that left a command unfinished has none of, whatever its
    message says, so it takes the execution-failure park instead.
    """
    head = refresh.head
    if agent_result.timed_out:
        refresh.parks(_TIMED_OUT.format(head=head))
        return
    refusal = _checkout_refusal(worktree, head)
    if refusal is None:
        log.info(
            "issue=#%d could not read the checkout its report refresh ran in; "
            "recording nothing and holding for the next tick", refresh.issue.number,
        )
        refresh.write()
        return
    if refusal:
        _left_the_head(refresh, refusal)
        return
    outcome = None if agent_result.unfinished_steps else _outcomes._report_outcome_of_run(agent_result)
    if isinstance(outcome, _outcome_models._ReadyReport):
        _records_the_report(refresh, agent_result)
    elif isinstance(outcome, _outcome_models._VerifiedReport):
        refresh.parks(_VERIFIED.format(head=head))
    else:
        _parks_the_failure(refresh, agent_result)


def _left_the_head(refresh: _models._ReportRefresh, refusal: str) -> None:
    """Park a run that committed or left loose work, with what it committed owed a report."""
    if refusal == _OFF_THE_HEAD:
        refresh.state.set(_report_delivery.UNREPORTED_WORK, True)
    refresh.parks(_LEFT_THE_HEAD.format(head=refresh.head, detail=refusal))


def _parks_the_failure(
    refresh: _models._ReportRefresh, agent_result: AgentResult,
) -> None:
    """Park a run that wrote no report the way an agent failure always parks, the debt beside it."""
    refresh.state.set(_report_delivery.OWED_REPORT, True)
    _dev_parks._on_question(
        refresh.gh, refresh.issue, refresh.state,
        _guards._ParkedRun(
            agent_result, _guards._ROUTE_REPORT_REFRESH, before_sha=refresh.head,
        ),
    )
    refresh.write()


def _records_the_report(
    refresh: _models._ReportRefresh, agent_result: AgentResult,
) -> None:
    """Record the fresh report under the frozen requirements, then bind and settle it.

    Nothing is recorded over a world that moved while the agent was out, and
    a recording this build refuses parks where it is made.
    """
    if _moved_under_the_run(refresh):
        refresh.write()
        return
    if _report_delivery.recording_stops_the_tick(
        refresh.gh, refresh.issue, refresh.state, agent_result,
        _records.HandedRun(WorkflowLabel.VALIDATING, refresh.requirements),
    ):
        return
    _settlement._settles_the_report(
        refresh.gh, refresh.spec, refresh.issue, refresh.state,
        WorkflowLabel.VALIDATING,
    )


def _moved_under_the_run(refresh: _models._ReportRefresh) -> bool:
    """Whether the pull request's head or the requirements moved while the agent was out.

    Either read nobody could take counts as moved: a report recorded over a
    world nobody could see would be bound and published onto whatever it is.
    """
    head = _review_report._pull_request_head(refresh.gh, refresh.issue, refresh.debt.pr_number)
    if head != refresh.head:
        log.info(
            "issue=#%d PR #%d no longer reads as standing on %s, the head its "
            "report refresh was asked about; recording nothing",
            refresh.issue.number, refresh.debt.pr_number, refresh.head[:8],
        )
        return True
    try:
        moved = refresh.requirements_moved(refresh.gh.get_issue(refresh.issue.number))
    except Exception:
        log.exception(
            "issue=#%d could not read its requirements again after its report "
            "refresh; recording nothing", refresh.issue.number,
        )
        return True
    if moved:
        log.info(
            "issue=#%d requirements moved while its report refresh ran; "
            "recording nothing and leaving the edit to the drift road",
            refresh.issue.number,
        )
    return moved
