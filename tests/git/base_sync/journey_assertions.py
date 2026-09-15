# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What an adjudicated candidate's rebase journey leaves, however it got there."""
from __future__ import annotations

from orchestrator.workflow.late_split import (
    exemption_reading as _exemption_reading,
    rewrite_reading as _rewrite_reading,
    rewrite_values as _rewrite_values,
)
from orchestrator.workflow.stages.implementing import late_publication_state as _late_publication_state
from tests.git.base_sync.exemption_git_support import ISSUE, events_of
from tests.git.base_sync.real_git_test_support import PR_NUMBER
from tests.workflow.fixtures import LABEL_DECOMPOSING, LABEL_VALIDATING

CLEAN_REBASE = "auto_clean_rebase"
RECOVERY_PUSHED = "crash_recovery_pushed"
RECOVERY_RELABELLED = "crash_recovery_relabel_only"

ADJUDICATOR = "decomposer"
REVIEWER = "reviewer"

# The record one interrupted attempt leaves, which every finish drops.
KEY_PENDING_PUSH_SHA = "pending_auto_base_rebase_push_sha"
KEY_PENDING_REWRITE_SHA = "pending_auto_base_rebase_rewrite_sha"


class JourneyAssertions:
    """The readings every leg of the journey is held to.

    Mixed into a journey fixture whose case has recorded `accepted`, the
    commit the adjudication accepted, and `adjudication`, the issue thread as
    that adjudication left it.
    """

    def _assert_decided_once(self, *roles: str) -> None:
        """One reading, one verdict, one agent run for them, and nothing said since.

        `roles` are the agents that ran after the adjudicator. The thread is
        compared whole, so a rebase or a recovery that measured or adjudicated
        again -- or only announced itself on the issue -- fails here.
        """
        self.assertEqual(len(events_of(self, "late_measurement")), 1)
        self.assertEqual(len(events_of(self, "late_verdict")), 1)
        self.assertEqual(self._gh.label_history.count((ISSUE, LABEL_DECOMPOSING)), 1)
        self.assertEqual(
            [record["agent_role"] for record in events_of(self, "agent_spawn")],
            [ADJUDICATOR, *roles],
        )
        self.assertEqual(self._issue_comments(), self.adjudication)
        self.assertTrue(all(self.accepted in body for body in self.adjudication))

    def _assert_rotated_onto(
        self, published: str, replaced: str, transfers: int = 1,
    ) -> None:
        """The verdict and the receipt are on this commit, each move reported.

        The receipt is read whole -- the commit, the head its push replaced,
        and the pull request it went onto -- since a verdict that moved over a
        receipt still naming the commit it came from is a publication nothing
        on the comment accounts for.
        """
        durable = self._durable()
        self.assertEqual(
            (
                _late_publication_state._published_commit(durable),
                _late_publication_state._published_lease(durable),
                _late_publication_state._published_pull_request(durable),
            ),
            (published, replaced, PR_NUMBER),
        )
        self.assertTrue(_exemption_reading.is_exempt(durable, published))
        self.assertEqual(
            _rewrite_reading.read_rewrite_authorization(durable).phase,
            _rewrite_values.LateRewritePhase.PUBLISHED,
        )
        self.assertEqual(len(events_of(self, "late_transfer")), transfers)

    def _assert_rebased_by(self, *methods: str) -> None:
        """The `base_rebased` records the journey filed, in order."""
        self.assertEqual(
            [record["method"] for record in events_of(self, "base_rebased")],
            list(methods),
        )

    def _assert_reviewable(self) -> None:
        """The attempt is gone, nothing is parked, and the round is the reviewer's."""
        durable = self._durable()
        self.assertIsNone(durable.get(KEY_PENDING_PUSH_SHA))
        self.assertIsNone(durable.get(KEY_PENDING_REWRITE_SHA))
        self.assertFalse(durable.get("awaiting_human"))
        self.assertEqual(durable.get("review_round"), 0)
        self.assertEqual(self._gh.workflow_label(self._issue()), LABEL_VALIDATING)
