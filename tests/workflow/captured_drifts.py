# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A requirements-drift resume whose developer reports while an operator holds the issue, dispatched as a poll does.

The world is the drift report world (`drift_reports`): an open pull request on
the issue's branch whose last publication the code-publication receipt names,
a checkout on its head at the issue's own path, a push that moves the pull
request onto the commit it sends, and a body edited off the baseline the issue
records. The developer an operator holds the issue under applies the control
to the issue itself as it runs (`captured_fixes.HeldUnder`), so the live-pause
guard behind it, and every poll after it, reads it. Every tick is a whole
dispatch (`issue_processing._process_issue`), since it is the dispatcher that
decides a captured completion ahead of the stage handler, and the stage's own
drift check behind it.
"""
from __future__ import annotations

from functools import partial
from types import MappingProxyType
from unittest.mock import MagicMock, patch

from orchestrator import config
from orchestrator.workflow.engine import issue_processing as _issue_processing
from tests.support.fakes import FakeLabel
from tests.workflow import captured_fixes as _fixes, drift_reports as world
from tests.workflow.fixtures import _TEST_SPEC, AGENT_RUN_WRITES, Launched

BASELINE = "user_content_hash"
ROUND = "review_round"

# The records a held return may move beside its charge and accounting: its capture.
HELD_WRITES = 1

# What a recovery reads of the checkout: the commit the held run left, which
# the remote agrees with once the push lands; and the head the pull request
# already carries, where the run committed nothing.
COMMITTED = _fixes.COMMITTED
UNMOVED = _fixes.UNMOVED

READING = _fixes.READING

# A recovery whose checkout reads as the commit the held run left at its
# admission and once behind it, will not read the time after, and reads as
# that commit again from then on.
LOST_ONCE = MappingProxyType({
    **COMMITTED, world.HEAD_SHAS: (world.FIXED_HEAD, world.FIXED_HEAD, "", world.FIXED_HEAD),
})

# The head a human resets the checkout onto while the issue is held, and the
# one somebody pushes onto the pull request meanwhile.
MOVED_HEAD = "d" * len(world.FIXED_HEAD)

# Wide enough that no case here is ended by the review cap, which is a bound of
# its own with its own park and its own operator command.
_REVIEW_ROUNDS = 10


class HeldAtTheWalk:
    """A write over a capture -- its transfer or its retirement -- whose edit's last read sees `control` applied.

    The write reads the comment for itself, its guarded commit reads it
    again, and the strict editor sending the edit walks the thread to it once
    more: the last reading before the edit goes out. The control lands on
    `issue` during that walk, behind everything the write took before it.
    """

    def __init__(self, github, issue, control: str, write) -> None:
        self._github = github
        self._issue = issue
        self._control = control
        self._write = write
        self._walks = github._pinned_comment
        self.applied = False

    def __call__(self, *args, **kwargs):
        """Make the write as asked, the control applied during its strict edit's walk to the comment."""
        with patch.object(self._github, "_pinned_comment", side_effect=self._walk):
            return self._write(*args, **kwargs)

    def _walk(self, *walked, **options):
        """Walk to the comment as the client does, applying the control during the strict edit's walk."""
        found = self._walks(*walked, **options)
        if options.get("authoritative") and not self.applied:
            self._issue.labels.append(FakeLabel(self._control))
            self.applied = True
        return found


def held(record: dict) -> tuple:
    """What a held return must leave as it was: the baseline, the round, and the reports and debt."""
    return tuple(record.get(field) for field in (
        BASELINE, ROUND, "developer_report_delivery", "developer_report_pending", "developer_report_owed",
    ))


class HeldDriftTicks(world._DriftReportMixin):
    """Whole dispatches over one issue edited under its pull request, its developer held as it resumes."""

    def held_drift(self, reply: str, control: str = _fixes.PAUSED, **run_options) -> dict:
        """A dispatch of the stage's drift resume, held under `control` as it runs and finishing as `reply`.

        The run is launched once and its return held: nothing moves but its
        charge, its accounting, and its capture -- no report, push, label,
        round, baseline, or session. Answers the record it left.
        """
        self.control = control
        launched = Launched.over(self.github, self.issue.number)
        held_under = _fixes.HeldUnder(self, control, reply)
        ran = self.dispatched(MagicMock(side_effect=held_under), **run_options)
        ran[_fixes.RUN_AGENT].assert_called_once()
        left = launched.held(
            self, self.github, self.issue.number,
            writes=AGENT_RUN_WRITES + HELD_WRITES, beside=(_fixes.CAPTURED,),
        )
        self.assertEqual(_fixes.stage_of(left), _fixes.PENDING)
        self.assertEqual(self.published_reports(), [])
        return left

    def dispatched(self, run_agent=None, **run_options):
        """One whole dispatch of the issue over its checkout; the seams it ran over.

        A run that `committed` leaves the checkout on `FIXED_HEAD`; one that
        did not leaves it where the pull request stands.
        """
        agents = MagicMock() if run_agent is None else run_agent
        standing = self.pull_request.head.sha
        after = world.FIXED_HEAD if run_options.pop("committed", True) else standing
        options = MappingProxyType({
            "has_new_commits": True,
            "dirty_files": (),
            "push_branch": world._LandingPush(self.pull_request),
            world.HEAD_SHAS: (standing, after),
            world.FETCHED_TIP: after,
            "issue_worktree": _fixes.CHECKOUT,
            **run_options,
        })
        with patch(world._WORKTREE_PATH, return_value=world._EXISTING_WORKTREE), patch.object(
            config, "MAX_REVIEW_ROUNDS", _REVIEW_ROUNDS,
        ):
            return self._run(
                partial(_issue_processing._process_issue, self.github, _TEST_SPEC, self.issue),
                run_agent=agents,
                **options,
            )

    def held_ticks(self) -> None:
        """Two dispatches while the issue stays held: neither runs anything nor writes anything."""
        for tick in ("first", "second"):
            with self.subTest(held_tick=tick):
                before = (self.pinned(), self.github.write_state_calls)
                self.dispatched()[_fixes.RUN_AGENT].assert_not_called()
                self.assertEqual((self.pinned(), self.github.write_state_calls), before)

    def lifts_the_control(self) -> None:
        """Take the control the issue is held under off it."""
        for label in tuple(self.issue.labels):
            if label.name == self.control:
                self.issue.labels.remove(label)

    def unheld(self, **run_options):
        """Take the control off and dispatch once; no agent may run."""
        self.lifts_the_control()
        recovered = self.dispatched(**run_options)
        recovered[_fixes.RUN_AGENT].assert_not_called()
        return recovered

    def hand_edit(self, **fields) -> None:
        """Rewrite pinned fields as another road, or a human, would between two ticks."""
        state = self.github.read_pinned_state(self.issue)
        for key, spelled in fields.items():
            state.set(key, spelled)
        self.github.write_pinned_state(self.issue, state)
