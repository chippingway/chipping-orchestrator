# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""One oversized change, adjudicated once and reviewed again, on a real repo.

The whole road an accepted candidate takes when the base moves under it, with
nothing about it seeded. A `workflow:validating` publication the real counter
reads past the ceiling is held by the real size gate; the real adjudicator
answers `single`, an operator authorizes it, and the settlement records the
exemption and the digest of what that commit contributes over the pair it
froze. Then the base advances on the real remote and the per-tick refresh
replays the branch onto it and force-publishes the result through the same
gate.

That replay is a commit no human ever saw, and everything here turns on it
being recognized as the change they already ruled on: the exemption and the
receipt move onto it, the push is leased to the head the pull request was
standing on, and the real reviewer goes round again over it -- with one
measurement, one verdict, one adjudicator run, and the adjudication's own
comments for the life of the issue.
"""
from __future__ import annotations

import unittest

from orchestrator.workflow.late_split import exemption_reading as _exemption_reading
from tests.git.base_sync.exemption_git_support import events_of
from tests.git.base_sync.journey_adjudication_support import adjudicates_once
from tests.git.base_sync.journey_assertions import CLEAN_REBASE, REVIEWER, JourneyAssertions
from tests.git.base_sync.journey_git_support import OversizedJourneyRealGitFixture
from tests.git.base_sync.journey_push_support import BEFORE_THE_REBASE
from tests.workflow.fixtures import LABEL_DOCUMENTING

# A second base advance needs a commit of its own: the first one writes a
# fixed file with fixed content.
SECOND_ADVANCE_FILE = "later.txt"
SECOND_ADVANCE_BODY = "later base side\n"


class AdjudicatedRebaseJourneyTest(
    JourneyAssertions, OversizedJourneyRealGitFixture, unittest.TestCase,
):
    """The change a human ruled on, carried through the base advance under it."""

    def setUp(self) -> None:
        super().setUp()
        self.accepted = self._commits_an_oversized_candidate()
        adjudicates_once(self, self.accepted)
        self.adjudication = self._issue_comments()
        self._advance_base(conflicting=False)
        self.pushed = self._refreshes()

    def test_the_replay_carries_the_verdict_over(self) -> None:
        # The replay is named against the commit the gate proved and leased to
        # the head the pull request was standing on, so a branch somebody else
        # moved rejects it instead of being overwritten. The exemption, its
        # identity over the new fork point, and the receipt are all on the far
        # side of it, and the reviewer's spent round is reset for a new head.
        replayed = self._wt_head()
        self.assertNotEqual(replayed, self.accepted)
        self.assertEqual(
            (self.pushed.revision, self.pushed.force_with_lease),
            (replayed, self.accepted),
        )
        self._assert_rotated_onto(replayed, self.accepted)
        self.assertEqual(
            _exemption_reading.read_semantic_identity(self._durable()).base_sha,
            self._merge_base(),
        )
        self._assert_rebased_by(CLEAN_REBASE)
        self._assert_reviewable()
        self._assert_decided_once()

    def test_the_review_reruns_on_one_adjudication(self) -> None:
        # The real `workflow:validating` tick over the rewritten checkout: one
        # reviewer run and an approval that carries the issue on, while the
        # journey still counts the one reading, verdict, adjudicator run, and
        # thread. The approval squashes the head again and the exemption is
        # past that rewrite too, so a later reading finds the change decided.
        reviewer = self._reviews()

        reviewer.assert_called_once()
        self.assertEqual(
            [record["verdict"] for record in events_of(self, "review_verdict")],
            ["approved"],
        )
        self.assertEqual(self._gh.workflow_label(self._issue()), LABEL_DOCUMENTING)
        self._assert_decided_once(REVIEWER)
        approved = self._wt_head()
        self.assertNotEqual(approved, self.accepted)
        self.assertTrue(_exemption_reading.is_exempt(self._durable(), approved))

    def test_a_second_advance_rotates_it_again(self) -> None:
        # A settled transfer is never cleared, so it still stands when the next
        # advance anchors a rebase to the commit that transfer rotated onto --
        # and a tick lost before that rebase comes back to it. Read as a claim
        # about the new attempt it would be a permission leased elsewhere; the
        # permit licenses the second replay rather than a second adjudication.
        rotated = self._wt_head()
        self._commit_to_base(SECOND_ADVANCE_FILE, SECOND_ADVANCE_BODY)
        self._refreshes(BEFORE_THE_REBASE)

        self._refreshes()

        replayed = self._wt_head()
        self.assertNotEqual(replayed, rotated)
        self._assert_rotated_onto(replayed, rotated, transfers=2)
        self._assert_rebased_by(CLEAN_REBASE, CLEAN_REBASE)
        self._assert_reviewable()
        self._assert_decided_once()


if __name__ == "__main__":
    unittest.main()
