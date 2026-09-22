# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What the publication a drift park still owes counts the reviewer.

`review_round` is what `MAX_REVIEW_ROUNDS` counts, and it advances on exactly
one event: a head the reviewer has not seen reaching the pull request. The
delayed publication a park owes is that event as much as a push is -- except
where somebody has already paid for it, and there are two of those.

An `in_review` requirements edit that reset the budget is the first: the reset
IS the round accounting of that edit, and counting again would charge it twice.
A report's own RECORD carrying the round is the second, and it is the one this
module is mostly about: a fixing round that finished on a report froze its
bookmarks and its round onto that record precisely so the write completing the
publication is the only thing that spends them.

The RECORD is asked rather than the debt, because the two part company. A drift
resume records a report carrying no bookkeeping at all, since its own
disposition bumps the round; where that push failed, the publication a park
owes is the only road left to count it, and a road reading the debt would hand
that reviewer a head no round was ever spent on. So an empty group and a frozen
one are opposite answers, and both records are asked, since the debt passes from
the delivered record to the transaction it becomes and the pairs travel with it.

Every record here is written through the engine's own writers rather than
seeded as fields, so what these cases are about is the record this build really
produces.
"""
from __future__ import annotations

import unittest

from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    report_delivery as _report_delivery,
    report_delivery_state as _delivery_state,
    report_record_state as _record_state,
    report_records as _records,
)
from orchestrator.workflow.late_split import formats as _formats
from orchestrator.workflow.stages.implementing import (
    late_gate_models as _late_gate_models,
)
from orchestrator.workflow.stages.validating import rounds as _rounds, state as _state
from orchestrator.workflow.state import WorkflowLabel

# A whole digest and a whole object id, taken at the widths this domain
# records them at: every member of a record is read back at its exact width,
# so an abbreviation of either is no value at all.
_REQUIREMENTS = "a" * max(_formats.DIGEST_LENGTHS)

_SOURCE_SHA = "b" * min(_formats.COMMIT_LENGTHS)

_REPO_SLUG = "chippingway/orchestrator"

_BRANCH = "orchestrator/chippingway__orchestrator/issue-7"

_PR_NUMBER = 12

_RECEIPT = "issue-7-report-1"

_REPORT_TEXT = "Answered the review in the report."

# The bookkeeping a fixing round freezes onto its record, so that the write
# completing its publication is the only thing that ever spends it.
_FROZEN = ((_state._REVIEW_ROUND, 3), ("pending_fix_at", None))

# Where the counter stands before any of these roads runs.
_SPENT_ROUNDS = 2


def _delivered(spends: tuple) -> _records.DeliveredReport:
    """One completed run's report, recorded before its code is published."""
    return _records.DeliveredReport(
        receipt=_RECEIPT,
        report_revision=1,
        mode=_records.ReportMode.PUBLISH,
        route=WorkflowLabel.FIXING,
        requirements_revision=_REQUIREMENTS,
        report=_REPORT_TEXT,
        spends=spends,
    )


def _pending(spends: tuple) -> _records.PendingReport:
    """The transaction that record becomes once its publication exists."""
    return _records.PendingReport(
        receipt=_RECEIPT,
        subject=_records.ReportSubject(
            repo_slug=_REPO_SLUG,
            pr_number=_PR_NUMBER,
            branch=_BRANCH,
            source_sha=_SOURCE_SHA,
            requirements_revision=_REQUIREMENTS,
        ),
        report_revision=1,
        mode=_records.ReportMode.PUBLISH,
        route=WorkflowLabel.FIXING,
        report=_REPORT_TEXT,
        spends=spends,
    )


class OwedPublicationRoundTest(unittest.TestCase):
    """The round a publication a park still owes lands the reviewer on."""

    def setUp(self) -> None:
        self.state = PinnedState(
            state_data={_state._REVIEW_ROUND: _SPENT_ROUNDS},
        )

    def test_a_frozen_round_counts_nothing(self) -> None:
        # Counted here, the round the record froze is counted twice -- and
        # once a tick before the report it belongs to is anywhere.
        for case, write, record in (
            ("delivered", _delivery_state.record_delivered_report, _delivered(_FROZEN)),
            ("a transaction", _record_state.record_pending_report, _pending(_FROZEN)),
        ):
            with self.subTest(case=case):
                self.setUp()
                self.assertTrue(write(self.state, record))

                self.assertEqual(
                    _rounds._spends_for_an_owed_publication(self.state),
                    _late_gate_models._SPENDS_NOTHING,
                )

    def test_a_record_that_froze_none_advances_it(self) -> None:
        # The drift resume's own record is this shape: its disposition bumps
        # the round, and where that push failed this publication is the only
        # road left to count one. Read off the DEBT rather than the record,
        # both shapes would count nothing and the reviewer would be handed a
        # head no round was ever spent on.
        for case, write, record in (
            ("delivered", _delivery_state.record_delivered_report, _delivered(())),
            ("a transaction", _record_state.record_pending_report, _pending(())),
        ):
            with self.subTest(case=case):
                self.setUp()
                self.assertTrue(write(self.state, record))

                self.assertEqual(
                    _rounds._spends_for_an_owed_publication(self.state),
                    self._the_next_round(),
                )

    def test_an_issue_with_no_record_advances_it(self) -> None:
        # The ordinary debt this stage's own roads leave: a drift resume that
        # committed and parked before anything was pushed, so the head the
        # reply finally publishes is one no reviewer has read.
        self.assertEqual(
            _rounds._spends_for_an_owed_publication(self.state),
            self._the_next_round(),
        )

    def test_a_budget_an_edit_reset_counts_nothing(self) -> None:
        # The reset IS the round accounting of a requirements edit on an
        # approved pull request, so counting the publication that edit
        # produced would charge the same edit twice.
        self.state.set(_report_delivery.OWED_ROUND_RESET, True)

        self.assertEqual(
            _rounds._spends_for_an_owed_publication(self.state),
            _late_gate_models._SPENDS_NOTHING,
        )

    def _the_next_round(self) -> _late_gate_models._Spends:
        """The round this counter lands on, frozen as a caller carries it."""
        return _late_gate_models._Spends(
            fields=((_state._REVIEW_ROUND, _SPENT_ROUNDS + 1),),
        )


if __name__ == "__main__":
    unittest.main()
