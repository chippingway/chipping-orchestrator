# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Settled evidence a direct finish holds, continues, or parks the attempt over, proved ready before it does.

Direct finishes of the recovery's road held to the dormant settled-evidence
policy (`settled_route_support`): issue #7's run settled and its finish
killed at a final handoff boundary. Something the run rests on then moves
beside whatever keeps the next finish from routing, and the finish proves the
run first, so the movement invalidates it whole -- revision and binding kept,
the run made once -- and putting it back revives nothing: an out-of-step
handoff; an unfinishable typed landing (its base count, remote, publication,
or pull request); a continuation over a base advanced without changing a
tree, proved before and behind its announcement, and one held beside an
unreadable pending record -- the base advance itself excused; a newer
transaction recorded right behind that proof's invalidation, left owed as
written beside an unfinishable landing; and the
finish's own debt park, its notice raising or its record refused over report
3, which abandons a captured run.
"""
from __future__ import annotations

import unittest
from dataclasses import replace
from functools import partial
from unittest.mock import patch

from orchestrator.git.base_sync.rewrite_handoffs import _PushOutcome, _RewriteRefusal
from orchestrator.git.publication.probes import _BranchDivergence
from orchestrator.git.ref_transport import _RefRead
from orchestrator.workflow.engine import verification_records as _records
from orchestrator.workflow.engine.rewrite_finish_models import FinishOutcome
from tests.workflow.engine import (
    held_run_support as held,
    rewrite_finish_git_support as git_support,
    rewrite_finish_moves as finish_moves,
    rewrite_finish_readings as readings,
    rewrite_handoff_test_support as handoff,
    rewrite_verification_recovery_support as support,
    settled_finish_support as settled,
)
from tests.workflow.interleaving import _RacesPastTheCall

# A pending record no reader can take a transaction from.
_UNREADABLE = "unreadable"

# How a continuing finish goes: whether the issue is edited before it, what is
# done to the issue while its notice is posted -- edited, or put back between
# the proof before the continuation and the one behind its announcement --
# and the boundary the finish is killed at, if any.
_CONTINUING = (
    (True, None, None),
    (True, None, handoff.BEFORE_THE_RETIREMENT),
    (False, "edits", None),
    (True, "restores", None),
)

# The issue reads of a direct finish's proof of the run: its first reading,
# and its last word's.
_THE_LAST_WORDS_READING = 2

# When a held continuation's issue is edited: never, before the finish, or
# between the proof's two readings of it.
_NEVER = "never"
_EDITS = (_NEVER, "before the finish", "between the proof's readings")


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


# The edit invalidating settled evidence over the comment read afresh, behind
# which another road records a newer transaction for the head.
_BEHIND_THE_INVALIDATION = handoff.Boundary(
    "behind the invalidation", "edit_pinned_state",
    lambda _issue, state, *, over, **_options: bool(over.get(_records.CURRENT_EVIDENCE))
    and state.get(_records.CURRENT_EVIDENCE) is None,
)


class HoldProofTest(held.HoldCase, unittest.TestCase):
    """A finish keeping the attempt over settled evidence proves it first, so restoring what moved revives nothing."""

    def test_holds_out_of_step_behind_the_proof(self) -> None:
        # The handoff stops naming the settled run and the issue is edited
        # under it: the run is invalidated before the route is held over that
        # handoff, so putting both back routes the head with nothing current.
        for boundary in handoff.BOUNDARIES:
            with self.subTest(boundary=boundary.name):
                self.setUp()
                head = self.settles_then_dies(boundary)
                kept = self.writes_beside(_records.EVIDENCE_HANDOFF, None, held.EDITED_BODY)

                self.assertEqual(self.finalizes(head), FinishOutcome.HELD)
                self.assert_invalidated(standing=self.anchor)
                self.writes_beside(*kept)
                self.assertEqual(self.finalizes(head), FinishOutcome.ROUTED)

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
                self.issue.body = held.EDITED_BODY

                self.assertEqual(self.finalizes(head, alters=alters), FinishOutcome.UNFINISHABLE)

                self.assert_invalidated(standing=self.anchor)
                self.issue.body = written
                self.assertEqual(self.finalizes(head), FinishOutcome.ROUTED)
                self.assert_invalidated(standing=None)
                self.assert_routed_once(head)


    def test_a_successor_behind_the_proof_is_kept(self) -> None:
        # The finish is handed a landing nothing accounts for over an edited
        # issue, and another road records a newer transaction for the head
        # right behind the invalidation its proof lands: that transaction
        # stands owed exactly as written beside the run invalidated whole,
        # with nothing proved, abandoned, or posted over it.
        head = self.settles_then_dies()
        self.issue.body = held.EDITED_BODY
        newer: list = []
        moving = _BEHIND_THE_INVALIDATION.moving(self.gh.edit_pinned_state, partial(self._records_beside, newer))
        unread = _UNFINISHABLE[1][1]
        with patch.object(self.gh, "edit_pinned_state", moving):
            self.assertEqual(self.finalizes(head, alters=unread), FinishOutcome.UNFINISHABLE)

        self.assert_retired_whole(self.settled, pending=newer[0])
        self.assertEqual(self.posted(newer[0]), [])
        self.assert_made()

    def _records_beside(self, newer: list) -> None:
        """Record a newer transaction for the head as another road would, over the run's binding; kept in `newer`."""
        newer.append(settled.records_a_newer_run(self, binding=self.settled.binding))


class ContinuationProofTest(held.HoldCase, unittest.TestCase):
    """A continuation proves the run it keeps for the rebase behind it, the base advance alone excused."""

    def test_a_continuation_proves_the_run(self) -> None:
        # The base advances past the head without changing a tree, and the
        # issue is edited before the continuing finish or while its notice is
        # posted: the run is invalidated before the attempt is retired -- by
        # the proof before the continuation, or the one behind its
        # announcement -- so the issue put back while the notice is posted,
        # right behind the retirement, or after a finish killed before it
        # leaves the rebase behind it nothing to carry.
        for before, at_notice, boundary in _CONTINUING:
            with self.subTest(before=before, at_notice=at_notice, boundary=getattr(boundary, "name", None)):
                self.setUp()
                head = self.settles_then_dies()
                self.advances_without_change()
                written = self.issue.body
                self._continues_edited(head, written, before=before, at_notice=at_notice, boundary=boundary)

                self.issue.body = written
                if boundary is not None:
                    self.assertEqual(self.finalizes(head), FinishOutcome.CONTINUED)

                self.assert_invalidated(standing=None)
                self.assert_continued(head)

    def test_a_held_continuation_proves_the_run_first(self) -> None:
        # The base advances past the head again beside a pending record nobody
        # can read: the continuation is held, the run kept for the rebase
        # behind it where only the base moved, and invalidated first where the
        # issue was edited -- before the finish, or between the proof's two
        # readings of it; with all put back the head is continued with
        # nothing of the run current.
        for edited in _EDITS:
            with self.subTest(edited=edited):
                self.setUp()
                head = self.settles_then_dies()
                support.advances_the_base_again(self)
                self._git("fetch", held.QUIET, "origin", cwd=self._wt)
                kept = self.writes_beside(_records.PENDING_EVIDENCE, _UNREADABLE, self.issue.body)
                self._holds_edited(head, edited)

                expected = self.settled if edited == _NEVER else None
                self.assertEqual(readings.pinned_records(self)[1], expected)
                self.assertEqual(self.pinned_fields(readings.KEY_PENDING_PUSH), (self.anchor,))
                self.writes_beside(*kept)
                self.assertEqual(self.finalizes(head), FinishOutcome.CONTINUED)

                self._assert_continued_over(head, edited)

    def _assert_continued_over(self, head: str, edited: str) -> None:
        """`head` continued once, the run invalidated whole wherever the issue was `edited` -- never, kept."""
        if edited != _NEVER:
            self.assert_invalidated(standing=None)
        self.assert_continued(head)

    def _continues_edited(self, head: str, written: str, *, before: bool, at_notice: str | None, boundary) -> None:
        """Finish `head` once, killed at `boundary`, the issue edited `before` the finish and as `at_notice` says.

        The issue is put back as `written` right behind the retirement too,
        ahead of the rebase the caller makes behind the continuation.
        """
        edits = partial(setattr, self.issue, "body", held.EDITED_BODY)
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
            handoff.dies_at(self.gh, boundary, partial(self.finalizes, head))

    def _holds_edited(self, head: str, edited: str) -> None:
        """Finish `head` once, HELD, with the issue edited as `edited` names, the body left edited behind it."""
        edits = partial(setattr, self.issue, "body", held.EDITED_BODY)
        if edited == "before the finish":
            edits()
        reads = self.gh.get_issue
        if edited == "between the proof's readings":
            reads = _RacesPastTheCall(self.gh.get_issue, _THE_LAST_WORDS_READING, edits)
        written = self.issue.body
        with patch.object(self.gh, "get_issue", reads):
            self.assertEqual(self.finalizes(head), FinishOutcome.HELD)
        self.issue.body = written if edited == _NEVER else self.issue.body


class ParkNoticeProofTest(held.HoldCase, unittest.TestCase):
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
                finish_moves.fills_the_comment(self, held.SHORT_OF_THE_DEBT)
                replaced = self.settles_under_the_notice(head, raises=raises)

                self.assert_invalidated(standing=self.anchor)
                self.assertFalse(readings.pinned(self).get("awaiting_human"))
                self.puts_back_records(replaced)
                finish_moves.makes_room(self)
                self.assertEqual(self.finalizes(head), FinishOutcome.ROUTED)

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
                finish_moves.fills_the_comment(self, held.SHORT_OF_THE_DEBT)
                self.puts_back_records(self.settles_under_the_notice(head, raises=raises, restores=not raises))

                self.assert_abandoned(captured)
                finish_moves.makes_room(self)
                self.assertEqual(self.finalizes(head), FinishOutcome.ROUTED)
                self.assert_abandoned(captured)
                self.assert_routed_once(head)


if __name__ == "__main__":
    unittest.main()
