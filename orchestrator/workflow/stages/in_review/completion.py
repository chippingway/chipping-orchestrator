# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A final docs pass's completion, as the ready ping announces the head it completed on.

An approval is of one review subject, and the docs pass behind it may leave
the pull request on a head that subject is not about: a docs commit the
reviewer never saw, verified by a run of exactly that commit or, under an
empty `VERIFY_COMMANDS`, by nothing. The pass is recorded apart from the
approval (`final_docs_records`), and the approved subject, the settled report
and its source commit, and the evidence the approval rests on stay as they
were. The ordinary readiness proof would refuse such a head -- the current
evidence answers for another head, or the approval's claim names evidence a
run of the docs commit superseded -- and it would be right to: nothing in
those records says the docs commit was ever looked at. The completion is
what says so, and only it.

- It QUALIFIES the head it completed on for the ping (`qualifies`), read
  whole and on exactly that head, as the docs stamps and a GitHub approval
  each qualify one. A docs stamp alone qualifies a head for the ordinary
  proof and nothing more: it is no completion, so it licenses no exception.
- A comment recording one at all is held to it, whatever qualified the head
  (`recorded`, `readiness_verdict`): the whole final-documentation proof
  (`final_docs_proof.final_docs_verdict`) stands in for the ordinary one,
  proving the approval and its report, the evidence the approval's claim
  names, the verification of the final head, and the lineage between them
  apart. A record that will not read, or names another head than the one the
  ping would, refuses: a damaged completion, or a push past it, pings nobody,
  and a comment carrying none is never asked about one.
- The last word every road about to move an approval on takes
  (`review_coverage._approval_holds`) asks the evidence the completion rests
  on in place of the approval's own claim (`evidence_stands`): its records,
  the verification context the evidence it names was minted under, and every
  artifact it rests on re-read once more behind every request the proof made
  (`final_docs_proof._artifacts_refusal`), since a run of the docs commit is
  current evidence the claim was never given.

Nothing here writes. The ping's own writes are decided on the completion
beside every record the proof read (`ready_ping`), so one a maintainer edits
while the ping is decided refuses them.
"""
from __future__ import annotations

import logging
from typing import Any

from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    final_docs_proof as _final_docs_proof,
    final_docs_records as _final_docs,
    verification_proof as _proof,
    verification_settlement_state as _settlement,
)
from orchestrator.workflow.engine.report_evidence_models import ReportEvidence, ReportEvidenceVerdict
from orchestrator.workflow.engine.verification_proof import ProofReading

log = logging.getLogger("orchestrator.workflow")

_ANOTHER_HEAD = ReportEvidence(
    ReportEvidenceVerdict.DEFER,
    "the final-documentation completion names another head than the one the ping would name",
)


def recorded(state: PinnedState) -> bool:
    """Whether the pinned comment records a final-documentation completion, whether or not it reads whole."""
    return state.get(_final_docs.FINAL_DOCS) is not None


def qualifies(state: PinnedState, head_sha: str) -> bool:
    """Whether a completion read whole names `head_sha` as the head its pass completed on."""
    final = _final_docs.read_final_docs(state)
    return final is not None and bool(head_sha) and final.final_head == head_sha


def readiness_verdict(reading: ProofReading, head_sha: str) -> ReportEvidence:
    """Prove the completion `reading.state` records for a ping naming `head_sha`; PROVED carries the pull request.

    Refused where it names another final head; one that will not read is the
    proof's own to refuse. Nothing is written.
    """
    final = _final_docs.read_final_docs(reading.state)
    if final is not None and final.final_head != head_sha:
        return _ANOTHER_HEAD
    return _final_docs_proof.final_docs_verdict(reading)


def evidence_stands(reading: ProofReading, pull_request: Any) -> bool | None:
    """Whether the evidence the completion rests on still stands, read last; None where it could not be read.

    The completion's records off the pinned comment first -- the approval,
    the report it covers, the verification, and the approval's claim -- then
    the verification context the named evidence was minted under, still the
    one configured (`_context_refusal`), and every artifact it rests on
    re-read on `pull_request`, the one the proof read: the named evidence's
    still passing, and the claimed evidence's still the one that settled,
    under the configuration now. What `approved_evidence.stands` asks of an
    approval's own evidence, so a configuration moved while the proof read
    pings nobody on this route either.
    """
    final = _final_docs.read_final_docs(reading.state)
    if final is None:
        return False
    refused = (
        _final_docs_proof._recorded_refusal(reading, final)
        or _context_refusal(reading.state, final)
        or _final_docs_proof._artifacts_refusal(reading, final, pull_request)
    )
    if refused is None:
        return True
    log.info(
        "issue=#%d the evidence its final docs pass rests on %s: %s",
        reading.issue.number, "could not be read" if refused.holds else "no longer stands", refused.refusal,
    )
    return None if refused.holds else False


def _context_refusal(state: PinnedState, final: _final_docs.FinalDocs) -> ReportEvidence | None:
    """Refuse the evidence `final` names where it was minted under another verification context than now; or None.

    Asked behind `_recorded_refusal`, so evidence named is this issue's
    current evidence. A completion resting on none has only the claimed
    evidence's context to hold, which its artifact's re-read asks.
    """
    if final.evidence is None:
        return None
    return _proof._context_verdict(_settlement.read_current_evidence(state).binding)
