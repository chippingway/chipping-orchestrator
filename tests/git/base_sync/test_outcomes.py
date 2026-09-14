# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Terminal answers a verified crash recovery selects on the `outcomes` owner."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from orchestrator.git.base_sync import outcomes, persistence, recovery_notices as _recovery_notices, snapshot
from tests.git.base_sync import base_sync_helpers as fixtures

FINALIZE_HELPER = "_finalize_recovered_rebase"

RESET_HELPER = "_reset_clear_and_park"

ABORT_HELPER = "_abort_recovery_unverified"

SHORT_LOCAL = fixtures.RECOVERED_SHA[:8]

SHORT_REMOTE = fixtures.REMOTE_SHA[:8]

SHORT_ANCHOR = fixtures.PRE_REBASE_SHA[:8]

ALREADY_PUBLISHED = "already published"

REBASE_AGAIN_PHRASE = "rebasing once more"

DIRTY_FILES = ("scratch.txt", "notes.md")

NOTICE_BUILDERS = (
    _recovery_notices._already_published_recovery_notice,
    _recovery_notices._pushed_recovery_notice,
)


def _park_dirty(context, snapshot) -> bool:
    """Park a dirty recovery over a fixed set of leftover files."""
    return outcomes._park_dirty_recovery(context, snapshot, list(DIRTY_FILES))


# Each park outcome, the durable reason it records, whether it also cleans the
# worktree, and the phrase that tells its HITL message apart from the others.
PARK_CASES = (
    (
        outcomes._park_diverged_recovery,
        fixtures.PARK_PUSH_FAILED,
        False,
        "updated out-of-band",
    ),
    (
        _park_dirty,
        fixtures.PARK_DIRTY,
        True,
        f"carries {len(DIRTY_FILES)} uncommitted change(s)",
    ),
    (
        outcomes._park_failed_recovery_push,
        fixtures.PARK_PUSH_FAILED,
        False,
        "`--force-with-lease` push",
    ),
)


class RecoveryNoticeTest(unittest.TestCase):
    """Both notices name the recovered head and where the issue goes next."""

    def test_current_head_promises_the_route(self) -> None:
        for builder in NOTICE_BUILDERS:
            with self.subTest(notice=builder.__name__):
                notice = builder(
                    fixtures._recovery_context(behind=0),
                    fixtures.RECOVERED_SHA,
                )
                self.assertIn(f"#{fixtures.PR_NUMBER}", notice)
                self.assertIn(SHORT_LOCAL, notice)
                self.assertIn(
                    f"`{fixtures.LABEL}` -> `{fixtures.VALIDATING}`",
                    notice,
                )
                self.assertNotIn(REBASE_AGAIN_PHRASE, notice)

    def test_lagging_head_announces_another_rebase(self) -> None:
        for builder in NOTICE_BUILDERS:
            with self.subTest(notice=builder.__name__):
                notice = builder(
                    fixtures._recovery_context(behind=2),
                    fixtures.RECOVERED_SHA,
                )
                self.assertIn("2 commit(s)", notice)
                self.assertIn(REBASE_AGAIN_PHRASE, notice)

    def test_notices_name_their_own_recovery_path(self) -> None:
        context = fixtures._recovery_context()

        self.assertIn(
            ALREADY_PUBLISHED,
            _recovery_notices._already_published_recovery_notice(
                context, fixtures.RECOVERED_SHA,
            ),
        )
        self.assertIn(
            "pushed the recovered head",
            _recovery_notices._pushed_recovery_notice(context, fixtures.RECOVERED_SHA),
        )


class AlreadyPublishedRecoveryTest(unittest.TestCase):
    """A landed push is finalized as a relabel, with nothing pushed again."""

    def test_finalize_carries_the_relabel_only_method(self) -> None:
        finalize = MagicMock(return_value=True)

        with patch.object(persistence, FINALIZE_HELPER, finalize):
            finalized = outcomes._finalize_already_published_recovery(
                fixtures._recovery_context(),
                fixtures._snapshot(local_head=fixtures.RECOVERED_SHA),
            )

        self.assertTrue(finalized)
        self.assertEqual(
            finalize.call_args.kwargs.get("local_head"),
            fixtures.RECOVERED_SHA,
        )
        self.assertEqual(
            finalize.call_args.kwargs.get("method"),
            "crash_recovery_relabel_only",
        )
        self.assertIn(
            ALREADY_PUBLISHED, finalize.call_args.kwargs.get("notice"),
        )


class UnknownComparisonTest(unittest.TestCase):
    """Heads that differ but compare as `(0, 0)` abort rather than guess."""

    def test_abort_detail_names_both_heads(self) -> None:
        abort = MagicMock(return_value=True)

        with patch.object(snapshot, ABORT_HELPER, abort):
            aborted = outcomes._reject_unknown_recovery_comparison(
                fixtures._recovery_context(), fixtures._snapshot(),
            )

        self.assertTrue(aborted)
        detail = abort.call_args.args[1]
        self.assertIn(SHORT_LOCAL, detail)
        self.assertIn(SHORT_REMOTE, detail)
        self.assertIn("`(0, 0)`", detail)


class RecoveryParkTest(unittest.TestCase):
    """Every unfinishable recovery resets onto the anchor and parks."""

    def test_each_park_names_its_reason(self) -> None:
        for park, reason, clean, fragment in PARK_CASES:
            with self.subTest(park=park.__name__):
                self._assert_parks(park, reason, clean, fragment)

    def _assert_parks(self, park, reason: str, clean: bool, fragment: str) -> None:
        context = fixtures._recovery_context()
        reset = MagicMock()

        with patch.object(persistence, RESET_HELPER, reset):
            parked = park(context, fixtures._snapshot(ahead=1, behind=1))

        # Every park owns the tick: the caller stops here rather than falling
        # through to the normal rebase flow against a parked issue.
        self.assertTrue(parked)
        self.assertEqual(
            reset.call_args.args, (context, fixtures.PRE_REBASE_SHA),
        )
        self.assertEqual(reset.call_args.kwargs.get("reason"), reason)
        self.assertEqual(reset.call_args.kwargs.get("clean", False), clean)
        self._assert_message(reset.call_args.kwargs.get("message"), fragment)

    def _assert_message(self, message: str, fragment: str) -> None:
        self.assertIn(fragment, message)
        self.assertIn(f"#{fixtures.PR_NUMBER}", message)
        self.assertIn(SHORT_ANCHOR, message)


if __name__ == "__main__":
    unittest.main()
