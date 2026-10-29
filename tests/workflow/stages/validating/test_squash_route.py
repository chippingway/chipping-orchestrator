# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Where the recorded-collapse route sits in a validating tick, and why.

A squash this issue began and did not finish is answered before anything else
on the tick runs an agent. Asked only from the approval road it would be asked
on no tick whose reviewer times out, crashes, or votes CHANGES_REQUESTED: an
already-landed collapse would never get its notice, its watermarks, or its
relabel, a record nothing can read would reach `fixing` without the park it
owes, and a body edit would resume the dev on a branch standing on a commit
nobody accounted for.

The park is the other half of owning the tick, and the two kinds are answered
differently. This recovery's own park is retried every tick and mentions
nobody twice -- what its notice asks for is proved by the recovery getting
further, not by a reply. A park the size gate worded is held instead, since
the gate says its own piece on every reading it cannot take, and the reply to
one is spent on the recovery rather than on the dev, who would otherwise be
resumed on the very branch the record is about.
"""
from __future__ import annotations

import unittest

from orchestrator.workflow.engine import review_subjects as _review_subjects
from orchestrator.workflow.late_split import collapses as _collapses
from orchestrator.workflow.stages.validating import approved_evidence as _approved_evidence
from tests.workflow.stages.validating import squash_approval_support as _support
from tests.workflow.stages.validating.squash_approval_support import (
    _CollapseWorldMixin,
    _LandsWithACollapseRecorded,
    _RefusesTheCollapse,
    _SquashApprovalFixtureMixin,
)

# The stage a reviewer's CHANGES_REQUESTED would send this issue to, which a
# record nothing can account for may not reach without its park.
LABEL_FIXING = "workflow:fixing"

HANDED_ON = (_support.APPROVAL_ISSUE, _support.LABEL_DOCUMENTING)

# What the park a recovery takes over an approval that does not stand says first.
NOT_RESUMED = "squash-on-approval was not resumed"

# Each way a recorded squash can be left with no approval standing behind
# publishing it, as the edit that leaves it so: an approval record removed,
# written null, or in a shape its reader refuses; a subject of another head
# than the collapse was planned over; and a collapse record that will not
# read whole, which no approval can be bound to.
_REMOVED = object()

_UNBACKED = (
    (_review_subjects.APPROVED_SUBJECT, lambda _recorded: _REMOVED),
    (_approved_evidence.APPROVED_EVIDENCE, lambda _recorded: _REMOVED),
    (_review_subjects.APPROVED_SUBJECT, lambda _recorded: None),
    (_approved_evidence.APPROVED_EVIDENCE, lambda _recorded: None),
    (_review_subjects.APPROVED_SUBJECT, lambda _recorded: "approved"),
    (_review_subjects.APPROVED_SUBJECT, lambda recorded: {**recorded, "sha": _support.COLLAPSED_HEAD}),
    (_collapses.LATE_COLLAPSE_COUNT, lambda _recorded: _REMOVED),
)


class PendingCollapseRouteTest(
    unittest.TestCase,
    _SquashApprovalFixtureMixin,
    _CollapseWorldMixin,
):
    """No road on the tick may reach an agent while a collapse is recorded."""

    def test_a_landed_collapse_is_finished_first(self) -> None:
        github, issue = self._approved_issue()
        self._records_a_collapse(github)

        mocks = self._lands_a_collapse(github, issue)

        mocks[_support.RUN_AGENT].assert_not_called()
        mocks[_support.SQUASH_SEAM].assert_called_once()
        self.assertIn(HANDED_ON, github.label_history)
        self.assertNotIn(_support.COLLAPSE_KEY, github.pinned_data(_support.APPROVAL_ISSUE))

    def test_an_unaccountable_record_parks_first(self) -> None:
        github, issue = self._approved_issue()
        self._records_a_collapse(github)

        mocks = self._run_squash_approval(github, issue, _RefusesTheCollapse())

        mocks[_support.RUN_AGENT].assert_not_called()
        self.assertTrue(github.pinned_data(_support.APPROVAL_ISSUE)[_support.AWAITING_HUMAN])
        self.assertNotIn((_support.APPROVAL_ISSUE, LABEL_FIXING), github.label_history)
        self.assertNotIn(HANDED_ON, github.label_history)

    def test_nothing_recorded_still_reviews(self) -> None:
        # The route costs one lookup on the pinned comment: an issue with no
        # collapse on it reaches the reviewer exactly as it always did.
        github, issue = self._approved_issue()

        mocks = self._lands_a_collapse(github, issue)

        mocks[_support.RUN_AGENT].assert_called_once()

    def test_a_drifted_body_waits_for_the_collapse(self) -> None:
        # Ahead of the drift route as well as of the reviewer: resumed on an
        # edited body, the dev is pointed at a branch standing on a commit
        # nothing has accounted for. And the edit is requirements the approval
        # was never given, so no approval stands behind publishing the squash
        # either: nothing is pushed on either tick, no developer is resumed,
        # and the squash parks with its record kept.
        github, issue = self._approved_issue()
        self._records_a_collapse(github)
        self._edits_the_body(github)

        ticks = [self._lands_a_collapse(github, issue), self._lands_a_collapse(github, issue)]

        pinned = github.pinned_data(issue.number)
        self.assertEqual(
            [(tick[_support.RUN_AGENT].call_count, tick[_support.SQUASH_SEAM].call_count) for tick in ticks],
            [(0, 0), (0, 0)],
        )
        self.assertEqual(
            (pinned[_support.PARK_REASON], _support.COLLAPSE_KEY in pinned, HANDED_ON in github.label_history),
            (_support.PARK_SQUASH_FAILED, True, False),
        )

    def test_a_gate_park_is_left_alone(self) -> None:
        # The size gate posts a fresh notice for every reading it cannot take,
        # so a tick that ran the recovery back into it would mention a human
        # every poll. Held instead, until they answer.
        github, issue = self._approved_issue()
        self._records_a_collapse(github)
        self._parks(github)

        mocks = self._run_squash_approval(github, issue, _RefusesTheCollapse())

        mocks[_support.RUN_AGENT].assert_not_called()
        mocks[_support.SQUASH_SEAM].assert_not_called()
        self.assertEqual(github.posted_comments, [])
        self.assertTrue(github.pinned_data(_support.APPROVAL_ISSUE)[_support.AWAITING_HUMAN])

    def test_its_own_park_is_retried_quietly(self) -> None:
        # What that notice asks for -- a branch reconciled, a comment repaired
        # -- is proved by the recovery getting further rather than by a reply,
        # so it runs again every tick and mentions nobody a second time.
        github, issue = self._approved_issue()
        self._records_a_collapse(github)
        self._parks(github, _support.PARK_SQUASH_FAILED)

        mocks = self._run_squash_approval(github, issue, _RefusesTheCollapse())

        mocks[_support.RUN_AGENT].assert_not_called()
        mocks[_support.SQUASH_SEAM].assert_called_once()
        self.assertEqual(github.posted_comments, [])

    def test_a_human_reply_retries_the_collapse(self) -> None:
        # And the reply is the answer that park asked for, so it clears that
        # park and is spent on the recovery rather than on the dev. It is also
        # words on the thread the approval was never given, though, so no
        # approval stands behind publishing the squash: nothing is pushed, and
        # the recovery's own park takes the gate's place for a human to
        # reconcile the branch.
        github, issue = self._approved_issue()
        self._records_a_collapse(github)
        self._parks(github)
        self._human_replies(issue)

        tick = self._lands_a_collapse(github, issue)

        pinned = github.pinned_data(issue.number)
        self.assertEqual(
            (tick[_support.RUN_AGENT].call_count, tick[_support.SQUASH_SEAM].call_count),
            (0, 0),
        )
        self.assertEqual(
            (pinned[_support.AWAITING_HUMAN], pinned[_support.PARK_REASON]),
            (True, _support.PARK_SQUASH_FAILED),
        )


class UnapprovedCollapseRouteTest(
    unittest.TestCase,
    _SquashApprovalFixtureMixin,
    _CollapseWorldMixin,
):
    """A recorded squash is published by nothing an approval does not stand behind."""

    def test_an_unbacked_squash_parks_instead(self) -> None:
        # The pull request stands where a landed push would leave it, which
        # is no proof that resuming the push publishes nothing: nothing is
        # pushed, every record is kept, and the park is taken once -- the
        # next tick asks again and mentions nobody.
        for key, edit in _UNBACKED:
            with self.subTest(key=key, edit=edit):
                ran, left = self._two_ticks(key, edit)

                self.assertEqual(ran, [(0, 0), (0, 0)])
                self.assertEqual(left, (1, _support.PARK_SQUASH_FAILED, True, False))

    def _two_ticks(self, key: str, edit) -> tuple:
        """Two ticks over a recorded squash whose `key` was edited by `edit`: what each ran, and what they left.

        The squash calls and agent runs of each tick, and what is left on the
        issue (`_left`).
        """
        world = self._approved_issue()
        self._records_a_collapse(world[0])
        planned = world[0].pinned_data(world[1].number)[_support.COLLAPSE_KEY]
        self._edits(world[0], key, edit)
        ran = [self._ticks(*world), self._ticks(*world)]
        return ran, self._left(world, planned)

    def _left(self, world, planned: str) -> tuple:
        """How many notices said the squash was not resumed, the park reason, whether the record still names `planned`.

        And whether the label moved to documenting.
        """
        github = world[0]
        pinned = github.pinned_data(world[1].number)
        return (
            sum(NOT_RESUMED in body for _, body in github.posted_comments),
            pinned[_support.PARK_REASON],
            pinned[_support.COLLAPSE_KEY] == planned,
            HANDED_ON in github.label_history,
        )

    def _ticks(self, github, issue) -> tuple[int, int]:
        """Run one tick whose squash would land; how many times it ran the squash, and an agent."""
        tick = self._run_squash_approval(github, issue, _LandsWithACollapseRecorded())
        return tick[_support.SQUASH_SEAM].call_count, tick[_support.RUN_AGENT].call_count

    def _edits(self, github, key: str, edit) -> None:
        """Leave the pinned record `key` as `edit` makes it, taken off the comment where that is `_REMOVED`."""
        issue = github.get_issue(_support.APPROVAL_ISSUE)
        state = github.read_pinned_state(issue)
        edited = edit(state.get(key))
        if edited is _REMOVED:
            state.state_data.pop(key)
        else:
            state.set(key, edited)
        github.write_pinned_state(issue, state)


if __name__ == "__main__":
    unittest.main()
