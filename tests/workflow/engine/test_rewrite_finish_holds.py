# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A landed base rewrite whose evidence something moved under, or whose evidence write did not land.

A result whose head, checkout, requirements, or configuration moved while the
commands ran is recorded nowhere, and the head goes to the fresh reviewer. A
review recorded meanwhile, a pinned comment that would not read again, an
evidence write whose answer was lost, and one the comment had no room for each
hold the route instead: nothing relabelled, the attempt standing. The next
finish -- the recovery of the push it finds standing -- decides over the
comment as it then reads, and repeats neither the announcement nor a record
an earlier finish already made, while still invalidating evidence a context
moved since then no longer lets stand.
"""
from __future__ import annotations

import unittest
from functools import partial
from unittest.mock import patch

from orchestrator import config
from orchestrator.git.publication.probes import _BranchDivergence
from orchestrator.workflow.engine.rewrite_finish_models import FinishOutcome
from tests.workflow.engine import (
    rewrite_evidence_test_support as rewrite_support,
    rewrite_finish_evidence_test_support as finish_support,
    rewrite_finish_moves as moves,
    rewrite_finish_readings as readings,
    verification_evidence_test_support as support,
)
from tests.workflow.interleaving import _RacesPastTheStep

REBASED = support.REBASED_SHA

SQUASHED = support.SQUASHED_SHA

FOUND = finish_support.FOUND

TO_VALIDATING = readings.ROUTED

# A checkout that committed past the rebased head the remote still stands on.
_AHEAD = _BranchDivergence(tip=REBASED, ahead=1, readable=True)

# How much longer a timeout configured otherwise is than the one in force, so
# a move is one from whatever an earlier subtest's patch left configured.
_LONGER_BY = 600

# What an operator configures otherwise while the commands run, each of which
# moves the context the settled evidence was taken under.
_CONTEXT_MOVES = (
    (
        "a command was configured beside the suite",
        lambda case: case.enterContext(patch.object(
            config, "VERIFY_COMMANDS", (support.SUITE, rewrite_support.LINT),
        )),
    ),
    (
        "the timeout was configured otherwise",
        lambda case: case.enterContext(patch.object(
            config, "VERIFY_TIMEOUT", config.VERIFY_TIMEOUT + _LONGER_BY,
        )),
    ),
)

# What another road does while the rebased head's commands run, which leaves
# the result eligible for nothing.
_MOVES = (
    ("the checkout committed past the remote", lambda case: setattr(case.world, "remote", _AHEAD)),
    ("a push moved the pull request and the branch", lambda case: case.moves_the_head(support.SQUASHED_SHA)),
    ("the issue body was edited", lambda case: setattr(case.issue, "body", "Also cover a moved base.")),
    *_CONTEXT_MOVES,
)


class MovedDuringVerificationTest(unittest.TestCase, finish_support.RewriteFinishCase):
    """A result something it is bound to moved under while it ran is recorded nowhere."""

    def setUp(self) -> None:
        finish_support.RewriteFinishCase.setUp(self)

    def test_a_moved_result_is_refused(self) -> None:
        # Passing or failing, the run is no evidence of the rebased head:
        # nothing is recorded or posted as a failure, and the head goes to the
        # fresh reviewer with the replaced head's evidence invalidated.
        for moved, moves_it in _MOVES:
            for exit_status in (0, rewrite_support.FAILED_EXIT):
                with self.subTest(moved=moved, exit_status=exit_status):
                    self._runs_under(moves_it, exit_status)

                    self.assertEqual(self.finishes(REBASED), FinishOutcome.ROUTED)

                    self.assertEqual(self.at_the_relabel(), (None, None, self.invalidated()))
                    self.assertEqual(len(readings.notices(self)), 1)

    def test_a_context_moved_meanwhile_invalidates(self) -> None:
        # The squash leaves the tested tree, but the settled artifact was
        # edited by hand, so nothing is carried and the suite runs on the
        # squash. A command or a timeout configured otherwise while it runs
        # refuses the result, and moves the context the settled evidence was
        # taken under: the equal tree no longer spares that evidence, and it
        # is invalidated before the route rather than left current.
        for moved, moves_it in _CONTEXT_MOVES:
            with self.subTest(moved=moved):
                self.setUp()
                self.attempts(SQUASHED)
                self.rewrites(SQUASHED)
                support.artifact_comment(self).body = "Rewritten by hand."
                self.during = moves_it

                self.assertEqual(self.finishes(SQUASHED), FinishOutcome.ROUTED)

                self.assertEqual(self.at_the_relabel(), (None, None, self.invalidated()))
                self.assertEqual(
                    (len(self.handed), readings.relabels(self)),
                    (1, TO_VALIDATING),
                )

    def test_a_review_moved_meanwhile_holds_the_route(self) -> None:
        # A later report settles and is reviewed while the commands run. The
        # result is refused, and so is the write that would invalidate the
        # settled evidence, since records it was decided on moved. The next
        # finish runs again over the comment as it then reads, records that
        # run against the later review, and announces nothing a second time.
        self._runs_under(moves.later_review)

        self.assertEqual(self.finishes(REBASED), FinishOutcome.REFUSED)

        self._assert_held()
        self.during = moves.unmoved
        self.assertEqual(self.finishes(REBASED, FOUND), FinishOutcome.ROUTED)
        pending = self.at_the_relabel()[0]
        self.assertEqual(pending.binding.target.subject, readings.pinned(self)["review_subject"])
        self.assertEqual(
            (len(self.handed), len(readings.notices(self))),
            (2, 1),
        )

    def test_an_unreadable_comment_holds_the_route(self) -> None:
        # The pinned comment would not read again after the run: nothing is
        # decided, written, or routed. Once it reads, the next finish records a
        # run of the rebased head and routes it.
        self._runs_under(moves.unreadable)

        self.assertEqual(self.finishes(REBASED), FinishOutcome.HELD)

        self.gh.pinned_failures.unreadable.clear()
        self._assert_held()
        self.during = moves.unmoved
        self.assertEqual(self.finishes(REBASED, FOUND), FinishOutcome.ROUTED)
        pending, _current, retired = self.at_the_relabel()
        self.assertEqual((pending.binding.tested_sha, retired), (REBASED, self.invalidated()))

    def _runs_under(self, moves_it, exit_status: int = 0) -> None:
        """A fresh case whose rebase onto `REBASED` exits `exit_status` while `moves_it` happens."""
        self.setUp()
        self.attempts(REBASED)
        self.rewrites(REBASED)
        self.exits[support.SUITE] = exit_status
        self.during = moves_it

    def _assert_held(self) -> None:
        """Nothing routed, the attempt standing, and the settled evidence current and nothing retired."""
        held = readings.pinned(self)
        _pending, current, retired = readings.records(held)
        self.assertEqual(
            (readings.relabels(self), held[readings.KEY_PENDING_PUSH], current.receipt, retired),
            ((), support.TESTED_SHA, self.source.receipt, ()),
        )


class EvidenceWriteTest(unittest.TestCase, finish_support.RewriteFinishCase):
    """An evidence write that did not land or fit holds the route, and the next finish repeats nothing it made."""

    def setUp(self) -> None:
        finish_support.RewriteFinishCase.setUp(self)

    def test_an_unconfirmed_record_is_made_once(self) -> None:
        # The evidence write lands and its answer is lost: nothing routes. The
        # next finish finds the transaction recorded for the landed head and
        # routes it, with no second run, revision, or history entry.
        self.attempts(REBASED)
        self.rewrites(REBASED)
        self.during = moves.loses_answers

        self.assertEqual(self.finishes(REBASED), FinishOutcome.UNCONFIRMED)

        self.gh.pinned_failures.lost.clear()
        recorded = readings.pinned_records(self)
        self.assertEqual(readings.relabels(self), ())
        self.assertEqual(self.finishes(REBASED, FOUND), FinishOutcome.ROUTED)
        self.assertEqual(self.at_the_relabel(), recorded)
        floor = readings.pinned(self)[readings.KEY_REVISION_FLOOR]
        self.assertEqual(
            (len(self.handed), floor, len(readings.notices(self))),
            (1, recorded[0].revision, 1),
        )

    def test_a_reused_carry_is_invalidated_once_owed(self) -> None:
        # The exact tree's carry is recorded and the settled evidence left
        # current, and the retirement behind the relabel is refused. The
        # configuration moves before the next finish, which reuses the carry
        # -- no run, no second revision -- but invalidates the settled
        # evidence the moved context no longer lets stand, before it routes.
        self.attempts(SQUASHED)
        self.rewrites(SQUASHED)
        relabel = self.gh.set_workflow_label
        self.gh.set_workflow_label = _RacesPastTheStep(relabel, partial(finish_support.spends_a_round, self))

        self.assertEqual(self.finishes(SQUASHED), FinishOutcome.REFUSED)

        self.gh.set_workflow_label = relabel
        carried, current, _retired = readings.pinned_records(self)
        self.assertEqual(current.receipt, self.source.receipt)
        with patch.object(config, "VERIFY_COMMANDS", (support.SUITE, rewrite_support.LINT)):
            self.assertEqual(self.finishes(SQUASHED, FOUND), FinishOutcome.ROUTED)
        self.assertEqual(readings.pinned_records(self), (carried, None, self.invalidated()))
        self.assertEqual(
            (self.handed, readings.attempt(readings.pinned(self))),
            ([], readings.RETIRED),
        )

    def test_no_room_to_invalidate_holds_the_route(self) -> None:
        # The comment fills while the commands run, so the write the decision
        # was staged for overflows it and is refused. The next finish, over the
        # full comment, has no room to invalidate the settled evidence and
        # holds. Once room is made, the one after records and routes.
        self.attempts(REBASED)
        self.rewrites(REBASED)
        self.during = moves.fills_the_comment

        self.assertEqual(self.finishes(REBASED), FinishOutcome.REFUSED)

        self.during = moves.unmoved
        with self.assertLogs(support.WORKFLOW_LOG, "ERROR") as logged:
            self.assertEqual(self.finishes(REBASED, FOUND), FinishOutcome.HELD)
            self.assertIn("no room to invalidate", support.logged_refusal(logged))
        self.assertEqual(
            (readings.relabels(self), readings.pinned_records(self)[2]),
            ((), ()),
        )
        moves.makes_room(self)
        self.assertEqual(self.finishes(REBASED, FOUND), FinishOutcome.ROUTED)
        pending, _current, retired = self.at_the_relabel()
        self.assertEqual(
            (pending.binding.tested_sha, retired, len(self.handed)),
            (REBASED, self.invalidated(), 3),
        )


if __name__ == "__main__":
    unittest.main()
