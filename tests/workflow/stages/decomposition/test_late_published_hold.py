# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The hold an overflow entered PAST publication puts on its own pull request.

The plan side of the same owner is in `test_late_hold.py`. What differs here
is which pull request is marked and what proves it may be: the entry the gate
froze names the implementation pull request the work is already on, so nothing
is looked up and no provenance is derived from a head. What the head IS for is
recorded beside the body -- the reading that says which change wore the
notice, kept apart from the published head a settlement pins its push to.
"""
from __future__ import annotations

import unittest
from unittest.mock import patch

from orchestrator.workflow.stages.decomposition import late_hold as _late_hold
from orchestrator.workflow.stages.decomposition.late_models import (
    _LateDisposition,
)
from tests.support.fakes import FakeGitHubClient
from tests.workflow.stages.decomposition import late_test_support as _support
from tests.workflow.stages.decomposition.late_published_support import (
    published_generation,
    seed_published_pr,
)
from tests.workflow.stages.decomposition.late_recorder_support import (
    HoldSnapshot,
)
from tests.workflow.stages.decomposition.late_run_support import (
    adjudicate,
    agent_reply,
)

# Whichever pull request the issue records, which a publication has already
# moved onto the implementation one by the time a crossed hold is reached.
KEY_PR_NUMBER = "pr_number"

CLOSED = "closed"

EDIT_PR_BODY = "edit_pr_body"

WORKFLOW_LOG = "orchestrator.workflow"

INFO_LEVEL = "INFO"

ERROR_LEVEL = "ERROR"

# What the notice on an already-published pull request has to say, and the
# clause it must not: the work on it reached the remote long before the hold,
# so what the adjudication stands in front of is the push, not a publication.
PENDING_PUSH_CLAUSE = "before that commit is pushed onto it"

UNPUBLISHED_CLAUSE = "adjudicated before anything is published"


class _PublishedHoldCase(unittest.TestCase):
    """One issue whose oversized candidate is already on a pull request."""

    def setUp(self) -> None:
        self.github = FakeGitHubClient()
        self.generation = published_generation()
        self.issue = _support.seed_late_issue(
            self.github, self.generation, pr_number=_support.PUBLISHED_PR_NUMBER,
        )
        self.published_pr = seed_published_pr(self.github)

    def _reconcile(self, generation=None):
        return _late_hold._reconcile_hold(
            self.github,
            self.issue,
            self.github.read_pinned_state(self.issue),
            self.generation if generation is None else generation,
        )

    def _pinned(self) -> dict:
        return self.github.pinned_data(_support.LATE_ISSUE_NUMBER)


class PublishedPrHoldTest(_PublishedHoldCase):
    """What the entry names is what wears the notice, and what is recorded."""

    def test_the_recorded_implementation_pr_is_held(self) -> None:
        # Nothing on this issue says the pull request is a plan, and nothing
        # needs to: the entry says the candidate was measured against it, so
        # the notice goes on it and the description it replaced is preserved.
        published_body = self.published_pr.body

        hold = self._reconcile()

        self.assertTrue(hold.held)
        self.assertEqual(hold.generation.plan_pr_number, _support.PUBLISHED_PR_NUMBER)
        self.assertEqual(hold.generation.plan_pr_body, published_body)
        self.assertIn(_support.HOLD_MARKER_PREFIX, self.published_pr.body)

    def test_the_notice_names_the_pending_push(self) -> None:
        # The work on this pull request was published a while ago, so a notice
        # telling its author their change is being held "before anything is
        # published" describes a change that is not theirs. What the
        # adjudication actually stands in front of is the commit's push.
        self._reconcile()

        self.assertIn(PENDING_PUSH_CLAUSE, self.published_pr.body)
        self.assertNotIn(UNPUBLISHED_CLAUSE, self.published_pr.body)

    def test_the_marked_head_is_recorded_first(self) -> None:
        # The identity, the head, and the body go down in one write before
        # the edit: a later tick holding only the identity could not say
        # which change wore the notice.
        recorder = HoldSnapshot(self.github)

        with patch.object(self.github, EDIT_PR_BODY, recorder):
            hold = self._reconcile()

        self.assertEqual(hold.generation.plan_pr_head, _support.PUBLISHED_HEAD_SHA)
        self.assertEqual(
            [held.get(_support.KEYS.plan_pr_head) for held in recorder.snapshots],
            [_support.PUBLISHED_HEAD_SHA],
        )

    def test_the_published_head_is_left_alone(self) -> None:
        # The hold records what it READ; the entry records what the gate
        # proved. A pull request somebody pushed to between the two is marked
        # over its current tip, and re-stamping the entry from that reading
        # would move the evidence a settlement pins its push to.
        self.published_pr.head.sha = _support.OTHER_SHA

        hold = self._reconcile()

        self.assertEqual(hold.generation.plan_pr_head, _support.OTHER_SHA)
        self.assertEqual(hold.generation.published_sha, _support.PUBLISHED_HEAD_SHA)
        self.assertEqual(
            self._pinned().get(_support.KEYS.published_sha), _support.PUBLISHED_HEAD_SHA,
        )

    def test_a_moved_head_changes_nothing(self) -> None:
        # An adjudication runs for as long as an agent takes, and a push
        # underneath leaves the same pull request on a different commit. The
        # notice is about a change a human could merge, so it stands, the
        # recorded reading is kept, and the movement is reported.
        first = self._reconcile()
        self.published_pr.head.sha = _support.OTHER_SHA

        with self.assertLogs(WORKFLOW_LOG, level=INFO_LEVEL):
            second = self._reconcile(first.generation)

        self.assertTrue(second.held)
        self.assertEqual(second.generation.plan_pr_head, _support.PUBLISHED_HEAD_SHA)
        self.assertEqual(len(self.github.edited_pr_bodies), 1)


class PublishedHoldBoundaryTest(_PublishedHoldCase):
    """What the entry does not decide: a settled pull request, and a retry."""

    def test_a_settled_implementation_pr_is_not_held(self) -> None:
        # A human who merged or closed it decided something about that pull
        # request and nothing about the commit under adjudication.
        self.published_pr.state = CLOSED

        hold = self._reconcile()

        self.assertFalse(hold.held)
        self.assertFalse(hold.failed)
        self.assertEqual(self.github.edited_pr_bodies, [])
        self.assertIsNone(hold.generation.plan_pr_number)

    def test_a_stale_hold_moves_to_the_entry(self) -> None:
        # A generation re-measured past its own push is adjudicating the
        # change on the published pull request. A notice left on the plan one
        # marks nothing while the change a human could merge carries none, so
        # the first is restored and the second marked -- in that order, since
        # the record holds one identity and one preserved body.
        held = self._crossed_hold()

        hold = self._reconcile(held)

        self.assertTrue(hold.held)
        self.assertEqual(hold.generation.plan_pr_number, _support.PUBLISHED_PR_NUMBER)
        self.assertEqual(self.plan_pr.body, _support.PLAN_PR_BODY)
        self.assertIn(_support.HOLD_MARKER_PREFIX, self.published_pr.body)

    def test_a_stale_hold_nothing_can_release_parks(self) -> None:
        # The preserved body is the only copy of the plan PR's description,
        # so a second hold taken before it is back would destroy it. Nothing
        # is marked and the caller parks instead.
        held = self._crossed_hold()
        published_body = self.published_pr.body

        with (
            patch.object(self.github, EDIT_PR_BODY, side_effect=RuntimeError),
            self.assertLogs(WORKFLOW_LOG, level=ERROR_LEVEL),
        ):
            hold = self._reconcile(held)

        self.assertTrue(hold.failed)
        self.assertFalse(hold.held)
        self.assertEqual(hold.generation.plan_pr_number, _support.PLAN_PR_NUMBER)
        self.assertEqual(self.published_pr.body, published_body)

    def test_a_crossed_spelling_is_ours_and_rewritten(self) -> None:
        # A record can cross publication mid-cycle: guidance resumes the
        # developer, their push lands, and the re-measurement enters the gate
        # past it. Both current spellings are ours, so the notice already
        # standing is rewritten in the side the record now names -- read as a
        # human's words it would park the issue displaced instead, with a
        # "do not merge" nothing would ever take back off.
        held = published_generation(
            plan_pr_number=_support.PUBLISHED_PR_NUMBER,
            plan_pr_head=_support.PUBLISHED_HEAD_SHA,
            plan_pr_body=_support.PLAN_PR_BODY,
        )
        self.published_pr.body = _late_hold._unpublished_hold_body(held)

        hold = self._reconcile(held)

        self.assertTrue(hold.held)
        self.assertFalse(hold.displaced)
        self.assertEqual(self.published_pr.body, _late_hold._hold_body(held))

    def test_the_release_restores_its_body(self) -> None:
        # The same release the plan side runs, on the pull request this cycle
        # actually marked: the record names it, and the body it displaced is
        # written back over the notice.
        published_body = self.published_pr.body
        first = self._reconcile()

        release = _late_hold._release_hold(
            self.github, self.issue, first.generation,
        )

        self.assertFalse(release.failed)
        self.assertEqual(self.published_pr.body, published_body)

    def _crossed_hold(self):
        """This cycle holding the plan PR, re-entered past publication.

        What guidance buys reaches it: the hold went on before the first push,
        the developer was resumed, their push landed, and the re-measurement
        entered the gate on the pull request the work is now on.
        """
        self.plan_pr = _support.seed_plan_pr(self.github)
        held = published_generation(
            plan_pr_number=_support.PLAN_PR_NUMBER,
            plan_pr_head=self.plan_pr.head.sha,
            plan_pr_body=_support.PLAN_PR_BODY,
        )
        self.plan_pr.body = _late_hold._unpublished_hold_body(held)
        return held


class _BodiesAtSpawn:
    """What each pull request carried the moment the agent was started.

    The order is only visible from inside the spawn: a hold reconciled after
    it, or released by the settlement behind it, would leave the same bodies
    behind by the time a test looked.
    """

    def __init__(self, github, agent_result) -> None:
        self.bodies: list[dict] = []
        self._github = github
        self._agent_result = agent_result

    def __call__(self, *_called, **_options):
        self.bodies.append({
            number: self._github.get_pr(number).body
            for number in (_support.PLAN_PR_NUMBER, _support.PUBLISHED_PR_NUMBER)
        })
        return self._agent_result


class PublishedHoldBeforeSpawnTest(_PublishedHoldCase):
    """The whole tick, proving which pull request wears the notice at spawn.

    The hold is what stops a human merging a change while the question of
    whether it should exist as one issue is still open, so the change under
    adjudication has to be the one marked BEFORE an agent starts under it.
    """

    def test_the_implementation_pr_is_held_at_spawn(self) -> None:
        # A generation that crossed publication mid-cycle: the plan PR was
        # marked before the push and the entry names the implementation one
        # after it. Starting a decomposer with the notice still on the plan PR
        # leaves the change a human could merge carrying nothing at all.
        self._seed_crossed_hold()
        watched = _BodiesAtSpawn(self.github, agent_reply(_support.SPLIT_REPLY))

        outcome, spawn = adjudicate(self.github, self.issue, watched)

        spawn.assert_called_once()
        self.assertNotEqual(outcome.disposition, _LateDisposition.PARKED)
        self.assertIn(_support.HOLD_MARKER_PREFIX, watched.bodies[0][_support.PUBLISHED_PR_NUMBER])
        self.assertEqual(watched.bodies[0][_support.PLAN_PR_NUMBER], _support.PLAN_PR_BODY)

    def test_an_immovable_hold_spawns_nothing(self) -> None:
        # The notice cannot be moved, so no agent runs under a pull request
        # nothing on it says is being adjudicated.
        self._seed_crossed_hold()
        refused = patch.object(
            self.github, EDIT_PR_BODY, side_effect=RuntimeError,
        )

        with refused, self.assertLogs(WORKFLOW_LOG, level=ERROR_LEVEL):
            outcome, spawn = adjudicate(self.github, self.issue)

        self.assertEqual(outcome.disposition, _LateDisposition.PARKED)
        spawn.assert_not_called()

    def _seed_crossed_hold(self) -> None:
        """Re-seed this issue holding the plan PR it marked before the push."""
        plan_pr = _support.seed_plan_pr(self.github)
        held = published_generation(
            plan_pr_number=_support.PLAN_PR_NUMBER,
            plan_pr_head=plan_pr.head.sha,
            plan_pr_body=_support.PLAN_PR_BODY,
        )
        plan_pr.body = _late_hold._unpublished_hold_body(held)
        self.github.seed_state(
            _support.LATE_ISSUE_NUMBER,
            **{
                **_support.generation_state(held),
                KEY_PR_NUMBER: _support.PUBLISHED_PR_NUMBER,
            },
        )


if __name__ == "__main__":
    unittest.main()
