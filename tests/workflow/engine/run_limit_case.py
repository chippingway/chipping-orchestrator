# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Parked-issue setup for agent-run exhaustion tests."""
from __future__ import annotations

import unittest

from orchestrator.workflow.engine import run_limit as _run_limit
from tests.workflow.engine import (
    run_limit_seeds as _limit_seeds,
    run_limit_test_support as support,
)


class _ParkCase(unittest.TestCase):
    """One issue the spent-ledger park is taken on, and the ledger it reads."""

    def setUp(self) -> None:
        client, issue = support.issue_and_client()
        self.gh = client
        self.issue = issue

    def _park(self, state) -> None:
        _run_limit._park_exhausted(
            self.gh, self.issue, state, _limit_seeds.ledger(), support.LAUNCH,
        )
