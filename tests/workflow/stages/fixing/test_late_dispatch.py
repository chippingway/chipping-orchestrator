# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A pair frozen for a published pull request, answered before its stage runs.

The freeze is durable and the count that follows it is not, so a tick that
dies in between leaves a record naming both commits with no number on it. What
these pin down is that the next tick takes that reading first: the handler
below would otherwise spawn a reviewer, resume a developer, or read a pull
request still standing where the gate froze it, while the record goes on
freezing the branch out of the base refresh.
"""

from __future__ import annotations

import importlib
import unittest
from unittest.mock import Mock, patch

from orchestrator.git.measurement.models import FrozenCommit
from orchestrator.git.worktrees import paths as _worktree_paths
from orchestrator.workflow import state as _workflow_state
from orchestrator.workflow.engine import (
    issue_processing as _issue_processing,
    stage_targets as _stage_targets,
)
from orchestrator.workflow.late_split import phases as _late_phases
from tests.support.fakes import FakeGitHubClient, FakePRRef, make_issue
from tests.workflow.fixtures import (
    _TEST_SPEC,
    LABEL_DECOMPOSING,
    MEASURED_CANDIDATE_SHA,
    SHA_LENGTH,
    _agent,
    _issue_branch,
    _open_pr_for,
    _PatchedWorkflowMixin,
)
from tests.workflow.stages.fixing import (
    fixing_test_support as fixing,
    published_gate_support as support,
)

ISSUE = fixing.ISSUE
PR_NUMBER = fixing.PR_NUMBER
CEILING = support.CEILING
PAST_THE_CEILING = support.PAST_THE_CEILING
COUNT_ADDED_LINES = support.COUNT_ADDED_LINES
KEY_APPROVED_SHA = support.KEY_APPROVED_SHA
KEY_CANDIDATE_SHA = support.KEY_CANDIDATE_SHA
KEY_MISS_COUNT = support.KEY_MISS_COUNT
KEY_SOURCE_STAGE = support.KEY_SOURCE_STAGE
RUN_AGENT = "run_agent"
PARK_MEASUREMENT_FAILED = support.PARK_MEASUREMENT_FAILED
PARK_REASON = fixing.PARK_REASON
PUSH_BRANCH = fixing.PUSH_BRANCH
KEY_RECEIPT_SHA = support.KEY_RECEIPT_SHA
KEY_RECEIPT_PR = support.KEY_RECEIPT_PR
# The two keywords a gated push names its commit and pins its ref by.
REVISION = "revision"
LEASE = "force_with_lease"

WORKTREE_PATH = "_worktree_path"
# A commit the record does not name, for a checkout something moved while no
# run of this tick was out.
MOVED_CANDIDATE = "ef" * (SHA_LENGTH // 2)
AWAITING_HUMAN = fixing.AWAITING_HUMAN

# The anchor an auto rebase pins before git runs, which its own recovery is
# the only road that ends.
KEY_ANCHOR = "pending_auto_base_rebase_push_sha"

# A stage the refresh drives, which is the only kind an auto rebase pins one on.
ANCHORED_STAGE = _workflow_state.WorkflowLabel.VALIDATING

# What a reading nobody could take left behind, for the tick that takes it.
_MEASUREMENT_PARK = ((AWAITING_HUMAN, True), (PARK_REASON, PARK_MEASUREMENT_FAILED))

# The step that park's own notice named, which every measurement park this
# road takes records with the flags: it is what tells the poll after it
# whether the sentence on the thread already covers what the reading stopped
# at.
_ANNOUNCED_STEP = support.MeasurementFailure.BASE_ABSENT

# The five states the gate can take an issue out of, and so the five that can
# be left holding a pair their own tick froze and never counted.
PUBLISHING_LABELS = (
    _workflow_state.WorkflowLabel.FIXING,
    _workflow_state.WorkflowLabel.VALIDATING,
    _workflow_state.WorkflowLabel.DOCUMENTING,
    _workflow_state.WorkflowLabel.IN_REVIEW,
    _workflow_state.WorkflowLabel.RESOLVING_CONFLICT,
)

# The boundaries a split's own transaction leaves a record standing at once
# its candidate has been committed to becoming children.
SETTLED_SPLIT_PHASES = (
    _late_phases.LatePhase.SPLITTING,
    _late_phases.LatePhase.SUPERSEDING,
    _late_phases.LatePhase.CLEANING_UP,
)

# The ordered register that split wrote down as it created them, which the
# retirement keeps because it says which child owns which slice.
SPLIT_CHILDREN = (1585, 1586)

# The pull request the supersession closed, which the same write that
# hands the issue to `umbrella` stops calling this issue's.
KEY_PR_NUMBER = "pr_number"


class _FrozenPairMixin(_PatchedWorkflowMixin):
    """One issue whose record names a pair, and one tick routed over it."""

    def _frozen(
        self,
        *,
        label: str = fixing.FIXING,
        stage: str = fixing.FIXING,
        parked: bool = False,
        **recorded,
    ):
        """An issue whose record names a pair and carries no count."""
        github = FakeGitHubClient()
        issue = make_issue(ISSUE, label=label)
        github.add_issue(issue)
        if parked:
            recorded.setdefault("measurement_failure", _ANNOUNCED_STEP)
        github.seed_state(
            ISSUE,
            branch=_issue_branch(ISSUE),
            pr_number=PR_NUMBER,
            **(dict(_MEASUREMENT_PARK) if parked else {}),
            **support.recorded_generation(stage=stage, **recorded),
        )
        # Standing exactly where the record says it froze it: a head that
        # moved is its own refusal, tested beside this one.
        _open_pr_for(
            github,
            issue_number=ISSUE,
            pr_number=PR_NUMBER,
            head=FakePRRef(sha=fixing.PR_HEAD_SHA),
        )
        return github, issue

    def _route(self, github, issue, *, handled=None, **run_options):
        """Route one issue the way a tick does, reporting the handler call."""
        dispatched = Mock()
        owner_name, named = _stage_targets._STAGE_HANDLER_TARGETS[
            handled or _workflow_state.WorkflowLabel.FIXING
        ]
        run_options.setdefault("run_agent", _agent())
        with patch.object(
            importlib.import_module(owner_name), named, dispatched,
        ), patch.object(
            _worktree_paths, WORKTREE_PATH, return_value=fixing.TEMP_ROOT,
        ):
            mocks = self._run(
                lambda: _issue_processing._route_issue_to_handler(
                    github, _TEST_SPEC, issue,
                    github.workflow_label(issue),
                ),
                **run_options,
            )
        return dispatched, mocks

    def _route_to_the_stage(self, github, issue, **run_options):
        """Route one issue with the real stage handler behind the tick.

        What the mocked form cannot say: the recovery hands the handler a
        world, and whether that world is the one the crashed tick would have
        left is only answerable by letting the handler read it.
        """
        run_options.setdefault("run_agent", _agent())
        with patch.object(
            _worktree_paths, WORKTREE_PATH, return_value=fixing.TEMP_ROOT,
        ):
            return self._run(
                lambda: _issue_processing._route_issue_to_handler(
                    github, _TEST_SPEC, issue,
                    github.workflow_label(issue),
                ),
                **run_options,
            )


class FrozenPairReconciliationTest(unittest.TestCase, _FrozenPairMixin):
    """What a crash between the freeze and the count leaves, and what pays it."""

    def test_a_small_pair_publishes_and_dispatches(self) -> None:
        # The count comes back under the ceiling, so the candidate earns the
        # push the crashed tick owed -- named against the commit that was
        # measured and pinned to the head the pair froze. Only then does the
        # handler run, over the same world that tick would have handed it.
        # Every stage the gate can take an issue out of can be left holding
        # one, and the reading is the same on all five.
        for label in PUBLISHING_LABELS:
            with self.subTest(stage=label):
                github = self._frozen(label=label, stage=label)[0]

                dispatched, mocks = self._route(
                    github, github.get_issue(ISSUE), handled=label,
                )

                mocks[COUNT_ADDED_LINES].assert_called_once()
                pushed = mocks[PUSH_BRANCH].call_args
                self.assertEqual(
                    pushed.kwargs[REVISION], MEASURED_CANDIDATE_SHA,
                )
                self.assertEqual(pushed.kwargs[LEASE], fixing.PR_HEAD_SHA)
                dispatched.assert_called_once()

    def test_a_published_pair_leaves_no_debt(self) -> None:
        # The record is retired and the debt the approval named is paid by the
        # push that landed, with a receipt in its place: left standing, it
        # would freeze this branch out of the base refresh for the rest of the
        # issue's life over work the pull request already has.
        github = self._frozen()[0]

        self._route(github, github.get_issue(ISSUE))

        pinned = github.pinned_data(ISSUE)
        self.assertNotIn(KEY_CANDIDATE_SHA, pinned)
        self.assertIsNone(pinned[KEY_APPROVED_SHA])
        self.assertEqual(pinned[KEY_RECEIPT_SHA], MEASURED_CANDIDATE_SHA)
        # And the publication the push went onto, so the recovery behind this
        # one proves an identity rather than searching a branch for one.
        self.assertEqual(pinned[KEY_RECEIPT_PR], PR_NUMBER)

    def test_a_retried_pair_retires_its_park(self) -> None:
        # The park the failed reading left is durable, and no run of this tick
        # clears it: the reading IS the tick. Left standing, the source stage
        # below reads `awaiting_human` and takes its parked road -- waiting for
        # a reply to the very question this tick answered -- while the commit
        # it just approved sits unpushed.
        github, issue = self._frozen(parked=True)

        dispatched, mocks = self._route(github, issue)

        mocks[COUNT_ADDED_LINES].assert_called_once()
        dispatched.assert_called_once()
        pinned = github.pinned_data(ISSUE)
        self.assertFalse(pinned.get(AWAITING_HUMAN))
        self.assertIsNone(pinned.get(PARK_REASON))
        self.assertEqual(pinned[KEY_RECEIPT_SHA], MEASURED_CANDIDATE_SHA)

    def test_a_lost_reading_holds_the_tick(self) -> None:
        # The base object is not here and a fetch did not bring it back: the
        # transport rather than the record. The stage may not run behind that
        # -- the candidate is unmeasured and the pull request has not received
        # it -- and no human is owed anything yet, which is exactly what lets
        # the next tick re-enter this same pair, with no agent behind it and
        # no reading of the remote for a base that has moved since.
        github, issue = self._frozen()

        dispatched, mocks = self._route(
            github, issue, base_object_present=False,
        )

        dispatched.assert_not_called()
        mocks[COUNT_ADDED_LINES].assert_not_called()
        mocks[RUN_AGENT].assert_not_called()
        self.assertEqual(github.posted_comments, [])
        pinned = github.pinned_data(issue.number)
        self.assertEqual(pinned[KEY_MISS_COUNT], 1)
        self.assertEqual(pinned[KEY_CANDIDATE_SHA], MEASURED_CANDIDATE_SHA)
        self.assertFalse(pinned.get(AWAITING_HUMAN))

    def test_a_base_the_remote_finally_names_is_kept(self) -> None:
        # A park standing over the pair suppresses the second MENTION, never
        # what the reading learned. A remote that would not answer records no
        # base at all, so the pass that finally gets an id for one is what
        # gives every retry after it an exact object to ask for -- dropped
        # here, the next pass asks the remote again and freezes whatever the
        # branch has moved to since, which is a different pair under the same
        # generation.
        github, issue = self._frozen(parked=True, base_sha="")

        self._route(github, issue, frozen_base=FrozenCommit(
            sha=support.MEASURED_BASE_SHA,
            failure=support.MeasurementFailure.BASE_ABSENT,
        ))

        pinned = github.pinned_data(issue.number)
        self.assertEqual(
            pinned[support.KEY_BASE_SHA], support.MEASURED_BASE_SHA,
        )
        self.assertEqual(github.posted_comments, [])
        self.assertTrue(pinned[AWAITING_HUMAN])

    def test_an_oversized_pair_stops_the_stage(self) -> None:
        # The reading the crash interrupted is the one that says this pull
        # request may not grow, so it is answered before the handler that
        # would have grown it.
        github, issue = self._frozen()

        with patch.object(fixing.config, support.MAX_ADDED_LINES, CEILING):
            dispatched, _mocks = self._route(
                github, issue, added_lines=PAST_THE_CEILING,
            )

        dispatched.assert_not_called()
        self.assertEqual(github.label_history, [(ISSUE, LABEL_DECOMPOSING)])

    def test_a_moved_candidate_is_refused(self) -> None:
        # No developer ran on this tick, so there is no run whose output a
        # head that is not the recorded candidate could be -- it is a checkout
        # something moved, and measuring it would settle this generation on a
        # commit it was never about. The park is made durable here, because
        # nothing runs behind this to write it.
        github, issue = self._frozen()

        dispatched, mocks = self._route(
            github, issue,
            candidate_commit=FrozenCommit(sha=MOVED_CANDIDATE),
        )

        dispatched.assert_not_called()
        mocks[COUNT_ADDED_LINES].assert_not_called()
        self.assertEqual(github.label_history, [])
        pinned = github.pinned_data(ISSUE)
        self.assertEqual(pinned[KEY_CANDIDATE_SHA], MEASURED_CANDIDATE_SHA)
        self.assertEqual(pinned[PARK_REASON], PARK_MEASUREMENT_FAILED)


class AnchoredPairTest(unittest.TestCase, _FrozenPairMixin):
    """A pair an auto rebase froze on its own replay, beside its anchor."""

    def test_the_published_pair_still_holds_the_tick(self) -> None:
        # The rebase died before the count, so both records stand. The pair's
        # freeze lets the reconciliation run and its leased push lands -- but
        # the anchor is still pinned, and the handler behind would run before
        # the recovery that finalizes the replay. The tick stops there, and
        # the anchor is left for the refresh to answer.
        anchored, anchored_issue = self._frozen(
            label=ANCHORED_STAGE, stage=ANCHORED_STAGE,
        )
        self._pins_the_anchor(anchored, anchored_issue)

        stage_handler, patched = self._route(
            anchored, anchored_issue, handled=ANCHORED_STAGE,
        )

        patched[PUSH_BRANCH].assert_called_once()
        stage_handler.assert_not_called()
        self.assertEqual(
            anchored.pinned_data(ISSUE)[KEY_ANCHOR], fixing.PR_HEAD_SHA,
        )

    def test_an_oversized_generation_holds_decomposer(self) -> None:
        # Measured past the ceiling, the generation is the adjudication's to
        # decide, and the reconciliation ahead of the decomposer leaves it
        # standing -- so the anchor is asked on that road too, and the tick
        # stops before a decomposer is spawned over an unpublished replay.
        decomposing = _workflow_state.WorkflowLabel.DECOMPOSING
        oversized, oversized_issue = self._frozen(
            label=decomposing, additions=PAST_THE_CEILING,
        )
        self._pins_the_anchor(oversized, oversized_issue)

        decomposer, spawned = self._route(
            oversized, oversized_issue, handled=decomposing,
        )

        decomposer.assert_not_called()
        spawned[RUN_AGENT].assert_not_called()

    def _pins_the_anchor(self, github, issue) -> None:
        """Leave the anchor the rebase pinned before git ran."""
        state = github.read_pinned_state(issue)
        state.set(KEY_ANCHOR, fixing.PR_HEAD_SHA)
        github.write_pinned_state(issue, state)


class ParkedPairPollTest(unittest.TestCase, _FrozenPairMixin):
    """What a poll past the park still owes, and what it may not repeat."""

    def test_every_lost_reading_reaches_the_sinks(self) -> None:
        # This road re-reads the pair on every poll by design -- that is how a
        # transport coming back settles it with no human -- so the stream is
        # the only place those readings exist at all. Reported by none of
        # them, a pair nobody can measure looks exactly like one nobody is
        # looking at. What the standing park spares is the THREAD: one
        # mention, made on the poll that spent the bound.
        parked = self._frozen(parked=True)

        for poll in (1, 2, 3):
            with self.subTest(poll=poll):
                self._route(*parked, base_object_present=False)

                self.assertEqual(len(self._failures(parked[0])), poll)
                self.assertEqual(parked[0].posted_comments, [])

    def _failures(self, github) -> list:
        """The typed measurement failures both sinks were handed."""
        return [
            record for record in github.recorded_events
            if record.get("event") == support.EVENT_LATE_FAILURE
        ]


class StrandedRecordTest(unittest.TestCase, _FrozenPairMixin):
    """A pair frozen on one stage and read while the issue sits on another."""

    def test_a_record_of_another_stage_stops_the_tick(self) -> None:
        # A record entered on `fixing` and read while the issue sits somewhere
        # else belongs to a stage that has moved. It may not be re-entered
        # from here -- it would be measured under a publication it was never
        # taken on -- and the stage the label now names may not run either:
        # the candidate is unmeasured and unpushed, so `validating` would hand
        # a reviewer a head the pull request never received. Neither road is
        # this process's to pick, so the tick stops and says so once.
        for label in PUBLISHING_LABELS[1:]:
            with self.subTest(label=label):
                github = self._frozen(label=label)[0]

                dispatched, mocks = self._route(
                    github, github.get_issue(ISSUE), handled=label,
                )

                mocks[COUNT_ADDED_LINES].assert_not_called()
                dispatched.assert_not_called()
                mocks[PUSH_BRANCH].assert_not_called()
                self.assertEqual(github.label_history, [])
                pinned = github.pinned_data(ISSUE)
                self.assertTrue(pinned[AWAITING_HUMAN])
                self.assertEqual(pinned[PARK_REASON], PARK_MEASUREMENT_FAILED)
                # The pair is kept whole: the stage it was entered on is what
                # a human puts the label back to, and the commit is still the
                # one to measure.
                self.assertEqual(
                    pinned[KEY_CANDIDATE_SHA], MEASURED_CANDIDATE_SHA,
                )
                self.assertEqual(pinned[KEY_SOURCE_STAGE], fixing.FIXING)

    def test_a_stranded_record_asks_a_human_once(self) -> None:
        # The refusal is unrepairable from here, so every later poll reads the
        # same record and would file the same report. The park it already left
        # is what tells the second tick to hold quietly.
        github, issue = self._frozen(label=fixing.VALIDATING, parked=True)

        dispatched, _mocks = self._route(
            github, issue, handled=_workflow_state.WorkflowLabel.VALIDATING,
        )

        dispatched.assert_not_called()
        self.assertEqual(github.posted_comments, [])


class SettledSplitRecordTest(unittest.TestCase, _FrozenPairMixin):
    """A record whose candidate the adjudication turned into children.

    The retirement drops the measurement, because one that still answered
    "oversized" would pin `workflow:decomposing`, and keeps the publication
    group, because the umbrella re-asks it in front of every child it releases
    and every branch it deletes. What that leaves is the exact shape of a pair
    frozen and never counted -- on an issue whose label the same write moved
    to `workflow:umbrella`.
    """

    def test_a_settled_split_reaches_its_own_handler(self) -> None:
        # Without the record's own settlement answering first, the group would
        # name `fixing` while the issue is on `umbrella`, and the
        # stranded-reading refusal would hold every tick in front of the walk
        # that releases the children.
        for phase in SETTLED_SPLIT_PHASES:
            with self.subTest(phase=phase):
                github = self._settled(phase=phase)

                dispatched, mocks = self._route(
                    github, github.get_issue(ISSUE),
                    handled=_workflow_state.WorkflowLabel.UMBRELLA,
                )

                dispatched.assert_called_once()
                mocks[COUNT_ADDED_LINES].assert_not_called()
                self.assertEqual(github.posted_comments, [])
                self.assertIsNone(github.pinned_data(ISSUE).get(PARK_REASON))

    def test_a_park_standing_on_it_is_retired(self) -> None:
        # The park is durable and nothing about a settled split is a human's
        # to answer, so a flag left standing would read as waiting on one for
        # good -- and hold the branch it names out of the pre-tick base
        # refresh for just as long.
        github = self._settled(parked=True)

        dispatched, _mocks = self._route(
            github, github.get_issue(ISSUE),
            handled=_workflow_state.WorkflowLabel.UMBRELLA,
        )

        dispatched.assert_called_once()
        pinned = github.pinned_data(ISSUE)
        self.assertFalse(pinned[AWAITING_HUMAN])
        self.assertIsNone(pinned[PARK_REASON])

    def _settled(self, *, phase=_late_phases.LatePhase.CLEANING_UP, parked=False):
        """The record a split's retirement leaves, on the label it hands to.

        The measurement gone, the publication group and the ordered child
        register kept, and no `pr_number` on the issue -- the same write drops
        it, since the pull request the supersession closed carries work the
        children are replacing.
        """
        github = self._frozen(
            label=_workflow_state.WorkflowLabel.UMBRELLA, parked=parked,
        )[0]
        github.seed_state(ISSUE, **{
            **github.pinned_data(ISSUE),
            KEY_PR_NUMBER: None,
            **support.recorded_generation(
                threshold=None,
                phase=phase,
                split_children=SPLIT_CHILDREN,
            ),
        })
        return github
