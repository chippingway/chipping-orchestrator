# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The docs commit the size gate measures, and the pass a hold leaves owed.

A docs pass is the last push before a human is asked to merge, so it is
measured like every other candidate for a pull request the remote already
carries. A hold ends the tick with the pass itself finished, which is what the
receipt here is about: the adjudication publishes the commit and hands the
label back, and the tick that gets it has to finish the handoff rather than
read a branch in sync with its remote as an issue no docs pass has run for.
"""
from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from orchestrator import config
from orchestrator.git.measurement.models import (
    FrozenCommit,
    MeasurementFailure,
)
from tests.workflow.fixtures import MEASURED_CANDIDATE_SHA, _agent
from tests.workflow.mid_run_effects import _MovesThePullRequest
from tests.workflow.stages.documenting import (
    documenting_test_support as documenting_support,
)
from tests.workflow.stages.documenting.documenting_test_support import (
    _FreshDocumentingFixture,
)

DEV_SESSION = "dev-sess"

# The head a docs pass leaves the checkout on. Each IS the commit the size
# gate proves that checkout to, because in production they are one read of one
# worktree: the stage names the commit it means to publish and the gate
# refuses a checkout standing anywhere else, so a fixture that spelled them
# differently would be modelling the race rather than the tick.
SHA_AFTER = MEASURED_CANDIDATE_SHA
SHA_BEFORE = documenting_support.SHA_BEFORE

# A pull request somebody else pushed to while the docs agent was out.
MOVED_PR_HEAD = "cafef00d" * 5

# The ahead/behind reading a branch level with its remote answers.
IN_SYNC = (0, 0)

DOCS_VERDICT = "docs_verdict"
DOCS_CHECKED_SHA = "docs_checked_sha"
SETTLED_DOCS_SHA = "docs_settled_sha"
VERDICT_UPDATED = "updated"

DECOMPOSING = "workflow:decomposing"
IN_REVIEW = "in_review"

CEILING = 5
PAST_THE_CEILING = 6
MAX_ADDED_LINES = "MAX_ADDED_LINES"

RUN_AGENT = "run_agent"
PUSH_BRANCH = "_push_branch"
REVISION = "revision"

DOCS_REPLY = "docs: README tweak"

# A commit something else put on the checkout between the pass reading its own
# head and the gate proving that checkout for itself.
STRAY_COMMIT = "9a9a9a9a" * 5

# The head a settled verdict published, and the one a replacement host
# rebuilt from a moved pull request finds instead.
SETTLED_SHA = "5e771ed0" * 5
MOVED_HEAD = "0d0d0d0d" * 5

# A receipt no checkout can be compared to.
NOT_A_COMMIT = "nope"

CANDIDATE_ABSENT = MeasurementFailure.CANDIDATE_ABSENT


class DocumentingSizeGateTest(
    unittest.TestCase,
    _FreshDocumentingFixture,
):
    """A docs commit is measured before it joins the pull request it is for."""

    def test_an_oversized_docs_commit_is_held(self) -> None:
        # The docs push is the last one before a human is asked to merge,
        # which is what makes it matter rather than what makes it an
        # exception: a pass that took the diff past the ceiling would put an
        # unadjudicated pull request in front of the person who merges it.
        oversized = self._seeded()

        with patch.object(config, MAX_ADDED_LINES, CEILING):
            mocks = self._run_documenting(
                *oversized,
                run_agent=_agent(
                    session_id=DEV_SESSION,
                    last_message="docs: README tweak",
                ),
                push_branch=True,
                head_shas=[SHA_BEFORE, SHA_AFTER],
                branch_ahead_behind=IN_SYNC,
                added_lines=PAST_THE_CEILING,
            )

        mocks[PUSH_BRANCH].assert_not_called()
        routed = [label for _, label in oversized[0].label_history]
        self.assertEqual(routed, [DECOMPOSING])
        # The pass is over -- an agent ran and committed -- so the head it
        # produced is left as the receipt the handoff is still owed.
        self.assertEqual(
            oversized[0].pinned_data(self.issue_number).get(SETTLED_DOCS_SHA),
            SHA_AFTER,
        )

    def test_a_settled_commit_hands_off(self) -> None:
        # A settled `single` verdict publishes the held commit from the
        # adjudication and hands the label back here. The branch is in sync
        # with its remote by then, which is the reading an issue no docs pass
        # has run for gives -- so without the receipt this tick would spawn a
        # second docs agent over work the first one already published, commit
        # again, and hand the gate a candidate to adjudicate a second time.
        gh, issue = self._settled_docs_commit()

        mocks = self._run_documenting(
            gh, issue,
            run_agent=MagicMock(),
            head_shas=[SHA_AFTER],
            branch_ahead_behind=IN_SYNC,
        )

        mocks[RUN_AGENT].assert_not_called()
        mocks[PUSH_BRANCH].assert_not_called()
        self.assertIn((self.issue_number, IN_REVIEW), gh.label_history)
        state = gh.pinned_data(self.issue_number)
        self.assertEqual(state.get(DOCS_VERDICT), VERDICT_UPDATED)
        self.assertEqual(state.get(DOCS_CHECKED_SHA), SHA_AFTER)
        self.assertIsNone(state.get(SETTLED_DOCS_SHA))

    def test_an_unpublished_receipt_is_measured(self) -> None:
        # The receipt alone cannot say the commit reached the remote: a
        # verdict that parked, or a human who moved the label by hand, leaves
        # the same receipt over a commit still on disk. Ahead of the remote it
        # stands, and the recovered-commit path carries it through the gate,
        # which is the one road that measures it again.
        gh, issue = self._settled_docs_commit()

        mocks = self._run_documenting(
            gh, issue,
            run_agent=MagicMock(),
            head_shas=[SHA_AFTER],
            branch_ahead_behind=(1, 0),
            push_branch=True,
            added_lines=1,
        )

        mocks[RUN_AGENT].assert_not_called()
        mocks[PUSH_BRANCH].assert_called_once()
        self.assertIn((self.issue_number, IN_REVIEW), gh.label_history)
        self.assertIsNone(
            gh.pinned_data(self.issue_number).get(SETTLED_DOCS_SHA),
        )

    def _settled_docs_commit(self):
        """A docs pass the gate held and an adjudication has since settled."""
        return self._seeded(docs_settled_sha=SHA_AFTER)


class DocumentingCandidateBindingTest(
    unittest.TestCase,
    _FreshDocumentingFixture,
):
    """The commit this pass publishes is the commit this pass made."""

    def test_a_checkout_that_moved_publishes_nothing(self) -> None:
        # The stage reads the head its docs commit left, and the gate proves
        # the checkout again for itself. Between the two the worktree is
        # writable -- so a commit landing there would be measured and pushed
        # while the stamp below recorded the id the pass read as documented.
        gh, issue = self._seeded()

        mocks = self._run_documenting(
            gh, issue,
            run_agent=_agent(session_id=DEV_SESSION, last_message=DOCS_REPLY),
            push_branch=True,
            head_shas=[SHA_BEFORE, SHA_AFTER],
            branch_ahead_behind=IN_SYNC,
            added_lines=1,
            candidate_commit=FrozenCommit(sha=STRAY_COMMIT),
        )

        mocks[PUSH_BRANCH].assert_not_called()
        state = gh.pinned_data(self.issue_number)
        # The pre-spawn watermark stands; what must not be recorded is the
        # head this pass made, which nothing published.
        self.assertNotEqual(state[DOCS_CHECKED_SHA], SHA_AFTER)
        self.assertNotIn(DOCS_VERDICT, state)
        self.assertNotIn((self.issue_number, IN_REVIEW), gh.label_history)

    def test_a_publication_that_moved_mid_run_refuses(self) -> None:
        # The race the pass's own head closes, on the last push before a human
        # is asked to merge. The pull request was standing on A when the
        # reviewer approved it and this pass began there; somebody pushed B
        # while the agent was out, and the agent committed C on top of A. Read
        # afterwards, B becomes the lease and this force-push drops it -- and
        # what it drops is what that human would then not see.
        moved, moved_issue = self._seeded()

        mocks = self._run_documenting(
            moved, moved_issue,
            run_agent=_MovesThePullRequest(
                moved.get_pr(self.pr_number),
                MOVED_PR_HEAD,
                _agent(session_id=DEV_SESSION, last_message=DOCS_REPLY),
            ),
            push_branch=True,
            head_shas=[SHA_BEFORE, SHA_AFTER],
            branch_ahead_behind=IN_SYNC,
            added_lines=1,
        )

        mocks[PUSH_BRANCH].assert_not_called()
        self.assertNotIn((self.issue_number, IN_REVIEW), moved.label_history)
        # And the pull request is left exactly where the other push put it.
        self.assertEqual(moved.get_pr(self.pr_number).head.sha, MOVED_PR_HEAD)

    def test_an_agreeing_checkout_publishes(self) -> None:
        # What says the refusal above is about the disagreement rather than
        # about the binding refusing every pass it stands in front of.
        gh, issue = self._seeded()

        mocks = self._run_documenting(
            gh, issue,
            run_agent=_agent(session_id=DEV_SESSION, last_message=DOCS_REPLY),
            push_branch=True,
            head_shas=[SHA_BEFORE, SHA_AFTER],
            branch_ahead_behind=IN_SYNC,
            added_lines=1,
        )

        self.assertEqual(
            mocks[PUSH_BRANCH].call_args.kwargs[REVISION], SHA_AFTER,
        )
        self.assertIn((self.issue_number, IN_REVIEW), gh.label_history)


class SettledDocsProofTest(
    unittest.TestCase,
    _FreshDocumentingFixture,
):
    """What a settled receipt is proved against before it is consumed."""

    def test_a_moved_head_leaves_the_receipt(self) -> None:
        # In sync is not the same claim as carrying it. A replacement host
        # rebuilds the checkout from a pull request that has moved on, and
        # what it gets is a branch level with its remote and standing on
        # somebody else's head -- so the docs pass would be reported over a
        # commit this branch does not have.
        gh, issue = self._seeded(docs_settled_sha=SETTLED_SHA)

        mocks = self._run_documenting(
            gh, issue,
            run_agent=MagicMock(),
            head_shas=[MOVED_HEAD],
            branch_ahead_behind=IN_SYNC,
            candidate_commit=FrozenCommit(sha=MOVED_HEAD),
        )

        self._assert_unclaimed(gh, mocks)

    def test_an_unreadable_head_leaves_the_receipt(self) -> None:
        # A revision this host cannot peel is not a head anything may be
        # compared against, which is what a checkout the commit never reached
        # answers with.
        gh, issue = self._seeded(docs_settled_sha=SETTLED_SHA)

        mocks = self._run_documenting(
            gh, issue,
            run_agent=MagicMock(),
            head_shas=[MOVED_HEAD],
            branch_ahead_behind=IN_SYNC,
            candidate_commit=FrozenCommit(failure=CANDIDATE_ABSENT),
        )

        self._assert_unclaimed(gh, mocks)

    def test_a_receipt_that_is_no_id_is_refused(self) -> None:
        # Read fail-closed like every other commit field: a hand-edited value
        # is no receipt, and comparing a checkout to it would compare it to
        # nothing.
        gh, issue = self._seeded(docs_settled_sha=NOT_A_COMMIT)

        mocks = self._run_documenting(
            gh, issue,
            run_agent=MagicMock(),
            head_shas=[SETTLED_SHA],
            branch_ahead_behind=IN_SYNC,
        )

        self._assert_unclaimed(gh, mocks)

    def _assert_unclaimed(self, gh, mocks) -> None:
        """The receipt stands and nothing is handed on behind it."""
        state = gh.pinned_data(self.issue_number)
        self.assertNotIn(DOCS_CHECKED_SHA, state)
        self.assertNotIn((self.issue_number, IN_REVIEW), gh.label_history)
        mocks[PUSH_BRANCH].assert_not_called()
