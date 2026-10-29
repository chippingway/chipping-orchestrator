# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The documenting stage's own verification of the head a final docs pass completed on, staged as its completion.

The approval that moved the label here was of one review subject, and the
evidence it rests on answers for the head it was given over -- or the head
its squash published, through that squash's carry. A pass that publishes a
docs commit leaves the pull request on a head none of it is about, and the
review of the approval is not asked again for it. So what that head needs is
verification of its own, taken here, by the stage that moved it, and recorded
apart from the approval (`verifies_final_head`): the completion record
(`final_docs_records`) naming the approved subject, the head the pass was
entered on, the head it completed on, and how that head is verified -- the
approved subject, the settled report and its source commit, and the evidence
the approval rests on left exactly as they are.

How depends on the head and the configuration, read once:

- The entry head unchanged -- a pass that published nothing -- is RETAINED:
  the current evidence, which the approval rests on, is named as it stands,
  with its own provenance, a squash's carry still naming the approved commit
  as the one tested. Nothing runs and nothing is minted; whether that evidence
  still proves is the proof's (`final_docs_proof`).
- A changed head under an empty `VERIFY_COMMANDS` is UNCONFIGURED: nothing is
  configured, so nothing is required, nothing runs, and nothing is recorded as
  having passed -- the record names no evidence, and proves only while the
  configuration stays empty.
- A changed head under a configuration is EXECUTED: the configured commands
  run on this issue's checkout through the verify runner
  (`git/verification/runner.py`), and only a run of exactly the final head,
  under exactly the configuration read for it, says anything about it -- a
  baseline that is another commit or context is MOVED, whatever it passed or
  failed. A run `verification_local_runs` binds is minted as an
  orchestrator-executed transaction answering for the final head over the
  approved review -- the tested commit the final head itself -- and recorded
  beside the completion naming it, so the dispatcher's existing
  reconciliation proves, publishes, and settles it like any other
  (`verification_transaction`): a lost post response is found again by its
  receipt, and a refused or unconfirmed settlement leaves it owed for the next
  tick. Any other run is FAILED -- the configured commands did not pass on the
  final head, or could not be shown to -- and records nothing, the run kept
  whole so its failing command and output stay actionable; a run that passed
  and still binds nothing records nothing either.

Nothing here writes. What is staged on the state in hand -- the completion,
and for EXECUTED the transaction, with whatever the transaction abandons into
history and the revision floor it raises (`OWNED`) -- is measured against the
comment first, the transaction's own settlement and later invalidation
included (`verification_record_state`), and the pass's completion lands it
(`final_completion`), owning those fields and decided on every record the
evidence is bound through (`VERIFIED`). Staged nowhere, nothing authorizes a
completion: a missing or malformed record proves nothing.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum

from orchestrator import config
from orchestrator.git.verification import models as _verify_models, runner as _verify_runner
from orchestrator.git.worktrees import paths as _worktree_paths
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    final_docs_records as _final_docs,
    report_record_state as _report_record_state,
    verification_durable as _durable,
    verification_local_runs as _local_runs,
    verification_record_state as _record_state,
    verification_records as _records,
    verification_settlement_state as _settlement,
)
from orchestrator.workflow.engine.report_commits import ReportWrite
from orchestrator.workflow.engine.review_subjects import APPROVED_SUBJECT
from orchestrator.workflow.stages.documenting import models as _models

# The commands and the per-command timeout one run is handed, read once.
_Configuration = tuple[tuple[str, ...], int]

# What staging a final head's verification may change: the completion, and an
# executed run's transaction with the history and revision floor it moves.
OWNED = (
    _final_docs.FINAL_DOCS,
    _records.PENDING_EVIDENCE,
    _records.EVIDENCE_HISTORY,
    _records.REVISION_FLOOR,
)

# The guarded commit landing what was staged, alone or within a completion
# that owns and is decided on more: owning `OWNED`, and decided on every
# record the evidence is bound through (`verification_durable`), which the
# approval, the settled report, and the evidence the decision read are among.
VERIFIED = ReportWrite(owned=frozenset(OWNED), decided_on=frozenset(_durable._BOUND_RECORDS))


class FinalRoute(StrEnum):
    """What verifying a final head came to.

    RECORDED staged the completion, and for an executed run its transaction.
    FAILED ran the configured commands on the final head without passing.
    MOVED ran them on something other than the final head under the
    configuration read for it. UNBOUND found nothing a completion could
    follow or rest on: no approval or settled report to bind, no current
    evidence to retain, or a passing run that binds nothing. UNRECORDED found
    no room on the comment, or nobody could say which revisions were spent.
    Only RECORDED stages anything.
    """

    RECORDED = "recorded"
    FAILED = "failed"
    MOVED = "moved"
    UNBOUND = "unbound"
    UNRECORDED = "unrecorded"

    @classmethod
    def of_run(cls, run: _verify_models.VerifyResult, head: str, configured: _Configuration) -> FinalRoute:
        """What `run` can come to: MOVED off `head` or `configured`, FAILED short of passing, else RECORDED to bind."""
        if (run.commit, run.context_revision) != (head, _verify_models._context_revision(*configured)):
            return cls.MOVED
        return cls.RECORDED if run.status == _verify_models.VERIFY_STATUS_OK else cls.FAILED


@dataclass(frozen=True)
class FinalOutcome:
    """One final head's verification: its route, the completion staged, and the run made of it, if any."""

    route: FinalRoute
    final: _final_docs.FinalDocs | None = None
    run: _verify_models.VerifyResult | None = None


def verifies_final_head(ctx: _models._DocumentingContext, entry_head: str, final_head: str) -> FinalOutcome:
    """Verify the head a pass entered on `entry_head` completed on, `final_head`, and stage how; nothing is written.

    The approval the completion follows is the one `ctx.state` records now.
    Staged on `ctx.state` only where RECORDED; the caller lands it through
    `VERIFIED`, or a completion owning and decided on as much.
    """
    approved = ctx.state.get(APPROVED_SUBJECT)
    if not isinstance(approved, dict):
        return FinalOutcome(FinalRoute.UNBOUND)
    final = _final_docs.FinalDocs(approved, entry_head, final_head, _final_docs.FinalVerification.RETAINED)
    if final_head == entry_head:
        return _retained(ctx.state, final)
    configured = (tuple(config.VERIFY_COMMANDS), config.VERIFY_TIMEOUT)
    if not configured[0]:
        return _stages(ctx.state, replace(final, verification=_final_docs.FinalVerification.UNCONFIGURED))
    return _executed(ctx, replace(final, verification=_final_docs.FinalVerification.EXECUTED), configured)


def _retained(state: PinnedState, final: _final_docs.FinalDocs) -> FinalOutcome:
    """Stage `final` naming the current evidence as it stands; UNBOUND where there is none."""
    current = _settlement.read_current_evidence(state)
    if current is None:
        return FinalOutcome(FinalRoute.UNBOUND)
    named = _final_docs.FinalEvidence(current.receipt, current.revision)
    return _stages(state, replace(final, evidence=named))


def _executed(
    ctx: _models._DocumentingContext, final: _final_docs.FinalDocs, configured: _Configuration,
) -> FinalOutcome:
    """Run `configured` on the final head and stage the transaction it binds beside `final`, or say why not.

    The run answers for the approved review at the final head
    (`FinalDocs.final_target`), and has to have tested exactly the final head
    under exactly `configured` (`FinalRoute.of_run`). A passing run that
    binds nothing is UNBOUND.
    """
    target = final.final_target(ctx.state)
    if target is None:
        return FinalOutcome(FinalRoute.UNBOUND)
    worktree = _worktree_paths._worktree_path(ctx.spec, ctx.issue.number)
    run = _verify_runner._run_verify_commands(worktree, *configured)
    route = FinalRoute.of_run(run, final.final_head, configured)
    bound = _local_runs.local_run_evidence(run, target) if route is FinalRoute.RECORDED else None
    if bound is None:
        return FinalOutcome(FinalRoute.UNBOUND if route is FinalRoute.RECORDED else route, run=run)
    return replace(_records_run(ctx, final, bound), run=run)


def _records_run(
    ctx: _models._DocumentingContext, final: _final_docs.FinalDocs, bound: _local_runs.LocalRunEvidence,
) -> FinalOutcome:
    """Mint the transaction `bound` is, past every spent revision, and stage it beside `final` naming it."""
    pending = _record_state.mint_pending_evidence(ctx.state, ctx.issue.number, *bound)
    if pending is None:
        return FinalOutcome(FinalRoute.UNRECORDED)
    named = _final_docs.FinalEvidence(pending.receipt, pending.revision)
    return _stages(ctx.state, replace(final, evidence=named), pending)


def _stages(
    state: PinnedState, final: _final_docs.FinalDocs, pending: _records.PendingEvidence | None = None,
) -> FinalOutcome:
    """Stage `final`, and `pending` beside it, on `state` where both read back whole and the comment has room.

    Composed apart and laid over `state` only whole, so a refusal leaves it
    exactly as it was. The transaction is recorded through its own owner,
    which measures its settlement and invalidation too; a completion with no
    transaction is measured as it stands.
    """
    composed = PinnedState(state_data=dict(state.state_data))
    if not _final_docs.record_final_docs(composed, final):
        return FinalOutcome(FinalRoute.UNBOUND)
    recorded = pending is None or _record_state.record_pending_evidence(composed, pending)
    if not (recorded and _report_record_state.fits_the_comment(composed.state_data)):
        return FinalOutcome(FinalRoute.UNRECORDED)
    state.state_data = composed.state_data
    return FinalOutcome(FinalRoute.RECORDED, final=final)
