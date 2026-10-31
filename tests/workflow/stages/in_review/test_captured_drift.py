# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A requirements-drift resume on an approved pull request, held under a control, and finished with no developer run.

A body edit on `in_review` resumes the developer on the drift road. Held
under `paused` or `backlog`, its report is captured as it returns and nothing
else moves: the label, the round, the baseline, the move to `validating` the
edit owes, and the pull request's readers all stay as the launch found them.
Unheld, the dispatcher's recovery publishes the captured report -- beside the
commit, or onto the head the pull request carries -- and hands the issue back
to `validating` with the round reset, exactly once, its baseline the
requirements the run was handed. The pull-request feedback the run's prompt
quoted is read once, as its own tick reads it; a comment posted on the pull
request while it waits stays unread for the next scan, a status that
establishes nothing keeps the capture, and an edit, a reset checkout, or a
push meanwhile retires the capture instead of publishing the old output.
"""
from __future__ import annotations

import unittest
from itertools import product
from unittest.mock import MagicMock, patch

from orchestrator.workflow.stages.in_review import feedback as _feedback, surfaces as _surfaces
from tests.support.fakes import FakeComment, FakeLabel, FakeUser
from tests.workflow import (
    captured_drifts as _held,
    captured_fixes as _fixes,
    drift_reports as world,
    fix_reports as _fix_world,
)
from tests.workflow.fixtures import LABEL_IN_REVIEW, LABEL_VALIDATING, _agent

ISSUE = 2_432
PR = 24_320

_HOLDS = tuple(product((_fixes.PAUSED, _fixes.BACKLOG), (True, False)))

_HANDOFF_PENDING = "in_review_handoff_pending"
_PR_READER = "pr_last_comment_id"

# A review budget nearly spent under the approval the edit made stale.
_SPENT_ROUNDS = 2

# A reviewer's comment posted on the pull request while the issue is held.
_LATE_FEEDBACK_ID = 70_000

# A reviewer's comment posted on the pull request behind the in_review scan,
# so the drift resume's prompt quotes it rather than a fix round taking it.
_QUOTED_FEEDBACK_ID = 60_000

_QUOTED_FEEDBACK = "please keep the old flag working too"

# A reply on the issue thread too long for the excerpt a drift prompt quotes
# the thread under, so the prompt cuts it, and the short reply behind it.
_CUT_REPLY_ID = 59_999

_PAST_THE_EXCERPT = 5_000

_CUT_REPLY_BODY = "x" * _PAST_THE_EXCERPT

_CUT_REPLY = FakeComment(id=_CUT_REPLY_ID, body=_CUT_REPLY_BODY, user=FakeUser("alice"))

_SHORT_REPLY = FakeComment(id=_QUOTED_FEEDBACK_ID, body=_QUOTED_FEEDBACK, user=FakeUser("alice"))


class _CommentedBehindTheScan:
    """The in_review feedback scan, behind which a reviewer comments on the pull request, or humans reply on the
    issue thread (`replies`), once.
    """

    def __init__(self, case, *replies: FakeComment) -> None:
        self._case = case
        self._replies = replies
        self._scan = _feedback._scan_fresh_pr_feedback

    def __call__(self, *args, **kwargs):
        """Scan as the stage does, then post the comments the drift resume's prompt reads."""
        scanned = self._scan(*args, **kwargs)
        if self._replies:
            self._case.issue.comments.extend(self._replies)
        else:
            self._case.pull_request.issue_comments.append(FakeComment(
                id=_QUOTED_FEEDBACK_ID, body=_QUOTED_FEEDBACK, user=FakeUser("bob"),
            ))
        return scanned


class _HeldDuringTheCarry:
    """The carry's read of both IssueComment surfaces, during which an operator applies `control` to the issue once."""

    def __init__(self, case, control: str) -> None:
        self._case = case
        self._control = control
        self._reads = _surfaces._issue_space_above
        self.applied = False

    def __call__(self, *args, **kwargs):
        """Apply the control as the first read goes on, then answer as that read does."""
        if not self.applied:
            self._case.issue.labels.append(FakeLabel(self._control))
            self.applied = True
        return self._reads(*args, **kwargs)


def _finished(case) -> dict:
    """The capture, the reports published, the relabels, the round, the marker, the baseline, and the subject."""
    finished = case.pinned()
    subject = case.records()["current"].subject
    return {
        "stage": _fixes.stage_of(finished),
        "reports": len(case.published_reports()),
        "relabels": case.github.label_history,
        "round": finished[_held.ROUND],
        "marker": finished.get(_HANDOFF_PENDING),
        "baseline": finished[_held.BASELINE],
        "requirements": subject.requirements_revision,
        "source": subject.source_sha,
    }


class HeldInReviewDriftTest(unittest.TestCase, _held.HeldDriftTicks):
    """A held in_review drift resume's report is captured, waited through, and finished once on `validating`."""

    def test_each_hold_is_finished_once(self) -> None:
        # Under either control, a resume that committed and one that
        # answered in its report alone: held, the label, round, baseline, and
        # owed move stay as they were; unheld, the report is published once,
        # the issue goes back to `validating` once with the round reset, and
        # the baseline records the requirements the run was handed.
        for control, committed in _HOLDS:
            with self.subTest(control=control, committed=committed):
                self.seeded(ISSUE, PR, LABEL_IN_REVIEW, review_round=_SPENT_ROUNDS)
                launched = _held.held(self.pinned())
                self.held_drift(world.reported(), control, committed=committed)
                held = self.pinned()
                self.assertEqual(
                    (_held.held(held), held.get(_HANDOFF_PENDING), self.github.label_history),
                    (launched, None, []),
                )
                self.held_ticks()
                self.unheld(**_held.READING[committed])
                self.assertEqual(_finished(self), {
                    "stage": _fixes.HANDED_OFF,
                    "reports": 1,
                    "relabels": [(ISSUE, LABEL_VALIDATING)],
                    "round": 0,
                    "marker": None,
                    "baseline": world.handed_revision(self.issue),
                    "requirements": world.handed_revision(self.issue),
                    "source": world.FIXED_HEAD if committed else world.PUBLISHED_HEAD,
                })

    def test_a_control_during_the_carry_holds_it(self) -> None:
        # An operator holds the issue again while the recovery's carry reads
        # the thread and the pull request's conversation, under either
        # control: the issue read again behind those reads holds the capture,
        # with nothing settled, pushed, published, or relabelled; once that
        # control comes off too, the next dispatch finishes it once.
        for control in (_fixes.PAUSED, _fixes.BACKLOG):
            with self.subTest(control=control):
                self.seeded(ISSUE, PR, LABEL_IN_REVIEW)
                self.held_drift(world.reported(), control)
                self.lifts_the_control()
                before = self.pinned()
                held = _HeldDuringTheCarry(self, control)
                with patch.object(_surfaces, "_issue_space_above", held):
                    self.dispatched(**_held.COMMITTED)[_fixes.PUSH_BRANCH].assert_not_called()
                self.assertTrue(held.applied)
                self.assertEqual(
                    (self.pinned(), self.published_reports(), self.github.label_history),
                    (before, [], []),
                )
                self.unheld(**_held.COMMITTED)
                self.assertEqual(
                    (len(self.published_reports()), self.github.label_history),
                    (1, [(ISSUE, LABEL_VALIDATING)]),
                )

    def test_later_feedback_stays_unread(self) -> None:
        # A reviewer comments on the pull request while the issue is held:
        # the recovery settles only what the run was handed, so the reader of
        # that surface stays below the comment for the next in_review scan.
        self.seeded(ISSUE, PR, LABEL_IN_REVIEW)
        self.held_drift(world.reported())
        self.pull_request.issue_comments.append(FakeComment(
            id=_LATE_FEEDBACK_ID, body="please also cover the empty input", user=FakeUser("bob"),
        ))
        self.unheld(**_held.COMMITTED)
        finished = self.pinned()
        self.assertEqual(
            (len(self.published_reports()), self.github.label_history),
            (1, [(ISSUE, LABEL_VALIDATING)]),
        )
        self.assertLess(finished[_PR_READER], _LATE_FEEDBACK_ID)

    def test_quoted_feedback_is_read_once(self) -> None:
        # The drift resume's prompt quoted a reviewer's comment on the pull
        # request, and another reviewer comments while the issue is held: the
        # recovery's carry crosses the comment the run was handed, as its own
        # tick's carry would, and stops below the later one for the next scan.
        self._held_over_quoted_feedback()
        self.pull_request.issue_comments.append(FakeComment(
            id=_LATE_FEEDBACK_ID, body="please also cover the empty input", user=FakeUser("bob"),
        ))
        with _fix_world.author_policy():
            self.unheld(**_held.COMMITTED)
        finished = self.pinned()
        self.assertEqual(
            (_fixes.stage_of(finished), self.github.label_history),
            (_fixes.HANDED_OFF, [(ISSUE, LABEL_VALIDATING)]),
        )
        self.assertGreaterEqual(finished[_PR_READER], _QUOTED_FEEDBACK_ID)
        self.assertLess(finished[_PR_READER], _LATE_FEEDBACK_ID)

    def test_an_unread_conversation_holds_it(self) -> None:
        # The pull request's conversation the quoted comment is read back
        # from will not read: the capture is kept with nothing written,
        # settled, or published, and the dispatch whose read answers
        # finishes it once, the quoted comment read.
        self._held_over_quoted_feedback()
        before = (self.pinned(), self.github.write_state_calls, [])
        with _fix_world.author_policy(), patch.object(
            _surfaces, "_unread_pr_conversation", side_effect=RuntimeError("conversation unavailable"),
        ):
            self.unheld(**_held.COMMITTED)[_fixes.PUSH_BRANCH].assert_not_called()
        kept = (self.pinned(), self.github.write_state_calls, self.published_reports())
        self.assertEqual(kept, before)
        with _fix_world.author_policy():
            self.dispatched(**_held.COMMITTED)
        self.assertEqual(len(self.published_reports()), 1)
        self.assertGreaterEqual(self.pinned()[_PR_READER], _QUOTED_FEEDBACK_ID)

    def test_moves_while_held_retire_it(self) -> None:
        # An edit of the body, the checkout reset off the commit reported on,
        # or the pull request pushed to another head: the capture is retired
        # with nothing published, pushed, relabelled, or settled.
        for moved in ("edit", "checkout", "pull request"):
            with self.subTest(moved=moved):
                self.seeded(ISSUE, PR, LABEL_IN_REVIEW)
                launched = _held.held(self.pinned())
                self.held_drift(world.reported())
                reading = dict(_held.COMMITTED)
                if moved == "edit":
                    world.edits(self, world.LATER_BODY)
                elif moved == "checkout":
                    reading[world.HEAD_SHAS] = (_held.MOVED_HEAD,)
                else:
                    self.pull_request.head.sha = world.CONCURRENT_HEAD
                self.unheld(**reading)[_fixes.PUSH_BRANCH].assert_not_called()
                retired = self.pinned()
                self.assertEqual(
                    (
                        _fixes.stage_of(retired),
                        self.published_reports(),
                        self.github.label_history,
                        _held.held(retired),
                    ),
                    (_fixes.RETIRED, [], [], launched),
                )

    def _held_over_quoted_feedback(self) -> None:
        """Seed the issue and hold its drift resume, whose prompt quoted a reviewer's comment on the pull request."""
        self.seeded(ISSUE, PR, LABEL_IN_REVIEW)
        self.control = _fixes.PAUSED
        held_under = MagicMock(side_effect=_fixes.HeldUnder(self, _fixes.PAUSED, world.reported()))
        with _fix_world.author_policy(), patch.object(
            _feedback, "_scan_fresh_pr_feedback", _CommentedBehindTheScan(self),
        ):
            self.dispatched(held_under)
        self.assertIn(_QUOTED_FEEDBACK, held_under.call_args.args[1])
        self.assertEqual(_fixes.stage_of(self.pinned()), _fixes.PENDING)


class QuotedThreadTest(unittest.TestCase, _held.HeldDriftTicks):
    """The issue-thread replies a held drift resume's prompt quoted are read by its recovery as by its own tick."""

    def test_a_quoted_reply_is_read_once(self) -> None:
        # A human replies on the issue thread behind the scan, so the drift
        # resume's prompt quotes it: the recovery's carry crosses it as the
        # live tick's carry does, rather than leaving it to buy a fix round.
        live, recovered = self._on_both_roads(_SHORT_REPLY)
        self.assertGreaterEqual(min(live[0], recovered[0]), _QUOTED_FEEDBACK_ID)

    def test_an_omission_holds_both_below_it(self) -> None:
        # A reply too long for the excerpt, and a short one behind it: the
        # prompt quotes the short one whole and only part of the long one, so
        # neither road's carry nor its reply boundary crosses the long one.
        live, recovered = self._on_both_roads(_CUT_REPLY, _SHORT_REPLY)
        self.assertEqual(recovered, live)
        self.assertLess(recovered[0], _CUT_REPLY.id)

    def _on_both_roads(self, *replies: FakeComment) -> tuple:
        """The PR reader and reply boundary a live drift resume, then a held and recovered one, leave over `replies`."""
        finished = []
        for held in (False, True):
            self.seeded(ISSUE, PR, LABEL_IN_REVIEW)
            behind = _CommentedBehindTheScan(self, *replies)
            with _fix_world.author_policy(), patch.object(_feedback, "_scan_fresh_pr_feedback", behind):
                if held:
                    self.held_drift(world.reported())
                else:
                    self.dispatched(_agent(session_id=world.DEV_SESSION, last_message=world.reported()))
            with _fix_world.author_policy():
                if held:
                    self.unheld(**_held.COMMITTED)
            pinned = self.pinned()
            self.assertEqual(len(self.published_reports()), 1)
            finished.append((pinned[_PR_READER], pinned.get("last_action_comment_id")))
        return tuple(finished)


class UnreadStatusTest(unittest.TestCase, _held.HeldDriftTicks):
    """A recovery whose status read establishes nothing about the tree keeps the capture for a reading that returns."""

    def test_an_unread_status_keeps_it(self) -> None:
        # The status of the checkout the commit, or a report alone, would go
        # out from establishes nothing: that is no loose tree, so the capture
        # is kept with nothing written, settled, pushed, or relabelled, and
        # the dispatch whose status reads finishes it once.
        for committed in (True, False):
            with self.subTest(committed=committed):
                self.seeded(ISSUE, PR, LABEL_IN_REVIEW)
                self.held_drift(world.reported(), committed=committed)
                before = (self.pinned(), self.github.write_state_calls, [])
                unread = self.unheld(**_held.READING[committed], tree_readable=False)
                unread[_fixes.PUSH_BRANCH].assert_not_called()
                kept = (self.pinned(), self.github.write_state_calls, self.github.label_history)
                self.assertEqual(kept, before)
                self.dispatched(**_held.READING[committed])
                self.assertEqual(
                    (len(self.published_reports()), self.github.label_history),
                    (1, [(ISSUE, LABEL_VALIDATING)]),
                )


if __name__ == "__main__":
    unittest.main()
