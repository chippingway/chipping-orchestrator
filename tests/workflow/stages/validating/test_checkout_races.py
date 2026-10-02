# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The checkout an approval is handed on from, and what lands in it after the review.

The branch an approval hands on is taken from the round's checkout: squashed
from there, or -- with `SQUASH_ON_APPROVAL=off` and nothing to rewrite --
handed on as it stands, where the documenting stage takes a checkout ahead of
its pull request for docs work of its own and publishes it. The verify gate
proves the checkout only while its own commands run, and reads nothing where
none are configured, so behind the approval notice the checkout is proved
again: still standing on the head the reviewer was handed, with nothing left
uncommitted. A commit made there since, a change left in it, or a head nobody
could read hands nothing on -- no approval is recorded, nothing is squashed,
and the label stays -- while the checkout the reviewer read goes on to
`documenting` as it always did.
"""
from __future__ import annotations

import unittest
from types import MappingProxyType
from unittest.mock import patch

from orchestrator import config
from orchestrator.git.verification.models import VerifyResult
from tests.workflow.fixtures import _agent, approved_on
from tests.workflow.stages.validating import squash_approval_support as _support
from tests.workflow.stages.validating.squash_approval_support import _SquashApprovalFixtureMixin
from tests.workflow.stages.validating.test_squash_route import HANDED_ON

# A commit made in the checkout after the reviewer's round and its verification.
LOCAL_COMMIT = "c0ffee11" * 5

APPROVED_SUBJECT = "review_approved_subject"

# A gate that ran the suite over the head the reviewer was handed and passed.
_VERIFIED = VerifyResult(status="ok", commit=_support.SQUASHED_SHA)


def _reads(head: str, *dirty: str) -> MappingProxyType:
    """The run options a checkout standing on `head`, with `dirty` left uncommitted in it, reads back as."""
    return MappingProxyType({"head_shas": (head,), "dirty_files": dirty})


# What the checkout reads as behind the approval notice, and whether the
# approval is handed on from it.
_CHECKOUTS = (
    ("the reviewed head, clean", _reads(_support.SQUASHED_SHA), True),
    ("a commit made since", _reads(LOCAL_COMMIT), False),
    ("a change left uncommitted", _reads(_support.SQUASHED_SHA, "notes.txt"), False),
    ("a head nobody could read", _reads(""), False),
)


class CheckoutRaceTest(unittest.TestCase, _SquashApprovalFixtureMixin):
    """An approval is handed on only from the checkout its reviewer read."""

    def setUp(self) -> None:
        # Nothing is rewritten, so the branch goes on exactly as the checkout
        # stands, and a configured suite is what the gate verified.
        self.enterContext(patch.object(config, "SQUASH_ON_APPROVAL", False))
        self.enterContext(patch.object(config, "VERIFY_COMMANDS", ("pytest",)))

    def test_only_the_reviewed_checkout_is_handed_on(self) -> None:
        for name, checkout, handed_on in _CHECKOUTS:
            with self.subTest(name):
                self.assertEqual(self._handed_on(checkout), (handed_on,) * 3)

    def _handed_on(self, checkout) -> tuple:
        """Whether an approval over `checkout` reached `documenting`, recorded its approval, and ran the squash."""
        github, issue, _pr = self._setup()

        mocks = self._run_validating(
            github,
            issue,
            run_agent=_agent(last_message=approved_on(_support.SQUASHED_SHA)),
            verify_result=_VERIFIED,
            **checkout,
        )

        recorded = APPROVED_SUBJECT in github.pinned_data(_support.APPROVAL_ISSUE)
        return (HANDED_ON in github.label_history, recorded, mocks[_support.SQUASH_SEAM].called)


if __name__ == "__main__":
    unittest.main()
