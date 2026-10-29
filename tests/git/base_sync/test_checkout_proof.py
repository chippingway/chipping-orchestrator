# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The base-sync tail's clean, held to a checkout switched while its reset ran.

The reset-and-park tail proves the checkout the issue's own before its reset,
but the reset is a window of its own, and the clean behind it deletes whatever
untracked files the tree holds. So the clean asks again: a checkout switched
off the issue's branch while the reset ran is neither cleaned nor parked, and
the attempt stands for the recovery that finds the checkout restored.
"""
from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from orchestrator.git import commands
from orchestrator.git.base_sync import persistence
from tests.git.base_sync import base_sync_helpers as fixtures
from tests.support.checkout_identity import stated_identity, stated_switch

_PARK_MESSAGE = "@human the rebase could not finalize"

_RESET_ARGS = ("reset", "--hard", fixtures.PRE_REBASE_SHA)


def _switched_reset(*_args, **_kwargs):
    """A reset that lands while the checkout is switched off the issue's branch."""
    stated_switch()
    return fixtures._git_result()


class SwitchedCleanTest(unittest.TestCase):
    """One reset-and-park tail that cleans, over a checkout switched while its reset ran."""

    def test_a_switch_during_the_reset_cleans_nothing(self) -> None:
        # The context's checkout is no real worktree at a layout path, so its
        # identity is stated: the issue's own until the reset, switched behind it.
        stated_identity(self)
        context = fixtures._recovery_context(**{fixtures.KEY_PENDING_PUSH_SHA: fixtures.PRE_REBASE_SHA})
        hardened = MagicMock(side_effect=_switched_reset)

        with patch.object(commands, fixtures.GIT_HARDENED, hardened):
            persistence._reset_clear_and_park(
                context, fixtures.PRE_REBASE_SHA,
                message=_PARK_MESSAGE, reason=fixtures.PARK_DIRTY, clean=True,
            )

        pinned = context.gh.pinned_data(fixtures.ISSUE)
        self.assertEqual([called.args for called in hardened.call_args_list], [_RESET_ARGS])
        self.assertEqual(pinned.get(fixtures.KEY_PENDING_PUSH_SHA), fixtures.PRE_REBASE_SHA)
        self.assertIsNone(pinned.get(fixtures.KEY_PARK_REASON))
        self.assertEqual(context.gh.posted_comments, [])


if __name__ == "__main__":
    unittest.main()
