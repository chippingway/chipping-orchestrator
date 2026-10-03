# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Guidance a late revision answered, carried across the split it ends in.

A human's guidance resumes the developer, the revision comes back still
oversized, the adjudication splits it, and the parent is handed to
`workflow:umbrella`. The first poll of that umbrella runs the ordinary drift
check over a thread still carrying the guidance, which was answered two ticks
earlier -- so it has to read as the baseline rather than as an edit, or the
children the split just made are orphaned and the same work is decomposed a
second time, with no human having written anything in between.

What must still be an edit is the other half. Words that arrived after the
reading the revision consumed were acted on by nobody, and the next agent is
owed them; the controls an operator types and the orchestrator's own comments
are not requirements at all, and route nothing. The children the decomposer
then answers the edit with replace the split's own inside the same lineage:
one level below the root, pointed at the snapshot the split still holds, and
recorded as its consumers.
"""
from __future__ import annotations

import unittest
from unittest.mock import patch

from orchestrator import config
from orchestrator.github.comments import ORCHESTRATOR_COMMENT_MARKER
from orchestrator.workflow.late_split import state as _late_state
from orchestrator.workflow.stages.decomposition import late_relabel as _late_relabel
from orchestrator.workflow.stages.decomposition.late_result_models import _LateDisposition
from orchestrator.workflow.state import WorkflowLabel
from tests.workflow.stages.decomposition import (
    late_content_replies as _replies,
    late_content_support as _support,
    late_crash_support as _crash,
    late_revision_support as _revision_support,
    late_test_support as _stage_support,
    replacement_split_support as _split,
)
from tests.workflow.stages.decomposition.late_requirements_support import (
    DRIFT_NOTICE,
    KEY_CHILDREN,
    KEY_USER_CONTENT_HASH,
    GuidedSplitCase,
    posted,
    recorded_baselines,
    requirements,
)

LATER_GUIDANCE = "one more thing: keep the old endpoint alive"

# A comment a late baseline counted before any stage consumed it.
COUNTED = "and the importer must log every skipped row"

COUNTED_ID = 9

ALLOWED_AUTHORS = "ALLOWED_ISSUE_AUTHORS"

KEY_CONSUMERS = "late_consumers"

# The lineage and the pointer a child's ancestry records: everything a late
# split seeds but the slice it declared and the base branch it names.
_INHERITED_KEYS = (
    "late_ancestry_root_issue",
    "late_ancestry_depth",
    "late_ancestry_parent",
    "late_ancestry_cycle_id",
    "late_ancestry_generation",
    "late_ancestry_snapshot_ref",
    "late_ancestry_snapshot_sha",
    "late_ancestry_mirror_first",
)

# The two slices the adjudicator's split proposes: one set of children is
# exactly this many issues.
_SLICES = 2

# What a died handoff takes to reach its first umbrella poll: the tick that
# puts the label back on `decomposing`, the one that re-enters the
# transaction from the recorded verdict, and then the poll itself.
_RETRY_TICKS = 3

# Everything a thread can carry after the split that is not a requirement,
# each by the author that posts it. The allowlist is on for all of them, so
# the outsider is filtered by the same rule every other reader applies.
_NOT_REQUIREMENTS = (
    ("a bare continue", _support.BARE_CONTINUE, {}),
    ("a run grant", "/orchestrator add-agent-runs 3", {}),
    ("an authorization", _replies.authorization(_support.REVISED_SHA), {}),
    (
        "the orchestrator's own comment",
        f"relabelled.\n\n{ORCHESTRATOR_COMMENT_MARKER}",
        {},
    ),
    ("a third-party bot", LATER_GUIDANCE, {"user_type": "Bot"}),
    ("an outsider", LATER_GUIDANCE, {"login": _support.OUTSIDER}),
)


def _commented(issue) -> None:
    """A trusted human adding a requirement as a comment of its own."""
    _replies.reply(issue, LATER_GUIDANCE)


def _edited(issue) -> None:
    """A trusted human rewriting the body."""
    issue.body = _support.EDITED_BODY


# The two ways a requirement can move past the consumed reading, and what the
# next agent has to be shown because of it.
_LATER_EDITS = (
    ("a trusted comment", _commented, LATER_GUIDANCE),
    ("a body edit", _edited, _support.EDITED_BODY),
)


class GuidedSplitHandoffTest(GuidedSplitCase):
    """One set of children survives the first poll of the umbrella a split made."""

    def setUp(self) -> None:
        self._start()

    def test_the_first_umbrella_poll_keeps_the_split(self) -> None:
        revised, _resumed = self._revise_oversized()
        consumed = self._pinned()[KEY_USER_CONTENT_HASH]
        split = self._split()
        created = self._created()

        self._dispatch()

        self.assertEqual(revised.disposition, _LateDisposition.REVISED)
        self.assertEqual(split.disposition, _LateDisposition.SETTLED)
        # Durable with the revision, before any split: the guidance is inside
        # the baseline from the write that consumed it.
        self.assertEqual(consumed, requirements(self.issue))
        self.assertEqual(
            self.github.workflow_label(self.issue), WorkflowLabel.UMBRELLA,
        )
        self.assertEqual(len(created), _SLICES)
        self.assertEqual(self._pinned()[KEY_CHILDREN], created)
        self.assertFalse(any(DRIFT_NOTICE in body for body in self._bodies()))

    def test_a_died_handoff_retries_without_drift(self) -> None:
        # The window the relabel guard exists for: `umbrella` on the issue
        # over a generation the pinned comment still reads as live.
        self._revise_oversized()
        with _crash.killed_after(self.github, "set_workflow_label"), self.assertRaises(KeyboardInterrupt):
            self._split()
        created = self._created()
        self.assertTrue(_late_relabel._adjudication_is_live(
            _late_state.read_late_generation(self.github.read_pinned_state(self.issue)),
        ))

        for _ in range(_RETRY_TICKS):
            self._dispatch()

        self.assertEqual(
            self.github.workflow_label(self.issue), WorkflowLabel.UMBRELLA,
        )
        self.assertEqual(self._created(), created)
        self.assertEqual(self._pinned()[KEY_CHILDREN], created)
        self.assertFalse(any(DRIFT_NOTICE in body for body in self._bodies()))


class LaterRequirementsTest(GuidedSplitCase):
    """What arrived past the consumed reading is still an edit for the next agent."""

    def test_a_later_edit_reroutes_to_the_decomposer(self) -> None:
        for shape, change, said in _LATER_EDITS:
            with self.subTest(shape=shape):
                self._start()
                self._revise_oversized()
                self._split(arriving=change)

                self._dispatch()
                decomposer = self._redecompose()

                self.assertTrue(any(DRIFT_NOTICE in body for body in self._bodies()))
                self.assertEqual(self._pinned()[KEY_USER_CONTENT_HASH], requirements(self.issue))
                decomposer.assert_called_once()
                self.assertIn(said, decomposer.call_args.args[1])

    def test_replacements_inherit_the_lineage(self) -> None:
        # The edit is genuine, so the decomposer's answer replaces the split's
        # own children -- and they are the lineage's second generation, not a
        # fresh root's first.
        for shape, change, said in _LATER_EDITS:
            with self.subTest(shape=shape):
                self._start()
                self._revise_oversized()
                self._split(arriving=change)
                originals = self._created()

                self._dispatch()
                decomposer = self._redecompose(_split.REPLACEMENT_MANIFEST)

                self.assertIn(said, decomposer.call_args.args[1])
                self._assert_replaced(originals)

    def test_controls_and_our_comments_are_no_edit(self) -> None:
        for shape, body, author in _NOT_REQUIREMENTS:
            with self.subTest(shape=shape):
                self._start()
                self._revise_oversized()
                self._split()
                posted(self.issue, body, **author)

                with patch.object(config, ALLOWED_AUTHORS, (_replies.HUMAN,)):
                    self._dispatch()

                self.assertEqual(
                    self.github.workflow_label(self.issue), WorkflowLabel.UMBRELLA,
                )
                self.assertEqual(self._pinned()[KEY_CHILDREN], self._created())
                self.assertFalse(any(DRIFT_NOTICE in comment for comment in self._bodies()))

    def _assert_replaced(self, originals: list) -> None:
        """The replacements are tracked, protected, and cut where the originals were.

        One level below the root, pointed at the one snapshot the split still
        holds, and recorded beside the originals as its consumers.
        """
        replacements = [number for number in self._created() if number not in originals]
        protected = sorted([*originals, *replacements])
        inherited = [self._inherited(number) for number in replacements]
        cut = self._inherited(originals[0])
        self.assertEqual(self._pinned()[KEY_CHILDREN], replacements)
        self.assertEqual(len(replacements), _split.REPLACEMENT_COUNT)
        self.assertEqual(self._pinned()[KEY_CONSUMERS], protected)
        self.assertEqual(cut[_INHERITED_KEYS[1]], 1)
        self.assertEqual(inherited, [cut for _ in replacements])

    def _inherited(self, number: int) -> dict:
        """The lineage and pointer one child's pinned comment records."""
        pinned = self.github.pinned_data(number)
        return {key: pinned.get(key) for key in _INHERITED_KEYS}


class UnrecordedBaselineHandoffTest(GuidedSplitCase):
    """An issue with no requirements baseline hands its umbrella the reading it carried on over.

    Nothing was consumed, so no baseline is recorded; what the adjudication
    read is recorded as observed instead, and the umbrella's first poll
    compares against that. Both ways the late baseline can stand -- taken on
    this tick, or taken before and persisted -- come to the same thing.
    """

    def test_a_quiet_reading_keeps_the_split(self) -> None:
        for taken in (False, True):
            with self.subTest(fingerprints_taken=taken):
                self._start_unrecorded(taken)
                split = self._split()
                handed = recorded_baselines(self._pinned())
                created = self._created()

                self._dispatch()

                self.assertEqual(split.disposition, _LateDisposition.SETTLED)
                # Handed on as observed; recorded as the baseline only by the
                # umbrella poll that found the thread unchanged.
                self.assertEqual(handed, (None, requirements(self.issue)))
                self.assertEqual(self._pinned()[KEY_USER_CONTENT_HASH], requirements(self.issue))
                self.assertEqual(self._pinned()[KEY_CHILDREN], created)
                self.assertEqual(len(created), _SLICES)
                self.assertFalse(any(DRIFT_NOTICE in body for body in self._bodies()))

    def test_an_edit_during_the_run_reroutes(self) -> None:
        # The reading consumed nothing, and the change lands while the
        # adjudicator runs: the umbrella's first poll has the observed reading
        # to see it against rather than taking the thread as it finds it.
        for taken in (False, True):
            for shape, change, said in _LATER_EDITS:
                with self.subTest(fingerprints_taken=taken, shape=shape):
                    self._start_unrecorded(taken)
                    self._split(arriving=change)

                    self._dispatch()
                    decomposer = self._redecompose()

                    self.assertTrue(any(DRIFT_NOTICE in body for body in self._bodies()))
                    self.assertEqual(self._pinned()[KEY_USER_CONTENT_HASH], requirements(self.issue))
                    decomposer.assert_called_once()
                    self.assertIn(said, decomposer.call_args.args[1])

    def _start_unrecorded(self, taken: bool) -> None:
        """Seed a candidate frozen on an issue with no requirements baseline.

        `taken` persists late fingerprints over the quiet thread first, the
        whole-thread way a generation recorded before bounded baselines was. No
        guidance follows, so the reading finds nothing to hand on and the
        adjudication carries on over it: the frozen candidate is the one the
        split is made from.
        """
        self._seed(baseline=taken, bounded=False)
        self.head = _stage_support.CANDIDATE_SHA


class CountedCommentHandoffTest(GuidedSplitCase):
    """A late baseline that counts a comment no stage consumed gives it up before any split.

    The generation was baselined over the whole thread, and the issue-wide
    baseline is missing or older than the comment. Left counted, the comment
    would reach no agent -- and the umbrella's first poll would either take it
    as that umbrella's baseline or meet it as an edit and orphan the children.
    """

    def test_the_comment_reaches_the_developer_first(self) -> None:
        for shape, older in (("no recorded baseline", False), ("an older baseline", True)):
            with self.subTest(recorded=shape):
                self._start_counted(older=older)

                revised, resumed = self._revise_oversized()
                self._split()
                created = self._created()
                self._dispatch()

                self.assertEqual(revised.disposition, _LateDisposition.REVISED)
                self.assertIn(COUNTED, resumed.call_args.args[1])
                self.assertEqual(self.github.workflow_label(self.issue), WorkflowLabel.UMBRELLA)
                self.assertEqual(self._pinned()[KEY_CHILDREN], created)
                self.assertFalse(any(DRIFT_NOTICE in body for body in self._bodies()))

    def _start_counted(self, *, older: bool) -> None:
        """Seed late fingerprints that count one comment, over no baseline or an older one.

        The older baseline is the one recorded before the comment was written.
        """
        self._seed(
            comments=(_replies.human_comment(COUNTED_ID, COUNTED),), bounded=False, **_revision_support.DEV_PIN,
        )
        if older:
            counted = self.issue.comments.pop()
            self.github.seed_state(_stage_support.LATE_ISSUE_NUMBER, **{
                **self._pinned(), KEY_USER_CONTENT_HASH: requirements(self.issue),
            })
            self.issue.comments.append(counted)
        self.head = _support.REVISED_SHA


if __name__ == "__main__":
    unittest.main()
