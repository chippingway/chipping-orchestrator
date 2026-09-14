# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The post-publication entry a generation records, and what it may not be."""
from __future__ import annotations

import unittest
from dataclasses import replace

from orchestrator.workflow.late_split.formats import InvalidLateValue
from orchestrator.workflow.late_split.publication import PublicationContext
from orchestrator.workflow.state import WorkflowLabel
from tests.workflow.late_split import generation_test_support as _support

_STAGE = "stage"
_PR_NUMBER = "pr_number"
_PUBLISHED_SHA = "published_sha"

# Every workflow state with an edge to the adjudication that no publication is
# entered from: three that have that edge for reasons of their own and no pull
# request behind any of them, and the seam whose own push OPENS the pull
# request. They are what tells the general graph from the exact predicate.
_UNPUBLISHED_STAGES = (
    WorkflowLabel.READY,
    WorkflowLabel.BLOCKED,
    WorkflowLabel.UMBRELLA,
    WorkflowLabel.IMPLEMENTING,
)

# What each of the three fields reads back as once a hand edit has taken it,
# keyed by the name on the record rather than the argument that set it.
_UNNAMED_CONTEXT = (
    ("source_stage", None),
    ("published_pr_number", None),
    (_PUBLISHED_SHA, ""),
)


def _entered_at(**overrides) -> dict:
    """The whole of what a post-publication entry names, one field swapped."""
    named = {
        _STAGE: _support.SOURCE_STAGE,
        _PR_NUMBER: _support.PUBLISHED_PR_NUMBER,
        _PUBLISHED_SHA: _support.PUBLISHED_SHA,
    }
    return {**named, **overrides}


class PublicationEntryTest(unittest.TestCase):
    """What a post-publication entry has to name to be recorded as one."""

    def test_an_entry_names_what_was_published(self) -> None:
        entered = PublicationContext.enter(
            **_entered_at(),
        )

        self.assertTrue(entered.post_publication)
        self.assertIs(entered.source_stage, WorkflowLabel.IN_REVIEW)
        self.assertEqual(
            entered.published_pr_number, _support.PUBLISHED_PR_NUMBER,
        )
        self.assertEqual(entered.published_sha, _support.PUBLISHED_SHA)
        self.assertTrue(entered.is_complete)

    def test_saying_nothing_is_pre_publication(self) -> None:
        # The absence is the answer rather than a gap, which is what lets a
        # record written without this group stay valid untouched.
        recorded = PublicationContext()

        self.assertFalse(recorded.post_publication)
        self.assertFalse(recorded.is_complete)

    def test_a_stage_is_kept_as_the_state_it_names(self) -> None:
        # The wire spelling a pinned comment holds is the label itself, and
        # what the record keeps is the member a later tick acts on.
        entered = PublicationContext.enter(
            **_entered_at(stage=str(WorkflowLabel.FIXING)),
        )

        self.assertIs(entered.source_stage, WorkflowLabel.FIXING)

    def test_an_entry_it_cannot_name_is_refused(self) -> None:
        # The pinned write drops what it cannot type, so a value accepted
        # here would leave the marker standing over a context nothing could
        # reconcile: a state this workflow has no label for, a pull request
        # nobody can ask GitHub about, or a head that is not a commit.
        refused = (
            (_STAGE, "workflow:sharpening"),
            (_STAGE, None),
            (_STAGE, _support.PUBLISHED_PR_NUMBER),
            (_PR_NUMBER, 0),
            (_PR_NUMBER, True),
            (_PR_NUMBER, "34"),
            (_PUBLISHED_SHA, "a1b2c3d"),
            (_PUBLISHED_SHA, ""),
            (_PUBLISHED_SHA, None),
        )
        for field, damaged in refused:
            with self.subTest(field=field, damaged=damaged), self.assertRaises(InvalidLateValue):
                PublicationContext.enter(
                    **_entered_at(**{field: damaged}),
                )

    def test_a_stage_nothing_publishes_from_refuses(self) -> None:
        # Being a workflow state is not enough for the one field that says
        # where a settled adjudication puts the issue back and which stage a
        # reconciliation may measure and push from. Recorded from a state that
        # publishes onto no pull request, the group would send a later tick to
        # push a candidate no post-publication stage ever committed.
        for named in _UNPUBLISHED_STAGES:
            with self.subTest(named=named), self.assertRaises(InvalidLateValue):
                PublicationContext.enter(
                    **_entered_at(stage=str(named)),
                )

    def test_a_hand_edited_stage_names_no_publication(self) -> None:
        # The read side of the same rule, because the write is not the only
        # road onto the pinned comment: an older binary and an operator's edit
        # each leave a whole-LOOKING group behind, and read back as context it
        # would be reconciled and pushed from a stage that publishes nothing.
        entered = PublicationContext.enter(
            **_entered_at(),
        )
        for named in _UNPUBLISHED_STAGES:
            with self.subTest(named=named):
                damaged = replace(entered, source_stage=named)

                self.assertTrue(damaged.post_publication)
                self.assertFalse(damaged.is_complete)

    def test_the_marker_alone_names_no_publication(self) -> None:
        # Every field beside the flag is read fail-closed, so a hand-edited
        # or older pinned comment can leave the marker with a pull request
        # nothing can name, a head no branch is compared against, or a stage
        # nothing could put the issue back into. None of the three can be
        # recovered from anywhere else on the issue.
        entered = PublicationContext.enter(
            **_entered_at(),
        )
        for field, gone in _UNNAMED_CONTEXT:
            with self.subTest(field=field):
                damaged = replace(entered, **{field: gone})

                self.assertTrue(damaged.post_publication)
                self.assertFalse(damaged.is_complete)


if __name__ == "__main__":
    unittest.main()
