# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Issue #7's interrupted rebase, its replay left in the checkout and PR #42 still on the anchor.

The world the ordinary publication cases move (`rewrite_publication_test_support`)
-- the head the checkout proves to, the base the replay sits over, PR #42's
branch as the remote has it, and a push that lands only under the head the
pull request stands on -- with a tick that died between its rebase and its
push left on it: the anchor pinned, the replay recorded, the checkout standing
on it. The recovery reads the remote through the fetch it verifies against, so
that reading follows PR #42 too (`RecoveryGit`), and every hardened command a
rollback runs is recorded beside it.
"""
from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from orchestrator.workflow.engine import base_refresh as _base_refresh
from tests.git.base_sync import refresh_test_support as base
from tests.git.base_sync.report_debt_test_support import owed
from tests.git.base_sync.sync_test_support import _patch_base_sync
from tests.workflow.engine import rewrite_publication_test_support as world
from tests.workflow.observation_support import ObservedCloseCase

ISSUE = base.ISSUE
ANCHOR = world.ANCHOR
REPLAY = world.REPLAY

LABEL_VALIDATING = "workflow:validating"
LABEL_DECOMPOSING = "workflow:decomposing"

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
PARK_DIRTY = "auto_base_rebase_dirty"

# The one push a retry makes: the replay, leased to the anchor the attempt pinned.
RETRIED = (REPLAY, ANCHOR)

# What a recovery said: nothing, or one notice and one `base_rebased` event
# naming the replay, filed as a push the recovery made with the round reset.
SAID_NOTHING = (0, [])
SAID_ONCE = (1, [(REPLAY, "crash_recovery_pushed", 0)])
PUSHED_NOTICE = "pushed the recovered head"

# How far behind its base the checkout reads.
LEVEL = "0\n"

# The reset a rollback puts the checkout back onto its anchor with, and the
# clean a dirty one runs after it.
RESET_ONTO_THE_ANCHOR = ("reset", "--hard", ANCHOR)
CLEAN = ("clean", "-fd")

GIT_FAILURE_EXIT_CODE = 128

_REMOTE_READ = ("rev-parse",)
_REMOTE_REFS = "refs/remotes/"
_RESET = ("reset",)


def head(github) -> str:
    """The head PR #42 stands on."""
    return github.pulls[base.PR_NUMBER].head.sha


def attempt(github) -> dict:
    """Issue #7's attempt record, member by member."""
    durable = github.pinned_data(ISSUE)
    return {key: durable.get(key) for key in ATTEMPT_KEYS}


def parked(github) -> tuple:
    """Whether issue #7 waits on a human, and why."""
    durable = github.pinned_data(ISSUE)
    return durable.get(KEY_AWAITING_HUMAN), durable.get(KEY_PARK_REASON)


def watermark(github) -> int | None:
    """The comment issue #7 last acted on."""
    return github.pinned_data(ISSUE).get(KEY_WATERMARK)


def said(github) -> tuple[int, list[tuple]]:
    """How many notices PR #42 was given, and each `base_rebased` event as its head, method, and round."""
    notices = [body for number, body in github.posted_pr_comments if number == base.PR_NUMBER]
    events = [
        (event["sha"], event["method"], event["review_round"])
        for event in github.recorded_events if event.get("event") == "base_rebased"
    ]
    return len(notices), events


class RecoveryGit:
    """Hardened git as the recovery and a rollback run it: the fetched branch where PR #42 stands.

    `rev-parse` of a remote-tracking ref answers the head PR #42 is on, which
    is what the recovery's own fetch would have brought down. Every other
    command succeeds, save a reset `refuses_reset` makes fail, and each is
    recorded as its arguments.
    """

    def __init__(self, case) -> None:
        self.refuses_reset = False
        self.calls: list[tuple] = []
        self._case = case

    def __call__(self, *args, **_options):
        self.calls.append(args)
        if args[:1] == _REMOTE_READ:
            return base._git_result(stdout=self._remote_head(args))
        refused = self.refuses_reset and args[:1] == _RESET
        return base._git_result(returncode=GIT_FAILURE_EXIT_CODE if refused else 0)

    def ran(self, command: tuple) -> bool:
        """Whether a command beginning with `command` was run."""
        width = len(command)
        return any(called[:width] == command for called in self.calls)

    def _remote_head(self, args: tuple) -> str:
        """What `rev-parse` answers: PR #42's head for a remote-tracking ref, nothing for any other."""
        if not str(args[1]).startswith(_REMOTE_REFS):
            return ""
        return f"{head(self._case.gh)}\n"


class RetryCase(ObservedCloseCase, base._SyncWorktreeWithBaseFixture, unittest.TestCase):
    """Issue #7 in review over PR #42 on the anchor, a spent round, and the replay its dead tick left."""

    def setUp(self) -> None:
        super().setUp()
        self._fresh()

    def _fresh(self, **state) -> None:
        """Seed the interrupted attempt afresh, over a world where nothing has moved; `state` overrides any field."""
        self._fresh_process()
        self.gh = base.FakeGitHubClient()
        self._seed_pr_issue(**{"review_round": 3, **base._pending_attempt(REPLAY), **state})
        self.world = world.RewriteWorld(self)
        self.git = RecoveryGit(self)

    def _ticks(self, standing: str = REPLAY) -> None:
        """Run one refresh of issue #7's checkout, standing on `standing` and level with its base."""
        with _patch_base_sync(
            dirty=MagicMock(return_value=[]),
            rebase=MagicMock(return_value=(True, [])),
            push=self.world.push,
            head_sha=MagicMock(return_value=standing),
            fetch=MagicMock(return_value=base._git_result()),
            git=MagicMock(return_value=base._git_result(stdout=LEVEL)),
            hardened=self.git,
        ):
            _base_refresh._sync_worktree_with_base(self.gh, self.spec, self.wt, ISSUE)

    def _replies(self) -> int:
        """A trusted human's reply on issue #7's thread; its id."""
        reply = self.gh.next_reply_id(self.gh._issues[ISSUE])
        self._add_comment(reply, "branch reconciled, please retry", base.HUMAN_LOGIN)
        return reply

    def _assert_finished(self) -> None:
        """PR #42 on the replay, routed to review once, its attempt retired and its debt owed, said once."""
        self.assertEqual(head(self.gh), REPLAY)
        self.assertEqual(self.gh.label_history, [(ISSUE, LABEL_VALIDATING)])
        self.assertEqual(attempt(self.gh), RETIRED)
        durable = self.gh.pinned_data(ISSUE)
        self.assertEqual(durable.get(KEY_REVIEW_ROUND), 0)
        self.assertEqual(durable.get(KEY_REWRITE_DEBT), owed(ANCHOR, REPLAY))
        self.assertEqual(said(self.gh), SAID_ONCE)
        self.assertIn(PUSHED_NOTICE, self.gh.posted_pr_comments[-1][1])

    def _assert_rolled_back(self, left_on: str, reason: str = PARK_PUSH_FAILED) -> None:
        """PR #42 left on `left_on`, nothing said or routed, the checkout reset onto its anchor, the attempt retired."""
        self.assertEqual(head(self.gh), left_on)
        self.assertTrue(self.git.ran(RESET_ONTO_THE_ANCHOR))
        self.assertEqual(self.gh.label_history, [])
        self.assertEqual(parked(self.gh), (True, reason))
        self.assertEqual(attempt(self.gh), RETIRED)
        self.assertEqual(said(self.gh), SAID_NOTHING)
