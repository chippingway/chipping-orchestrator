# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The notice a park over a manifest correction's attempt posts, measured as GitHub receives it.

Asked of the notice owed directly, over the correction world's armed attempt:
a notice whose post -- receipt and the orchestrator's comment marker included
-- fits one comment goes out whole, and one a single character past it goes
out as the words held on the record, cut to fit, rather than as a comment
GitHub refuses after the notice was held.
"""
from __future__ import annotations

import unittest

from orchestrator.github.pinned_state import MAX_PINNED_BODY
from orchestrator.workflow.engine import comments as _comments
from orchestrator.workflow.stages.decomposition import correction_notices as _notices
from tests.workflow.stages.decomposition import correction_test_support as support


class PostedNoticeTest(unittest.TestCase):
    """The notice owed fits one comment as posted, marker and all."""

    def test_the_post_fits_one_comment(self) -> None:
        for name, past in (("at the limit", 0), ("one past it", 1)):
            with self.subTest(name):
                message, notice = self._owed(past)

                self.assertLessEqual(len(_comments._with_orch_marker(notice)), MAX_PINNED_BODY)
                self.assertEqual(message in notice, not past, "whole only where it fits")

    def _owed(self, past: int) -> tuple[str, str]:
        """A notice whose post renders `past` characters beyond one comment, and what the park owes posting."""
        world = support.seeded()
        attempt = world.arms().reading.attempt
        rendered = len(_comments._with_orch_marker(_notices.receipted("", attempt)))
        message = "x" * (MAX_PINNED_BODY - rendered + past)
        notice = _notices.owing(world.github, world.issue, world.state, attempt, message)
        self.assertIsNotNone(notice)
        return message, notice


if __name__ == "__main__":
    unittest.main()
