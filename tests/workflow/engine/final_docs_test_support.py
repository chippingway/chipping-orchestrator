# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""An approved issue a final docs pass completed on, and the proof its completion is read by.

Built on the evidence world (`verification_evidence_test_support`): a settled
report about the tested commit, the review of it approved, and the evidence
that approval rests on published and settled by the dispatcher's own
reconciliation -- the reviewer's own account of the tested commit, and, where
the approval squashed, that account carried onto the squash as the approval's
squash carries it, copied from the settled artifact -- with the approval's
evidence claim naming it, repointed at the carry as the squash repoints it. A
pass then completes on
the head it was entered on, or publishes the docs commit `DOCS_SHA` over it:
the approval's own evidence RETAINED, a run of the docs commit EXECUTED and
settled, or, under an empty configuration, nothing run at all. The proof is
handed the issue as a caller fetched it before the proof -- a copy of the one
the client serves, so an edit landing on the issue meanwhile is seen only by a
read taken afresh -- and the world can be moved while the proof re-reads the
last artifact it re-reads, as a human editing the issue or pushing to the
pull request meanwhile would.
"""
from __future__ import annotations

import functools
from collections.abc import Callable, Iterator
from copy import copy
from dataclasses import replace
from unittest.mock import patch

from orchestrator import config
from orchestrator.github.verification_evidence import EvidenceSource
from orchestrator.workflow.engine import (
    final_docs_proof as _proof,
    final_docs_records as _final_docs,
    report_evidence_models as _evidence_models,
    review_subjects as _review_subjects,
    verification_record_state as _record_state,
    verification_records as _records,
    verification_settlement_state as _settlement,
)
from orchestrator.workflow.stages.validating import approved_evidence as _approved_evidence
from orchestrator.workflow.stages.validating.review_verdicts import EvidenceClaim, EvidenceUse
from tests.workflow.engine import (
    verification_evidence_test_support as support,
    verification_record_test_support as _record_support,
    verification_world_fixture as _world,
)

DOCS_SHA = _world.DOCS_SHA

DOCS_TREE = _world.DOCS_TREE

FINAL_DOCS = _final_docs.FINAL_DOCS

APPROVED_EVIDENCE = _approved_evidence.APPROVED_EVIDENCE

RETAINED = _final_docs.FinalVerification.RETAINED

EXECUTED = _final_docs.FinalVerification.EXECUTED

UNCONFIGURED = _final_docs.FinalVerification.UNCONFIGURED

# The client's re-read of a verification artifact, which a case intercepts to
# move the world behind it.
REREAD = "reread_verification_artifact"


class FinalDocsCase(support.VerificationEvidenceCase):
    """An issue whose review was approved over settled evidence, entered into its final docs pass.

    `entry_head` is the head the pass was entered on: the tested commit, or
    the squash once the approval squashed; `approval_evidence` is the evidence
    the approval rests on, as it settled, once it is approved.
    """

    def setUp(self) -> None:
        support.VerificationEvidenceCase.setUp(self)
        self.entry_head = support.TESTED_SHA

    def approves(self, *, squashed: bool = False) -> _records.CurrentEvidence:
        """Approve the review over the reviewer's settled evidence, carried onto a squash where `squashed`.

        Returns the evidence the approval rests on, as it settled, which the
        approval's claim names.
        """
        _review_subjects.record_approved(self.state, self.subject)
        self.record(self.binding(source=EvidenceSource.REVIEWER_REPORTED))
        self.reconcile()
        if squashed:
            self.entry_head = support.SQUASHED_SHA
            _carries_onto_the_squash(self)
        current = _settlement.read_current_evidence(self.state)
        self.assertEqual(current.binding.target.target_head, self.entry_head)
        claim = EvidenceClaim(
            EvidenceUse.PUBLISHED, current.receipt, current.revision, current.content_revision,
            passed=current.passed, covers=True,
        )
        self.persists(APPROVED_EVIDENCE, claim.recorded())
        self.approval_evidence = current
        return current

    def completes_as(
        self, verification: _final_docs.FinalVerification, *, squashed: bool,
    ) -> _records.CurrentEvidence:
        """Approve, squashed or not, and complete the docs pass as `verification` says; the approval's evidence.

        RETAINED completes on the entry head over that evidence, EXECUTED
        publishes the docs commit and settles its run, and UNCONFIGURED
        publishes it under an empty configuration with nothing run.
        """
        if verification is UNCONFIGURED:
            self.enterContext(patch.object(config, "VERIFY_COMMANDS", ()))
        approved = self.approves(squashed=squashed)
        if verification is RETAINED:
            self.completes(self.entry_head, verification, approved)
        elif verification is EXECUTED:
            self.runs_the_final_head()
            self.assertFalse(self.reconcile())
        else:
            self.moves_the_head(DOCS_SHA)
            self.completes(DOCS_SHA, verification)
        return approved

    def completes(
        self, final_head: str, verification: _final_docs.FinalVerification, evidence: object = None,
    ) -> _final_docs.FinalDocs:
        """Record and persist the completion of a pass entered on `entry_head` that completed on `final_head`.

        `evidence` names the transaction it rests on -- a pending, current, or
        historical record -- or None for none.
        """
        named = None if evidence is None else _final_docs.FinalEvidence(evidence.receipt, evidence.revision)
        final = _final_docs.FinalDocs(
            self.state.get(_review_subjects.APPROVED_SUBJECT), self.entry_head, final_head, verification, named,
        )
        self.assertTrue(_final_docs.record_final_docs(self.state, final))
        self.gh.write_pinned_state(self.issue, self.state)
        return final

    def runs_the_final_head(self, exit_status: int = 0) -> _records.PendingEvidence:
        """Publish the docs commit and record a run of it, exiting `exit_status`, beside the completion naming it.

        Recorded as the documenting stage records one, and left owed for the
        reconciliation to publish and settle.
        """
        self.moves_the_head(DOCS_SHA)
        approved = self.state.get(_review_subjects.APPROVED_SUBJECT)
        final = _final_docs.FinalDocs(approved, self.entry_head, DOCS_SHA, EXECUTED)
        bound = self.binding(
            target=final.final_target(self.state), tested_sha=DOCS_SHA, tested_tree=DOCS_TREE,
        )
        pending = _record_state.mint_pending_evidence(
            self.state, support.ISSUE_NUMBER, bound, (_record_support.ran(exit_status=exit_status),),
        )
        named = _final_docs.FinalEvidence(pending.receipt, pending.revision)
        self.assertTrue(_final_docs.record_final_docs(self.state, replace(final, evidence=named)))
        self.assertTrue(_record_state.record_pending_evidence(self.state, pending))
        self.gh.write_pinned_state(self.issue, self.state)
        return pending

    def persists(self, key: str, recorded: object) -> None:
        """Write one pinned field over the persisted comment, as another road's write would."""
        self.state = self.gh.read_pinned_state(self.issue)
        self.state.set(key, recorded)
        self.gh.write_pinned_state(self.issue, self.state)

    def verdict(self) -> _evidence_models.ReportEvidence:
        """What the final-documentation proof says of the persisted comment now, over the issue as fetched now.

        The proof holds a copy of the issue the client serves, as a caller
        holds the one it fetched: an edit to `self.issue` while the proof
        runs reaches only the client's own reads.
        """
        self.state = self.gh.read_pinned_state(self.issue)
        fetched = copy(self.issue)
        with self.seams():
            return _proof.final_docs_verdict(replace(support.reading(self), issue=fetched))


def _carries_onto_the_squash(case: FinalDocsCase) -> None:
    """Squash the approved commit and carry the settled evidence onto it, copied, as the approval's squash does."""
    current = _settlement.read_current_evidence(case.state)
    copied = support.posted_artifacts(case)[-1].commands
    case.moves_the_head(support.SQUASHED_SHA)
    carry = _record_state.mint_pending_evidence(
        case.state, support.ISSUE_NUMBER, current.binding.retargeted(support.SQUASHED_SHA), copied,
        current.receipt,
    )
    case.assertTrue(_record_state.record_pending_evidence(case.state, carry))
    case.gh.write_pinned_state(case.issue, case.state)
    case.reconcile()


def moves_during_the_last_read(case: FinalDocsCase, moves: Callable[[FinalDocsCase], object]) -> None:
    """Have `moves` move `case`'s world behind the last artifact re-read the proof takes, for the rest of the case.

    The proof is taken once first, and has to prove, to count its re-reads;
    every re-read after that is the client's own, and `moves` runs as the
    last of a proof's returns.
    """
    reread = getattr(case.gh, REREAD)
    with patch.object(case.gh, REREAD, side_effect=reread) as counted:
        case.assertTrue(case.verdict().proved)
        reads = counted.call_count
    countdown = iter(range(reads - 1, -1, -1))
    moving = functools.partial(_reads_then_moves, reread, functools.partial(moves, case), countdown)
    case.enterContext(patch.object(case.gh, REREAD, side_effect=moving))


def _reads_then_moves(
    reread: Callable,
    moves: Callable[[], object],
    countdown: Iterator[int],
    pull_request: object,
    comment_id: int,
) -> object:
    """Re-read through `reread`, then `moves` where `countdown` says this re-read is the last."""
    found = reread(pull_request, comment_id)
    if next(countdown, None) == 0:
        moves()
    return found
