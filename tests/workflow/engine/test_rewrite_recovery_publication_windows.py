# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A landed base rewrite's captured run whose publication or settlement did not finish, recovered under its anchor.

The publication's finish records its run of the rebased head and then
publishes and settles it with the attempt still standing. Where that stops
short -- the artifact posted and its answer lost, the process dead behind the
post, a post whose outcome nobody could read, or a settlement whose commit
went out unconfirmed or whose comment would not read -- nothing is relabelled
and the attempt stands, so every later tick's base refresh comes back to it. The recovery
proves the run again, finds an artifact an earlier post landed under its
receipt rather than posting it again, and settles it once: one artifact, one
current record with the transcript, revision, and binding the finish captured,
the history holding only the evidence the rewrite moved past, and a field
another road wrote meanwhile kept. Nothing runs again, nothing is pushed or
announced a second time, and no developer is launched, however often the
recovery polls. While the publication or settlement is unresolved nothing is
announced -- no notice, no `base_rebased` event, no round reset -- relabelled,
or cleared. An artifact a human edited out of its format under the receipt is
the one answer that never settles: the run is abandoned, and the head goes to
the fresh reviewer. Settled evidence an interrupted recovery left is routed as
it stands only while nothing beside it says otherwise: a newer transaction
recorded for the head is settled over it, and a revision spent past it with
nothing left recorded outranks it for good, so it is invalidated and the head
routed to the fresh reviewer.
"""
from __future__ import annotations

import unittest
from functools import partial
from unittest.mock import patch

from orchestrator.github.pull_request_reports import ReportLookup, ReportPresence
from orchestrator.workflow.engine import verification_record_state as _record_state
from orchestrator.workflow.engine.rewrite_finish_models import FinishOutcome
from tests.workflow.engine import (
    rewrite_finish_git_support as git_support,
    rewrite_finish_moves as moves,
    rewrite_finish_readings as readings,
    rewrite_verification_recovery_support as support,
)
from tests.workflow.interleaving import _RacesPastTheCall

# A usage total another road folds onto the pinned comment while the run waits.
_USAGE = "issue_total_tokens"

_FOLDED = 4_096


def _loses_the_answer(case: support.CapturedRunCase, head: str) -> None:
    """Finish `head` with GitHub landing the artifact and losing the answer; the finish holds."""
    with patch.object(case.gh.report_failures, "lost", {git_support.PR_NUMBER}):
        case.assertEqual(case.finishes(head), FinishOutcome.HELD)


def _dies_behind_the_post(case: support.CapturedRunCase, head: str) -> None:
    """Finish `head` with the process dying once the artifact landed, as its settlement re-reads it."""
    case.dies_at("reread_verification_artifact", partial(case.finishes, head))


def _unconfirmed(_pull_request, _artifact) -> ReportLookup:
    """A post whose outcome nobody could read: nothing landed, and nothing says so."""
    return ReportLookup(ReportPresence.UNCONFIRMED)


def _after_the_post(case: support.CapturedRunCase, then) -> None:
    """Have `then` done to `case` once, just after the next artifact post answers."""
    posts_then = _RacesPastTheCall(case.gh.publish_verification_artifact, 1, partial(then, case))
    case.enterContext(patch.object(case.gh, support.POST, posts_then))


def _records_newer(case: support.CapturedRunCase, captured):
    """Record a newer transaction for `captured`'s head beside it, as another road would; that transaction."""
    state = case.gh.read_pinned_state(case.issue)
    newer = _record_state.mint_pending_evidence(state, git_support.ISSUE, captured.binding, captured.commands)
    case.assertTrue(_record_state.record_pending_evidence(state, newer))
    case.gh.write_pinned_state(case.issue, state)
    return newer


def _writes(case: support.CapturedRunCase, key: str, recorded) -> None:
    """Write `recorded` as `key` on `case`'s pinned comment as it stands, as another road would."""
    state = case.gh.read_pinned_state(case.issue)
    state.set(key, recorded)
    case.gh.write_pinned_state(case.issue, state)


# The artifact on the thread and its transaction unsettled, by each road there.
_POSTED_UNSETTLED = (
    ("the post's answer was lost", _loses_the_answer),
    ("the process died behind the post", _dies_behind_the_post),
)

# A settlement that did not land behind its post -- every pinned edit landing
# with its answer lost, the settlement's commit first, or the comment refusing
# every read -- and what lets the next one.
_FAILED_SETTLEMENTS = (
    ("its commit went out unconfirmed", moves.loses_answers, lambda case: case.gh.pinned_failures.lost.clear()),
    ("the comment would not read again", moves.unreadable, lambda case: case.gh.pinned_failures.unreadable.clear()),
)


class PublicationWindowTest(support.CapturedRunCase, unittest.TestCase):
    """A run whose publication or settlement stopped short is settled once by a later recovery."""

    def test_a_posted_artifact_is_settled_once(self) -> None:
        # The artifact landed and the transaction was never settled. Another
        # road folds a usage total onto the comment meanwhile. The recovery
        # finds the artifact under its receipt and settles it, keeping that
        # total and the revision floor, and the poll after it changes nothing.
        for window, leaves_it in _POSTED_UNSETTLED:
            with self.subTest(window=window):
                head, captured = self._leaves_posted(leaves_it)

                self.recovers()
                self.recovers()

                self.assert_settled(captured)
                self.assert_recovered(head)
                pinned = readings.pinned(self)
                self.assertEqual(
                    (pinned[_USAGE], pinned[readings.KEY_REVISION_FLOOR]),
                    (_FOLDED, captured.revision),
                )

    def test_an_unread_post_holds_every_poll(self) -> None:
        # The finish died before its post. While no post's outcome can be
        # read, every poll holds with the run owed and the attempt standing:
        # nothing is posted, relabelled, or run. Once one reads, the run is
        # posted and settled once.
        head, captured = self.captures()
        with patch.object(self.gh, support.POST, _unconfirmed):
            self.recovers()
            self.recovers()

        self.assert_held(captured)
        self.assert_unannounced()
        self.assertEqual(self.posted(captured), [])
        self.recovers()
        self.assert_settled(captured)
        self.assert_recovered(head)

    def test_a_failed_settlement_leaves_the_attempt(self) -> None:
        # The recovery posts the artifact and its settlement does not land:
        # nothing is relabelled and the attempt stands. The poll after it
        # finds the artifact -- or the settlement that did land -- and routes
        # the run settled once, with no second post.
        for failed in _FAILED_SETTLEMENTS:
            with self.subTest(failure=failed[0]):
                self.setUp()
                head, captured = self.captures()
                _after_the_post(self, failed[1])

                self.recovers()

                self.assert_unannounced()
                standing = readings.pinned(self)[readings.KEY_PENDING_PUSH]
                posted = self.posted(captured)
                self.assertEqual((standing, posted), (self.anchor, [captured.commands]))
                failed[2](self)
                self.recovers()
                self.assert_settled(captured)
                self.assert_recovered(head)

    def test_an_edited_artifact_is_abandoned(self) -> None:
        # The artifact landed with its answer lost, and a human edits it out
        # of its format before the recovery reads it back. Nothing makes the
        # run answer under that receipt again, and left owed it would hold the
        # anchor on every poll: it is abandoned rather than settled or posted
        # again, and the head goes on to the fresh reviewer.
        head, captured = self._leaves_posted(_loses_the_answer)
        thread = self.pull_request.issue_comments
        edited = next(posted for posted in thread if captured.receipt in posted.body)
        edited.body = f"{edited.body}\nEdited by hand."

        self.recovers()

        self.assert_abandoned(captured)
        self.assert_recovered(head)
        self.assertEqual(self.posted(captured), [])

    def test_a_newer_record_is_settled_over_it(self) -> None:
        # The recovery settles the run and dies at its relabel, behind its
        # announcement. Another road then records a newer transaction for
        # the same head. The next recovery does not route the settled run
        # past it: it publishes and settles the newer one, which supersedes
        # the run into history, and routes with nothing run or said again.
        head, captured = self.captures()
        self.dies_at(support.RELABEL, self.recovers)
        newer = _records_newer(self, captured)

        self.recovers()

        settled = readings.pinned_records(self)
        retired = (*git_support.invalidated(self), (captured.receipt, "superseded"))
        self.assertEqual(settled[1].receipt, newer.receipt)
        self.assertEqual((settled[0], settled[2]), (None, retired))
        self.assertEqual(self.posted(captured), [captured.commands])
        self.assertEqual(self.posted(newer), [newer.commands])
        self.assert_recovered(head)

    def test_a_floor_past_the_run_invalidates_it(self) -> None:
        # The recovery settles the run and dies at its relabel, and a
        # revision past it is spent with nothing left recorded beside it --
        # a newer transaction dropped. That revision outranks the run for
        # good, so the next recovery invalidates it whole rather than route
        # it as the last word on the head or hold every later poll over it,
        # and routes the head, already announced, to the fresh reviewer.
        head, captured = self.captures()
        self.dies_at(support.RELABEL, self.recovers)
        _writes(self, readings.KEY_REVISION_FLOOR, captured.revision + 1)

        self.recovers()

        retired = (*git_support.invalidated(self), (captured.receipt, readings.INVALIDATED))
        self.assertEqual(readings.pinned_records(self), (None, None, retired))
        self.assert_recovered(head)

    def _leaves_posted(self, leaves_it) -> tuple:
        """A fresh case's reviewed rebase whose finish `leaves_it` posted and unsettled, then a usage fold.

        The head, and the run its finish captured, held with its one artifact
        on the pull request.
        """
        self.setUp()
        head = self.lands_a_reviewed_rebase()
        leaves_it(self, head)
        captured = readings.pinned_records(self)[0]
        self.assert_held(captured)
        self.assert_unannounced()
        self.assertEqual(self.posted(captured), [captured.commands])
        _writes(self, _USAGE, _FOLDED)
        return head, captured


if __name__ == "__main__":
    unittest.main()
