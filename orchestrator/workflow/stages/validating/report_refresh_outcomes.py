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
on a later tick without a second comment. The base refresh rebases nothing
while the report is captured and not yet handed on, or recorded and unsettled
(`git/base_sync/frozen.py`), so it finishes about the head it was written for.
Before anything is recorded the pull request's head and the requirements are
read again: a head somebody moved, or an issue edited, while the agent was out
makes the report one about a world that is gone, so it is dropped unrecorded
and the next tick asks its own road -- the reviewer road's refusal of a head
the debt does not explain, or the drift resume that answers the edit. A read
nobody could take records nothing either, and holds for the next tick.

A run launched on the refresh's road that finished on that report, no quota
stopping it and the checkout left clean on the head, is captured as it returns
(`refresh_road`), so the recording is the capture's transfer into the delivery
(`implementing/captured_report`), minted from what the capture kept and handed
off in the very commit that records it, and recorded from the run as ever where
no capture of it stands. A quota stop, a commit, or loose work the run returned
over earns no capture at all, and parks below as ever -- on the checkout as the
road read it returning, so a reset or a cleanup since publishes nothing of it
(`refresh_road.RefreshRoad.returned_over`). A park that hands a
captured report to nobody -- loose work the tree carries by the time the
disposition reads it again, a world that moved under the run -- withdraws the
capture first, so the reply answering the park is captured afresh. A reading
that did not return -- the checkout's tree, the pull request, the requirements
-- keeps it instead, the tick held with nothing written, for the dispatcher's
recovery to take that reading again with no developer run
(`captured_refresh`), which disposes a held capture here as well, on a result
rebuilt from it. The checkout's HEAD is the one the capture names, read as the
run returned.

A report VERIFIED where it already stood is refused. The report the pull
request carried when the rewrite landed is the account of the head before it,
so accepting a pointer to it would carry that account forward on nobody's
proof -- which is the one thing the debt exists to stop. A timeout parks the
same way, rather than taking the transient park a fix round's timeout takes:
that park clears itself once the branch reads level, and the debt behind it
would put the refresh straight back out on the next tick, one timeout after
another.

Everything else a finished run can leave -- a question, a silent exit, a
provider refusal, an unfinished command -- is an agent failure, and takes the
park that failure always takes (`implementing/parks.py`), so the
session-rotation streak and `/orchestrator continue` behave exactly as on
every other developer road. A quota stop takes it too, and is asked ahead of
the checkout and the timeout alike, since either refusal would name neither
the quota nor its reset and refuse the bare continue that retries the run.
An unfinished command is read ahead of the message: a run whose tool step
was still active when it ended -- what the AGY recovery behind the resume
hands back once its one retry is spent -- verified nothing it
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
from orchestrator.github import pinned_refusal as _pinned_refusal
from orchestrator.workflow.engine import (
    guards as _guards,
    report_delivery as _report_delivery,
    report_outcome_models as _outcome_models,
    report_outcomes as _outcomes,
    report_records as _records,
)
from orchestrator.workflow.stages.implementing import (
    captured_report as _captured_report,
    parks as _dev_parks,
    session_read as _session_read,
)
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
    "orchestrator rewrote the pull request onto, did not leave the checkout "
    "as it found it: {detail}"
)

_TIMED_OUT = (
    "the developer run asked for a fresh report of `{head}`, the head this "
    "orchestrator rewrote the pull request onto, timed out before it wrote one"
)

_VERIFIED = (
    "the developer run asked for a fresh report of `{head}`, the head this "
    "orchestrator rewrote the pull request onto, verified a report already on "
    "the pull request instead -- and the report standing there when the "
    "rewrite landed is about the head before it, so carrying it forward would "
    "describe another commit"
)


def _checkout_refusal(worktree: Path, head: str, standing: str = "") -> str | None:
    """Why the checkout is not a clean `head`: "" where it is, None where nobody could read it.

    The HEAD first and the tree behind it, each a reading that can fail, and
    one nobody could take holds rather than refuses: the next tick is as
    likely to read it. `standing` is a HEAD already read as the run returned
    -- the one its capture names -- and is answered on rather than read again.
    """
    standing = standing or _verification_probes._head_sha(worktree)
    if not standing:
        return None
    if standing != head:
        return _OFF_THE_HEAD
    tree = _worktree_status._worktree_status(worktree)
    if not tree.readable:
        return None
    return _LOOSE_WORK if tree.paths else ""


def _disposes_the_refresh(
    refresh: _models._ReportRefresh, worktree: Path, agent_result: AgentResult, returned: str | None = "",
) -> None:
    """Record and settle the fresh report the run wrote, or park what it left instead.

    Called for a run that finished, in the order the module note gives: the
    timeout, then the checkout, and only then the outcome the run ended on --
    which a run that left a command unfinished has none of, whatever its
    message says, so it takes the execution-failure park instead. A run an
    account quota stopped is asked about ahead of all three
    (`_parks_a_quota_stop`). The checkout's HEAD is the one the run's own
    capture names where one stands, read as it returned, so a HEAD that will
    not read again is never taken for a checkout nobody could read.
    `returned` is why the checkout refused the refresh as the run returned
    over it, as its road read it (`refresh_road.RefreshRoad.returned_over`):
    a refusal there, or a reading that did not return, stands as this
    disposition's own, so no cleanup or reset since makes such a run a
    refresh; "" -- nothing refused, or no reading taken -- reads the checkout
    here, where a later reading may still refuse what the return did not.

    Called by the dispatcher's recovery of a held capture too
    (`captured_refresh`), on a result rebuilt from it: no timeout, no quota,
    no unfinished step, and the READY report it was captured on.
    """
    head = refresh.head
    if _session_read._is_session_limit(agent_result):
        _parks_a_quota_stop(refresh, worktree, agent_result)
        return
    if agent_result.timed_out:
        refresh.parks(_TIMED_OUT.format(head=head))
        return
    refusal = returned
    if refusal == "":
        refusal = _checkout_refusal(worktree, head, _captured_report.pending_source(refresh.state, agent_result))
    if refusal != "":
        _left_the_head(refresh, refusal, agent_result)
        return
    outcome = None if agent_result.unfinished_steps else _outcomes._report_outcome_of_run(agent_result)
    if isinstance(outcome, _outcome_models._ReadyReport):
        _records_the_report(refresh, agent_result)
    elif isinstance(outcome, _outcome_models._VerifiedReport):
        refresh.parks(_VERIFIED.format(head=head))
    else:
        _parks_the_failure(refresh, agent_result)


def _parks_a_quota_stop(
    refresh: _models._ReportRefresh, worktree: Path, agent_result: AgentResult,
) -> None:
    """Park a refresh an account quota stopped as the session limit, whatever its checkout reads as.

    The quota is what a human has to wait out, so it outranks the timeout and
    the checkout refusals alike, whose `report_undeliverable` park would name
    neither the quota nor the reset. What those would have kept is kept: a
    commit the run left off the head is recorded as work no report describes,
    loose work stays in the checkout, and the report the refresh owed stays
    owed (`_parks_the_failure`) for the run the continue buys.
    """
    if _checkout_refusal(worktree, refresh.head) == _OFF_THE_HEAD:
        refresh.state.set(_report_delivery.UNREPORTED_WORK, True)
    _parks_the_failure(refresh, agent_result)


def _left_the_head(refresh: _models._ReportRefresh, refusal: str | None, agent_result: AgentResult) -> None:
    """Park a run that committed or left loose work, with what it committed owed a report; hold over an unread one.

    Neither hands the run's report to anybody, so the run's own capture,
    where the run returned clean on the head and its tree reads otherwise
    now, is settled first (`implementing/captured_report.parks_beside_the_capture`):
    a checkout nobody could read (`refusal` None) keeps it, the tick held
    with nothing written, for the recovery to read it again with no
    developer run; a checkout carrying loose work withdraws it, so the reply
    answering the park is captured afresh, and a withdrawal that does not
    settle parks nothing. With no capture, an unread checkout holds with what
    the tick staged written, as it always did.
    """
    state = refresh.state
    if not _captured_report.parks_beside_the_capture(
        refresh.gh, refresh.issue, state, agent_result, unread=refusal is None,
    ):
        return
    if refusal is None:
        log.info(
            "issue=#%d could not read the checkout its report refresh ran in; "
            "recording nothing and holding for the next tick", refresh.issue.number,
        )
        refresh.write()
        return
    if refusal == _OFF_THE_HEAD:
        state.set(_report_delivery.UNREPORTED_WORK, True)
    refresh.parks(_LEFT_THE_HEAD.format(head=refresh.head, detail=refusal))


def _parks_the_failure(
    refresh: _models._ReportRefresh, agent_result: AgentResult,
) -> None:
    """Park a run that wrote no report the way an agent failure always parks, the debt beside it.

    No run parked here was captured: the refresh's road takes no quota stop,
    whatever its message closed on, and no return without a READY report.
    """
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
    a recording this build refuses parks where it is made. The run's own
    capture, where one stands, is what is recorded: handed to the delivery
    in the commit that records it (`implementing/captured_report`). A world
    that moved withdraws it, since its report is about a world that is gone,
    and one nobody could read keeps it, the tick held with nothing written,
    for the recovery to read again.
    """
    moved = _moved_under_the_run(refresh)
    if moved is not False:
        if _captured_report.parks_beside_the_capture(
            refresh.gh, refresh.issue, refresh.state, agent_result, unread=moved is None,
        ):
            refresh.write()
        return
    if _captured_report.recording_stops_the_tick(
        refresh.gh, refresh.issue, refresh.state, agent_result,
        _records.HandedRun(WorkflowLabel.VALIDATING, refresh.requirements),
    ):
        return
    _settlement._settles_the_report(
        refresh.gh, refresh.spec, refresh.issue, refresh.state,
        WorkflowLabel.VALIDATING,
    )


def _moved_under_the_run(refresh: _models._ReportRefresh) -> bool | None:
    """Whether the pull request's head or the requirements moved while the agent was out; None where unread.

    A read nobody could take records nothing either, since a report recorded
    over a world nobody could see would be bound and published onto whatever
    it is -- but it proves nothing moved, so it is told apart from a move.
    """
    head = _review_report._pull_request_head(refresh.gh, refresh.issue, refresh.debt.pr_number)
    if head is None:
        return None
    if head != refresh.head:
        log.info(
            "issue=#%d PR #%d no longer reads as standing on %s, the head its "
            "report refresh was asked about; recording nothing",
            refresh.issue.number, refresh.debt.pr_number, refresh.head[:8],
        )
        return True
    try:
        moved = refresh.requirements_moved(refresh.gh.get_issue(refresh.issue.number))
    except _pinned_refusal.RecordRefused:
        # A record admission refuses is the dispatcher's to answer, not this catch's.
        raise
    except Exception:
        log.exception(
            "issue=#%d could not read its requirements again after its report "
            "refresh; recording nothing", refresh.issue.number,
        )
        return None
    if moved:
        log.info(
            "issue=#%d requirements moved while its report refresh ran; "
            "recording nothing and leaving the edit to the drift road",
            refresh.issue.number,
        )
    return moved
