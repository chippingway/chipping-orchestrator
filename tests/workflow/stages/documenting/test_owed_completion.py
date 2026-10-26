# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A finished docs pass's completion that landed with its relabel lost, finished with no second pass.

The world is the retained-evidence one (`documenting_evidence_test_support`):
an approval squashed, its carry settled, and a docs pass that changes nothing,
whose completion records the carry as the evidence the unchanged head rests
on. Its write lands and the relabel behind it does not, so no receipt is left
-- only the completion, the stamp, and the approval they follow. The next
dispatch reads those as the pass finished and moves the issue into review,
running, writing, and announcing nothing. What tells that from a pass still
owed is the completion itself: a later approval retires the verdict its pass
was stamped with, and a completion that will not read is no completion, so
either runs the pass the approval bought.
"""
from __future__ import annotations

import contextlib
import unittest
from unittest.mock import MagicMock, patch

from orchestrator.workflow.engine import final_docs_records as _final_docs, review_subjects as _review_subjects
from tests.workflow import approved_squash as _approved_squash, review_world as _world
from tests.workflow.fixtures import LABEL_DOCUMENTING, LABEL_IN_REVIEW
from tests.workflow.stages.documenting import documenting_evidence_test_support as evidence

SQUASHED = _approved_squash.SQUASHED

RUN_AGENT = _world.RUN_AGENT

RETAINED = _final_docs.FinalVerification.RETAINED.value

# The completion the unchanged pass records, as its verification and both
# heads, beside the stamp: the squash the pass was entered and completed on.
COMPLETED = ((RETAINED, SQUASHED, SQUASHED), (SQUASHED, "no_change"))

# A completion's final head as a hand edit abbreviates it, which no record reads as.
_ABBREVIATED = SQUASHED[: len(SQUASHED) // 2]


class _RelabelLost(RuntimeError):
    """The relabel into review failing behind a completion that landed."""


class _RefusesReview:
    """The relabels a tick makes, refusing the move into review alone."""

    def __init__(self, relabels) -> None:
        self._relabels = relabels

    def __call__(self, issue, label):
        if label == LABEL_IN_REVIEW:
            raise _RelabelLost
        return self._relabels(issue, label)


class LandedCompletionTest(evidence.EvidenceWorld, unittest.TestCase):
    """A completion whose write landed is finished from what it recorded, and nothing else is."""

    def test_a_lost_relabel_is_finished_from_it(self) -> None:
        # The completion landed and the relabel did not: the next dispatch
        # moves the issue into review from the completion alone -- no docs
        # agent, no write, and no second notice.
        self.landed_with_its_relabel_lost()
        writes, notices = self.github.write_state_calls, len(self.pull_request.issue_comments)

        finished = self.dispatched()

        finished[RUN_AGENT].assert_not_called()
        self.assertEqual(self.labels(), (LABEL_DOCUMENTING, LABEL_IN_REVIEW))
        self.assertEqual(self.completed(), COMPLETED)
        written = (self.github.write_state_calls, len(self.pull_request.issue_comments))
        self.assertEqual(written, (writes, notices))

    def test_an_unfollowed_completion_runs_the_pass(self) -> None:
        # A later approval retires the verdict the finished pass was stamped
        # with, and a completion a hand edit damaged reads as none: neither
        # is a pass finished for the approval that stands, so the next
        # dispatch runs the docs pass that approval bought.
        for name, unsettles in (
            ("a later approval", self.approves_again),
            ("a damaged completion", self.damages_the_completion),
        ):
            with self.subTest(name):
                self.setUp()
                self.landed_with_its_relabel_lost()
                unsettles()

                rerun = self.documents()

                rerun[RUN_AGENT].assert_called_once()
                self.assertEqual(self.labels()[-1], LABEL_IN_REVIEW)

    def landed_with_its_relabel_lost(self) -> None:
        """Approve, squash, settle the carry, and pass the docs unchanged, with the relabel into review lost."""
        self.squashed()
        relabel = _RefusesReview(self.github.set_workflow_label)
        with patch.object(self.github, "set_workflow_label", relabel), contextlib.suppress(_RelabelLost):
            self.documents()
        self.assertEqual(self.labels(), (LABEL_DOCUMENTING,))
        self.assertEqual(self.completed(), COMPLETED)

    def dispatched(self) -> dict:
        """One dispatcher tick over the head the pull request stands on, with nothing to spawn."""
        head = self.pull_request.head.sha
        return _approved_squash.dispatches(
            self, self.github, self.issue, head, run_agent=MagicMock(), head_shas=(head,), checkout_tree=None,
        )

    def approves_again(self) -> None:
        """A later approval of the very subject the comment records, as its write leaves the comment.

        The subject recorded afresh, and the docs verdict an earlier approval's
        pass was stamped with retired beside it (`review_subjects.record_approved`).
        """
        approved = dict(self.pinned()[_review_subjects.APPROVED_SUBJECT])
        evidence.rewrites(self, {_review_subjects.APPROVED_SUBJECT: approved, evidence.DOCS_VERDICT: None})

    def damages_the_completion(self) -> None:
        """A hand edit abbreviating the completion's final head."""
        recorded = dict(self.pinned()[_final_docs.FINAL_DOCS])
        recorded["final_head"] = _ABBREVIATED
        evidence.rewrites(self, {_final_docs.FINAL_DOCS: recorded})

    def completed(self) -> tuple:
        """The completion as its verification and both heads, beside the stamp."""
        pinned = self.pinned()
        recorded = pinned.get(_final_docs.FINAL_DOCS) or {}
        return (
            (recorded.get("verification"), recorded.get("entry_head"), recorded.get("final_head")),
            (pinned.get(evidence.CHECKED_DOCS_SHA), pinned.get(evidence.DOCS_VERDICT)),
        )


if __name__ == "__main__":
    unittest.main()
