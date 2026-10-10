# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The evidence a landed base rewrite's head is routed with, made durable before anything routes it.

The finish (`rewrite_finish`) asks this once its checkpoint is durable and
before the relabel to `workflow:validating` or the attempt's retirement
(`settles`), for a head it routes: a head the base advanced past again is
rebased once more, and the head that rebase lands is decided then. The
decision is the evidence policy's (`rewrite_evidence.decides`); what it
requires of the pinned comment is staged here and lands in one guarded commit
(`rewrite_finish_writes.EVIDENCE`) before the finish goes on:

- Current evidence the rewrite moved past -- a changed full tree or
  verification context -- is retired into history as INVALIDATED, whole, on
  every route, so evidence of the replaced head never stands current beside
  the rewritten one.
- A FRESH run of the rewritten head, or a CARRIED decision, is recorded as the
  evidence transaction's pending record (`verification_record_state`), with
  the room its settlement and its later invalidation need. Its artifact is not
  posted here: the dispatcher's reconciliation (`verification_transaction`)
  waits behind the standing anchor, then proves the whole binding again over
  the settled report and the applicable review subject, and publishes it --
  and only that settlement makes it current. A result the comment cannot take
  is recorded nowhere, and the head goes to the fresh reviewer instead.
- A REVIEWER decision records nothing: the fresh reviewer is handed no current
  evidence (`stages/validating/review_evidence.py`), so its prompt tells it to
  run the verification itself (`review_evidence_prompts`). So does a MOVED
  result, refused whatever it said, and a FAILED run -- whose notice, the
  failing command, how it failed, and its output's tail, is recorded in the
  same write and then put on the pull request once (`rewrite_finish_failures`)
  before the route, so the failure stays actionable.

The route is held instead -- nothing relabelled or retired, the attempt left
standing for a later tick's recovery to finish -- for a decision short of a
reading nobody could take (HELD), an invalidation the comment has no room for
(HELD), an evidence write refused or never confirmed (REFUSED, UNCONFIRMED),
and a failure notice whose publication nobody could confirm (HELD). The
standing anchor holds every handler meanwhile, so no reviewer is handed the
head.

The finish that completes it -- the recovery of the push already landed --
repeats nothing an earlier one made durable. One that died before its
evidence write landed, before its commands ran or behind a run that
completed, captured nothing, and the decision is taken afresh, running the
commands again where the policy runs them. A failure notice it recorded is
the decision itself, taken again with no second run and published only where
the pull request does not carry it yet. A transaction it recorded for the
landed head is a captured run or carry, never made again: proved again over
what this finish reads (`rewrite_finish_captured`), it is routed exactly as
recorded, or -- something it is bound to moved since -- abandoned into history
in the same write, with nothing run again and the fresh reviewer owing the
evidence. A head the base advanced past again is decided nothing for
(`continues`): a transaction recorded for it is abandoned before the attempt
retires, since the next rebase replaces that head.

Whether the current evidence has to be invalidated is asked as the write is
staged, on every road, rather than taken from a decision read before its
commands ran: the configuration can move while they run, or between a finish
and the one that retries it, and either way an equal tree spares the
evidence only under the context configured when it is written.
"""
from __future__ import annotations

import logging

from orchestrator.github.pinned_state import PinnedState
from orchestrator.github.verification_evidence import VerifiedCommand
from orchestrator.workflow.engine import (
    rewrite_evidence as _rewrite_evidence,
    rewrite_finish_captured as _captured,
    rewrite_finish_failures as _failures,
    rewrite_finish_notices as _notices,
    rewrite_finish_writes as _writes,
    verification_record_state as _record_state,
    verification_settlement_state as _settlement,
)
from orchestrator.workflow.engine.rewrite_evidence_models import RewriteEvidence, RewriteEvidenceRoute
from orchestrator.workflow.engine.rewrite_finish_models import FinishOutcome, LandedFinish
from orchestrator.workflow.engine.verification_records import EvidenceBinding

log = logging.getLogger("orchestrator.workflow")

# What a fresh or carried result is recorded as: the binding, the transcript,
# and the settled evidence a carry copied that transcript from.
_Licensed = tuple[EvidenceBinding, tuple[VerifiedCommand, ...], str | None]


def settles(finish: LandedFinish) -> FinishOutcome | None:
    """Decide the evidence `finish`'s landed head is routed with, and land what it requires; None to route it.

    Anything else is where the finish stops, with nothing routed and the
    attempt standing. A decision an earlier finish of this landing made
    durable is taken again with nothing run, behind the invalidation the
    current evidence is owed now: the failure notice it recorded published,
    and the transaction it recorded proved again first -- routed as it was
    captured, or abandoned where something moved under it
    (`rewrite_finish_captured`).
    """
    failure = _failures.recorded(finish.state, finish.head)
    captured = _captured.recorded(finish)
    if failure is None and captured is None:
        return _decides(finish)
    staged = _writes.staging(finish)
    if not _invalidates(finish, staged):
        return FinishOutcome.HELD
    stopped = None if captured is None else _captured.proved_again(finish, staged, captured)
    if stopped is not None:
        return stopped
    return _lands(finish, staged) or _failures.publishes(finish, failure)


def continues(finish: LandedFinish) -> FinishOutcome | None:
    """Abandon what an earlier finish recorded for a landed head the base advanced past; None to continue it.

    The caller's next rebase replaces that head, so a transaction recorded
    for it is a decision no route takes (`rewrite_finish_captured.sets_aside`),
    abandoned in the evidence write before the attempt retires. Nothing is
    decided, run, or invalidated for the head itself.
    """
    staged = _writes.staging(finish)
    return _captured.sets_aside(finish, staged) or _lands(finish, staged)


def _decides(finish: LandedFinish) -> FinishOutcome | None:
    """Ask the policy, then land what its decision requires and publish a failure it found; None to route."""
    decided = _rewrite_evidence.decides(finish)
    if decided.refusal is not None and decided.refusal.holds:
        log.warning(
            "issue=#%d holding the route of %.8s: its verification evidence could not be decided (%s)",
            finish.issue.number, finish.head, decided.reason,
        )
        return FinishOutcome.HELD
    staged = _writes.staging(finish)
    if not _invalidates(finish, staged):
        return FinishOutcome.HELD
    _records(finish, decided, staged)
    notice = None
    if decided.route is RewriteEvidenceRoute.FAILED:
        notice = _notices.failure(finish, decided.run)
        _failures.records(staged, finish.head, notice)
    return _lands(finish, staged) or _failures.publishes(finish, notice)


def _invalidates(finish: LandedFinish, staged: PinnedState) -> bool:
    """Stage the invalidation the current evidence is owed now on `staged`; False only where it has no room.

    Owed is asked here, behind any commands the decision ran, rather than
    taken from the decision, whose answer was read before them: a command or
    a timeout configured otherwise while they ran moves the context the
    current evidence was taken under, and an equal tree no longer spares it
    (`rewrite_evidence.invalidates_current`). Through the settlement owner's
    own retirement, which keeps the whole binding and measures the comment's
    room; logged where that room is not there.
    """
    if not _rewrite_evidence.invalidates_current(finish) or _settlement.retire_current_evidence(staged):
        return True
    log.error(
        "issue=#%d holding the route of %.8s: the pinned comment has no room to invalidate "
        "the verification evidence its base rewrite moved past",
        finish.issue.number, finish.head,
    )
    return False


def _records(finish: LandedFinish, decided: RewriteEvidence, staged: PinnedState) -> None:
    """Stage the transaction a fresh or carried result is recorded as, where the comment can take it.

    Minted past every revision the issue spent and recorded through the
    transaction's own owner, which measures the record, its settlement, and
    the invalidation that settlement leaves room for. One it refuses leaves
    `staged` as it was, and the fresh reviewer owes the evidence.
    """
    licensed = _licensed(decided)
    if licensed is None:
        return
    binding, commands, copied_from = licensed
    pending = _record_state.mint_pending_evidence(staged, finish.issue.number, binding, commands, copied_from)
    if pending is not None and _record_state.record_pending_evidence(staged, pending):
        log.info(
            "issue=#%d recorded %s verification evidence revision %d for %.8s ahead of its route",
            finish.issue.number, decided.route.value, pending.revision, finish.head,
        )
        return
    log.error(
        "issue=#%d could not record the %s verification evidence of %.8s on its pinned comment; "
        "the fresh reviewer owes it",
        finish.issue.number, decided.route.value, finish.head,
    )


def _licensed(decided: RewriteEvidence) -> _Licensed | None:
    """What `decided` licenses recording, or None for a decision that records no evidence."""
    if decided.fresh is not None:
        binding, commands = decided.fresh
        return binding, commands, None
    carry = decided.carry
    if carry is None:
        return None
    return carry.binding, carry.commands, carry.copied_from


def _lands(finish: LandedFinish, staged: PinnedState) -> FinishOutcome | None:
    """Land what `staged` carries over the fresh comment; None where it landed or there was nothing to write."""
    if staged.data == finish.state.data:
        return None
    return _writes.lands(finish, staged, _writes.EVIDENCE)
