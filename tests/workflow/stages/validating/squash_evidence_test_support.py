# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""An approval whose squash publishes another head, driven through `validating`'s own round.

The squash seam, the collapse it records, and the evidence records and
artifacts a case reads back are the shared approval journey's
(`tests/workflow/approved_squash.py`), which the stages past this one drive
through whole dispatcher ticks. Here the world is the live reviewer round
(`evidence_round_test_support`), ticked whole -- the evidence reconciliation,
then the validating handler -- and what is `validating`'s own is spelled
beside it: a squash notice the thread refuses, a relabel GitHub refuses once,
and another road's later round over the squashed head.
"""
from __future__ import annotations

from orchestrator.workflow.engine import review_subjects as _review_subjects
from tests.workflow import approved_squash as _approved_squash, published_reports as _published_reports
from tests.workflow.stages.validating import evidence_round_test_support as _round

HEAD = _round.HEAD

# The commit the squash publishes, the count its collapse record names, a tree
# no evidence was gathered on, the pinned record of the approval's claim, and
# the notice the squash posts -- the shared journey's own.
SQUASHED = _approved_squash.SQUASHED

COLLAPSED = _approved_squash.COLLAPSED

OTHER_TREE = _approved_squash.OTHER_TREE

APPROVED_EVIDENCE = _approved_squash.APPROVED_EVIDENCE

SQUASH_NOTICE = _approved_squash.SQUASH_NOTICE

# The squash that publishes, and one dispatcher tick in a case's hermetic world.
LandsTheSquash = _approved_squash.LandsTheSquash

dispatches = _approved_squash.dispatches


class RefusesTheNotice:
    """A pull-request thread that refuses the first squash notice posted to it and takes every other post.

    The one post a handoff stops on: the count it is worded from lives on the
    collapse record, which is kept for the recovery to announce.
    """

    def __init__(self, github) -> None:
        self._posts = github.pr_comment
        self._refused = False

    def __call__(self, pr_number: int, body: str):
        if SQUASH_NOTICE in body and not self._refused:
            self._refused = True
            raise RuntimeError("comment refused")
        return self._posts(pr_number, body)


def reviews_the_squashed_head(case) -> None:
    """Another road's later round over the squashed head: a report of it settled, and a reviewer handed it and returned.

    What the approval was never given: a review subject about that head,
    naming a report the approved one is not, recorded as handed and as
    returned.
    """
    _published_reports.republishes_the_report(case.github, case.issue, "A report of the squashed head.")
    state = case.github.read_pinned_state(case.issue)
    state.set(_review_subjects.RETURNED_SUBJECT, case.handed(state).subject.recorded())
    case.github.write_pinned_state(case.issue, state)


class RefusesTheRelabelOnce:
    """A GitHub that refuses the first relabel and takes every one after it."""

    def __init__(self, github) -> None:
        self._relabels = github.set_workflow_label
        self._refused = False

    def __call__(self, issue, label):
        if not self._refused:
            self._refused = True
            raise RuntimeError("label update rejected")
        return self._relabels(issue, label)


class SquashedRoundWorld(_approved_squash.SquashedApproval, _round.LiveRoundWorld):
    """An issue whose reviewer is about to approve, and whose approval's squash publishes another head.

    Every tick reaches the validating handler, whatever the label reads.
    """
