# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""An issue in review whose final docs pass recorded its completion, seeded as the documenting stage records one.

The world is the readiness proof's (`readiness_test_support`): the approval of
the settled report over the reviewer's passing run of the configured suite,
settled as the current evidence of `HEAD`. The pass behind that approval then
completed one of three ways, its record written by the completion's own
recorder in the current format and nothing else qualifying the head for the
ping -- no docs stamp, and no GitHub approval:

- RETAINED on `HEAD` itself, naming the approval's own evidence as it stands;
- EXECUTED on the docs commit `DOCS_HEAD` pushed over it, verified by a run of
  exactly that commit this orchestrator executed -- recorded beside the
  completion naming it, its artifact posted under this client's login, and
  settled as the reconciliation settles it, the approval's evidence superseded
  into history -- or left owed, or failing, where a case says so;
- UNCONFIGURED on `DOCS_HEAD` under an empty `VERIFY_COMMANDS`, naming nothing.

Each kind is a route `seeded_on` names beside the docs stamp and the GitHub
approval, which it seeds as the readiness world does, so one case runs every
route. The docs commit descends from `HEAD` in the checkout on this host
unless a case says otherwise, and a case can have the world moved behind that
reading -- the last request the completion's proof makes before its last word.
"""
from __future__ import annotations

from dataclasses import replace
from unittest.mock import MagicMock, patch

from orchestrator import config
from orchestrator.github.pinned_state import PinnedState
from orchestrator.github.verification_evidence import EvidenceSource, VerifiedCommand
from orchestrator.workflow.engine import (
    final_docs_records as _final_docs,
    verification_proof as _proof,
    verification_record_state as _record_state,
    verification_records as _records,
    verification_settlement_state as _settlement,
)
from orchestrator.workflow.state import WorkflowLabel
from tests.workflow import published_reports as _published_reports, verified_approvals as _verified
from tests.workflow.git_owners import seam_patch
from tests.workflow.stages.in_review import readiness_test_support as _readiness, ready_ping_test_support as _ping

HEAD = _readiness.HEAD

# The docs commit a pass that published one leaves the pull request on.
DOCS_HEAD = "d0c5c0de" * 5

RETAINED = _final_docs.FinalVerification.RETAINED

EXECUTED = _final_docs.FinalVerification.EXECUTED

UNCONFIGURED = _final_docs.FinalVerification.UNCONFIGURED

KINDS = (RETAINED, EXECUTED, UNCONFIGURED)

# The pinned records a case reads and edits the approval and its completion
# by -- formats live issues carry, so spelled here rather than read off the owner.
COMPLETION = "docs_final_provenance"

APPROVED = "review_approved_subject"

APPROVED_EVIDENCE = "review_approved_evidence"

CURRENT_REPORT = "developer_report_current"

# A run of the docs commit whose suite failed.
FAILED_RUN = (VerifiedCommand(_readiness.SUITE, 1, _readiness.FAILED_OUTPUT),)

# How short a hand edit cuts a commit id.
_ABBREVIATED = 12

# The client requests a case lands a move behind: a comment's post, and the
# re-read of the settled report at its location.
_COMMENT = "comment"

_REPORT_READ = "reread_report_location"

# What the unmergeable park's notice says.
_UNMERGEABLE = "not mergeable"


class CompletionEdits:
    """What a maintainer leaves of the completion and the docs stamps on the pinned comment, as a hand edit would."""

    def damaged(self) -> dict:
        """The completion with its final head cut short, so it no longer reads whole."""
        recorded = dict(self.pinned()[COMPLETION])
        recorded["final_head"] = self.pull_request.head.sha[:_ABBREVIATED]
        return recorded

    def damages_the_completion(self) -> None:
        """Leave the completion cut short on the comment."""
        self.restates(**{COMPLETION: self.damaged()})

    def drops_the_completion(self) -> None:
        """Leave no completion recorded at all, the head and its evidence as the pass left them."""
        self.restates(**{COMPLETION: None})

    def stamps_the_docs(self) -> None:
        """Stamp the docs verdict on the head the pull request stands on, as a docs pass that checked it would."""
        self.restates(docs_checked_sha=self.pull_request.head.sha, docs_verdict="updated")

    def damages_behind_the_park_notice(self) -> None:
        """Cut the completion short once the unmergeable park's notice is posted, as an edit landing then would."""
        behind = _Behind(self, _COMMENT, CompletionEdits.damages_the_completion, _parks)
        self.enterContext(patch.object(self.github, _COMMENT, behind))

    def edits_by_hand(self) -> None:
        """Edit the record the ping over this head rests on: the completion cut short, or else the approval respelled.

        The approval is respelled as of the next report revision, which the
        next tick hands back for review rather than pinging.
        """
        if self.pinned().get(COMPLETION) is not None:
            self.damages_the_completion()
            return
        approved = dict(self.pinned()[APPROVED])
        approved["report_revision"] += 1
        self.restates(**{APPROVED: approved})


class WorldMoves:
    """What an operator, a pusher, a human on the pull request, or git does to a completed pass."""

    def deletes_the_approvals_artifact(self) -> None:
        """A human deleting, from the pull request, the artifact of the evidence the approval rests on."""
        self.pull_request.issue_comments.remove(self.comment_at(self.approval_artifact))

    def configures_the_suite(self) -> None:
        """An operator configuring the suite for the rest of the case, after a pass that ran under none."""
        self.enterContext(patch.object(config, "VERIFY_COMMANDS", (_readiness.SUITE,)))

    def descends_nowhere(self) -> None:
        """The docs commit's history read as not containing the head the pass was entered on."""
        self.descends = False

    def pushes_approved_on_github(self) -> None:
        """A push past the final head, which a human then approves on GitHub."""
        self.pushes()
        self.pull_request.approved = True

    def refreshes_the_report(self) -> None:
        """A later report settled about the head the pull request stands on, over the approved one."""
        _published_reports.republishes_the_report(self.github, self.issue)

    def behind_the_armed_report_read(self, move) -> None:
        """Have `move` made once, behind the first re-read of the settled report over an armed ping.

        That is the last proof's own re-read, behind its check of the
        verification context, so only its last word reads anything after it.
        """
        behind = _Behind(self, _REPORT_READ, move, _armed)
        self.enterContext(patch.object(self.github, _REPORT_READ, behind))

    def behind_the_lineage(self, move) -> None:
        """Have `move` made once, behind the next reading of the final head's lineage."""
        self.owed_moves.append(move)


class _CompletionFixture(CompletionEdits, WorldMoves, _readiness._ReadinessFixture):
    """The readiness world, which a case may seed with a final docs pass's completion qualifying its head alone."""

    def setUp(self) -> None:
        super().setUp()
        self.descends = True
        self.owed_moves = []
        self.enterContext(seam_patch("_descends", MagicMock(side_effect=_Lineage(self))))

    def seeded_on(self, route: str) -> None:
        """Seed `route`: a pass completed as the kind it names, or a docs stamp or GitHub approval of `HEAD`."""
        if route in KINDS:
            self.completed(_final_docs.FinalVerification(route))
        else:
            super().seeded_on(route)

    def completed(
        self, kind: _final_docs.FinalVerification, run: tuple | None = None, *, settled: bool = True,
    ) -> None:
        """Seed the approval's world with the pass behind it completed as `kind`, and nothing else qualifying the head.

        EXECUTED records `run` of the docs commit -- the passing suite by
        default -- settled where `settled` and left owed otherwise.
        """
        if kind is UNCONFIGURED:
            self.enterContext(patch.object(config, "VERIFY_COMMANDS", ()))
        self.seeded()
        self.pull_request.approved = False
        state = self.github.read_pinned_state(self.issue)
        current = _settlement.read_current_evidence(state)
        self.approval_artifact = current.comment_id
        final = _final_docs.FinalDocs(
            state.get(APPROVED), HEAD, HEAD, kind, _final_docs.FinalEvidence(current.receipt, current.revision),
        )
        if kind is not RETAINED:
            self.pull_request.head.sha = DOCS_HEAD
            final = replace(final, final_head=DOCS_HEAD, evidence=None)
        if kind is EXECUTED:
            state = self._executes(state, final, run or _verified.passing_run(), settled=settled)
        elif not _final_docs.record_final_docs(state, final):
            raise AssertionError("the pinned comment would not record the completion")
        self.restates(**state.data)

    def withheld_after(self, kind: _final_docs.FinalVerification, moves: tuple, **options) -> None:
        """Complete `kind` as `options` say, make each of `moves`, and tick: the ping is withheld.

        The case is set up afresh behind it, for the next.
        """
        self.completed(kind, **options)
        for move in moves:
            move(self)
        before = self.standing()
        self.tick()
        self.assert_withheld(before)
        self.doCleanups()
        self.setUp()

    def approval_records(self) -> tuple:
        """The approved subject, the evidence claim beside it, and the settled report, as the comment holds them."""
        pinned = self.pinned()
        return (pinned[APPROVED], pinned[APPROVED_EVIDENCE], pinned[CURRENT_REPORT])

    def _executes(self, state: PinnedState, final, commands: tuple, *, settled: bool) -> PinnedState:
        """`state` with a run of `commands` on the docs commit recorded beside `final` naming it, settled or owed."""
        bound = _records.EvidenceBinding(
            target=final.final_target(state),
            source=EvidenceSource.ORCHESTRATOR_EXECUTED,
            tested_sha=DOCS_HEAD,
            tested_tree=_verified.TREE,
            context_revision=_proof.configured_context_revision(),
        )
        pending = _record_state.mint_pending_evidence(state, self.issue.number, bound, commands)
        named = replace(final, evidence=_final_docs.FinalEvidence(pending.receipt, pending.revision))
        if not (_final_docs.record_final_docs(state, named) and _record_state.record_pending_evidence(state, pending)):
            raise AssertionError("the pinned comment would not record the run of the docs commit")
        return _verified.settles(self.github, state, pending, WorkflowLabel.DOCUMENTING) if settled else state


class _Lineage:
    """Whether the docs commit descends from the entry head, as the case has it, every move it owes made first."""

    def __init__(self, case) -> None:
        self._case = case

    def __call__(self, *_asked) -> bool:
        owed = self._case.owed_moves
        self._case.owed_moves = []
        for move in owed:
            move(self._case)
        return self._case.descends


class _Behind:
    """A client request answered as always, `move` made on the case once behind the first one `when` accepts."""

    def __init__(self, case, request: str, move, when) -> None:
        self._case = case
        self._asked = getattr(case.github, request)
        self._move = move
        self._when = when
        self._moved = False

    def __call__(self, *asked, **named):
        answered = self._asked(*asked, **named)
        if not self._moved and self._when(self._case, *asked):
            self._moved = True
            self._move(self._case)
        return answered


def _armed(case, *_asked) -> bool:
    """Whether `case`'s pinned comment records a ping armed and not yet made."""
    return isinstance(case.pinned().get(_ping.PENDING), dict)


def _parks(_case, _issue, body: str) -> bool:
    """Whether `body`, posted on the issue, is the unmergeable park's notice."""
    return _UNMERGEABLE in body
