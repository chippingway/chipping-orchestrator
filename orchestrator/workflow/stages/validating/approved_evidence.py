# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The verification evidence an approval was proved over, and what every road acting on it holds it to.

An approval proved over evidence (`unverified_approvals`) rests on that
evidence for as long as anything acts on the approval, not only at the proof.
The evidence counts only as it is: the claim has to name this issue's CURRENT
evidence exactly -- the same receipt, revision, and digest -- that evidence
has to prove current again (`verification_proof.current_evidence_verdict`),
and its artifact, re-read at the comment it settled as, has to be the one that
settled, still passing and carrying every configured `VERIFY_COMMANDS`
command exactly, exiting 0 (`review_claims.covers_the_configuration`). A
claim on a transaction still owed is a publication that stood down, and one on
evidence superseded or retired is evidence the pull request no longer stands
on (`refusal`).

The approval arc takes that proof again behind the local verify gate and
behind the approval comment (`handoff._Held.evidence_stands`), since each is a
request long enough for the artifact to be deleted or edited on the pull
request, or a later revision settled -- and the artifact is on the pull
request, where no pinned record shows it moving. Past the squash the whole
proof cannot be taken again: the force-push stands the pull request on a
commit the evidence was never bound to, so the head, checkout, and subject it
was proved against are gone. So the claim is recorded beside the approved
subject (`records`), and every later road that would move the approval on --
the squash tail's relabel, the recovery of a squash an earlier tick did not
finish, the documenting stage's opening, the merge gate -- holds it to every
part of that proof the rewrite left standing (`stands`): off the records, the
evidence it names still the current evidence, exactly; no revision past it
spent, whether that newer transaction settled or is still owed; its handoff
still describing it; and the verification context it was minted under still
the one configured -- and off the pull request it was published on, which the
rewrite did not touch, its artifact re-read at the comment it settled as,
still the one that settled, passing and covering the configuration. A later
revision recorded or settled, the current record retired, the configuration
moved, or the artifact deleted or edited is evidence the approval was never
given, and the move is not taken over it; an artifact nobody could read holds
the move for a later tick.

A squash that publishes another head carries evidence onto it, only by tree
equivalence (`squash_evidence`) -- this evidence, or the run the approval's
verify gate made on the approved head in its place -- and points the record
at the carried transaction in the same write, `published`, its digest and
flags the ones the carried transcript earns: unchanged where it is this
evidence's own, the gate run's where that is carried. So once that carry
settles every road holds the approval to evidence answering for the head it
moves, and a carry abandoned without settling leaves the record naming no
current evidence, which refuses the move. One still owed holds the move
rather than refusing it, on the squash's own roads (`squash_evidence`): the
reconciliation stood down on it for want of room, and a later tick settles
it.

Every approval reaches the arc proved over the evidence its verdict names, so
every approval records that claim; one recorded before approvals were proved
over evidence carries none and is held to none -- unless the current evidence
is a carry, which only a claim ever puts there: with the claim gone, the
approval does not stand over it. Nor does any approval over a carry whose
review subject no longer stands (`review_coverage._approval_stands`), which
every later reader asks before moving the approval on; `validating`, which
owns the carry, invalidates it when the issue comes back (`collapse`).
"""
from __future__ import annotations

import logging

from github.Issue import Issue

from orchestrator import config
from orchestrator.config import models as _config_models
from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.github.pull_request_reports import ReportPresence
from orchestrator.workflow.engine import (
    verification_current as _current,
    verification_proof as _proof,
    verification_record_state as _record_state,
    verification_records as _records,
    verification_settlement_state as _settlement,
)
from orchestrator.workflow.stages.validating import review_claims as _claims, review_verdicts as _verdicts

log = logging.getLogger("orchestrator.workflow")

# The evidence claim the recorded approval rests on, beside the approved subject.
APPROVED_EVIDENCE = "review_approved_evidence"

FAILED = "a command its verification lists did not exit 0"

MOVED = "the evidence it relies on is no longer this issue's current evidence"

_UNCOVERED = (
    "its verification does not include, exactly as configured and exiting 0, "
    "every command `VERIFY_COMMANDS` requires"
)

_UNPUBLISHED = "its verification evidence could not be published on the pull request"

_ARTIFACT_MOVED = "its artifact is gone or no longer the one that settled"


def records(state: PinnedState, claim: _verdicts.EvidenceClaim | None) -> None:
    """Stage `claim` as the evidence the approval being recorded rests on, or drop the record where it rests on none.

    Dropped only where one is set, so an issue that never carried the key is
    not given it. The caller writes.
    """
    if claim is not None:
        state.set(APPROVED_EVIDENCE, claim.recorded())
    elif state.get(APPROVED_EVIDENCE) is not None:
        state.set(APPROVED_EVIDENCE, None)


def stands(gh: GitHubClient, state: PinnedState) -> bool | None:
    """Whether the evidence the recorded approval rests on still stands past the squash; None where unread.

    Every part of the proof the rewrite left standing. The records first: the
    claim names the current record exactly, no revision past it has been
    spent -- a newer transaction raises the floor the moment it is recorded,
    settled or not (`verification_current._outranked`) -- the evidence
    handoff still describes it, and it was minted under the verification
    context configured now. Then its artifact, re-read at the comment it
    settled as on the pull request it was published on, which no rewrite
    moves: still the one that settled, passing, and carrying every configured
    command. True where no claim is recorded -- absent or written null -- for
    an approval recorded before approvals were proved over evidence, save
    over current evidence carried onto a head it did not run on: only an
    approval squash's claim ever puts that there, so an approval with none
    has lost the word that evidence answers on, and it does not stand. A
    record that will not read names nothing anyone could hold the approval
    to, so it is no approval's evidence; a pull request or thread nobody
    could read is None.
    """
    recorded = state.get(APPROVED_EVIDENCE)
    current = _settlement.read_current_evidence(state)
    if recorded is None:
        return current is None or current.binding.tested_sha == current.binding.target.target_head
    claim = _verdicts.EvidenceClaim.read(recorded)
    if claim is None or not _on_the_records(state, current, claim):
        return False
    pr_number = current.binding.target.publication.pr_number
    try:
        refused = _artifact_refusal(gh, gh.get_pr(pr_number), current)
    except Exception:
        log.exception("could not read PR #%s again for the evidence an approval rests on", pr_number)
        return None
    return None if refused is None else not refused


def refusal(
    gh: GitHubClient,
    spec: _config_models.RepoSpec,
    issue: Issue,
    state: PinnedState,
    claim: _verdicts.EvidenceClaim,
) -> str | None:
    """Why the evidence `claim` names may not be acted on; "" where it may, None where it could not be read.

    The claim's own flags are the caller's to have asked: they are the
    verdict's copy of what the evidence said, and they never move.
    """
    current = _settlement.read_current_evidence(state)
    if not _on_the_records(state, current, claim):
        return _unsettled_refusal(state, claim)
    proved = _proof.current_evidence_verdict(_proof.ProofReading(gh, spec, issue, state))
    if proved.holds:
        return None
    if not proved.proved:
        return f"{MOVED}: {proved.refusal}"
    return _artifact_refusal(gh, proved.pull_request, current)


def uncovered() -> str:
    """Why evidence missing a configured command refuses the approval, naming what is required."""
    listed = ", ".join(f"`{command}`" for command in config.VERIFY_COMMANDS)
    return f"{_UNCOVERED}: {listed}"


def _on_the_records(
    state: PinnedState, current: _records.CurrentEvidence | None, claim: _verdicts.EvidenceClaim,
) -> bool:
    """Whether the records still carry `current` as the evidence `claim` names, and as evidence that may stand.

    Named exactly -- receipt, revision, and digest -- with no revision past it
    spent, its handoff describing it, and minted under the verification
    context configured now: every part of the proof the pinned comment alone
    answers, which no rewrite of the branch moves.
    """
    if current is None:
        return False
    named = (claim.receipt, claim.revision, claim.digest)
    return (
        (current.receipt, current.revision, current.content_revision) == named
        and not _current._outranked(state, current)
        and _current._handoff_describes(state, current)
        and current.binding.context_revision == _proof.configured_context_revision()
    )


def _artifact_refusal(
    gh: GitHubClient, pull_request, current: _records.CurrentEvidence,
) -> str | None:
    """Why the settled evidence itself refuses the approval; "" where it may stand, None to hold.

    Read off the artifact on `pull_request`, the one the proof just proved,
    rather than off the claim: the pass flag the proof holds to it, and the
    commands it carries for the configuration's coverage.
    """
    presence, found = gh.reread_verification_artifact(pull_request, current.comment_id)
    if presence is ReportPresence.UNCONFIRMED:
        return None
    if presence is not ReportPresence.PRESENT or not _current._is_the_settled_artifact(found, current):
        return f"{MOVED}: {_ARTIFACT_MOVED}"
    if not current.passed:
        return FAILED
    return "" if _claims.covers_the_configuration(found.commands) else uncovered()


def _unsettled_refusal(state: PinnedState, claim: _verdicts.EvidenceClaim) -> str:
    """Why a claim the records no longer carry as current evidence refuses the approval.

    A published claim whose transaction is still the one owed is evidence
    that never reached the pull request; anything else is evidence that did
    and has since been superseded, outranked, retired, or left behind by the
    verification configuration.
    """
    pending = _record_state.read_pending_evidence(state)
    owed = pending is not None and pending.receipt == claim.receipt
    if claim.use is _verdicts.EvidenceUse.PUBLISHED and owed:
        return _UNPUBLISHED
    return MOVED
