# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Rollback drops only the permission for the abandoned rewrite."""
from __future__ import annotations

import unittest

from orchestrator.workflow.late_split import (
    exemption_reading as _exemption_reading,
    rewrite_fields as _rewrite_fields,
    rewrite_reading as _rewrite_reading,
    rewrites as _rewrites,
)
from orchestrator.workflow.stages.implementing import (
    late_transfer as _transfer,
)
from tests.workflow.stages.implementing import (
    late_transfer_case as _transfer_case,
    late_transfer_payloads as _transfer_payloads,
    late_transfer_test_support as _support,
)


class AbandonedAuthorizationTest(_transfer_case._TransferCase, unittest.TestCase):
    """What a rollback owes when the push a permission licensed is refused."""

    def setUp(self) -> None:
        super().setUp()
        self._carried()
        self.gate = _support.gate(self.github, self.issue, self.state)

    def test_a_rollback_drops_the_permission(self) -> None:
        # Both heads a rewrite can be put back onto. A squash collapses the
        # accepted commit itself, so the reset lands on the commit the
        # exemption never left. A base rebase reads the pre-rebase anchor for
        # itself and goes back to THAT, which is the accepted commit only
        # while the branch was standing exactly on it -- and the equality of
        # the two contributions never said that it was. Either way the object
        # the permission was granted for is on no branch, and it goes with it.
        for restored in (_transfer_payloads.ACCEPTED_SHA, _transfer_payloads.LEASED_SHA):
            with self.subTest(restored=restored):
                self._carried()

                self.assertTrue(
                    _transfer._abandoned_authorization(self.gate, restored),
                )

                self.assertTrue(
                    _exemption_reading.is_exempt(self.state, _transfer_payloads.ACCEPTED_SHA),
                )
                identity = _exemption_reading.read_semantic_identity(self.state)
                self.assertEqual(identity.candidate_sha, _transfer_payloads.ACCEPTED_SHA)
                self.assertEqual(identity.fingerprint, _transfer_payloads.ACCEPTED_DIGEST)
                self.assertFalse(
                    _rewrite_reading.carries_rewrite_authorization(self.state),
                )

    def test_a_published_transfer_is_not_dropped(self) -> None:
        # Past the receipt the pull request carries the rewritten commit and
        # the exemption has already moved onto it, so there is no permission
        # left outstanding and nothing here to take back.
        _support.spent(self.state)

        self.assertFalse(
            _transfer._abandoned_authorization(self.gate, _transfer_payloads.ACCEPTED_SHA),
        )

        self.assertTrue(_exemption_reading.is_exempt(self.state, _transfer_payloads.REWRITTEN_SHA))

    def test_another_reset_drops_nothing(self) -> None:
        self.assertFalse(
            _transfer._abandoned_authorization(self.gate, _transfer_payloads.STRANGER_SHA),
        )

        self.assertTrue(
            _rewrite_reading.carries_rewrite_authorization(self.state),
        )

    def test_a_damaged_authorization_is_not_dropped(self) -> None:
        # Dropping a permission nobody can check would throw away the only
        # account of how the exemption came to name what it names.
        self.state.data.pop(_rewrite_fields.LATE_REWRITE_FROM_BASE_SHA)

        self.assertFalse(
            _transfer._abandoned_authorization(self.gate, _transfer_payloads.ACCEPTED_SHA),
        )

        self.assertTrue(
            _rewrite_reading.carries_rewrite_authorization(self.state),
        )

    def test_no_permission_drops_nothing(self) -> None:
        _rewrites.clear_rewrite_authorization(self.state)

        self.assertFalse(
            _transfer._abandoned_authorization(self.gate, _transfer_payloads.ACCEPTED_SHA),
        )
