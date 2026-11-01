# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A rewritten head's report refresh held under a control, captured, and finished with no developer run.

The developer asked for a fresh report of the head this orchestrator rebased
the pull request onto finishes on one while an operator holds the issue under
`paused` or `backlog`. Its report is captured as it returns -- an Antigravity
continuation's included -- and nothing else is settled: no report, park,
round, session, or debt moves. Unheld, the dispatcher's recovery records that
report through the refresh's own disposition, binds it to the receipt's
publication and settles it about the rewritten head, with no developer or
reviewer run, no run charged or accounted again, and no round spent; the next
tick drops the debt and hands the reviewer that report. A verification of the
report the rebase left behind, a timeout, an unfinished command, a quota stop
whatever its message closed on, and a report over a commit or over loose work
-- read as the run returns, whoever cleans the checkout during the hold -- earn
no capture at all, their accounting alone kept. A debt, receipt, head,
checkout, or requirements that moved while the capture waited retires it with
nothing published, and one nobody can read holds it with nothing written until
it reads; a lineage the refresh was entered over is asked again by its own
module (`test_captured_refresh_lineage`). A process or an answer lost at the
handoff, and a control applied as the handoff goes out, are finished by a later
dispatch with nothing paid twice, and the base refresh rebases nothing over the
capture until its report has settled.

On a live tick the capture is the report's one copy as well: loose work the
tree carries only once the capture was taken withdraws it ahead of its park, so
the reply answering that park is captured afresh; a pull request that will not
read once the run is back keeps it for the next dispatch; and a HEAD that will
not read again behind it is answered on the head the capture names.
"""
from __future__ import annotations

import contextlib
import unittest
from dataclasses import replace
from types import MappingProxyType
from unittest.mock import MagicMock, patch

from orchestrator.git.verification.status import _WorktreeStatus
from orchestrator.git.worktrees.models import ProbeAnswer
from orchestrator.workflow.engine import completion_handoff as _handoff, guards as _guards
from tests.workflow import (
    agent_failure_values as _agent_failures,
    captured_drifts as _drifts,
    captured_fixes as _fixes,
    drift_reports as _drift_world,
    fix_reports as _fix_world,
    published_reports as _published_reports,
    reviewed_reports as _reviewed,
)
from tests.workflow.stages.validating import (
    captured_refresh_test_support as _held,
    report_refresh_crashes as _crashes,
    report_refresh_test_support as _support,
    squash_rebase_journey_support as _journey,
)

RUN_AGENT = _held.RUN_AGENT

DEBT = _support.DEBT

LEASE = "implementing_published_lease"

# What a case moves beside the dispatch's own readings, as it names each: a
# push over the pull request, an edit of the issue, and a pull request GitHub
# does not answer.
PUSHED = "pushed"

EDITED = "edited"

UNREADABLE_PR = "unreadable_pr"

_MOVES = frozenset((PUSHED, EDITED, UNREADABLE_PR))

UNREPORTED_WORK = "developer_report_unreported_work"

UNDELIVERABLE = "report_undeliverable"

AWAITING_HUMAN = "awaiting_human"

# What every refresh here reports.
FRESH = _support.FRESH_REPORT

_CLEAN = _WorktreeStatus(readable=True, paths=())

# A refresh's run finished on a fresh report of the rewritten head.
REPORTED = _support._agent(session_id=_drift_world.DEV_SESSION, last_message=_support.fresh())

# A run whose message opens on an account quota's notice and closes on a
# fresh report, and the park a session limit takes.
QUOTA_REPORT = _support._agent(
    session_id=_drift_world.DEV_SESSION,
    last_message=f"{_agent_failures.SESSION_LIMIT_MESSAGE}\n\n{_support.fresh()}",
)

SESSION_LIMIT = "agent_silent"

# The debt carried onto another head than the one the refresh reported on.
CARRIED = replace(_support.REWRITE, rewritten_head=_support.SECOND_HEAD).recorded()

# What each control holds an issue under.
CONTROLS = (_fixes.PAUSED, _fixes.BACKLOG)

# Every prerequisite that moves while the capture waits, spelled as a reader
# takes it -- the debt paid, gone, or carried onto another head, the receipt
# naming another publication, the pull request pushed over, the checkout reset
# off the head, the issue edited -- beside what the recovery's dispatch reads.
MOVED = (
    ("the debt paid", {DEBT: None}, {}),
    ("the debt gone", {DEBT: _fixes.OMITTED}, {}),
    ("the debt onto another head", {DEBT: CARRIED}, {}),
    ("the receipt onto another publication", {LEASE: _support.SECOND_HEAD}, {}),
    ("the pull request pushed over", {}, {PUSHED: _support.FOREIGN_HEAD}),
    ("the checkout reset", {}, {_drift_world.HEAD_SHAS: (_support.SECOND_HEAD,)}),
    ("the requirements edited", {}, {EDITED: _drift_world.LATER_BODY}),
)

# Every prerequisite nobody can read while the capture waits -- the debt, the
# receipt, the checkout's ownership, the pull request, and the checkout's tree
# the recovery's disposition proves clean -- beside the dispatch's readings.
UNREAD = (
    ("the debt", {DEBT: {"pr": _support.PR}}, {}),
    ("the receipt", {LEASE: "not-a-commit"}, {}),
    ("the checkout's ownership", {}, {"checkout_identity": ProbeAnswer.UNREADABLE}),
    ("the pull request", {}, {UNREADABLE_PR: True}),
    ("the checkout's tree", {}, {"tree_readable": False}),
)

# A live run that leaves the checkout off the rewritten head or carrying loose
# work, beside the readings it is dispatched over, the work it leaves recorded
# as nothing describes, and the stage its capture is left at: a commit, and
# loose work, the run returns over, which earn none -- and park all the same
# where a reset or a cleanup puts the checkout back before the disposition reads
# it; and loose work the tree carries only by the time the disposition reads it
# again, which retires one.
_DIRTY = _WorktreeStatus(readable=True, paths=("notes.txt",))

_COMMITTED = MappingProxyType({_drift_world.HEAD_SHAS: (_support.REWRITTEN_HEAD, _drift_world.FIXED_HEAD)})

_LOOSE = MappingProxyType({"tree_states": (_CLEAN, _DIRTY, _CLEAN)})

_RESET = MappingProxyType({
    _drift_world.HEAD_SHAS: (_support.REWRITTEN_HEAD, _drift_world.FIXED_HEAD, _support.REWRITTEN_HEAD),
})

MOVED_CHECKOUTS = (
    ("a commit it returns over", _COMMITTED, True, None),
    ("a commit it returns over, reset since", _RESET, True, None),
    ("loose work it returns over", {"tree_states": (_CLEAN, _DIRTY)}, None, None),
    ("loose work it returns over, cleaned since", _LOOSE, None, None),
    ("loose work behind its capture", {"tree_states": (_CLEAN, _CLEAN, _DIRTY)}, None, _fixes.RETIRED),
)

# Every return a refresh's road refuses to capture, held all the same, beside
# the checkout it returns over: a verification of the report the rebase left
# behind, which only a fresh report pays; a timeout; a run that left a command
# unfinished, whatever its message reads as; an account quota's notice closing
# on a report; and a report over a commit, or over loose work somebody cleans
# up while the issue is held.
UNPAID = (
    ("a verification of the report standing", None, {}),
    ("a timeout", _support._agent(session_id=_drift_world.DEV_SESSION, timed_out=True), {}),
    (
        "an unfinished command",
        replace(_held.continued(), unfinished_steps=_held.unfinished_agy_run().unfinished_steps),
        {},
    ),
    ("a quota notice closing on a report", QUOTA_REPORT, {}),
    ("a report over a commit", REPORTED, _COMMITTED),
    ("a report over loose work cleaned up since", REPORTED, _LOOSE),
)

# A checkout whose HEAD reads as the rewritten head as a run is launched over
# it and as the run returns, will not read once behind that, and reads again
# from then on.
_HEAD = _support.REWRITTEN_HEAD

LOST_ONCE = MappingProxyType({_drift_world.HEAD_SHAS: (_HEAD, _HEAD, "", _HEAD)})

# Where the handoff of a recovered capture is lost, beside how many dispatches
# after it run nobody before the reviewer does: a process lost before the
# commit leaves the capture pending, for the next dispatch to finish; one lost
# once it landed, or an answer lost, leaves the delivery owning the report.
LOST = (
    (_fixes.SENT, 1),
    (_fixes.LANDED, 0),
    (_fixes.ANSWER, 0),
)


class HeldRefreshTest(unittest.TestCase, _held.HeldRefreshes):
    """A held refresh's report is captured, waited through, and finished once with no developer run."""

    def test_each_hold_is_finished_once(self) -> None:
        # Under either control the run is launched once and only its charge,
        # accounting, and capture move; two held polls write nothing. Unheld,
        # the report is published once and settled about the rewritten head
        # under the baseline, one revision past the report the rebase left,
        # with nothing parked, charged, accounted, or spent, and nobody run.
        # The next tick drops the debt and runs the reviewer alone.
        for control in CONTROLS:
            with self.subTest(control=control):
                self.rebased()
                held = self.held_refresh(control=control)
                self.held_ticks()
                self.unheld()
                self.assert_finished(self.kept(held))
                self.reviewed_next()

    def test_a_recovery_settles_as_the_live_refresh(self) -> None:
        # The same refresh, its return held and recovered, settles the same
        # session, report, round, and capture as one whose own tick disposed
        # of it -- a resumed conversation charged one resume either way.
        settled = []
        for held in (False, True):
            self.rebased()
            if held:
                self.held_refresh()
                self.unheld()
            else:
                self.dispatched(REPORTED)
            pinned, current = self.pinned(), self.records()["current"]
            settled.append((
                pinned["dev_session_id"], pinned.get("dev_resume_count"), pinned["review_round"],
                _fixes.stage_of(pinned), current.subject, current.report_revision,
            ))
        self.assertEqual(settled[0], settled[1])

    def test_a_held_continuation_is_finished_once(self) -> None:
        # An Antigravity session leaves a command running and its one
        # continuation finishes on the report while the issue is held: both
        # exits are accounted, the continuation's report alone is captured,
        # and the recovery publishes it once with no developer run.
        self.rebased()
        _reviewed.restate(self, dev_agent=_held.AGY)
        held = self.held_refresh(_held.continued(), before=(_held.unfinished_agy_run(),))
        self.assertEqual(_fixes.capture_of(held).session_id, _held.AGY_SESSION)
        self.unheld()
        self.assert_finished(self.kept(held))
        self.reviewed_next()

    def test_an_unconfirmed_capture_is_finished_next(self) -> None:
        # Nothing holds the issue, but the capture's own commit lands with
        # its answer lost: the tick withholds everything behind it, posting
        # nothing. The next dispatch reads the capture back and finishes it,
        # with no second developer run.
        self.rebased()
        lost = _fixes.LostAtTheHandoff(self.github, _fixes.ANSWER, stage=_fixes.PENDING)
        with patch.object(self.github, "edit_pinned_state", lost):
            self.dispatched(REPORTED)[RUN_AGENT].assert_called_once()
        held = self.pinned()
        self.assertEqual(_fixes.stage_of(held), _fixes.PENDING)
        self.assertEqual(self.fresh_reports(), [])
        self.dispatched()[RUN_AGENT].assert_not_called()
        self.assert_finished(self.kept(held))


class LiveCaptureTest(unittest.TestCase, _held.HeldRefreshes):
    """A live refresh's own tick settles its capture: withdrawn ahead of a park, kept over a reading that failed."""

    def test_a_moved_checkout_parks_it(self) -> None:
        # The run committed, or left loose work, beside its report: a return
        # over a checkout off the head or carrying loose work earns no
        # capture, and parks on the checkout as it returned, however it reads
        # by the disposition -- reset or cleaned since -- so nothing is
        # published from it; loose work the tree carries only once its
        # capture was taken retires that capture ahead of the park. Either
        # way the park stands, and the reply answering it resumes the
        # developer, whose report is captured afresh and handed on, published
        # once.
        for name, reading, unreported, stage in MOVED_CHECKOUTS:
            with self.subTest(name):
                self.rebased()
                self.dispatched(REPORTED, **reading)
                parked = self.pinned()
                self.assertEqual((self.captured_stage(), self.published()), (stage, []))
                self.assertEqual(parked["park_reason"], UNDELIVERABLE)
                self.assertEqual(parked.get(UNREPORTED_WORK), unreported)
                _fix_world.replied(self, "please write the report of the rebased head")
                self.dispatched(REPORTED)
                self.assertEqual(self.captured_stage(), _fixes.HANDED_OFF)
                self.assertEqual(self.published(), [FRESH])

    def test_a_quota_stop_is_never_captured(self) -> None:
        # The run's message opens on an account quota's notice and closes on
        # a report block: the quota is what it parks as, so its road takes
        # no capture of it, and no later dispatch publishes the report as a
        # refresh.
        self.rebased()
        self.dispatched(QUOTA_REPORT)
        self.assertIsNone(self.captured_stage())
        self.assertEqual(self.pinned()["park_reason"], SESSION_LIMIT)
        self.dispatched()[RUN_AGENT].assert_not_called()
        self.assertEqual(self.published(), [])

    def test_a_lost_head_still_settles_it(self) -> None:
        # The checkout's HEAD reads as the rewritten head as the run is
        # launched and as it returns, and will not read once behind that
        # capture: the tick answers on the head the capture names and hands
        # the report on, unparked, rather than holding the capture over a
        # checkout nobody could read. The next tick settles it, once, and the
        # reviewer is handed it.
        self.rebased()
        self.dispatched(REPORTED, **LOST_ONCE)
        handed = self.pinned()
        self.assertEqual(_fixes.stage_of(handed), _fixes.HANDED_OFF)
        self.assertFalse(handed.get(AWAITING_HUMAN))
        self.reviewed_next()
        self.assertEqual(self.published(), [FRESH])

    def test_an_unanswered_pull_request_keeps_it(self) -> None:
        # The pull request will not read once the run is back: nothing is
        # recorded, parked, or written past the run's accounting and its
        # capture, and the next dispatch finishes that capture with no
        # second developer run.
        self.rebased()
        unanswered = _held.UnansweredAfter(self)
        self.dispatched(MagicMock(side_effect=unanswered))[RUN_AGENT].assert_called_once()
        unanswered.answered()
        held = self.pinned()
        self.assertEqual(_fixes.stage_of(held), _fixes.PENDING)
        self.assertEqual(self.unrecorded(), _support.NOTHING)
        self.dispatched()[RUN_AGENT].assert_not_called()
        self.assert_finished(self.kept(held))


class UnpaidReturnTest(unittest.TestCase, _held.HeldRefreshes):
    """A held return its road refuses keeps its accounting alone, and the next tick asks again."""

    def test_an_unpaid_return_is_never_captured(self) -> None:
        # Nothing is captured, recorded, parked, or published, and the debt
        # stands; unheld, the next dispatch asks the developer again, and
        # only that fresh report is published and settled.
        for name, reply, readings in UNPAID:
            with self.subTest(name):
                self.rebased()
                verified = _fix_world.verified(
                    _support.PR, self.opening_report.location.comment_id, _published_reports.DELIVERED_REPORT,
                )
                self.held_unpaid(verified if reply is None else reply, **readings)
                self.lifts_the_control()
                self.dispatched(REPORTED)[RUN_AGENT].assert_called_once()
                self.assertEqual(self.published(), [FRESH])


class MovedWhileHeldTest(unittest.TestCase, _held.HeldRefreshes):
    """A held capture the issue moved past is retired, or held where nothing can be read, and never published."""

    def test_a_moved_prerequisite_retires_it(self) -> None:
        # The report answers a debt, publication, head, or requirements the
        # issue no longer has, so the capture is retired with its invocation
        # kept and nothing recorded, published, charged, or parked.
        for name, edits, reading in MOVED:
            with self.subTest(name):
                self.rebased()
                held = self.held_refresh()
                self.unheld(**self._moves(edits, reading))
                self.assert_retired(held)

    def test_an_unread_prerequisite_holds_it(self) -> None:
        # Nothing proves the capture stale, so it is kept with nothing
        # written or settled; once the reading returns, the next dispatch
        # finishes it once with no developer run.
        for name, edits, reading in UNREAD:
            with self.subTest(name):
                self.rebased()
                held = self.held_refresh()
                self._moves(edits, {})
                self._unheld_over(reading)
                self._moves({field: held[field] for field in edits}, {})
                self.dispatched()[RUN_AGENT].assert_not_called()
                self.assert_finished(self.kept(held))

    def _moves(self, edits: dict, reading: dict) -> dict:
        """Rewrite `edits` on the pinned comment, push or edit the issue where `reading` says; the readings left."""
        if edits:
            _fixes.CapturedFixTicks.hand_edit(self, **edits)
        if reading.get(PUSHED):
            self.pull_request.head.sha = reading[PUSHED]
        if reading.get(EDITED):
            _drift_world.edits(self, reading[EDITED])
        return {name: read for name, read in reading.items() if name not in _MOVES}

    def _unheld_over(self, reading: dict) -> None:
        """Take the control off and dispatch once over `reading`: nothing is written or published."""
        before = self.standing()
        with self._unanswered(reading):
            self.unheld(**self._moves({}, reading))
        self.assert_held(before)

    def _unanswered(self, reading: dict):
        """GitHub leaving every read of the pull request unanswered, where `reading` asks it to; else nothing."""
        if reading.get(UNREADABLE_PR):
            return patch.object(self.github, "get_pr", side_effect=ConnectionError("GitHub did not answer"))
        return contextlib.nullcontext()


class LostHandoffTest(unittest.TestCase, _held.HeldRefreshes):
    """A process or an answer lost at the recovery's handoff is finished by a later dispatch, nothing paid twice."""

    def test_a_lost_handoff_is_finished_once(self) -> None:
        # Lost before the handoff, the capture still holds the report and the
        # next dispatch finishes it; lost once it landed, or with its answer
        # lost, the delivery owns it and the report hold settles it. Either
        # way the report is published once, nobody is run until it settles,
        # and then the reviewer alone.
        for lost, quiet in LOST:
            with self.subTest(lost=lost):
                self.rebased()
                held = self.held_refresh()
                self.lifts_the_control()
                with _crashes.losing_the_handoff(self, lost):
                    self.dispatched()
                for _ in range(quiet):
                    self.dispatched()[RUN_AGENT].assert_not_called()
                self.reviewed_next()
                self.assertEqual(self.published(), [FRESH])
                self.assertEqual(self.exits_since(held), 1)

    def test_a_control_at_the_transfer_holds_it(self) -> None:
        # An operator holds the issue again as the strict editor sending the
        # transfer's edit walks to the comment, under either control: nothing
        # is sent, settled, or published. Once that control comes off too, the
        # next dispatch finishes it once.
        for control in CONTROLS:
            with self.subTest(control=control):
                self.rebased()
                held = self.held_refresh(control=control)
                self.lifts_the_control()
                before = self.standing()
                transfer = _drifts.HeldAtTheWalk(self.github, self.issue, control, _handoff.transfer)
                with patch.object(_handoff, "transfer", transfer):
                    self.dispatched()
                self.assertTrue(transfer.applied)
                self.assert_held(before)
                self.unheld()
                self.assert_finished(self.kept(held))


class HeldRefreshJourneyTest(_journey._SquashRebaseJourney, unittest.TestCase):
    """The base refresh rebases nothing over a captured refresh until its report has settled."""

    def test_an_advance_waits_for_the_captured_report(self) -> None:
        # The refresh of the rebased squash is held as it reports, and the
        # base advances: the pull request and the debt stay on the head the
        # report was written for. The recovery settles it, its reviewer is
        # handed it, and only then does the next advance rebase the branch.
        self.walks_into_review()
        self.base_refresh(_journey.REBASED)
        with patch.object(_guards, "_paused_during_agent_run", return_value=True):
            self.dispatched(_journey.refresh())
        held = (_journey.REBASED, self.pinned()[DEBT])
        self.base_refresh(_journey.ADVANCED)
        self.assertEqual(self._standing(), held)
        self.approved_into_review(_journey.REBASED)
        self.assertIn(f"> {_journey.REBASED_REPORT}", self.spawned(_journey.REVIEWER)[0])
        self.base_refresh(_journey.ADVANCED)
        self.assertEqual(self._standing()[0], _journey.ADVANCED)

    def _standing(self) -> tuple:
        """The head the pull request stands on, and the debt the comment claims."""
        return self.pull_request.head.sha, self.pinned()[DEBT]


if __name__ == "__main__":
    unittest.main()
