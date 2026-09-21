# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a run that moved no head IS while a report is still owed.

Every ordinary reply that moves no head is a question, and the one reading here
is what keeps the reply an undeliverable-report park earns from being read as
one: the issue was waiting for a report rather than for code, and the commits
are already on the branch.
"""

from __future__ import annotations

import unittest

from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    report_delivery_state as _delivery_state,
    report_redelivery as _redelivery,
)
from tests.workflow.engine import (
    report_delivery_test_support as delivery_support,
)
from tests.workflow.fixtures import _FAKE_WT, _TEST_SPEC, _agent
from tests.workflow.git_owners import seam_patch


class OwedReportRedeliveryTest(unittest.TestCase):
    """A run that committed nothing, on an issue that is owed a report.

    Every ordinary reply that moves no head is a question. An issue holding a
    report nothing could deliver is the exception: it was waiting for a report
    rather than for code, and the commits are already on the branch.
    """

    def test_a_report_republishes_the_branch(self) -> None:
        state = PinnedState()
        _delivery_state.record_delivered_report(state, delivery_support.DELIVERED)

        with seam_patch("_has_new_commits", lambda *_args: True):
            self.assertTrue(_redelivery.redelivers_an_owed_report(
                _TEST_SPEC,
                state,
                _agent(last_message=delivery_support.ready(delivery_support.DELIVERED.report)),
                _FAKE_WT,
            ))

    def test_each_reading_answers_on_its_own(self) -> None:
        # The debt, the outcome and the branch are required together: an issue
        # owing nothing is the ordinary no-commit reply, a run that asked
        # rather than reported is still a question, and a branch with nothing
        # ahead of base would publish a pull request with no diff in it.
        answered = (
            ("no report is owed", PinnedState(), delivery_support.ready(delivery_support.DELIVERED.report)),
            (
                "the run asked a question",
                PinnedState(state_data=dict(delivery_support.OWED)),
                "which database?",
            ),
        )
        with seam_patch("_has_new_commits", lambda *_args: True):
            for described, state, message in answered:
                with self.subTest(refusal=described):
                    self.assertFalse(_redelivery.redelivers_an_owed_report(
                        _TEST_SPEC, state, _agent(last_message=message),
                        _FAKE_WT,
                    ))

        with seam_patch("_has_new_commits", lambda *_args: False):
            self.assertFalse(_redelivery.redelivers_an_owed_report(
                _TEST_SPEC,
                PinnedState(state_data=dict(delivery_support.OWED)),
                _agent(last_message=delivery_support.ready(delivery_support.DELIVERED.report)),
                _FAKE_WT,
            ))


if __name__ == "__main__":
    unittest.main()
