# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The fix a reviewer's change request handed its developer, captured as it returns and finished once.

The developer the request's handoff launches reports while an operator holds
the issue under `paused` or `backlog`. Its report is captured beside the run's
accounting and nothing else moves: the request stays handed, the round
unspent, the label on `workflow:fixing`, and the pull request where it stood.
Once the control comes off, the dispatcher's recovery finishes the round from
the capture with no developer or reviewer launched: the commit, or the report
alone on the head the pull request already carries, is published once, the
round spent once, the request retired in the commit that hands the report on,
and the issue handed back for a fresh review. A request another road moved
meanwhile retires the capture; one nobody can read, or a pull request nobody
can read, holds it. A process lost, or an answer lost, at the handoff is
finished by the next tick with nothing paid twice, and a report its round
parks without handing on is withdrawn so the reply that answers the park runs.
"""
from __future__ import annotations

import unittest
from itertools import product
from types import MappingProxyType
from unittest.mock import patch

from github import GithubException

from orchestrator import config
from orchestrator.workflow.engine import completion_routes as _routes
from orchestrator.workflow.stages.validating import fix_road as _fix_road
from orchestrator.workflow.state import WorkflowLabel
from tests.workflow import captured_fixes as _held, fix_reports as world, published_reports as _published_reports
from tests.workflow.fixtures import LABEL_FIXING, LABEL_VALIDATING, accounted

ISSUE = 2_429

PR = 24_290

# Every hold a round's developer may return under, by the control and by
# whether it committed or answered in its report alone.
_HOLDS = tuple(product((_held.PAUSED, _held.BACKLOG), (True, False)))

# The round settlement the request's report rides, frozen at its launch.
_SPENDS = ((_held.ROUND, 1), (_held.ANCHOR, None), ("fixing_round_settled", True))

# The moves another road makes while the issue is held, each as the one record
# it rewrites: the feedback anchor pointed at some other comment, and the
# request taken off.
_MOVES = ((_held.ANCHOR, 4_242), (_held.VERDICT, None))

# Records spelled as nothing their own readers take: the anchor, the request,
# and the settled report the request was reviewed over.
_DAMAGES = (
    (_held.ANCHOR, "not a comment id"),
    (_held.VERDICT, {"round": "not a round"}),
    (_held.CURRENT_REPORT, {"damaged": True}),
    (_held.CURRENT_REPORT, None),
)

# What the live round and a held one finished by the recovery each leave.
_SETTLED = (_held.ROUND, _held.VERDICT, _held.ANCHOR, "dev_session_id", "dev_resume_count", "user_content_hash")

# The park a spent run ledger stands on, and the reply that lifts it.
_PARK_REASON = "park_reason"
_RUN_LIMIT = "agent_run_limit"
_GRANT = "/orchestrator add-agent-runs 1"

# The issue's run ledger, capped at the runs the round spends -- its
# reviewer's and its developer's -- and the spent ledger's park as an operator
# records it while the recovery re-reads the reviewed report.
_RUN_CAP = "MAX_AGENT_RUNS_PER_ISSUE"
_RUNS_SPENT = 2
_RUN_LIMIT_PARK = MappingProxyType({_held.AWAITING: True, _PARK_REASON: _RUN_LIMIT})

# Why a capture a guarded decision ended was retired.
_REASON = "reason"
_INVALIDATED = "invalidated"

# The report another road settles over the one a held request was reviewed over.
_LATER_REPORT = "A later report supersedes the reviewed report."

# The verification evidence records a request's claim is judged over.
_CURRENT_EVIDENCE = "verification_evidence_current"
_EVIDENCE_HANDOFF = "verification_evidence_handoff"
_EVIDENCE_HISTORY = "verification_evidence_history"

# Each evidence record spelled as nothing its reader takes: `null` is damage
# for the handoff and the history, which no writer leaves so, and so is the
# handoff dropped from beside the current evidence its settlement wrote it with.
_DAMAGED_EVIDENCE = (
    (_CURRENT_EVIDENCE, {"damaged": True}),
    (_EVIDENCE_HANDOFF, {"damaged": True}),
    (_EVIDENCE_HANDOFF, None),
    (_EVIDENCE_HANDOFF, _held.OMITTED),
    (_EVIDENCE_HISTORY, None),
)
_REVISION_FLOOR = "verification_evidence_revision"

# The client's re-read of a report where it settled, which a case answers itself.
_REREAD = "reread_report_location"

# What an operator damages while the recovery re-reads the reviewed report:
# the settled report's handoff, spelled `null` or taken off, and -- beside a
# request claiming the evidence its reviewer's passing check published -- that
# evidence's handoff or current record.
_DAMAGED_REPORT = ((_held.REPORT_HANDOFF, None), (_held.REPORT_HANDOFF, _held.OMITTED))
_DAMAGED_CLAIM = ((_EVIDENCE_HANDOFF, None), (_CURRENT_EVIDENCE, "unreadable"))

# The report record a transfer would have handed the capture's report to.
_DELIVERED = "developer_report_delivery"

# The requirements a human writes while the recovery reads the reviewed report.
_EDITED_BODY = "New requirements landed during the subject read."

# What a pull request nobody could read answers.
_UNAVAILABLE = 502

# The two readings a round whose report has nowhere to go parks on: loose
# work in the checkout, and a remote that has moved past the head.
_NOWHERE = (
    MappingProxyType({"dirty_files": ("scratch.txt",)}),
    MappingProxyType({world.AHEAD_BEHIND: (0, 1)}),
)


class HeldFixTest(unittest.TestCase, _held.CapturedFixTicks):
    """A held round's report is captured, waited through, and finished once with no developer run."""

    def test_each_hold_is_finished_once(self) -> None:
        # Under either control, a round that committed and one that answered
        # in its report alone: held, nothing but the capture and the run's
        # accounting moves, and two held polls write nothing; unheld, the
        # recovery publishes the report -- beside the commit, or onto the
        # head the pull request already carries, replacing the report it
        # carried -- spends the round once, retires the request, and hands
        # the issue back, with no agent run and the feedback posted once.
        for control, committed in _HOLDS:
            with self.subTest(control=control, committed=committed):
                self.seeded(ISSUE, PR, LABEL_VALIDATING)
                self.held_fix(world.reported(), control, committed=committed)
                held = self.pinned()
                self._held(held, committed=committed)
                self.held_ticks()
                self.unheld(**_held.READING[committed])
                self._finished(held, committed=committed)

    def test_a_recovery_settles_as_the_live_round(self) -> None:
        # The same round, its return held and recovered, settles the same
        # round, request, anchor, session, and requirements as one whose own
        # tick disposed of it -- a resumed conversation charged one resume.
        settled = []
        for held in (False, True):
            self.seeded(ISSUE, PR, LABEL_VALIDATING)
            if held:
                self.held_fix(world.reported())
                self.unheld(**_held.COMMITTED)
            else:
                self.requested_fix(world.reported(), issue_worktree=_held.CHECKOUT)
            pinned = self.pinned()
            settled.append(tuple(map(pinned.get, _SETTLED)))
            self.assertEqual(_held.stage_of(pinned), _held.HANDED_OFF)
        self.assertEqual(settled[0], settled[1])

    def test_a_report_alone_is_reviewed_afresh(self) -> None:
        # A report answering the reviewer in words alone replaces the one the
        # pull request carried on the same head, so the next validating tick
        # runs a fresh reviewer over it rather than carrying any verdict on.
        self.seeded(ISSUE, PR, LABEL_VALIDATING)
        self.held_fix(world.reported(), committed=False)
        self.unheld(**_held.UNMOVED)

        reviewed = self.reviewed()

        reviewed[_held.RUN_AGENT].assert_called_once()
        self.assertEqual(self.pinned()["review_subject"]["report_revision"], 2)

    def test_a_run_limit_park_holds_until_a_grant(self) -> None:
        # A spent run ledger's park stands beside the held capture: the hold
        # it is answered by keeps the capture and the park as they are, and
        # recovers nothing. An operator's grant lifts it, and the recovery
        # behind finishes the round with no developer launched and no run
        # charged against the allowance the grant widened.
        self.seeded(ISSUE, PR, LABEL_VALIDATING)
        self.held_fix(world.reported())
        ledger = self.ledger()
        self.hand_edit(**{_held.AWAITING: True, _PARK_REASON: _RUN_LIMIT})
        self.unheld(**_held.COMMITTED)
        parked = self.pinned()
        self.assertEqual(
            (
                _held.stage_of(parked),
                parked[_held.AWAITING],
                parked[_PARK_REASON],
                self.reports(),
            ),
            (_held.PENDING, True, _RUN_LIMIT, 0),
        )
        world.replied(self, _GRANT)

        self.dispatched(**_held.COMMITTED)[_held.RUN_AGENT].assert_not_called()

        granted = self.pinned()
        self.assertEqual(
            (
                _held.stage_of(granted),
                granted[_held.ROUND],
                self.reports(),
                self.ledger(),
            ),
            (_held.HANDED_OFF, 1, 1, ledger),
        )

    def test_the_stage_holds_beside_the_capture(self) -> None:
        # The fixing stage's own road, reached over a capture nothing has
        # decided -- as a dispatch never reaches it -- neither drops the
        # request as a launch that may have run nor launches its developer
        # again: it holds with nothing written.
        self.seeded(ISSUE, PR, LABEL_VALIDATING)
        self.held_fix(world.reported())
        self.lifts_the_control()
        before = (self.pinned(), self.github.write_state_calls)

        handled = self.parked_resume(world.reported(), issue_worktree=_held.CHECKOUT, **_held.COMMITTED)

        handled[_held.RUN_AGENT].assert_not_called()
        self.assertEqual((self.pinned(), self.github.write_state_calls), before)

    def _held(self, held: dict, *, committed: bool) -> None:
        """`held` captured the run on the request's road, and moved nothing the round's disposition owns."""
        captured = _held.capture_of(held)
        handoff = captured.handoff
        self.assertEqual(
            (
                _held.stage_of(held),
                handoff.route,
                handoff.origin,
                handoff.spends,
                tuple(field for field, _digest in handoff.frozen),
                handoff.watermarks,
                handoff.requirements_revision,
                captured.run.resumed,
            ),
            (
                _held.PENDING,
                _routes.CompletionRoute.REQUESTED_CHANGES,
                WorkflowLabel.FIXING,
                _SPENDS,
                tuple(sorted(_fix_road.FROZEN)),
                (),
                held["user_content_hash"],
                world.DEV_SESSION,
            ),
        )
        self.assertEqual(
            (captured.run.before_sha, captured.run.source_sha),
            (world.PUBLISHED_HEAD, world.FIXED_HEAD if committed else world.PUBLISHED_HEAD),
        )
        self.assertEqual(
            (
                held[_held.VERDICT]["handed"] is not None,
                held[_held.ANCHOR],
                held[_held.ROUND],
                tuple(self.github.label_history),
                self.reports(),
                self.pull_request.head.sha,
                accounted(held),
                self.feedback_posts(),
            ),
            (
                True,
                held[_held.VERDICT]["anchor"],
                0,
                ((ISSUE, LABEL_FIXING),),
                0,
                world.PUBLISHED_HEAD,
                (2, 2),
                1,
            ),
        )
        self.ledger_held = self.ledger()

    def _finished(self, held: dict, *, committed: bool) -> None:
        """The recovery published the report once, spent the round once, and retired the request in its handoff."""
        recovered = self.pinned()
        head = world.FIXED_HEAD if committed else world.PUBLISHED_HEAD
        current = self.records()["current"]
        self.assertEqual(
            (
                _held.stage_of(recovered),
                _held.capture_of(recovered).invocation,
                recovered[_held.ROUND],
                recovered[_held.VERDICT],
                recovered[_held.ANCHOR],
            ),
            (_held.HANDED_OFF, _held.capture_of(held).invocation, 1, None, None),
        )
        self.assertEqual(
            (
                current.report_revision,
                current.subject.source_sha,
                self.reports(),
                self.pull_request.head.sha,
                self.github.label_history[-1],
                self.feedback_posts(),
            ),
            (2, head, 1, head, (ISSUE, LABEL_VALIDATING), 1),
        )
        self.assertEqual(accounted(recovered), (2, 2))
        self.assertEqual(self.ledger(), self.ledger_held)


class WithdrawnFixTest(unittest.TestCase, _held.CapturedFixTicks):
    """A report its round parks without handing on is withdrawn, so the reply that answers the park runs."""

    def test_a_report_with_nowhere_to_go_is_withdrawn(self) -> None:
        # A report alone over loose work, or over a head the remote has moved
        # past, parks with the report recorded nowhere: its capture is retired
        # ahead of the park, the request with it, and the reply that answers
        # the park launches the developer again rather than being held behind
        # a capture nothing would ever decide.
        for refused in _NOWHERE:
            with self.subTest(refused=dict(refused)):
                self.seeded(ISSUE, PR, LABEL_VALIDATING)
                self.requested_fix(world.reported(), committed=False, issue_worktree=_held.CHECKOUT, **refused)
                parked = self.pinned()
                self.assertEqual(
                    (
                        _held.stage_of(parked),
                        parked[_held.CAPTURED][_REASON],
                        parked[_held.AWAITING],
                        parked[_held.VERDICT],
                        self.reports(),
                    ),
                    (_held.RETIRED, _INVALIDATED, True, None, 0),
                )
                world.replied(self)

                resumed = self.parked_resume(world.reported(), committed=False, issue_worktree=_held.CHECKOUT)

                resumed[_held.RUN_AGENT].assert_called_once()


class UnreadHeadTest(unittest.TestCase, _held.CapturedFixTicks):
    """A report alone whose head proof met a reading that did not return keeps its capture for the reading again."""

    def test_an_unread_head_keeps_the_report(self) -> None:
        # A status nobody could take, a fetch that failed, or a divergence git
        # would not count proves nothing against the head -- on the live round
        # or on the recovery of a held one. The capture and the request stay,
        # nothing is recorded, parked, or spent, and the next dispatch, whose
        # readings return, publishes the report once with no developer run.
        for (described, unread), live in product(world.UNPROVED_HEADS, (True, False)):
            if described in world.HELD_READINGS:
                with self.subTest(reading=described, live=live):
                    self.seeded(ISSUE, PR, LABEL_VALIDATING)
                    self._unread(unread, live=live)
                    self._kept()
                    self.dispatched(**_held.UNMOVED)[_held.RUN_AGENT].assert_not_called()
                    finished = self.pinned()
                    self.assertEqual(
                        (
                            _held.stage_of(finished),
                            self.reports(),
                            finished[_held.ROUND],
                            finished[_held.VERDICT],
                        ),
                        (_held.HANDED_OFF, 1, 1, None),
                    )

    def _unread(self, unread: dict, *, live: bool) -> None:
        """The round's report alone meeting `unread`: on its own tick where `live`, else on its held one's recovery."""
        if live:
            self.requested_fix(world.reported(), committed=False, issue_worktree=_held.CHECKOUT, **unread)
            return
        self.held_fix(world.reported(), committed=False)
        self.unheld(**{**_held.UNMOVED, **unread})

    def _kept(self) -> None:
        """The capture still pending beside the request handed, with nothing recorded, parked, or spent."""
        kept = self.pinned()
        self.assertEqual(
            (
                _held.stage_of(kept),
                kept[_held.VERDICT]["handed"] is not None,
                bool(kept.get(_held.AWAITING)),
                set(self.records().values()),
                kept[_held.ROUND],
            ),
            (_held.PENDING, True, False, {None}, 0),
        )


class MovedRequestTest(unittest.TestCase, _held.CapturedFixTicks):
    """A held round whose request another road moved, or nobody can read, is retired or held -- never published."""

    def test_a_moved_request_retires_the_capture(self) -> None:
        # Another road points the feedback anchor at another comment, or
        # takes the request off: the capture answers a request that is no
        # longer this one, so it is retired, nothing is published or run, and
        # the move stands as that road wrote it.
        for field, moved in _MOVES:
            with self.subTest(field=field):
                self.seeded(ISSUE, PR, LABEL_VALIDATING)
                self.held_fix(world.reported())
                self.hand_edit(**{field: moved})
                self.unheld(**_held.COMMITTED)
                retired = self.pinned()
                self.assertEqual(
                    (
                        _held.stage_of(retired),
                        retired[_held.CAPTURED][_REASON],
                        retired[field],
                        self.reports(),
                        self.pull_request.head.sha,
                        retired[_held.ROUND],
                    ),
                    (_held.RETIRED, _INVALIDATED, moved, 0, world.PUBLISHED_HEAD, 0),
                )

    def test_an_unreadable_record_holds_the_capture(self) -> None:
        # A request, an anchor, or the settled report the request was
        # reviewed over, spelled as nothing its reader takes, proves nothing
        # about the capture, so the dispatch writes nothing and runs nothing,
        # and the capture waits.
        for field, damaged in _DAMAGES:
            with self.subTest(field=field, damaged=damaged):
                self.seeded(ISSUE, PR, LABEL_VALIDATING)
                self.held_fix(world.reported())
                self.hand_edit(**{field: damaged})
                self._holds()

    def test_a_superseded_report_retires_it(self) -> None:
        # Another road settles a later report on the pull request while the
        # issue is held: the request was reviewed over a report the pull
        # request no longer carries, so the capture is retired and the newer
        # report stands as settled, nothing of the run's published over it.
        self.seeded(ISSUE, PR, LABEL_VALIDATING)
        self.held_fix(world.reported(), committed=False)
        _published_reports.republishes_the_report(self.github, self.issue, text=_LATER_REPORT)
        self.unheld(**_held.UNMOVED)
        retired = self.pinned()
        self.assertEqual(
            (
                _held.stage_of(retired),
                retired[_held.CAPTURED][_REASON],
                self.records()["current"].report_revision,
                self.reports(),
            ),
            (_held.RETIRED, _INVALIDATED, 2, 0),
        )

    def test_an_unread_report_holds_it(self) -> None:
        # The report the request was reviewed over will not read where it
        # settled: nothing proves the request stale, so the capture is held
        # with nothing written, and the next dispatch, which reads it, finishes
        # the round once.
        self.seeded(ISSUE, PR, LABEL_VALIDATING)
        self.held_fix(world.reported())
        reviewed = _held.ReadAt(self, self.opening_report.location)
        with patch.object(self.github, _REREAD, side_effect=reviewed):
            self._holds()
        self.dispatched(**_held.COMMITTED)[_held.RUN_AGENT].assert_not_called()
        finished = _held.stage_of(self.pinned())
        self.assertEqual((finished, self.reports()), (_held.HANDED_OFF, 1))

    def test_a_disagreeing_pair_holds_until_repaired(self) -> None:
        # The settled report and its handoff no longer agree -- either one a
        # revision past the other, or taken off from beside it -- once the
        # control comes off. One settlement writes the two together, so the
        # pair is damage rather than a report settled since over the one
        # reviewed: over a round that committed and one that answered in its
        # report alone, the capture is held with nothing written. Repaired,
        # the next dispatch finishes the round once with no developer run --
        # one round, one report revision, one accounted exit, and the
        # feedback posted once.
        for (field, moved), committed in product(_held.DISAGREEING, (True, False)):
            with self.subTest(field=field, moved=moved, committed=committed):
                self.seeded(ISSUE, PR, LABEL_VALIDATING)
                self.held_fix(world.reported(), committed=committed)
                settled = self.unsettles(field, moved)
                self._holds(committed=committed)
                self.hand_edit(**{field: settled})
                self.unheld(**_held.READING[committed])
                finished = self.pinned()
                self.assertEqual(
                    (
                        _held.stage_of(finished),
                        finished[_held.ROUND],
                        finished[_held.CURRENT_REPORT][_held.REVISION],
                        self.reports(),
                        self.feedback_posts(),
                        accounted(finished),
                    ),
                    (_held.HANDED_OFF, 1, 2, 1, 1, (2, 2)),
                )

    def test_an_unread_pull_request_holds_it(self) -> None:
        # The pull request will not read on the first dispatch behind the
        # hold: held with nothing written. It reads on the next, which
        # finishes the round once.
        self.seeded(ISSUE, PR, LABEL_VALIDATING)
        self.held_fix(world.reported())
        unreadable = GithubException(_UNAVAILABLE, "bad gateway", None)
        with patch.object(self.github, "get_pr", side_effect=unreadable):
            self._holds()
        self.dispatched(**_held.COMMITTED)[_held.RUN_AGENT].assert_not_called()
        finished = self.pinned()
        self.assertEqual(
            (_held.stage_of(finished), self.reports(), finished[_held.ROUND]),
            (_held.HANDED_OFF, 1, 1),
        )

    def _holds(self, *, committed: bool = True) -> None:
        """Take the control off and dispatch: nothing written, nothing run, the capture still pending."""
        before = (self.pinned(), self.github.write_state_calls)
        held = self.unheld(**_held.READING[committed])
        held[_held.PUSH_BRANCH].assert_not_called()
        self.assertEqual((self.pinned(), self.github.write_state_calls), before)
        self.assertEqual(_held.stage_of(self.pinned()), _held.PENDING)


class SubjectReadTest(unittest.TestCase, _held.CapturedFixTicks):
    """What the recovery reads of the reviewed subject is read again behind, and damage there holds."""

    def test_a_control_during_the_read_holds_it(self) -> None:
        # An operator applies either control while the recovery re-reads the
        # report the request was reviewed over: the issue is fetched again
        # behind that read, so nothing is written -- the capture pending, the
        # request handed, no round spent -- and once the control comes off
        # the next dispatch finishes the round once.
        for control in (_held.PAUSED, _held.BACKLOG):
            with self.subTest(control=control):
                self.seeded(ISSUE, PR, LABEL_VALIDATING)
                self.held_fix(world.reported(), committed=False)
                before = self.pinned()
                during = _held.ReadAt(self, self.opening_report.location, control=control)
                with patch.object(self.github, _REREAD, side_effect=during):
                    self.unheld(**_held.UNMOVED)
                self.assertEqual(self.pinned(), before)
                self.control = control
                self.unheld(**_held.UNMOVED)
                finished = _held.stage_of(self.pinned())
                self.assertEqual((finished, self.reports()), (_held.HANDED_OFF, 1))

    def test_damaged_evidence_holds_it(self) -> None:
        # The request claims the evidence its reviewer's passing check
        # published. Any of its records spelled as nothing its reader takes --
        # the current evidence, or the handoff or the history beside a claim
        # that still reads as settled, `null` where no writer leaves one
        # included, and the handoff gone from beside the current evidence it
        # was settled with -- is no proof of anything: the capture is held
        # with nothing written.
        for damaged, spelled in _DAMAGED_EVIDENCE:
            with self.subTest(damaged=damaged, spelled=spelled):
                self.seeded(ISSUE, PR, LABEL_VALIDATING)
                self.held_verified_fix()
                self.assertIsNotNone(self.pinned()[_held.VERDICT]["evidence"])
                self.hand_edit(**{damaged: spelled})
                before = self.pinned()
                self.unheld(**_held.UNMOVED)
                self.assertEqual(self.pinned(), before)

    def test_an_edit_during_the_read_holds_it(self) -> None:
        # The issue is edited while the recovery re-reads the report the
        # request was reviewed over: the issue read again behind that read no
        # longer asks for what the run was handed, so nothing is written, the
        # capture pending and the request handed.
        self.seeded(ISSUE, PR, LABEL_VALIDATING)
        self.held_fix(world.reported(), committed=False)
        before = self.pinned()
        during = _held.ReadAt(self, self.opening_report.location, edit=_EDITED_BODY)
        with patch.object(self.github, _REREAD, side_effect=during):
            self.unheld(**_held.UNMOVED)
        self.assertEqual(self.pinned(), before)

    def test_a_push_during_the_read_holds_it(self) -> None:
        # Somebody pushes onto the pull request while the recovery re-reads
        # the report the request was reviewed over, the checkout still a
        # commit ahead of the new head. The pull request read again behind
        # that read no longer stands on the head the admission read, so
        # nothing is pushed or written -- the capture pending, the request
        # handed, no round spent -- whether the run committed or answered in
        # its report alone, and the next dispatch decides on the new head.
        for committed in (False, True):
            with self.subTest(committed=committed):
                self.seeded(ISSUE, PR, LABEL_VALIDATING)
                self.held_fix(world.reported(), committed=committed)
                before = self.pinned()
                during = _held.ReadAt(self, self.opening_report.location, push=True)
                with patch.object(self.github, _REREAD, side_effect=during):
                    recovered = self.unheld(**_held.READING[committed])
                recovered[_held.PUSH_BRANCH].assert_not_called()
                self.assertEqual((self.pinned(), self.reports()), (before, 0))

    def test_a_push_holds_a_superseded_request(self) -> None:
        # The request claims evidence a later revision superseded, which
        # would retire the capture, but somebody pushes onto the pull request
        # while the recovery re-reads the reviewed report: no retirement is
        # decided against a head the pull request no longer stands on, and
        # the capture waits with nothing written.
        self.seeded(ISSUE, PR, LABEL_VALIDATING)
        self.held_verified_fix()
        self.hand_edit(**{_REVISION_FLOOR: self.pinned()[_REVISION_FLOOR] + 1})
        before = self.pinned()
        during = _held.ReadAt(self, self.opening_report.location, push=True)
        with patch.object(self.github, _REREAD, side_effect=during):
            self.unheld(**_held.UNMOVED)
        self.assertEqual(self.pinned(), before)

    def test_superseded_evidence_retires_it(self) -> None:
        # A later evidence revision spent over the one the request claims is
        # proof: the request is one nobody is asking about any more, and the
        # capture is retired with nothing published.
        self.seeded(ISSUE, PR, LABEL_VALIDATING)
        self.held_verified_fix()
        self.hand_edit(**{_REVISION_FLOOR: self.pinned()[_REVISION_FLOOR] + 1})
        self.unheld(**_held.UNMOVED)
        retired = self.pinned()
        self.assertEqual(
            (_held.stage_of(retired), retired[_held.CAPTURED][_REASON], self.reports()),
            (_held.RETIRED, _INVALIDATED, 0),
        )


class SubjectDamageTest(unittest.TestCase, _held.CapturedFixTicks):
    """A subject damaged while the recovery reads it holds the capture through its transfer, finished once repaired."""

    def test_a_damaged_report_holds_it(self) -> None:
        # An operator damages the settled report's handoff -- spelled `null`,
        # or taken off -- while the recovery re-reads the report the request
        # was reviewed over. The round's report is recorded decided on the
        # request's subject as the recovery read it, so its transfer finds
        # that subject moved and lands nothing, whether the run committed or
        # answered in its report alone. Repaired, the next dispatch finishes
        # the round once, the feedback posted once.
        for (field, spelled), committed in product(_DAMAGED_REPORT, (False, True)):
            with self.subTest(field=field, spelled=spelled, committed=committed):
                self.seeded(ISSUE, PR, LABEL_VALIDATING)
                self.held_fix(world.reported(), committed=committed)
                self._damaged_during_the_read(field, spelled, _held.READING[committed])
                finished = self.pinned()
                self.assertEqual(
                    (
                        _held.stage_of(finished),
                        finished[_held.ROUND],
                        self.reports(),
                        self.feedback_posts(),
                    ),
                    (_held.HANDED_OFF, 1, 1, 1),
                )

    def test_a_damaged_claim_holds_it(self) -> None:
        # The request claims the evidence its reviewer's passing check
        # published, and an operator damages that evidence's handoff or its
        # current record while the recovery re-reads the reviewed report: the
        # transfer finds the claim moved and lands nothing. Repaired, the next
        # dispatch finishes the round once.
        for field, spelled in _DAMAGED_CLAIM:
            with self.subTest(field=field, spelled=spelled):
                self.seeded(ISSUE, PR, LABEL_VALIDATING)
                self.held_verified_fix()
                self._damaged_during_the_read(field, spelled, _held.UNMOVED)
                finished = self.pinned()
                self.assertEqual(
                    (_held.stage_of(finished), finished[_held.ROUND], self.reports()),
                    (_held.HANDED_OFF, 1, 1),
                )

    def test_a_run_limit_park_holds_it(self) -> None:
        # The round's developer spent the issue's last run, and an operator
        # records the spent ledger's park while the recovery re-reads the
        # reviewed report. The round's report is recorded decided on the
        # park's flags as the recovery read them, so the park stands: the
        # capture pending, nothing published, pushed, or spent, and only the
        # operator's write on the comment. The grant that lifts the park lets
        # the next dispatch finish the round once, with no developer run.
        for committed in (False, True):
            with self.subTest(committed=committed), patch.object(config, _RUN_CAP, _RUNS_SPENT):
                self.seeded(ISSUE, PR, LABEL_VALIDATING)
                self.held_fix(world.reported(), committed=committed)
                self.assertEqual(self.ledger()[0], _RUNS_SPENT)
                writes = self.github.write_state_calls
                during = _held.ReadAt(self, self.opening_report.location, damage=_RUN_LIMIT_PARK)
                with patch.object(self.github, _REREAD, side_effect=during):
                    self.unheld(**_held.READING[committed])[_held.PUSH_BRANCH].assert_not_called()
                parked = self.pinned()
                self.assertEqual(
                    (
                        _held.stage_of(parked),
                        parked[_PARK_REASON],
                        parked[_held.ROUND],
                        self.reports(),
                        self.github.write_state_calls,
                    ),
                    (_held.PENDING, _RUN_LIMIT, 0, 0, writes + 1),
                )
                world.replied(self, _GRANT)
                self.dispatched(**_held.READING[committed])[_held.RUN_AGENT].assert_not_called()
                granted = self.pinned()
                self.assertEqual(
                    (_held.stage_of(granted), granted[_held.ROUND], self.reports()),
                    (_held.HANDED_OFF, 1, 1),
                )

    def _damaged_during_the_read(self, field: str, spelled, reading) -> None:
        """`field` damaged as `spelled` during the reviewed report's re-read holds the capture; then it is repaired.

        Held, nothing is written but the damage: the capture pending, the
        request handed, no report delivered, no round spent, nothing pushed,
        and the issue left on `workflow:fixing`.
        """
        settled = self.pinned()[field]
        writes = self.github.write_state_calls
        during = _held.ReadAt(self, self.opening_report.location, damage={field: spelled})
        with patch.object(self.github, _REREAD, side_effect=during):
            self.unheld(**reading)[_held.PUSH_BRANCH].assert_not_called()
        held = self.pinned()
        self.assertEqual(
            (
                _held.stage_of(held),
                held[_held.VERDICT]["handed"] is not None,
                held.get(_DELIVERED),
                held[_held.ROUND],
                self.reports(),
                self.github.label_history[-1],
                self.github.write_state_calls,
            ),
            (_held.PENDING, True, None, 0, 0, (ISSUE, LABEL_FIXING), writes + 1),
        )
        self.hand_edit(**{field: settled})
        self.unheld(**reading)


class LostHandoffTest(unittest.TestCase, _held.CapturedFixTicks):
    """A process or an answer lost at the handoff is finished by the next tick, nothing paid twice."""

    def test_a_live_round_lost_at_its_handoff(self) -> None:
        # The live round's process is lost as the report's handoff goes out
        # -- the request still handed beside its pending capture -- or right
        # after it landed, the request retired with it and the commit not yet
        # pushed; or the handoff lands with its answer lost, the tick held.
        # The next dispatch finishes the round either way -- from the capture,
        # or from the delivery the handoff left -- with no developer or
        # reviewer run, one report, and one round.
        for lost in (_held.SENT, _held.LANDED, _held.ANSWER):
            with self.subTest(lost=lost):
                self.seeded(ISSUE, PR, LABEL_VALIDATING)
                self._lost_at_the_handoff(lost, self._live_round)
                left = self.pinned()
                handed = lost != _held.SENT
                self.assertEqual(
                    (_held.stage_of(left), left[_held.VERDICT] is None, self.reports()),
                    (_held.HANDED_OFF if handed else _held.PENDING, handed, 0),
                )
                self._finished_once(handed=handed)

    def test_a_held_round_lost_at_its_handoff(self) -> None:
        # The same losses in the recovery of a held round: whichever the
        # dispatch behind it finds, it finishes the round once.
        for lost in (_held.SENT, _held.LANDED, _held.ANSWER):
            with self.subTest(lost=lost):
                self.seeded(ISSUE, PR, LABEL_VALIDATING)
                self.held_fix(world.reported())
                self._lost_at_the_handoff(lost, self._recovery)
                self._finished_once(handed=lost != _held.SENT)

    def _lost_at_the_handoff(self, lost: str, ticked) -> None:
        """Run `ticked` with the process, or the answer, lost at the edit handing the capture off."""
        with patch.object(self.github, "edit_pinned_state", _held.LostAtTheHandoff(self.github, lost)):
            try:
                ticked()
            except SystemExit:
                self.assertNotEqual(lost, _held.ANSWER)

    def _live_round(self) -> None:
        """The direct round, its developer reporting with nothing holding the issue."""
        self.requested_fix(world.reported(), issue_worktree=_held.CHECKOUT)

    def _recovery(self) -> None:
        """The dispatch recovering a held round, the control taken off."""
        self.unheld(**_held.COMMITTED)

    def _finished_once(self, *, handed: bool) -> None:
        """The next dispatch runs no agent and leaves one report, one round, the request retired, the issue handed back.

        A handoff that landed leaves its commit unpushed, one ahead of the
        pull request, for the fixing stage's report recovery to publish; one
        that never went out leaves the capture for the dispatcher's recovery.
        """
        finishing = self.dispatched(**(_held.STRANDED if handed else _held.COMMITTED))
        finishing[_held.RUN_AGENT].assert_not_called()
        pinned = self.pinned()
        self.assertEqual(
            (
                _held.stage_of(pinned),
                pinned[_held.VERDICT],
                pinned[_held.ROUND],
                self.reports(),
                self.records()["current"].report_revision,
                self.pull_request.head.sha,
                self.github.label_history[-1],
                accounted(pinned),
            ),
            (
                _held.HANDED_OFF,
                None,
                1,
                1,
                2,
                world.FIXED_HEAD,
                (ISSUE, LABEL_VALIDATING),
                (2, 2),
            ),
        )


if __name__ == "__main__":
    unittest.main()
