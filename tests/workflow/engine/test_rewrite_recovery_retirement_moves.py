# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A captured run something moves under while its route is taken, abandoned before the retirement lands.

A finish recorded its run for the landed head and died at its relabel, and the
recovery proves that run again and takes the last word behind every request it
made -- and then, as the recovery relabels the issue, another road moves the
review subject the run is bound through, or the configured verification
command changes. The last word is asked once more behind the relabel, before
the write that retires the attempt lands: it reads the move and abandons the
run, and the retirement goes on over what that left. A subject moved just after
a last word read the comment -- the evidence step's, or the one behind the
relabel -- refuses the retirement instead, which is decided on every record the
run is bound through, and the last word asked again behind the refusal abandons
the run, for the next recovery to route the head -- even where the subject is
put back the moment the retirement's guard has read it, ahead of that last
word, since the guard's reading is handed to the word as the movement it is.
So putting the subject or the configuration back afterwards revives nothing --
neither a later recovery nor the dispatcher's reconciliation settles the run. Nothing runs, pushes, or
announces again, and no developer is launched.
"""
from __future__ import annotations

import hashlib
import unittest
from functools import partial
from unittest.mock import patch

from orchestrator.git.base_sync import rewrite_facts
from orchestrator.workflow.engine.review_subjects import REVIEW_SUBJECT
from tests.workflow.engine import (
    rewrite_finish_readings as readings,
    rewrite_verification_recovery_support as support,
)

# A requirements revision no reviewer was handed, for a review subject another road records.
_ELSEWHERE = hashlib.sha256(b"requirements recorded behind the last word").hexdigest()


class _RacesPastTheCall:
    """A step answering as it always does, with `raced` made once, just after its call number `nth` answers."""

    def __init__(self, step, nth: int, raced) -> None:
        self._step = step
        self._calls = 0
        self._nth = nth
        self._raced = raced

    def __call__(self, *called, **options):
        """Answer as the step does, making the race behind call number `nth`."""
        answered = self._step(*called, **options)
        self._calls += 1
        if self._calls == self._nth:
            self._raced()
        return answered


def _records_the_subject(case: support.VerificationRecoveryCase, recorded: dict) -> None:
    """Record `recorded` as the review subject on `case`'s pinned comment, as another road's write would."""
    moved = case.gh.read_pinned_state(case.issue)
    moved.set(REVIEW_SUBJECT, recorded)
    case.gh.write_pinned_state(case.issue, moved)


def _moves_the_subject(case: support.VerificationRecoveryCase, recorded: dict) -> None:
    """Record a review subject no reviewer was handed in place of `recorded`."""
    _records_the_subject(case, {**recorded, "requirements": _ELSEWHERE})


def _after(where, nth: int, moves, case: support.VerificationRecoveryCase, recorded: dict) -> None:
    """Have `moves` made just after call number `nth` of the step `where` names for `case` answers."""
    owner, step = where(case)
    case.enterContext(patch.object(owner, step, getattr(owner, step)))
    racing = _RacesPastTheCall(getattr(owner, step), nth, partial(moves, case, recorded))
    setattr(owner, step, racing)


def _moves_until_read(case: support.VerificationRecoveryCase, recorded: dict) -> None:
    """Move the review subject off `recorded`, and put it back once the next read of the comment answers."""
    _moves_the_subject(case, recorded)
    _after(*_COMMENT_READ, _records_the_subject, case, recorded)


# The steps a move is hung on, each beside the call it follows: the relabel, the
# next read of the pinned comment, and the checkout's reading -- the recovery's
# second of which is the evidence step's last word, behind the captured run's
# proof.
_RELABEL = (lambda case: (case.gh, "set_workflow_label"), 1)
_COMMENT_READ = (lambda case: (case.gh, "read_pinned_state"), 1)
_LAST_WORD = (lambda _case: (rewrite_facts, "_reads_the_checkout"), 2)

# What moves while the route is taken, beside what puts it back and whether the
# recovery that read it still retires the attempt: the review subject the run is
# bound through, and the configured verification command, both moved as the
# issue is relabelled; and the subject moved once a last word has read the
# comment -- the one behind the relabel, or the evidence step's ahead of the
# retirement's preparation -- which the retirement refuses, whether it stays
# moved or is put back as soon as the retirement's guard has read it.
_MOVES = (
    ("the review subject", partial(_after, *_RELABEL, _moves_the_subject), _records_the_subject, True),
    (
        "the configured command",
        partial(_after, *_RELABEL, lambda case, _recorded: case.configures("echo another")),
        lambda case, _recorded: case.configures(support.CONFIGURED),
        True,
    ),
    (
        "the review subject, behind the relabel's last word",
        partial(_after, *_RELABEL, partial(_after, *_COMMENT_READ, _moves_the_subject)),
        _records_the_subject,
        False,
    ),
    (
        "the review subject, behind the evidence step's last word",
        partial(_after, *_LAST_WORD, _moves_the_subject),
        _records_the_subject,
        False,
    ),
    (
        "the review subject, put back behind the retirement's commit",
        partial(_after, *_RELABEL, partial(_after, *_COMMENT_READ, _moves_until_read)),
        _records_the_subject,
        False,
    ),
    (
        "the review subject, put back behind the retirement's preparation",
        partial(_after, *_LAST_WORD, _moves_until_read),
        _records_the_subject,
        False,
    ),
)


class RetirementMoveRecoveryTest(support.CapturedRunCase, unittest.TestCase):
    """A run something moved under while its route was taken is abandoned, and no restoration revives it."""

    def test_a_move_at_retirement_abandons(self) -> None:
        # The run is abandoned and the head routed to the fresh reviewer --
        # or, where the retirement refused the move, routed by the next
        # recovery with the run already abandoned. Put back, the move revives
        # nothing in a later recovery or in the reconciliation.
        for move in _MOVES:
            with self.subTest(moved=move[0]):
                head, captured, recorded = self._recovers_beside(move[1])

                self.assert_abandoned(captured)
                if move[3]:
                    self.assert_recovered(head)
                else:
                    self.assertEqual(readings.pinned(self)[readings.KEY_PENDING_PUSH], self.anchor)
                move[2](self, recorded)
                self.recovers()
                self.reconciles()
                self.assert_abandoned(captured)
                self.assert_recovered(head)

    def _recovers_beside(self, arms) -> tuple:
        """A fresh case's captured run, recovered with the move `arms` hangs on one of its steps.

        The head, the run, and the review subject recorded before the move.
        """
        self.setUp()
        head, captured = self.captures()
        recorded = self.gh.read_pinned_state(self.issue).get(REVIEW_SUBJECT)
        arms(self, recorded)
        self.recovers()
        return head, captured, recorded


if __name__ == "__main__":
    unittest.main()
