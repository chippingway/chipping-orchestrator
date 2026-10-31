# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The human-feedback route's fixing round, its developer held as it runs, and every later tick dispatched whole.

The world is the human-feedback route's (`human_fix_reports`): an approved pull
request a human comments on, the `in_review` tick that bookmarks the batch and
flips the label, and the fixing round behind it. The round's developer is the
one an operator may hold the issue under as it runs (`Held`), and every tick
after it is a whole dispatch (`captured_fixes.HeldFixTicks`), since it is the
dispatcher that decides a captured completion ahead of the stage handler.
`FeedbackTicks` adds what a case reads back over those ticks.
"""
from __future__ import annotations

from types import MappingProxyType
from unittest.mock import MagicMock, patch

from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import review_subjects as _review_subjects
from tests.support.fakes import FakeComment, FakeLabel, FakeUser
from tests.workflow import (
    captured_fixes as _held,
    drift_reports as _drift_world,
    fix_reports as world,
    human_fix_reports as human,
    published_reports as _published_reports,
)
from tests.workflow.fixtures import LABEL_IN_REVIEW, LABEL_VALIDATING, _agent, accounted

# The round the approved pull request arrives carrying, which this route resets.
SPENT_ROUNDS = 2

PENDING_FIX_AT = "pending_fix_at"
PENDING_FIX_IDS = "pending_fix_issue_ids"
PR_LAST = "pr_last_comment_id"
BOUNDARY = "last_action_comment_id"
BASELINE = "user_content_hash"

# What a human asks the round for, by whether its answer is a commit.
ASKED = MappingProxyType({True: human.HUMAN_CODE_FEEDBACK, False: human.HUMAN_REPORT_FEEDBACK})

# What a human replies on the issue thread while the round is out, which no
# prompt of it carried.
LATER_REPLY = "and please keep the old flag working too"

# Where a round the recovery or the next dispatch finished leaves the issue:
# its capture handed off, one report on the pull request, the round reset,
# and the label back on `workflow:validating` (`FeedbackTicks.standing`).
HANDED_BACK = (_held.HANDED_OFF, 1, 0, LABEL_VALIDATING)

# The revision the round's report settles at: the one past the report the
# pull request was opened with, and no other.
ROUND_REVISION = 2


class Held:
    """The developer's run, during which `during` happens and an operator applies `control`, ending as `returned`."""

    def __init__(self, case, control: str, returned, during=None) -> None:
        self._case = case
        self._control = control
        self._returned = returned
        self._during = during

    def __call__(self, *_spawn, **_options):
        """Make the move, apply the control as the run goes on, then answer as the run finished."""
        if self._during is not None:
            self._during()
        self._case.issue.labels.append(FakeLabel(self._control))
        return self._returned


class CommentingPush(_drift_world._LandingPush):
    """A push that lands, a human commenting on the pull request as it does."""

    def __init__(self, case) -> None:
        super().__init__(case.pull_request)
        self._case = case

    def __call__(self, *push, **options):
        """Land the push, then leave the comment."""
        landed = super().__call__(*push, **options)
        self._case.comments_on_the_pull_request()
        return landed


class ControlAtRead:
    """The pull request's reads, an operator's `control` applied as the `at`-th of them is answered.

    `ahead` is how many had been answered when the first pinned edit went
    out, None until one did -- with no `at`, a count of the reads a tick
    takes ahead of its first write.
    """

    def __init__(self, case, control: str = _held.PAUSED, at: int | None = None) -> None:
        self._case = case
        self._read = case.github.get_pr
        self._edit = case.github.edit_pinned_state
        self._control = control
        self._at = at
        self.reads = 0
        self.ahead = None

    def read(self, pr_number: int):
        """Answer one read of the pull request, applying the control where it is the `at`-th."""
        answered = self._read(pr_number)
        self.reads += 1
        if self.reads == self._at:
            self._case.issue.labels.append(FakeLabel(self._control))
        return answered

    def edit(self, issue, state, **options):
        """Send one pinned edit, noting how many reads were answered ahead of the first."""
        if self.ahead is None:
            self.ahead = self.reads
        return self._edit(issue, state, **options)


class _FeedbackWorld(human._HumanFixReportMixin, _held.CapturedFixTicks):
    """The human-feedback route's ticks, and what a human does between and during them."""

    def opened(self, issue_number: int, pr_number: int, *, committed: bool = True, **extra) -> int:
        """An approved pull request a human comments on, routed to `workflow:fixing`; the comment's id."""
        self.seeded(issue_number, pr_number, LABEL_IN_REVIEW, review_round=SPENT_ROUNDS, **extra)
        self.routed(ASKED[committed])
        self.later = None
        return max(comment.id for comment in self.issue.comments)

    def held_round(self, returned=None, control: str = _held.PAUSED, during=None, **run_options):
        """A dispatch of the round, its developer held under `control` and ending as `returned`, a report by default."""
        self.control = control
        if returned is None:
            returned = _agent(session_id=world.DEV_SESSION, last_message=world.reported())
        runs = world._Runs(Held(self, control, returned, during))
        return self.dispatched(MagicMock(side_effect=runs), **run_options)

    def live_round(self) -> None:
        """The fixing round, its developer reporting with nothing holding the issue."""
        self.resumed(world.reported(), issue_worktree=_held.CHECKOUT)

    def answered_afresh(self) -> tuple:
        """A dispatch whose developer reports over the batch; how many runs it made, and the last one's prompt."""
        developer = MagicMock(side_effect=world._Runs(world.reported()))
        runs = self.dispatched(developer, **_held.UNMOVED)[_held.RUN_AGENT]
        return runs.call_count, runs.call_args.args[1]

    def comments_on_the_pull_request(self) -> None:
        """A human comment on the pull request, above everything posted so far."""
        self.later = FakeComment(
            id=self.github.next_reply_id(self.issue), body=human.LATER_PR_COMMENT, user=FakeUser("alice"),
        )
        self.pull_request.issue_comments.append(self.later)

    def replies_later(self) -> None:
        """A human reply on the issue thread, above everything it holds."""
        world.replied(self, LATER_REPLY)

    def routes_it_afresh(self) -> tuple:
        """The issue back on its approved pull request and rescanned by `in_review`; where it went, and the batch."""
        self.github.apply_foreign_label(self.issue, LABEL_IN_REVIEW)
        _published_reports.approves_the_report(self.github, self.issue)
        self.rescanned()
        return self.github.label_history[-1], self.pinned()[PENDING_FIX_IDS]


class FeedbackTicks(_FeedbackWorld):
    """Those ticks, with what a case reads back after them."""

    def reads_ahead_of_the_handoff(self, issue_number: int, pr_number: int) -> int:
        """How many pull request reads a held round's recovery takes ahead of its first pinned edit."""
        self.opened(issue_number, pr_number, committed=False)
        self.held_round(committed=False)
        self.lifts_the_control()
        counting = ControlAtRead(self)
        with patch.object(self.github, "get_pr", side_effect=counting.read), patch.object(
            self.github, "edit_pinned_state", side_effect=counting.edit,
        ):
            self.dispatched(**_held.UNMOVED)
        return counting.ahead

    def standing(self) -> tuple:
        """The capture's stage, how many reports the pull request carries, the round, and the label last written."""
        pinned = self.pinned()
        return (
            _held.stage_of(pinned),
            self.reports(),
            pinned[_held.ROUND],
            self.github.label_history[-1][1],
        )

    def fields(self, *names: str) -> tuple:
        """What the pinned record holds now under each of `names`, None for a key it lacks."""
        pinned = self.pinned()
        return tuple(pinned.get(name) for name in names)

    def finished(self, held: dict, *, committed: bool) -> None:
        """The recovery published the report once, settled the frozen batch and round, and handed the issue back."""
        handoff = _held.capture_of(held).handoff
        frozen = dict(handoff.watermarks)
        self.assertEqual(self.standing(), HANDED_BACK)
        self.assertEqual(
            _held.capture_of(self.pinned()).invocation,
            _held.capture_of(held).invocation,
        )
        self.assertEqual(
            self.fields(PENDING_FIX_AT, PENDING_FIX_IDS, _held.AWAITING),
            (None, None, False),
        )
        self.assertEqual(
            self.fields(PR_LAST, BOUNDARY),
            (frozen[PR_LAST], frozen[BOUNDARY]),
        )
        self.assertEqual(accounted(self.pinned()), accounted(held))
        self._published(handoff.requirements_revision, committed=committed)

    def finished_once(self, *, handed: bool) -> None:
        """The next dispatch runs no agent and leaves the round finished once on the commit the run left.

        A handoff that landed leaves the commit unpushed, one ahead of the pull
        request, for the fixing stage's report recovery to publish; one that
        never went out leaves the capture for the dispatcher's recovery.
        """
        finishing = self.dispatched(**(_held.STRANDED if handed else _held.COMMITTED))
        finishing[_held.RUN_AGENT].assert_not_called()
        self.assertEqual(self.standing(), HANDED_BACK)
        self.assertEqual(self.records()["current"].report_revision, ROUND_REVISION)
        self.assertEqual(self.fields(PENDING_FIX_AT), (None,))
        self.assertEqual(self.pull_request.head.sha, world.FIXED_HEAD)
        self.assertEqual(accounted(self.pinned()), (1, 1))

    def _published(self, requirements: str, *, committed: bool) -> None:
        """The round's one report, on the head the pull request carries, stamped with what its run was handed.

        The approval the issue arrived with was given the report this one
        replaced, so it covers the pull request no longer.
        """
        head = world.FIXED_HEAD if committed else world.PUBLISHED_HEAD
        current = self.records()["current"]
        self.assertEqual(
            (current.report_revision, current.subject.source_sha, self.pull_request.head.sha),
            (ROUND_REVISION, head, head),
        )
        self.assertEqual(
            (current.subject.requirements_revision, *self.fields(BASELINE)),
            (requirements, requirements),
        )
        self.assertFalse(_review_subjects.approval_covers_current(PinnedState(state_data=self.pinned())))
