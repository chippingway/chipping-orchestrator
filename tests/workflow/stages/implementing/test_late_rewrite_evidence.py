# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a squash tells the gate about the commit it replaced."""
from __future__ import annotations

import unittest

from orchestrator.workflow.late_split import rewrite_values as _rewrite_values
from orchestrator.workflow.stages.implementing import (
    late_gate_models as _late_gate_models,
    late_rewrite as _rewrite,
)
from orchestrator.workflow.state import WorkflowLabel

SHA_LENGTH = 40

# The commit the plan collapsed, the head the pull request is standing on, the
# merge base both sides are read over, and the object the squash produced.
COLLAPSED_SHA = "a" * SHA_LENGTH
STANDING_SHA = "b" * SHA_LENGTH
MERGE_BASE_SHA = "c" * SHA_LENGTH
SQUASHED_SHA = "d" * SHA_LENGTH

PR_NUMBER = 77
SOURCE_STAGE = WorkflowLabel.VALIDATING


class RewriteEvidenceTest(unittest.TestCase):
    """The pre-rewrite head and the lease are two facts, not one spelling.

    The entry checks the head a caller began at against the tip the pull
    request is on and admits one carve-out: a tip a durable record says this
    issue's own push put there. Past that carve-out the two really differ, and
    an exemption is carried on the commit that was COLLAPSED while the push is
    pinned to the tip the remote has.
    """

    def test_the_collapsed_head_is_not_the_lease(self) -> None:
        rewritten = self._rewritten(STANDING_SHA)

        self.assertEqual(rewritten.from_sha, COLLAPSED_SHA)
        self.assertEqual(rewritten.lease, STANDING_SHA)

    def test_both_contributions_share_the_merge_base(self) -> None:
        # A squash moves neither end of the branch's fork point; it rewrites
        # what sits on top of it.
        rewritten = self._rewritten(STANDING_SHA)

        self.assertEqual(rewritten.from_base_sha, MERGE_BASE_SHA)
        self.assertEqual(rewritten.to_base_sha, MERGE_BASE_SHA)
        self.assertEqual(rewritten.to_sha, SQUASHED_SHA)

    def test_the_publication_comes_from_the_entry(self) -> None:
        rewritten = self._rewritten(STANDING_SHA)

        self.assertEqual(rewritten.pr_number, PR_NUMBER)
        self.assertEqual(rewritten.source_stage, SOURCE_STAGE)
        self.assertEqual(rewritten.kind, _rewrite_values.LateRewriteKind.SQUASH)

    def test_an_unmoved_publication_names_them_alike(self) -> None:
        # The ordinary tick, where the tip the pull request is on IS the head
        # the squash collapsed -- which is why reading one off the other went
        # unnoticed until the carve-out separated them.
        rewritten = self._rewritten(COLLAPSED_SHA)

        self.assertEqual(rewritten.from_sha, COLLAPSED_SHA)
        self.assertEqual(rewritten.lease, COLLAPSED_SHA)

    def _rewritten(self, standing: str) -> _rewrite_values.LateRewrite:
        """The evidence a squash hands in for a publication standing here."""
        return _rewrite._rewritten(
            _late_gate_models._PublicationEntry(
                stage=SOURCE_STAGE,
                pr_number=PR_NUMBER,
                published_sha=standing,
            ),
            SQUASHED_SHA,
            _rewrite._Collapsed(
                head=COLLAPSED_SHA, base_sha=MERGE_BASE_SHA,
            ),
        )
