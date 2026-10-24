# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The drift baseline an ordinary split seeds each child with, and the one its recovery cannot.

A split's seed records what the drift check read off the child as its create
answered it -- the slice, the receipt, any snapshot reuse instructions, and the
parent footer -- so whatever lands on the child after the create is measured
against what it was created saying: a requirements edit is drift the child's
own check meets, and a comment the hash filters is not. A recovery has no
create's answer in hand, and a receipt proves the slice rather than the words,
so a child it seeds is left with no baseline, edited or not; one the split's
seed did land is kept. A seed or a read that never comes back stops the
summary and the finalize until the recovery has read what landed.
"""
from __future__ import annotations

import unittest
from dataclasses import dataclass
from types import MappingProxyType
from unittest.mock import patch

from orchestrator import config
from orchestrator.github.comments import ORCHESTRATOR_COMMENT_MARKER
from tests.support.fakes import FakeGitHubClient, FakeIssue, make_issue
from tests.workflow.fixtures import (
    KEY_PARENT_NUMBER,
    LABEL_BLOCKED,
    LABEL_DECOMPOSING,
    LABEL_READY,
    LABEL_UMBRELLA,
    _agent,
    _manifest,
)
from tests.workflow.stages.decomposition import (
    child_baseline_support as _baseline_support,
    child_claim_test_support as _claim_support,
    replacement_lineage_support as _lineage_support,
    replacement_split_support as _split,
)
from tests.workflow.stages.decomposition.decomposing_test_support import _DecomposingWorkflowMixin

KEY_BASELINE = _baseline_support.KEY_BASELINE

RUN_AGENT = "run_agent"

_PARENT = 97

# The one author the allowlist these cases run under trusts.
_TRUSTED = "alice"

_ONE_SLICE = _manifest('{"decision": "split", "children": [{"title": "A", "body": "a", "depends_on": []}]}')

# A baseline some writer recorded on a child before its seed, beside the hold
# the dispatcher puts on a child whose seed has not landed.
_RECORDED_BASELINE = "a baseline recorded before the seed"
_RECORDED = MappingProxyType({
    "schema_version": 1,
    "awaiting_human": True,
    "park_reason": "replacement_lineage_unproved",
    KEY_BASELINE: _RECORDED_BASELINE,
})

# Where a briefed child's reuse instructions could be pointed instead.
_FOREIGN_REF = "refs/orchestrator/late-split/issue-4/cycle-2/gen-1"

# The park a seed that could not be written, or a record that could not be
# read, takes on the parent.
PARK_CHILD_SEED_FAILED = "child_seed_failed"

# What every split summary opens with.
_SUMMARY = ":bookmark_tabs: decomposer split this into"

# The parents a recovered split is driven under: the root of a late lineage
# holding the snapshot its own split preserved, and an issue no late split
# charged.
_PARENTS = MappingProxyType({
    "a late root": _lineage_support.own_split(),
    "an ordinary issue": None,
})

# Where the parent and its child stand, the parks the parent took, and how
# many summaries it posted: the split held by a park, and finalized once with
# the child not yet started -- past that park, or past none.
_PARKED = (LABEL_DECOMPOSING, LABEL_BLOCKED, [PARK_CHILD_SEED_FAILED], 0)
_FINALIZED_PAST_THE_PARK = (LABEL_UMBRELLA, LABEL_BLOCKED, [PARK_CHILD_SEED_FAILED], 1)
_FINALIZED = (LABEL_UMBRELLA, LABEL_BLOCKED, [], 1)


@dataclass(frozen=True)
class _Edited:
    """A human's edit to one field of an issue, appending to what it says."""

    field: str
    appended: str

    def __call__(self, gh: FakeGitHubClient, issue: FakeIssue) -> None:
        """Append to the field."""
        setattr(issue, self.field, f"{getattr(issue, self.field)}{self.appended}")


@dataclass(frozen=True)
class _Landing:
    """Something landing on a child, beside whether it is a requirements edit the drift check counts."""

    land: object
    edits: bool


_BODY_EDIT = _Edited("body", "\n\nand cover the edge cases too")

# What can land on a child between its create and its seed: its title, its
# body, or a trusted comment is a requirements edit; a comment the hash
# filters -- an untrusted author's, a bot's, or one carrying the orchestrator's
# marker -- is not.
_LANDED_BEFORE_THE_SEED = MappingProxyType({
    "its title edited": _Landing(_Edited("title", ", and its docs"), edits=True),
    "its body edited": _Landing(_BODY_EDIT, edits=True),
    "a trusted comment": _Landing(_baseline_support.Commented(_TRUSTED), edits=True),
    "an untrusted comment": _Landing(_baseline_support.Commented("mallory"), edits=False),
    "a bot's comment": _Landing(_baseline_support.Commented(_TRUSTED, kind="Bot"), edits=False),
    "a generated comment": _Landing(
        _baseline_support.Commented(_TRUSTED, body=f"noted {ORCHESTRATOR_COMMENT_MARKER}"), edits=False,
    ),
})


class CreationBaselineTest(unittest.TestCase, _DecomposingWorkflowMixin):
    """A `decomposing` parent splitting into one slice, its child's baseline read back after."""

    def setUp(self) -> None:
        self.github = FakeGitHubClient()
        self.parent = make_issue(_PARENT, label=LABEL_DECOMPOSING)
        self.github.add_issue(self.parent)

    @patch.object(config, "ALLOWED_ISSUE_AUTHORS", (_TRUSTED,))
    def test_only_the_create_answer_is_baselined(self) -> None:
        # Something lands on the child after its create returned, ahead of
        # the seed's reading under its claim. The seed records what the drift
        # check read off the child as created, so what landed is measured
        # against it -- drift where it edits the requirements, nothing where
        # the hash filters it.
        for landed, landing in _LANDED_BEFORE_THE_SEED.items():
            with self.subTest(landed=landed):
                self.setUp()
                recorded, created, drifted = self._split_landing(landing.land)

                self.assertEqual(recorded, created, "the seed records the child as created")
                self.assertEqual(drifted, landing.edits)

    def test_a_recorded_baseline_is_kept(self) -> None:
        # Another writer reached the child first, and its record already
        # carries a baseline: the seed links the child and lifts that
        # writer's hold, and leaves the baseline as it stands.
        self.github.create_child_issue = _baseline_support.ReadAtCreation(self.github, _RECORDED)

        self._run_decomposing(self.github, self.parent, run_agent=_agent(last_message=_ONE_SLICE))

        seeded = self.github.pinned_data(self.github.created_child_issues[0].number)
        self.assertEqual(
            (seeded.get(KEY_PARENT_NUMBER), seeded.get("awaiting_human"), seeded.get(KEY_BASELINE)),
            (_PARENT, False, _RECORDED_BASELINE),
        )

    def test_a_briefing_is_part_of_it(self) -> None:
        # A child owed its parent's snapshot is created with the reuse
        # instructions after its receipt, and they are part of what it was
        # created saying: unedited it reads as unchanged, and instructions
        # repointed since read as the edit they are.
        github, issue = _split.late_parent(_lineage_support.own_split())
        _split.redecompose(github, issue, _split.ONE_REPLACEMENT_MANIFEST)
        child = github.created_child_issues[0]

        self.assertIn(_lineage_support.SNAPSHOT_REF, child.body, "the child is briefed")
        self.assertFalse(_baseline_support.drifted(github, child.number), "and reads as unchanged unedited")
        child.body = child.body.replace(_lineage_support.SNAPSHOT_REF, _FOREIGN_REF)
        self.assertTrue(_baseline_support.drifted(github, child.number), "and repointed as edited")

    def _split_landing(self, land) -> tuple:
        """Split the parent into one slice, `land` landing on its child as the seed's claim is granted.

        Answers the baseline the child's record carries, what the drift check
        read off the child as its create returned, and whether that check
        reads the child as changed since. The split publishes and releases the
        child either way.
        """
        created = _baseline_support.ReadAtCreation(self.github)
        self.github.create_child_issue = created
        landing = _claim_support.EditedOnClaim(_baseline_support.LandedOnce(self.github, land, _PARENT))
        with landing.installed():
            self._run_decomposing(self.github, self.parent, run_agent=_agent(last_message=_ONE_SLICE))
        child = self.github.created_child_issues[0].number
        self.assertEqual(self.github.label_history, [(_PARENT, LABEL_BLOCKED), (child, LABEL_READY)])
        recorded = self.github.pinned_data(child).get(KEY_BASELINE)
        return recorded, created.readings[0], _baseline_support.drifted(self.github, child)


class RecoveredBaselineTest(unittest.TestCase):
    """A split whose child's seed never came back, and the recovery that finishes it."""

    def setUp(self, parent: str = "a late root") -> None:
        github, issue = _split.late_parent(_PARENTS[parent])
        self.github = github
        self.issue = issue

    def test_an_edit_before_the_repair_is_no_baseline(self) -> None:
        # The process dies at the seed, and the child is edited while its
        # recovery is due. The create's answer died with the process, and the
        # receipt proves the slice, not the words: the recovery links the
        # child and finalizes, and leaves its baseline missing rather than
        # taking what it says by then as what it was created saying.
        for parent in _PARENTS:
            with self.subTest(parent=parent):
                self.setUp(parent)
                child = self._split_into_a_lost_seed(lands=False)
                _BODY_EDIT(self.github, self.github.get_issue(child))

                self._recover()

                seeded = self.github.pinned_data(child)
                self.assertEqual(seeded.get(KEY_PARENT_NUMBER), _lineage_support.PARENT)
                self.assertNotIn(KEY_BASELINE, seeded)
                self.assertEqual(self._standing(child), _FINALIZED)

    def test_a_lost_seed_answer_keeps_its_baseline(self) -> None:
        # The seed lands and its answer is lost: the split parks naming the
        # child and publishes nothing past it. An edit lands while the park
        # stands; once a human lifts it, the recovery finds the seed that
        # landed and keeps its baseline -- what the child was created saying
        # -- so the edit stays drift, and the summary and the finalize are
        # published once each.
        child = self._split_into_a_lost_seed(lands=True)
        created = _baseline_support.reading(self.github.get_issue(child))
        landed = self.github.pinned_data(child).get(KEY_BASELINE)
        parked = self._standing(child)
        _BODY_EDIT(self.github, self.github.get_issue(child))

        self._recover(lifting=True)

        self.assertEqual((landed, parked), (created, _PARKED))
        self.assertEqual(self.github.pinned_data(child).get(KEY_BASELINE), created)
        self.assertTrue(_baseline_support.drifted(self.github, child), "the edit is still drift")
        self.assertEqual(self._standing(child), _FINALIZED_PAST_THE_PARK)

    def test_an_unreadable_record_holds_the_recovery(self) -> None:
        # The child's record cannot be read under its claim, which proves
        # nothing about what landed there: the recovery writes nothing to it
        # and parks rather than summarizing or finalizing. Once the record
        # reads again and the park is lifted, the child is seeded with no
        # baseline and the split is published once.
        child = self._split_into_a_lost_seed(lands=False)
        unreadable = patch.object(
            self.github, "read_pinned_state", _baseline_support.UnreadableRecord(self.github, child),
        )
        with unreadable, self.assertLogs(_claim_support.WORKFLOW_LOG, level="ERROR"):
            self._recover()
        held = (self.github.pinned_data(child), self._standing(child))

        self._recover(lifting=True)

        seeded = self.github.pinned_data(child)
        self.assertEqual(held, ({}, _PARKED))
        self.assertEqual(seeded.get(KEY_PARENT_NUMBER), _lineage_support.PARENT)
        self.assertNotIn(KEY_BASELINE, seeded)
        self.assertEqual(self._standing(child), _FINALIZED_PAST_THE_PARK)

    def _split_into_a_lost_seed(self, *, lands: bool) -> int:
        """Run the one-replacement split into a child seed that never comes back; the child it created.

        `lands` lands the seed and loses its answer, which the split parks
        on; otherwise the process dies before the seed lands.
        """
        lost = _baseline_support.LostSeed(self.github, _lineage_support.PARENT, lands=lands)
        expected = self.assertLogs(_claim_support.WORKFLOW_LOG, level="ERROR") if lands else (
            self.assertRaises(KeyboardInterrupt)
        )
        with patch.object(self.github, "write_pinned_state", lost), expected:
            _split.redecompose(self.github, self.issue, _split.ONE_REPLACEMENT_MANIFEST)
        return _split.replacements(self.github)[0]

    def _recover(self, *, lifting: bool = False) -> None:
        """The next decomposing tick, answered without the decomposer -- the parent's park lifted by hand first.

        `lifting` takes the park off as the human its notice asked for would.
        """
        if lifting:
            parked = self.github.pinned_data(_lineage_support.PARENT)
            self.github.seed_state(_lineage_support.PARENT, **{**parked, "awaiting_human": False, "park_reason": None})
        _split.redecompose(self.github, self.issue)[RUN_AGENT].assert_not_called()

    def _standing(self, child: int) -> tuple:
        """Where the parent and the child stand, the parks the parent took, and how many summaries it posted."""
        summaries = [body for _, body in self.github.posted_comments if _SUMMARY in body]
        return (
            self.github.workflow_label(self.issue),
            self.github.workflow_label(self.github.get_issue(child)),
            _split.parks(self.github),
            len(summaries),
        )


if __name__ == "__main__":
    unittest.main()
