# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Issue #7's settled run under a later finish, and what moves the attempt or the evidence records under it.

The settled case (`rewrite_captured_test_support.SettledEvidenceCase`): the
landed head's run settled under the anchor and the finish dead before
announcing it, the run ledger charged by another road's launch
(`settled_finish_support.charges`). A case asks one retirement primitive
directly over the finish a later recovery holds, built over the comment as it
reads (`landed`), while another finish
of the landing announces the head on the attempt (`announces`) or routes it,
retiring the attempt (`routes`), or marks movement under the run in its
handoff's place (`marks_the_run`), or another road pins an attempt of its own
(`replaces`) -- its anchor any JSON value at all -- settles a newer run under
its own receipt (`supersedes`), or leaves the handoff null
(`drops_the_handoff`). It reads back that nothing was
posted, run, launched, relabelled, or charged (`assert_untouched`), and the
run marked (`assert_marked`) or invalidated whole (`assert_whole`).
"""
from __future__ import annotations

from orchestrator.workflow.engine import (
    verification_records as _records,
    verification_settlement_state as _settlement,
)
from tests.workflow.engine import (
    rewrite_captured_test_support as settled_support,
    rewrite_finish_evidence_test_support as finish_support,
    rewrite_finish_readings as readings,
    rewrite_settled_moves as settled_moves,
    settled_finish_support as settled,
    verification_evidence_test_support as support,
)


def announces(case, head: str = settled_support.REBASED) -> None:
    """The mark and the record of the event another finish of the landing puts on the attempt for `head`."""
    state = case.gh.read_pinned_state(case.issue)
    state.set(readings.KEY_ANNOUNCED_EVENT, head)
    state.set(readings.KEY_ANNOUNCED, head)
    case.gh.write_pinned_state(case.issue, state)


def routes(case) -> None:
    """Another finish's route of the landing, retiring the attempt whole."""
    state = case.gh.read_pinned_state(case.issue)
    for key in readings.ATTEMPT_KEYS:
        state.set(key, None)
    case.gh.write_pinned_state(case.issue, state)


def replaces(case, written: object = support.SQUASHED_SHA) -> None:
    """Another road's attempt pinned in place of the landing's, its anchor spelled `written`."""
    settled_moves.writes_over(case, readings.KEY_PENDING_PUSH, written)


def supersedes(case) -> None:
    """Another road's newer run of the head, settled over the evidence under a receipt of its own."""
    newer = settled_moves.records_a_newer_one(case)
    state = case.gh.read_pinned_state(case.issue)
    posted = case.gh.publish_verification_artifact(case.pull_request, newer.artifact)
    case.gh.write_pinned_state(case.issue, _settlement.settled_state(
        state, newer, posted.landed_id, finish_support.REVIEWING,
    ))


def marks_the_run(case) -> None:
    """Another finish's mark of movement read under the settled run, written in its handoff's place."""
    settled_moves.writes_over(case, _records.EVIDENCE_HANDOFF, {"moved": case.settled.receipt})


def drops_the_handoff(case) -> None:
    """Another road leaving the evidence handoff null, so a mark in its place grows the comment."""
    settled_moves.writes_over(case, _records.EVIDENCE_HANDOFF, None)


class RetirementCase(settled_support.SettledEvidenceCase):
    """The settled case, its run ledger charged, asked over the finish a later recovery holds."""

    def setUp(self) -> None:
        settled_support.SettledEvidenceCase.setUp(self)
        settled.charges(self)
        self.artifacts_before = len(self.artifacts())

    def pinned(self) -> dict:
        """The record the pinned comment carries now."""
        return readings.pinned(self)

    def forgets(self, missing: tuple) -> None:
        """Take the attempt members `missing` off the comment, as an attempt pinned before they existed carries none."""
        pinned = self.pinned()
        for member in missing:
            pinned.pop(member)
        self.puts_back(pinned)

    def assert_untouched(self, attempt=None) -> None:
        """Nothing posted, run, launched, relabelled, or charged; the attempt as `attempt` spells it, where given.

        `artifacts_before` counts the artifacts a case expects, another road's
        among them.
        """
        self.assertEqual(len(self.artifacts()), self.artifacts_before)
        self.assertEqual((self.verify.call_count, self.developer.call_count), (0, 0))
        self.assertEqual(readings.relabels(self), ())
        settled.assert_charged_as_left(self)
        if attempt is not None:
            self.assertEqual(readings.attempt(self.pinned()), attempt)

    def assert_marked(self) -> None:
        """The run kept current, the mark of movement read under its receipt in its handoff's place."""
        marked = {"moved": self.settled.receipt}
        self.assertEqual(self.pinned()[_records.EVIDENCE_HANDOFF], marked)
        self.assertEqual(self.records()[1], self.settled)

    def assert_whole(self) -> None:
        """The run invalidated into history whole -- revision, transcript, and provenance kept -- nothing current."""
        history = _settlement.read_evidence_history(self.gh.read_pinned_state(self.issue))
        invalidated = _records.HistoricalEvidence.of(self.settled, _records.Retirement.INVALIDATED)
        self.assertEqual(history[-1], invalidated)
        self.assertEqual(self.records(), self.invalidated_whole())
