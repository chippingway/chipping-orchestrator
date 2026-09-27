# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A persisted verdict that may not be acted on, and the road it takes back to a reviewer.

A refused approval parks only while the subject it approved still stands: a
push since the verdict's write drops it for a fresh reviewer instead of
waiting on a human. Either park a verdict takes -- `reviewer_unverified` or
`reviewer_unrecorded` -- is answered by a bare `/orchestrator continue` with a
fresh reviewer and no developer, and the unrecorded park lands under the
ceiling GitHub enforces wherever the comment has room for a park at all. A
waiting verdict whose evidence can never settle is dropped rather than waited
on forever, while one whose subject merely would not read is held for the
next tick rather than dropped as stale.
"""
from __future__ import annotations

import unittest
from unittest.mock import patch

from orchestrator import config
from orchestrator.github.pinned_state import MAX_PINNED_BODY, pinned_state_body
from tests.workflow.fixtures import LABEL_DOCUMENTING, LABEL_FIXING, LABEL_VALIDATING, _agent
from tests.workflow.stages.validating import review_verdict_readings as _read, review_verdict_test_support as _world
from tests.workflow.stages.validating.validating_review_test_support import FIX_HEAD_SHAS

VERIFY = "_run_verify_commands"

AWAITING_HUMAN = "awaiting_human"

CONTINUE = "/orchestrator continue"

# A change request longer than most of what the pinned comment holds.
_LONG = "12 passed, 1 failed " * 1000

# Each park a returned verdict takes, what the reviewer returned to earn it,
# and the operator notes that leave the comment no room for that verdict.
_PARKS = (
    ("reviewer_unverified", "LGTM\n\nVERDICT: APPROVED", 0),
    ("reviewer_unrecorded", f"{_LONG}\n\nVERDICT: CHANGES_REQUESTED", MAX_PINNED_BODY - len(_LONG)),
)

# A configuration the recorded evidence was never run under.
_MOVED_CONFIGURATION = (_world.SUITE, "uv run ruff check")

UNRECORDED = "reviewer_unrecorded"

WRITE = "write_pinned_state"

UNDECLARED_REQUEST = f"{_world.REQUESTED}\n\nVERDICT: CHANGES_REQUESTED"

UNRECORDED_NOTICE = "could not be recorded on the pinned comment"

# How much room the comment has left once a change request too long to record
# returns: enough for the park over the comment as it stands, though not
# beside what the returned run staged -- or not even for that.
_ROOM_FOR_THE_PARK = (
    ("over the comment as it stands", 300, (UNRECORDED, True, 1)),
    ("nowhere", 40, (None, None, 0)),
)

# Each recheck behind which the pull request will not read once, the pinned
# write or post it follows, and the feedback posts the next tick leaves once
# it hands the request over.
_UNREADABLE_RECHECKS = (
    (
        "before the feedback post",
        (WRITE, lambda state: state.get(_world.RETURNED_VERDICT) is not None),
        1,
    ),
    ("behind the feedback post", ("pr_comment", lambda body: _read.FEEDBACK_NOTICE in body), 2),
)


def _notes(case, text: str) -> None:
    """Put `text` down as the operator's notes on `case`'s pinned comment."""
    state = case.github.read_pinned_state(case.issue)
    state.set("operator_notes", text)
    case.github.write_pinned_state(case.issue, state)


def _leaves_room(case, room: int) -> None:
    """Fill `case`'s pinned comment with operator notes until `room` characters are left under the ceiling."""
    _notes(case, "")
    bare = len(pinned_state_body(case.pinned()))
    _notes(case, "x" * (MAX_PINNED_BODY - bare - room))


def _unrecorded_notices(case) -> int:
    """How many notices of an unrecorded verdict `case`'s issue thread carries."""
    return sum(1 for _, body in case.github.posted_comments if UNRECORDED_NOTICE in body)


class _EnforcesTheCeiling:
    """Pinned-comment writes refused past the ceiling, as GitHub refuses them."""

    def __init__(self, github) -> None:
        self._write = github.write_pinned_state

    def __call__(self, issue, state):
        if len(pinned_state_body(state.data)) > MAX_PINNED_BODY:
            raise RuntimeError("the pinned comment is past what GitHub accepts")
        return self._write(issue, state)


class _PullReadFailsOnce:
    """A pull request read that fails once, the first time it is asked after `arm`."""

    def __init__(self, github) -> None:
        self._read = github.get_pr
        self._armed = False

    def __call__(self, pr_number):
        if self._armed:
            self._armed = False
            raise ConnectionError("the pull request could not be read")
        return self._read(pr_number)

    def arm(self, _case) -> None:
        """Fail the next read."""
        self._armed = True


def _undecided():
    """A reviewer run that decides nothing a case here asks about."""
    return _agent(session_id="rev-2", last_message="Reading.\n\nVERDICT: UNKNOWN")


class VerdictRecoveryTest(_world.ReviewVerdictWorld, unittest.TestCase):
    """Every road a verdict that may not be acted on takes leads to a fresh reviewer."""

    def test_a_moved_subject_drops_a_refused_approval(self) -> None:
        # The head moves behind the reused approval's write, so the evidence
        # no longer proves current -- but the approval is of a head nobody is
        # asking about, which a fresh reviewer answers without a reply.
        digest = _read.settles_evidence(self).content_revision
        behind = _world.AnotherRoadBehind(
            self,
            WRITE,
            lambda state: state.get(_world.RETURNED_VERDICT) is not None,
            _world.pushes,
        )

        ran = behind.returning(f"Covered.\n\nVERIFICATION: REUSED sha256:{digest}\n\nVERDICT: APPROVED")

        pinned = self.pinned()
        self.assertEqual(
            (
                bool(pinned.get(AWAITING_HUMAN)),
                pinned.get(_world.PARK_REASON),
                pinned[_world.RETURNED_VERDICT],
                ran[VERIFY].call_count,
                self.github.label_history,
            ),
            (False, None, None, 0, []),
        )

    def test_a_bare_continue_buys_a_fresh_reviewer(self) -> None:
        for reason, message, filled in _PARKS:
            with self.subTest(reason):
                self.setUp()
                _notes(self, "x" * filled)
                self.returns(message)
                self.assertEqual(self.pinned()[_world.PARK_REASON], reason)
                # The room the unrecorded park asks for, freed as it says.
                _notes(self, "")
                _world.replies(self, CONTINUE)

                ran = self.dispatched(_undecided())

                self.assertEqual(
                    (ran[_world.RUN_AGENT].call_count, _read.spawned_roles(self)),
                    (1, ("reviewer",)),
                )

    def test_a_lost_claim_drops_its_waiting_verdict(self) -> None:
        # The approval waits on its published evidence, and the configuration
        # moves before that evidence settles: it never can, so the verdict is
        # dropped and the next tick's reviewer reviews under what stands.
        self.github.report_failures.lost.add(_world.PR)
        self.returns(_world.declared_run())
        self.github.report_failures.lost.discard(_world.PR)
        self.assertIsNotNone(self.pinned()[_world.RETURNED_VERDICT])

        with patch.object(config, "VERIFY_COMMANDS", _MOVED_CONFIGURATION):
            dropped = self.dispatched()
            waiting = self.pinned()[_world.RETURNED_VERDICT]
            reviewed = self.dispatched(_undecided())

        self.assertEqual(
            (
                dropped[_world.RUN_AGENT].call_count,
                waiting,
                self.github.label_history,
                reviewed[_world.RUN_AGENT].call_count,
                _read.spawned_roles(self),
            ),
            (0, None, [], 1, ("reviewer",)),
        )

    def test_an_unrecorded_park_lands_where_it_fits(self) -> None:
        # The verdict has no room, nor its park beside what the returned run
        # staged: the park goes down over the comment as it stands rather
        # than a notice over a write GitHub refuses -- and where not even that
        # fits, nothing is posted that no park backs.
        for name, room, expected in _ROOM_FOR_THE_PARK:
            with self.subTest(name):
                self.setUp()
                _leaves_room(self, room)

                with patch.object(self.github, WRITE, _EnforcesTheCeiling(self.github)):
                    self.returns(f"{_LONG}\n\nVERDICT: CHANGES_REQUESTED")

                pinned = self.pinned()
                self.assertEqual(
                    (pinned.get(_world.PARK_REASON), pinned.get(AWAITING_HUMAN), _unrecorded_notices(self)),
                    expected,
                )

    def test_an_unread_recheck_holds_an_approval(self) -> None:
        # The pull request will not read once the evidence has settled: the
        # verdict is held rather than dropped as stale, and the next tick
        # finishes it without a reviewer.
        self._unread_behind(
            (WRITE, lambda state: state.get("verification_evidence_current") is not None),
            _world.declared_run(),
        )
        waiting = self.pinned()
        self.assertEqual(
            (
                waiting[_world.RETURNED_VERDICT]["verdict"],
                waiting.get(_world.PARK_REASON),
                self.github.label_history,
            ),
            ("approved", None, []),
        )

        finished = self.dispatched()

        self.assertEqual(
            (finished[_world.RUN_AGENT].call_count, self.github.label_history),
            (0, [(_world.ISSUE, LABEL_DOCUMENTING)]),
        )

    def test_an_unread_recheck_holds_a_request(self) -> None:
        # The pull request will not read once, at either recheck around the
        # feedback post: nothing is handed over or dropped, and the next tick
        # hands the request to its one developer.
        for name, behind, posts in _UNREADABLE_RECHECKS:
            with self.subTest(name):
                self.setUp()

                held = self._unread_behind(behind, UNDECLARED_REQUEST)

                self.assertEqual(
                    (held[_world.RUN_AGENT].call_count, self.pinned()[_world.RETURNED_VERDICT]["handed"]),
                    (0, None),
                )

                fixed = self.dispatched(_world.developer(), dirty_files=(), push_branch=True, head_shas=FIX_HEAD_SHAS)

                self.assertEqual(
                    (
                        fixed[_world.RUN_AGENT].call_count,
                        len(_read.feedback_posts(self)),
                        self.github.label_history,
                    ),
                    (1, posts, [(_world.ISSUE, LABEL_FIXING), (_world.ISSUE, LABEL_VALIDATING)]),
                )

    def _unread_behind(self, behind: tuple, message: str) -> dict:
        """The tick `message` returns in, over a pull request that will not read once behind `behind`'s request."""
        reads = _PullReadFailsOnce(self.github)
        with patch.object(self.github, "get_pr", reads):
            return _world.AnotherRoadBehind(self, *behind, reads.arm).returning(message)


if __name__ == "__main__":
    unittest.main()
