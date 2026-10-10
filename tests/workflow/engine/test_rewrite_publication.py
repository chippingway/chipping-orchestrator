# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The ordinary publication of a clean rebase, through the per-tick refresh and the workflow's coordinator.

The gate rules on the candidate the git owner read before anything is pushed,
the git owner reads it again and publishes exactly that candidate under its
anchor's lease -- or refuses what moved since it was read, or proves a remote
already standing on it rather than taking a reading's word -- with the gate's
ending barrier between that reading and the push, and a landing is finished
once. Each case reads back what GitHub was left with: PR #42's head, the
label, the pinned record, the notices and events, and what the next tick does.
"""
from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from orchestrator.workflow.engine import base_refresh as _base_refresh
from tests.git.base_sync import refresh_test_support as base
from tests.git.base_sync.report_debt_test_support import owed
from tests.git.base_sync.sync_test_support import _patch_base_sync
from tests.workflow.engine import (
    rewrite_gate_holds_support as holds,
    rewrite_publication_moves as moves,
    rewrite_publication_test_support as world,
)
from tests.workflow.observation_support import ObservedCloseCase

ISSUE = base.ISSUE

LABEL_VALIDATING = "workflow:validating"

KEY_AWAITING_HUMAN = "awaiting_human"
KEY_PARK_REASON = "park_reason"
KEY_WATERMARK = "last_action_comment_id"
KEY_REVIEW_ROUND = "review_round"
KEY_REWRITE_DEBT = "developer_report_rewrite_debt"
KEY_PENDING_PUSH = "pending_auto_base_rebase_push_sha"
KEY_REWRITE_SHA = "pending_auto_base_rebase_rewrite_sha"

# Every field one attempt puts on the comment, which a finish or a rollback retires as one.
ATTEMPT_KEYS = (
    KEY_PENDING_PUSH,
    "pending_auto_base_rebase_rewrite_pr",
    "pending_auto_base_rebase_rewrite_stage",
    KEY_REWRITE_SHA,
    "pending_auto_base_rebase_announced_sha",
)

RETIRED = dict.fromkeys(ATTEMPT_KEYS)

PARK_PUSH_FAILED = "auto_base_rebase_push_failed"

# The one push a publication makes: the replay, leased to the anchor it replaced.
PUBLISHED = (world.REPLAY, world.ANCHOR)

# What a finished publication said: no notices yet, or one notice and one
# `base_rebased` event naming the replay, filed as the tick's own rebase with
# the round reset.
SAID_NOTHING = (0, [])
SAID_ONCE = (1, [(world.REPLAY, "auto_clean_rebase", 0)])

# A landing this tick sent nothing for, said once as one found already standing.
SAID_FOUND = (1, [(world.REPLAY, "crash_recovery_relabel_only", 0)])
FOUND_NOTICE = "was already published"

# How far behind its base the checkout reads, before a rebase and once one has landed.
BEHIND = "2\n"
LEVEL = "0\n"

# The reset a rollback puts the checkout back onto its anchor with.
RESET_ONTO_THE_ANCHOR = ("reset", "--hard", world.ANCHOR)

# What moves after the gate measured the candidate and before the git owner
# reads it again for its push, and where PR #42 is left standing.
MOVES = (
    ("work landing on the checkout", moves.lands_on_the_checkout, world.ANCHOR),
    ("a base ref repointed", moves.REWOUND, world.ANCHOR),
    ("somebody's push to the branch", moves.PUSHED_OVER, world.FOREIGN),
    ("a remote that stops answering", moves.silences_the_remote, world.ANCHOR),
)

# A candidate prepared over a remote that already read as standing on the
# replay, and somebody's push overtaking that reading: before the git owner
# reads the remote again, or after it and before the proof. Each with the
# readings that showed the replay, and the pushes the tick made: none, or the
# proof -- the replay leased to itself.
SHOWN_ONCE = (world.REPLAY,)
SHOWN_TWICE = (world.REPLAY, world.REPLAY)
PROOF = (world.REPLAY, world.REPLAY)
STALE_LANDINGS = (
    ("before the reread", world.races_the_reread, SHOWN_ONCE, []),
    ("before the proof", world.races_the_barrier, SHOWN_TWICE, [PROOF]),
)

# What a remote already on the replay does not excuse: every other reading the
# push would have been refused on, failing as the git owner reads it again.
UNEXCUSED = (
    ("a base that can no longer be counted", moves.BASE_UNREADABLE),
    ("a base ref repointed", moves.REWOUND),
    ("work landing on the checkout", moves.lands_on_the_checkout),
)

# The publication ending while the git owner reads the candidate again.
ENDINGS = (
    ("a close a poll latched", moves.latches_a_close),
    ("the pull request merged", moves.merges_the_pull_request),
    ("the pull request closed", moves.closes_the_pull_request),
)

# A reading the git owner refuses the push on, and each ending beside each one.
REFUSED_READS = (
    ("a remote that stops answering", moves.silences_the_remote),
    ("work landing on the checkout", moves.lands_on_the_checkout),
)
ENDED_AND_REFUSED = tuple(
    (ending, ends, refused, refuses)
    for ending, ends in ENDINGS
    for refused, refuses in REFUSED_READS
)


def _head(github) -> str:
    """The head PR #42 stands on."""
    pull = github.pulls[base.PR_NUMBER]
    return pull.head.sha


def _attempt(github) -> dict:
    """Issue #7's attempt record, member by member."""
    durable = github.pinned_data(ISSUE)
    return {key: durable.get(key) for key in ATTEMPT_KEYS}


def _parked(github) -> tuple:
    """Whether issue #7 waits on a human, and why."""
    durable = github.pinned_data(ISSUE)
    return durable.get(KEY_AWAITING_HUMAN), durable.get(KEY_PARK_REASON)


def _said(github) -> tuple[int, list[tuple]]:
    """How many notices PR #42 was given, and each `base_rebased` event as its head, method, and round."""
    notices = [body for number, body in github.posted_pr_comments if number == base.PR_NUMBER]
    events = [
        (event["sha"], event["method"], event["review_round"])
        for event in github.recorded_events if event.get("event") == "base_rebased"
    ]
    return len(notices), events


class _PublicationCase(ObservedCloseCase, base._SyncWorktreeWithBaseFixture, unittest.TestCase):
    """Issue #7 in review over PR #42 on its anchor, with a spent round, two commits behind its base."""

    def setUp(self) -> None:
        super().setUp()
        self._fresh()

    def _fresh(self) -> None:
        """Seed the issue afresh, over a world where nothing has moved and no close was seen."""
        self._fresh_process()
        self.gh = base.FakeGitHubClient()
        self._seed_pr_issue(review_round=3)
        self.world = world.RewriteWorld(self)
        self.hardened = MagicMock(return_value=base._git_result())

    def _ticks(self, behind: str = BEHIND) -> None:
        """Run one refresh of issue #7's checkout, reading `behind` as its lag against base."""
        with _patch_base_sync(
            dirty=MagicMock(return_value=[]),
            rebase=MagicMock(return_value=(True, [])),
            push=self.world.push,
            head_sha=MagicMock(return_value=world.ANCHOR),
            git=MagicMock(return_value=base._git_result(stdout=behind)),
            hardened=self.hardened,
        ):
            _base_refresh._sync_worktree_with_base(self.gh, self.spec, self.wt, ISSUE)

    def _assert_finished(self, said: tuple = SAID_ONCE) -> None:
        """PR #42 on the replay, routed to review once, its attempt retired and its debt owed, and `said` once."""
        self.assertEqual(_head(self.gh), world.REPLAY)
        self.assertEqual(self.gh.label_history, [(ISSUE, LABEL_VALIDATING)])
        self.assertEqual(_attempt(self.gh), RETIRED)
        durable = self.gh.pinned_data(ISSUE)
        self.assertEqual(durable.get(KEY_REVIEW_ROUND), 0)
        self.assertEqual(durable.get(KEY_REWRITE_DEBT), owed(world.ANCHOR, world.REPLAY))
        self.assertEqual(_said(self.gh), said)

    def _assert_held(self) -> None:
        """Nothing pushed, said, routed, reset, or parked, and the attempt left standing for the cleanup it is owed."""
        self.assertEqual(self.world.pushes, [])
        self.assertEqual(_head(self.gh), world.ANCHOR)
        self.assertEqual(self.gh.label_history, [])
        self.assertEqual(_said(self.gh), SAID_NOTHING)
        attempt = _attempt(self.gh)
        self.assertEqual(attempt[KEY_PENDING_PUSH], world.ANCHOR)
        self.assertEqual(attempt[KEY_REWRITE_SHA], world.REPLAY)
        self.assertFalse(_parked(self.gh)[0])
        resets = [recorded.args[:3] for recorded in self.hardened.call_args_list]
        self.assertNotIn(RESET_ONTO_THE_ANCHOR, resets)

    def _assert_rolled_back(self, left_on: str) -> None:
        """PR #42 left on `left_on`, nothing said, the checkout back on its anchor, the attempt retired, parked."""
        self.assertEqual(_head(self.gh), left_on)
        resets = [recorded.args[:3] for recorded in self.hardened.call_args_list]
        self.assertIn(RESET_ONTO_THE_ANCHOR, resets)
        self.assertEqual(self.gh.label_history, [])
        self.assertEqual(_parked(self.gh), (True, PARK_PUSH_FAILED))
        self.assertEqual(_attempt(self.gh), RETIRED)
        self.assertEqual(_said(self.gh), SAID_NOTHING)


class PublishedRebaseTest(_PublicationCase):
    """A candidate the gate let through, published by the git owner and finished once."""

    def test_a_clean_rebase_is_finished_once(self) -> None:
        self._ticks()
        self._ticks(LEVEL)

        self.assertEqual(self.world.pushes, [PUBLISHED])
        self._assert_finished()

    def test_a_lost_answer_is_not_pushed_again(self) -> None:
        # The push reached the remote and git answered a failure: read again,
        # the remote stands on the replay, so the landing is finished as the
        # publication it was rather than rolled back off a branch that carries it.
        self.world.answered = False

        self._ticks()
        self._ticks(LEVEL)

        self.assertEqual(self.world.pushes, [PUBLISHED])
        self._assert_finished()

    def test_a_proved_landing_is_announced_as_found(self) -> None:
        # The remote already carries the replay while GitHub still names the
        # anchor, and catches up before the proof. Nothing is sent: the landing
        # is proved by the replay leased to itself and announced as one found
        # standing -- the proof's answer lost or not, since it had nothing to
        # send either way.
        for answered in (True, False):
            with self.subTest(answered=answered):
                self._fresh()
                self.world.reads_first(world.REPLAY, world.REPLAY)
                self.world.answered = answered

                with world.races_the_barrier(self, moves.CAUGHT_UP):
                    self._ticks()

                self.assertEqual(self.world.pushes, [PROOF])
                self._assert_finished(SAID_FOUND)
                self.assertIn(FOUND_NOTICE, self.gh.posted_pr_comments[-1][1])

    def test_a_rejected_lease_waits_for_a_reply(self) -> None:
        self.world.rejects = True
        self._ticks()

        self.assertEqual(self.world.pushes, [PUBLISHED])
        self._assert_rolled_back(world.ANCHOR)

        self.world.rejects = False
        reply = self.gh.next_reply_id(self.gh._issues[ISSUE])
        self._add_comment(reply, "branch reconciled, please retry", base.HUMAN_LOGIN)
        self._ticks()

        self.assertEqual(self.world.pushes, [PUBLISHED, PUBLISHED])
        self._assert_finished()
        self.assertEqual(_parked(self.gh), (False, None))
        self.assertEqual(self.gh.pinned_data(ISSUE).get(KEY_WATERMARK), reply)


class RefusedBeforeThePushTest(_PublicationCase):
    """A candidate the git owner will not publish, and a gate that will not let one through."""

    def test_what_moved_since_the_gate_is_refused(self) -> None:
        # Nothing is sent over a checkout, a base, or a remote that moved after
        # the measurement, nor over a remote nobody can read: the checkout goes
        # back onto its anchor and the issue parks for a human.
        for moved, move, left_on in MOVES:
            with self.subTest(moved):
                self._fresh()

                with world.races_the_reread(self, move):
                    self._ticks()

                self.assertEqual(self.world.pushes, [])
                self._assert_rolled_back(left_on)

    def test_a_stale_landing_is_not_finished(self) -> None:
        # The candidate was prepared over a remote already on the replay, and
        # somebody pushed over it since: the reading it was prepared with is
        # read again, and a remote still showing the replay is proved at the
        # remote before anything is finished, so their push is kept and
        # nothing is recorded, announced, or routed for the replay.
        for overtaken, races, readings, pushes in STALE_LANDINGS:
            with self.subTest(overtaken):
                self._fresh()
                self.world.reads_first(*readings)

                with races(self, moves.PUSHED_OVER):
                    self._ticks()

                self.assertEqual(self.world.pushes, pushes)
                self._assert_rolled_back(world.FOREIGN)
                self.assertIsNone(self.gh.pinned_data(ISSUE).get(KEY_REWRITE_DEBT))

    def test_a_landing_excuses_no_other_reading(self) -> None:
        # The remote already reads as standing on the replay, and the base or
        # the checkout fails as the git owner reads them again. That claim of
        # a landing outranks none of them, so the candidate is refused as any
        # other would be: nothing is proved, recorded, announced, or routed.
        for failed, fails in UNEXCUSED:
            with self.subTest(failed):
                self._fresh()
                self.world.reads_first(world.REPLAY, world.REPLAY)

                with world.races_the_reread(self, fails):
                    self._ticks()

                self.assertEqual(self.world.pushes, [])
                self._assert_rolled_back(world.ANCHOR)
                self.assertIsNone(self.gh.pinned_data(ISSUE).get(KEY_REWRITE_DEBT))

    def test_an_ending_during_the_reread_holds(self) -> None:
        # The barrier is asked after the git owner's own reading, immediately
        # before the push, so an ending that lands while the remote is read is
        # still answered: nothing pushed, reset, parked, said, or routed, and
        # the attempt left standing for the cleanup it is owed.
        for ending, ends in ENDINGS:
            with self.subTest(ending):
                self._fresh()

                with world.races_the_reread(self, ends):
                    self._ticks()

                self._assert_held()

    def test_an_ending_beside_a_refused_read_holds(self) -> None:
        # The barrier is asked whatever the git owner's reading answered, so a
        # publication that ended while that reading refused the push is held
        # for its cleanup rather than rolled back and parked as a push that
        # failed.
        for ending, ends, refused, refuses in ENDED_AND_REFUSED:
            with self.subTest(ending=ending, refused=refused):
                self._fresh()

                with world.races_the_reread(self, ends), world.races_the_reread(self, refuses):
                    self._ticks()

                self._assert_held()

    def test_the_rebase_spends_only_a_retry(self) -> None:
        # The reply that let the rebase start is the operator's retry where it
        # says nothing else, and the anchor's own write records it read on the
        # requirements baseline as well as the watermark -- so the adjudication
        # the gate hands the replay to, on this tick or after a crash, never
        # reads it as guidance. A reply that says more is a human's words: the
        # watermark moves past it as it always has, and the baseline stays
        # short of it for the adjudication to hand it to the developer.
        for body, spent in holds.REPLIES:
            with self.subTest(body):
                self._fresh()
                self.world.rejects = True
                self._ticks()
                holds.covers_the_thread(self.gh)
                self.world.rejects = False
                reply = holds.replies(self, body)
                before = holds.read_through(self.gh)[1]

                with holds.oversized():
                    self._ticks()

                read = holds.baseline_through(self.gh, reply) if spent else before
                self.assertEqual(holds.left_with(self.gh), (None, None, world.REPLAY))
                self.assertEqual(holds.read_through(self.gh), (reply, read))

    def test_only_an_adjudication_takes_the_attempt(self) -> None:
        # Past the ceiling, the gate hands the issue to an adjudication with
        # the replay standing, and nothing is pushed, announced, or routed to
        # review -- and the attempt goes to the live generation in the same
        # tick, so no anchor is left to hold that adjudication behind. A count
        # nobody can pin parks instead and leaves no adjudication to take the
        # replay over, so the attempt stays pinned for the recovery the park's
        # reply brings back.
        for count, relabelled, left, parked in holds.HOLDS:
            with self.subTest(count.__name__):
                self._fresh()

                with count():
                    self._ticks()

                self.assertEqual(self.world.pushes, [])
                self.assertEqual(_head(self.gh), world.ANCHOR)
                self.assertEqual(self.gh.label_history, list(relabelled))
                self.assertEqual(holds.left_with(self.gh), left)
                self.assertEqual(_parked(self.gh), parked)
                self.assertEqual(_said(self.gh), SAID_NOTHING)


if __name__ == "__main__":
    unittest.main()
