# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What `publication` publishes on a clean rebase, and what `guards` refuse."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from orchestrator.config import settings as config
from orchestrator.git.measurement import additions as _measurement
from orchestrator.git.measurement.models import AdditionMeasurement
from orchestrator.workflow.engine import dispatch as _dispatch
from orchestrator.workflow.stages.in_review import handler as _in_review
from tests.git.base_sync.clean_assertions import (
    _assert_clean_events,
    _assert_clean_publication,
    _assert_clean_state_comments,
    _assert_conflict_publication,
    _assert_conflict_state_event,
    _assert_push_failure_git,
    _assert_push_failure_state,
)
from tests.git.base_sync.refresh_scenarios import (
    PUSH_PATCH,
    REBASE_PATCH,
    _clean_rebase_scenario,
    _conflict_rebase_scenario,
)
from tests.git.base_sync.refresh_test_support import (
    CONFLICT_PR_HEAD_SHA,
    GATE_BASE_SHA,
    GATE_CANDIDATE_SHA,
    _AwaitingHumanRecorder,
    _git_result,
    _SyncWorktreeWithBaseFixture,
)
from tests.support.fakes import FakePRRef

ISSUE = 7

# The debt the size gate records before a rebase is pushed, and the head it
# pins that push against.
KEY_APPROVED_SHA = "late_approved_sha"
KEY_APPROVED_LEASE = "late_approved_lease"

# The reset a rollback makes, and the exit code a refused one reports.
_HARD_RESET = ("reset", "--hard")
_GIT_FAILED = 128


class _RefusesTheHardReset:
    """A worktree whose rollback will not go through.

    Every other hardened command answers as the ordinary scenario's does, so
    what the case is about is the one that decides whether the approved commit
    is still reachable.
    """

    def __call__(self, *args, **options):
        if args[:2] == _HARD_RESET:
            return _git_result(returncode=_GIT_FAILED, stderr="reset refused")
        return _git_result()


CEILING = 5
PAST_THE_CEILING = 6
MAX_ADDED_LINES = "MAX_ADDED_LINES"
LABEL_DECOMPOSING = "workflow:decomposing"
COUNT_ADDED_LINES = "_count_added_lines"


def _oversized():
    """A count that takes the pull request past the ceiling."""
    return MagicMock(return_value=AdditionMeasurement(
        base_sha=GATE_BASE_SHA,
        candidate_sha=GATE_CANDIDATE_SHA,
        additions=PAST_THE_CEILING,
    ))

# Workflow labels the publication routes between.
LABEL_VALIDATING = "workflow:validating"
LABEL_RESOLVING_CONFLICT = "workflow:resolving_conflict"
LABEL_DOCUMENTING = "workflow:documenting"

THREE_BEHIND_STDOUT = "3\n"

# The boundary a generation is frozen at, so a partial record reads as one a
# tick left mid-question rather than as prose nobody wrote.
PHASE_MEASURING = "measuring"


class CleanRebaseRoutingUnitTest(_SyncWorktreeWithBaseFixture, unittest.TestCase):
    def test_in_review_rebase_routes_to_validating(self) -> None:
        self._seed_pr_issue(review_round=3)
        self._add_pr()
        scenario = _clean_rebase_scenario(THREE_BEHIND_STDOUT)

        scenario.run(self)

        _assert_clean_publication(self, self, scenario)
        _assert_clean_state_comments(self, self)
        _assert_clean_events(self, self)

    def test_conflict_rebase_routes_to_resolution(self) -> None:
        self._seed_pr_issue()
        self._add_pr(head=FakePRRef(sha=CONFLICT_PR_HEAD_SHA))
        scenario = _conflict_rebase_scenario()

        scenario.run(self)

        _assert_conflict_publication(self, self, scenario)
        _assert_conflict_state_event(self, self)

    def test_validating_rebase_stays_validating(self) -> None:
        self._seed_pr_issue(label=LABEL_VALIDATING)
        self._add_pr()
        scenario = _clean_rebase_scenario()

        scenario.run(self)

        self.assertIn((ISSUE, LABEL_VALIDATING), self.gh.label_history)
        self.assertNotIn(
            (ISSUE, LABEL_RESOLVING_CONFLICT),
            self.gh.label_history,
        )
        scenario[PUSH_PATCH].assert_called_once()

    def test_an_oversized_rebase_is_held(self) -> None:
        # A rebase onto a base that has moved changes what the branch adds to
        # it, so the pull request can cross the ceiling with nobody having
        # written a line. The refresh may not force-publish it past that:
        # nothing is pushed and the issue is adjudicated instead of routed
        # back to the reviewer.
        self._seed_pr_issue(label=LABEL_VALIDATING)
        scenario = _clean_rebase_scenario()

        with patch.object(config, MAX_ADDED_LINES, CEILING), patch.object(
            _measurement, COUNT_ADDED_LINES, _oversized(),
        ):
            scenario.run(self)

        scenario[PUSH_PATCH].assert_not_called()
        self.assertIn((ISSUE, LABEL_DECOMPOSING), self.gh.label_history)
        self.assertNotIn((ISSUE, LABEL_VALIDATING), self.gh.label_history)

    def test_documenting_rebase_routes_to_validating(self) -> None:
        self._seed_pr_issue(label=LABEL_DOCUMENTING)
        self._add_pr()

        _clean_rebase_scenario().run(self)

        self.assertIn((ISSUE, LABEL_VALIDATING), self.gh.label_history)
        self.assertNotIn(
            (ISSUE, LABEL_RESOLVING_CONFLICT),
            self.gh.label_history,
        )


class PartialLateRecordUnitTest(
    _SyncWorktreeWithBaseFixture, unittest.TestCase,
):
    """A record carrying part of a group is not one to rebase a branch under.

    The refresh runs first each tick, and the owner that reads a partial late
    record as damage runs at dispatch -- so a hold that recognised only the
    two commits would rebase and force-push the branch a whole tick before
    anything parked it. What the park then promises, and what every retry
    behind it is bound to, is a checkout still standing where the record says.
    """

    def test_a_reading_with_no_candidate_holds(self) -> None:
        # The base it was measured from, the ceiling it was measured against,
        # and the boundary it stands at all survive the edit that took the
        # commit -- and the retry reads every one of them.
        refreshed = self._refreshed(
            late_base_sha=GATE_BASE_SHA,
            late_threshold=CEILING,
            late_phase=PHASE_MEASURING,
        )

        refreshed[REBASE_PATCH].assert_not_called()
        refreshed[PUSH_PATCH].assert_not_called()
        self.assertEqual(self.gh.label_history, [])

    def test_a_lease_with_no_approval_holds(self) -> None:
        # The same claim from its other end: the pair is written together and
        # a lease alone names the head a push was owed against and nothing
        # else, so a rebase under it moves the branch the repair would put
        # back.
        refreshed = self._refreshed(
            late_approved_lease=CONFLICT_PR_HEAD_SHA,
        )

        refreshed[REBASE_PATCH].assert_not_called()
        refreshed[PUSH_PATCH].assert_not_called()

    def test_an_untouched_issue_still_rebases(self) -> None:
        # What says the two above are about the damage rather than about the
        # refresh refusing every issue that ever entered the gate.
        refreshed = self._refreshed()

        refreshed[PUSH_PATCH].assert_called_once()

    def _refreshed(self, **record):
        """One pre-tick refresh of an issue carrying `record`."""
        self._seed_pr_issue(label=LABEL_VALIDATING, **record)
        scenario = _clean_rebase_scenario()
        scenario.run(self)
        return scenario


class CleanRebasePushFailureUnitTest(
    _SyncWorktreeWithBaseFixture, unittest.TestCase,
):
    """What a refused force-push leaves the next tick to read.

    The rewritten branch never reached the remote, so the reset puts the
    worktree back where the pull request is and the park stops every same-tick
    handler from working over a head the remote does not have.
    """

    def test_clean_push_failure_resets_and_parks(self) -> None:
        self._seed_pr_issue()
        self._add_pr()
        scenario = _clean_rebase_scenario(push_result=False)

        scenario.run(self)

        _assert_push_failure_git(self, self, scenario)
        _assert_push_failure_state(self, self)

    def test_clean_push_failure_skips_handler(self) -> None:
        self._seed_pr_issue()
        self._add_pr()
        scenario = _clean_rebase_scenario(push_result=False)
        in_review = _AwaitingHumanRecorder()

        with patch.object(
            _in_review,
            "_handle_in_review",
            side_effect=in_review,
        ):
            scenario.run(self)
            _dispatch._process_issue(
                self.gh,
                self.spec,
                self.gh._issues[ISSUE],
            )

        self.assertEqual(in_review.observed, [True])
        self.assertEqual(self.gh.posted_pr_comments, [])
        self.assertEqual(self.gh.label_history, [])

    def test_a_failed_reset_keeps_the_debt_it_left(self) -> None:
        # The reset is what makes the approved commit unreachable, and so what
        # licenses dropping the record naming it. Refused, the branch may
        # still be standing on that commit while the approval, the head its
        # push is pinned to, and the round that push closes are the only
        # things naming any of it -- dropped there, the exact-candidate retry
        # has nothing to ask for by id and the next tick measures whatever the
        # worktree turns out to be.
        self._seed_pr_issue()
        self._add_pr()

        _clean_rebase_scenario(
            push_result=False, hardened=MagicMock(
                side_effect=_RefusesTheHardReset(),
            ),
        ).run(self)

        pinned = self.gh.pinned_data(ISSUE)
        self.assertEqual(pinned[KEY_APPROVED_SHA], GATE_CANDIDATE_SHA)
        self.assertEqual(pinned[KEY_APPROVED_LEASE], CONFLICT_PR_HEAD_SHA)

    def test_a_reset_forgets_the_debt_it_abandons(self) -> None:
        # The size gate approved the rebased head before this push and
        # recorded it as a commit still owed a publication. The reset above
        # puts the branch back on the pre-rebase SHA, so that commit is not on
        # this branch any more -- only the reflog has it. Left standing, the
        # debt is one nothing can pay: the pre-tick base refresh freezes this
        # branch out of the sync for as long as the issue lives, and the
        # reconciliation ahead of every handler stops the tick for a
        # publication that is never coming.
        self._seed_pr_issue()
        self._add_pr()

        _clean_rebase_scenario(push_result=False).run(self)

        pinned = self.gh.pinned_data(ISSUE)
        self.assertIsNone(pinned[KEY_APPROVED_SHA])
        self.assertIsNone(pinned[KEY_APPROVED_LEASE])

if __name__ == "__main__":
    unittest.main()
