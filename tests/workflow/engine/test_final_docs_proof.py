# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A final-documentation completion proves its final head only while every link it names is proved apart.

Each verification proves, with the approval squashed and not -- and squashed
after a round an operator's grant bought, whose approval is under the
requirements through that grant while its report keeps the ones it was
written against: the approval's
own evidence of the unchanged head, retained with its own provenance; a run
of the docs commit this orchestrator executed, published and settled by the
dispatcher's reconciliation; and, under an empty configuration, nothing run
and nothing claimed. Whichever, the approved review, the settled report, its
source commit, and the evidence the approval rests on stay exactly as they
were, and no artifact names the docs commit as the head reviewed or a run as
one on a commit it did not run on.

Then each case moves exactly one link and the proof refuses -- holding only
where a reading could not be taken -- and writes and posts nothing: the record
missing or damaged, the approval retired or respelled where its reader refuses
it, the approval's evidence claim damaged, gone, naming other evidence, or
saying it failed -- refused off the pinned comment before any request -- that
evidence moved onto another branch, current or in history, the run of the
final head or the retained evidence moved onto another branch with the pull
request, the review subject
it answers for no longer recorded as it was, invalidated,
outranked by newer evidence, its handoff damaged, other
evidence recorded between it and the run of the final head, its artifact
deleted, edited, or unread, or its configuration moved, the report refreshed
or owed, the requirements edited, the
pull request pushed, the configuration moved or added, the artifact gone or
unread, a run still owed or failing, the entry head linked to no squash, and a
final head not descending from it. Every artifact the proof re-reads is
asked ahead of the readings an edit or a push would move -- the issue read
afresh behind them, since the one the proof is handed was fetched before --
so the issue edited or the pull request pushed while the last of them is read
refuses too, and an issue that would not read again holds.
"""
from __future__ import annotations

import itertools
import unittest
from functools import partial
from operator import methodcaller
from typing import NamedTuple
from unittest.mock import patch

from orchestrator import config
from orchestrator.github.pull_request_reports import ReportPresence
from orchestrator.github.verification_evidence import EvidenceSource
from orchestrator.workflow.engine import (
    report_records as _report_records,
    report_settlement_state as _report_settlement,
    review_subjects as _review_subjects,
    verification_records as _records,
    verification_settlement_state as _settlement,
)
from tests.workflow.engine import (
    final_docs_test_support as final_support,
    verification_evidence_test_support as support,
    verification_reply_round_fixture as _reply_round,
    verification_report_fixture as _report,
)

_KINDS = (final_support.RETAINED, final_support.EXECUTED, final_support.UNCONFIGURED)

_LINT = "uv run ruff check orchestrator tests"

# How short an abbreviated commit id is cut, and how long a digest is.
_ABBREVIATED = 12

_DIGEST_LENGTH = 64

# The docs commit's id abbreviated, and a digest no evidence here carries.
_ABBREVIATED_DOCS = final_support.DOCS_SHA[:_ABBREVIATED]

_OTHER_DIGEST = "0" * _DIGEST_LENGTH

# A branch the settled report was not published to.
_OTHER_BRANCH = f"{support.BRANCH}-different"

# Why an approval no longer recorded as the completion names it, and its
# evidence claim no longer the one it was given, refuse a completion.
_UNAPPROVED = "no longer the one this issue records"

_UNCLAIMED = "evidence claim does not read, pass, and name the evidence it rests on"

# Why the artifact of the evidence the approval rests on refuses a completion.
_UNSHOWN = "is gone or no longer the one that settled"

_UNREAD_ARTIFACT = (ReportPresence.UNCONFIRMED, None)

# The case's own write of one pinned field (`FinalDocsCase.persists`).
_PERSISTS = "persists"


class _Move(NamedTuple):
    """One moved link: what it is, the completion it moves, the move, whether it holds, and what it says."""

    moved: str
    verification: object
    squashed: bool
    moves: object
    holds: bool
    refusal: str


def _respells(case, key: str, member: str, respelled: object) -> None:
    """Respell one member of what `key` records as `respelled`, as a hand edit would."""
    recorded = dict(case.gh.read_pinned_state(case.issue).get(key))
    recorded[member] = respelled
    case.persists(key, recorded)


def _refreshes_the_report(case) -> None:
    """Settle a later report about the docs commit, as a report refresh would."""
    case.state = case.gh.read_pinned_state(case.issue)
    _report.settles_report(case, 2, _report.LATER_REPORT_TEXT, reviewed=False, head=final_support.DOCS_SHA)
    case.gh.write_pinned_state(case.issue, case.state)


def _links_no_squash(case) -> None:
    """Record the completion as entered on the squash, which no carry of this approval names."""
    case.entry_head = support.SQUASHED_SHA
    case.completes(final_support.DOCS_SHA, final_support.UNCONFIGURED)


def _touches_the_artifact(case, *, approval: bool = False, edited: str = "") -> None:
    """Delete an artifact from the pull request, or replace its body with `edited`, as a human would.

    The current evidence's artifact, or, where `approval`, the one the
    evidence the approval rests on settled as.
    """
    case.state = case.gh.read_pinned_state(case.issue)
    record = case.approval_evidence if approval else _settlement.read_current_evidence(case.state)
    posted = next(
        comment for comment in case.pull_request.issue_comments if comment.id == record.comment_id
    )
    if edited:
        posted.body = edited
    else:
        case.pull_request.issue_comments.remove(posted)


_MOVES = (
    _Move(
        "no completion is recorded", final_support.EXECUTED, True,
        methodcaller(_PERSISTS, final_support.FINAL_DOCS, None),
        False, "no readable final-documentation completion",
    ),
    _Move(
        "the completion was edited", final_support.EXECUTED, True,
        partial(_respells, key=final_support.FINAL_DOCS, member="final_head", respelled=_ABBREVIATED_DOCS),
        False, "no readable final-documentation completion",
    ),
    _Move(
        "the approval was retired", final_support.EXECUTED, True,
        methodcaller(_PERSISTS, _review_subjects.APPROVED_SUBJECT, None),
        False, _UNAPPROVED,
    ),
    _Move(
        "the approval's report revision was respelled true", final_support.EXECUTED, True,
        partial(_respells, key=_review_subjects.APPROVED_SUBJECT, member="report_revision", respelled=True),
        False, _UNAPPROVED,
    ),
    _Move(
        "the approval's pull request was respelled a float", final_support.RETAINED, False,
        partial(_respells, key=_review_subjects.APPROVED_SUBJECT, member="pr", respelled=float(support.PR_NUMBER)),
        False, _UNAPPROVED,
    ),
    _Move(
        "the approval's evidence claim was damaged", final_support.RETAINED, True,
        methodcaller(_PERSISTS, final_support.APPROVED_EVIDENCE, {"damaged": True}),
        False, _UNCLAIMED,
    ),
    _Move(
        "a damaged claim refuses before any request", final_support.UNCONFIGURED, True,
        lambda case: (
            case.persists(final_support.APPROVED_EVIDENCE, {"damaged": True}),
            case.enterContext(patch.object(case.gh, "get_pr", side_effect=RuntimeError("GitHub did not answer"))),
        ),
        False, _UNCLAIMED,
    ),
    _Move(
        "the approval's evidence claim is gone", final_support.EXECUTED, True,
        methodcaller(_PERSISTS, final_support.APPROVED_EVIDENCE, None),
        False, _UNCLAIMED,
    ),
    _Move(
        "the approval's evidence claim names another digest", final_support.RETAINED, False,
        partial(_respells, key=final_support.APPROVED_EVIDENCE, member="digest", respelled=_OTHER_DIGEST),
        False, _UNCLAIMED,
    ),
    _Move(
        "the approval's evidence claim says it failed", final_support.UNCONFIGURED, True,
        partial(_respells, key=final_support.APPROVED_EVIDENCE, member="passed", respelled=False),
        False, _UNCLAIMED,
    ),
    _Move(
        "the issue records another pull request", final_support.RETAINED, False,
        methodcaller(_PERSISTS, "pr_number", support.PR_NUMBER + 1),
        False, _UNAPPROVED,
    ),
    _Move(
        "a report is owed", final_support.EXECUTED, True,
        methodcaller(_PERSISTS, _report_records.PENDING_REPORT, {"receipt": "r"}),
        False, "is still owed",
    ),
    _Move(
        "the report was refreshed", final_support.UNCONFIGURED, True,
        _refreshes_the_report, False, "not the one the approval covers",
    ),
    _Move(
        "the requirements were edited", final_support.EXECUTED, False,
        lambda case: setattr(case.issue, "body", "Also document the empty configuration."),
        False, "requirements moved",
    ),
    _Move(
        "the pull request was pushed past the final head", final_support.EXECUTED, True,
        methodcaller("moves_the_head", support.REBASED_SHA),
        False, "moved off the recorded commit",
    ),
    _Move(
        "the configuration moved under the run", final_support.EXECUTED, True,
        lambda case: case.enterContext(
            patch.object(config, "VERIFY_COMMANDS", (support.SUITE, _LINT)),
        ),
        False, "every command `VERIFY_COMMANDS` requires",
    ),
    _Move(
        "verification was configured since", final_support.UNCONFIGURED, False,
        lambda case: case.enterContext(
            patch.object(config, "VERIFY_COMMANDS", (support.SUITE,)),
        ),
        False, "configured now, and the final head carries none",
    ),
    _Move(
        "the retained evidence was outranked", final_support.RETAINED, True,
        support.posts_unsettled, False, "newer than the current record",
    ),
    _Move(
        "the run's artifact was deleted", final_support.EXECUTED, True,
        _touches_the_artifact, False, "gone or no longer the one that settled",
    ),
    _Move(
        "the approval's evidence was invalidated", final_support.EXECUTED, True,
        lambda case: case.persists(_records.EVIDENCE_HISTORY, [
            dict(entry, retired=_records.Retirement.INVALIDATED.value)
            for entry in case.gh.read_pinned_state(case.issue).get(_records.EVIDENCE_HISTORY)
        ]),
        False, _UNCLAIMED,
    ),
    _Move(
        "the approval's current evidence names another branch", final_support.UNCONFIGURED, False,
        partial(_respells, key=_records.CURRENT_EVIDENCE, member="branch", respelled=_OTHER_BRANCH),
        False, _UNCLAIMED,
    ),
    _Move(
        "the run moved onto another branch with the pull request", final_support.EXECUTED, False,
        lambda case: (
            _respells(case, key=_records.CURRENT_EVIDENCE, member="branch", respelled=_OTHER_BRANCH),
            setattr(case.pull_request.head, "ref", _OTHER_BRANCH),
        ),
        False, "does not answer for the final head",
    ),
    _Move(
        "the retained evidence moved onto another branch with the pull request", final_support.RETAINED, True,
        lambda case: (
            _respells(case, key=_records.CURRENT_EVIDENCE, member="branch", respelled=_OTHER_BRANCH),
            setattr(case.pull_request.head, "ref", _OTHER_BRANCH),
        ),
        False, "does not answer for the final head",
    ),
    _Move(
        "the approval's superseded evidence names another branch", final_support.EXECUTED, True,
        lambda case: case.persists(_records.EVIDENCE_HISTORY, [
            dict(entry, branch=_OTHER_BRANCH)
            for entry in case.gh.read_pinned_state(case.issue).get(_records.EVIDENCE_HISTORY)
        ]),
        False, _UNCLAIMED,
    ),
    _Move(
        "the returned review subject is gone", final_support.UNCONFIGURED, True,
        methodcaller(_PERSISTS, _review_subjects.RETURNED_SUBJECT, None),
        False, "no readable review_returned_subject is recorded",
    ),
    _Move(
        "the returned review subject names another review", final_support.EXECUTED, True,
        partial(_respells, key=_review_subjects.RETURNED_SUBJECT, member="requirements", respelled=_OTHER_DIGEST),
        False, "another subject than the recorded review_returned_subject",
    ),
    _Move(
        "the approval's artifact was deleted", final_support.UNCONFIGURED, True,
        partial(_touches_the_artifact, approval=True), False, _UNSHOWN,
    ),
    _Move(
        "the approval's artifact was edited", final_support.EXECUTED, True,
        partial(_touches_the_artifact, approval=True, edited="Tests passed, trust me."), False, _UNSHOWN,
    ),
    _Move(
        "the approval's artifact would not re-read", final_support.UNCONFIGURED, False,
        lambda case: case.enterContext(
            patch.object(case.gh, "reread_verification_artifact", return_value=_UNREAD_ARTIFACT),
        ),
        True, "artifact could not be re-read",
    ),
    _Move(
        "newer evidence outranks the approval's", final_support.UNCONFIGURED, True,
        support.posts_unsettled, False, "newer than the current record",
    ),
    _Move(
        "the evidence handoff was damaged", final_support.UNCONFIGURED, True,
        methodcaller(_PERSISTS, _records.EVIDENCE_HANDOFF, {"damaged": True}),
        False, "handoff does not describe the current evidence",
    ),
    _Move(
        "the configuration moved since the approval", final_support.UNCONFIGURED, True,
        lambda case: case.enterContext(patch.object(config, "VERIFY_TIMEOUT", config.VERIFY_TIMEOUT + 1)),
        False, "recorded under another verification configuration",
    ),
    _Move(
        "the run's artifact would not re-read", final_support.EXECUTED, True,
        lambda case: case.enterContext(
            patch.object(case.gh, "reread_verification_artifact", return_value=_UNREAD_ARTIFACT),
        ),
        True, "could not be re-read",
    ),
    _Move(
        "no squash links the entry head", final_support.UNCONFIGURED, False,
        _links_no_squash, False, _UNCLAIMED,
    ),
    _Move(
        "the squash reads as another tree", final_support.UNCONFIGURED, True,
        lambda case: case.world.trees.update({support.SQUASHED_SHA: support.REBASED_TREE}),
        False, "no longer read as the tree the squash recorded",
    ),
    _Move(
        "the final head does not descend from the entry", final_support.EXECUTED, True,
        lambda case: case.world.descent.update({(support.SQUASHED_SHA, final_support.DOCS_SHA): False}),
        False, "does not descend from the head the docs pass was entered on",
    ),
    _Move(
        "the final head's ancestry would not read", final_support.UNCONFIGURED, False,
        lambda case: case.world.descent.update({(support.TESTED_SHA, final_support.DOCS_SHA): None}),
        True, "descends from the head the docs pass was entered on could not be read",
    ),
    _Move(
        "the issue would not read again", final_support.EXECUTED, True,
        lambda case: case.enterContext(
            patch.object(case.gh, "get_issue", side_effect=RuntimeError("GitHub did not answer")),
        ),
        True, "could not be read afresh for its requirements",
    ),
    _Move(
        "the checkout is not on this host", final_support.UNCONFIGURED, False,
        lambda case: setattr(case.world, "path", case.world.path / "absent"),
        False, "not on this host",
    ),
)

# The issue edited, and the pull request pushed off the final head, as a
# human would while the proof re-reads an artifact: what moved, the move, and
# what the proof says of it.
_MOVED_MEANWHILE = (
    (
        "the requirements were edited",
        lambda case: setattr(case.issue, "body", "Also document the empty configuration."),
        "requirements moved",
    ),
    (
        "the pull request was pushed",
        methodcaller("moves_the_head", support.REBASED_SHA),
        "not standing on the recorded commit",
    ),
)

# Each of those moves behind the last artifact re-read the proof takes, for
# every verification with the approval squashed and not.
_DURING_THE_LAST_READ = tuple(
    _Move(
        f"{moved} during the last artifact read", verification, squashed,
        partial(final_support.moves_during_the_last_read, moves=moves), False, refusal,
    )
    for verification, squashed in itertools.product(_KINDS, (False, True))
    for moved, moves, refusal in _MOVED_MEANWHILE
)


class ProvedCompletionTest(unittest.TestCase, final_support.FinalDocsCase):
    """Each verification proves its final head, every identity it follows left as it was."""

    def setUp(self) -> None:
        final_support.FinalDocsCase.setUp(self)

    def test_each_verification_proves_its_final_head(self) -> None:
        for squashed in (False, True):
            for verification in _KINDS:
                with self.subTest(verification=verification, squashed=squashed):
                    self.setUp()
                    approved = self.completes_as(verification, squashed=squashed)

                    proved = self.verdict()

                    self.assertTrue(proved.proved, proved.refusal)
                    self.assertEqual(proved.pull_request.number, support.PR_NUMBER)
                    self._keeps_the_approval(approved)
                    self._names_only_the_docs_run(verification)

    def test_a_granted_round_squashed_proves(self) -> None:
        # An operator's grant bought the approved round, so the approval and
        # the squash's carry of its evidence are under the requirements
        # through that grant, while the report keeps the ones it was written
        # against: the lineage holds the carry to the approval, not the report.
        for verification in _KINDS:
            with self.subTest(verification):
                self.setUp()
                self.subject = _reply_round.settles_a_granted_round(self)
                self.completes_as(verification, squashed=True)

                proved = self.verdict()

                written_against = _report_settlement.read_current_report(self.state).subject.requirements_revision
                self.assertNotEqual(self.subject.requirements_revision, written_against)
                self.assertTrue(proved.proved, proved.refusal)

    def _keeps_the_approval(self, approved: _records.CurrentEvidence) -> None:
        """The approval, its report, and the evidence it rests on -- current or history -- exactly as they were."""
        report = _report_settlement.read_current_report(self.state)
        self.assertEqual(
            (self.state.get(_review_subjects.APPROVED_SUBJECT), report.report_revision, report.subject.source_sha),
            (self.subject.recorded(), 1, support.TESTED_SHA),
        )
        kept = (
            _settlement.read_current_evidence(self.state), *_settlement.read_evidence_history(self.state),
        )
        bindings = [record.binding for record in kept if record.receipt == approved.receipt]
        self.assertEqual(bindings, [approved.binding])

    def _names_only_the_docs_run(self, verification) -> None:
        """Every artifact names the approved commit as the one reviewed; one names the docs commit, as its run."""
        found = self.artifacts()
        self.assertEqual({posted.review_subject for posted in found}, {support.TESTED_SHA})
        docs_runs = [
            (posted.source, posted.tested_sha) for posted in found if posted.target_head == final_support.DOCS_SHA
        ]
        executed = [(EvidenceSource.ORCHESTRATOR_EXECUTED, final_support.DOCS_SHA)]
        self.assertEqual(docs_runs, executed if verification is final_support.EXECUTED else [])


class RefusedCompletionTest(unittest.TestCase, final_support.FinalDocsCase):
    """One moved link refuses the completion, or holds it, and nothing is written or posted."""

    def setUp(self) -> None:
        final_support.FinalDocsCase.setUp(self)

    def test_every_moved_link_refuses_the_completion(self) -> None:
        for move in _MOVES:
            with self.subTest(move.moved):
                self.setUp()
                self.completes_as(move.verification, squashed=move.squashed)
                move.moves(self)
                self._refuses(move)

    def test_a_move_during_an_artifact_read_refuses(self) -> None:
        # Each artifact re-read is a request a human can edit the issue or
        # push to the pull request behind: both are read behind every one of
        # them, so neither is proved over.
        for move in _DURING_THE_LAST_READ:
            with self.subTest(move.moved, verification=move.verification, squashed=move.squashed):
                self.setUp()
                self.completes_as(move.verification, squashed=move.squashed)
                move.moves(self)
                self._refuses(move)

    def test_a_run_short_of_passing_never_proves(self) -> None:
        # A run still owed to the pull request, and a run that failed -- the
        # failure published and settled as exactly what happened -- prove
        # nothing about the final head.
        self.approves(squashed=True)
        self.runs_the_final_head()
        owed = self.verdict()
        self.setUp()
        self.approves(squashed=True)
        failed = self.runs_the_final_head(exit_status=1)
        self.reconcile()

        settled = _settlement.read_current_evidence(self.state)
        self.assertIn("not this issue's current evidence", owed.refusal)
        self.assertEqual((settled.receipt, settled.passed), (failed.receipt, False))
        self.assertEqual(self.artifacts()[-1].tested_sha, final_support.DOCS_SHA)
        self.assertIn("did not exit 0", self.verdict().refusal)

    def test_a_claim_on_superseded_evidence_refuses(self) -> None:
        # Later evidence of the same head settled after the approval, and the
        # completion retains it: the approval's claim still names the earlier
        # record, so the approval does not rest on what was retained.
        self.approves()
        self.record(self.binding(source=EvidenceSource.REVIEWER_REPORTED))
        self.reconcile()
        self.completes(self.entry_head, final_support.RETAINED, _settlement.read_current_evidence(self.state))

        self._refuses(_Move("", final_support.RETAINED, False, None, False, _UNCLAIMED))

    def test_evidence_recorded_before_the_run_refuses(self) -> None:
        # A failing transaction recorded behind the approval's evidence and
        # abandoned by the run of the final head recorded past it: the
        # approval's evidence was not superseded by that run alone.
        self.approves(squashed=True)
        self.record(self.binding(source=EvidenceSource.REVIEWER_REPORTED), exit_status=1)
        self.runs_the_final_head()
        self.assertFalse(self.reconcile())

        self._refuses(_Move("", final_support.EXECUTED, True, None, False, "recorded between"))

    def _refuses(self, move: _Move) -> None:
        """The proof refuses `move`, or holds it, for its own reason, writing and posting nothing."""
        before = (self.gh.write_state_calls, len(self.artifacts()))

        refused = self.verdict()

        self.assertEqual((refused.proved, refused.holds), (False, move.holds))
        self.assertIn(move.refusal, refused.refusal)
        self.assertEqual((self.gh.write_state_calls, len(self.artifacts())), before)


if __name__ == "__main__":
    unittest.main()
