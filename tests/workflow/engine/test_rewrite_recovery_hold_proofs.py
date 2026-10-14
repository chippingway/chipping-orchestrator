# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Settled evidence the finish holds, continues, or parks the attempt over, proved ready before it does.

Every finish held to the dormant settled-evidence policy (`settled_finish_support`):
issue #7's run settled and its finish killed at a final handoff boundary.
Something the run rests on then moves beside whatever keeps the next finish
from routing, and the finish proves the run first, so the movement
invalidates it whole -- revision and binding kept, the run made once -- and
putting it back revives nothing: an out-of-step handoff; an unfinishable
typed landing (its base count, remote, publication, or pull request); a
continuation over a base advanced without changing a tree, proved before and
behind its announcement, and one held beside an unreadable pending record --
the base advance itself excused; and the finish's own debt park, its notice
raising or its record refused over report 3, which abandons a captured run.
"""
from __future__ import annotations

import unittest
from dataclasses import replace
from functools import partial
from unittest.mock import patch

from orchestrator.git.base_sync.rewrite_handoffs import _PushOutcome, _RewriteRefusal
from orchestrator.git.publication.probes import _BranchDivergence
from orchestrator.git.ref_transport import _RefRead
from orchestrator.workflow.engine import (
    rewrite_finish_writes as _writes,
    verification_records as _records,
    verification_settlement_state as _settlement,
)
from orchestrator.workflow.engine.rewrite_finish_models import FinishOutcome, FinishRoad
from tests.workflow.engine import (
    rewrite_finish_git_support as git_support,
    rewrite_finish_moves as finish_moves,
    rewrite_finish_readings as readings,
    rewrite_handoff_test_support as handoff,
    rewrite_verification_recovery_support as support,
    settled_finish_support as settled,
    verification_report_fixture as _report,
)
from tests.workflow.interleaving import _RacesPastTheCall, _RacesPastTheStep

_EDITED_BODY = "Also cover a base that moved twice."

# A pending record no reader can take a transaction from.
_UNREADABLE = "unreadable"

# The report and review records report 3's settlement moves, as the pinned comment spells them.
_MOVED_RECORDS = (
    "developer_report_current",
    "developer_report_handoff",
    "review_subject",
    "review_returned_subject",
)

_QUIET = "--quiet"

# Room on the pinned comment for the run's history entry and the park behind
# it, and short of the landing's report debt and the announcement it rides.
_SHORT_OF_THE_DEBT = 250

# How a continuing tick goes: whether the issue is edited before it, what is
# done to the issue while its notice is posted -- edited, or put back between
# the proof before the continuation and the one behind its announcement --
# and the boundary the tick is killed at, if any.
_CONTINUING = (
    (True, None, None),
    (True, None, handoff.BEFORE_THE_RETIREMENT),
    (False, "edits", None),
    (True, "restores", None),
)

# The issue reads of a recovery's proof of the run: the refresh's own is the
# first, the proof's first reading the second, and its last word's the third.
_THE_LAST_WORDS_READING = 3


def _settles_a_later_report(case: support.CapturedRunCase, head: str, replaced: list) -> None:
    """Settle and review report 3 of `head` as another road would, keeping in `replaced` the records it moves."""
    pinned = readings.pinned(case)
    replaced.append({key: pinned.get(key) for key in _MOVED_RECORDS})
    case.state = case.gh.read_pinned_state(case.issue)
    _report.settles_report(case, 3, "Implemented the change and covered a base that moved twice.", head=head)
    case.gh.write_pinned_state(case.issue, case.state)


def _candidate_with(landed, part: str, **fields):
    """`landed` with `fields` replaced on the candidate's `part` -- its checkout, or its attempt."""
    candidate = landed.candidate
    altered = replace(getattr(candidate, part), **fields)
    return replace(landed, candidate=replace(candidate, **{part: altered}))


# Each typed landing the pinned record does not account for, as the finish is
# handed it: a base count nobody could take, a remote nobody could read, a
# publication a guard refused, and an attempt made for another pull request.
_UNFINISHABLE = (
    ("its base count", partial(_candidate_with, part="checkout", base=_BranchDivergence())),
    ("its remote", partial(replace, remote=_RefRead(sha=None, detail="unreachable"))),
    ("its publication", partial(replace, outcome=_PushOutcome.REFUSED, refusal=_RewriteRefusal.MOVED_REMOTE)),
    ("its pull request", partial(_candidate_with, part="attempt", pr_number=git_support.PR_NUMBER + 1)),
)


def _loses_the_answer(moves) -> None:
    """Make `moves`, then lose the answer of the request it was made behind."""
    moves()
    raise RuntimeError("the answer was lost")


class _HoldCase(settled.SettledRunCase):
    """Issue #7's settled run, its finish killed, and what the attempt and the run read back as."""

    def settles_then_dies(self, boundary: handoff.Boundary = handoff.BEFORE_THE_ANNOUNCEMENT) -> str:
        """Land a reviewed rebase and settle its run, its finish killed at `boundary`; the head, the run kept."""
        head = self.lands_a_reviewed_rebase()
        handoff.dies_at(self.gh, boundary, partial(self.finishes, head))
        self.settled = readings.pinned_records(self)[1]
        return head

    def writes_beside(self, key: str, record, body: str) -> tuple:
        """Write `record` as `key` and `body` as the issue's; the record and body they replaced."""
        state = self.gh.read_pinned_state(self.issue)
        replaced = (key, state.get(key), self.issue.body)
        state.set(key, record)
        self.gh.write_pinned_state(self.issue, state)
        self.issue.body = body
        return replaced

    def advances_without_change(self) -> None:
        """Move the base past the head by a file added and removed again, so a rebase onto it changes no tree."""
        work = self._work
        self._git("checkout", _QUIET, "main", cwd=work)
        for step in ("add", "remove"):
            if step == "add":
                (work / "transient.txt").write_text("a file the base keeps for a moment\n")
                self._git("add", "transient.txt", cwd=work)
            else:
                self._git("rm", _QUIET, "transient.txt", cwd=work)
            message = f"base {step}s a transient file"
            self._git("commit", _QUIET, "-m", message, cwd=work, env_extra=self._author_env)
        self._git("push", _QUIET, "origin", "main", cwd=work)

    def assert_invalidated(self, *, standing: str | None, pushed: int = 0) -> None:
        """The settled run invalidated whole, the attempt on `standing`, the run made once, `pushed` pushes."""
        settled = self.settled
        retired = (*git_support.invalidated(self), (settled.receipt, readings.INVALIDATED))
        self.assertEqual(readings.pinned_records(self), (None, None, retired))
        entry = _settlement.read_evidence_history(self.gh.read_pinned_state(self.issue))[-1]
        self.assertEqual((entry.revision, entry.binding), (settled.revision, settled.binding))
        self.assertEqual(readings.pinned(self)[readings.KEY_PENDING_PUSH], standing)
        made = (self.runs(), self.pushes.call_count, self.developer.call_count)
        self.assertEqual(made, (1, pushed, 0))

    def assert_routed_once(self, head: str) -> None:
        """`head` filed as `base_rebased`, announced, and relabelled once."""
        noticed = len(readings.notices(self))
        said = (support.announced(self), noticed, readings.relabels(self))
        self.assertEqual(said, ([head], 1, readings.ROUTED))


class HoldProofTest(_HoldCase, unittest.TestCase):
    """A recovery keeping the attempt over settled evidence proves it first, so restoring what moved revives nothing."""

    def test_holds_out_of_step_behind_the_proof(self) -> None:
        # The handoff stops naming the settled run and the issue is edited
        # under it: the run is invalidated before the route is held over that
        # handoff, so putting both back routes the head with nothing current.
        for boundary in handoff.BOUNDARIES:
            with self.subTest(boundary=boundary.name):
                self.setUp()
                head = self.settles_then_dies(boundary)
                kept = self.writes_beside(_records.EVIDENCE_HANDOFF, None, _EDITED_BODY)

                self.recovers()
                self.assert_invalidated(standing=self.anchor)
                self.writes_beside(*kept)
                self.recovers()

                self.assert_invalidated(standing=None)
                self.assert_routed_once(head)

    def test_an_unfinishable_landing_proves_first(self) -> None:
        # The finish is handed a landing the record does not account for, and
        # the issue was edited: it finishes nothing, the run invalidated
        # before the attempt is kept, and with the issue back the landing as
        # it reads routes the head with nothing current.
        for unaccounted, alters in _UNFINISHABLE:
            with self.subTest(unaccounted=unaccounted):
                self.setUp()
                head = self.settles_then_dies()
                written = self.issue.body
                self.issue.body = _EDITED_BODY

                finished = self.finishes(head, FinishRoad.RECOVERY, alters)

                self.assertEqual(finished, FinishOutcome.UNFINISHABLE)
                self.assert_invalidated(standing=self.anchor)
                self.issue.body = written
                self.assertEqual(self.finishes(head, FinishRoad.RECOVERY), FinishOutcome.ROUTED)
                self.assert_invalidated(standing=None)
                self.assert_routed_once(head)


class ContinuationProofTest(_HoldCase, unittest.TestCase):
    """A continuation proves the run it keeps for the rebase behind it, the base advance alone excused."""

    def test_a_continuation_proves_the_run(self) -> None:
        # The base advances past the head without changing a tree, and the
        # issue is edited before the continuing tick or while its notice is
        # posted: the run is invalidated before the attempt is retired -- by
        # the proof before the continuation, or the one behind its
        # announcement -- so the issue put back while the notice is posted,
        # right behind the retirement, or after a tick killed before it leaves
        # the rebase behind it nothing to carry.
        for before, at_notice, boundary in _CONTINUING:
            with self.subTest(before=before, at_notice=at_notice, boundary=getattr(boundary, "name", None)):
                self.setUp()
                self.settles_then_dies()
                self.advances_without_change()
                written = self.issue.body
                self._continues_edited(written, before=before, at_notice=at_notice, boundary=boundary)

                self.issue.body = written
                self.recovers()

                self.assert_invalidated(standing=None, pushed=1)

    def test_a_held_continuation_proves_the_run_first(self) -> None:
        # The base advances past the head again beside a pending record nobody
        # can read: the continuation is held, the run kept for the rebase
        # behind it where only the base moved, and invalidated first where the
        # issue was edited -- before the tick, or between the proof's two
        # readings of it; with all put back the head is continued to another
        # rebase with nothing of the run current.
        for edited in ("never", "before the tick", "between the proof's readings"):
            with self.subTest(edited=edited):
                self.setUp()
                self.settles_then_dies()
                support.advances_the_base_again(self)
                kept = self.writes_beside(_records.PENDING_EVIDENCE, _UNREADABLE, self.issue.body)
                self._holds_edited(edited)

                expected = self.settled if edited == "never" else None
                self.assertEqual(readings.pinned_records(self)[1], expected)
                self.assertEqual(readings.pinned(self)[readings.KEY_PENDING_PUSH], self.anchor)
                self.writes_beside(*kept)
                for _ in range(2):
                    self.recovers()

                self.assert_invalidated(standing=None, pushed=1)

    def _continues_edited(self, written: str, *, before: bool, at_notice: str | None, boundary) -> None:
        """Recover once, killed at `boundary`, the issue edited `before` the tick and as `at_notice` says.

        The issue is put back as `written` right behind the retirement too,
        ahead of the rebase the same tick makes behind the continuation.
        """
        edits = partial(setattr, self.issue, "body", _EDITED_BODY)
        restores = partial(setattr, self.issue, "body", written)
        if before:
            edits()
        noticing = self.gh.pr_comment
        if at_notice:
            noticing = _RacesPastTheCall(noticing, 1, edits if at_notice == "edits" else restores)
        retiring = handoff.BEFORE_THE_RETIREMENT.moving(self.gh.edit_pinned_state, restores)
        with (
            patch.object(self.gh, "pr_comment", noticing),
            patch.object(self.gh, "edit_pinned_state", retiring),
        ):
            handoff.dies_at(self.gh, boundary, self.recovers)

    def _holds_edited(self, edited: str) -> None:
        """Recover once with the issue edited as `edited` names, the body left edited behind the tick."""
        edits = partial(setattr, self.issue, "body", _EDITED_BODY)
        if edited == "before the tick":
            edits()
        reads = self.gh.get_issue
        if edited == "between the proof's readings":
            reads = _RacesPastTheCall(self.gh.get_issue, _THE_LAST_WORDS_READING, edits)
        written = self.issue.body
        with patch.object(self.gh, "get_issue", reads):
            self.recovers()
        self.issue.body = written if edited == "never" else self.issue.body


class ParkNoticeProofTest(_HoldCase, unittest.TestCase):
    """A park a report moved under while its notice was posted, raised or refused, proves the run before it stops."""

    def test_a_debt_park_notice_proves_the_run(self) -> None:
        # The comment has no room for the landing's report debt, and while
        # the debt park's notice is posted report 3 of the head is settled --
        # which refuses the park's record, decided on the report records, or
        # is followed by the post's answer lost: the run is invalidated before
        # the finish stops, so report 2 put back and room made route the head
        # with nothing current.
        for raises in (False, True):
            with self.subTest(raised=raises):
                self.setUp()
                head = self.settles_then_dies()
                finish_moves.fills_the_comment(self, _SHORT_OF_THE_DEBT)
                replaced = self._settles_under_the_notice(head, raises=raises)

                self.assert_invalidated(standing=self.anchor)
                self.assertFalse(readings.pinned(self).get("awaiting_human"))
                self._puts_back(replaced)
                finish_moves.makes_room(self)
                self.recovers()

                self.assert_invalidated(standing=None)
                self.assert_routed_once(head)

    def test_a_debt_park_abandons_a_captured_run(self) -> None:
        # The run was only captured: report 3 settled while the debt park's
        # notice is posted refuses the park's record -- report 2 put back
        # right behind that refusal -- or is followed by the post's answer
        # lost, and either way the run is abandoned whole before the finish
        # stops; room made, the head is routed with nothing current.
        for raises in (False, True):
            with self.subTest(raised=raises):
                self.setUp()
                head, captured = self.captures()
                finish_moves.fills_the_comment(self, _SHORT_OF_THE_DEBT)
                self._puts_back(self._settles_under_the_notice(head, raises=raises, restores=not raises))

                self.assert_abandoned(captured)
                finish_moves.makes_room(self)
                self.recovers()
                self.assert_abandoned(captured)
                self.assert_routed_once(head)

    def _settles_under_the_notice(self, head: str, *, raises: bool, restores: bool = False) -> dict:
        """Recover with report 3 of `head` settled as a notice posts, lost where `raises`, put back where `restores`."""
        replaced: list = []
        moves = partial(_settles_a_later_report, self, head, replaced)
        if raises:
            moves = partial(_loses_the_answer, moves)
        restored = _RacesPastTheStep(_writes.lands, partial(self._puts_back_once, replaced, restores))
        with (
            patch.object(self.gh, "comment", _RacesPastTheCall(self.gh.comment, 1, moves)),
            patch.object(_writes, "lands", restored),
        ):
            self.recovers()
        return replaced[0]

    def _puts_back_once(self, replaced: list, restores: bool) -> None:
        """Write back what report 3 moved, once it moved, where `restores`."""
        if restores and replaced and replaced[-1] is not None:
            self._puts_back(replaced[-1])
            replaced.append(None)

    def _puts_back(self, recorded: dict) -> None:
        """Write the report and review records back as `recorded` kept them, before report 3 moved them."""
        state = self.gh.read_pinned_state(self.issue)
        for key, kept in recorded.items():
            state.set(key, kept)
        self.gh.write_pinned_state(self.issue, state)


if __name__ == "__main__":
    unittest.main()
