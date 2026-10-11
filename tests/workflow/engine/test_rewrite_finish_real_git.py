# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A landed base rewrite's evidence over a real checkout, a real remote, and a real verify run.

Through the whole per-tick base refresh, a rebase over a base that moved what
the branch carries invalidates the settled evidence before the route, and one
that leaves the tested tree defers it; neither runs anything, since no review
of the rewritten head exists yet. Handed a landing whose head a reviewer was
handed, the finish runs the configured command through the verify runner in
the checkout: a pass is recorded with exactly what it printed, a failure is
posted on the pull request, and a run under which the checkout or the remote
moved is recorded nowhere. An exact tree's carry a later finish proves again
under a context moved between the two finishes is abandoned with nothing run,
and the evidence it carried is invalidated.
"""
from __future__ import annotations

import unittest
from functools import partial
from unittest.mock import patch

from orchestrator.git import branch_transport
from orchestrator.workflow.engine.rewrite_finish_models import FinishOutcome, FinishRoad
from tests.git.base_sync.real_git_test_support import _LocalBranchPusher
from tests.workflow.engine import (
    rewrite_finish_evidence_test_support as finish_support,
    rewrite_finish_git_support as git_support,
    rewrite_finish_readings as readings,
)
from tests.workflow.interleaving import _RacesPastTheStep

ROUTED = FinishOutcome.ROUTED

TO_VALIDATING = readings.ROUTED

_FRESH = "13 checks passed on the rebased tree"

# A committer for the stray commit a command makes, which the runner's
# stripped environment does not carry.
_STRAY_COMMIT = "git -c user.name=stray -c user.email=stray@example.invalid commit --quiet --allow-empty -m stray"


def _commits(_case: git_support.RealGitFinishCase) -> str:
    """A command that commits in the checkout, past the head the remote stands on."""
    return _STRAY_COMMIT


def _puts_the_remote_back(case: git_support.RealGitFinishCase) -> str:
    """A command that moves the pull request's remote branch back onto the head the rebase replaced."""
    return f"git -C '{case._remote}' update-ref refs/heads/{git_support.BRANCH} {case.anchor}"


def _decided_moved(head: str) -> str:
    """What the evidence policy logs of a result something moved under while it verified `head`."""
    short_head = head[:8]
    return f"decided moved evidence for the base rewrite's head {short_head}"


class RefreshedEvidenceRealGitTest(git_support.RealGitFinishCase, unittest.TestCase):
    """The whole base refresh: a changed tree invalidates before the route, an exact one defers."""

    def test_a_changed_tree_is_invalidated(self) -> None:
        git_support.advances_the_base(self)

        self._refreshes()

        head = self._wt_head()
        self.assertEqual(git_support.remote_head(self), head)
        self.assertNotEqual(git_support.tree(self, head), self.source.binding.tested_tree)
        self.assertEqual(readings.pinned_records(self), git_support.nothing_recorded(self))
        self._assert_routed_with_nothing_run()

    def test_an_exact_tree_is_deferred(self) -> None:
        git_support.advances_the_base(self, net=False)

        self._refreshes()

        head = self._wt_head()
        self.assertNotEqual(head, self.anchor)
        self.assertEqual(git_support.tree(self, head), self.source.binding.tested_tree)
        pending, current, retired = readings.pinned_records(self)
        self.assertEqual(
            (pending, current.receipt, retired),
            (None, self.source.receipt, ()),
        )
        self._assert_routed_with_nothing_run()

    def _refreshes(self) -> None:
        """One per-tick base refresh, its lease-pinned push sent to the bare remote."""
        with patch.object(branch_transport, "_push_branch", side_effect=_LocalBranchPusher()):
            self._refresh()

    def _assert_routed_with_nothing_run(self) -> None:
        """The issue routed to `workflow:validating`, the configured command never run."""
        self.assertEqual(
            (self.runs(), readings.relabels(self)),
            (0, TO_VALIDATING),
        )


class VerifiedRewriteRealGitTest(git_support.RealGitFinishCase, unittest.TestCase):
    """A landing whose head a reviewer was handed is verified by the configured command, in the checkout."""

    def test_a_pass_is_recorded_as_it_printed(self) -> None:
        head = self._reviewed_rebase(f"echo '{_FRESH}'")

        self.assertEqual(self.finishes(head), ROUTED)

        pending, current, retired = readings.pinned_records(self)
        self.assertEqual(
            (current, retired, self.runs()),
            (None, git_support.invalidated(self), 1),
        )
        self._assert_ran_on(pending, head)

    def test_a_failure_is_posted_and_records_nothing(self) -> None:
        head = self._reviewed_rebase("echo 'test_rebased failed' && exit 3")

        self.assertEqual(self.finishes(head), ROUTED)

        failed = readings.notices(self)[-1]
        self.assertIn("exited with code 3", failed)
        self.assertIn("> test_rebased failed", failed)
        self.assertEqual(readings.pinned_records(self), git_support.nothing_recorded(self))

    def test_a_move_during_the_run_records_nothing(self) -> None:
        # A command that commits moves the checkout past the remote; one that
        # puts the remote branch back moves the pull request's branch off the
        # head. Either way the run is of nothing the head can be routed with,
        # and the landing it was made for no longer stands: the route holds.
        for moved, command in (("the checkout", _commits), ("the remote", _puts_the_remote_back)):
            with self.subTest(moved=moved):
                self.setUp()
                head = self._reviewed_rebase(command(self))

                with self.assertLogs("orchestrator.workflow", "INFO") as logged:
                    self.assertEqual(self.finishes(head), FinishOutcome.HELD)
                    self.assertIn(_decided_moved(head), str(logged.output))

                self.assertEqual(readings.pinned_records(self), git_support.nothing_recorded(self))
                self.assertEqual(
                    (self.runs(), len(readings.notices(self))),
                    (1, 1),
                )

    def _assert_ran_on(self, pending, head: str) -> None:
        """`pending` is the configured command's run on `head`, executed here and recorded as it printed."""
        binding = pending.binding
        self.assertEqual(
            (binding.tested_sha, binding.tested_tree, binding.source.value),
            (head, git_support.tree(self, head), "orchestrator-executed"),
        )
        transcript = [(ran.exit_status, ran.output.strip()) for ran in pending.commands]
        self.assertEqual(transcript, [(0, _FRESH)])

    def _reviewed_rebase(self, command: str) -> str:
        """Configure `command`, rebase onto a moved base, and hand a reviewer the rebased head; that head."""
        self.configures(command)
        git_support.advances_the_base(self)
        head = self.rebases_by_hand()
        self.reviews(head)
        return head



class AbandonedCarryRealGitTest(git_support.RealGitFinishCase, unittest.TestCase):
    """An exact tree's carry, recorded by a finish whose retirement was refused, proved again by the finish after it."""

    def test_a_moved_context_abandons_the_carry(self) -> None:
        # The rebase leaves the tested tree and a reviewer was handed it, so
        # the settled evidence is carried and stays current; another road's
        # round refuses the retirement behind the relabel. The configuration
        # moves before the recovery finishes the landing: the carry is proved
        # again and refused, so it is abandoned rather than routed, nothing
        # runs, and the settled evidence the moved context no longer lets
        # stand is invalidated before the route.
        git_support.advances_the_base(self, net=False)
        head = self.rebases_by_hand()
        self.reviews(head)
        relabel = self.gh.set_workflow_label
        self.gh.set_workflow_label = _RacesPastTheStep(relabel, partial(finish_support.spends_a_round, self))

        self.assertEqual(self.finishes(head), FinishOutcome.REFUSED)

        self.gh.set_workflow_label = relabel
        carried, current, _retired = readings.pinned_records(self)
        self.assertEqual(
            (carried.copied_from, carried.binding.tested_tree, current.receipt),
            (self.source.receipt, git_support.tree(self, head), self.source.receipt),
        )
        self.configures(f"test -f feature.py && echo '{_FRESH}'")
        self.assertEqual(self.finishes(head, FinishRoad.RECOVERY), ROUTED)
        self.assertEqual(
            readings.pinned_records(self),
            (None, None, (*git_support.invalidated(self), (carried.receipt, readings.ABANDONED))),
        )
        self.assertEqual(
            (self.runs(), readings.attempt(readings.pinned(self))),
            (0, readings.RETIRED),
        )


if __name__ == "__main__":
    unittest.main()
