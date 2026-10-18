# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The parks and the reset-and-park tail on the `persistence` owner, and the recovery answers it transports.

A recovery context may carry what its recovery owes over a landed reset, what
it records before the reset moves the checkout, and the park every recovery
park is recorded through. Each is optional, and a context carrying none takes
the tail exactly as a refresh's own context does.
"""

from __future__ import annotations

import unittest
from dataclasses import replace
from functools import partial
from itertools import product
from types import MappingProxyType
from unittest.mock import MagicMock, patch

from orchestrator.git import commands
from orchestrator.git.base_sync import (
    persistence,
    recovery_holds,
    replay_publication_parks,
    replay_transfer_parks,
)
from orchestrator.git.base_sync.models import _AutoRebaseRecoverySnapshot
from tests.git.base_sync import base_sync_helpers as fixtures
from tests.git.base_sync.base_sync_helpers import _OrderedCall, _recorded_calls

PARK_MESSAGE = "@human the rebase could not finalize"

RESET_ARGS = ("reset", "--hard", fixtures.PRE_REBASE_SHA)

CLEAN_ARGS = ("clean", "-fd")

REASON_FIELD = "reason"

# The reason a recovery that keeps a stranded attempt parks under.
PARK_FAILED = "auto_base_rebase_failed"

PARK_EVENT = "park_awaiting_human"

# The client calls whose order is the contract these owners publish through.
ISSUE_COMMENT = "comment"

EMIT_EVENT = "emit_event"

WRITE_STATE = "write_pinned_state"

KEY_ANNOUNCED_SHA = "pending_auto_base_rebase_announced_sha"

KEY_REWRITE_BASE = "pending_auto_base_rebase_rewrite_base"

# The base tip the attempt's replay was made onto.
ONTO_SHA = "0e70ba5e" * 5

# A record a recovery's answer to its landed reset stages, standing in for the
# abandonment of whatever it owes over the head the reset took the checkout off.
KEY_SETTLED = "settled_over_the_reset"

SETTLED = "settled"

# What a road taken over a reset that landed, and over one that failed, leaves:
# the anchor standing as the answer was asked, the answer's record, the anchor
# on the comment, and the park's one write.
_ANSWERED = ([fixtures.PRE_REBASE_SHA], SETTLED, None, [WRITE_STATE])

_UNANSWERED = ([], None, fixtures.PRE_REBASE_SHA, [WRITE_STATE])

# What a landed reset whose answer may not go with the release leaves: the
# answer asked, nothing written, and the anchor kept.
_HELD = ([fixtures.PRE_REBASE_SHA], None, fixtures.PRE_REBASE_SHA, [])

# The record a recovery makes before its reset, as the order of calls names it.
_RECORDED = "recorded"

_RESETTING = f"{fixtures.GIT_HARDENED}:reset"

# A recorded reset git answers with each exit code, and the anchor and base tip
# the park leaves: released over a reset that landed, kept whole over one that
# did not.
_RECORDED_RESETS = (
    (0, (None, None)),
    (fixtures.GIT_FAILURE_EXIT_CODE, (fixtures.PRE_REBASE_SHA, ONTO_SHA)),
)

# Everything one interrupted attempt carries past the anchor: the replay it
# recorded making, the base tip it made it onto, and the publication it made
# it for, the head a finish said it had already announced, and the debt the
# gate wrote before the push. A reset that landed abandons every one of them;
# a reset that failed abandons none.
_ANCHOR = fixtures.PRE_REBASE_SHA[:8]

# What the park's notice says behind the caller's reason, for each way the reset
# and a clean behind it can go: whether the reset lands, whether a clean ran and
# landed (None where none was asked), and what the notice says of them.
_OUTCOMES = (
    (True, None, (f"Local HEAD has been reset to `{_ANCHOR}`", "is dropped by the pinned-state write")),
    (False, None, (f"`git reset --hard {_ANCHOR}` failed (`fatal: bad object`)", "keeps the attempt")),
    (True, True, ("has been reset", ", and untracked files were cleaned")),
    (True, False, ("has been reset", "`git clean -fd` failed, so untracked files may remain")),
    (False, True, ("did not land", "though untracked files were cleaned")),
    (False, False, ("did not land", "`git clean -fd` failed too")),
)

# What git answers a reset or a clean that landed, and one that failed.
_GIT_ANSWERS = MappingProxyType({
    True: fixtures._git_result(),
    False: fixtures._git_result(returncode=fixtures.GIT_FAILURE_EXIT_CODE, stderr="fatal: bad object\n"),
})

_IN_FLIGHT = MappingProxyType({
    fixtures.KEY_PENDING_PUSH_SHA: fixtures.PRE_REBASE_SHA,
    "pending_auto_base_rebase_rewrite_sha": fixtures.RECOVERED_SHA,
    KEY_REWRITE_BASE: ONTO_SHA,
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

    def test_the_notice_says_what_the_reset_came_to(self) -> None:
        # The caller says why it parks, and the tail what its reset, the clean
        # behind it, and the drop came to: a reset that failed is never
        # reported as made, nor an attempt it kept as dropped.
        for resets, cleans, said in _OUTCOMES:
            with self.subTest(resets=resets, cleans=cleans):
                notice = self._notice(resets=resets, cleans=cleans)

                self.assertTrue(notice.startswith(PARK_MESSAGE), notice)
                self.assertEqual([phrase in notice for phrase in said], [True, True], notice)
                self.assertNotIn("did not land" if resets else "has been reset", notice)

    def _notice(self, *, resets: bool, cleans: bool | None) -> str:
        """The notice a park posts behind a reset that `resets` lands and a clean `cleans` says came to."""
        answers = (_GIT_ANSWERS[resets], _GIT_ANSWERS[bool(cleans)])
        hardened = MagicMock(side_effect=answers)
        context, _, _ = self._reset_and_park(hardened=hardened, clean=cleans is not None)
        return context.gh.posted_comments[-1][1]

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



class ResetAnswerTest(unittest.TestCase):
    """What a recovery owes over its landed reset rides the park's one write beside the attempt's release."""

    def test_the_answer_rides_the_park_write(self) -> None:
        # Asked while the attempt it answers for still stands, whether the
        # recovery reset the checkout itself or the refresh took the abort
        # over a checkout nobody could count; a reset that failed moved
        # nothing, so nothing is asked and the attempt stays.
        for road, exit_code in product((_resets, _aborts), (0, fixtures.GIT_FAILURE_EXIT_CODE)):
            with self.subTest(road=road.__name__, exit_code=exit_code):
                self.assertEqual(self._takes(road, exit_code), _UNANSWERED if exit_code else _ANSWERED)

    def test_only_a_refusing_answer_holds(self) -> None:
        # An answer that settles says True and releases; one that says False
        # keeps the attempt guarding its record, nothing written or parked.
        for road, releases in product((_resets, _aborts), (True, False)):
            with self.subTest(road=road.__name__, releases=releases):
                left = _ANSWERED if releases else _HELD
                self.assertEqual(self._takes(road, 0, releases=releases), left)

    def test_an_unrecorded_reset_is_not_made(self) -> None:
        # Nothing is reset, written, or parked, and the attempt stands with
        # its base tip for the next tick to record again.
        for road in (_resets, _aborts):
            with self.subTest(road=road.__name__):
                ordered, published = self._records(road, recorded=False, exit_code=0)

                standing = (published[fixtures.KEY_PENDING_PUSH_SHA], published[KEY_REWRITE_BASE])
                self.assertEqual((ordered, standing), ([_RECORDED], (fixtures.PRE_REBASE_SHA, ONTO_SHA)))

    def test_the_record_comes_before_the_reset(self) -> None:
        # A reset that lands is released in the park's write; one git refused
        # moved nothing, so the tip the record blanked is staged back for the
        # park that keeps the attempt.
        for exit_code, kept in _RECORDED_RESETS:
            with self.subTest(exit_code=exit_code):
                ordered, published = self._records(_resets, recorded=True, exit_code=exit_code)

                standing = (published.get(fixtures.KEY_PENDING_PUSH_SHA), published.get(KEY_REWRITE_BASE))
                self.assertEqual((ordered, standing), ([_RECORDED, _RESETTING, WRITE_STATE], kept))

    def _takes(self, road, exit_code: int, *, releases: bool = True) -> tuple:
        """Take `road` over a reset git answers with `exit_code`, owed an answer of `releases`, and read it back."""
        owed = _Owed(releases)
        context, takes = road(owed)
        ordered: list[str] = []
        with _recorded_calls(ordered, context.gh, WRITE_STATE), patch.object(
            commands, fixtures.GIT_HARDENED, MagicMock(return_value=fixtures._git_result(returncode=exit_code)),
        ):
            takes()
        published = context.gh.pinned_data(fixtures.ISSUE)
        return owed.asked, published.get(KEY_SETTLED), published.get(fixtures.KEY_PENDING_PUSH_SHA), ordered

    def _records(self, road, *, recorded: bool, exit_code: int) -> tuple:
        """Take `road` handed a record of its reset that `recorded`, over a reset git answers with `exit_code`."""
        owed = _Owed(recorded=recorded)
        context, takes = road(owed, records_before_a_reset=owed.records)
        answer = MagicMock(return_value=_GIT_ANSWERS[not exit_code])
        hardened = _OrderedCall(owed.ordered, fixtures.GIT_HARDENED, answer)
        with _recorded_calls(owed.ordered, context.gh, WRITE_STATE), patch.object(
            commands, fixtures.GIT_HARDENED, hardened,
        ):
            takes()
        return owed.ordered, context.gh.pinned_data(fixtures.ISSUE)


class _Owed:
    """A recovery's answers over its reset: a record staged on `state` once it landed, and one made ahead of it.

    `releases` is what the answer to a landed reset says: True to release the attempt, or
    False to keep it. `recorded` is whether the record made ahead of the reset
    (`records`) lands, blanking the base tip on the tick's state; each one is
    noted in `ordered`.
    """

    def __init__(self, releases: bool = True, *, recorded: bool = True) -> None:
        self.state = None
        self.asked: list[str | None] = []
        self.ordered: list[str] = []
        self._releases = releases
        self._recorded = recorded

    def __call__(self) -> bool:
        self.asked.append(self.state.get(fixtures.KEY_PENDING_PUSH_SHA))
        self.state.set(KEY_SETTLED, SETTLED)
        return self._releases

    def records(self, context) -> bool:
        """Record the reset ahead of it: the base tip blanked on `context`'s state, where the record lands."""
        self.ordered.append(_RECORDED)
        if self._recorded:
            context.state.set(KEY_REWRITE_BASE, None)
        return self._recorded


class RecoveryParkTest(unittest.TestCase):
    """A recovery context's own park records every recovery park; a context with none writes the state whole."""

    def test_a_carried_park_records_each_park(self) -> None:
        # The reset tail, over a reset that landed or not, and the parks that
        # never reset: each is handed to the context's park with its reason,
        # and nothing posts or writes the tick's state whole.
        for name, parks, exit_code, reason in _CARRIED_PARKS:
            with self.subTest(park=name):
                self.assertEqual(self._parks(parks, exit_code), ([reason], []))

    def test_a_carried_park_refuses_a_foreign_reason(self) -> None:
        foreign = partial(persistence._parks_the_recovery, message=PARK_MESSAGE, reason="reviewer_timeout")

        with self.assertRaises(AssertionError):
            self._parks(foreign)

    def _parks(self, parks, exit_code: int = 0) -> tuple:
        """Take `parks` over a context carrying its own park and a reset git answers with `exit_code`.

        The reasons that park was handed, and the client calls made beside it.
        """
        park = MagicMock()
        context = fixtures._recovery_context(**_IN_FLIGHT)
        ordered: list[str] = []
        with _recorded_calls(ordered, context.gh, ISSUE_COMMENT, WRITE_STATE), patch.object(
            commands, fixtures.GIT_HARDENED, MagicMock(return_value=_GIT_ANSWERS[not exit_code]),
        ):
            parks(replace(context, lands_a_park=park))
        reasons = [handed.args[2] for handed in park.call_args_list]
        return reasons, ordered


_TAIL = partial(
    persistence._reset_clear_and_park,
    reset_sha=fixtures.PRE_REBASE_SHA,
    message=PARK_MESSAGE,
    reason=fixtures.PARK_PUSH_FAILED,
)

_UNFINISHED = partial(
    replay_transfer_parks._park_unfinished_recovery,
    recovery_snapshot=_AutoRebaseRecoverySnapshot(branch=fixtures.BRANCH, local_head=fixtures.RECOVERED_SHA),
    detail="the route could not close",
)

# Every park a recovery takes, the reset git answers it with, and its reason.
_CARRIED_PARKS = (
    ("the tail over a landed reset", _TAIL, 0, fixtures.PARK_PUSH_FAILED),
    ("the tail over a failed reset", _TAIL, fixtures.GIT_FAILURE_EXIT_CODE, fixtures.PARK_PUSH_FAILED),
    ("the unfinished park", _UNFINISHED, 0, fixtures.PARK_PUSH_FAILED),
    ("the stranded park", replay_publication_parks._park_stranded_recovery, 0, PARK_FAILED),
)


def _resets(owed: _Owed, **answers):
    """A recovery context carrying `owed` and `answers`, and the reset-and-park tail it takes."""
    context = fixtures._recovery_context(**_IN_FLIGHT)
    owed.state = context.state
    return context, partial(
        persistence._reset_clear_and_park,
        replace(context, settles_over_a_reset=owed, **answers),
        fixtures.PRE_REBASE_SHA,
        message=PARK_MESSAGE,
        reason=fixtures.PARK_PUSH_FAILED,
    )


def _aborts(owed: _Owed, **answers):
    """A refresh's context over a checkout nobody could count, and the abort it takes, handed `owed` and `answers`."""
    context = fixtures._sync_context(pending_pre_rebase_sha=fixtures.PRE_REBASE_SHA, **_IN_FLIGHT)
    owed.state = context.state
    return context, partial(
        recovery_holds._answers_an_unreadable_checkout, context, None, settles_over_a_reset=owed, **answers,
    )


if __name__ == "__main__":
    unittest.main()
