# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The recovery of a landed base rewrite's verification, through the next tick's whole base refresh.

A tick that died after its push landed -- before the configured command ran,
or behind a run that completed and was never recorded -- captured nothing, so
the recovery proves the landing again and decides its evidence afresh: the
command runs once more on the rebased head, and what it printed is recorded
before the route -- unless the base was rewound under the head, which runs
nothing. A run the evidence write captured before the tick died is routed
exactly as recorded with no second run, unless something it was bound to moved
since -- the requirements, the report and review subject, the configuration,
or the base -- which abandons it, with nothing run again and the fresh reviewer
owing the evidence; once abandoned it is never run again, even by a recovery
whose own route that abandonment stopped short of. A review that moves while
the recovery proves the run abandons it the same way. Something moving while the
recovery's own run is under way leaves that run eligible for nothing -- a landing
that moved holds the route too -- and a
base that advances meanwhile holds the head unrouted for the next recovery to
rebase. No recovery pushes the landed head again, repeats its announcement, or
launches a developer.
"""
from __future__ import annotations

import unittest
from functools import partial
from unittest.mock import patch

from orchestrator.git.base_sync import pre_pr
from tests.workflow.engine import (
    rewrite_finish_git_support as git_support,
    rewrite_finish_readings as readings,
    rewrite_verification_recovery_support as support,
    verification_report_fixture as _report,
)
from tests.workflow.interleaving import _RacesPastTheStep

_EDITED_BODY = "Also cover a moved base."

_UPDATE_REF = "update-ref"

_STRAY_COMMIT = (
    "-c", "user.name=stray", "-c", "user.email=stray@example.invalid",
    "commit", "--quiet", "--allow-empty", "-m", "stray",
)


def _settles_a_later_report(case: support.VerificationRecoveryCase, head: str) -> None:
    """Settle report 3 of `head` and hand a reviewer it, over the comment as it stands."""
    case.state = case.gh.read_pinned_state(case.issue)
    _report.settles_report(case, 3, "Implemented the change and covered a base that moved twice.", head=head)
    case.gh.write_pinned_state(case.issue, case.state)


def _settles_once_read(case: support.VerificationRecoveryCase, head: str, reread) -> None:
    """Put `reread` back on `case`'s client, then settle report 3 of `head` and hand a reviewer it."""
    case.gh.reread_report_location = reread
    _settles_a_later_report(case, head)


def _rewinds_the_base(case: support.VerificationRecoveryCase, _head: str) -> None:
    """Force the remote's base back onto the commit the anchor was made over, dropping what it advanced by."""
    case._git(_UPDATE_REF, "refs/heads/main", f"{case.anchor}^", cwd=case._remote)


def _puts_the_remote_back(case: support.VerificationRecoveryCase) -> None:
    """Move the pull request's remote branch back onto the head the rebase replaced."""
    case._git(_UPDATE_REF, f"refs/heads/{git_support.BRANCH}", case.anchor, cwd=case._remote)


# What moves a captured run was bound to before the recovery reads it.
_MOVED_BEFORE = (
    ("the issue body was edited", lambda case, _head: setattr(case.issue, "body", _EDITED_BODY)),
    ("a later report was settled and reviewed", _settles_a_later_report),
    ("another command was configured", lambda case, _head: case.configures("echo another")),
    ("the base was rewound under the head", _rewinds_the_base),
)

# What another road does while the recovery's own run of the command is under way.
# Beside each, whether the head still routes once the run is refused: a landing
# that moved holds it for the next tick instead.
_MOVED_DURING = (
    ("the checkout committed past the remote", lambda case: case._git(*_STRAY_COMMIT, cwd=case._wt), False),
    ("the remote branch was put back on the anchor", _puts_the_remote_back, False),
    ("the issue body was edited", lambda case: setattr(case.issue, "body", _EDITED_BODY), True),
    ("another command was configured", lambda case: case.configures("echo another"), True),
)


class MissingRecordRecoveryTest(support.VerificationRecoveryCase, unittest.TestCase):
    """A landing whose tick died before its run was durably recorded is verified once more by the recovery."""

    def test_a_run_never_recorded_is_resumed(self) -> None:
        # Before the command ran, or behind a run that completed: either way
        # nothing of it reached the pinned comment and the attempt stands, so
        # the recovery runs the command and records exactly what it printed.
        for completed, ran in ((False, 0), (True, 1)):
            with self.subTest(completed=completed):
                self.setUp()
                head = self.lands_a_reviewed_rebase()
                self.dies_verifying(head, completed=completed)
                self.assert_held(None)
                self.assertEqual(self.runs(), ran)

                self.recovers()

                self._assert_recorded_a_run_of(head)
                self.assertEqual(self.runs(), ran + 1)
                self.assert_recovered(head)

    def test_a_rewound_base_runs_nothing(self) -> None:
        # The base is rewound under the landed head before the recovery, so
        # the head carries commits over it beyond its own replay: nothing
        # runs and nothing is recorded, and the head goes to the fresh
        # reviewer, which owes the evidence.
        head = self.lands_a_reviewed_rebase()
        self.dies_verifying(head, completed=False)
        _rewinds_the_base(self, head)

        self.recovers()

        self.assertEqual(
            (readings.pinned_records(self), self.runs()),
            (git_support.nothing_recorded(self), 0),
        )
        self.assert_recovered(head)

    def test_a_base_rewound_mid_rebase_runs_nothing(self) -> None:
        # The refresh rebases the branch onto the advanced base, and the base
        # -- the local ref and the remote's own -- is rewound the moment git
        # returns, before the attempt records what its replay was made onto.
        # The attempt names no tip the rewind could stand in for, so once a
        # reviewer is handed the published head and its finish is recovered,
        # nothing runs or is recorded and the head goes to the fresh reviewer.
        rewound = self._git("rev-parse", "refs/heads/main", cwd=self._remote).strip()
        git_support.advances_the_base(self)
        rebases = partial(self._rebases_then_rewinds, pre_pr._rebase_base_into_worktree, rewound)
        with patch.object(pre_pr, "_rebase_base_into_worktree", side_effect=rebases):
            self.dies_routing(self.recovers)
        head = git_support.remote_head(self)
        self.pull_request.head.sha = head
        self.reviews(head)

        self.recovers()

        recorded = readings.records(readings.pinned(self))
        self.assertEqual(
            (recorded, self.runs(), readings.relabels(self)),
            (git_support.nothing_recorded(self), 0, readings.ROUTED),
        )
        said = (support.announced(self), self.pushes.call_count, self.developer.call_count)
        self.assertEqual(said, ([head], 1, 0))

    def _rebases_then_rewinds(self, rebase, rewound: str, spec, worktree) -> tuple:
        """Run `rebase` as the refresh asked, then rewind the base -- the local ref and the remote's -- to `rewound`."""
        rebased = rebase(spec, worktree)
        self._git(_UPDATE_REF, "refs/remotes/origin/main", rewound, cwd=self._wt)
        self._git(_UPDATE_REF, "refs/heads/main", rewound, cwd=self._remote)
        return rebased

    def _assert_recorded_a_run_of(self, head: str) -> None:
        """The command's run on `head` pending, executed here and recorded as it printed, beside nothing current."""
        pending, current, retired = readings.pinned_records(self)
        binding = pending.binding
        self.assertEqual(
            (binding.tested_sha, binding.tested_tree, binding.source.value),
            (head, git_support.tree(self, head), "orchestrator-executed"),
        )
        transcript = [(command.exit_status, command.output.strip()) for command in pending.commands]
        self.assertEqual(
            (transcript, current, retired),
            ([(0, git_support.CHECKED)], None, git_support.invalidated(self)),
        )


class CapturedRunRecoveryTest(support.VerificationRecoveryCase, unittest.TestCase):
    """A run the evidence write captured is routed as recorded, or abandoned where what it was bound to moved."""

    def test_a_captured_run_is_routed_as_recorded(self) -> None:
        # The tick died at the relabel behind the write that recorded its
        # run: the recovery routes that very transaction, run once.
        head, captured = self._captures()
        self.assertEqual(readings.relabels(self), ())

        self.recovers()

        self.assertEqual(
            (readings.pinned_records(self), self.runs()),
            ((captured, None, git_support.invalidated(self)), 1),
        )
        self.assert_recovered(head)

    def test_a_moved_captured_run_is_abandoned(self) -> None:
        # The run was captured, so it is not run again; proved again over
        # what moved, it is abandoned into history rather than routed, and
        # the fresh reviewer owes the evidence.
        for moved, moves_it in _MOVED_BEFORE:
            with self.subTest(moved=moved):
                self.setUp()
                head, captured = self._captures()
                moves_it(self, head)

                self.recovers()

                self._assert_abandoned(captured)
                self.assert_recovered(head)

    def test_an_advanced_base_abandons_the_run(self) -> None:
        # The base moved again before the recovery: the landed head is not
        # routed, its captured run is abandoned before its attempt retires,
        # and the tick's own rebase publishes and routes the next head with
        # nothing run, since no reviewer was handed that head.
        head, captured = self._captures()
        support.advances_the_base_again(self)

        self.recovers()

        rebased = git_support.remote_head(self)
        self.assertNotEqual(rebased, head)
        self._assert_abandoned(captured)
        self.assertEqual(
            (support.announced(self), self.pushes.call_count, self.developer.call_count),
            ([head, rebased], 1, 0),
        )
        self.assertEqual(
            (readings.relabels(self), readings.attempt(readings.pinned(self))),
            (readings.ROUTED, readings.RETIRED),
        )

    def test_an_abandoned_run_is_not_run_again(self) -> None:
        # The recovery abandons the captured run for a moved configuration
        # and dies at its relabel, behind that durable abandonment. The next
        # recovery finds the run retired in history: it runs nothing again
        # and routes the head to the fresh reviewer.
        head, captured = self._captures()
        self.configures("echo another")
        self.dies_routing(self.recovers)
        self._assert_abandoned(captured)

        self.recovers()

        self._assert_abandoned(captured)
        self.assert_recovered(head)

    def test_a_review_moved_mid_proof_abandons(self) -> None:
        # A later report settles and is reviewed while the recovery re-reads
        # the one the captured run is bound to: the run proves over what the
        # tick read, but the last word reads the review records again and
        # finds the later review, so the run is abandoned unrun -- in a write
        # that moved review does not refuse -- and the head goes to the fresh
        # reviewer.
        head, captured = self._captures()
        reread = self.gh.reread_report_location
        self.gh.reread_report_location = _RacesPastTheStep(reread, partial(_settles_once_read, self, head, reread))

        self.recovers()

        self._assert_abandoned(captured)
        self.assert_recovered(head)

    def _captures(self) -> tuple:
        """Land a reviewed rebase whose finish records its run and dies at the relabel; the head, and that run."""
        head = self.lands_a_reviewed_rebase()
        self.dies_routing(partial(self.finishes, head))
        self.assertEqual(self.runs(), 1)
        return head, readings.pinned_records(self)[0]

    def _assert_abandoned(self, captured) -> None:
        """Nothing pending or current, the settled evidence invalidated and `captured` abandoned, and no second run."""
        retired = (*git_support.invalidated(self), (captured.receipt, readings.ABANDONED))
        self.assertEqual(
            (readings.pinned_records(self), self.runs()),
            ((None, None, retired), 1),
        )


class MovedDuringRecoveryTest(support.VerificationRecoveryCase, unittest.TestCase):
    """A recovery's own run something moved under is recorded nowhere, and the fresh reviewer owes the evidence."""

    def test_a_move_during_the_rerun_records_nothing(self) -> None:
        # Whatever moved, the run is recorded nowhere. A landing that moved
        # under it -- the checkout or the remote branch off the head -- holds
        # the route as well, with nothing pushed or announced again.
        for moved, moves_it, routes in _MOVED_DURING:
            with self.subTest(moved=moved):
                self.setUp()
                head = self.lands_a_reviewed_rebase()
                self.dies_verifying(head, completed=False)

                with self.assertLogs("orchestrator.workflow", "INFO") as logged:
                    self.recovers(during=moves_it)
                    self.assertIn(support.decided_moved(head), str(logged.output))

                self.assertEqual(
                    (readings.pinned_records(self), self.runs()),
                    (git_support.nothing_recorded(self), 1),
                )
                if routes:
                    self.assert_recovered(head)
                else:
                    self.assert_held(None)

    def test_a_base_moved_during_the_rerun_holds(self) -> None:
        # The base advances while the recovery's run is under way: the head is
        # no longer level with it, so the run is recorded nowhere and the head
        # is not routed. The next recovery counts the head against the moved
        # base and continues it to the tick's rebase, which publishes and
        # routes the next head with nothing run, since no reviewer was handed it.
        head = self.lands_a_reviewed_rebase()
        self.dies_verifying(head, completed=False)

        with self.assertLogs("orchestrator.workflow", "INFO") as logged:
            self.recovers(during=support.advances_the_base_again)
            self.assertIn(support.decided_moved(head), str(logged.output))

        self.assert_held(None)
        self.recovers()
        rebased = git_support.remote_head(self)
        recorded = readings.pinned_records(self)
        self.assertEqual(
            (recorded, self.runs(), readings.relabels(self)),
            (git_support.nothing_recorded(self), 1, readings.ROUTED),
        )
        self.assertEqual(
            (support.announced(self), self.pushes.call_count, self.developer.call_count),
            ([head, rebased], 1, 0),
        )


if __name__ == "__main__":
    unittest.main()
