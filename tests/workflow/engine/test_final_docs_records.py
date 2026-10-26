# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A final-documentation completion is read whole or not at all, and licenses only the run it names.

Each verification round-trips through the pinned comment's own rendering and
parser exactly as written. Every member missing, added, or spelled otherwise
than its writer spells it -- a head abbreviated, an approval nothing
identifies, a verification this build does not name, evidence where none is
owed or missing where some is, a receipt minted under another revision, heads
equal where they must differ or differing where they must not -- reads as no
completion, and a staging that would not read back whole is refused with
nothing staged.

An EXECUTED completion is the one record that lets a run answer for the
approved review at another head than the one reviewed: only an
orchestrator-executed run tested on exactly its final head, on the settled
report's publication -- a run moved onto another branch, or with no settled
report to bind it to, licenses nothing -- over exactly the approval this
issue records -- read whole, so an approval respelled with a `true` or a
float where a number belongs, which `==` would take for the number, licenses
nothing.
"""
from __future__ import annotations

import unittest
import uuid
from dataclasses import replace

from orchestrator.github.pinned_state import PinnedState
from orchestrator.github.verification_evidence import EvidenceSource
from orchestrator.workflow.engine import (
    final_docs_records as _final_docs,
    report_records as _report_records,
    report_settlement_state as _report_settlement,
    review_subjects as _review_subjects,
    verification_records as _records,
)
from tests.workflow.engine import verification_record_test_support as support, verification_world_fixture as _world

APPROVED = support.SUBJECT.recorded()

# The transaction the completions here rest on, by its revision and receipt.
REVISION = 3

RECEIPT = _records.RECEIPT.format(
    issue=support.ISSUE_NUMBER, revision=REVISION, nonce=uuid.UUID(int=0).hex,
)

EVIDENCE = _final_docs.FinalEvidence(RECEIPT, REVISION)

# How short an abbreviated commit id is cut, and requirements no approval here was given.
_ABBREVIATED = 12

_OTHER_REQUIREMENTS = "0" * len(support.REQUIREMENTS)

# The report the approved review was handed, settled on the pull request's branch.
_SETTLED = _report_records.CurrentReport(
    subject=support.TARGET.publication,
    report_revision=support.SUBJECT.report.report_revision,
    content_revision=support.SUBJECT.report.content_revision,
    location=support.SUBJECT.report.location,
)

# One completion of each verification, as its writer stages it.
_COMPLETIONS = (
    _final_docs.FinalDocs(
        APPROVED, support.TESTED_SHA, support.TESTED_SHA, _final_docs.FinalVerification.RETAINED, EVIDENCE,
    ),
    _final_docs.FinalDocs(
        APPROVED, _world.SQUASHED_SHA, _world.DOCS_SHA, _final_docs.FinalVerification.EXECUTED, EVIDENCE,
    ),
    _final_docs.FinalDocs(APPROVED, support.TESTED_SHA, _world.DOCS_SHA, _final_docs.FinalVerification.UNCONFIGURED),
)

_EXECUTED = _COMPLETIONS[1].recorded()

# Every way a recorded completion is not one its writer wrote, each a change
# to the EXECUTED completion's record.
_DAMAGE = (
    ("a member missing", lambda recorded: recorded.pop("evidence")),
    ("a member added", lambda recorded: recorded.update(extra=1)),
    ("an abbreviated head", lambda recorded: recorded.update(final_head=_world.DOCS_SHA[:_ABBREVIATED])),
    ("a head that is no commit id", lambda recorded: recorded.update(entry_head=None)),
    ("an approval nothing identifies", lambda recorded: recorded.update(approved=dict(APPROVED, sha=None))),
    ("an approval of no report", lambda recorded: recorded.update(
        approved=dict(APPROVED, report_revision=None, report_content=None),
    )),
    ("a verification this build does not name", lambda recorded: recorded.update(verification="passed")),
    ("a verification nothing hashes", lambda recorded: recorded.update(verification=["executed"])),
    ("no evidence where some is owed", lambda recorded: recorded.update(evidence=None)),
    ("a receipt of another revision", lambda recorded: recorded.update(
        evidence={"receipt": RECEIPT, "revision": REVISION + 1},
    )),
    ("evidence of a member too many", lambda recorded: recorded.update(
        evidence={"receipt": RECEIPT, "revision": REVISION, "passed": True},
    )),
    ("evidence where none is owed", lambda recorded: recorded.update(verification="unconfigured")),
    ("a changed head called retained", lambda recorded: recorded.update(verification="retained")),
    ("an unchanged head called executed", lambda recorded: recorded.update(final_head=_world.SQUASHED_SHA)),
)


class FinalDocsReadingTest(unittest.TestCase):
    """What a completion record reads as."""

    def test_each_verification_round_trips(self) -> None:
        for final in _COMPLETIONS:
            with self.subTest(final.verification):
                state = PinnedState(comment_id=1, state_data={})
                self.assertTrue(_final_docs.record_final_docs(state, final))

                self.assertEqual(_final_docs.read_final_docs(support.reread(state)), final)

    def test_a_damaged_record_reads_as_none(self) -> None:
        for damage, damages in _DAMAGE:
            with self.subTest(damage):
                recorded = dict(_EXECUTED)
                damages(recorded)

                self.assertIsNone(_final_docs.FinalDocs.read(recorded))

    def test_an_unreadable_completion_is_not_staged(self) -> None:
        state = PinnedState(comment_id=1, state_data={})
        final = replace(_COMPLETIONS[1], evidence=None)

        self.assertFalse(_final_docs.record_final_docs(state, final))
        self.assertFalse(state.carries(_final_docs.FINAL_DOCS))


class FinalHeadLicenseTest(unittest.TestCase):
    """Which bindings an EXECUTED completion lets answer for the approved review."""

    def setUp(self) -> None:
        self.state = PinnedState(comment_id=1, state_data={_review_subjects.APPROVED_SUBJECT: APPROVED})
        self.assertTrue(_report_settlement.record_current_report(self.state, _SETTLED))
        _final_docs.record_final_docs(self.state, _COMPLETIONS[1])
        # The run of the docs commit, answering for it over the approved review.
        publication = replace(support.TARGET.publication, source_sha=_world.DOCS_SHA)
        self.run = support.binding(
            target=replace(support.TARGET, publication=publication), tested_sha=_world.DOCS_SHA,
        )

    def test_only_its_final_head_run_is_licensed(self) -> None:
        other_head = replace(self.run.target.publication, source_sha=_world.REBASED_SHA)
        other_branch = replace(self.run.target.publication, branch=f"{support.BRANCH}-renamed")
        refused = (
            ("a reviewer's account", replace(self.run, source=EvidenceSource.REVIEWER_REPORTED)),
            ("a run of another commit", replace(self.run, tested_sha=support.TESTED_SHA)),
            ("a run answering for another head", replace(
                self.run, target=replace(self.run.target, publication=other_head),
            )),
            ("a run on another branch", replace(
                self.run, target=replace(self.run.target, publication=other_branch),
            )),
            ("a run over another review", replace(
                self.run, target=replace(self.run.target, subject=dict(APPROVED, requirements=_OTHER_REQUIREMENTS)),
            )),
        )

        self.assertTrue(_final_docs.answers_for(self.state, self.run))
        for named, binding in refused:
            with self.subTest(named):
                self.assertFalse(_final_docs.answers_for(self.state, binding))

    def test_no_license_without_its_completion(self) -> None:
        moves = (
            ("no completion", lambda state: state.set(_final_docs.FINAL_DOCS, None)),
            ("no settled report", lambda state: state.set(_report_records.CURRENT_REPORT, None)),
            ("a completion resting on no run", lambda state: _final_docs.record_final_docs(state, _COMPLETIONS[2])),
            ("the approval retired", lambda state: state.set(_review_subjects.APPROVED_SUBJECT, None)),
            ("the approval respelled true", lambda state: state.set(
                _review_subjects.APPROVED_SUBJECT, dict(APPROVED, report_revision=True),
            )),
            ("the approval respelled a float", lambda state: state.set(
                _review_subjects.APPROVED_SUBJECT, dict(APPROVED, pr=float(support.PR_NUMBER)),
            )),
        )
        for named, moves_it in moves:
            with self.subTest(named):
                self.setUp()
                moves_it(self.state)

                self.assertFalse(_final_docs.answers_for(self.state, self.run))


if __name__ == "__main__":
    unittest.main()
