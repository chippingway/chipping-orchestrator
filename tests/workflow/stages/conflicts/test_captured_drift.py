# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A requirements-drift resume mid-rebase, held under a control, and finished with no developer run on its exact lease.

A body edit that lands while `resolving_conflict` rebases the pull request,
and the reply that answers a park that edit's resume left owing a report,
each launch on the drift road. Held under `paused` or `backlog`, the report is
captured as it returns and nothing else moves: the conflict round, the
baseline, the label, and the pull request. Unheld, the recovery publishes the
report through the road both share -- leased against the head the run's
caller proved, the head the body edit began at or the pull request's own head
ahead of the reply -- and hands a pushed round to `validating` once, counted
once; a report with no commit settles on the head the pull request carries and
leaves the issue here. A push meanwhile retires the capture rather than
adopting the moved head as the lease.
"""
from __future__ import annotations

import unittest
from itertools import product

from tests.workflow import (
    captured_drifts as _held,
    captured_fixes as _fixes,
    drift_reports as world,
    fix_reports as _fix_world,
)
from tests.workflow.fixtures import LABEL_VALIDATING, _agent
from tests.workflow.stages.conflicts import drift_report_support as conflict

_CONFLICT_ROUND = "conflict_round"

# The head a force-push is leased against, as the push seam is handed it.
_LEASE = "force_with_lease"

_HOLDS = tuple(product((_fixes.PAUSED, _fixes.BACKLOG), (True, False)))

# A developer that committed and wrote no report, which parks the body edit's
# resume owing one.
_UNREPORTED = "rebased onto main and folded in the new criterion"


class HeldConflictDriftTicks(conflict._ConflictDriftReportMixin, _held.HeldDriftTicks):
    """Whole dispatches mid-rebase, the stage's git answering as a branch on its base, under the fix loop's authors."""

    def dispatched(self, run_agent=None, **run_options):
        """One whole dispatch under the world the conflict stage reads its git and its replies in."""
        with conflict.on_its_base(), _fix_world.author_policy():
            return super().dispatched(run_agent, **run_options)


class HeldConflictDriftTest(unittest.TestCase, HeldConflictDriftTicks):
    """A held drift resume mid-rebase is captured, waited through, and finished once on its own lease."""

    def test_each_hold_is_finished_once(self) -> None:
        # Under either control, a resume that committed and one that
        # answered in its report alone: held, the round, baseline, and label
        # stay as they were; unheld, the report is published once, a commit
        # is pushed over the head the resume began at and its round counted
        # once on the way to `validating`, and a report alone stays here on
        # the head the pull request carries.
        for control, committed in _HOLDS:
            with self.subTest(control=control, committed=committed):
                self.seeded_on_conflict()
                launched = _held.held(self.pinned())
                held = self.held_drift(world.reported(), control, committed=committed)
                self.assertEqual(
                    (_held.held(held), held[_CONFLICT_ROUND], self.github.label_history),
                    (launched, 0, []),
                )
                self.held_ticks()
                self._leased(self.unheld(**_held.READING[committed]), committed=committed)
                self._finished(committed=committed)

    def test_a_held_reply_finishes_the_report_it_owes(self) -> None:
        # The body edit's resume committed and wrote no report, so it parked
        # owing one; the reply that answers it is held as it reports. The
        # recovery publishes the commit under that report, leased against the
        # head the pull request stood on ahead of the reply, and hands the
        # round to `validating` once, the report settling behind it.
        self.seeded_on_conflict(documented=False)
        self.dispatched(_agent(session_id=world.DEV_SESSION, last_message=_UNREPORTED))
        world.human_reply(self)
        self.held_drift(world.reported(), **world.STRANDED)
        self.assertEqual(self.pull_request.head.sha, world.PUBLISHED_HEAD)
        self._leased(self.unheld(**world.STRANDED), committed=True)
        self.reconcile()
        self._finished(committed=True)

    def test_a_push_while_held_retires_it(self) -> None:
        # Somebody pushes to the pull request while the issue is held: the
        # lease the run's caller proved no longer stands, so the capture is
        # retired with nothing pushed, published, counted, or relabelled.
        self.seeded_on_conflict()
        launched = _held.held(self.pinned())
        self.held_drift(world.reported())
        self.pull_request.head.sha = world.CONCURRENT_HEAD
        self.unheld(**_held.COMMITTED)[_fixes.PUSH_BRANCH].assert_not_called()
        retired = self.pinned()
        self.assertEqual(
            (_fixes.stage_of(retired), self.published_reports(), retired[_CONFLICT_ROUND], self.github.label_history),
            (_fixes.RETIRED, [], 0, []),
        )
        self.assertEqual(_held.held(retired), launched)

    def _leased(self, recovered, *, committed: bool) -> None:
        """A recovery that `committed` pushed once, leased against the head its caller proved; else nothing."""
        pushed = recovered[_fixes.PUSH_BRANCH]
        self.assertEqual(pushed.call_count, int(committed))
        if committed:
            self.assertEqual(pushed.call_args.kwargs.get(_LEASE), world.PUBLISHED_HEAD)

    def _finished(self, *, committed: bool) -> None:
        """One report published, of the requirements the run was handed, and the round counted by the commit alone."""
        finished = self.pinned()
        subject = self.records()["current"].subject
        self.assertEqual(
            (
                len(self.published_reports()),
                subject.requirements_revision,
                subject.source_sha,
                finished[_held.BASELINE],
                finished[_CONFLICT_ROUND],
                self.github.label_history,
            ),
            (
                1,
                self.handed(),
                world.FIXED_HEAD if committed else world.PUBLISHED_HEAD,
                self.handed(),
                1 if committed else 0,
                [(conflict.ISSUE, LABEL_VALIDATING)] if committed else [],
            ),
        )


if __name__ == "__main__":
    unittest.main()
