# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Tests for the delivered stretch of the issue thread, kept apart from the reply boundary."""

from __future__ import annotations

import unittest

from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    prompt_context as _prompt_context,
    prompt_delivery as _prompt_delivery,
    thread_delivery as _thread_delivery,
)
from tests.support.fakes import FakeComment, FakeGitHubClient, FakeUser, make_issue

DELIVERED_AFTER = "delivered_after_comment_id"
DELIVERED_THROUGH = "delivered_through_comment_id"
LAST_ACTION = "last_action_comment_id"
AUTHOR = "alice"
CUT_ID = 10
QUOTED_ID = 20
BOUNDARY = 50
CROSSED_ID = 45
READ_TO = 70
LATER_ID = 90
LONG_CONTEXT_CHARS = 3980
LONG_CONTEXT = "x" * LONG_CONTEXT_CHARS
CUT_BODY = "REQUIRED: keep the old column"
OUR_NOTICE = "<!--orchestrator-comment-->\nParked."
CUT_THREAD = ((CUT_ID, CUT_BODY), (QUOTED_ID, LONG_CONTEXT))
WHOLE_THREAD = ((CUT_ID, CUT_BODY), (QUOTED_ID, "short context"))
# A stretch a later prompt over the cut thread meets, and one it lies beyond a gap from.
MET_STRETCH = ((0, QUOTED_ID), (0, QUOTED_ID))
STRETCH_BEYOND_A_GAP = ((BOUNDARY, LATER_ID), (CUT_ID, QUOTED_ID))


def _recorded(after=None, through=None, boundary=None) -> PinnedState:
    """A record carrying the delivered stretch and the reply boundary, a None one absent."""
    named = zip((DELIVERED_AFTER, DELIVERED_THROUGH, LAST_ACTION), (after, through, boundary), strict=True)
    return PinnedState(state_data={field: recorded for field, recorded in named if recorded is not None})


def _thread(*comments) -> tuple:
    """A client over one issue carrying `comments`, given as (id, body) pairs."""
    issue = make_issue(1, comments=[
        FakeComment(id=comment_id, body=body, user=FakeUser(AUTHOR)) for comment_id, body in comments
    ])
    return FakeGitHubClient([issue]), issue


def _quoted_thread(thread: tuple) -> object:
    """The record of a prompt quoting `thread`, given as (id, body) pairs."""
    github, issue = _thread(*thread)
    return _prompt_context._delivered_thread(github, issue, PinnedState())


class DeliveredThreadTest(unittest.TestCase):
    """What the feedback readers count as handed to a developer."""

    def test_only_the_stretch_counts(self) -> None:
        delivered = _thread_delivery.DeliveredThread.read(_recorded(CUT_ID, BOUNDARY))
        asked = (CUT_ID - 1, CUT_ID, CUT_ID + 1, BOUNDARY, BOUNDARY + 1)

        covered = [delivered.covers(comment_id) for comment_id in asked]
        self.assertEqual(covered, [False, False, True, True, False])

    def test_a_missing_bound_counts_nothing(self) -> None:
        # No reader may take a field a record does not carry, one that is no
        # comment id as its writers spell it, or the reply boundary, as
        # feedback somebody answered.
        for recorded in (
            (0, None, BOUNDARY),
            (None, BOUNDARY),
            (True, BOUNDARY),
            ("0", BOUNDARY),
            (0, str(BOUNDARY)),
            (),
        ):
            with self.subTest(recorded=recorded):
                delivered = _thread_delivery.DeliveredThread.read(_recorded(*recorded))
                self.assertFalse(delivered.covers(CUT_ID + 1))


class RecordedDeliveryTest(unittest.TestCase):
    """A prompt over the whole thread records the stretch it quoted."""

    def test_the_stretch_runs_over_our_newest_post(self) -> None:
        # The pickup standing above the thread it quoted is nobody's input, so
        # the stretch reaches the boundary standing on it -- on a thread
        # carrying nothing but the pickup as well, which a later resume's
        # settlement then carries over the replies it hands over.
        for thread in (((CUT_ID, CUT_BODY), (QUOTED_ID, OUR_NOTICE)), ((QUOTED_ID, OUR_NOTICE),)):
            with self.subTest(thread=len(thread)):
                state = _recorded(boundary=QUOTED_ID)
                _thread_delivery.records_delivery(state, _quoted_thread(thread))
                self.assertEqual(_thread_delivery.DeliveredThread.read(state).recorded(), (0, QUOTED_ID))

    def test_the_stretch_is_what_the_prompt_quoted(self) -> None:
        for case, record, floor in (
            ("the bound cut the oldest", _quoted_thread(CUT_THREAD), CUT_ID),
            ("nothing was cut", _quoted_thread(WHOLE_THREAD), 0),
        ):
            with self.subTest(case=case):
                state = _recorded(boundary=BOUNDARY)
                _thread_delivery.records_delivery(state, record)
                self.assertEqual(_thread_delivery.DeliveredThread.read(state).recorded(), (floor, QUOTED_ID))

    def test_a_stretch_it_meets_is_kept(self) -> None:
        # A later prompt leaving more of the thread out takes nothing back from
        # one that quoted it; one beyond a gap replaces it, since one stretch
        # cannot leave the gap out. The stretch the prompt quoted, kept apart
        # from its record -- as a captured completion keeps it -- is recorded
        # exactly as the record itself is.
        cut = _quoted_thread(CUT_THREAD)
        self.assertEqual(_thread_delivery.DeliveredThread.quoted(cut).recorded(), (CUT_ID, QUOTED_ID))
        for prior, kept in (MET_STRETCH, STRETCH_BEYOND_A_GAP):
            for recorded in (cut, _thread_delivery.DeliveredThread.quoted(cut)):
                with self.subTest(prior=prior, kept_apart=recorded is not cut):
                    state = _recorded(*prior)
                    _thread_delivery.records_delivery(state, recorded)
                    self.assertEqual(_thread_delivery.DeliveredThread.read(state).recorded(), kept)


class ReadsThroughTest(unittest.TestCase):
    """A road moving the reply boundary carries the stretch only over nothing unread."""

    def test_a_reaching_stretch_follows_it(self) -> None:
        state = _recorded(0, BOUNDARY, BOUNDARY)
        _thread_delivery.reads_through(state, READ_TO)

        self.assertEqual(state.get(LAST_ACTION), READ_TO)
        self.assertEqual(state.get(DELIVERED_THROUGH), READ_TO)

    def test_a_stretch_never_falls(self) -> None:
        state = _recorded(0, LATER_ID, LATER_ID)
        _thread_delivery.reads_through(state, READ_TO)

        self.assertEqual(state.get(DELIVERED_THROUGH), LATER_ID)

    def test_no_stretch_moves_the_boundary_alone(self) -> None:
        state = _recorded(boundary=BOUNDARY)
        _thread_delivery.reads_through(state, READ_TO)

        self.assertEqual(state.get(LAST_ACTION), READ_TO)
        self.assertFalse(_thread_delivery.DeliveredThread.read(state).covers(READ_TO))

    def test_without_a_read_a_short_stretch_stays(self) -> None:
        state = _recorded(0, QUOTED_ID, BOUNDARY)
        _thread_delivery.reads_through(state, READ_TO)

        self.assertEqual(state.get(DELIVERED_THROUGH), QUOTED_ID)

    def test_a_settlement_moves_a_reaching_stretch(self) -> None:
        # A resume's settlement reads only past the boundary. Where the stretch
        # reaches it, both move over the reply the resume quoted; where a
        # park's stamp stood the boundary over comments the read never saw,
        # the boundary moves and the stretch stays below them.
        for boundary, through in ((QUOTED_ID, READ_TO), (BOUNDARY, QUOTED_ID)):
            with self.subTest(boundary=boundary):
                state = _recorded(0, QUOTED_ID, boundary)
                reply = FakeComment(id=READ_TO, body="go on", user=FakeUser(AUTHOR))
                _prompt_delivery.create_prompt_delivery_snapshot(issue_comments=[reply], state=state).settle(state)
                self.assertEqual(state.get(LAST_ACTION), READ_TO)
                self.assertEqual(state.get(DELIVERED_THROUGH), through)

    def test_a_carry_crosses_only_what_nobody_is_owed(self) -> None:
        # A road reading to 70 quoted the reply at 70 whole, over a boundary a
        # park stamped at 50. The stretch follows it only where the thread
        # between them, read again, is the quoted reply and nobody's input --
        # wherever the boundary stood, above it as much as below.
        for case, crossed, at, through in (
            ("a human reply below the boundary", "keep the old column", CROSSED_ID, QUOTED_ID),
            ("a human reply above the boundary", "keep the old column", READ_TO - 1, QUOTED_ID),
            ("our own post", OUR_NOTICE, CROSSED_ID, READ_TO),
            ("a bare run grant", "/orchestrator add-agent-runs 2", CROSSED_ID, READ_TO),
            ("a bare continue", "/orchestrator continue", CROSSED_ID, READ_TO),
            ("an authorization", "/orchestrator authorize-oversized abc123", CROSSED_ID, READ_TO),
        ):
            with self.subTest(case=case):
                self.assertEqual(self._carried_over(crossed, at).get(DELIVERED_THROUGH), through)

    def _carried_over(self, crossed: str, at: int) -> PinnedState:
        """The record a road quoting the reply at 70 leaves, `crossed` at `at` over a boundary stamped at 50."""
        stamped = [(QUOTED_ID, "a"), (BOUNDARY, OUR_NOTICE), (READ_TO, "go on")]
        stamped.append((at, crossed))
        github, issue = _thread(*sorted(stamped))
        state = _recorded(0, QUOTED_ID, BOUNDARY)
        delivered = _thread_delivery.DeliveredThread.read(state)
        delivered.carry(READ_TO, github, issue, state, frozenset((READ_TO,)))
        return state


class KnownThroughTest(unittest.TestCase):
    """What a snapshot taken in two reads proves complete."""

    def test_the_newest_known_id_bounds_it(self) -> None:
        first_read = [FakeComment(id=QUOTED_ID, body="a", user=FakeUser(AUTHOR))]

        self.assertEqual(_thread_delivery.known_through(first_read), QUOTED_ID)
        recorded = (BOUNDARY, None, "90", True)
        self.assertEqual(_thread_delivery.known_through(first_read, *recorded), BOUNDARY)
        self.assertIsNone(_thread_delivery.known_through([]))

    def test_a_reply_between_the_reads_caps_it(self) -> None:
        # The thread is read first and the pull request second; a reply that
        # landed on the thread in between is in neither read, so the bound
        # stays beneath it however far the pull request's read reached.
        self.assertEqual(self._bound_over(LATER_ID), LATER_ID)
        self.assertEqual(self._bound_over(LATER_ID, BOUNDARY), BOUNDARY - 1)
        # Under the first read's own bound, nothing is read again.
        self.assertEqual(self._bound_over(CUT_ID, BOUNDARY), QUOTED_ID)

    def _bound_over(self, pr_comment_id: int, *landed) -> int | None:
        """The bound of a thread read at 20 and a pull request read at `pr_comment_id`, `landed` in between."""
        github, issue = _thread((QUOTED_ID, "a"))
        thread = list(github.comments_after(issue, None))
        for found in landed:
            issue.comments.append(FakeComment(id=found, body="b"))
        conversation = [FakeComment(id=pr_comment_id, body="pr")]
        return _thread_delivery.known_through_both(github, issue, thread, conversation)


if __name__ == "__main__":
    unittest.main()
