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
requirements the run was handed. A comment posted on the pull request while
it waits stays unread for the next scan, and an edit, a reset checkout, or a
push meanwhile retires the capture instead of publishing the old output.
"""
from __future__ import annotations

import unittest
from itertools import product
from unittest.mock import patch

from orchestrator.workflow.stages.in_review import surfaces as _surfaces
from tests.support.fakes import FakeComment, FakeLabel, FakeUser
from tests.workflow import captured_drifts as _held, captured_fixes as _fixes, drift_reports as world
from tests.workflow.fixtures import LABEL_IN_REVIEW, LABEL_VALIDATING

ISSUE = 2_432
PR = 24_320

_HOLDS = tuple(product((_fixes.PAUSED, _fixes.BACKLOG), (True, False)))

_HANDOFF_PENDING = "in_review_handoff_pending"
_PR_READER = "pr_last_comment_id"

# A review budget nearly spent under the approval the edit made stale.
_SPENT_ROUNDS = 2

# A reviewer's comment posted on the pull request while the issue is held.
_LATE_FEEDBACK_ID = 70_000


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


if __name__ == "__main__":
    unittest.main()
