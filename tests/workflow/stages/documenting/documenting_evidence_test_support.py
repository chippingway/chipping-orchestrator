# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A docs pass that changed nothing, over an approval whose verification evidence it may retain.

The world is the shared approval journey (`tests/workflow/approved_squash.py`),
ticked whole by the dispatcher: a reviewer approves with a passing run, the
squash publishes an equivalent tree, the reconciliation settles the carry onto
it, and the label moves here. A docs tick is the dispatcher's too, its agent a
pass replying `DOCS: NO_CHANGE` -- having first done another road's work where
a case names some (`documents`), so the change lands while the pass is out.
Every commit reads as the tested tree unless a case stands another in for one.
What a case moves meanwhile, a request that stops answering, and what the
pinned comment and pull request say afterwards are spelled here too.
"""
from __future__ import annotations

from contextlib import ExitStack
from dataclasses import replace
from functools import partial
from unittest.mock import MagicMock, patch

from orchestrator.git.verification import probes as _verification_probes
from orchestrator.github import pinned_state as _pinned_state, verification_artifacts as _artifacts
from orchestrator.workflow.engine import (
    report_settlement_state as _report_settlement,
    verification_records as _records,
    verification_settled_fields as _settled_fields,
    verification_settlement_state as _settlement,
)
from tests.support import agy_stream
from tests.workflow import (
    approved_squash as _approved_squash,
    published_reports as _published_reports,
    review_world as _world,
)
from tests.workflow.fixtures import _agent
from tests.workflow.git_owners import seam_patch

DOCS_NO_CHANGE = "Inspected the diff; nothing to document.\nDOCS: NO_CHANGE"

# What every notice a docs pass posts on the pull request opens with.
DOCS_NOTICE = ":books: documenting pass"

# The pinned records a case reads back, spelled as the comment spells them.
DOCS_VERDICT = "docs_verdict"
CHECKED_DOCS_SHA = "docs_checked_sha"
CURRENT_EVIDENCE = "verification_evidence_current"
CURRENT_REPORT = "developer_report_current"
APPROVED_SUBJECT = "review_approved_subject"
LAUNCHED_DOCS_SHA = "docs_launched_sha"
PARK_REASON = "park_reason"

# The records the issue's locked developer session is named by.
_DEV_AGENT = "dev_agent"
_DEV_SESSION_ID = "dev_session_id"

# What a human edits the report, the issue, and the artifact to say.
EDITED_REPORT = "Implemented something else entirely."
EDITED_BODY = "An edited body nobody reviewed."
FAILED_OUTPUT = "1 failed"

# What a request that stops answering raises, and the git seams a tree and an object's kind are read through.
_UNANSWERED = "the request went unanswered"

TREE_READ = "_tree_sha"

LOOKUP = "_object_kind"

# A tree read git could not even be started for, which raises rather than answering.
UNSTARTED_TREE_READ = "an unstarted tree read"


def merges(case) -> None:
    """A human merging the pull request."""
    case.pull_request.merged = True
    case.pull_request.state = "closed"


def rewrites(case, edited: dict) -> None:
    """A human rewriting each record of the pinned comment `edited` names to the value beside it, in one edit."""
    state = case.github.read_pinned_state(case.issue)
    for record, edited_value in edited.items():
        state.set(record, edited_value)
    case.github.write_pinned_state(case.issue, state)


def records_instead(case, commands: tuple) -> None:
    """A hand edit leaving the current evidence carrying `commands`, and the approval's claim on it gone.

    The record and its artifact both: the artifact rendered afresh in the
    current format, and the record's digest and pass flag the ones those
    commands earn, so each still describes the other and the evidence proves
    current.
    """
    state = case.github.read_pinned_state(case.issue)
    current = _settlement.read_current_evidence(state)
    rerun = _records.PendingEvidence(
        receipt=current.receipt, revision=current.revision, binding=current.binding, commands=commands,
    )
    case._comment_at(current.comment_id).body = _artifacts.render_verification_artifact(rerun.artifact)
    state.set(CURRENT_EVIDENCE, _settled_fields.current_object(
        replace(current, content_revision=rerun.content_revision, passed=rerun.passed),
    ))
    state.set(_approved_squash.APPROVED_EVIDENCE, None)
    case.github.write_pinned_state(case.issue, state)


def _documents_after(case, during, *_asked, **_options):
    """The docs pass's run: `during` done on `case` first, where given, then the no-change reply."""
    if during is not None:
        during(case)
    return _agent(session_id=_world.DEV_SESSION, last_message=DOCS_NO_CHANGE)


class Unanswered:
    """A reading that stops answering once the docs agent has run, until the case `answers` it again.

    `request` names the client request that then raises; without one, the
    pull request's thread stops answering, which a re-read of the report or
    the artifact on it reports as unconfirmed rather than raising. `TREE_READ`
    is git's reading of the squashed head's tree instead, which then answers
    nothing for a commit the repository still holds; `UNSTARTED_TREE_READ`
    is that reading raising, git not started at all; `LOOKUP` is git's lookup
    of what an id names, behind a presence probe that answers no for it.
    """

    def __init__(self, request: str | None = None) -> None:
        self._request = request
        self._patches = ExitStack()

    def __call__(self, case) -> None:
        if self._request == TREE_READ:
            case.trees[_approved_squash.SQUASHED] = ""
        elif self._request == UNSTARTED_TREE_READ:
            unstarted = MagicMock(side_effect=OSError(_UNANSWERED))
            self._patches.enter_context(seam_patch(TREE_READ, unstarted))
        elif self._request == LOOKUP:
            # The tick's own stand-in for the presence probe, which answers no
            # on any failure; patched here instead, it would be restored over
            # the real probe once the tick's own stand-ins come off.
            _verification_probes._commit_present.return_value = False
            self._patches.enter_context(seam_patch(LOOKUP, lambda *_asked: None))
        elif self._request is None:
            _world.stops_answering(case)
        else:
            refused = MagicMock(side_effect=RuntimeError(_UNANSWERED))
            self._patches.enter_context(patch.object(case.github, self._request, refused))

    def answers(self, case) -> None:
        """Answer the reading again, as GitHub or git does once it recovers."""
        if self._request == TREE_READ:
            case.trees.pop(_approved_squash.SQUASHED)
        elif self._request is None:
            case.github.report_failures.unreadable.discard(_world.PR)
        self._patches.close()


class EvidenceMoves:
    """What another road does while the docs pass is out: each a move of one thing the evidence answers for."""

    def another_tree(self) -> None:
        """The squashed head read as a tree no evidence was gathered on."""
        self.trees[_approved_squash.SQUASHED] = _approved_squash.OTHER_TREE

    def edits_the_requirements(self) -> None:
        """A human editing the issue's body."""
        self.issue.body = EDITED_BODY

    def edits_the_report(self) -> None:
        """A human editing the settled developer report in place, at its location."""
        report = _report_settlement.read_current_report(_pinned_state.PinnedState(state_data=self.pinned()))
        posted = self._comment_at(report.location.comment_id)
        posted.body = posted.body.replace(_published_reports.DELIVERED_REPORT, EDITED_REPORT)

    def edits_the_artifact(self) -> None:
        """A human editing the current evidence's artifact to report a failure."""
        posted = self._comment_at(self._artifact_id())
        posted.body = posted.body.replace(_world.SUITE_OUTPUT, FAILED_OUTPUT)

    def deletes_the_artifact(self) -> None:
        """A human deleting the current evidence's artifact from the pull request."""
        self.pull_request.issue_comments.remove(self._comment_at(self._artifact_id()))

    def _artifact_id(self) -> int:
        """The comment the current evidence settled as."""
        return _settlement.read_current_evidence(_pinned_state.PinnedState(state_data=self.pinned())).comment_id

    def _comment_at(self, comment_id: int):
        """The pull request's comment `comment_id` names."""
        return next(posted for posted in self.pull_request.issue_comments if posted.id == comment_id)


class EvidenceWorld(_approved_squash.ApprovedSquashWorld, EvidenceMoves):
    """An issue whose approval's squash carried its evidence onto the head, ticked on into the docs pass."""

    def setUp(self) -> None:
        super().setUp()
        # The tree each commit reads as where a case stood one in; the tested
        # tree everywhere else.
        self.trees: dict[str, str] = {}
        self.enterContext(seam_patch("_tree_sha", self._tree_of))

    def squashed(self) -> None:
        """The approval, its squash published, and the carry settled with the label moved here."""
        self.approves()
        self.later()

    def documents(self, during=None, **run_options) -> dict:
        """One dispatcher tick on the docs pass, over the head the pull request stands on as it opens.

        `during` is another road's work while the agent is out.
        """
        head = self.pull_request.head.sha
        run_options.setdefault("checkout_tree", None)
        return _approved_squash.dispatches(
            self, self.github, self.issue, head,
            run_agent=MagicMock(side_effect=partial(_documents_after, self, during)),
            head_shas=(head,),
            **run_options,
        )

    def runs_on_antigravity(self) -> None:
        """The issue's developer session locked to Antigravity, whose every docs launch lands its record first."""
        rewrites(self, {_DEV_AGENT: agy_stream.SPEC, _DEV_SESSION_ID: agy_stream.SESSION_ID})

    def retained(self) -> tuple:
        """The current evidence, the current developer report, and the approval, as the pinned comment carries them."""
        pinned = self.pinned()
        return pinned.get(CURRENT_EVIDENCE), pinned.get(CURRENT_REPORT), pinned.get(APPROVED_SUBJECT)

    def announced(self) -> bool:
        """Whether a docs pass told the pull request anything."""
        return any(DOCS_NOTICE in posted.body for posted in self.pull_request.issue_comments)

    def _tree_of(self, _worktree, commit: str) -> str:
        return self.trees.get(commit, _world.TREE)
