# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a recovery's reset-and-park keeps, on the `persistence` owner.

The order an interrupted rebase is routed in is the workflow's
(`workflow/engine/rewrite_recovery.py`), and held beside it; the tail every
road that cannot finish ends in is this package's.
"""

from __future__ import annotations

import contextlib
import unittest
from types import MappingProxyType
from unittest.mock import MagicMock, patch

from orchestrator.git import commands as _commands
from orchestrator.git.base_sync import persistence
from tests.git.base_sync import base_sync_helpers as fixtures

# The commit an approval owes a push for, which the rollback would abandon.
_ABANDONED_SHA = "ab5e0000" * 5

_APPROVED_SHA = "late_approved_sha"
_APPROVED_LEASE = "late_approved_lease"
_SPENDS = "late_spends"

# The round that publication's route still owes, recorded beside the approval.
_OWED_ROUND = ("review_round", 2)

# The record of the attempt itself, which the same reset drops and the same
# refusal keeps: without it a later tick has no anchor to come back with and
# no id to ask for the candidate by.
_ANCHOR_KEY = "pending_auto_base_rebase_push_sha"
_REPLAY_KEY = "pending_auto_base_rebase_rewrite_sha"
_ANNOUNCED_KEY = "pending_auto_base_rebase_announced_sha"

_OWED = MappingProxyType({
    _APPROVED_SHA: _ABANDONED_SHA,
    _APPROVED_LEASE: fixtures.PRE_REBASE_SHA,
    _SPENDS: [list(_OWED_ROUND)],
    _ANCHOR_KEY: fixtures.PRE_REBASE_SHA,
    _REPLAY_KEY: _ABANDONED_SHA,
    _ANNOUNCED_KEY: _ABANDONED_SHA,
})

_PARK_MESSAGE = "the push did not land"
_GIT_FAILED = 128

# The report an earlier rebase left the pull request owing: from a head its
# settled report is about onto the anchor this attempt started from.
_REPORT_DEBT_KEY = "developer_report_rewrite_debt"
_REPORT_DEBT = MappingProxyType({
    "pr": fixtures.PR_NUMBER,
    "branch": fixtures.BRANCH,
    "previous_head": "ea41e700" * 5,
    "rewritten_head": fixtures.PRE_REBASE_SHA,
})


class RolledBackDebtTest(unittest.TestCase):
    """What a reset-and-park keeps when the reset itself will not go through.

    The reset is what makes an approved commit unreachable, and so what
    licenses dropping the record naming it. Refused, the branch may still be
    standing on that commit -- and the approval, the head its push is pinned
    to, and the route bookkeeping that push closes are the only things naming
    any of it.
    """

    def test_a_failed_reset_keeps_the_whole_debt(self) -> None:
        owing = fixtures._sync_context(**_OWED)

        with self._reset_refusing(_GIT_FAILED):
            persistence._reset_clear_and_park(
                owing, fixtures.PRE_REBASE_SHA,
                message=_PARK_MESSAGE, reason=fixtures.PARK_PUSH_FAILED,
            )

        pinned = owing.gh.pinned_data(fixtures.ISSUE)
        self.assertEqual(pinned[_APPROVED_SHA], _ABANDONED_SHA)
        self.assertEqual(pinned[_APPROVED_LEASE], fixtures.PRE_REBASE_SHA)
        self.assertEqual(tuple(pinned[_SPENDS][0]), _OWED_ROUND)
        # The attempt's own record goes with them, and for the same reason:
        # the comment is the only account of where the checkout may be
        # standing once the reset that would have settled it did not run.
        self.assertEqual(pinned[_ANCHOR_KEY], fixtures.PRE_REBASE_SHA)
        self.assertEqual(pinned[_REPLAY_KEY], _ABANDONED_SHA)
        # The checkpoint a finish left goes with them: dropped over a reset
        # that did not run, the next tick reads a publication that already
        # went out as one nothing has announced.
        self.assertEqual(pinned[_ANNOUNCED_KEY], _ABANDONED_SHA)

    def test_a_landed_reset_drops_it(self) -> None:
        # What says the refusal above is about the reset rather than about the
        # record never being dropped: reset, the approved commit is only in
        # the reflog and a debt naming it is one nothing can pay.
        owing = fixtures._sync_context(**_OWED)

        with self._reset_refusing(0):
            persistence._reset_clear_and_park(
                owing, fixtures.PRE_REBASE_SHA,
                message=_PARK_MESSAGE, reason=fixtures.PARK_PUSH_FAILED,
            )

        pinned = owing.gh.pinned_data(fixtures.ISSUE)
        self.assertIsNone(pinned[_APPROVED_SHA])
        self.assertIsNone(pinned[_APPROVED_LEASE])
        self.assertNotIn(_SPENDS, pinned)
        self.assertIsNone(pinned[_ANCHOR_KEY])
        self.assertIsNone(pinned[_REPLAY_KEY])
        self.assertIsNone(pinned[_ANNOUNCED_KEY])

    def test_a_landed_reset_keeps_the_report_debt(self) -> None:
        # No record of this attempt: the reset puts the branch back on the
        # head the debt names, so that head is still owed its report, and no
        # head of the abandoned replay's is claimed in its place.
        owing = fixtures._sync_context(**_OWED, **{_REPORT_DEBT_KEY: dict(_REPORT_DEBT)})

        with self._reset_refusing(0):
            persistence._reset_clear_and_park(
                owing, fixtures.PRE_REBASE_SHA,
                message=_PARK_MESSAGE, reason=fixtures.PARK_PUSH_FAILED,
            )

        self.assertEqual(owing.gh.pinned_data(fixtures.ISSUE)[_REPORT_DEBT_KEY], _REPORT_DEBT)

    @contextlib.contextmanager
    def _reset_refusing(self, returncode: int):
        """Answer every hardened git command with `returncode`."""
        with patch.object(
            _commands, "_git_hardened",
            MagicMock(return_value=fixtures._git_result(returncode=returncode)),
        ):
            yield


if __name__ == "__main__":
    unittest.main()
