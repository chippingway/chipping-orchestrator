# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The parks and the reset-and-park tail on the `persistence` owner, and the recovery answer it transports.

A recovery context may carry what its recovery owes over a landed reset. It is
optional, and a context carrying none takes the tail exactly as a refresh's own
context does. Every park's record lands as the attempt's checkpoint, over the
reading the tick last confirmed: behind the tick's own earlier writes, with what
it staged since counted once, and -- refused, lost, or over an attempt or its
evidence that moved without this road -- with nothing put back over the comment.
"""

from __future__ import annotations

import unittest
from dataclasses import replace
from functools import partial
from itertools import product
from types import MappingProxyType
from unittest.mock import MagicMock, patch

from orchestrator.git import commands
from orchestrator.git.base_sync import persistence, recovery_holds
from orchestrator.github.pinned_state import MAX_PINNED_BODY, pinned_state_body
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

# The strict edit a park's record lands through, as the attempt's checkpoint.
RECORD_STATE = "edit_pinned_state"

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
_ANSWERED = ([fixtures.PRE_REBASE_SHA], SETTLED, None, [RECORD_STATE])

_UNANSWERED = ([], None, fixtures.PRE_REBASE_SHA, [RECORD_STATE])

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

# A run's usage the tick staged since its last write, over the total the
# comment carried: counted once by the park that carries it.
KEY_TOKENS = "issue_total_tokens"

_READ_TOKENS = 100

_STAGED_TOKENS = 150

# An anchor and an evidence floor the comment came to carry after the tick
# read it, by no write of this road's.
_MOVED_ANCHOR = "0dd0a5c4" * 5

KEY_REVISION_FLOOR = "verification_evidence_revision"

# A field the tick's own write fills the comment with, leaving less room than
# a park's record takes.
KEY_PADDING = "padding"

_SHORT_OF_THE_PARK = 10

# What a park whose record did not land leaves the comment carrying: its
# anchor, whether it records the park, and its evidence floor.
_CARRIED = (fixtures.KEY_PENDING_PUSH_SHA, fixtures.KEY_AWAITING_HUMAN, KEY_REVISION_FLOOR)

# How a park's record can fail to land behind its notice, beside what the
# comment then carries: GitHub refusing the edit, or landing it and losing its
# answer, as the client names each; or a record of the attempt or its evidence
# the comment came to spell otherwise after the tick read it, by no write of
# this road's, which only an invariant failure explains and which is kept as
# it stands.
_UNLANDED_PARKS = (
    ("refused", "refused", (fixtures.PRE_REBASE_SHA, None, None)),
    ("landed, its answer lost", "lost", (fixtures.PRE_REBASE_SHA, True, None)),
    ("the attempt moved", (fixtures.KEY_PENDING_PUSH_SHA, _MOVED_ANCHOR), (_MOVED_ANCHOR, None, None)),
    ("the evidence moved", (KEY_REVISION_FLOOR, 3), (fixtures.PRE_REBASE_SHA, None, 3)),
)

# How the comment can fail to answer as the tick last confirmed it before a
# reset is made, beside the field read back and what it still carries: the
# anchor or the evidence floor spelled otherwise by no write of the tick's, and
# a comment that would not read at all.
_UNOWNED = (
    ("the anchor moved", (fixtures.KEY_PENDING_PUSH_SHA, _MOVED_ANCHOR), fixtures.KEY_PENDING_PUSH_SHA, _MOVED_ANCHOR),
    ("the evidence floor moved", (KEY_REVISION_FLOOR, 3), KEY_REVISION_FLOOR, 3),
    ("the comment would not read", "unreadable", fixtures.KEY_PENDING_PUSH_SHA, fixtures.PRE_REBASE_SHA),
)

# Two ways an attempt carrying records past its anchor is released by nothing,
# beside whether git lands the reset and how the park's record is broken: a
# reset that failed, under a park that lands keeping the attempt; and a reset
# that landed, under a park whose record GitHub refused.
_UNRELEASED = (("a reset that failed", False, None), ("a landed reset's record refused", True, "refused"))


def _breaks(context, how) -> None:
    """Fail `context`'s next pinned-comment edit as the client names `how`, or set the field `how` pairs on the comment.

    The field is set as no write of the tick's: the comment comes to spell it
    otherwise than the tick read it.
    """
    if isinstance(how, str):
        getattr(context.gh.pinned_failures, how).add(fixtures.ISSUE)
        return
    moved = context.gh.read_pinned_state(context.issue)
    moved.set(*how)
    context.gh.write_pinned_state(context.issue, moved)


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
            ordered, context.gh, ISSUE_COMMENT, EMIT_EVENT, RECORD_STATE,
        ):
            persistence._park_auto_rebase_failure(
                context.gh,
                context.issue,
                context.state,
                message=PARK_MESSAGE,
                reason=fixtures.PARK_PUSH_FAILED,
            )

        # The pinned-state record commits the park: the HITL comment and the
        # audit event both land while the durable state still says unparked.
        self.assertEqual(
            ordered,
            [ISSUE_COMMENT, f"{EMIT_EVENT}:{PARK_EVENT}", RECORD_STATE],
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

    def test_the_record_lands_behind_an_own_write(self) -> None:
        # The tick's own earlier write is a checkpoint rather than a move, so
        # the park's record lands over it, carrying the usage staged since
        # once, and the tick's state then reads as the comment does.
        context, published = self._parks()

        recorded = (published[KEY_ANNOUNCED_SHA], published[KEY_TOKENS], published[fixtures.KEY_AWAITING_HUMAN])
        self.assertEqual(recorded, (fixtures.RECOVERED_SHA, _STAGED_TOKENS, True))
        self.assertEqual(context.state.synced, context.gh.read_pinned_state(context.issue).synced)
        self.assertFalse(context.state.withheld)

    def test_an_unlanded_record_goes_no_further(self) -> None:
        # The notice is out either way. A record GitHub refused writes
        # nothing, one whose answer was lost may have landed, and one over an
        # attempt or evidence that moved without this road is refused with
        # that move kept as it stands: each is logged, and the tick's state is
        # withheld so nothing behind it writes the comment whole.
        for unlanded, breaks, carried in _UNLANDED_PARKS:
            with self.subTest(unlanded=unlanded), self.assertLogs("orchestrator.base_sync", "WARNING"):
                context, published = self._parks(breaks)

                self.assertEqual(tuple(map(published.get, _CARRIED)), carried)
                self.assertIn(PARK_MESSAGE, context.gh.posted_comments[-1][1])
                self.assertTrue(context.state.withheld)

    def test_a_record_with_no_room_is_withheld(self) -> None:
        # The comment, as the tick's own write left it, has no room for the
        # park's record: that record is refused for room with nothing written,
        # and the tick's state -- carrying the park the comment does not -- is
        # withheld from every whole-state write behind it all the same.
        context = fixtures._recovery_context(**{fixtures.KEY_PENDING_PUSH_SHA: fixtures.PRE_REBASE_SHA})
        context.state.set(KEY_PADDING, "")
        room = MAX_PINNED_BODY - len(pinned_state_body(context.state.data)) - _SHORT_OF_THE_PARK
        context.state.set(KEY_PADDING, "x" * room)
        context.gh.write_pinned_state(context.issue, context.state)

        with self.assertLogs("orchestrator.base_sync", "WARNING") as logged:
            persistence._park_auto_rebase_failure(
                context.gh, context.issue, context.state, message=PARK_MESSAGE, reason=fixtures.PARK_PUSH_FAILED,
            )
            self.assertIn("came back overflow", "\n".join(logged.output))

        self.assertIsNone(context.gh.read_pinned_state(context.issue).get(fixtures.KEY_AWAITING_HUMAN))
        self.assertTrue(context.state.withheld)

    def _parks(self, breaks=None) -> tuple:
        """Park an attempt behind the tick's own write and a run's usage staged since, `breaks` done first.

        The context, and what the comment then carries.
        """
        context = fixtures._recovery_context(**{
            fixtures.KEY_PENDING_PUSH_SHA: fixtures.PRE_REBASE_SHA, KEY_TOKENS: _READ_TOKENS,
        })
        context.state.set(KEY_ANNOUNCED_SHA, fixtures.RECOVERED_SHA)
        context.gh.write_pinned_state(context.issue, context.state)
        context.state.set(KEY_TOKENS, _STAGED_TOKENS)
        if breaks is not None:
            _breaks(context, breaks)
        persistence._park_auto_rebase_failure(
            context.gh, context.issue, context.state, message=PARK_MESSAGE, reason=fixtures.PARK_PUSH_FAILED,
        )
        return context, context.gh.pinned_data(fixtures.ISSUE)


class ResetClearAndParkTest(unittest.TestCase):
    """`_reset_clear_and_park` restores HEAD, drops the anchor, then parks."""

    def test_reset_targets_the_anchor_and_clears_it(self) -> None:
        context, hardened, ordered = self._reset_and_park()

        self.assertEqual(hardened.call_args.args, RESET_ARGS)
        self.assertEqual(
            hardened.call_args.kwargs.get("cwd"), fixtures.WORKTREE,
        )
        # HEAD is restored before anything is published, and the pinned-state
        # record is last: the HITL comment and the audit event both describe a
        # worktree already back on the anchor.
        self.assertEqual(
            ordered,
            [
                f"{fixtures.GIT_HARDENED}:reset",
                ISSUE_COMMENT,
                f"{EMIT_EVENT}:{PARK_EVENT}",
                RECORD_STATE,
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

    def test_an_unreleased_attempt_is_kept_whole(self) -> None:
        # A reset that failed parks all the same -- `awaiting_human` is what
        # short-circuits the same-tick handlers, and it has to land even when
        # the worktree is left on an unexpected SHA for the operator to
        # inspect. What may not go with it is the record: a reset that failed
        # abandoned nothing, so the comment is the only account of where the
        # checkout may be standing. Dropped there, the next tick has no
        # anchor to bring the recovery back with and no id to ask for the
        # candidate by, and the permission the reset could not undo is left
        # with nothing naming the attempt it belongs to. A reset that landed
        # under a park whose record GitHub refused released nothing either:
        # the next tick finds the checkout back on the anchor and recovers
        # that same attempt again.
        for unreleased, resets, breaks in _UNRELEASED:
            with self.subTest(unreleased=unreleased):
                context = self._reset_and_park(
                    hardened=MagicMock(return_value=_GIT_ANSWERS[resets]), in_flight=True, breaks=breaks,
                )[0]

                published = context.gh.pinned_data(fixtures.ISSUE)
                self.assertIs(bool(published.get(fixtures.KEY_AWAITING_HUMAN)), breaks is None)
                self.assertLessEqual(_IN_FLIGHT.items(), published.items())

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
        breaks=None,
    ):
        seeded = dict(_IN_FLIGHT) if in_flight else {
            fixtures.KEY_PENDING_PUSH_SHA: fixtures.PRE_REBASE_SHA,
        }
        context = fixtures._recovery_context(**seeded)
        if breaks is not None:
            _breaks(context, breaks)
        hardened = hardened or MagicMock(return_value=fixtures._git_result())
        ordered: list[str] = []
        recorder = _OrderedCall(ordered, fixtures.GIT_HARDENED, hardened)
        with _recorded_calls(
            ordered, context.gh, ISSUE_COMMENT, EMIT_EVENT, RECORD_STATE,
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
    """What a recovery owes over its landed reset rides the park's one write; nothing is reset over a moved record."""

    def test_the_answer_rides_the_park_write(self) -> None:
        # Asked while the attempt it answers for still stands, whether the
        # recovery reset the checkout itself or the refresh took the abort
        # over a checkout nobody could count; a reset that failed moved
        # nothing, so nothing is asked and the attempt stays.
        for road, exit_code in product((_resets, _aborts), (0, fixtures.GIT_FAILURE_EXIT_CODE)):
            with self.subTest(road=road.__name__, exit_code=exit_code):
                self.assertEqual(self._takes(road, exit_code), _UNANSWERED if exit_code else _ANSWERED)

    def test_a_record_not_as_confirmed_resets_nothing(self) -> None:
        # The reset is decided on the attempt and its evidence as the tick
        # last confirmed them, and moves the checkout ahead of every write.
        # Where the comment spells either otherwise -- moved by no write of
        # the recovery's -- or would not read at all, nothing is reset or
        # cleaned, nothing is asked of the recovery or posted, and the comment
        # stands as it is, whichever road the reset was taken on.
        for road, (unowned, breaks, field, kept) in product((_resets, _aborts), _UNOWNED):
            with self.subTest(road=road.__name__, unowned=unowned):
                self.assertEqual(self._resets_nothing(road, breaks, field), kept)

    def _takes(self, road, exit_code: int) -> tuple:
        """Take `road` over a reset git answers with `exit_code`, and read it back."""
        owed = _Owed()
        context, takes = road(owed)
        ordered: list[str] = []
        with _recorded_calls(ordered, context.gh, RECORD_STATE), patch.object(
            commands, fixtures.GIT_HARDENED, MagicMock(return_value=fixtures._git_result(returncode=exit_code)),
        ):
            takes()
        published = context.gh.pinned_data(fixtures.ISSUE)
        return owed.asked, published.get(KEY_SETTLED), published.get(fixtures.KEY_PENDING_PUSH_SHA), ordered
    def _resets_nothing(self, road, breaks, field: str):
        """Take `road` with `breaks` done to its comment first, asserting nothing was made; what `field` then reads."""
        owed = _Owed()
        context, takes = road(owed)
        _breaks(context, breaks)
        hardened = MagicMock(return_value=fixtures._git_result())
        with (
            patch.object(commands, fixtures.GIT_HARDENED, hardened),
            self.assertLogs("orchestrator.base_sync", "WARNING"),
        ):
            takes()
        hardened.assert_not_called()
        self.assertEqual((owed.asked, context.gh.posted_comments), ([], []))
        return context.gh.pinned_data(fixtures.ISSUE).get(field)


class _Owed:
    """A recovery's answer over its reset: a record staged on `state` once it landed, each asking noted."""

    def __init__(self) -> None:
        self.state = None
        self.asked: list[str | None] = []

    def __call__(self) -> None:
        self.asked.append(self.state.get(fixtures.KEY_PENDING_PUSH_SHA))
        self.state.set(KEY_SETTLED, SETTLED)


def _resets(owed: _Owed):
    """A recovery context carrying `owed`, and the reset-and-park tail it takes."""
    context = fixtures._recovery_context(**_IN_FLIGHT)
    owed.state = context.state
    return context, partial(
        persistence._reset_clear_and_park,
        replace(context, settles_over_a_reset=owed),
        fixtures.PRE_REBASE_SHA,
        message=PARK_MESSAGE,
        reason=fixtures.PARK_PUSH_FAILED,
    )


def _aborts(owed: _Owed):
    """A refresh's context over a checkout nobody could count, and the abort it takes, handed `owed`."""
    context = fixtures._sync_context(pending_pre_rebase_sha=fixtures.PRE_REBASE_SHA, **_IN_FLIGHT)
    owed.state = context.state
    return context, partial(
        recovery_holds._answers_an_unreadable_checkout, context, None, settles_over_a_reset=owed,
    )


if __name__ == "__main__":
    unittest.main()
