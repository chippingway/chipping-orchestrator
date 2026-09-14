# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What an authorized oversized candidate leaves behind when it publishes.

The one road to a publication that does not go through the ordinary
settlement: a human authorizes a candidate the ceiling refused, so no count
lets it past and nothing below the gate's door is asked. Everything the
retirement exists for is still true of it -- a generation left standing
freezes this branch out of the ordinary base refresh for as long as the issue
lives, and the guard that ends a cycle on a close reads it as one still
running.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from orchestrator.config import settings as config
from orchestrator.workflow.late_split import state as _late_state
from orchestrator.workflow.stages.implementing import (
    late_approval_reading as _late_approval_reading,
    late_approval_state as _late_approval_state,
    state as _state,
)
from tests.workflow.fixtures import _TEST_SPEC, LABEL_VALIDATING
from tests.workflow.observation_support import ObservedCloseCase
from tests.workflow.stages.implementing import (
    late_consent_case as _consent_case,
    late_consent_payloads as _consent_payloads,
)

_REPO_SLUG = _TEST_SPEC.slug

_VALIDATING = (_consent_payloads.ISSUE_NUMBER, LABEL_VALIDATING)

# The field that says a cycle is still there to end, and the one the write
# retiring it leaves in its place for a close observed inside that window.
_KEY_CYCLE_ID = "late_cycle_id"
_KEY_RETIRED_CYCLE_ID = "late_retired_cycle_id"

_KEY_CANCELLED = "late_cancelled"

_APPROVE = "_approve"

_MAX_ADDED_LINES = "MAX_ADDED_LINES"

# A ceiling an operator retuned between the authorization and the retry,
# which is the value a re-measured record would write down as the one they
# authorized against.
_A_RETUNED_CEILING = 5000

# Every term a bypass is recorded on: the pair it was measured between,
# the count, the ceiling, the digest, and the comment it was written in.
_THE_TERMS = (
    _consent_payloads.KEY_OVERRIDE_CANDIDATE_SHA,
    _consent_payloads.KEY_OVERRIDE_BASE_SHA,
    _consent_payloads.KEY_OVERRIDE_ADDITIONS,
    _consent_payloads.KEY_OVERRIDE_THRESHOLD,
    _consent_payloads.KEY_OVERRIDE_COMMENT_ID,
)


class _RemembersTheBasis:
    """The approval writer, saying what each debt it wrote rests on."""

    def __init__(self, wrapped) -> None:
        self._wrapped = wrapped
        self.on: list = []

    def __call__(self, state, *called, **options):
        self.on.append(called[-1])
        return self._wrapped(state, *called, **options)


class AuthorizedPublicationTest(
    ObservedCloseCase, _consent_case._ParkedCase, unittest.TestCase,
):
    """A command that publishes, and the record it may not leave standing."""

    def setUp(self) -> None:
        super().setUp()
        self._fresh_process()
        self._seed(**_consent_payloads.measured_pair())

    def test_the_command_retires_the_generation(self) -> None:
        # Reached without the retirement, the push lands and the handoff moves
        # the label while `late_cycle_id` still names a live cycle: every late
        # reading key stays on the record, the pull request's checkout is held
        # out of the base refresh for good, and a later close on this issue is
        # taken for a cancellation of a cycle that finished.
        self._reply(_consent_payloads.AUTHORIZE)

        mocks = self._run_tick()

        mocks[_consent_payloads.PUSH_BRANCH].assert_called_once()
        self.assertIn(_VALIDATING, self.github.label_history)
        self.assertFalse(
            _late_state.read_late_generation(self._state()).is_present,
        )
        self.assertIsNone(self._pinned().get(_KEY_CYCLE_ID))

    def test_the_debt_rests_on_the_authorization(self) -> None:
        # The one thing this settlement records differently from the small
        # candidate's. That one says the ceiling let the commit through, so a
        # tick coming back after a crash owes nobody a question before it
        # pushes; this one says a person did, which is a permission that has
        # to still be readable when the debt is spent.
        self._reply(_consent_payloads.AUTHORIZE)
        granting = _RemembersTheBasis(_late_approval_state._approve)

        with patch.object(_late_approval_state, _APPROVE, granting):
            self._run_tick()

        self.assertEqual(
            granting.on, [_late_approval_reading.LateApprovalBasis.AUTHORIZATION],
        )

    def test_a_retry_keeps_the_terms_it_was_given(self) -> None:
        # A publication that fails after the authorization is recorded leaves
        # the seam parked under a reason of its own, and the rollback puts
        # this park back so the operator is not asked again. Read as still
        # waiting, the retry measures the same commit afresh and writes NEW
        # terms over the ones the human agreed to -- a ceiling retuned in
        # between becomes the ceiling they are recorded as having authorized.
        # The terms of a bypass are the terms somebody agreed to.
        self._reply(_consent_payloads.AUTHORIZE)
        self._run_tick(push_branch=False)
        agreed = dict(self._pinned())

        with patch.object(config, _MAX_ADDED_LINES, _A_RETUNED_CEILING):
            mocks = self._run_tick()

        mocks[_consent_payloads.PUSH_BRANCH].assert_called_once()
        for term in _THE_TERMS:
            self.assertEqual(self._pinned()[term], agreed[term])

    def test_a_retry_leaves_nobody_waiting(self) -> None:
        # And the park comes down with the publication. Carried past it, a
        # commit publishes over a record still saying a human is holding the
        # issue, and the source stage's parked road stops on every poll after.
        self._reply(_consent_payloads.AUTHORIZE)
        self._run_tick(push_branch=False)

        self._run_tick()

        self.assertFalse(self._pinned()[_state._AWAITING_HUMAN])
        self.assertIsNone(self._pinned()[_state._PARK_REASON])

    def test_a_close_inside_it_publishes_nothing(self) -> None:
        # The close-safe half of that protocol, which the road would skip
        # entirely without it. The retirement write takes the cycle identity
        # off the record, and everything deciding what a close is worth reads
        # that identity -- so a poll landing inside the window would find an
        # issue with nothing to end. Caught there, the generation goes back
        # and the publication does not happen.
        self._reply(_consent_payloads.AUTHORIZE)
        self._latch_close(_REPO_SLUG, _consent_payloads.ISSUE_NUMBER)

        mocks = self._run_tick()

        mocks[_consent_payloads.PUSH_BRANCH].assert_not_called()
        self.assertNotIn(_VALIDATING, self.github.label_history)
        self.assertTrue(self._pinned()[_KEY_CANCELLED])

    def test_the_retiring_cycle_is_named_for_a_close(self) -> None:
        # And where no close is latched, the write still says which cycle it
        # dropped: a poll observing one in the window that follows receipts a
        # cycle the record has stopped naming, and this is what it is adopted
        # against.
        self._reply(_consent_payloads.AUTHORIZE)

        self._run_tick()

        self.assertEqual(self._pinned()[_KEY_RETIRED_CYCLE_ID], 1)


if __name__ == "__main__":
    unittest.main()
