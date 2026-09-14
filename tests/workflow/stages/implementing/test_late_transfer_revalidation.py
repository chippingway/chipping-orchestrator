# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Transfer recovery revalidates operator authorization and publication identity."""
from __future__ import annotations

import unittest

from orchestrator.workflow.late_split import (
    overrides as _overrides,
    rewrite_fields as _rewrite_fields,
    rewrite_reading as _rewrite_reading,
    rewrite_values as _rewrite_values,
)
from orchestrator.workflow.stages.implementing import (
    state as _state,
)
from orchestrator.workflow.state import WorkflowLabel
from tests.support import fakes as _github_fakes
from tests.workflow.stages.implementing import (
    late_transfer_case as _transfer_case,
    late_transfer_payloads as _transfer_payloads,
)


class RevalidatedRecoveryTest(_transfer_case._RecoveryCase, unittest.TestCase):
    """Every way the terms a permit was granted on stopped being true.

    Each leaves an approval standing over a rewrite nothing revalidated, and
    each has to fall back to the ordinary cumulative gate rather than ride the
    debt's bare object id to the remote.
    """

    def test_unproven_authorization_is_revalidated(self) -> None:
        # A permission needs a human authorization that still describes the
        # contribution; neither a missing record nor a stale digest grants it.
        for stale in (False, True):
            with self.subTest(stale_digest=stale):
                self.setUp()
                if stale:
                    self._recovered({
                        _overrides.LATE_OVERRIDE_FINGERPRINT: _transfer_payloads.OTHER_DIGEST,
                    })
                else:
                    _overrides.clear_publication_override(self.state)
                    self.github.write_pinned_state(self.issue, self.state)

                self.assertEqual(self._re_asked(), "")
                self.assertFalse(self._bypasses())


    def test_a_malformed_permission_is_measured(self) -> None:
        # The record the recovery would rebuild its evidence from is one this
        # build cannot read, so there is nothing to re-ask the permit over --
        # and the approval may not answer for it either, or an oversized
        # rewrite nothing revalidated would be pushed.
        for described, damage in _transfer_case._STANDING_CLAIMS.items():
            with self.subTest(claim=described):
                self._recovered(damage)

                self.assertEqual(self._re_asked(), "")
                self.assertFalse(self._bypasses())

    def test_a_disagreeing_digest_is_measured(self) -> None:
        # The digest the permission recorded is what it says it was granted
        # over. One that disagrees with the contribution actually here is a
        # record somebody edited or one taken under other rules, and a grant
        # that carried on would write this reading's digest over it -- a
        # repair of evidence nobody checked, under the authority of the
        # transfer being decided. So the permit refuses and the record stands.
        self._recovered({_rewrite_fields.LATE_REWRITE_FINGERPRINT: _transfer_payloads.OTHER_DIGEST})

        self.assertEqual(self._re_asked(), "")
        authorized = _rewrite_reading.read_rewrite_authorization(
            self.github.read_pinned_state(self.issue),
        )
        self.assertEqual(authorized.fingerprint, _transfer_payloads.OTHER_DIGEST)
        self.assertEqual(
            authorized.phase, _rewrite_values.LateRewritePhase.AUTHORIZED,
        )

    def test_a_replaced_publication_is_measured(self) -> None:
        # The permission names the pull request and the stage the rewrite was
        # made against. Repointed or relabelled since, the push it licensed is
        # one nothing may make unmeasured.
        self.state.set(_state._PR_NUMBER, _transfer_payloads.PR_NUMBER + 1)

        self.assertEqual(self._re_asked(), "")

    def test_a_relabelled_issue_is_measured(self) -> None:
        self.issue.labels.clear()
        self.issue.labels.append(_github_fakes.FakeLabel(str(WorkflowLabel.FIXING)))

        self.assertEqual(self._re_asked(), "")
