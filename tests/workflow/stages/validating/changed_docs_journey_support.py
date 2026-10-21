# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""An approval squashed and handed to its final-docs pass, whose docs commit changes the pull request.

The squashed round walked past its approval (`squash_rebase_journey_support`):
the reviewer approves the report settled about `HEAD`, the squash publishes
`SQUASHED` on the same tree and carries the approved run onto it, and the
carry settles and moves the label to `workflow:documenting`. There the docs
pass commits `DOCS_HEAD` on top of the squash and the push lands, standing the
pull request on it. Every tick from there is a whole dispatch of whatever label
the issue carries, and every run a dispatch spawns is recorded by role with
the prompt it was handed (`spawned`).

A case reads the walk back through `handed_back`: the records the hand-back is
judged by -- the report debt, the mark, the evidence and approval it retired,
and the stamp -- off the pinned comment as the next tick reads it. Where the
walk ends is read by the assertions of `_ChangedDocsWalk`: one run of each role
and nothing owed, parked, or told twice.
"""
from __future__ import annotations

import contextlib
from functools import partial
from unittest.mock import patch

from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    review_subjects as _review_subjects,
    verification_settlement_state as _settlement,
)
from orchestrator.workflow.state import WorkflowLabel
from tests.workflow import drift_reports as _drift_world
from tests.workflow.fixtures import MEASURED_CANDIDATE_SHA, _agent
from tests.workflow.stages.validating import squash_rebase_journey_support as _journey

HEAD = _journey.HEAD

SQUASHED = _journey.SQUASHED

# The docs commit the final-docs pass publishes on top of the squash: the
# commit the size gate proves the checkout to once its subject names the pull
# request.
DOCS_HEAD = MEASURED_CANDIDATE_SHA

# A docs pass that committed a docs change, and what the developer then
# reports about the head it published.
DOCS_CHANGED = (_journey.DOCUMENTER, _agent(last_message="docs: describe the new flag"))

DOCS_REPORT = "The docs now describe the new flag; the approved change is unchanged and the suite passes."

# The pinned records a hand-back is read back by.
REWRITE_DEBT = "developer_report_rewrite_debt"

HANDED_BACK = "docs_handed_back_sha"

DOCS_VERDICT = "docs_verdict"

DOCS_CHECKED = "docs_checked_sha"

# What a pinned edit carries when it is the hand-back's own write.
_HANDS_BACK = HANDED_BACK

# Every run the walk charges from the docs pass on, in order, and the labels
# the issue moves through from the walk on.
ONE_OF_EACH = (_journey.DOCUMENTER, _journey.REFRESHER, _journey.REVIEWER, _journey.DOCUMENTER)

DOCUMENTED_AGAIN = (
    WorkflowLabel.DOCUMENTING, WorkflowLabel.VALIDATING, WorkflowLabel.DOCUMENTING, WorkflowLabel.IN_REVIEW,
)

# The report the refresh settles, as its commit and revision: the docs commit,
# one revision past the approved report.
REFRESHED = (DOCS_HEAD, 2)

# How the refresh names the report the pull request carries: the approved
# commit, squashed into the head the docs commit replaced.
APPROVED_REPORT = f"describes `{HEAD}`, the approved commit this orchestrator squashed into `{SQUASHED}`"

# The record and the members of the report a pinned comment settled.
_CURRENT_REPORT = "developer_report_current"

_PARK_REASON = "park_reason"

_REVIEW_ROUND = "review_round"


class _Crashed(RuntimeError):
    """The process ending where a case says it ends."""


class _DiesOnTheHandBack:
    """The pinned edits a tick makes, ending on the one landing the hand-back -- or landing it and losing the answer.

    `lands` is the write going out and its answer lost: the edit is made and
    the process ends before anything is told of it.
    """

    def __init__(self, edits, *, lands: bool) -> None:
        self._edits = edits
        self._lands = lands

    def __call__(self, issue, state, **options):
        if state.get(_HANDS_BACK) is None:
            return self._edits(issue, state, **options)
        if self._lands:
            self._edits(issue, state, **options)
        raise _Crashed


class _DiesOnTheRelabel:
    """The relabels a tick makes, ending on the one handing the issue back to `validating`."""

    def __init__(self, relabels) -> None:
        self._relabels = relabels

    def __call__(self, issue, label):
        if label == WorkflowLabel.VALIDATING:
            raise _Crashed
        return self._relabels(issue, label)


@contextlib.contextmanager
def _on_the_hand_back(case, *, lands: bool):
    """The process ending on the hand-back's write, which lands first only where `lands`."""
    with patch.object(
        case.github, "edit_pinned_state", _DiesOnTheHandBack(case.github.edit_pinned_state, lands=lands),
    ), contextlib.suppress(_Crashed):
        yield


# The process ending on the hand-back's write with nothing of it landed, which
# leaves the receipt the gate put down; and the write landing with the process
# ending before its answer, which leaves the debt and mark with no relabel.
dying_on_the_hand_back = partial(_on_the_hand_back, lands=False)

losing_the_hand_back = partial(_on_the_hand_back, lands=True)


@contextlib.contextmanager
def dying_on_the_relabel(case):
    """The hand-back's write confirmed and the process ending on the relabel behind it."""
    with patch.object(
        case.github, "set_workflow_label", _DiesOnTheRelabel(case.github.set_workflow_label),
    ), contextlib.suppress(_Crashed):
        yield


class _ChangedDocsJourney(_journey._SquashRebaseJourney):
    """The squashed round walked into its final-docs pass, which publishes a docs commit."""

    def walks_into_documenting(self) -> None:
        """Approve, squash, and settle the carry, leaving the label on `workflow:documenting`.

        Nothing spawned on the way is kept, and what the issue has spent by
        then is `charged`, so a case reads its runs and charges from here on.
        """
        self.approves()
        self.later()
        self.spawns.clear()
        self.charged = self.spent()

    def changes_the_docs(self, push=None, **run_options) -> None:
        """One dispatch of the docs pass, committing `DOCS_HEAD` on the squash; its push lands unless `push` says.

        `run_options` are the dispatch's own readings beside those.
        """
        self.dispatched(
            DOCS_CHANGED,
            head_shas=(SQUASHED, DOCS_HEAD),
            push_branch=push or _drift_world._LandingPush(self.pull_request),
            **run_options,
        )

    def changes_the_docs_under(self, window) -> None:
        """The docs dispatch, cut short in `window` and followed by the dispatch that finds what it left.

        `window` is a context on the case, "push" for the push's answer lost,
        or None for a dispatch that runs through, which nothing follows.
        """
        if window is None:
            self.changes_the_docs()
            return
        if window == "push":
            with contextlib.suppress(RuntimeError):
                self.changes_the_docs(_journey.LandsThenDies(self.pull_request))
        else:
            with window(self):
                self.changes_the_docs()
        self.dispatched()

    def walks_into_a_lost_hand_back(self) -> None:
        """Walk into the docs pass, and have its push land and its hand-back's write die with nothing of it landed."""
        self.walks_into_documenting()
        with dying_on_the_hand_back(self):
            self.changes_the_docs()

    def assert_held_still(self) -> None:
        """Nothing handed back: the label, the pull request on the docs commit, no debt, and the evidence current."""
        self.assertEqual(self.labels()[-1], WorkflowLabel.DOCUMENTING)
        self.assertEqual(self.pull_request.head.sha, DOCS_HEAD)
        self.assertIsNone(self.pinned().get(REWRITE_DEBT))
        self.assertIsNotNone(self.current_evidence())

    def current_evidence(self):
        """The evidence the pinned comment records as current, or None."""
        return _settlement.read_current_evidence(PinnedState(state_data=self.pinned()))

    def handed_back(self) -> tuple:
        """The hand-back's records: the debt and mark, the stamp, and the evidence and approval it retired.

        The debt as the head it replaced and the head it names, beside the
        mark; the stamp as the head checked and the verdict; the evidence as the
        current record's tested commit and target head, and the retirement of
        every history entry; and whether an approval is still recorded.
        """
        pinned = self.pinned()
        debt = pinned.get(REWRITE_DEBT)
        current = self.current_evidence()
        history = _settlement.read_evidence_history(PinnedState(state_data=pinned)) or ()
        return (
            (debt and (debt["previous_head"], debt["rewritten_head"]), pinned.get(HANDED_BACK)),
            (pinned.get(DOCS_CHECKED), pinned.get(DOCS_VERDICT)),
            current and (current.binding.tested_sha, current.binding.target.target_head),
            tuple(entry.retired.value for entry in history),
            pinned.get(_review_subjects.APPROVED_SUBJECT) is not None,
        )


class _ChangedDocsWalk(_ChangedDocsJourney):
    """The report refresh the walk owes, and what a case reads the walk back by, from that report to where it ends."""

    def refreshes(self) -> None:
        """One dispatch whose developer run, should one be asked for, writes `DOCS_REPORT` as a ready report."""
        self.dispatched(_journey.refresh(DOCS_REPORT))

    def assert_refreshed_over(self, approved: str) -> None:
        """A report of the docs commit settled, `approved` left as written, and the refresh told what it is about."""
        settled = self.pinned()[_CURRENT_REPORT]
        self.assertEqual((settled["sha"], settled["revision"]), REFRESHED)
        self.assertEqual(self.pull_request.issue_comments[0].body, approved)
        self.assertIn(APPROVED_REPORT, self.spawned(_journey.REFRESHER)[0])

    def assert_reviewer_handed_the_report(self) -> None:
        """The fresh reviewer was handed the report of the docs commit, and the commit itself."""
        handed = self.spawned(_journey.REVIEWER)[0]
        self.assertIn(f"> {DOCS_REPORT}", handed)
        self.assertIn(DOCS_HEAD, handed)

    def assert_quiet_after(self) -> None:
        """Three more dispatches move, spawn, and tell nothing."""
        standing = self._standing()
        for _ in range(3):
            self.dispatched()
        self.assertEqual(self._standing(), standing)

    def assert_one_of_each(self, head: str = DOCS_HEAD, rounds: int = 1, walked: tuple = DOCUMENTED_AGAIN) -> None:
        """The walk ended in `in_review` on `head` with one run of each role charged, and nothing owed or parked.

        The labels it moved through from the walk on are `walked`. One report
        of `head` on the pull request, settled and the debt it paid gone; no
        notice anywhere saying a report could not be delivered; fresh evidence
        on `head` current; `head` stamped documented by the pass that found
        nothing to change; and `rounds` review rounds spent -- the one the
        hand-back spends, unless a base rewrite put the count back since.
        """
        self.assertEqual(self.labels()[-len(walked):], walked)
        self.assertEqual(self.roles(), ONE_OF_EACH)
        self.assertEqual(self.spent_since(self.charged)[0], len(ONE_OF_EACH))
        documented = ((head, "no_change"), (head, head))
        self.assertEqual(self.handed_back()[1:3], documented)
        bodies = [posted.body for posted in self.pull_request.issue_comments]
        said = bodies + [notice for _, notice in self.github.posted_comments]
        self.assertEqual(sum(DOCS_REPORT in body for body in bodies), 1)
        self.assertFalse(any(_journey.UNDELIVERABLE_NOTICE in body for body in said))
        self._assert_nothing_owed(head, rounds)

    def _assert_nothing_owed(self, head: str, rounds: int) -> None:
        """The report of `head` settled, the debt it paid gone, no park standing, and `rounds` review rounds spent."""
        pinned = self.pinned()
        owed = (pinned[_CURRENT_REPORT]["sha"], pinned[REWRITE_DEBT], pinned[_PARK_REASON])
        self.assertEqual(owed, (head, None, None))
        self.assertEqual(pinned[_REVIEW_ROUND], rounds)

    def _standing(self) -> tuple:
        """Where the issue stands: its label, and how much its pull request and thread were told."""
        told = len(self.pull_request.issue_comments)
        return self.labels()[-1], told, len(self.github.posted_comments)
