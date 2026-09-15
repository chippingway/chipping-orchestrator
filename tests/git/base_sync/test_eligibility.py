# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The gates one refresh-time PR rebase clears, on the `eligibility` owner."""

from __future__ import annotations

import contextlib
import unittest
from types import MappingProxyType
from unittest.mock import MagicMock, patch

from orchestrator import config
from orchestrator.git.base_sync import eligibility, recovery, terminal_handoff as _terminal_handoff
from orchestrator.git.verification import status as _worktree_status
from tests.git.base_sync import base_sync_helpers as fixtures

RECOVER = "_recover_pending_auto_base_rebase"

DIRTY_FILES = "_worktree_dirty_files"

# Every label the refresh drives a PR-having worktree through.
DETOUR_LABELS = ("workflow:validating", "workflow:documenting", "in_review", "workflow:fixing")

# A label the refresh leaves alone: `resolving_conflict` runs its own handler
# on the same tick, and the pre-PR stages have no pushed head to rebase.
IGNORED_LABEL = "workflow:resolving_conflict"

PARK_PUSH_FAILED = "auto_base_rebase_push_failed"

FOREIGN_PARK_REASON = "unmergeable"

PARK_WATERMARK_COMMENT_ID = 99

RETRY_COMMENT_ID = 200

OUTSIDER_COMMENT_ID = 201

TRUSTED_LOGIN = "geserdugarov"

OUTSIDER_LOGIN = "mallory"

ALLOWLIST = (TRUSTED_LOGIN,)

LEFTOVERS = ("scratch.py",)

# A merged PR and a closed-without-merge one are both terminal here.
TERMINAL_PR_STATES = ((True, "closed"), (False, "closed"))

_OWNERS = MappingProxyType(
    {
        DIRTY_FILES: _worktree_status,
        RECOVER: recovery,
    },
)


def _handled(recovered: bool = True) -> MagicMock:
    """A crash-recovery stub reporting whether it owns the tick."""
    return MagicMock(return_value=recovered)


@contextlib.contextmanager
def _patched(**collaborators):
    """Patch the named collaborators on the owner each one lives on."""
    with contextlib.ExitStack() as stack:
        for name, replacement in collaborators.items():
            stack.enter_context(
                patch.object(_OWNERS[name], name, replacement),
            )
        yield


class LabelEligibilityTest(unittest.TestCase):
    """Only the refresh-driven labels pass, and no anchor outlives one."""

    def test_every_detour_label_is_eligible(self) -> None:
        recover = _handled()
        for label in DETOUR_LABELS:
            with self.subTest(label=label), _patched(**{RECOVER: recover}):
                self.assertTrue(
                    eligibility._auto_rebase_label_is_eligible(
                        fixtures._sync_context(label=label),
                    ),
                )
        # An eligible label stays on the normal flow, so the anchor it may
        # carry is settled by the rebase itself.
        recover.assert_not_called()

    def test_ignored_label_settles_a_pinned_anchor(self) -> None:
        context = fixtures._sync_context(
            label=IGNORED_LABEL,
            pending_pre_rebase_sha=fixtures.PRE_REBASE_SHA,
        )
        recover = _handled()

        with _patched(**{RECOVER: recover}):
            self.assertFalse(
                eligibility._auto_rebase_label_is_eligible(context),
            )

        # The issue left the detour carrying a recovery target, and no later
        # tick reaches this branch again -- so the anchor is resolved here.
        self.assertEqual(
            recover.call_args.kwargs.get("pending_pre_rebase_sha"),
            fixtures.PRE_REBASE_SHA,
        )
        self.assertEqual(
            recover.call_args.kwargs.get("label"), IGNORED_LABEL,
        )

    def test_ignored_label_skips_recovery(self) -> None:
        recover = _handled()

        with _patched(**{RECOVER: recover}):
            self.assertFalse(
                eligibility._auto_rebase_label_is_eligible(
                    fixtures._sync_context(label=IGNORED_LABEL),
                ),
            )

        # With no anchor pinned there is nothing to finalize, so the gate
        # rejects the label without spending a network hop on it.
        recover.assert_not_called()


class RetryDecisionTest(unittest.TestCase):
    """A park is released only by a trusted reply, and only on disk later."""

    def test_unparked_issue_continues(self) -> None:
        decision = eligibility._auto_rebase_retry_decision(
            fixtures._sync_context(),
        )

        self.assertTrue(decision.should_continue)
        self.assertIsNone(decision.consumed_comment_id)

    def test_foreign_park_reason_is_left_to_its_stage(self) -> None:
        # A park the stage handlers own (an unmergeable PR, a review-round
        # cap) must survive the refresh even with a fresh reply waiting.
        decision = eligibility._auto_rebase_retry_decision(
            self._parked_context(reason=FOREIGN_PARK_REASON),
        )

        self.assertFalse(decision.should_continue)

    def test_auto_park_without_a_reply_stays_parked(self) -> None:
        decision = eligibility._auto_rebase_retry_decision(
            self._parked_context(comments=()),
        )

        self.assertFalse(decision.should_continue)

    def test_trusted_reply_reports_its_comment_id(self) -> None:
        context = self._parked_context()

        decision = eligibility._auto_rebase_retry_decision(context)

        self.assertTrue(decision.should_continue)
        self.assertEqual(decision.consumed_comment_id, RETRY_COMMENT_ID)
        # Reporting is not releasing: the park stays on disk until a rebase
        # is actually attempted, so a gate below cannot consume the reply
        # without acting on it.
        self.assertTrue(context.gh.pinned_data(fixtures.ISSUE).get(
            fixtures.KEY_AWAITING_HUMAN,
        ))

    def test_only_trusted_replies_release_a_park(self) -> None:
        trailing_outsider = self._parked_context(
            comments=(
                (RETRY_COMMENT_ID, TRUSTED_LOGIN),
                (OUTSIDER_COMMENT_ID, OUTSIDER_LOGIN),
            ),
        )
        outsider_only = self._parked_context(
            comments=((RETRY_COMMENT_ID, OUTSIDER_LOGIN),),
        )

        with patch.object(config, "ALLOWED_ISSUE_AUTHORS", ALLOWLIST):
            released = eligibility._auto_rebase_retry_decision(
                trailing_outsider,
            )
            refused = eligibility._auto_rebase_retry_decision(outsider_only)

        # The watermark a retry would advance to names the trusted reply
        # only, so the outsider comment after it is left unconsumed.
        self.assertEqual(released.consumed_comment_id, RETRY_COMMENT_ID)
        self.assertFalse(refused.should_continue)

    def _parked_context(
        self,
        *,
        reason: str = PARK_PUSH_FAILED,
        comments=((RETRY_COMMENT_ID, TRUSTED_LOGIN),),
    ):
        return fixtures._sync_context(
            comments=comments,
            awaiting_human=True,
            park_reason=reason,
            last_action_comment_id=PARK_WATERMARK_COMMENT_ID,
        )


class OpenPrTest(unittest.TestCase):
    """Terminal and unreadable PRs belong to the handler that finalizes them."""

    def test_open_pr_is_handed_back(self) -> None:
        context = fixtures._sync_context()
        pr = fixtures._add_pr(context.gh)

        self.assertIs(eligibility._open_auto_rebase_pr(context), pr)

    def test_unreadable_pr_leaves_state_alone(self) -> None:
        # No PR is registered, so the read raises. A half-known PR state is
        # not grounds for touching the anchor: the next tick retries from it.
        context = self._anchored_context()

        self.assertIsNone(eligibility._open_auto_rebase_pr(context))
        self.assertEqual(
            context.gh.pinned_data(fixtures.ISSUE).get(
                fixtures.KEY_PENDING_PUSH_SHA,
            ),
            fixtures.PRE_REBASE_SHA,
        )

    def test_terminal_pr_clears_a_pinned_anchor(self) -> None:
        for merged, pr_state in TERMINAL_PR_STATES:
            with self.subTest(merged=merged):
                context = self._anchored_context()
                fixtures._add_pr(
                    context.gh, merged=merged, pr_state=pr_state,
                )

                self.assertIsNone(
                    eligibility._open_auto_rebase_pr(context),
                )

                # A terminal PR makes the recovery target meaningless, so
                # the anchor must not survive into a re-opened future.
                self.assertIsNone(
                    context.gh.pinned_data(fixtures.ISSUE).get(
                        fixtures.KEY_PENDING_PUSH_SHA,
                    ),
                )

    def test_unanchored_terminal_pr_writes_nothing(self) -> None:
        context = fixtures._sync_context()
        fixtures._add_pr(context.gh, merged=True, pr_state="closed")
        write = MagicMock()

        with patch.object(context.gh, "write_pinned_state", write):
            self.assertIsNone(eligibility._open_auto_rebase_pr(context))

        write.assert_not_called()

    def test_terminal_pr_ends_the_whole_handoff(self) -> None:
        # The anchor is the least of what an attempt leaves: the debt and the
        # permission beside it are ended too, from the head the pull request
        # ended on, since that head may be the rewrite the permission names.
        context = self._anchored_context()
        merged, pr_state = TERMINAL_PR_STATES[0]
        fixtures._add_pr(context.gh, merged=merged, pr_state=pr_state)
        pull_request = context.gh.pulls[fixtures.PR_NUMBER]
        retired = MagicMock()

        with patch.object(_terminal_handoff, "_retires_the_terminal_handoff", retired):
            self.assertIsNone(eligibility._open_auto_rebase_pr(context))

        retired.assert_called_once_with(context, pull_request.head.sha)

    def _anchored_context(self):
        return fixtures._sync_context(
            pending_auto_base_rebase_push_sha=fixtures.PRE_REBASE_SHA,
            pending_pre_rebase_sha=fixtures.PRE_REBASE_SHA,
        )


class RecoveryDecisionTest(unittest.TestCase):
    """Crash recovery runs first, and only an unspent retry survives it."""

    def test_no_anchor_keeps_the_reported_retry(self) -> None:
        recover = _handled()

        with _patched(**{RECOVER: recover}):
            decision = eligibility._auto_rebase_recovery_decision(
                fixtures._sync_context(), RETRY_COMMENT_ID,
            )

        recover.assert_not_called()
        self.assertTrue(decision.should_continue)
        self.assertEqual(decision.consumed_comment_id, RETRY_COMMENT_ID)

    def test_finished_recovery_owns_the_tick(self) -> None:
        recover = _handled()

        with _patched(**{RECOVER: recover}):
            decision = eligibility._auto_rebase_recovery_decision(
                self._anchored_context(), RETRY_COMMENT_ID,
            )

        self.assertFalse(decision.should_continue)
        # Recovery is the side that can publish the rewrite, so the retry it
        # was handed is what it unparks with.
        self.assertEqual(
            recover.call_args.kwargs.get("unparking_consumed_max"),
            RETRY_COMMENT_ID,
        )
        self.assertEqual(
            recover.call_args.kwargs.get("behind"), fixtures.BEHIND_BY,
        )

    def test_released_park_drops_a_spent_retry(self) -> None:
        # Recovery cleared the park itself, so the reply it consumed must not
        # be re-consumed by the rebase this tick continues into.
        with _patched(**{RECOVER: _handled(recovered=False)}):
            decision = eligibility._auto_rebase_recovery_decision(
                self._anchored_context(), RETRY_COMMENT_ID,
            )

        self.assertTrue(decision.should_continue)
        self.assertIsNone(decision.consumed_comment_id)

    def test_surviving_park_keeps_its_retry(self) -> None:
        with _patched(**{RECOVER: _handled(recovered=False)}):
            decision = eligibility._auto_rebase_recovery_decision(
                self._anchored_context(awaiting_human=True),
                RETRY_COMMENT_ID,
            )

        self.assertTrue(decision.should_continue)
        self.assertEqual(decision.consumed_comment_id, RETRY_COMMENT_ID)

    def _anchored_context(self, **state_fields):
        return fixtures._sync_context(
            pending_pre_rebase_sha=fixtures.PRE_REBASE_SHA,
            **state_fields,
        )


class NormalStartTest(unittest.TestCase):
    """A rebase starts only on a clean worktree that is behind base."""

    def test_dirty_worktree_blocks_the_start(self) -> None:
        # Uncommitted edits would be force-pushed alongside the rebase, so
        # the reviewer would vote on a tree the PR head does not carry.
        dirty = MagicMock(return_value=list(LEFTOVERS))

        with _patched(**{DIRTY_FILES: dirty}):
            self.assertFalse(
                eligibility._normal_auto_rebase_can_start(
                    fixtures._sync_context(),
                ),
            )

    def test_clean_worktree_starts_only_when_behind(self) -> None:
        for behind, expected in ((0, False), (fixtures.BEHIND_BY, True)):
            with (
                self.subTest(behind=behind),
                _patched(**{DIRTY_FILES: MagicMock(return_value=[])}),
            ):
                self.assertEqual(
                    eligibility._normal_auto_rebase_can_start(
                        fixtures._sync_context(behind=behind),
                    ),
                    expected,
                )


if __name__ == "__main__":
    unittest.main()
