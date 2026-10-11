# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A newer transaction another road recorded beside a captured run stands as that road wrote it, and nothing announces.

A finish recorded its run for the landed head and died posting its artifact,
so the recovery publishes and settles it with the attempt still standing.
While the settlement's own write is answered -- GitHub has taken it, and its
answer is on the way back -- another road records a newer transaction for the
head beside it. The announcement is decided on the evidence records too, so it
reads that transaction and refuses: no notice, no `base_rebased` event, no
round reset, and the attempt stands with the newer transaction owed, however
often the recovery polls before it is answered. The next recovery settles that
transaction over the run, which goes into history as superseded, then
announces once and routes the head -- one artifact for each, nothing run
again, nothing pushed, and no developer launched.

A successor recorded over the run before any recovery, about the anchor
rather than the head, abandons the run into history and leaves no current
evidence at all. No finish of this landing can answer it, so the recovery
holds the route over it poll after poll -- and so it does where the base
advanced past the head again, whose continuation would otherwise be
announced and rebased: the successor and the revision floor it raised are
kept, the attempt stands, and nothing is announced, relabelled, reset,
posted, run, or pushed.

A newer head another road published on the pull request -- a fresh report
settled for it and a transaction recorded for it -- while the checkout still
holds the replay is no landing of this attempt's, and its transaction is not
the one whose receipt the finish put on the attempt, if it recorded any. The
recovery abandons nothing over it and parks the remote it reads
off the replay -- as the rollback it looks like where the run was captured,
which that transaction abandoned, and as a branch updated out of band where
the finish died before running anything -- resetting the checkout and
releasing the attempt with nothing pushed over it, and leaving that
transaction, its transcript, and its revision floor exactly as its road wrote
them, poll after poll -- whether or not the attempt's record names its
replay yet, which says nothing of whose a pending transaction is.
"""
from __future__ import annotations

import unittest
from dataclasses import replace
from functools import partial
from unittest.mock import patch

from orchestrator.workflow.engine import verification_record_state as _record_state
from tests.workflow.engine import (
    rewrite_finish_git_support as git_support,
    rewrite_finish_readings as readings,
    rewrite_verification_recovery_support as support,
    verification_report_fixture as report,
)
from tests.workflow.interleaving import _RacesPastTheCall


def _records_newer(case: support.CapturedRunCase, binding, commands):
    """Record a newer transaction under `binding` on the comment as it stands, as another road would; that record."""
    state = case.gh.read_pinned_state(case.issue)
    newer = _record_state.mint_pending_evidence(state, git_support.ISSUE, binding, commands)
    case.assertTrue(_record_state.record_pending_evidence(state, newer))
    case.gh.write_pinned_state(case.issue, state)
    return newer


def _records_behind_the_settlement(case: support.CapturedRunCase, captured) -> None:
    """Have a newer transaction recorded right after the settlement's write lands, before its answer comes back.

    The settlement's commit is the first guarded edit behind the artifact's
    post, so the edit the post arms is that commit's.
    """
    records = partial(_records_newer, case, captured.binding, captured.commands)
    behind = _RacesPastTheCall(case.gh.edit_pinned_state, 1, records)
    arms = partial(case.enterContext, patch.object(case.gh, "edit_pinned_state", behind))
    posts = _RacesPastTheCall(case.gh.publish_verification_artifact, 1, arms)
    case.enterContext(patch.object(case.gh, support.POST, posts))


def _publishes_a_newer_head(case: support.CapturedRunCase, replay: str, recorded):
    """Have another road publish a head past `replay`, settle a report for it, and record a transaction for it.

    That transaction, carrying `recorded`'s transcript and configuration
    bound to the newer head, its tree, and the review subject settled for it.
    The checkout is put back on `replay`, the head the attempt's record names.
    """
    case._git(*support.STRAY_COMMIT, cwd=case._wt)
    newer = case._wt_head()
    case._git("push", "--quiet", "origin", git_support.BRANCH, cwd=case._wt)
    case.pull_request.head.sha = newer
    case.state = case.gh.read_pinned_state(case.issue)
    report.settles_report(case, 3, report.LATER_REPORT_TEXT, head=newer)
    case.gh.write_pinned_state(case.issue, case.state)
    target = recorded.binding.retargeted(newer).target
    target = replace(target, subject=readings.pinned(case)["review_subject"])
    binding = replace(
        recorded.binding, target=target, tested_sha=newer, tested_tree=git_support.tree(case, newer),
    )
    case._git("reset", "--quiet", "--hard", replay, cwd=case._wt)
    return _records_newer(case, binding, recorded.commands)


def _uncaptured_beneath_a_newer_head(case: support.CapturedRunCase, *, unnamed: bool):
    """Land a reviewed rebase whose finish dies before running anything, then have another road publish past it.

    No evidence record names the replay and the attempt carries no receipt;
    the newer head's transaction is what the comment carries, and the
    attempt's record of its replay is blanked where `unnamed` says, as the
    window before git's result is recorded leaves it. That transaction.
    """
    head = case.lands_a_reviewed_rebase()
    case.dies_verifying(head, completed=False)
    case.assertEqual(readings.pinned_records(case)[0], None)
    newer = _publishes_a_newer_head(case, head, case.source)
    if unnamed:
        state = case.gh.read_pinned_state(case.issue)
        state.set(readings.KEY_REWRITE_SHA, None)
        case.gh.write_pinned_state(case.issue, state)
    return newer


# Whether the attempt's record names its replay, which says nothing of whose a
# pending transaction is.
_REPLAY_RECORDS = (("named", False), ("not yet named", True))


# Where the landing a successor about the anchor holds stands: routed, or with
# the base advanced past it again, which the recovery would continue.
_LANDINGS = (("routed", None), ("the base advanced again", support.advances_the_base_again))


class AnnouncementGuardTest(support.CapturedRunCase, unittest.TestCase):
    """The announcement is refused over a transaction recorded beside the settled run, and the attempt kept."""

    def test_a_newer_record_holds_the_route(self) -> None:
        # The run settles and a newer transaction lands beside it before the
        # settlement's answer is back: nothing is announced, reset, or
        # cleared, poll after poll. Answered by the next recovery, the newer
        # transaction is settled over the run, and the head announced once
        # and routed.
        head, captured = self.captures()
        _records_behind_the_settlement(self, captured)

        self.recovers()

        newer = self._assert_held_beside(captured)
        self.recovers()
        self.recovers()
        self._assert_settled_over(captured, newer)
        self.assert_recovered(head)

    def test_a_successor_off_the_landing_holds(self) -> None:
        # A successor about the anchor replaces the run before any recovery,
        # abandoning it with nothing current: the route -- or the
        # continuation, where the base advanced again -- is held poll after
        # poll, the successor and its revision floor kept, nothing announced.
        for landing, moves in _LANDINGS:
            with self.subTest(landing=landing):
                self.setUp()
                captured = self.captures()[1]
                successor = _records_newer(self, self.source.binding, captured.commands)
                if moves is not None:
                    moves(self)

                self.recovers()
                self.recovers()

                self.assert_held(successor)
                self.assert_unannounced()
                self._assert_kept(captured, successor)

    def test_a_newer_head_keeps_its_record(self) -> None:
        # Another road published a newer head and recorded its evidence while
        # the checkout still holds the replay: that transaction is not this
        # attempt's, so the recovery abandons nothing, parks the remote it
        # reads off the replay, and the transaction stands with its floor.
        head, captured = self.captures()
        successor = _publishes_a_newer_head(self, head, captured)

        self.recovers()
        self.recovers()

        self.assertEqual(readings.pinned_records(self)[0], successor)
        self._assert_kept(captured, successor)
        self.assertIn("rolled back or moved out of band", self.gh.posted_comments[-1][1])
        self.assertEqual(self._wt_head(), self.anchor)
        self.assertEqual(support.announced(self), [])
        self.assertIsNone(readings.pinned(self)[readings.KEY_PENDING_PUSH])

    def _assert_held_beside(self, captured):
        """`captured` current with a newer transaction owed beside it, the attempt standing, nothing announced; it."""
        newer, current = readings.pinned_records(self)[:2]
        self.assertEqual(newer.revision, captured.revision + 1)
        self.assertEqual(current.receipt, captured.receipt)
        self.assertEqual(readings.pinned(self)[readings.KEY_PENDING_PUSH], self.anchor)
        self.assert_unannounced()
        return newer

    def _assert_kept(self, captured, successor) -> None:
        """`captured` abandoned beside `successor`, the floor it raised kept, nothing posted, run, or pushed."""
        retired = readings.pinned_records(self)[2][-1]
        self.assertEqual(retired, (captured.receipt, readings.ABANDONED))
        self.assertEqual(successor.revision, captured.revision + 1)
        self.assertEqual(readings.pinned(self)[readings.KEY_REVISION_FLOOR], successor.revision)
        self.assertEqual(self.posted(successor), [])
        unmade = (self.runs(), self.pushes.call_count, self.developer.call_count)
        self.assertEqual(unmade, (1, 0, 0))

    def _assert_settled_over(self, captured, newer) -> None:
        """`newer` current over `captured`, superseded into history, each posted once."""
        pending, current, retired = readings.pinned_records(self)
        self.assertEqual((pending, current.receipt), (None, newer.receipt))
        self.assertEqual(retired[-1], (captured.receipt, "superseded"))
        self.assertEqual(self.posted(captured), [captured.commands])
        self.assertEqual(self.posted(newer), [newer.commands])


class UncapturedReplayTest(support.CapturedRunCase, unittest.TestCase):
    """A newer head's transaction beside a replay whose finish captured nothing is never abandoned by its recovery."""

    def test_a_newer_heads_record_stands(self) -> None:
        # The finish died before running anything, so it put no receipt on
        # the attempt, and another road then published a newer head and
        # recorded its evidence: no finish of this attempt's recorded that
        # transaction, whether or not the attempt's record names its replay
        # yet. The recovery parks the branch updated out of band, releasing
        # the attempt over the checkout's reset, and abandons nothing, poll
        # after poll.
        for replay, unnamed in _REPLAY_RECORDS:
            with self.subTest(replay=replay):
                self.setUp()
                newer = _uncaptured_beneath_a_newer_head(self, unnamed=unnamed)

                self.recovers()
                parked = len(self.gh.posted_comments)
                self.recovers()

                pinned = readings.pinned(self)
                self.assertEqual(pinned.get("park_reason"), "auto_base_rebase_push_failed")
                self.assertEqual(len(self.gh.posted_comments), parked)
                self.assertIsNone(pinned[readings.KEY_PENDING_PUSH])
                self.assertEqual(self._wt_head(), self.anchor)
                self._assert_untouched(newer)

    def _assert_untouched(self, newer) -> None:
        """`newer` pending exactly as its road wrote it, its floor kept, nothing posted, run, pushed, or announced."""
        self.assertEqual(readings.pinned_records(self)[0], newer)
        self.assertEqual(readings.pinned(self)[readings.KEY_REVISION_FLOOR], newer.revision)
        self.assertEqual(self.posted(newer), [])
        unmade = (self.runs(), self.pushes.call_count, self.developer.call_count)
        self.assertEqual(unmade, (0, 0, 0))
        self.assertEqual(support.announced(self), [])

if __name__ == "__main__":
    unittest.main()
