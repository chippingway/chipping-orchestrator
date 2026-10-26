# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Whether a recorded final-documentation completion still proves its final head documented and verified.

The completion (`final_docs_records`) is a claim, and nothing in it is taken
on its word: every link it names is proved again here, on the reading the
caller hands (`verification_proof.ProofReading`), before any reader may rely
on it. The links are four, and each is proved apart, so no proof of one is
read as a proof of another -- above all, the approval stays a proof about the
commit the reviewer was handed, never about the docs commit, and evidence
stays a proof about the commit its checks ran on.

The APPROVAL and the REPORT, off the pinned comment alone and first: the
approved subject the completion names is still exactly the one this issue
records as approved, read whole, on the pull request it pins; no developer
report is owed; the settled report is still the one that subject names -- its
revision and digest -- written about the very commit the subject is about; and
the evidence claim recorded beside the approval still reads, says its evidence
passed and covered the configuration, and names exactly an evidence record
this issue keeps of the entry head over the approved review -- for RETAINED,
the retained transaction itself (`final_docs_claims`). A report refreshed, a
review recorded since, an approval retired, replaced, or respelled, or its
claim damaged or naming other evidence is a completion of something that no
longer stands; off the pinned comment too, the review subject that evidence
is bound to has to pass the evidence proof's own subject guard. On the pull
request the verification read, it is held to the configuration now and to its
publication (`final_docs_claims.claimed_artifact_refusal`): under
UNCONFIGURED, which waives only the run of the final head, as current evidence
is -- no revision spent past it, its handoff describing it -- and under
EXECUTED, superseded by that run alone; either way its artifact re-read on
that pull request. Outranked, deleted, or edited it refuses, and unread it
holds. Only where the pull request, branch, and checkout stand is not asked of
it: a docs commit moves all three, and they are proved at the final head
instead.

The VERIFICATION of the final head, by what the completion says it rests on:

- RETAINED and EXECUTED name a transaction, which has to be this issue's
  current evidence exactly -- a run still owed, superseded, or retired is not
  -- and bound as the completion says, to exactly what evidence of the final
  head answers for (`FinalDocs.final_target`): the approved review on the
  settled report's repository, pull request, and branch at that head.
  RETAINED, the evidence the approval rests on, answering for the unchanged
  head, its own provenance kept -- a squash's carry still naming the approved
  commit as the one tested; EXECUTED, a run this orchestrator executed on
  exactly the final head (`final_docs_records.answers_for`). Then the whole
  proof every reader about to rely on current evidence takes
  (`verification_proof.current_evidence_verdict`): still the latest revision,
  its handoff and artifact standing, the pull request open on its branch and
  standing on the final head, the branch and the checkout there too, the
  tested commit and the final head reading as the tested tree, the configured
  verification context, the review subject, the settled report re-read at its
  location, and the requirements. And current
  is not passing: its artifact, re-read on the pull request that proof read,
  has to pass as an approval's must, at least one command, every one exiting
  0, and every configured `VERIFY_COMMANDS` command among them
  (`stages/validating/approved_evidence.py`, resolved when called). A failed
  or incomplete run never proves.
- UNCONFIGURED names none, and is no evidence that anything passed: it proves
  only while `VERIFY_COMMANDS` is still empty, so a configuration added since
  requires a run the final head never had. The parts of that proof no binding
  is needed for are taken over the final head and the approved review instead:
  the pull request open on its branch and standing on the final head, the
  checkout here and the branch fetched and level with it, the settled report
  re-read at its location as a reviewer would be handed it beside the approved
  review, and the issue's requirements still the approved ones.

Every artifact either verification re-reads -- the named evidence's, for
what it passed, and the claimed evidence's, for its standing -- is asked
between the pull request's reading and the rest of that proof
(`_ahead_refusal`, handed to `current_evidence_verdict` as its `ahead` where
the completion names evidence). Each re-read is a request long enough for the
issue to be edited or the pull request pushed to, and the issue the caller
hands was read before any of them, so behind them the issue is read afresh
and its requirements held to the revision the approval was given and the one
the drift baseline holds, as every road about to act on an approval holds
them (`stages/validating/review_coverage._requirements_stand`, resolved when
called) -- an issue nobody could read again holds -- and the readings that see
a push -- the branch fetched and the checkout standing on the final head --
are taken behind that, with the settled report re-read and the requirements
again over the thread as it stands. A completion is never proved over a
reading one of its own artifact re-reads outlived.

The LINEAGE last, in this host's checkout: the head the pass was entered on is
the approved commit itself, or the commit this orchestrator's approval squash
published over it, proved by that squash's own carry of the approved review
onto it and both commits reading as the tree it recorded
(`report_squash_lineage.squash_verdict`) -- the approved review, under the
requirements it was given, which for a round an operator's grant bought are
the thread through that grant rather than the ones the report was written
against; and a final head that differs from it has the entry head in its
history (`git/verification/objects._descends`).

The verdicts are the evidence proof's own. PROVED carries the pull request
the proof read. HOLD is a reading nobody could take -- the record is no
refusal, and nothing about it is decided. DEFER is everything else: a record
missing or malformed, an approval, report, requirements, configuration,
publication, or evidence that moved, a lineage not proved. None of them
writes anything; what a refusal means for the issue is the caller's.

Its reader is the in_review ready ping (`stages/in_review/completion.py`),
which takes the whole proof in place of the ordinary readiness proof over a
comment recording a completion, and re-reads every artifact the completion
rests on (`_artifacts_refusal`) once more as its last word.
"""
from __future__ import annotations

import importlib

from orchestrator import config
from orchestrator.git.verification import objects as _verification_objects
from orchestrator.git.worktrees import paths as _worktree_paths
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    final_docs_records as _final_docs,
    report_delivery as _report_delivery,
    report_publication_evidence as _publication,
    report_remote_evidence as _remote,
    report_settlement_state as _report_settlement,
    report_squash_lineage as _lineage,
    verification_settlement_state as _settlement,
    verification_subject as _subject,
)
from orchestrator.workflow.engine.final_docs_claims import claim_refusal, claimed_artifact_refusal
from orchestrator.workflow.engine.report_evidence_models import ReportEvidence, ReportEvidenceVerdict
from orchestrator.workflow.engine.review_subjects import ReviewSubject
from orchestrator.workflow.engine.stage_targets import (
    _VALIDATING_APPROVED_EVIDENCE_OWNER,
    _VALIDATING_REVIEW_COVERAGE_OWNER,
)
from orchestrator.workflow.engine.verification_proof import ProofReading, current_evidence_verdict

_DEFER = ReportEvidenceVerdict.DEFER

_HOLD = ReportEvidenceVerdict.HOLD

_UNRECORDED = ReportEvidence(_DEFER, "no readable final-documentation completion is recorded")

_UNAPPROVED = ReportEvidence(
    _DEFER, "the approval the final-documentation completion followed is no longer the one this issue records",
)

_OWED = ReportEvidence(_DEFER, "a developer report the approved review would describe is still owed")

_UNREPORTED = ReportEvidence(
    _DEFER, "the settled developer report is not the one the approval covers, about the commit it approved",
)

_CONFIGURED = ReportEvidence(_DEFER, "verification is configured now, and the final head carries none")

_UNNAMED = ReportEvidence(
    _DEFER, "the evidence the final head's verification rests on is not this issue's current evidence",
)

_UNBOUND = ReportEvidence(
    _DEFER, "the current evidence does not answer for the final head over the approved review as recorded",
)

_UNREAD_ARTIFACT = ReportEvidence(
    _HOLD, "the final head's evidence artifact could not be re-read for what it passed",
)

_MOVED_REQUIREMENTS = ReportEvidence(
    _DEFER, "the issue's requirements moved past the approval the completion followed, read afresh behind its reads",
)

_UNREAD_REQUIREMENTS = ReportEvidence(
    _HOLD, "the issue could not be read afresh for its requirements behind the completion's artifacts",
)

_NO_CHECKOUT = ReportEvidence(_DEFER, "the checkout the final head is read in is not on this host")

_UNDESCENDED = ReportEvidence(
    _DEFER, "the final head does not descend from the head the docs pass was entered on",
)

_UNREAD_DESCENT = ReportEvidence(
    _HOLD, "whether the final head descends from the head the docs pass was entered on could not be read",
)


def final_docs_verdict(reading: ProofReading) -> ReportEvidence:
    """Prove the completion `reading.state` records, every link apart; PROVED carries the pull request read.

    The pinned records first, then the verification's requests -- every
    artifact re-read ahead of the readings a push or an edit would move
    and the requirements over the issue read afresh behind them
    (`_ahead_refusal`) -- then the lineage in this host's checkout.
    Nothing is written.
    """
    final = _final_docs.read_final_docs(reading.state)
    if final is None:
        return _UNRECORDED
    refused = _recorded_refusal(reading, final)
    if refused is not None:
        return refused
    if final.evidence is None:
        found = _unverified_verdict(reading, final)
    else:
        found = current_evidence_verdict(
            reading, lambda pull_request: _ahead_refusal(reading, final, pull_request),
        )
    if not found.proved:
        return found
    return _lineage_verdict(reading, final) or found


def _recorded_refusal(reading: ProofReading, final: _final_docs.FinalDocs) -> ReportEvidence | None:
    """Refuse what the pinned comment alone says moved under `final`, or None.

    The approval and the pull request, a report owed, and the settled report
    the approval covers -- its revision, digest, and the commit it is about --
    then the verification (`_named_refusal`), and the evidence the approval's
    own claim names (`final_docs_claims.claim_refusal`). Asked again ahead of
    the artifacts by the ready ping's last word
    (`stages/in_review/completion.evidence_stands`).
    """
    state = reading.state
    if not final.follows(state):
        return _UNAPPROVED
    if _report_delivery.owes_a_report(state):
        return _OWED
    report = _report_settlement.read_current_report(state)
    approved = (*ReviewSubject.identity_recorded_in(final.approved), final.approved_commit)
    if report is None or approved != (
        report.subject.pr_number, report.report_revision, report.content_revision, report.subject.source_sha,
    ):
        return _UNREPORTED
    return _named_refusal(state, final) or claim_refusal(state, final)


def _named_refusal(state: PinnedState, final: _final_docs.FinalDocs) -> ReportEvidence | None:
    """Refuse a verification the pinned comment no longer bears out, or None.

    An empty configuration for a completion resting on no evidence; and
    otherwise the current evidence, named exactly and bound as the completion
    says -- the run of the final head for EXECUTED, the approval's own
    evidence of the unchanged head for RETAINED -- to exactly what evidence
    of the final head answers for (`FinalDocs.final_target`): the approved
    review on the settled report's repository, pull request, and branch.
    """
    if final.evidence is None:
        return _CONFIGURED if config.VERIFY_COMMANDS else None
    current = _settlement.read_current_evidence(state)
    if not final.evidence.names(current):
        return _UNNAMED
    if final.verification is _final_docs.FinalVerification.EXECUTED:
        bound = _final_docs.answers_for(state, current.binding)
    else:
        bound = current.binding.target == final.final_target(state)
    return None if bound else _UNBOUND


def _ahead_refusal(
    reading: ProofReading, final: _final_docs.FinalDocs, pull_request: object,
) -> ReportEvidence | None:
    """Refuse or hold `final` on what is asked between the pull request's reading and the rest; or None.

    `pull_request` is the one the verification read open on the final head.
    Every artifact the completion rests on is re-read on it
    (`_artifacts_refusal`), and behind them the issue is read afresh, its
    requirements still the revision the approval was given and the one the
    drift baseline holds (`stages/validating/review_coverage._requirements_stand`,
    resolved when called): the issue in hand was read before any of these
    requests, and its title and body say nothing of an edit landing during
    them.
    """
    refused = _artifacts_refusal(reading, final, pull_request)
    if refused is not None:
        return refused
    stands = importlib.import_module(_VALIDATING_REVIEW_COVERAGE_OWNER)._requirements_stand(
        reading.gh, reading.issue, reading.state,
    )
    if stands is None:
        return _UNREAD_REQUIREMENTS
    return None if stands else _MOVED_REQUIREMENTS


def _artifacts_refusal(
    reading: ProofReading, final: _final_docs.FinalDocs, pull_request: object,
) -> ReportEvidence | None:
    """Refuse or hold `final` on every artifact it rests on, re-read on `pull_request`; or None.

    The named evidence's first, where the verification rests on some: it has
    to pass as an approval's must, so one nobody could read holds, and one
    failing, short of a configured command, or no longer the one that settled
    refuses. Then the evidence the approval's claim names, still standing
    (`final_docs_claims.claimed_artifact_refusal`). Asked again, apart from
    the rest of the proof, by the ready ping's last word behind every request
    the proof made (`stages/in_review/completion.evidence_stands`).
    """
    if final.evidence is not None:
        owner = importlib.import_module(_VALIDATING_APPROVED_EVIDENCE_OWNER)
        refused = owner._artifact_refusal(
            reading.gh, pull_request, _settlement.read_current_evidence(reading.state),
        )
        if refused is None:
            return _UNREAD_ARTIFACT
        if refused:
            return ReportEvidence(_DEFER, refused)
    return claimed_artifact_refusal(reading.gh, reading.state, final, pull_request)


def _unverified_verdict(reading: ProofReading, final: _final_docs.FinalDocs) -> ReportEvidence:
    """Prove the final head of a completion resting on no evidence, over the approved review; PROVED, or a refusal.

    The pull request first and the checkout, then the claimed evidence's
    artifact on that pull request and the requirements over the issue read
    afresh behind it (`_ahead_refusal`), then the branch, the settled report
    as a reviewer of the approved review is handed it, and the requirements
    over the thread as it stands -- the parts of the evidence proof no run is
    needed for, each read behind that re-read.
    """
    target = final.final_target(reading.state)
    found = _publication.subject_verdict(reading.gh, target.publication)
    if not found.proved:
        return found
    if not _worktree_paths._worktree_path(reading.spec, reading.issue.number).exists():
        return _NO_CHECKOUT
    refused = _ahead_refusal(reading, final, found.pull_request) or _remote.subject_remote_verdict(
        reading.spec, reading.issue, target.publication,
    )
    if refused is None:
        refused = _subject.report_verdict(reading.gh, reading.state, target)
    if refused is None:
        refused = _subject.requirements_verdict(
            reading.issue, reading.state, target.publication.requirements_revision,
        )
    return refused or found


def _lineage_verdict(reading: ProofReading, final: _final_docs.FinalDocs) -> ReportEvidence | None:
    """Refuse or hold an entry head not linked to the approved commit, or a final head not descended from it."""
    if final.entry_head != final.approved_commit:
        squashed = _lineage.squash_verdict(
            reading.spec, reading.issue.number, reading.state, final.entry_head, final.approved,
        )
        if not squashed.proved:
            return squashed
    if final.final_head == final.entry_head:
        return None
    worktree = _worktree_paths._worktree_path(reading.spec, reading.issue.number)
    if not worktree.exists():
        return _NO_CHECKOUT
    descends = _verification_objects._descends(worktree, final.entry_head, final.final_head)
    if descends is None:
        return _UNREAD_DESCENT
    return None if descends else _UNDESCENDED
