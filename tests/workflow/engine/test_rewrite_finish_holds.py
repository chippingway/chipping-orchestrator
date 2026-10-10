# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A landed base rewrite whose evidence something moved under, or whose evidence write did not land.

A result whose head, checkout, requirements, or configuration moved while the
commands ran is recorded nowhere: a landing that moved holds the route, and
anything else sends the head to the fresh reviewer. A
review recorded meanwhile, a pinned comment that would not read again, an
evidence write whose answer was lost, and one the comment had no room for each
hold the route instead: nothing relabelled, the attempt standing. The next
finish -- the recovery of the push it finds standing -- decides over the
comment as it then reads, and repeats neither the announcement nor a record
an earlier finish already made, while still invalidating evidence a context
moved since then no longer lets stand -- and abandoning a recorded carry that
moved context refuses, with nothing run again.
"""
from __future__ import annotations

import unittest
from functools import partial
from itertools import product
from unittest.mock import patch

from orchestrator import config
from orchestrator.git.base_sync.rewrite_handoffs import _BaseStanding
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
# the result eligible for nothing, beside what the finish comes to: a landing
# that moved holds the route, and anything else lets it go on to the reviewer.
_MOVES = (
    (
        "the checkout committed past the remote",
        lambda case: setattr(case.world, "remote", _AHEAD),
        FinishOutcome.HELD,
    ),
    (
        "a push moved the pull request and the branch",
        lambda case: case.moves_the_head(support.SQUASHED_SHA),
        FinishOutcome.HELD,
    ),
    (
        "the issue body was edited",
        lambda case: setattr(case.issue, "body", "Also cover a moved base."),
        FinishOutcome.ROUTED,
    ),
    *((moved, moves_it, FinishOutcome.ROUTED) for moved, moves_it in _CONTEXT_MOVES),
)


# Routes that run no command: the exact tree's carry, and a changed tree with
# nothing configured.
_SILENT_ROUTES = (
    ("an exact tree's carry", SQUASHED, (support.SUITE,)),
    ("a changed tree with nothing configured", REBASED, ()),
)

# A base gone elsewhere since the head was counted, and one nobody could read,
# beside whether the route's recorded carry stands behind the hold: a base read
# elsewhere is movement established, which abandons it, and an unread one is
# not.
_HOLDING = tuple(
    (route, standing, standing is _BaseStanding.UNREAD and route[1] == SQUASHED)
    for route, standing in product(_SILENT_ROUTES, (_BaseStanding.MOVED, _BaseStanding.UNREAD))
)

# A base that is not the tip the replay was recorded as made onto, and an
# attempt that recorded none.
_REFUSING = tuple(product(_SILENT_ROUTES, (_BaseStanding.DROPPED, _BaseStanding.UNPROVEN)))


class MovedDuringVerificationTest(unittest.TestCase, finish_support.RewriteFinishCase):
    """A result something it is bound to moved under while it ran is recorded nowhere."""

    def setUp(self) -> None:
        finish_support.RewriteFinishCase.setUp(self)

    def test_a_moved_result_is_refused(self) -> None:
        # Passing or failing, the run is no evidence of the rebased head:
        # nothing is recorded or posted as a failure, and the replaced head's
        # evidence is invalidated. The head goes to the fresh reviewer, unless
        # the landing itself moved, which holds it for the next tick.
        for moved, moves_it, outcome in _MOVES:
            for exit_status in (0, rewrite_support.FAILED_EXIT):
                with self.subTest(moved=moved, exit_status=exit_status):
                    self._runs_under(moves_it, exit_status)

                    self.assertEqual(self.finishes(REBASED), outcome)

                    self.assertEqual(readings.pinned_records(self), (None, None, self.invalidated()))
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

    def test_an_unprovable_record_holds_the_route(self) -> None:
        # The evidence write lands and its answer is lost. The next finish
        # cannot re-read the settled report the captured run is bound to, so
        # it holds the route with the record standing and nothing run. Once
        # the report reads, the finish after it routes the record as captured.
        self.attempts(REBASED)
        self.rewrites(REBASED)
        self.during = moves.loses_answers
        self.assertEqual(self.finishes(REBASED), FinishOutcome.UNCONFIRMED)
        self.gh.pinned_failures.lost.clear()
        recorded = readings.pinned_records(self)
        unreadable = self.gh.report_failures.unreadable

        unreadable.add(support.PR_NUMBER)
        held = self.finishes(REBASED, FOUND)
        unreadable.clear()

        self.assertEqual(
            (held, readings.pinned_records(self), readings.relabels(self)),
            (FinishOutcome.HELD, recorded, ()),
        )
        self.assertEqual(self.finishes(REBASED, FOUND), FinishOutcome.ROUTED)
        self.assertEqual(
            (self.at_the_relabel(), len(self.handed)),
            (recorded, 1),
        )

    def test_a_moved_context_abandons_the_carry(self) -> None:
        # The exact tree's carry is recorded and the settled evidence left
        # current, and the retirement behind the relabel is refused. The
        # configuration moves before the next finish, which proves the carry
        # again and finds it refused: the carry is abandoned and the settled
        # evidence the moved context no longer lets stand invalidated, both
        # before the route, with nothing run and the reviewer owing evidence.
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
        self.assertEqual(
            readings.records(self.durable[-1]),
            (None, None, (*self.invalidated(), (carried.receipt, readings.ABANDONED))),
        )
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


class BaseStandingTest(unittest.TestCase, finish_support.RewriteFinishCase):
    """A recovered landing's evidence is held to the base its head was replayed onto on routes that run nothing too."""

    def setUp(self) -> None:
        finish_support.RewriteFinishCase.setUp(self)

    def test_a_moved_base_holds_a_silent_route(self) -> None:
        # Neither route runs anything, yet a base gone elsewhere since the
        # head was counted, or one nobody could read, holds both behind the
        # decision's write: nothing routed or retired, for the next tick to
        # count the head again. A carry the base was read moving under is
        # abandoned besides; an unread base leaves it to be proved again.
        for route, standing, keeps in _HOLDING:
            with self.subTest(route=route[0], standing=standing):
                self._lands(route[1], route[2], standing)

                self.assertEqual(self.finishes(route[1], FOUND), FinishOutcome.HELD)

                held = readings.pinned(self)
                carried = readings.records(held)[0] is not None
                self.assertEqual(
                    (held[readings.KEY_PENDING_PUSH], carried, self.handed),
                    (support.TESTED_SHA, keeps, []),
                )
                self.assertEqual(readings.relabels(self), ())

    def test_a_base_off_its_tip_records_nothing(self) -> None:
        # A base the head was not replayed onto, or no recorded tip, records
        # neither the carry nor anything else, and the head goes to the
        # fresh reviewer.
        for (route, head, commands), standing in _REFUSING:
            with self.subTest(route=route, standing=standing):
                self._lands(head, commands, standing)

                self.assertEqual(self.finishes(head, FOUND), FinishOutcome.ROUTED)

                self.assertEqual(
                    (self.at_the_relabel()[0], self.handed),
                    (None, []),
                )

    def _lands(self, head: str, commands: tuple, standing: _BaseStanding) -> None:
        """A fresh case whose rewrite onto `head` landed under `commands`, its base standing as `standing` says."""
        self.setUp()
        self.attempts(head)
        self.rewrites(head)
        self.world.base = standing
        self.enterContext(patch.object(config, "VERIFY_COMMANDS", commands))


if __name__ == "__main__":
    unittest.main()
