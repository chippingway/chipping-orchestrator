# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A poller that fetched the repository before it was renamed, beside one after.

The one started before is a real second process running its own dispatch seam
over a client described under the old name, in the namespace
`tests/support/writer_claim_processes.py` shares with the test.
"""
from __future__ import annotations

import contextlib

from tests.support.writer_claim_processes import DISPATCHING_POLLER, HELD, SharedNamespaceCase
from tests.workflow.engine.writer_claim_test_support import HeldIssuesCase

# The name another poller fetched the same repository under, before it was
# renamed to the one this process's client answers: a claim keyed on either
# name would meet no holder under the other.
PRE_RENAME_SLUG = "acme/widget-before-rename"


class RenamedRepositoryCase(SharedNamespaceCase, HeldIssuesCase):
    """The held-issue ticks, with the issues held by the poller started before the rename."""

    @contextlib.contextmanager
    def held_before_the_rename(self, *issue_numbers: int):
        """Hold these issues for the block, from the poller started before the rename."""
        poller = self.run_elsewhere(DISPATCHING_POLLER, self.github.repo_id, PRE_RENAME_SLUG, *issue_numbers)
        self.assertEqual(poller.said(), HELD, "the poller started before the rename holds them")
        yield
        self.assertEqual(poller.let_go(), 0)
