# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Which repositories the path sanitizer hands one checkout directory.

Driven from the configuration alone, because that is all the rule reads: every
repository's checkouts hang off one `WORKTREES_DIR` whatever clone it is on.
The flat `WORKTREES_DIR/issue-<n>` is never put to it -- no entry derives that
path -- and the inventory's own tests cover that against real checkouts.
"""

from __future__ import annotations

import logging
import unittest
from pathlib import Path

from orchestrator.git.worktrees import checkout_attribution
from tests.git.worktrees.artifact_test_support import (
    COLLIDING_SLUGS,
    GADGET_SLUG,
    LIFECYCLE_LOGGER,
    WIDGET_SLUG,
    _spec,
)

SHARED_CLONE = Path("/tmp/orchestrator-checkout-clone")


class WorktreeDirectoryTest(unittest.TestCase):
    """Entries the sanitizer cannot tell apart are refused together."""

    def test_a_shared_directory_refuses_both(self) -> None:
        specs = tuple(_spec(slug, SHARED_CLONE) for slug in COLLIDING_SLUGS)

        with self.assertLogs(LIFECYCLE_LOGGER, logging.WARNING) as logs:
            colliding = checkout_attribution._colliding_worktree_slugs(specs)
            refusal = logs.output[0]

        self.assertEqual(colliding, tuple(sorted(COLLIDING_SLUGS)))
        # Both claimants by name: an operator resolving this has to know which
        # two entries were handed the same directory.
        for slug in COLLIDING_SLUGS:
            with self.subTest(slug=slug):
                self.assertIn(slug, refusal)

    def test_distinct_directories_are_kept(self) -> None:
        specs = (
            _spec(WIDGET_SLUG, SHARED_CLONE), _spec(GADGET_SLUG, SHARED_CLONE),
        )

        self.assertEqual(
            checkout_attribution._colliding_worktree_slugs(specs), (),
        )


if __name__ == "__main__":
    unittest.main()
