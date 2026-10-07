# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The parks and the reset-and-park tail on the `persistence` owner."""

from __future__ import annotations

import unittest
from types import MappingProxyType
from unittest.mock import MagicMock, patch

from orchestrator.git import commands
from orchestrator.git.base_sync import persistence
from tests.git.base_sync import base_sync_helpers as fixtures
from tests.git.base_sync.base_sync_helpers import _OrderedCall, _recorded_calls

PARK_MESSAGE = "@human the rebase could not finalize"

RESET_ARGS = ("reset", "--hard", fixtures.PRE_REBASE_SHA)

CLEAN_ARGS = ("clean", "-fd")

REASON_FIELD = "reason"

PARK_EVENT = "park_awaiting_human"

# The client calls whose order is the contract these owners publish through.
ISSUE_COMMENT = "comment"

EMIT_EVENT = "emit_event"

WRITE_STATE = "write_pinned_state"

KEY_ANNOUNCED_SHA = "pending_auto_base_rebase_announced_sha"

# Everything one interrupted attempt carries past the anchor: the replay it
# recorded making and the publication it made it for, the head a finish said
# it had already announced, and the debt the gate wrote before the push. A
# reset that landed abandons every one of them; a reset that failed abandons
# none.
_IN_FLIGHT = MappingProxyType({
    fixtures.KEY_PENDING_PUSH_SHA: fixtures.PRE_REBASE_SHA,
    "pending_auto_base_rebase_rewrite_sha": fixtures.RECOVERED_SHA,
    "pending_auto_base_rebase_rewrite_pr": fixtures.PR_NUMBER,
    "pending_auto_base_rebase_rewrite_stage": fixtures.VALIDATING,
    KEY_ANNOUNCED_SHA: fixtures.RECOVERED_SHA,
    "late_approved_sha": fixtures.RECOVERED_SHA,
    "late_approved_lease": fixtures.PRE_REBASE_SHA,
})


class ParkAutoRebaseFailureTest(unittest.TestCase):
    """`_park_auto_rebase_failure` parks with a durable, recognizable reason."""

    def test_park_lands_on_the_issue_thread(self) -> None:
        context = fixtures._recovery_context()
        ordered: list[str] = []

        with _recorded_calls(
            ordered, context.gh, ISSUE_COMMENT, EMIT_EVENT, WRITE_STATE,
        ):
            persistence._park_auto_rebase_failure(
                context.gh,
                context.issue,
                context.state,
                message=PARK_MESSAGE,
                reason=fixtures.PARK_PUSH_FAILED,
            )

        # The pinned-state write commits the park: the HITL comment and the
        # audit event both land while the durable state still says unparked.
        self.assertEqual(
            ordered,
            [ISSUE_COMMENT, f"{EMIT_EVENT}:{PARK_EVENT}", WRITE_STATE],
        )
        published = context.gh.pinned_data(fixtures.ISSUE)
        self.assertTrue(published.get(fixtures.KEY_AWAITING_HUMAN))
        # `_park_awaiting_human` clears `park_reason` by contract; the reason
        # has to survive that, because the refresh-time retry scan keys off it
        # to tell an auto-rebase park from every other awaiting-human park.
        self.assertEqual(
            published.get(fixtures.KEY_PARK_REASON), fixtures.PARK_PUSH_FAILED,
        )
        self.assertEqual(
            context.gh.recorded_events[-1].get(REASON_FIELD),
            fixtures.PARK_PUSH_FAILED,
        )
        # The message goes to the issue thread, not the PR -- the
        # resume-on-human-reply scan only reads the issue.
        issue_number, body = context.gh.posted_comments[-1]
        self.assertEqual(issue_number, fixtures.ISSUE)
        self.assertIn(PARK_MESSAGE, body)
        self.assertEqual(context.gh.posted_pr_comments, [])

    def test_reason_outside_the_park_set_is_refused(self) -> None:
        context = fixtures._recovery_context()

        with self.assertRaises(AssertionError):
            persistence._park_auto_rebase_failure(
                context.gh,
                context.issue,
                context.state,
                message=PARK_MESSAGE,
                reason="reviewer_timeout",
            )


class ResetClearAndParkTest(unittest.TestCase):
    """`_reset_clear_and_park` restores HEAD, drops the anchor, then parks."""

    def test_reset_targets_the_anchor_and_clears_it(self) -> None:
        context, hardened, ordered = self._reset_and_park()

        self.assertEqual(hardened.call_args.args, RESET_ARGS)
        self.assertEqual(
            hardened.call_args.kwargs.get("cwd"), fixtures.WORKTREE,
        )
        # HEAD is restored before anything is published, and the pinned-state
        # write is last: the HITL comment and the audit event both describe a
        # worktree already back on the anchor.
        self.assertEqual(
            ordered,
            [
                f"{fixtures.GIT_HARDENED}:reset",
                ISSUE_COMMENT,
                f"{EMIT_EVENT}:{PARK_EVENT}",
                WRITE_STATE,
            ],
        )
        published = context.gh.pinned_data(fixtures.ISSUE)
        # The reset put HEAD back on the anchor, so leaving it pinned would
        # only make a later tick re-enter the "HEAD == anchor" no-op case.
        self.assertIsNone(published.get(fixtures.KEY_PENDING_PUSH_SHA))
        self.assertTrue(published.get(fixtures.KEY_AWAITING_HUMAN))
        self.assertEqual(
            published.get(fixtures.KEY_PARK_REASON), fixtures.PARK_PUSH_FAILED,
        )

    def test_clean_discards_leftovers_after_the_reset(self) -> None:
        context, hardened, _ = self._reset_and_park(
            clean=True, reason=fixtures.PARK_DIRTY,
        )

        self.assertEqual(
            [recorded.args for recorded in hardened.call_args_list],
            [RESET_ARGS, CLEAN_ARGS],
        )
        # Each park path carries its own reason all the way into the audit
        # event, so an operator can tell a dirty park from a push failure.
        self.assertEqual(
            context.gh.recorded_events[-1].get(REASON_FIELD),
            fixtures.PARK_DIRTY,
        )

    def test_a_landed_reset_drops_the_whole_attempt(self) -> None:
        # The branch is back where the attempt started, so every field
        # describing what it did past that point names a commit only the
        # reflog still has.
        context, _, _ = self._reset_and_park(in_flight=True)

        published = context.gh.pinned_data(fixtures.ISSUE)
        for field in _IN_FLIGHT:
            with self.subTest(field=field):
                self.assertIsNone(published.get(field))

    def test_a_failed_reset_keeps_the_whole_attempt(self) -> None:
        # The park lands either way -- `awaiting_human` is what
        # short-circuits the same-tick handlers, and it has to land even when
        # the worktree is left on an unexpected SHA for the operator to
        # inspect. What may not go with it is the record: a reset that failed
        # abandoned nothing, so the comment is the only account of where the
        # checkout may be standing. Dropped there, the next tick has no
        # anchor to bring the recovery back with and no id to ask for the
        # candidate by, and the permission the reset could not undo is left
        # with nothing naming the attempt it belongs to.
        failed = MagicMock(
            return_value=fixtures._git_result(
                returncode=fixtures.GIT_FAILURE_EXIT_CODE,
                stderr="fatal: bad object\n",
            ),
        )

        context, _, _ = self._reset_and_park(hardened=failed, in_flight=True)

        published = context.gh.pinned_data(fixtures.ISSUE)
        self.assertTrue(published.get(fixtures.KEY_AWAITING_HUMAN))
        for field, recorded in _IN_FLIGHT.items():
            with self.subTest(field=field):
                self.assertEqual(published.get(field), recorded)

    def _reset_and_park(
        self,
        *,
        hardened: MagicMock | None = None,
        clean: bool = False,
        reason: str = fixtures.PARK_PUSH_FAILED,
        in_flight: bool = False,
    ):
        seeded = dict(_IN_FLIGHT) if in_flight else {
            fixtures.KEY_PENDING_PUSH_SHA: fixtures.PRE_REBASE_SHA,
        }
        context = fixtures._recovery_context(**seeded)
        hardened = hardened or MagicMock(return_value=fixtures._git_result())
        ordered: list[str] = []
        recorder = _OrderedCall(ordered, fixtures.GIT_HARDENED, hardened)
        with _recorded_calls(
            ordered, context.gh, ISSUE_COMMENT, EMIT_EVENT, WRITE_STATE,
        ), patch.object(commands, fixtures.GIT_HARDENED, recorder):
            persistence._reset_clear_and_park(
                context,
                fixtures.PRE_REBASE_SHA,
                message=PARK_MESSAGE,
                reason=reason,
                clean=clean,
            )
        return context, hardened, ordered


if __name__ == "__main__":
    unittest.main()
