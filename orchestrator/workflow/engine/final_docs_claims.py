# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The evidence an approval's own claim names, as a final-documentation completion relies on it.

An approval is recorded beside a claim on the evidence it was proved over
(`review_approved_evidence`, written by `stages/validating/approved_evidence.py`),
and a completion of the docs pass behind it is a completion of THAT approval:
the docs pass changes nothing about which evidence the reviewed implementation
rests on, and the completion never rewrites the claim. So the final-documentation
proof (`final_docs_proof`) holds the completion to that claim and to the
evidence it names, apart from whatever verifies the final head.

On the pinned comment first (`claim_refusal`). The claim has to read whole
through its own owner (`stages/validating/review_verdicts.py`, resolved when
called), say its evidence passed and covered the configuration as an approval's
must, and name exactly -- receipt, revision, and digest -- an evidence record
this issue keeps that answers for the entry head over the approved review
(`claimed_evidence`), itself recorded as passing. Which record that is follows
from what verified the final head. Under RETAINED and UNCONFIGURED nothing was
recorded past the approval's evidence, so it has to be the current record --
for RETAINED, the retained transaction itself. Under EXECUTED the run of the
final head settling superseded it, so it has to be in history as superseded --
never invalidated or abandoned, which no longer answers for anything. And the
review subject it is bound to has to stand as the evidence proof's own subject
guard holds one (`verification_subject.subject_verdict`): the applicable
recorded subject -- `review_returned_subject` for a reviewer's account --
still exactly that one, about its head or, for an approval squash's carry,
the approved one, on the pull request this issue pins with no report owed.
RETAINED meets that guard in the verification proof itself.

Then on the pull request the verification read, ahead of the rest of it
(`claimed_artifact_refusal`), so the branch, the report, and the requirements
are read behind the re-read this asks for. The record has to have been
recorded under the verification context configured now: an approval's
evidence answers only under the configuration it was proved against, and the
claim's word that it covered every configured command means nothing once the
configuration moves. And it has to stand as the evidence the
approval was given, by the guards every reader relying on evidence takes:

- UNCONFIGURED waives the run of the final head, and none of the guards the
  approval's evidence is held to save the one a docs commit always moves: the
  pull request, branch, and checkout standing on the entry head, which now
  stand on the final head and are proved there. That evidence is still the
  current record, so beside its subject and context it is proved published as
  current evidence is (`verification_current.publication_verdict`): no
  revision spent past it -- a newer transaction, settled or owed, posted or
  not, outranks it -- the settlement handoff describing it, and its artifact
  re-read on the pull request the proof read, still exactly the one that
  settled.
- EXECUTED has the run of the final head as the one revision past it: the
  record has to be the revision just before that run's, so nothing was
  recorded between the approval's evidence and the run that superseded it,
  and its artifact is re-read the same way, still the one that settled.

A comment deleted or edited is evidence nobody can be shown, and a thread
nobody could read holds. The claim's digest pins the transcript to the one the
claim's coverage was read off, under the configuration still current. A
RETAINED completion's claimed record is the retained transaction, which the
verification proof holds to all of this already, so none of it is asked twice.
"""
from __future__ import annotations

import importlib
from typing import Any

from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.github.pull_request_reports import ReportPresence
from orchestrator.workflow.engine import (
    final_docs_records as _final_docs,
    verification_current as _current,
    verification_records as _records,
    verification_settlement_state as _settlement,
    verification_subject as _subject,
)
from orchestrator.workflow.engine.report_evidence_models import ReportEvidence, ReportEvidenceVerdict
from orchestrator.workflow.engine.stage_targets import (
    _VALIDATING_APPROVED_EVIDENCE_OWNER,
    _VALIDATING_REVIEW_VERDICTS_OWNER,
)
from orchestrator.workflow.engine.verification_proof import configured_context_revision

# An evidence record a claim may name: the current one, or one in history.
_Kept = _records.CurrentEvidence | _records.HistoricalEvidence

_UNCLAIMED = ReportEvidence(
    ReportEvidenceVerdict.DEFER,
    "the approval's evidence claim does not read, pass, and name the evidence it rests on for the entry head "
    "on the settled report's publication",
)

_RECONFIGURED = ReportEvidence(
    ReportEvidenceVerdict.DEFER,
    "the evidence the approval's claim names was recorded under another verification configuration than now",
)

_INTERVENED = ReportEvidence(
    ReportEvidenceVerdict.DEFER,
    "evidence was recorded between the evidence the approval's claim names and the run of the final head",
)

_UNREAD = ReportEvidence(
    ReportEvidenceVerdict.HOLD, "the artifact of the evidence the approval's claim names could not be re-read",
)

_UNSHOWN = ReportEvidence(
    ReportEvidenceVerdict.DEFER,
    "the artifact of the evidence the approval's claim names is gone or no longer the one that settled",
)


def claim_refusal(state: PinnedState, final: _final_docs.FinalDocs) -> ReportEvidence | None:
    """Refuse `final` where the approval's claim names no evidence it rests on, or its subject moved; or None.

    The record the claim names (`claimed_evidence`), then the evidence proof's
    own subject guard over it (`verification_subject.subject_verdict`): the
    pull request this issue pins, no developer report owed, and the
    applicable recorded review subject -- `review_returned_subject` for a
    reviewer's account -- still exactly the one the record is bound to, about
    its head or, for an approval squash's carry, the approved one. RETAINED
    is held to that guard by the verification proof itself, since its claimed
    record is the retained transaction.
    """
    claimed = claimed_evidence(state, final)
    if claimed is None:
        return _UNCLAIMED
    if final.verification is _final_docs.FinalVerification.RETAINED:
        return None
    return _subject.subject_verdict(state, claimed.binding)


def claimed_artifact_refusal(
    gh: GitHubClient, state: PinnedState, final: _final_docs.FinalDocs, pull_request: Any,
) -> ReportEvidence | None:
    """Refuse or hold `final` over the claimed evidence's context and standing, re-read on `pull_request`; or None.

    `pull_request` is the one the proof read open on the final head. Asked
    behind `claim_refusal`, so the claim names a record, and between that
    pull request's reading and the rest of the verification
    (`final_docs_proof`), so every reading a push or an edit would move is
    taken behind this request. RETAINED asks nothing here: its claimed record
    is the retained transaction, which the verification holds to all of it.
    """
    claimed = claimed_evidence(state, final)
    if claimed is None:
        return _UNCLAIMED
    if final.verification is _final_docs.FinalVerification.RETAINED:
        return None
    if claimed.binding.context_revision != configured_context_revision():
        return _RECONFIGURED
    return _standing_refusal(gh, state, final, pull_request, claimed)


def claimed_evidence(state: PinnedState, final: _final_docs.FinalDocs) -> _Kept | None:
    """The evidence record the approval's claim names for `final`'s entry head over its approval, or None.

    The claim read whole, passing and covering (`_passing_claim`); the record
    named exactly, passing, and bound to exactly what the evidence the
    approval rests on answers for (`FinalDocs.entry_target`) -- superseded
    into history under EXECUTED, the current record otherwise.
    """
    claim = _passing_claim(state)
    entry = final.entry_target(state)
    if claim is None or entry is None:
        return None
    kept = [_settlement.read_current_evidence(state)]
    if final.verification is _final_docs.FinalVerification.EXECUTED:
        history = _settlement.read_evidence_history(state) or ()
        kept = [record for record in history if record.retired is _records.Retirement.SUPERSEDED]
    named = (claim.receipt, claim.revision, claim.digest)
    return next((record for record in kept if _rests_on(record, named, entry)), None)


def _passing_claim(state: PinnedState) -> Any:
    """The evidence claim the approval is recorded beside, read whole through its own owner, or None.

    None too for a claim that does not say its evidence passed and covered
    the configuration, which no approval is recorded over.
    """
    owner = importlib.import_module(_VALIDATING_APPROVED_EVIDENCE_OWNER)
    claim = importlib.import_module(_VALIDATING_REVIEW_VERDICTS_OWNER).EvidenceClaim.read(
        state.get(owner.APPROVED_EVIDENCE),
    )
    if claim is None or not (claim.passed and claim.covers):
        return None
    return claim


def _standing_refusal(
    gh: GitHubClient, state: PinnedState, final: _final_docs.FinalDocs, pull_request: Any, claimed: _Kept,
) -> ReportEvidence | None:
    """Refuse or hold `claimed` where it no longer stands as the evidence the approval was given; or None.

    Under UNCONFIGURED it is the current record, held to every guard current
    evidence is (`verification_current.publication_verdict`). Under EXECUTED
    the run of the final head is the one revision past it, and its artifact
    is re-read here.
    """
    if final.verification is _final_docs.FinalVerification.UNCONFIGURED:
        return _current.publication_verdict(gh, state, claimed, pull_request)
    if final.evidence is None or final.evidence.revision != claimed.revision + 1:
        return _INTERVENED
    presence, found = gh.reread_verification_artifact(pull_request, claimed.comment_id)
    if presence is ReportPresence.UNCONFIRMED:
        return _UNREAD
    if presence is not ReportPresence.PRESENT or not _current._is_the_settled_artifact(found, claimed):
        return _UNSHOWN
    return None


def _rests_on(record: _Kept | None, named: tuple, entry: _records.EvidenceTarget) -> bool:
    """Whether `record` is the passing evidence `named` -- receipt, revision, digest -- bound to exactly `entry`.

    The whole target the evidence was recorded for: the repository, pull
    request, and branch the settled report was published to, the head the
    pass was entered on, the requirements the approved review was given, and
    that review. Its artifact names neither the branch nor the report, so a
    record moved onto another publication is refused here or nowhere.
    """
    if record is None or not record.passed:
        return False
    if (record.receipt, record.revision, record.content_revision) != named:
        return False
    return record.binding.target == entry
