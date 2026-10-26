# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""An approval handed to its final-docs pass, whose docs commit changes the pull request, walked on into review.

The round walked past its approval (`squash_rebase_journey_support`): the
reviewer approves the report settled about `HEAD` on its own run of the
configured suite, and the approval either squashes -- publishing `SQUASHED` on
the same tree, carrying the approved run onto it, and moving the label to
`workflow:documenting` once the carry settles -- or, with
`SQUASH_ON_APPROVAL` off, hands `HEAD` itself to the pass. There the docs pass
commits `DOCS_HEAD` on top of the head it was entered on, the push lands, and
the configured suite is run on exactly that commit (`docs_run`): the run the
completion records beside the approval, which the reconciliation of the next
tick publishes and settles. Every tick from there is a whole dispatch of
whatever label the issue carries, and every run a dispatch spawns is recorded
by role with the prompt it was handed (`spawned`). The docs commit is read as
descending from the head the pass was entered on, as it does in a checkout the
pass committed in.

A case reads the walk back through `completed` -- the completion the pass
recorded, the stamp beside it, and the report debt none of it owes -- and
through `approved`, the approval's own records as the next tick reads them,
which nothing past the approval may move. Where the walk ends is read by the
assertions of `_ChangedDocsWalk`: in review, told once, with no reviewer or
report refresh launched behind the approval.
"""
from __future__ import annotations

import contextlib
from unittest.mock import MagicMock

from orchestrator import config
from orchestrator.github.verification_evidence import EvidenceSource
from orchestrator.workflow.engine import final_docs_records as _final_docs, review_subjects as _review_subjects
from orchestrator.workflow.state import WorkflowLabel
from tests.workflow import drift_reports as _drift_world
from tests.workflow.fixtures import _agent
from tests.workflow.git_owners import seam_patch
from tests.workflow.stages.validating import (
    changed_docs_readings as _readings,
    readiness_journey_support as _readiness,
    squash_rebase_journey_support as _journey,
)

HEAD = _journey.HEAD

SQUASHED = _journey.SQUASHED

# The docs commit the final-docs pass publishes on top of the head it was
# entered on: the commit the size gate proves the checkout to once its subject
# names the pull request.
DOCS_HEAD = _readings.DOCS_HEAD

# A docs pass that committed a docs change.
DOCS_CHANGED = (_journey.DOCUMENTER, _agent(last_message="docs: describe the new flag"))

# The pinned records the walk is read back by.
REWRITE_DEBT = "developer_report_rewrite_debt"

DOCS_VERDICT = "docs_verdict"

DOCS_CHECKED = "docs_checked_sha"

CURRENT_REPORT = "developer_report_current"

REVIEW_ROUND = "review_round"

_PARK_REASON = "park_reason"

_READY_PING_SHA = "ready_ping_sha"

# A ready ping as the walk's timeline tells it.
_PINGED = (_readiness.READY,)

# The labels a walk moves through from the docs pass on: straight into review.
INTO_REVIEW = (WorkflowLabel.DOCUMENTING, WorkflowLabel.IN_REVIEW)

# What the walk tells from the docs pass on, in order: the docs pass spawned,
# the artifact of this orchestrator's own run of the docs commit, and the ready
# ping last.
DOCUMENTED_INTO_REVIEW = (
    (_readiness.SPAWN, _journey.DOCUMENTER),
    (_readiness.ARTIFACT, EvidenceSource.ORCHESTRATOR_EXECUTED, DOCS_HEAD, DOCS_HEAD),
    (_readiness.READY,),
)

# The same under an empty `VERIFY_COMMANDS`, which runs and publishes nothing.
DOCUMENTED_UNVERIFIED = (
    (_readiness.SPAWN, _journey.DOCUMENTER),
    (_readiness.READY,),
)
class _ChangedDocsJourney(_journey._SquashRebaseJourney):
    """The approved round walked into its final-docs pass, which publishes a docs commit."""

    def setUp(self) -> None:
        super().setUp()
        self.enterContext(seam_patch("_descends", MagicMock(return_value=True)))

    def walks_into_documenting(self) -> None:
        """Approve -- and, where the approval squashes, settle the carry -- leaving the label on documenting.

        Nothing spawned on the way is kept, and what the issue has spent by
        then is `charged`, so a case reads its runs and charges from here on;
        how far the threads were told by then is `walked`, which a case reads
        the timeline from; and the approval's records as they stand then are
        `approval`, which nothing past it may move.
        """
        self.approves(None if config.SQUASH_ON_APPROVAL else _readings.leaves_the_branch)
        self.settles_the_approval()

    def settles_the_approval(self) -> None:
        """Settle the carry an approval's squash owes, where it squashed, and keep what the walk reads from."""
        if config.SQUASH_ON_APPROVAL:
            self.later()
        self.spawns.clear()
        self.charged = self.spent()
        self.walked = _readiness.high_water(self)
        self.approval = self.approved()

    def changes_the_docs(self, push=None, verified=None, **run_options) -> None:
        """One dispatch of the docs pass, committing `DOCS_HEAD`; its push lands and its run passes unless told.

        `run_options` are the dispatch's own readings beside those.
        """
        entered = self.pull_request.head.sha
        self.dispatched(
            DOCS_CHANGED,
            head_shas=(entered, DOCS_HEAD),
            push_branch=push or _drift_world._LandingPush(self.pull_request),
            verify_result=_readings.docs_run() if verified is None else verified,
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
        self.dispatched(verify_result=_readings.docs_run())

    def approved(self) -> tuple:
        """The approval's records: the approved subject, the settled report, and the review rounds spent."""
        pinned = self.pinned()
        return (
            pinned.get(_review_subjects.APPROVED_SUBJECT),
            pinned.get(CURRENT_REPORT),
            pinned.get(REVIEW_ROUND),
        )



class _ChangedDocsWalk(_ChangedDocsJourney):
    """What a case reads the walk back by, from the docs pass to where it ends."""

    def entered_on(self) -> str:
        """The head the docs pass is entered on: the squash, or the approved commit where nothing squashed."""
        return SQUASHED if config.SQUASH_ON_APPROVAL else HEAD

    def assert_documented_into_review(
        self, verification=_final_docs.FinalVerification.EXECUTED, told=DOCUMENTED_INTO_REVIEW,
    ) -> None:
        """The walk ended in `in_review` on `DOCS_HEAD`, told once, with the approval exactly as it was.

        The completion records the head the pass was entered on and the docs
        commit, verified as `verification`; the commit is stamped `updated`;
        no report is owed; the approved subject, the settled report, and the
        review rounds spent are the approval's own; the only run spawned past
        the approval is the docs pass, charged once; and the walk told the
        pull request `told`, the ready ping last and once.
        """
        completion = ((verification.value, self.entered_on(), DOCS_HEAD), (DOCS_HEAD, "updated"), None)
        self.assertEqual(self.completed(), completion)
        self.assertEqual(self.labels()[-len(INTO_REVIEW):], INTO_REVIEW)
        self.assert_only_documented()
        self.assert_told_once(told, DOCS_HEAD)

    def assert_only_documented(self) -> None:
        """The approval's records exactly as it left them, and the docs pass the one run spawned and charged past it."""
        self.assertEqual(self.approved(), self.approval)
        self.assertEqual(self.roles(), (_journey.DOCUMENTER,))
        self.assertEqual(self.spent_since(self.charged)[0], 1)

    def assert_told_once(self, told: tuple, head: str) -> None:
        """The walk told the pull request `told`, the ready ping on `head` last and once, with no park standing."""
        walk = self.told(self.walked)
        pinged = walk.count(_PINGED)
        self.assertEqual(walk[-len(told):], told)
        self.assertEqual(pinged, 1)
        pinned = self.pinned()
        self.assertEqual(pinned.get(_READY_PING_SHA), head)
        self.assertIsNone(pinned.get(_PARK_REASON))

    def completed(self) -> tuple:
        """The completion as its verification, entry head, and final head; the stamp; and the report debt."""
        pinned = self.pinned()
        recorded = pinned.get(_final_docs.FINAL_DOCS) or {}
        return (
            (recorded.get("verification"), recorded.get("entry_head"), recorded.get("final_head")),
            (pinned.get(DOCS_CHECKED), pinned.get(DOCS_VERDICT)),
            pinned.get(REWRITE_DEBT),
        )

    def assert_quiet_into_review(self) -> None:
        """Three more dispatches move, spawn, verify, write, and tell nothing, the issue still in review."""
        self.assert_quiet()
        self.assertEqual(self.github.workflow_label(self.issue), WorkflowLabel.IN_REVIEW)
