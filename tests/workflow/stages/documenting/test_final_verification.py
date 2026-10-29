# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The documenting stage verifies the head a final docs pass completed on, and records only what is true of it.

An unchanged head runs nothing and names the evidence the approval rests on,
as it settled; a changed head under an empty `VERIFY_COMMANDS` runs nothing
and names no evidence at all. A changed head under a configuration runs the
configured commands on exactly that head, and the run it binds is recorded
beside the completion naming it, landed through the stage's guarded write,
and published and settled by the dispatcher's reconciliation -- a post whose
response was lost found again by its receipt rather than posted twice. The
approval, its report, and its evidence stay exactly as they were, and the
docs commit's run is published as a run of that commit over the approved
review.

A run that failed, one of another commit or under another configuration, a
passing run that binds nothing, and an issue with no approval to follow each
stage nothing at all.
"""
from __future__ import annotations

import dataclasses
import unittest
from unittest.mock import MagicMock, patch

from orchestrator import config
from orchestrator.git.verification import models as _verify_models
from orchestrator.github.verification_evidence import EvidenceSource
from orchestrator.workflow.engine import (
    report_commits as _commits,
    review_subjects as _review_subjects,
    verification_records as _records,
    verification_settlement_state as _settlement,
)
from orchestrator.workflow.stages.documenting import final_verification as _final_verification, models as _models
from tests.workflow.engine import (
    final_docs_test_support as final_support,
    verification_evidence_test_support as support,
)
from tests.workflow.fixtures import _TEST_SPEC
from tests.workflow.git_owners import seam_patch

_ROUTE = _final_verification.FinalRoute

_FAILED_EXIT = 1

_OTHER_CONTEXT = "0" * len(support.TESTED_TREE)


def _run(**fields) -> _verify_models.VerifyResult:
    """A passing run of the configured suite on the docs commit, any field replaced."""
    configured = tuple(config.VERIFY_COMMANDS)
    ran = _verify_models.VerifyCommandOutcome(
        command=support.SUITE,
        status=_verify_models.VERIFY_STATUS_OK,
        exit_code=0,
        output="12 passed",
        head_before=final_support.DOCS_SHA,
        head_after=final_support.DOCS_SHA,
        tree_before=final_support.DOCS_TREE,
        tree_after=final_support.DOCS_TREE,
    )
    recorded = {
        "status": _verify_models.VERIFY_STATUS_OK,
        "commit": final_support.DOCS_SHA,
        "tree_identity": final_support.DOCS_TREE,
        "configured_commands": configured,
        "attempted_commands": (ran,),
        "timeout": config.VERIFY_TIMEOUT,
        "context_revision": _verify_models._context_revision(configured, config.VERIFY_TIMEOUT),
    }
    return _verify_models.VerifyResult(**(recorded | fields))


def _failed_run() -> _verify_models.VerifyResult:
    """The suite run on the docs commit and failing there."""
    failed = dataclasses.replace(
        _run().attempted_commands[0], status=_verify_models.VERIFY_STATUS_FAILED, exit_code=_FAILED_EXIT,
    )
    return _run(status=_verify_models.VERIFY_STATUS_FAILED, attempted_commands=(failed,))


class _FinalVerificationCase(final_support.FinalDocsCase):
    """A docs pass about to complete, with the verify runner answering `self.answer`."""

    def setUp(self) -> None:
        final_support.FinalDocsCase.setUp(self)
        self.answer = None
        self.runs = 0

    def verifies(self, final_head: str) -> _final_verification.FinalOutcome:
        """Verify `final_head` over the persisted comment, counting the runs the runner was asked for."""
        self.state = self.gh.read_pinned_state(self.issue)
        ctx = _models._DocumentingContext(
            self.gh, _TEST_SPEC, self.issue, self.state, support.BRANCH, support.PR_NUMBER,
        )
        runner = MagicMock(return_value=self.answer)
        with seam_patch("_run_verify_commands", runner), self.seams():
            verified = _final_verification.verifies_final_head(ctx, self.entry_head, final_head)
        self.runs = runner.call_count
        return verified

    def lands(self) -> None:
        """Land what was staged through the stage's guarded write, which has to commit."""
        commit = _commits.ReportCommit(self.gh, self.issue, self.state)
        self.assertIsNone(commit.lands(self.state, _final_verification.VERIFIED).refusal)

    def lands_a_docs_run(self) -> _final_verification.FinalOutcome:
        """Publish the docs commit, verify it with a passing run, and land what that records."""
        self.moves_the_head(final_support.DOCS_SHA)
        self.answer = _run()
        verified = self.verifies(final_support.DOCS_SHA)
        self.lands()
        return verified


class RecordedVerificationTest(unittest.TestCase, _FinalVerificationCase):
    """What each final head records, and the reconciliation settling a run of it."""

    def setUp(self) -> None:
        _FinalVerificationCase.setUp(self)

    def test_an_unchanged_head_runs_nothing(self) -> None:
        # The unchanged squash keeps the carry the approval rests on, its
        # tested commit the approved one, named as it settled.
        approved = self.approves(squashed=True)

        verified = self._verifies_unrun(approved)

        self.assertEqual(
            (verified.final.verification, verified.final.evidence.receipt),
            (final_support.RETAINED, approved.receipt),
        )

    def test_no_configuration_runs_nothing(self) -> None:
        # A docs commit under no configuration names no evidence at all.
        self.enterContext(patch.object(config, "VERIFY_COMMANDS", ()))
        approved = self.approves(squashed=True)
        self.moves_the_head(final_support.DOCS_SHA)

        verified = self._verifies_unrun(approved)

        self.assertEqual(
            (verified.final.verification, verified.final.evidence),
            (final_support.UNCONFIGURED, None),
        )

    def test_a_docs_run_settles_as_its_own_run(self) -> None:
        approved = self.approves(squashed=True)

        verified = self.lands_a_docs_run()
        self.assertFalse(self.reconcile())

        current = _settlement.read_current_evidence(self.state)
        published = self.artifacts()[-1]
        self.assertEqual(
            (verified.route, verified.final.evidence.receipt, current.binding.source, current.passed),
            (_ROUTE.RECORDED, current.receipt, EvidenceSource.ORCHESTRATOR_EXECUTED, True),
        )
        self.assertEqual(
            (published.tested_sha, published.target_head, published.review_subject),
            (final_support.DOCS_SHA, final_support.DOCS_SHA, support.TESTED_SHA),
        )
        superseded = _settlement.read_evidence_history(self.state)[-1]
        self.assertEqual(
            (superseded.binding, superseded.retired),
            (approved.binding, _records.Retirement.SUPERSEDED),
        )
        self.assertEqual(self.state.get(_review_subjects.APPROVED_SUBJECT), self.subject.recorded())
        self.assertTrue(self.verdict().proved)

    def test_a_lost_post_is_found_again(self) -> None:
        self.approves()
        self.lands_a_docs_run()
        self.gh.report_failures.lost.add(support.PR_NUMBER)
        with self.assertLogs("orchestrator.github", "WARNING"):
            self.assertTrue(self.reconcile())
        self.gh.report_failures.lost.clear()
        landed = self.pull_request.issue_comments[-1]

        self.assertFalse(self.reconcile())

        heads = [posted.target_head for posted in self.artifacts()]
        self.assertEqual(_settlement.read_current_evidence(self.state).comment_id, landed.id)
        self.assertEqual(heads.count(final_support.DOCS_SHA), 1)
        self.assertTrue(self.verdict().proved)

    def _verifies_unrun(self, approved: _records.CurrentEvidence) -> _final_verification.FinalOutcome:
        """Verify the pull request's head and land it, with nothing run, minted, posted, or moved off `approved`."""
        unchanged = (self.state.get(_records.REVISION_FLOOR), self.artifacts(), approved)

        verified = self.verifies(self.pull_request.head.sha)
        self.lands()
        self.reconcile()

        moved = (
            self.state.get(_records.REVISION_FLOOR),
            self.artifacts(),
            _settlement.read_current_evidence(self.state),
        )
        self.assertEqual(
            (verified.route, self.runs, moved),
            (_ROUTE.RECORDED, 0, unchanged),
        )
        self.assertTrue(self.verdict().proved)
        return verified


class UnrecordedVerificationTest(unittest.TestCase, _FinalVerificationCase):
    """A final head nothing verifies stages nothing."""

    def setUp(self) -> None:
        _FinalVerificationCase.setUp(self)

    def test_what_verifies_nothing_records_nothing(self) -> None:
        cases = (
            ("a failing run", _failed_run(), _ROUTE.FAILED),
            ("a run of another commit", _run(commit=support.TESTED_SHA), _ROUTE.MOVED),
            ("a run under another configuration", _run(context_revision=_OTHER_CONTEXT), _ROUTE.MOVED),
            ("a passing run binding nothing", _run(attempted_commands=()), _ROUTE.UNBOUND),
            ("no approval to follow", None, _ROUTE.UNBOUND),
        )
        for named, answer, route in cases:
            with self.subTest(named):
                self.setUp()
                self._records_nothing(answer, route)

    def _records_nothing(self, answer: _verify_models.VerifyResult | None, route) -> None:
        """Verify the docs commit with the runner answering `answer`, which comes to `route` and stages nothing.

        No answer is an issue with no approval to follow, which runs nothing.
        """
        self.approves()
        self.moves_the_head(final_support.DOCS_SHA)
        if answer is None:
            self.persists(_review_subjects.APPROVED_SUBJECT, None)
        self.answer = answer
        persisted = dict(self.gh.read_pinned_state(self.issue).state_data)

        verified = self.verifies(final_support.DOCS_SHA)

        self.assertEqual(
            (verified.route, verified.final, verified.run, self.state.state_data),
            (route, None, answer, persisted),
        )
        self.assertEqual(self.runs, int(answer is not None))


if __name__ == "__main__":
    unittest.main()
