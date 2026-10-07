# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Issue #7's interrupted rebase whose push already landed: PR #42 on the replay its dead tick pushed.

The world the retry cases recover over (`rewrite_retry_test_support`) one step
further on: the push the dead tick made reached the remote, so PR #42 and the
checkout both stand on the replay the attempt recorded, whether or not anybody
heard back. The recovery's fetch and the observation behind it both read the
branch where PR #42 stands, and a case may move it between the two
(`RewriteWorld.reads_first`).

A case may also lose a tick of its own at one of the three moments a finish
leaves behind its notice and its event (`WINDOWS`): before the mark that
records them, at the relabel the mark is written ahead of, and at the write
that retires the attempt behind that relabel.
"""
from __future__ import annotations

from dataclasses import replace
from unittest.mock import MagicMock, patch

from orchestrator.git.publication import probes as _publication_probes
from orchestrator.workflow.engine import base_refresh as _base_refresh
from tests.git.base_sync import refresh_test_support as base, transfers_test_support as seed
from tests.git.base_sync.report_debt_test_support import owed, stands_on
from tests.git.base_sync.sync_test_support import _patch_base_sync
from tests.workflow.engine import rewrite_retry_test_support as retry

ISSUE = retry.ISSUE
ANCHOR = retry.ANCHOR
REPLAY = retry.REPLAY

# The head a rebase of the landed replay leaves, once the base has moved again.
NEXT = base.NEW_REBASED_SHA

KEY_ANNOUNCED = "pending_auto_base_rebase_announced_sha"
KEY_REWRITE_PR = "pending_auto_base_rebase_rewrite_pr"

# What a finish of a landing this tick sent nothing for says: one notice, and
# one `base_rebased` event naming the replay, filed as found already published.
FOUND = (REPLAY, "crash_recovery_relabel_only", 0)
SAID_FOUND = (1, [FOUND])
FOUND_NOTICE = "was already published"

# The same, followed by the publication of the rebase the tick goes on with
# past a base that moved again: the one push that tick makes, of the head the
# rebase leaves, leased to the replay PR #42 already stands on.
SAID_FOUND_THEN_REBASED = (2, [FOUND, (NEXT, "auto_clean_rebase", 0)])
REBASED_ON = (NEXT, REPLAY)
ADVANCED_NOTICE = "Base advanced again by 2 commit(s)"

# How far behind its base the landed replay counts once the base has moved again.
LAG = 2

DIED = "the process died before the tick returned"


class _FallenBehind:
    """The divergence probe, counting one head some commits behind the base and taking every other reading as before."""

    def __init__(self, probe, head: str, commits: int) -> None:
        self._probe = probe
        self._head = head
        self._commits = commits

    def __call__(self, spec, worktree, branch, *revision):
        counted = self._probe(spec, worktree, branch, *revision)
        if branch == spec.base_branch and revision[:1] == (self._head,):
            return replace(counted, behind=self._commits)
        return counted


class _LosesTheRetirement:
    """A guarded pinned edit that takes every write but the one retiring the attempt."""

    def __init__(self, edit) -> None:
        self._edit = edit

    def __call__(self, issue, state, *, over):
        """Lose the write that blanks the anchor, and send every other."""
        if state.get(retry.KEY_PENDING_PUSH) is None:
            raise RuntimeError(DIED)
        return self._edit(issue, state, over=over)


def _before_the_mark(case):
    """Lose the tick at the first guarded edit past the notice and the event: the mark."""
    return patch.object(case.gh, "edit_pinned_state", MagicMock(side_effect=RuntimeError(DIED)))


def _at_the_relabel(case):
    """Lose the tick at the relabel, with the mark already down."""
    return patch.object(case.gh, "set_workflow_label", MagicMock(side_effect=RuntimeError(DIED)))


def _after_the_relabel(case):
    """Lose the tick at the write that retires the attempt, with the relabel already made."""
    return patch.object(case.gh, "edit_pinned_state", _LosesTheRetirement(case.gh.edit_pinned_state))


# Each moment a finish can be lost at, with the mark the lost tick left and
# what the landing ends up announced as: a mark that never went down cannot
# say the notice and the event are out, so they are said once more.
WINDOWS = (
    ("before the mark", _before_the_mark, None, (2, [FOUND, FOUND])),
    ("at the relabel", _at_the_relabel, REPLAY, SAID_FOUND),
    ("after the relabel", _after_the_relabel, REPLAY, SAID_FOUND),
)


class LandedCase(retry.RetryCase):
    """Issue #7 in review over PR #42, which already stands on the replay its dead tick pushed."""

    def _fresh(self, **state) -> None:
        """Seed the interrupted attempt afresh, its push already on PR #42."""
        super()._fresh(**state)
        stands_on(self.gh, REPLAY)

    def _ticks(self, standing: str = REPLAY, *, lag: int = 0) -> None:
        """Run one refresh of issue #7's checkout, standing on `standing` `lag` commits behind its base.

        The lag is the checkout's from then on, every other reading taken as
        before. A rebase the refresh goes on with past the recovery replays
        the checkout onto `NEXT`, level with the base.
        """
        if lag:
            counted = _FallenBehind(_publication_probes._branch_divergence, standing, lag)
            base._patched(self, _publication_probes, "_branch_divergence", counted)
        with _patch_base_sync(
            dirty=MagicMock(return_value=[]),
            rebase=MagicMock(side_effect=self._replays),
            push=self.world.push,
            head_sha=MagicMock(return_value=standing),
            fetch=MagicMock(return_value=base._git_result()),
            git=MagicMock(return_value=base._git_result(stdout=f"{lag}\n")),
            hardened=self.git,
        ):
            _base_refresh._sync_worktree_with_base(self.gh, self.spec, self.wt, ISSUE)

    def _carries(self, *records) -> None:
        """Put each of `records` on issue #7's pinned comment, as the producer that writes it would."""
        state = self.gh.read_pinned_state(self.gh._issues[ISSUE])
        for record in records:
            record(state)
        self.gh.write_pinned_state(self.gh._issues[ISSUE], state)

    def _replays(self, *_args) -> tuple[bool, list]:
        """A clean rebase of the checkout onto the advanced base."""
        self.world.head = NEXT
        return True, []

    def _assert_finished(self, said: tuple = SAID_FOUND) -> None:
        """PR #42 on the replay with nothing pushed, routed to review once, its attempt retired and its debt owed."""
        self.assertEqual(self.world.pushes, [])
        self.assertEqual(retry.head(self.gh), REPLAY)
        self.assertEqual(self.gh.label_history, [(ISSUE, retry.LABEL_VALIDATING)])
        self.assertEqual(retry.attempt(self.gh), retry.RETIRED)
        durable = self.gh.pinned_data(ISSUE)
        self.assertEqual(durable.get(retry.KEY_REVIEW_ROUND), 0)
        self.assertEqual(durable.get(retry.KEY_REWRITE_DEBT), owed(ANCHOR, REPLAY))
        self.assertEqual(retry.said(self.gh), said)

    def _assert_held(self, *, parked: tuple = (None, None), standing: str = REPLAY) -> None:
        """Nothing pushed, said, routed, or reset, the attempt standing over PR #42 on `standing`, parked as `parked`.

        The checkout is never reset: the remote carries the head it stands on.
        """
        self.assertEqual(self.world.pushes, [])
        self.assertEqual(retry.head(self.gh), standing)
        self.assertEqual(self.gh.label_history, [])
        self.assertEqual(retry.said(self.gh), retry.SAID_NOTHING)
        self.assertFalse(self.git.ran(retry.RESET_ONTO_THE_ANCHOR))
        attempt = retry.attempt(self.gh)
        self.assertEqual(attempt[retry.KEY_PENDING_PUSH], ANCHOR)
        self.assertEqual(retry.parked(self.gh), parked)


def a_verdict_settled_onto_the_replay(state) -> None:
    """The adjudication of the anchor, and the transfer of its verdict onto the replay, settled whole."""
    seed.adjudicated(state)
    seed.settled(state)
