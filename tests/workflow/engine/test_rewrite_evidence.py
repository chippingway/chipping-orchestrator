# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The evidence a landed base rewrite's head would be routed with, decided over the rewrite's own trees.

An equal tree under the same context carries the current evidence, its tested
commit and source kept, but only onto a review of the rewritten head -- never
the approval of the head it replaced. A changed tree or context invalidates
that evidence into history and asks the configured commands for a fresh
result, which binds exactly what ran or stays actionable as a failure. An
empty configuration, or no report and review of the rewritten head to bind
to, runs nothing and leaves the evidence to the reviewer. Whatever ran is
eligible only while nothing it is bound to moved under it.
"""
from __future__ import annotations

import unittest
from unittest.mock import patch

from orchestrator import config
from orchestrator.git.publication.probes import _BranchDivergence
from orchestrator.git.verification import models as _verify_models
from orchestrator.github.verification_evidence import EvidenceSource
from orchestrator.workflow.engine import (
    review_subjects as _review_subjects,
    verification_record_state as _record_state,
    verification_records as _records,
    verification_settlement_state as _settlement,
)
from orchestrator.workflow.engine.rewrite_evidence_models import RewriteEvidence, RewriteEvidenceRoute
from tests.workflow.engine import (
    rewrite_evidence_test_support as rewrite_support,
    verification_evidence_test_support as support,
)

_LEVEL = "INFO"

_SUITE_AND_LINT = (support.SUITE, rewrite_support.LINT)

# Every way a subject the rewritten head's run would answer for is not there
# yet, the head rewritten onto, and the refusal it leaves to the reviewer.
_UNBOUND = (
    (
        "the report refresh never settled",
        lambda case: case.rewrites(support.REBASED_SHA, reported=False),
        support.REBASED_SHA, "no review_subject about the rewritten head",
    ),
    (
        "no reviewer was handed the refreshed report",
        lambda case: case.rewrites(support.REBASED_SHA, reviewed=False),
        support.REBASED_SHA, "no review_subject about the rewritten head",
    ),
    (
        "the refreshed report was edited where it settled",
        lambda case: (case.rewrites(support.REBASED_SHA), case.edits_the_report()),
        support.REBASED_SHA, "was edited, cut short, or rewritten",
    ),
    (
        "the refreshed report of the tested tree was edited",
        lambda case: (case.rewrites(support.SQUASHED_SHA), case.edits_the_report()),
        support.SQUASHED_SHA, "was edited, cut short, or rewritten",
    ),
    (
        "an approval of the replaced head stands",
        lambda case: (case.approves_the_tested_head(), case.rewrites(support.SQUASHED_SHA, reported=False)),
        support.SQUASHED_SHA, "not about the rewritten head",
    ),
)

# A checkout that committed past the rewritten head the remote still stands on.
_AHEAD = _BranchDivergence(tip=support.REBASED_SHA, ahead=1, readable=True)

# What another road does while the commands run, and the refusal it leaves.
_MOVES = (
    (
        "a push moved the pull request and the branch",
        lambda case: case.moves_the_head(support.SQUASHED_SHA),
        "moved off the recorded commit",
    ),
    (
        "the checkout moved past the remote",
        lambda case: setattr(case.world, "remote", _AHEAD),
        "carries commits the remote has not received",
    ),
    (
        "the issue body was edited on GitHub",
        lambda case: setattr(case.issue, "body", "Also cover a rebase onto a moved base."),
        "requirements moved",
    ),
    (
        "the issue title was edited on GitHub",
        lambda case: setattr(case.issue, "title", "Verify rebased heads"),
        "requirements moved",
    ),
    (
        "a later report settled and was reviewed",
        lambda case: case.rewrites(support.REBASED_SHA, revision=3),
        "another subject than the recorded review_subject",
    ),
    (
        "the configuration moved",
        lambda case: case.enterContext(patch.object(config, "VERIFY_COMMANDS", _SUITE_AND_LINT)),
        "verification configuration moved",
    ),
    (
        "the issue would not read again",
        lambda case: case.enterContext(patch.object(
            case.gh, "get_issue", side_effect=RuntimeError("GitHub did not answer"),
        )),
        "could not be read again after the run",
    ),
    (
        "the pinned comment would not read again",
        lambda case: case.enterContext(patch.object(
            case.gh, "read_pinned_state", side_effect=RuntimeError("GitHub did not answer"),
        )),
        "could not be read again after the run",
    ),
)


class CarriedRewriteTest(unittest.TestCase, rewrite_support.RewriteEvidenceCase):
    """An equal tree under the same context carries the evidence with its provenance."""

    def setUp(self) -> None:
        rewrite_support.RewriteEvidenceCase.setUp(self)

    def test_an_equal_tree_carries_its_provenance(self) -> None:
        # The squash reads as the tested tree, and the refreshed report about
        # it settled and was handed a reviewer: the carry keeps the commit the
        # commands ran on and names the artifact it copied, and nothing runs.
        self.rewrites(support.SQUASHED_SHA)

        decision = self.decide(support.SQUASHED_SHA)

        carry = decision.carry
        self.assertEqual(
            (decision.route, decision.invalidates, decision.run, self.handed),
            (RewriteEvidenceRoute.CARRIED, False, None, []),
        )
        self.assertEqual(
            (carry.binding.tested_sha, carry.binding.tested_tree, carry.binding.target.target_head),
            (support.TESTED_SHA, support.TESTED_TREE, support.SQUASHED_SHA),
        )
        self.assertEqual(
            (carry.copied_from, carry.commands, carry.binding.target.subject_commit),
            (self.source.receipt, self.source.commands, support.SQUASHED_SHA),
        )
        self.assertFalse(decision.stages(self.state))
        self.assertEqual(_settlement.read_current_evidence(self.state).receipt, self.source.receipt)


class ChangedRewriteTest(unittest.TestCase, rewrite_support.RewriteEvidenceCase):
    """A changed tree or context invalidates the evidence and is verified afresh."""

    def setUp(self) -> None:
        rewrite_support.RewriteEvidenceCase.setUp(self)

    def test_a_changed_tree_is_verified_afresh(self) -> None:
        # Both runs passed and printed different transcripts: the fresh one is
        # bound to the rewritten head as exactly what it printed, and the
        # settled one goes into history whole rather than being relabelled.
        self.rewrites(support.REBASED_SHA)
        self.outputs[support.SUITE] = rewrite_support.FRESH_OUTPUT

        decision = self.decide(support.REBASED_SHA)

        binding, commands = decision.fresh
        self.assertEqual(
            (decision.route, decision.invalidates, self.handed),
            (RewriteEvidenceRoute.FRESH, True, [(support.SUITE,)]),
        )
        self.assertEqual(
            (binding.source, binding.tested_sha, binding.tested_tree, binding.target.target_head),
            (EvidenceSource.ORCHESTRATOR_EXECUTED, support.REBASED_SHA, support.REBASED_TREE, support.REBASED_SHA),
        )
        self.assertEqual(
            (binding.target.subject, [(ran.command, ran.exit_status, ran.output) for ran in commands]),
            (self.state.get(_review_subjects.REVIEW_SUBJECT), [(support.SUITE, 0, rewrite_support.FRESH_OUTPUT)]),
        )
        self.assertNotEqual(commands, self.source.commands)
        self.assertTrue(decision.stages(self.state))
        retired = _settlement.read_evidence_history(self.state)[-1]
        self.assertEqual(
            (_settlement.read_current_evidence(self.state), retired.receipt, retired.retired, retired.binding),
            (None, self.source.receipt, _records.Retirement.INVALIDATED, self.source.binding),
        )
        fresh = _record_state.mint_pending_evidence(self.state, support.ISSUE_NUMBER, binding, commands)
        self.assertTrue(_record_state.record_pending_evidence(self.state, fresh))

    def test_a_moved_context_is_verified_afresh(self) -> None:
        # The squash keeps the tested tree, but the configuration grew a
        # command since the evidence was taken: nothing is carried, and the
        # fresh run binds every command with its own output.
        self.rewrites(support.SQUASHED_SHA)
        self.outputs[rewrite_support.LINT] = "All checks passed!"
        with patch.object(config, "VERIFY_COMMANDS", _SUITE_AND_LINT):
            decision = self.decide(support.SQUASHED_SHA)

        self.assertEqual(
            (decision.route, decision.invalidates, decision.carry, self.handed),
            (RewriteEvidenceRoute.FRESH, True, None, [_SUITE_AND_LINT]),
        )
        self.assertEqual(
            [(ran.command, ran.output) for ran in decision.fresh[1]],
            [(support.SUITE, f"{support.SUITE}: ok"), (rewrite_support.LINT, "All checks passed!")],
        )

    def test_a_failing_run_stays_actionable(self) -> None:
        # Nothing binds, and the run comes back whole: the failing command,
        # its exit status, and its output are what a park quotes.
        self.rewrites(support.REBASED_SHA)
        self.exits[support.SUITE] = rewrite_support.FAILED_EXIT
        self.outputs[support.SUITE] = rewrite_support.FAILED_OUTPUT

        decision = self.decide(support.REBASED_SHA)

        run = decision.run
        self.assertEqual(
            (decision.route, decision.invalidates, decision.fresh),
            (RewriteEvidenceRoute.FAILED, True, None),
        )
        self.assertEqual(
            (run.command, run.exit_code, run.output),
            (support.SUITE, rewrite_support.FAILED_EXIT, rewrite_support.FAILED_OUTPUT),
        )

    def test_a_pass_that_binds_nothing_is_no_pass(self) -> None:
        # The suite passed, but printed the fence its artifact closes with, so
        # no artifact can carry it: nothing is recorded as passing, and the
        # reviewer owes the evidence.
        self.rewrites(support.REBASED_SHA)
        self.outputs[support.SUITE] = "```\nclosed early"

        decision = self.decide(support.REBASED_SHA)

        self.assertEqual(
            (decision.route, decision.fresh, decision.run.status),
            (RewriteEvidenceRoute.REVIEWER, None, _verify_models.VERIFY_STATUS_OK),
        )
        self.assertIn("binds no evidence", decision.reason)


class ReviewerResponsibilityTest(unittest.TestCase, rewrite_support.RewriteEvidenceCase):
    """With nothing configured or nothing to bind to, nothing runs and the reviewer owes the evidence."""

    def setUp(self) -> None:
        rewrite_support.RewriteEvidenceCase.setUp(self)

    def test_empty_commands_run_and_pass_nothing(self) -> None:
        # The evidence was taken under the suite, so an empty configuration
        # is a moved context even over the tested tree.
        for head in (support.REBASED_SHA, support.SQUASHED_SHA):
            with self.subTest(head=head):
                self.setUp()
                self.rewrites(head)
                with patch.object(config, "VERIFY_COMMANDS", ()):
                    decision = self.decide(head)

                self.assertEqual(
                    (decision.route, decision.invalidates, decision.run, decision.fresh, decision.carry),
                    (RewriteEvidenceRoute.REVIEWER, True, None, None, None),
                )
                self.assertIn("no VERIFY_COMMANDS are configured", decision.reason)
                self.assertEqual(self.handed, [])

    def test_no_subject_of_the_head_runs_nothing(self) -> None:
        # A report and review of the head the rewrite replaced -- an approval
        # of it included -- are no binding for the rewritten one.
        for unbound, rewrites, head, refusal in _UNBOUND:
            with self.subTest(unbound=unbound):
                self.setUp()
                rewrites(self)
                with self.assertLogs(support.WORKFLOW_LOG, _LEVEL) as logged:
                    self.assertEqual(
                        self._unverified(head),
                        (RewriteEvidenceRoute.REVIEWER, head == support.REBASED_SHA, None, None, []),
                    )
                    self.assertIn(refusal, support.logged_refusal(logged))

    def _unverified(self, head: str) -> tuple:
        """The route, invalidation, carry, and run decided for `head`, and every run the runner was handed."""
        decision = self.decide(head)
        return (decision.route, decision.invalidates, decision.carry, decision.run, self.handed)


class MovedDuringVerificationTest(unittest.TestCase, rewrite_support.RewriteEvidenceCase):
    """A result something it is bound to moved under while it ran is eligible for nothing."""

    def setUp(self) -> None:
        rewrite_support.RewriteEvidenceCase.setUp(self)

    def test_a_move_during_the_run_disqualifies_it(self) -> None:
        # A failure is no failure of the rewritten head either, once the head
        # or anything else it is bound to has moved under it.
        for moved, moves, refusal in _MOVES:
            for exit_status in (0, rewrite_support.FAILED_EXIT):
                with self.subTest(moved=moved, exit_status=exit_status):
                    decision = self._moved_while_running(moves, exit_status)

                    self.assertEqual(
                        (
                            decision.route, decision.invalidates, decision.fresh,
                            decision.run.attempted_commands[-1].exit_code,
                        ),
                        (RewriteEvidenceRoute.MOVED, True, None, exit_status),
                    )
                    self.assertIn(refusal, decision.reason)

    def test_a_run_of_another_commit_disqualifies_it(self) -> None:
        # The checkout stood on the replaced head as the runner read its
        # baseline, and was back on the rebase before anything was read again:
        # neither a pass nor a failure there says anything about the rebase.
        for exit_status in (0, rewrite_support.FAILED_EXIT):
            with self.subTest(exit_status=exit_status):
                self.setUp()
                self.rewrites(support.REBASED_SHA)
                self.exits[support.SUITE] = exit_status
                self.checked_out = support.TESTED_SHA

                decision = self.decide(support.REBASED_SHA)

                self.assertEqual(
                    (decision.route, decision.fresh, decision.run.commit),
                    (RewriteEvidenceRoute.MOVED, None, support.TESTED_SHA),
                )
                self.assertIn("did not test the rewritten head", decision.reason)

    def _moved_while_running(self, moves, exit_status: int) -> RewriteEvidence:
        """The decision over the rebase whose suite exits `exit_status` while `moves` happens."""
        self.setUp()
        self.rewrites(support.REBASED_SHA)
        self.exits[support.SUITE] = exit_status
        self.during = moves
        with self.assertLogs(support.WORKFLOW_LOG, _LEVEL):
            return self.decide(support.REBASED_SHA)


if __name__ == "__main__":
    unittest.main()
