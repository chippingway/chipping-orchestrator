# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The proof that a settled report's approved commit was documented into the docs commit a recorded rewrite replaced.

Every case starts from the world a completed final docs pass leaves: the
approval of the settled report over the reviewer's evidence, squashed or not,
and a docs commit published over the head the pass was entered on, verified by
a run of its own and recorded as the completion. A base rebase of that docs
commit then records its report debt, naming the docs commit as the head
replaced. The completion is the provenance: proved where it covers the settled
report exactly, the entry head is the approved commit or a squash its carry
proves, and the docs commit descends from it. A later report, a debt about any
other head, a squash its carry no longer proves, and a docs commit off the
entry head's history prove nothing; a lineage git would not answer holds.
Reading the proof writes nothing. With no debt claimed at all, the published
docs commit is itself the rewrite of the head its pass was entered on, which a
review that comes back for it all the same is owed a report of.
"""
from __future__ import annotations

import unittest

from orchestrator.workflow.engine import report_docs_lineage as _lineage, report_rewrite_debt as _rewrite_debt
from orchestrator.workflow.engine.report_evidence_models import ReportEvidenceVerdict
from tests.workflow.engine import (
    final_docs_test_support as final_support,
    verification_evidence_test_support as support,
    verification_report_fixture as _report,
)
from tests.workflow.fixtures import _TEST_SPEC

DOCS = final_support.DOCS_SHA

REBASED = support.REBASED_SHA

DEFER = ReportEvidenceVerdict.DEFER

HOLD = ReportEvidenceVerdict.HOLD


def _later_report(case) -> None:
    """A later report settled about the docs commit, which the approval does not cover."""
    _report.settles_report(case, 2, _report.LATER_REPORT_TEXT, reviewed=False, head=DOCS)


def _retreed_squash(case) -> None:
    """The squash read as another tree than its carry recorded."""
    case.world.trees[support.SQUASHED_SHA] = support.REBASED_TREE


def _off_the_entry(case) -> None:
    """The docs commit read as not descending from the squash the pass was entered on."""
    case.world.descent[(support.SQUASHED_SHA, DOCS)] = False


def _unread_descent(case) -> None:
    """Git not answering whether the docs commit descends from the squash."""
    case.world.descent[(support.SQUASHED_SHA, DOCS)] = None


# What moves under a squashed completion, and what the proof then answers.
_MOVES = (
    ("a later report", _later_report, DEFER),
    ("a squash its carry no longer proves", _retreed_squash, DEFER),
    ("a docs commit off the entry head", _off_the_entry, DEFER),
    ("a descent git would not read", _unread_descent, HOLD),
)


class DocsLineageTest(unittest.TestCase, final_support.FinalDocsCase):
    """A rebase of a completed docs commit is linked to the settled report through the completion, and only so."""

    def setUp(self) -> None:
        final_support.FinalDocsCase.setUp(self)

    def test_a_completed_docs_commit_proves(self) -> None:
        # Squashed or not, the completion links the approved commit the
        # settled report is about to the docs commit the debt replaced, and
        # nothing is written.
        for squashed in (False, True):
            with self.subTest(squashed=squashed):
                self.setUp()
                self.rebases_the_docs(squashed=squashed)
                before = dict(self.state.state_data)

                proved = self.lineage()

                self.assertTrue(proved.proved, proved.refusal)
                self.assertEqual(self.gh.read_pinned_state(self.issue).state_data, before)

    def test_what_moved_proves_nothing(self) -> None:
        for name, moves, verdict in _MOVES:
            with self.subTest(name):
                self.setUp()
                self.rebases_the_docs(squashed=True)
                moves(self)
                self.gh.write_pinned_state(self.issue, self.state)

                self.assertEqual(self.lineage().verdict, verdict)

    def test_another_replaced_head_is_undocumented(self) -> None:
        # The debt names the squash as the head replaced -- the squash's own
        # lineage to prove -- so no completion's docs commit is in question.
        self.rebases_the_docs(squashed=True, replaced=support.SQUASHED_SHA)

        self.assertIsNone(_lineage.documented_into(self.state, support.SQUASHED_SHA))
        self.assertEqual(self.lineage().verdict, DEFER)

    def test_a_docs_commit_is_its_own_rewrite(self) -> None:
        # With no debt claimed, a completion that published a docs commit over
        # the approved report's commit is the rewrite of the head it was
        # entered on onto that commit; a later report, and a claim already
        # standing, leave nothing of it to stage.
        self.completes_as(final_support.EXECUTED, squashed=True)
        self.state = self.gh.read_pinned_state(self.issue)

        rewrite = _lineage.documented_rewrite(self.state)

        self.assertEqual((rewrite.previous_head, rewrite.rewritten_head), (support.SQUASHED_SHA, DOCS))
        self.state.set(_rewrite_debt.REWRITE_DEBT, rewrite.recorded())
        self.assertIsNone(_lineage.documented_rewrite(self.state))
        self.state.set(_rewrite_debt.REWRITE_DEBT, None)
        _later_report(self)
        self.assertIsNone(_lineage.documented_rewrite(self.state))

    def rebases_the_docs(self, *, squashed: bool, replaced: str = DOCS) -> None:
        """Complete a docs pass that published `DOCS`, then record a rebase of `replaced` onto `REBASED`."""
        self.completes_as(final_support.EXECUTED, squashed=squashed)
        self.moves_the_head(REBASED)
        self.state = self.gh.read_pinned_state(self.issue)
        debt = _rewrite_debt.RewriteDebt(
            pr_number=support.PR_NUMBER, branch=support.BRANCH, previous_head=replaced, rewritten_head=REBASED,
        )
        self.state.set(_rewrite_debt.REWRITE_DEBT, debt.recorded())
        self.gh.write_pinned_state(self.issue, self.state)

    def lineage(self):
        """What the proof says of the persisted comment, over the head the pull request stands on."""
        self.state = self.gh.read_pinned_state(self.issue)
        with self.seams():
            return _lineage.lineage_verdict(_TEST_SPEC, support.ISSUE_NUMBER, self.state, REBASED)


if __name__ == "__main__":
    unittest.main()
