# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The seed an ordinary split owes each child it creates, written under the child's own claim.

A child is dispatchable the moment its create returns, so the seed is written
under the child's writer claim, off the child's record read behind that claim
and held to admission. A genuinely fresh child is given its first record,
stamped with the supported version; one another poller pinned first is added
to, the hold its missing seed earned lifted; and one whose record admission
refuses is written nothing at all and left unseeded, so the split publishes no
summary, finalize, or release on it, and its recovery waits for a record
admission takes before it does. A seed write that fails parks the parent naming
the child and gives that claim back, so the child is not left held by a split
that has stopped writing it.
"""
from __future__ import annotations

import unittest
from types import MappingProxyType
from unittest.mock import patch

from orchestrator.workflow.stages.decomposition import child_creation as _child_creation
from orchestrator.workflow.stages.decomposition.models import _SplitPlan
from tests.support.fakes import FakeGitHubClient, make_issue
from tests.support.writer_claims import claimable
from tests.workflow.fixtures import (
    KEY_AWAITING_HUMAN,
    KEY_PARENT_NUMBER,
    LABEL_BLOCKED,
    LABEL_DECOMPOSING,
    _agent,
    _manifest,
)
from tests.workflow.stages.decomposition import child_claim_test_support as _support
from tests.workflow.stages.decomposition.decomposing_test_support import _DecomposingWorkflowMixin

_PARENT = 96

KEY_PARK_REASON = "park_reason"

KEY_CHILDREN = "children"

KEY_SCHEMA_VERSION = "schema_version"

RUN_AGENT = "run_agent"

# The hold the dispatcher puts on a child whose seed is missing.
_UNSEEDED_HOLD = "replacement_lineage_unproved"

# What every split summary opens with.
_SUMMARY = ":bookmark_tabs: decomposer split this into"

# Three slices, none waiting on another, and one slice alone.
_THREE_SLICES = _manifest(
    '{"decision": "split", "children": ['
    '{"title": "A", "body": "a", "depends_on": []}, '
    '{"title": "B", "body": "b", "depends_on": []}, '
    '{"title": "C", "body": "c", "depends_on": []}]}'
)

_ONE_SLICE = _manifest('{"decision": "split", "children": [{"title": "A", "body": "a", "depends_on": []}]}')

# What another poller pinned on the second child first: the hold on a seed
# that has not landed yet, in the supported version.
_HELD = MappingProxyType({KEY_SCHEMA_VERSION: 1, KEY_AWAITING_HUMAN: True, KEY_PARK_REASON: _UNSEEDED_HOLD})

# What a seed leaves on a child admission takes: the supported version, which
# a genuinely fresh child's first record is stamped with, and the parent link.
_LINKED = MappingProxyType({KEY_SCHEMA_VERSION: 1, KEY_PARENT_NUMBER: _PARENT})

# What the hold leaves once a seed lifts it.
_LIFTED = MappingProxyType({**_LINKED, KEY_AWAITING_HUMAN: False, KEY_PARK_REASON: None})

# What a refused child carries, under each version admission refuses: the
# same hold, and no parent link.
_REFUSED = MappingProxyType({
    shape: MappingProxyType({**version, KEY_AWAITING_HUMAN: True, KEY_PARK_REASON: _UNSEEDED_HOLD})
    for shape, version in _support.UNADMITTED.items()
})


class ClaimedSeedTest(unittest.TestCase):
    """A `decomposing` parent about to create its one slice."""

    def setUp(self) -> None:
        self.github = FakeGitHubClient()
        self.parent = make_issue(_PARENT, label=LABEL_DECOMPOSING)
        self.github.add_issue(self.parent)

    def test_a_failed_seed_gives_the_claim_back(self) -> None:
        refused = _support.RefusedWrite(self.github, self.github.write_pinned_state, _PARENT)
        plan = _SplitPlan.start([{"title": "first slice", "body": "do the first part"}], is_umbrella=False)
        state = self.github.read_pinned_state(self.parent)

        with patch.object(self.github, "write_pinned_state", refused), self.assertLogs(_support.WORKFLOW_LOG):
            seeded = _child_creation._create_planned_child(self.github, self.parent, state, plan, 0)

        first = self.github.created_child_issues[0].number
        self.assertFalse(seeded)
        self.assertEqual(refused.claimable_during, [False], "the seed is written under the child's claim")
        self.assertTrue(self.github.pinned_data(_PARENT)[KEY_AWAITING_HUMAN], "the parent is parked naming it")
        self.assertTrue(claimable(self.github.repo_id, first), "and the child's claim is given back")


class AdmittedSeedTest(unittest.TestCase, _DecomposingWorkflowMixin):
    """A `decomposing` parent splitting into children whose records differ by the time each seed is due."""

    def setUp(self) -> None:
        self.github = FakeGitHubClient()
        self.parent = make_issue(_PARENT, label=LABEL_DECOMPOSING)
        self.github.add_issue(self.parent)

    def test_each_seed_follows_its_admitted_reading(self) -> None:
        # The first child is genuinely fresh, another poller held the second
        # for its seed, and the third carries a record admission refuses.
        for shape in _support.UNADMITTED:
            with self.subTest(third=shape):
                self.setUp()
                said = self._split_over(shape)

                fresh, held, refused = [child.number for child in self.github.created_child_issues]
                self.assertLessEqual(
                    _LINKED.items(), self.github.pinned_data(fresh).items(),
                )
                self.assertLessEqual(
                    _LIFTED.items(), self.github.pinned_data(held).items(),
                )
                self.assertEqual(_support.standing(self.github, refused), _refused_standing(shape))
                self._assert_unpublished([fresh, held, refused])
                self.assertTrue(_names(said, refused), "the refusal is said locally")

    def test_recovery_waits_for_an_admitted_record(self) -> None:
        # Every recovery tick reads the refused child again under its claim
        # and writes nothing while admission refuses it; once a record
        # admission takes is back on it, the recovery seeds it and finalizes.
        self._split_over("unversioned")
        created = [child.number for child in self.github.created_child_issues]
        refused = created[-1]

        with self.assertLogs(_support.WORKFLOW_LOG, level="WARNING"):
            recovered = self._run_decomposing(self.github, self.parent, run_agent=_agent())

        recovered[RUN_AGENT].assert_not_called()
        self.assertEqual(_support.standing(self.github, refused), _refused_standing("unversioned"))
        self._assert_unpublished(created)

        self.github.seed_state(refused)
        self._run_decomposing(self.github, self.parent, run_agent=_agent())

        self.assertEqual(self.github.pinned_data(refused)[KEY_PARENT_NUMBER], _PARENT)
        self.assertEqual(self.github.label_history, [(_PARENT, LABEL_BLOCKED)])
        self.assertEqual(len(_summaries(self.github)), 1)

    def test_the_seed_reads_behind_its_claim(self) -> None:
        # The child is created fresh and a human's edit leaves its record
        # refused before the seed lands: as its claim is granted, where a
        # reading taken ahead of the claim would still have found it fresh, or
        # behind the seed's own reading, where the writer refuses it. Neither
        # is written over, and neither parks the parent.
        refusing = (
            ("as its claim is granted", _support.EditedOnClaim(self._refuse_child).installed),
            ("behind the seed's reading", lambda: patch.object(
                self.github, "write_pinned_state", _EditedBeforeItsSeed(self.github, self._refuse_child),
            )),
        )
        for edit, installed in refusing:
            with self.subTest(edit=edit):
                self.setUp()
                with installed(), self.assertLogs(_support.WORKFLOW_LOG, level="WARNING"):
                    self._run_decomposing(self.github, self.parent, run_agent=_agent(last_message=_ONE_SLICE))

                child = self.github.created_child_issues[0].number
                self.assertEqual(_support.standing(self.github, child), _refused_standing("another version"))
                self._assert_unpublished([child])

    def _split_over(self, shape: str) -> list[str]:
        """Run the tick that splits the parent into three slices, the third pinned `shape` as it is created.

        Answers the warnings the tick logged.
        """
        pinned = _PinnedAtCreation(self.github, (None, _HELD, _REFUSED[shape]))
        created = patch.object(self.github, "create_child_issue", pinned)
        with created, self.assertLogs(_support.WORKFLOW_LOG, level="WARNING") as logged:
            self._run_decomposing(self.github, self.parent, run_agent=_agent(last_message=_THREE_SLICES))
            return logged.output

    def _refuse_child(self, number: int) -> None:
        """Leave a child's record one admission refuses, as a human's edit would; the parent is left."""
        if number != _PARENT:
            self.github.seed_state(number, raw=True, **_REFUSED["another version"])

    def _assert_unpublished(self, children: list[int]) -> None:
        """Every child recorded, and the parent neither parked, finalized, summarized, nor releasing any."""
        parent = self.github.pinned_data(_PARENT)
        self.assertEqual(parent[KEY_CHILDREN], children, "every child is recorded")
        self.assertFalse(parent.get(KEY_AWAITING_HUMAN), "nothing parks")
        self.assertEqual(self.github.label_history, [], "nothing is finalized or released")
        self.assertEqual(_summaries(self.github), [], "and nothing is summarized")


class _PinnedAtCreation:
    """A child create after which each new child carries the record its slice names, or none at all."""

    def __init__(self, gh: FakeGitHubClient, records: tuple) -> None:
        self._gh = gh
        self._create = gh.create_child_issue
        self._records = list(records)

    def __call__(self, **fields):
        """Create the child, then pin on it what another writer left there first."""
        child = self._create(**fields)
        record = self._records.pop(0)
        if record is not None:
            self._gh.seed_state(child.number, raw=True, **record)
        return child


class _EditedBeforeItsSeed:
    """A whole-state write in front of which a human's edit lands on the issue it writes."""

    def __init__(self, gh: FakeGitHubClient, edit) -> None:
        self._write = gh.write_pinned_state
        self._edit = edit

    def __call__(self, issue, state):
        """Edit the issue, then write it as the writer would."""
        self._edit(issue.number)
        return self._write(issue, state)


def _refused_standing(shape: str) -> tuple:
    """What a refused child still carries: its record under `shape`, an empty thread, its birth label, and open."""
    return dict(_REFUSED[shape]), [], [LABEL_BLOCKED], False


def _summaries(github: FakeGitHubClient) -> list[str]:
    """The split summaries posted on the parent's thread."""
    return [
        body for number, body in github.posted_comments
        if number == _PARENT and _SUMMARY in body
    ]


def _names(output: list[str], number: int) -> bool:
    """Whether a logged line names this issue's pinned comment."""
    return any(f"issue=#{number} pinned comment" in line for line in output)


if __name__ == "__main__":
    unittest.main()
