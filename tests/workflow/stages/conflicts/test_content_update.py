# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What this stage's content updates owe the pull request they join.

Every commit `workflow:resolving_conflict` publishes goes onto a pull request
the remote already carries -- a clean rebase that produced a new head, a
resolution an agent wrote, a body edit resolved into a commit, and commits a
crashed tick left unpushed. None of them is a diff of its own to the reviewer
who reads the result: what a push produces is everything the pull request
comes to with the commit in it, which is why the reading the size gate takes
is three-dot from the base the REMOTE names rather than from the head the pull
request was standing on.

The four windows that reading opens are what these pin down. A reading nobody
could take leaves a pair frozen with no count on it, and the tick ahead of the
next handler is what answers it -- without re-rebasing and without re-running
the agent that already finished. A candidate the count comes back over is HELD
rather than pushed, which ends the tick on `workflow:decomposing` with the
round this stage was in the middle of recorded for the tick that resumes
behind the settlement. A publication that MOVED between the freeze and the
reading that answers it is refused rather than measured against a pull request
the pair was never taken on. And a rebase that changed no head never enters the
gate at all: there is nothing to publish, so there is nothing to measure, and
the round it counts is the one that keeps a permanently-unmergeable pull
request from looping forever.
"""
from __future__ import annotations

import importlib
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from orchestrator.git.measurement.models import MeasurementFailure
from orchestrator.git.worktrees import paths as _worktree_paths
from orchestrator.workflow import state as _workflow_state
from orchestrator.workflow.engine import (
    issue_processing as _issue_processing,
    stage_targets as _stage_targets,
)
from tests.workflow.fixtures import (
    _TEST_SPEC,
    MEASURED_BASE_SHA,
    MEASURED_CANDIDATE_SHA,
    _agent,
)
from tests.workflow.stages.conflicts.content_update_support import (
    CONFLICT_ISSUE,
    CONFLICT_PR,
    CONFLICT_PR_HEAD_SHA,
    GATE_CEILING,
    MOVED_PR_HEAD_SHA,
    RESOLVED_HEAD_SHA,
    _ResolvingConflictMixin,
    recorded_generation,
)

CONFLICT_FILE = "a.py"

BEFORE_HEAD = CONFLICT_PR_HEAD_SHA
MERGED_HEAD = RESOLVED_HEAD_SHA

RESOLVING_CONFLICT = _workflow_state.WorkflowLabel.RESOLVING_CONFLICT

LABEL_DECOMPOSING = "workflow:decomposing"
LABEL_VALIDATING = "workflow:validating"

PUSH_BRANCH = "_push_branch"
RUN_AGENT = "run_agent"
COUNT_ADDED_LINES = "_count_added_lines"
WORKTREE_PATH = "_worktree_path"

# The two keywords a gated push names its commit and pins its ref by.
REVISION = "revision"
LEASE = "force_with_lease"

AWAITING_HUMAN = "awaiting_human"
PARK_REASON = "park_reason"
CONFLICT_ROUND = "conflict_round"
RESOLVED_AT = "last_conflict_resolved_at"
SETTLED_OUTCOME = "conflict_settled_outcome"
SETTLED_SHA = "conflict_settled_sha"

KEY_CANDIDATE_SHA = "late_candidate_sha"
KEY_BASE_SHA = "late_base_sha"
KEY_ADDITIONS = "late_additions"
KEY_PUBLISHED_SHA = "late_published_sha"
KEY_PUBLISHED_PR = "late_published_pr_number"
KEY_SOURCE_STAGE = "late_source_stage"

PARK_MEASUREMENT_FAILED = "late_measurement_failed"

DRIFT_RESOLVED = "drift_resolved"
BASE_UP_TO_DATE = "base_up_to_date"

MAX_ADDED_LINES = "MAX_ADDED_LINES"
UNDER_THE_CEILING = 4
PAST_THE_CEILING = GATE_CEILING + 1

# A checkout something wrote to between the reading and the count, so the diff
# a push would publish is not the diff anything here could measure.
DIFF_FAILED = MeasurementFailure.DIFF_FAILED

# The pull request a pair was frozen against, where the issue has since been
# repointed at another one.
OTHER_PR = 801

# A directory that is really on disk, so the reconciliation ahead of the
# handler finds a checkout to take its reading in.
TEMP_ROOT = Path("/tmp")

# What the dev says when a body edit needs no code change, which is the one
# no-commit reply this stage does not park on.
DRIFT_ACK = "ACK: the resolution already covers the edited requirement"


def _rounds_of(github) -> list[dict]:
    """Every `conflict_round` increment this run recorded."""
    return [
        event for event in github.recorded_events
        if event["event"] == CONFLICT_ROUND
    ]


class _ContentUpdateMixin(_ResolvingConflictMixin):
    """One conflict tick that puts a commit on an open pull request."""

    def _agent_resolution(self, **run_options):
        """One dev-resolved conflict, run to the gate in front of its push."""
        github, issue = self._seed()[:2]
        return github, self._run_with_merge(
            github, issue,
            merge_succeeded=False,
            conflicted_files=[CONFLICT_FILE],
            head_shas=[BEFORE_HEAD, MERGED_HEAD],
            push_branch=True,
            **run_options,
        )[0]

    def _drift_resolution(self, *, agent=None, **run_options):
        """One body edit resolved into a commit, run to the same gate."""
        github, issue = self._seed()[:2]
        self._seed_with_baseline_hash(github, issue)
        issue.body = "the requirement moved while the rebase was in flight"
        run_options.setdefault("head_shas", [BEFORE_HEAD, MERGED_HEAD])
        return github, self._run_with_merge(
            github, issue,
            push_branch=True,
            run_agent_result=agent or _agent(
                session_id="dev-sess", last_message="resolved the edit",
            ),
            **run_options,
        )[0]

    def _assert_measurement_park(self, github) -> None:
        """A human was asked, and the reading is what they were asked about."""
        pinned = self._pinned(github)
        self.assertTrue(pinned[AWAITING_HUMAN])
        self.assertEqual(pinned[PARK_REASON], PARK_MEASUREMENT_FAILED)

    def _frozen_pair(self, *, parked: bool = False, **record):
        """The pinned comment a crash between the freeze and the count left.

        Unparked by default, which is the shape a crash leaves: the freeze
        landed and the tick died before anything could report a failure. A
        park rides along only where the case is about the retry a reading
        nobody could take is owed.
        """
        park = {
            AWAITING_HUMAN: True, PARK_REASON: PARK_MEASUREMENT_FAILED,
        } if parked else {}
        return self._seed(extra_state={
            **park, **recorded_generation(), **record,
        })[:2]

    def _reconciled(self, github, issue, **run_options):
        """Route one tick with the reconciliation ahead of a mocked handler."""
        dispatched = Mock()
        owner_name, named = _stage_targets._STAGE_HANDLER_TARGETS[
            RESOLVING_CONFLICT
        ]
        run_options.setdefault("added_lines", UNDER_THE_CEILING)
        with patch.object(
            importlib.import_module(owner_name), named, dispatched,
        ), patch.object(
            _worktree_paths, WORKTREE_PATH, return_value=TEMP_ROOT,
        ):
            mocks = self._run(
                lambda: _issue_processing._route_issue_to_handler(
                    github, _TEST_SPEC, issue, github.workflow_label(issue),
                ),
                run_agent=_agent(),
                **run_options,
            )
        return dispatched, mocks


class ConflictCumulativeReadingTest(unittest.TestCase, _ContentUpdateMixin):
    """What the gate reads for a content update, and what never reaches it.

    The ceiling is not a claim about the commit: what a push produces is the
    whole pull request with the commit in it, so a two-line resolution onto an
    already-large branch is held exactly as a large one is. And the gate stands
    in front of a PUSH, so the two exits that publish nothing read nothing.
    """

    def test_the_reading_is_the_whole_pull_request(self) -> None:
        # Three-dot from the base the REMOTE names to the candidate, which is
        # what makes the ceiling cumulative. Taken from the head the pull
        # request is standing on instead, a branch could be grown past
        # `MAX_ADDED_LINES` one small resolution at a time -- which is the one
        # outcome this gate exists to prevent.
        mocks = self._agent_resolution(added_lines=UNDER_THE_CEILING)[1]

        counted = mocks[COUNT_ADDED_LINES].call_args
        self.assertEqual(counted.args[1], MEASURED_BASE_SHA)
        self.assertEqual(counted.args[2], MERGED_HEAD)

    def test_a_no_op_rebase_is_never_measured(self) -> None:
        # Measured anyway, this exit would route a pull request nobody grew
        # into an adjudication over a diff that was already on it -- and the
        # commit it would be held for does not exist. The round it counts
        # without a push is covered where that counter is.
        github, issue = self._seed()[:2]

        mocks = self._run_with_merge(
            github, issue,
            merge_succeeded=True,
            head_shas=[BEFORE_HEAD, BEFORE_HEAD],
            push_branch=True,
        )[0]

        mocks[COUNT_ADDED_LINES].assert_not_called()
        self.assertNotIn(KEY_CANDIDATE_SHA, self._pinned(github))

    def test_an_acked_body_edit_is_not_measured(self) -> None:
        # The dev read the edited body and reports the resolution already
        # covers it. Nothing was committed, so there is nothing to publish and
        # nothing to measure -- and no round is owed for a reading nobody
        # took.
        github, mocks = self._drift_resolution(
            agent=_agent(session_id="dev-sess", last_message=DRIFT_ACK),
            head_shas=[BEFORE_HEAD, BEFORE_HEAD],
        )

        mocks[COUNT_ADDED_LINES].assert_not_called()
        mocks[PUSH_BRANCH].assert_not_called()
        pinned = self._pinned(github)
        self.assertEqual(pinned[CONFLICT_ROUND], 0)
        self.assertIsNone(pinned.get(SETTLED_OUTCOME))


class ConflictMeasurementRetryTest(unittest.TestCase, _ContentUpdateMixin):
    """A reading this stage could not take, and the tick that takes it again.

    The freeze is durable and the count that follows it is not. What a failure
    leaves is a pair naming both commits with no number on it, and nothing on
    this stage would go back for it: the next tick would fetch, compare, and
    rebase a branch whose resolution is already on it.
    """

    def test_a_failed_reading_freezes_its_pair(self) -> None:
        # The pair is what makes the retry a retry: asked for by id, the same
        # two commits are measured again. Reported and dropped, the next tick
        # rebases under the park and measures whatever the checkout points at
        # by then.
        github = self._unread_resolution()[0]

        pinned = self._pinned(github)
        self.assertEqual(pinned[KEY_CANDIDATE_SHA], MERGED_HEAD)
        self.assertEqual(pinned[KEY_BASE_SHA], MEASURED_BASE_SHA)
        self.assertNotIn(KEY_ADDITIONS, pinned)
        self._assert_measurement_park(github)

    def test_a_failed_reading_records_its_entry(self) -> None:
        # A pair frozen for a published pull request is only answerable
        # against the publication it was taken on, and none of the three can
        # be worked out later: the label is replaced by the adjudication, the
        # pull request is not the plan one beside it, and the head is one the
        # next push moves.
        pinned = self._pinned(self._unread_resolution()[0])

        self.assertEqual(pinned[KEY_SOURCE_STAGE], str(RESOLVING_CONFLICT))
        self.assertEqual(pinned[KEY_PUBLISHED_PR], CONFLICT_PR)
        self.assertEqual(pinned[KEY_PUBLISHED_SHA], CONFLICT_PR_HEAD_SHA)

    def test_a_failed_reading_publishes_nothing(self) -> None:
        # A reading that could not be taken is not a small candidate. Nothing
        # goes onto the pull request, no round is counted, and the label stays
        # where the resolution left it.
        github, mocks = self._unread_resolution()

        mocks[PUSH_BRANCH].assert_not_called()
        self.assertNotIn(
            (CONFLICT_ISSUE, LABEL_VALIDATING), github.label_history,
        )
        self.assertEqual(self._pinned(github)[CONFLICT_ROUND], 0)

    def test_the_retry_measures_the_recorded_pair(self) -> None:
        # Taken ahead of the handler rather than by it, so the reading is the
        # RECORDED one: the same base and the same candidate, asked for by id
        # rather than re-derived from a branch the base refresh has moved
        # under since.
        github, issue = self._frozen_pair(parked=True)

        mocks = self._reconciled(github, issue)[1]

        counted = mocks[COUNT_ADDED_LINES].call_args
        self.assertEqual(counted.args[1], MEASURED_BASE_SHA)
        self.assertEqual(counted.args[2], MEASURED_CANDIDATE_SHA)

    def test_the_retry_runs_no_dev(self) -> None:
        # The failure was a reading rather than a question, so what it earns
        # is the same pair counted once more and no agent at all -- one that
        # ran would answer with different work, over a resolution a human may
        # already have read.
        github, issue = self._frozen_pair(parked=True)

        dispatched, mocks = self._reconciled(github, issue)

        mocks[RUN_AGENT].assert_not_called()
        pushed = mocks[PUSH_BRANCH].call_args
        self.assertEqual(pushed.kwargs[REVISION], MEASURED_CANDIDATE_SHA)
        self.assertEqual(pushed.kwargs[LEASE], CONFLICT_PR_HEAD_SHA)
        # Only once the effects are out does the stage run over them.
        dispatched.assert_called_once()

    def _unread_resolution(self):
        """One agent resolution whose count could not be taken."""
        return self._agent_resolution(added_lines=DIFF_FAILED)


class ConflictExternalMovementTest(unittest.TestCase, _ContentUpdateMixin):
    """A publication that moved while this stage's pair awaited its count.

    The frozen group is what makes a cumulative reading repeatable: it names
    the pull request the pair was measured against, the stage it was entered
    from, and the head that pull request was standing on. A reading answered
    against anything else is a count taken on one publication and settled
    against another.
    """

    def test_a_moved_head_refuses_the_frozen_pair(self) -> None:
        # Somebody else's push landing between the freeze and this tick. The
        # pair no longer describes what this branch would add to that pull
        # request, so nothing is counted and nothing goes out.
        github, mocks = self._moved(head=MOVED_PR_HEAD_SHA)

        mocks[COUNT_ADDED_LINES].assert_not_called()
        mocks[PUSH_BRANCH].assert_not_called()
        self._assert_measurement_park(github)
        # Named rather than counted, because what an operator has to
        # reconcile differs by which member of the group moved.
        self.assertIn(
            f"was standing at `{CONFLICT_PR_HEAD_SHA}`",
            github.posted_comments[-1][1],
        )

    def test_a_repointed_pull_request_refuses_it_too(self) -> None:
        # The head alone is not an identity -- a branch reused across two pull
        # requests can put the same commit at the tip of both -- so the pull
        # request the pair was measured against is compared as well.
        github, mocks = self._moved(**{KEY_PUBLISHED_PR: OTHER_PR})

        mocks[COUNT_ADDED_LINES].assert_not_called()
        self._assert_measurement_park(github)
        self.assertIn(
            f"measured against pull request #{OTHER_PR}",
            github.posted_comments[-1][1],
        )

    def test_a_refused_pair_is_left_standing(self) -> None:
        # Not re-entered: stamping what this tick read over the group would
        # hide the very disagreement the comparison exists to catch, and the
        # next tick would answer an old count under a publication nobody
        # measured it against.
        pinned = self._pinned(self._moved(head=MOVED_PR_HEAD_SHA)[0])

        self.assertEqual(pinned[KEY_PUBLISHED_SHA], CONFLICT_PR_HEAD_SHA)
        self.assertEqual(pinned[KEY_CANDIDATE_SHA], MEASURED_CANDIDATE_SHA)

    def _moved(self, *, head: str = "", **record):
        """Route one frozen pair over a publication it was not taken on."""
        github, issue = self._frozen_pair(**record)
        if head:
            github.get_pr(CONFLICT_PR).head.sha = head
        return github, self._reconciled(github, issue)[1]


if __name__ == "__main__":
    unittest.main()
