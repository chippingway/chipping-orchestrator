# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The current evidence a finish of the attempt settled for its landed head, told from any other.

The settled case (`rewrite_captured_test_support.SettledEvidenceCase`): the
landed head's run settled under the anchor, the attempt still standing. That
evidence is the attempt's while the receipt the finish put on the attempt
names it, or -- on an attempt that carries no receipt -- while its record names
the evidence's head as the replay or its mark names it as announced. Evidence
about any other head, and no current evidence at all, is none of its.
"""
from __future__ import annotations

import unittest
from types import MappingProxyType

from orchestrator.workflow.engine import (
    rewrite_landing_records as _landing_records,
    verification_settlement_state as _settlement,
)
from tests.workflow.engine import (
    rewrite_captured_test_support as settled_support,
    verification_evidence_test_support as support,
)
from tests.workflow.engine.rewrite_finish_readings import KEY_ANNOUNCED, KEY_EVIDENCE_RECEIPT, KEY_REWRITE_SHA

# An attempt that carries no receipt, its record naming another head as its replay.
_UNRECEIPTED = MappingProxyType({KEY_EVIDENCE_RECEIPT: None, KEY_REWRITE_SHA: support.SQUASHED_SHA})

# What the attempt carries beside the evidence, and whether that evidence is its own.
_ATTEMPTS = (
    ("under the finish's receipt, whatever replay the record names", {KEY_REWRITE_SHA: support.SQUASHED_SHA}, True),
    ("the replay an unreceipted attempt names", {KEY_EVIDENCE_RECEIPT: None}, True),
    ("the head an unreceipted attempt announced", {**_UNRECEIPTED, KEY_ANNOUNCED: settled_support.REBASED}, True),
    ("about a head the attempt never named", _UNRECEIPTED, False),
    ("under another receipt", {**_UNRECEIPTED, KEY_EVIDENCE_RECEIPT: "another-receipt"}, False),
)


class SettledReadingTest(settled_support.SettledEvidenceCase, unittest.TestCase):
    """Only the evidence a finish of the standing attempt settled reads as its own."""

    def test_only_the_attempts_own_is_settled(self) -> None:
        for name, carried, owned in _ATTEMPTS:
            with self.subTest(name):
                state = self.gh.read_pinned_state(self.issue)
                state.data.update(carried)

                self.assertEqual(_landing_records.settled(state), self.settled if owned else None)

        state = self.gh.read_pinned_state(self.issue)
        self.assertTrue(_settlement.retire_current_evidence(state))
        self.assertIsNone(_landing_records.settled(state))


if __name__ == "__main__":
    unittest.main()
