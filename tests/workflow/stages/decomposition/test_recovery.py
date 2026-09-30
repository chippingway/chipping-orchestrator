# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import unittest
from types import MappingProxyType
from unittest.mock import patch

from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.late_split import lineage as _lineage
from orchestrator.workflow.stages.decomposition.replacement_lineage import PARK_LINEAGE_UNPROVED
from tests.support.fakes import (
    FakeGitHubClient,
    make_issue,
)
from tests.workflow.fixtures import (
    BACKEND_CLAUDE,
    KEY_AWAITING_HUMAN,
    KEY_PARENT_NUMBER,
    LABEL_BLOCKED,
    LABEL_DECOMPOSING,
    LABEL_UMBRELLA,
    _agent,
    _manifest,
)
from tests.workflow.stages.decomposition import (
    late_crash_support as _crash,
    replacement_lineage_support as _support,
)
from tests.workflow.stages.decomposition.decomposing_test_support import (
    _DecomposingWorkflowMixin,
)
from tests.workflow.stages.decomposition.decomposition_test_support import _seed_blocked_children

KEY_DECOMPOSER_AGENT = "decomposer_agent"
KEY_DECOMPOSER_SESSION_ID = "decomposer_session_id"
KEY_CHILDREN = "children"
KEY_UMBRELLA = "umbrella"
CLEANUP_DECOMPOSE_WORKTREE = "_cleanup_decompose_worktree"
RUN_AGENT = "run_agent"
CONFIG_DECOMPOSE = "DECOMPOSE"
DECOMPOSER_SESSION = "dec-sess"
DEV_SESSION = "dev-sess"
TRUSTED_AUTHOR = "alice"
CREATED_AT = "2026-05-03T00:00:00+00:00"
PICKUP_ISSUE_NUMBER = 10
SINGLE_DECISION_ISSUE_NUMBER = 11
CONTEXT_HANDOFF_ISSUE_NUMBER = 73
SPLIT_DECISION_ISSUE_NUMBER = 12
UMBRELLA_SPLIT_ISSUE_NUMBER = 50
NON_UMBRELLA_SPLIT_ISSUE_NUMBER = 51
DEPENDENCY_SPLIT_ISSUE_NUMBER = 13
COMMITS_PARK_ISSUE_NUMBER = 40
DIRTY_PARK_ISSUE_NUMBER = 41
MALFORMED_MANIFEST_ISSUE_NUMBER = 14
QUESTION_PARK_ISSUE_NUMBER = 15
SILENT_FAILURE_ISSUE_NUMBER = 115
RESUME_ISSUE_NUMBER = 16
FILTERED_RESUME_ISSUE_NUMBER = 17
RETRY_CAP_ISSUE_NUMBER = 18
HUMAN_REPLY_COMMENT_ID = 1100
OUTSIDER_REPLY_COMMENT_ID = 1101
PRIOR_ACTION_COMMENT_ID = 900
DISABLED_PICKUP_ISSUE_NUMBER = 19
DISABLED_LABELED_ISSUE_NUMBER = 20
DISABLED_RATCHET_ISSUE_NUMBER = 21
RATCHET_FIRST_COMMENT_ID = 950
RATCHET_LATEST_COMMENT_ID = 960
DISABLED_MONOTONIC_ISSUE_NUMBER = 22
OLDER_COMMENT_ID = 500
PRESERVED_HIGH_WATERMARK = 10000
HALF_COMPLETE_DISABLED_PARENT_NUMBER = 50
RECOVERY_CHILD_NUMBERS = (101, 102)
PERSISTENCE_ISSUE_NUMBER = 80
COMPLETE_RECOVERY_PARENT_NUMBER = 50
AWAITING_RECOVERY_PARENT_NUMBER = 51
AWAITING_RECOVERY_CHILD_NUMBER = 201
PARTIAL_RECOVERY_PARENT_NUMBER = 52
ORPHAN_RECOVERY_PARENT_NUMBER = 53
ORPHAN_REPAIR_PARENT_NUMBER = 60
HEALTHY_CHILD_NUMBER = 601
ORPHAN_CHILD_NUMBER = 602
STALE_PARK_COMMENT_ID = 999
EXPECTED_COUNT_ORDER_ISSUE_NUMBER = 82
CHILD_STATE_ORDER_ISSUE_NUMBER = 83
WORKTREE_ISSUE_NUMBER = 70
DIRTY_WORKTREE_ISSUE_NUMBER = 71
AWAITING_WORKTREE_ISSUE_NUMBER = 73
NON_STRING_RATIONALE_ISSUE_NUMBER = 72
FRESH_USAGE_ISSUE_NUMBER = 620
RESUMED_USAGE_ISSUE_NUMBER = 621
NO_COMMENT_USAGE_ISSUE_NUMBER = 622
INTERRUPTED_USAGE_ISSUE_NUMBER = 623
DIRTY_INTERRUPTED_USAGE_ISSUE_NUMBER = 624

SINGLE_MANIFEST_PAYLOAD = '{"decision": "single", "rationale": "fits"}'
SPLIT_MANIFEST = _manifest(
    '{"decision": "split", "children": [{"title": "A", "body": "a"},{"title": "B", "body": "b"}]}'
)
READ_ONLY_FRAGMENT = "read-only"
IMPLEMENTED_MESSAGE = "implemented"
PARK_DECOMPOSITION_CRASH = "decomposition_crash"
# An issue that is not the replacement's parent, which a foreign link names.
_OTHER_PARENT = 999
# What a pinned comment that would not parse reads back as.
_UNPARSED = PinnedState(comment_id=1, parsed=False)


def _orphan_recovery_fixture():
    github = FakeGitHubClient()
    parent = make_issue(
        ORPHAN_REPAIR_PARENT_NUMBER,
        label=LABEL_DECOMPOSING,
    )
    github.add_issue(parent)
    for child_number in (HEALTHY_CHILD_NUMBER, ORPHAN_CHILD_NUMBER):
        github.add_issue(make_issue(child_number, label=LABEL_BLOCKED))
    github.seed_state(
        HEALTHY_CHILD_NUMBER,
        parent_number=ORPHAN_REPAIR_PARENT_NUMBER,
        created_at=CREATED_AT,
    )
    github.seed_state(
        ORPHAN_CHILD_NUMBER,
        awaiting_human=True,
        park_reason=None,
        last_action_comment_id=STALE_PARK_COMMENT_ID,
    )
    github.seed_state(
        ORPHAN_REPAIR_PARENT_NUMBER,
        children=[HEALTHY_CHILD_NUMBER, ORPHAN_CHILD_NUMBER],
        expected_children_count=2,
        decomposed_at=CREATED_AT,
        decomposer_agent=BACKEND_CLAUDE,
        decomposer_session_id=DECOMPOSER_SESSION,
    )
    return github, parent


class DecompositionRecoveryTest(
    unittest.TestCase,
    _DecomposingWorkflowMixin,
):
    def test_half_finished_recovery_flips_to_blocked(self) -> None:
        # Simulate: a prior tick created+persisted children but crashed
        # before flipping the parent label from `decomposing` to
        # `blocked`. The next tick must NOT re-spawn the decomposer
        # (would create duplicate children); it must finalize the parent
        # transition. The parent's `_handle_blocked` activates no-dep
        # children on a subsequent tick.
        gh = FakeGitHubClient()
        issue = make_issue(COMPLETE_RECOVERY_PARENT_NUMBER, label=LABEL_DECOMPOSING)
        gh.add_issue(issue)
        # Children already exist on GitHub with `parent_number` seeded --
        # the crash happened AFTER both child seeds, between the parent's
        # last incremental write and the parent label flip.
        _seed_blocked_children(
            gh,
            COMPLETE_RECOVERY_PARENT_NUMBER,
            RECOVERY_CHILD_NUMBERS,
        )
        gh.seed_state(
            COMPLETE_RECOVERY_PARENT_NUMBER,
            children=list(RECOVERY_CHILD_NUMBERS),
            decomposed_at=CREATED_AT,
            decomposer_agent=BACKEND_CLAUDE,
            decomposer_session_id=DECOMPOSER_SESSION,
        )

        mocks = self._run_decomposing(
            gh,
            issue,
            run_agent=_agent(),
        )

        # Decomposer was NOT respawned; no new children were created.
        mocks[RUN_AGENT].assert_not_called()
        self.assertEqual(gh.created_child_issues, [])
        self.assertIn(
            (COMPLETE_RECOVERY_PARENT_NUMBER, LABEL_BLOCKED),
            gh.label_history,
        )
        # Children + decomposed_at preserved.
        self.assertEqual(
            gh.pinned_data(COMPLETE_RECOVERY_PARENT_NUMBER).get(KEY_CHILDREN),
            list(RECOVERY_CHILD_NUMBERS),
        )

    def test_half_complete_awaiting_human_holds(self) -> None:
        # If the prior tick parked awaiting_human after partial child
        # creation, the recovery must NOT silently flip the parent to
        # `blocked`; the human's intervention is still required.
        gh = FakeGitHubClient()
        issue = make_issue(AWAITING_RECOVERY_PARENT_NUMBER, label=LABEL_DECOMPOSING)
        gh.add_issue(issue)
        gh.seed_state(
            AWAITING_RECOVERY_PARENT_NUMBER,
            children=[AWAITING_RECOVERY_CHILD_NUMBER],
            awaiting_human=True,
            decomposer_agent=BACKEND_CLAUDE,
            decomposer_session_id=DECOMPOSER_SESSION,
        )

        mocks = self._run_decomposing(
            gh,
            issue,
            run_agent=_agent(),
        )

        mocks[RUN_AGENT].assert_not_called()
        self.assertEqual(gh.created_child_issues, [])
        # Label NOT flipped; human still owns it.
        self.assertNotIn(
            (AWAITING_RECOVERY_PARENT_NUMBER, LABEL_BLOCKED),
            gh.label_history,
        )
        self.assertTrue(gh.pinned_data(AWAITING_RECOVERY_PARENT_NUMBER).get(KEY_AWAITING_HUMAN))

    def test_partial_children_recovery_parks(self) -> None:
        # SIGKILL between iterations leaves a partial `children` list
        # that the half-finished recovery used to silently treat as
        # complete -- stranding any un-created dependents and never
        # creating the missing children. With `expected_children_count`
        # persisted up-front, the recovery distinguishes partial from
        # complete and parks awaiting human.
        gh = FakeGitHubClient()
        issue = make_issue(PARTIAL_RECOVERY_PARENT_NUMBER, label=LABEL_DECOMPOSING)
        gh.add_issue(issue)
        gh.seed_state(
            PARTIAL_RECOVERY_PARENT_NUMBER,
            children=[RECOVERY_CHILD_NUMBERS[0]],
            expected_children_count=3,
            decomposed_at=CREATED_AT,
            decomposer_agent=BACKEND_CLAUDE,
            decomposer_session_id=DECOMPOSER_SESSION,
        )

        mocks = self._run_decomposing(
            gh,
            issue,
            run_agent=_agent(),
        )

        mocks[RUN_AGENT].assert_not_called()
        self.assertEqual(gh.created_child_issues, [])
        # Parked, not finalized to blocked.
        self.assertNotIn(
            (PARTIAL_RECOVERY_PARENT_NUMBER, LABEL_BLOCKED),
            gh.label_history,
        )
        state = gh.pinned_data(PARTIAL_RECOVERY_PARENT_NUMBER)
        self.assertTrue(state.get(KEY_AWAITING_HUMAN))
        last_comment = gh.posted_comments[-1][1]
        self.assertIn("crashed mid-way", last_comment)
        self.assertIn("1 of 3", last_comment)

    def test_orphan_recovery_parks_without_children(
        self,
    ) -> None:
        # SIGKILL between `create_child_issue` returning and the parent's
        # incremental `children` write leaves the parent with
        # `expected_children_count` set but zero recorded children, while
        # an orphan child issue exists on GitHub. The previous recovery
        # branch only fired when `state.get("children")` was truthy, so
        # this case fell through, the decomposer was respawned, and a
        # different manifest produced duplicate child issues alongside
        # the orphan.
        gh = FakeGitHubClient()
        issue = make_issue(ORPHAN_RECOVERY_PARENT_NUMBER, label=LABEL_DECOMPOSING)
        gh.add_issue(issue)
        gh.seed_state(
            ORPHAN_RECOVERY_PARENT_NUMBER,
            expected_children_count=2,
            decomposer_agent=BACKEND_CLAUDE,
            decomposer_session_id=DECOMPOSER_SESSION,
        )

        mocks = self._run_decomposing(
            gh,
            issue,
            run_agent=_agent(),
        )

        mocks[RUN_AGENT].assert_not_called()
        self.assertEqual(gh.created_child_issues, [])
        self.assertNotIn(
            (ORPHAN_RECOVERY_PARENT_NUMBER, LABEL_BLOCKED),
            gh.label_history,
        )
        state = gh.pinned_data(ORPHAN_RECOVERY_PARENT_NUMBER)
        self.assertTrue(state.get(KEY_AWAITING_HUMAN))
        last_comment = gh.posted_comments[-1][1]
        self.assertIn("crashed mid-way", last_comment)
        self.assertIn("0 of 2", last_comment)

    def test_orphan_recovery_seeds_parent_number(self) -> None:
        # SIGKILL between the parent's child-record write and the child's
        # pinned-state seed for the LAST child satisfies
        # `len(children) == expected_children_count` but leaves that child
        # orphaned (label=blocked, no `parent_number`). A prior
        # `_handle_blocked` tick may have already parked the orphan as
        # "manual relabel suspected" with `awaiting_human=True`. Without
        # repair, recovery finalizes the parent to `blocked`, the parent's
        # walk later flips the orphan to `ready`, and
        # `_handle_implementing` reads the stale park and sits waiting on
        # a human reply that never comes.
        gh, parent = _orphan_recovery_fixture()

        mocks = self._run_decomposing(
            gh,
            parent,
            run_agent=_agent(),
        )

        mocks[RUN_AGENT].assert_not_called()
        self.assertEqual(gh.created_child_issues, [])
        self.assertIn(
            (ORPHAN_REPAIR_PARENT_NUMBER, LABEL_BLOCKED),
            gh.label_history,
        )
        # Orphan got parent_number seeded and stale park cleared.
        orphan_state = gh.pinned_data(ORPHAN_CHILD_NUMBER)
        self.assertEqual(
            orphan_state.get(KEY_PARENT_NUMBER),
            ORPHAN_REPAIR_PARENT_NUMBER,
        )
        self.assertFalse(orphan_state.get(KEY_AWAITING_HUMAN))
        # Healthy child untouched.
        self.assertEqual(
            gh.pinned_data(HEALTHY_CHILD_NUMBER).get(KEY_PARENT_NUMBER),
            ORPHAN_REPAIR_PARENT_NUMBER,
        )


def _written(ancestry, **edits) -> dict:
    """The pinned fields one ancestry is written as, `edits` landing over them."""
    recorded = PinnedState()
    _lineage.write_late_ancestry(recorded, ancestry)
    return {**recorded.data, **edits}


# What a recorded child may carry that the crashed split did not seed: part of
# the group, a field its reader would drop, a whole group naming another
# lineage, and a link to another parent -- beside the owed ancestry, or alone.
_FOREIGN_SEEDS = MappingProxyType({
    "part of the group": MappingProxyType({"late_ancestry_depth": 1}),
    "a field its reader would drop": MappingProxyType(
        _written(_support.ROOT_REPLACEMENT, late_ancestry_generation="first"),
    ),
    "another lineage": MappingProxyType(_written(_support.cut_from_ancestor())),
    "another parent beside the owed ancestry": MappingProxyType(
        _written(_support.ROOT_REPLACEMENT, **{KEY_PARENT_NUMBER: _OTHER_PARENT}),
    ),
    "another parent and no ancestry": MappingProxyType({KEY_PARENT_NUMBER: _OTHER_PARENT}),
})


class _DiesSeedingAChild:
    """A process that dies at the first write to a child's pinned comment.

    The parent's own writes land, which is what puts the child in `children`
    and on the consumer ledger: the crash is the one between that record and
    the seed.
    """

    def __init__(self, client) -> None:
        self._wrote = client.write_pinned_state

    def __call__(self, issue, state):
        if issue.number != _support.PARENT:
            raise KeyboardInterrupt("seed")
        return self._wrote(issue, state)


class _ReplacementRecoveryCase(unittest.TestCase):
    """A split inside a late lineage, interrupted, and the tick that recovers it.

    The parent is the root of the lineage its own split started, holding the
    snapshot that split preserved; the decomposer answered with one
    replacement.
    """

    def setUp(self) -> None:
        github, issue = _support.late_parent(_support.own_split())
        self.github = github
        self.issue = issue

    def _die_seeding(self) -> int:
        """Run the split into the crash between its parent record and its seed.

        Reports the child it left: recorded, protected, and seeded with
        nothing at all.
        """
        dying = patch.object(self.github, "write_pinned_state", _DiesSeedingAChild(self.github))
        with dying, self.assertRaises(KeyboardInterrupt):
            _support.redecompose(self.github, self.issue, _support.ONE_REPLACEMENT_MANIFEST)
        child = _support.replacements(self.github)[0]
        self.assertIn(child, _support.consumers(self.github))
        self.assertEqual(self.github.pinned_data(child), {})
        return child

    def _recover(self) -> None:
        """The next decomposing tick, which a recovery answers without the decomposer."""
        _support.redecompose(self.github, self.issue)[RUN_AGENT].assert_not_called()

    def _unprotect(self) -> None:
        """Take every replacement back off the parent's consumer ledger."""
        unprotected = {**self.github.pinned_data(_support.PARENT), _support.KEY_CONSUMERS: [_support.ORIGINAL]}
        self.github.seed_state(_support.PARENT, **unprotected)

    def _seeded(self, child: int):
        """The ancestry one child's pinned comment records."""
        return _lineage.read_late_ancestry(self.github.read_pinned_state(self.github.get_issue(child)))

    def _labels(self, child: int) -> tuple:
        """Where the parent and one of its children stand."""
        return (
            self.github.workflow_label(self.issue),
            self.github.workflow_label(self.github.get_issue(child)),
        )


class ReplacementCrashTest(_ReplacementRecoveryCase):
    """A split a crash interrupted is repaired to its lineage before anything starts."""

    def test_a_deferred_seed_is_repaired_first(self) -> None:
        child = self._die_seeding()

        self._recover()

        self.assertEqual(_support.replacements(self.github), [child])
        self.assertEqual(self._seeded(child), _support.ROOT_REPLACEMENT)
        self.assertEqual(self.github.pinned_data(child)[KEY_PARENT_NUMBER], _support.PARENT)
        # Finalized only once repaired; the walk that starts it comes later.
        self.assertEqual(self._labels(child), (LABEL_UMBRELLA, LABEL_BLOCKED))

    def test_an_unprotected_child_gets_no_pointer(self) -> None:
        # Recorded by a split that never put it on the ledger: the lineage is
        # still owed to it, and a pointer nothing keeps is not.
        child = self._die_seeding()
        self._unprotect()

        self._recover()

        self.assertEqual(self._seeded(child), _support.ROOT_LINEAGE)
        self.assertEqual(_support.consumers(self.github), [_support.ORIGINAL])

    def test_an_unproved_lineage_is_not_finalized(self) -> None:
        # The record the split was proved on no longer proves it: a stray
        # ancestry key with no parent beside it.
        child = self._die_seeding()
        damaged = {**self.github.pinned_data(_support.PARENT), "late_ancestry_depth": 1}
        self.github.seed_state(_support.PARENT, **damaged)

        self._recover()

        self.assertEqual(self.github.pinned_data(child), {})
        self.assertEqual(self._labels(child), (LABEL_DECOMPOSING, LABEL_BLOCKED))
        self.assertEqual(_support.parks(self.github), [PARK_LINEAGE_UNPROVED])

    def test_an_unrecorded_child_is_never_started(self) -> None:
        # The crash before the parent record: the child exists, and nothing
        # on the parent names it -- not `children`, and not the ledger.
        with _crash.killed_after(self.github, "create_child_issue"), self.assertRaises(KeyboardInterrupt):
            _support.redecompose(self.github, self.issue, _support.ONE_REPLACEMENT_MANIFEST)
        orphan = _support.replacements(self.github)[0]

        self._recover()

        self.assertEqual(_support.consumers(self.github), [_support.ORIGINAL])
        self.assertEqual(self.github.pinned_data(orphan), {})
        self.assertEqual(self._labels(orphan), (LABEL_DECOMPOSING, LABEL_BLOCKED))
        self.assertEqual(_support.parks(self.github), [PARK_DECOMPOSITION_CRASH])


class RecordedSeedTest(_ReplacementRecoveryCase):
    """A child the crashed split recorded is held to the ancestry it was owed.

    What it already carries is asked about before anything is written to it
    or the split is finalized: only the seed it was owed, whole, lets it
    through as it stands.
    """

    def test_a_whole_seed_is_left_as_owed(self) -> None:
        # The seed landed and the finalize did not.
        child = self._die_seeding()
        self.github.seed_state(child, **_written(_support.ROOT_REPLACEMENT))

        self._recover()

        self.assertEqual(self._seeded(child), _support.ROOT_REPLACEMENT)
        self.assertEqual(self._labels(child), (LABEL_UMBRELLA, LABEL_BLOCKED))

    def test_an_unprotected_pointer_is_dropped(self) -> None:
        # The seed landed with its pointer, and the ledger that protected it
        # no longer names the child: the lineage stands, and the pointer goes
        # with the ordering stamp that was a claim about it.
        child = self._die_seeding()
        self.github.seed_state(child, **_written(_support.ROOT_REPLACEMENT))
        self._unprotect()

        self._recover()

        self.assertEqual(self._seeded(child), _support.ROOT_LINEAGE)
        self.assertEqual(_support.consumers(self.github), [_support.ORIGINAL])
        self.assertEqual(self._labels(child), (LABEL_UMBRELLA, LABEL_BLOCKED))

    def test_a_foreign_ancestry_is_never_finalized(self) -> None:
        for shape, carried in _FOREIGN_SEEDS.items():
            with self.subTest(shape=shape):
                self.setUp()
                child = self._die_seeding()
                self.github.seed_state(child, **carried)

                self._recover()

                self.assertEqual(self.github.pinned_data(child), dict(carried))
                self.assertEqual(self._labels(child), (LABEL_DECOMPOSING, LABEL_BLOCKED))
                self.assertEqual(_support.parks(self.github), [PARK_LINEAGE_UNPROVED])
                self.assertIn(f"#{child}", self.github.posted_comments[-1][1])

    def test_an_unreadable_seed_is_never_finalized(self) -> None:
        # Nothing on it can be checked, and a seed written over it would take
        # whatever it carried with it.
        child = self._die_seeding()

        with patch.object(self.github, "read_pinned_state", side_effect=self._reads_unparsed(child)):
            self._recover()

        self.assertEqual(self.github.pinned_data(child), {})
        self.assertEqual(self._labels(child), (LABEL_DECOMPOSING, LABEL_BLOCKED))
        self.assertEqual(_support.parks(self.github), [PARK_LINEAGE_UNPROVED])

    def _reads_unparsed(self, child: int):
        """The client's pinned read, answering for `child` with a comment that would not parse."""
        read = self.github.read_pinned_state
        return lambda issue: _UNPARSED if issue.number == child else read(issue)
