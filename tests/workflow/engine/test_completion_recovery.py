# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What the dispatch does with a pending captured completion, ahead of the stage that would lose or repeat it.

Each case lands a capture through its own checkpoint, makes somebody else's
move, then dispatches the issue whole, with the stage handler stood in for,
and reads back what the dispatch reached and what the pinned comment carries.
An applicable capture is handed to its road's owner, admitted, and to nothing
else -- held where no road has an owner, as in this build; a stale one is
retired, keeping which invocation it was, and the tick ends behind it, the
stage running on the next one as it would without it; and an uncertain or
damaged one holds the stage with nothing written. What an effect stands on
is read again behind the issue's last fetch, in `test_completion_effect`.
"""
from __future__ import annotations

import unittest
from types import MappingProxyType

from orchestrator.git.worktrees.models import ProbeAnswer
from orchestrator.workflow.engine import (
    completion_prerequisites as _prerequisites,
    completion_records as _records,
    completion_recovery_models as _models,
    completion_routes as _routes,
)
from orchestrator.workflow.state import WorkflowLabel
from tests.workflow.engine import completion_dispatch_support as _dispatch, completion_recovery_support as _support
from tests.workflow.engine.completion_turn_support import Case, Turn

_NUMBER = _support.NUMBER
_Reason = _models.Reason
_Standing = _models.Standing
_RETIRED = (_records.CaptureStage.RETIRED, _records.RetirementReason.INVALIDATED)
_RETIRED_STAGE = _records.CaptureStage.RETIRED.value
_FIELD = _support.FIELD
_HANDLED = (_NUMBER,)

_DONE = (str(WorkflowLabel.DONE),)

_VALIDATING = Turn(labels=(str(WorkflowLabel.VALIDATING),))

_ON_VALIDATING = WorkflowLabel.VALIDATING

# A drift resume read on `validating`, a rewritten-head refresh, and a late revision.
_DRIFT = _support.road(_routes.CompletionRoute.REQUIREMENTS_DRIFT, _ON_VALIDATING)
_REFRESH = _support.road(_routes.CompletionRoute.REPORT_REFRESH, _ON_VALIDATING)
_REVISION = _support.road(_routes.CompletionRoute.LATE_REVISION, WorkflowLabel.DECOMPOSING)

_DEBT = "developer_report_rewrite_debt"

_RECEIPTS = "issue_usage_receipts"

_EARLIER = "0f0f0f0f0f0f0f0f0f0f0f0f0f0f0f0f0f0f0f0f"

# A pull request's state once closed.
_CLOSED = "closed"


def _debt_of(rewritten: str, **publication) -> MappingProxyType:
    """The pinned edit recording the report debt a rewrite onto `rewritten` left, on the pull request and branch pinned.

    `publication` names another `pr` or `branch` the debt is owed on.
    """
    owed = {"pr": _support.PR_NUMBER, "branch": _support.BRANCH, "previous_head": _EARLIER, "rewritten_head": rewritten}
    return MappingProxyType({_DEBT: {**owed, **publication}})


# The capture's run read back as accounted after all, its receipt on the ledger.
_RECEIPT = (_support.ORDINAL, _support.NONCE)
_RECEIPTED = MappingProxyType({_RECEIPTS: {"floor": 0, "recent": [list(_RECEIPT)]}})

# A capture whose run's usage checkpoint never confirmed.
_UNACCOUNTED = MappingProxyType({"accounting": "unresolved"})

# The recorded pull request merged, and the `discussion` plan it carried as
# the implementing road reads it -- the head it stands on, or one pushed past.
_MERGED = MappingProxyType({"state": _CLOSED, "merged": True})
_PLAN = MappingProxyType({"discussion_plan_sha": _support.BEFORE})
_PAST_THE_PLAN = MappingProxyType({"discussion_plan_sha": _EARLIER})

# A refresh's run, which started on the rewritten head and committed nothing,
# and the pull request standing on that same head.
_UNCOMMITTED = (("before_sha", _support.SOURCE),)
_ON_THE_SOURCE = MappingProxyType({"sha": _support.SOURCE})

# Each road whose records still stand, and the move that leaves them so: a
# drift on a pull-request stage beside its pull request, a refresh beside the
# debt of the head its run reported on and its pull request stands on, and an
# unaccounted run read back since.
_STANDING = MappingProxyType({
    "drift beside its pull request": Case(Turn(), None, pull_request=True, label=_ON_VALIDATING, road=_DRIFT),
    "refresh beside its debt": Case(
        Turn(edits=_debt_of(_support.SOURCE), pull_request=_ON_THE_SOURCE), None,
        pull_request=True, run=_UNCOMMITTED, label=_ON_VALIDATING, road=_REFRESH,
    ),
    "accounting read back": Case(Turn(members=_UNACCOUNTED, edits=_RECEIPTED), None),
    "implementation beside its merged plan": Case(
        Turn(edits=_PLAN, pull_request=_MERGED), None, pull_request=True,
    ),
})

# Another current-layout branch than the one the issue's record pins, and another pull request on the same head.
_OTHER_BRANCH = "orchestrator/chippingway__chipping-orchestrator/issue-1"
_OTHER_PR = _support.PR_NUMBER + 1

# Each proof that a capture no longer answers what the issue is.
_STALE = MappingProxyType({
    "closed": Case(Turn(closed=True), _Reason.ENDED),
    "done": Case(Turn(labels=_DONE), _Reason.ENDED),
    "relabelled": Case(_VALIDATING, _Reason.RELABELLED),
    "requirements moved": Case(Turn(comment="Also cover the edge case."), _Reason.REQUIREMENTS_MOVED),
    "branch moved": Case(Turn(), _Reason.BRANCH_MOVED, run=(("branch", _OTHER_BRANCH),)),
    "checkout moved": Case(Turn(head=_support.ELSEWHERE), _Reason.CHECKOUT_MOVED),
    "pull request closed": Case(
        Turn(pull_request=MappingProxyType({"state": _CLOSED})), _Reason.PULL_REQUEST_ENDED, pull_request=True,
    ),
    "pull request merged past its plan": Case(
        Turn(edits=_PAST_THE_PLAN, pull_request=_MERGED), _Reason.PULL_REQUEST_ENDED, pull_request=True,
    ),
    "pull request pushed over": Case(
        Turn(pull_request=MappingProxyType({"sha": _support.ELSEWHERE})), _Reason.PULL_REQUEST_MOVED,
        pull_request=True,
    ),
    "pull request gone": Case(
        Turn(edits=MappingProxyType({"pr_number": _support.DROPPED})), _Reason.PREREQUISITE_GONE,
        pull_request=True, label=_ON_VALIDATING, road=_DRIFT,
    ),
    "refresh owed nothing": Case(
        Turn(), _Reason.PREREQUISITE_GONE, pull_request=True, label=_ON_VALIDATING, road=_REFRESH,
    ),
    "refresh of another head": Case(
        Turn(edits=_debt_of(_support.ELSEWHERE), pull_request=_ON_THE_SOURCE), _Reason.PREREQUISITE_GONE,
        pull_request=True, run=_UNCOMMITTED, label=_ON_VALIDATING, road=_REFRESH,
    ),
    "refresh that committed past its rewritten head": Case(
        Turn(edits=_debt_of(_support.BEFORE)), _Reason.PREREQUISITE_GONE,
        pull_request=True, label=_ON_VALIDATING, road=_REFRESH,
    ),
    "refresh over a pull request off its reported head": Case(
        Turn(edits=_debt_of(_support.SOURCE)), _Reason.PULL_REQUEST_MOVED,
        pull_request=True, label=_ON_VALIDATING, road=_REFRESH,
    ),
    "refresh of another pull request's debt": Case(
        Turn(edits=_debt_of(_support.SOURCE, pr=_OTHER_PR), pull_request=_ON_THE_SOURCE), _Reason.PREREQUISITE_GONE,
        pull_request=True, run=_UNCOMMITTED, label=_ON_VALIDATING, road=_REFRESH,
    ),
    "refresh of another branch's debt": Case(
        Turn(edits=_debt_of(_support.SOURCE, branch=_OTHER_BRANCH), pull_request=_ON_THE_SOURCE),
        _Reason.PREREQUISITE_GONE, pull_request=True, run=_UNCOMMITTED, label=_ON_VALIDATING, road=_REFRESH,
    ),
    "refresh over a replacement pull request": Case(
        Turn(
            edits=MappingProxyType({**_debt_of(_support.SOURCE), "pr_number": _OTHER_PR}), pull_request=_ON_THE_SOURCE,
        ),
        _Reason.PREREQUISITE_GONE, pull_request=True, run=_UNCOMMITTED, label=_ON_VALIDATING, road=_REFRESH,
    ),
    "revision with no adjudication": Case(
        Turn(), _Reason.PREREQUISITE_GONE, label=WorkflowLabel.DECOMPOSING, road=_REVISION,
    ),
})

# An auto rebase's anchor, and one spelled `false` beside the pull request and
# stage its rewrite was begun on: only a null anchor is none.
_ANCHOR = "pending_auto_base_rebase_push_sha"
_FALSE_ANCHOR = MappingProxyType({
    _ANCHOR: False,
    "pending_auto_base_rebase_rewrite_pr": _support.PR_NUMBER,
    "pending_auto_base_rebase_rewrite_stage": str(WorkflowLabel.VALIDATING),
})

# Each reading nobody could take, or that nothing proves.
_UNREAD = MappingProxyType({
    "comment": Case(Turn(unanswered="read_pinned_state"), _Reason.RECORD_UNREAD),
    "issue": Case(Turn(unanswered="get_issue"), _Reason.ISSUE_UNREAD),
    "controls applied meanwhile": Case(
        Turn(refetched=(str(WorkflowLabel.IMPLEMENTING), "paused")), _Reason.ISSUE_UNREAD,
    ),
    "thread": Case(Turn(unanswered="comments_after"), _Reason.REQUIREMENTS_UNREAD),
    "branch refused": Case(Turn(edits=MappingProxyType({"branch": "orchestrator/issue-2427"})), _Reason.BRANCH_REFUSED),
    "pull request": Case(Turn(unanswered="get_pr"), _Reason.PULL_REQUEST_UNREAD, pull_request=True),
    "pull request head": Case(
        Turn(pull_request=MappingProxyType({"sha": None})), _Reason.PULL_REQUEST_UNREAD, pull_request=True,
    ),
    "checkout unreadable": Case(Turn(identity=ProbeAnswer.UNREADABLE), _Reason.CHECKOUT_UNPROVEN),
    "checkout not its own": Case(Turn(identity=ProbeAnswer.REFUTED), _Reason.CHECKOUT_UNPROVEN),
    "head unread": Case(Turn(head=""), _Reason.CHECKOUT_UNPROVEN),
    "checkout elsewhere": Case(Turn(), _Reason.CHECKOUT_UNPROVEN, run=(("worktree", "/elsewhere/issue-2427"),)),
    "refresh debt unreadable": Case(
        Turn(edits=MappingProxyType({_DEBT: "owed"})), _Reason.PREREQUISITE_UNREAD,
        pull_request=True, label=_ON_VALIDATING, road=_REFRESH,
    ),
    "accounting unresolved": Case(Turn(members=_UNACCOUNTED), _Reason.ACCOUNTING_UNRESOLVED),
    "anchor unreadable": Case(Turn(edits=MappingProxyType({_ANCHOR: "not-a-commit"})), _Reason.ANCHOR_UNREAD),
    "anchor spelled empty": Case(Turn(edits=MappingProxyType({_ANCHOR: ""})), _Reason.ANCHOR_UNREAD),
    "anchor spelled false beside its terms": Case(
        Turn(edits=_FALSE_ANCHOR), _Reason.ANCHOR_UNREAD,
        pull_request=True, label=_ON_VALIDATING, road=_DRIFT,
    ),
    "accounting beside a damaged counter": Case(
        Turn(members=_UNACCOUNTED, edits=MappingProxyType({**_RECEIPTED, "issue_total_tokens": "many"})),
        _Reason.ACCOUNTING_UNRESOLVED,
    ),
})

# Each claim nothing may act on or clear: a capture that will not read, one
# of another comment, and a cycle the record has left or that will not read.
_DAMAGED = MappingProxyType({
    "null": Case(Turn(edits=MappingProxyType({_support.FIELD: None})), _Reason.DAMAGED),
    "a string": Case(Turn(edits=MappingProxyType({_support.FIELD: "pending"})), _Reason.DAMAGED),
    "a member missing": Case(Turn(members=MappingProxyType({"source": _support.DROPPED})), _Reason.DAMAGED),
    "another comment": Case(Turn(members=MappingProxyType({"comment": 999_999})), _Reason.NOT_THIS_RECORD),
    "another cycle": Case(Turn(edits=MappingProxyType({"late_cycle_id": 5})), _Reason.NOT_THIS_RECORD),
    "an unreadable cycle": Case(Turn(edits=MappingProxyType({"late_cycle_id": "five"})), _Reason.DAMAGED),
})


def _beside(record: dict) -> dict:
    """Every field a record carries beside its capture."""
    return {key: kept for key, kept in record.items() if key != _FIELD}


def _stage(record: dict) -> str:
    """The stage the capture a record carries stands at."""
    return record[_support.FIELD]["stage"]


class ApplicableCaptureTest(unittest.TestCase):
    """A capture every reading still admits goes to its road's owner, and nowhere else."""

    def test_its_road_owner_is_handed_it(self) -> None:
        # Handed the capture, the issue read afresh, the label, and the head
        # the pull request stood on, the owner answers for the tick: stopping
        # it holds the handler, carrying on reaches it. Admission itself
        # writes nothing, charges no run, and clears no park.
        for stops, pull_request in ((True, False), (False, True)):
            with self.subTest(stops=stops, pull_request=pull_request):
                world = _support.CapturedWorld(pull_request=pull_request)
                captured = world.captured()

                seen = _dispatch.observed(world, _dispatch.RoadOwner(stops=stops))

                self._admitted(seen.handed, captured, _support.BEFORE if pull_request else None)
                self.assertEqual(seen.ran, () if stops else _HANDLED)
                self.assertTrue(seen.untouched)

    def test_its_road_standing_hands_it_on(self) -> None:
        # Each road's own records still standing -- its pull request, the debt
        # a refresh answers, and the receipt of an unaccounted run -- admit it.
        for name, case in _STANDING.items():
            with self.subTest(name):
                world = _support.CapturedWorld(case.label, pull_request=case.pull_request)
                captured = world.captured(case.road)

                seen = _dispatch.observed(world, _dispatch.RoadOwner(), case.turn)

                self.assertEqual([admitted.capture.invocation for admitted in seen.handed], [captured.invocation])

    def test_a_road_no_owner_takes_holds_it(self) -> None:
        # A rewritten-head refresh's road has no owner in this build, beside
        # its debt and its pull request as they stand: nothing finishes the
        # capture, so nothing may run the work again over it -- every tick
        # holds, and none writes.
        refresh = _STANDING["refresh beside its debt"]
        world = _support.CapturedWorld(refresh.label, pull_request=refresh.pull_request)
        world.captured(refresh.road)
        for tick, turn in (("first", refresh.turn), ("second", None)):
            with self.subTest(tick=tick):
                seen = _dispatch.observed(world, turn=turn)
                self.assertEqual(seen.ran, ())
                self.assertTrue(seen.untouched)
                self.assertEqual(_stage(seen.after), _records.CaptureStage.PENDING)

    def _admitted(self, handed: tuple, captured: _records.CompletionCapture, head: str | None) -> None:
        """`handed` is the one admitted handoff of `captured`, on the issue read afresh, at `head`."""
        self.assertEqual(len(handed), 1)
        admitted = handed[0]
        self.assertEqual(admitted.capture, captured)
        self.assertEqual((admitted.issue.number, admitted.label), (_NUMBER, WorkflowLabel.IMPLEMENTING))
        self.assertEqual(admitted.pull_request_head, head)


class StaleCaptureTest(unittest.TestCase):
    """A capture a reading proved stale is retired, and the tick ends behind it, for the stage to run on the next."""

    def test_each_proof_of_staleness_retires_it(self) -> None:
        for name, case in _STALE.items():
            with self.subTest(name):
                world = _support.CapturedWorld(case.label, pull_request=case.pull_request)
                captured = world.captured(case.road, **dict(case.run))

                seen = _dispatch.observed(world, _dispatch.RoadOwner(), case.turn)

                self.assertTrue(seen.says(case.reason), seen.said)
                self._retired(seen, captured)

    def test_an_unlanded_retirement_holds_it(self) -> None:
        # Refused, the capture stands and the next dispatch decides afresh,
        # retiring it and ending its own tick; never confirmed, the next
        # dispatch reads what landed and runs the stage, retiring nothing
        # twice.
        for failure, retired_by_then in (("refused", False), ("lost", True)):
            with self.subTest(failure=failure):
                self._retried(failure, retired_by_then=retired_by_then)

    def _retried(self, failure: str, *, retired_by_then: bool) -> None:
        """A retirement `failure` keeps from landing holds the dispatch, and the one after it settles the capture."""
        world = _support.CapturedWorld()
        world.captured()
        failing = getattr(world.github.pinned_failures, failure)
        failing.add(_NUMBER)

        held = _dispatch.observed(world, turn=_VALIDATING)

        failing.discard(_NUMBER)
        self.assertEqual(held.ran, ())
        self.assertEqual(_stage(held.after) == _RETIRED_STAGE, retired_by_then)
        again = _dispatch.observed(world)
        self.assertEqual(again.writes, 0 if retired_by_then else 1)
        settled = again if retired_by_then else _dispatch.observed(world)
        self.assertEqual((settled.ran, _stage(settled.after)), (_HANDLED, _RETIRED_STAGE))

    def _retired(self, seen: _dispatch.Observed, captured: _records.CompletionCapture) -> None:
        """`captured` was retired as invalidated, nothing else moved, and the tick ended behind it."""
        retired = _support.read_capture(seen.after)
        self.assertEqual((retired.stage, retired.reason), _RETIRED)
        self.assertEqual(retired.invocation, captured.invocation)
        self.assertEqual(_beside(seen.after), _beside(seen.before), "the invalidation owns the capture alone")
        self.assertEqual((seen.ran, seen.handed), ((), ()))


class UndecidedCaptureTest(unittest.TestCase):
    """A capture nothing can decide on holds the stage, and nothing is written over it."""

    def test_an_unread_world_holds_it(self) -> None:
        for name, case in _UNREAD.items():
            with self.subTest(name):
                self._held(case, _Standing.UNCERTAIN)

    def test_a_damaged_capture_is_held(self) -> None:
        for name, case in _DAMAGED.items():
            with self.subTest(name):
                self._held(case, _Standing.DAMAGED)

    def test_an_unreadable_pr_number_holds_it(self) -> None:
        # Asked of the road itself: a whole dispatch reads the pinned number
        # in its anchor guard ahead of the recovery, which a spelling no
        # number reads as stops first.
        world = _support.CapturedWorld(pull_request=True)
        captured = world.captured()
        world.hand_edit(pr_number="seventy-seven")

        refused = _prerequisites.road_refusal(world.github.read_pinned_state(world.issue), captured)

        self.assertEqual(refused, _models.Decision(_Standing.UNCERTAIN, _Reason.PREREQUISITE_UNREAD))

    def _held(self, case: Case, standing: _Standing) -> None:
        """`case`'s move holds the dispatch under `standing`, with nothing handed on, run, or written."""
        world = _support.CapturedWorld(case.label, pull_request=case.pull_request)
        world.captured(case.road, **dict(case.run))

        seen = _dispatch.observed(world, _dispatch.RoadOwner(), case.turn)

        self.assertTrue(seen.says(case.reason, standing), seen.said)
        self.assertEqual((seen.ran, seen.handed), ((), ()))
        self.assertTrue(seen.untouched)


if __name__ == "__main__":
    unittest.main()
