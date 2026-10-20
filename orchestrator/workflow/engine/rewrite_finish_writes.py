# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The guarded commits a landed base rewrite's finish writes through, and the park it takes for want of room.

A finish writes the pinned comment at points requests apart -- behind the
notice and the audit event, around the relabel -- each one a checkpoint over
the last. Written whole from the state in hand, each would put back what the
comment carries over whatever the tick did not stage. So each lands through
the guarded commit (`pinned_commit`) under the tick-state guard the developer
report's commits use (`report_commits.ReportCommit`): captured over the
reading the caller's state was last synced with -- the tick's own last
confirmed write, or the reading taken once the writer claim was held --
owning every field the tick staged since beside the fields each write
declares, decided on the records each write declares and on the pinned
fields the publication is resolved from (`ReportWrite.on_the_publication`),
and keeping every other field -- unknown ones included -- as the fresh reading
carries it. A write that landed advances that reading, so the next one is
decided over it; a record that reads otherwise without a write of the
finish's is no checkpoint of its own, and refuses the write.

Six writes, and each lists what it has to land exactly among the records it
is decided on as well as among its own, since a field staged as it was read is
no move of the write's and would otherwise be left to whatever the comment
carries. `CHECKPOINT` makes the report debt durable and, on a finish that
announces, the reset round and the announcement mark beside it, the notice's
ledger entry reserved over the fresh ledger and kept beside it, and the record
of the event -- staged before it is prepared, so the announcement is measured
whole over the fresh comment before anything is said; it is decided
on the attempt being finished, the report records and claim the debt was
staged over, the park's flags, the round, and the evidence records, and it
lands only once the landed head's evidence is resolved: an evidence record
that no longer reads as the finish resolved it refuses the announcement
before its notice is posted, and the attempt stands for the next finish to
read. `EVIDENCE` makes the landed head's evidence decision durable ahead of
its announcement and its route (`rewrite_finish_evidence`): the current
evidence retired into history, the transaction a fresh or carried result is
recorded as, with the revision floor it raises and the attempt's receipt of
it, and the notice a failed run is owed (`rewrite_finish_failures`) --
decided on the attempt, the debt, and every record the evidence is bound
through (`verification_durable`), so a report, a review subject, or an
evidence record that no longer reads as the decision was taken over refuses
it. `ABANDONMENT` retires a recorded transaction no route may take -- one
something was read moving under, or one recorded for a head the base advanced
past (`rewrite_finish_captured`) -- staged on the tick's own copy (`abandons`)
and decided only on the records it retires and the attempt. It owns the base
tip the replay was recorded as made onto too, which an abandonment with no
room for its history entry blanks. `ANNOUNCED_EVENT` records the
`base_rebased` event a finish is filing for the landed head, on its own and
right ahead of it, decided on the attempt alone, so the event goes out only
behind a write proving the attempt stands. `FINISH` retires the attempt,
resets the round, spends a human's retry, and clears a failure notice the
route no longer owes, decided on the attempt, the park's flags, the round,
the claim the checkpoint made durable, and every record the evidence is bound
through -- so the head is routed only with evidence decided and settled over
the records the comment still carries. `PARK` records the park a debt with no
room takes, decided on what the checkpoint would have been -- the round
included, since how wide it is decides which of the two writes the debt was
measured on had no room.

Anything but a commit that landed stops the finish there (`lands`,
`prepares`), and nothing that depends on the write is made: a refusal writes
nothing, and an edit GitHub never confirmed may or may not have landed. Either
withholds the tick's state from every whole-state write behind it
(`ReportCommit.withholds`) -- save a refusal for room alone over a comment
that, read again, is still the one the tick synced with. That comment is
simply too full, a debt park that cannot fit on it included, and the state may
still be written over it. A refusal that names a record the evidence is bound
through is collected for a caller that asks (`_stopped`), as movement under a
transaction recorded for the head.
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from types import MappingProxyType

from orchestrator.git.base_sync import attempts as _attempts, state as _base_sync_state
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    guards as _guards,
    pinned_commit_models as _commit_models,
    prompt_delivery as _prompt_delivery,
    report_commits as _commits,
    report_rewrite_debt as _rewrite_debt,
    rewrite_finish_debt as _debt,
    verification_durable as _durable,
    verification_records as _evidence_records,
)
from orchestrator.workflow.engine.report_evidence_models import ReportEvidence, ReportEvidenceVerdict
from orchestrator.workflow.engine.rewrite_finish_failures import FAILED_VERIFICATION
from orchestrator.workflow.engine.rewrite_finish_models import FinishOutcome, LandedFinish
from orchestrator.workflow.engine.verification_carries import ABANDONS
from orchestrator.workflow.engine.verification_proof import ProofReading

log = logging.getLogger("orchestrator.workflow")

_ROUND = _base_sync_state._REVIEW_ROUND

_ATTEMPT = frozenset(_attempts._ATTEMPT_KEYS)

_PARK_FLAGS = frozenset((_base_sync_state._AWAITING_HUMAN, _base_sync_state._PARK_REASON))

# Why a debt with no room parks.
_FOR_THE_DEBT = _base_sync_state._REASON_AUTO_BASE_REBASE_UNRECORDED_DEBT

# The records a rewrite's debt is staged over: the report records whose settled
# subject it follows, and the claim already standing.
_CLAIM = frozenset((*_commits.REPORT_RECORDS, _rewrite_debt.REWRITE_DEBT))

# The evidence records a landed head's evidence step resolves before the
# announcement: one that reads otherwise than the step left it is evidence the
# announcement would otherwise go out over unresolved.
_EVIDENCE_RECORDS = frozenset((
    _evidence_records.PENDING_EVIDENCE,
    _evidence_records.CURRENT_EVIDENCE,
    _evidence_records.EVIDENCE_HISTORY,
    _evidence_records.EVIDENCE_HANDOFF,
    _evidence_records.REVISION_FLOOR,
))

CHECKPOINT = _commits.ReportWrite(
    owned=frozenset((
        _rewrite_debt.REWRITE_DEBT,
        _ROUND,
        _base_sync_state._PENDING_ANNOUNCED_SHA,
        _base_sync_state._PENDING_ANNOUNCED_EVENT,
    )),
    decided_on=_CLAIM | _ATTEMPT | _PARK_FLAGS | {_ROUND} | _EVIDENCE_RECORDS,
)

EVIDENCE = _commits.ReportWrite(
    owned=frozenset((
        _evidence_records.PENDING_EVIDENCE,
        _evidence_records.CURRENT_EVIDENCE,
        _evidence_records.EVIDENCE_HISTORY,
        _evidence_records.REVISION_FLOOR,
        FAILED_VERIFICATION,
        _base_sync_state._PENDING_EVIDENCE_RECEIPT,
    )),
    decided_on=frozenset(_durable._BOUND_RECORDS) | _ATTEMPT | {_rewrite_debt.REWRITE_DEBT},
)

# An abandonment staged on the tick's own copy: decided only on the records it
# retires and the attempt, so a review or report record it never reads is kept
# as the comment carries it -- save a carry's approval the copy still names,
# which a comment carrying another refuses as the conflict it is.
ABANDONMENT = _commits.ReportWrite(
    owned=frozenset((*ABANDONS, _base_sync_state._PENDING_REWRITE_BASE)),
    decided_on=frozenset((_evidence_records.PENDING_EVIDENCE, _evidence_records.EVIDENCE_HISTORY)) | _ATTEMPT,
)

# The record of the `base_rebased` event a finish is filing, landed on its own
# right ahead of the event and of the checkpoint (`rewrite_finish_events`), so
# the event goes out only behind a write proving the attempt still stands.
ANNOUNCED_EVENT = _commits.ReportWrite(
    owned=frozenset((_base_sync_state._PENDING_ANNOUNCED_EVENT,)),
    decided_on=_ATTEMPT,
)

FINISH = _commits.ReportWrite(
    owned=_ATTEMPT | _PARK_FLAGS | {
        _ROUND, _prompt_delivery.PINNED_LAST_ACTION_COMMENT_ID, FAILED_VERIFICATION,
    },
    decided_on=frozenset(_durable._BOUND_RECORDS) | _ATTEMPT | _PARK_FLAGS | {_ROUND, _rewrite_debt.REWRITE_DEBT},
)

PARK = _commits.ReportWrite(
    owned=_PARK_FLAGS | {_prompt_delivery.PINNED_LAST_ACTION_COMMENT_ID},
    decided_on=_CLAIM | _ATTEMPT | _PARK_FLAGS | {_ROUND},
)

# The records a transaction recorded for the landed head is bound through.
_BOUND = frozenset(_durable._BOUND_RECORDS)

# What a refusal that read a record of `_BOUND` moved observed: movement under
# any transaction recorded for the head, which the caller hands to the last
# word as its proof, so a record put back before that word reads it again
# revives nothing (`rewrite_finish_captured.stands_before_the_route`).
_BOUND_MOVED = ReportEvidence(
    ReportEvidenceVerdict.DEFER, "a record the evidence is bound through moved under a write finishing the landing",
)

# What a write that did not land is answered as.
_UNLANDED = MappingProxyType({
    _commit_models.CommitStatus.UNCONFIRMED: FinishOutcome.UNCONFIRMED,
    _commit_models.CommitStatus.REFUSED: FinishOutcome.REFUSED,
})


def staging(finish: LandedFinish) -> PinnedState:
    """A copy of the tick's state for one write to be staged on, the tick's own left as it is."""
    return _commits.ReportCommit(finish.gh, finish.issue, finish.state).staging()


def retirement(finish: LandedFinish) -> PinnedState:
    """The tick's state with the `FINISH` write staged on a copy of it.

    The whole attempt retired, the round reset, and the human reply a recovery
    re-entered on spent with the park it answered: a finish that dropped the
    attempt without spending that reply would leave the park flagged beside a
    route nothing brings back. A failure notice recorded for the landed head
    is cleared with it, since the route behind it is taken only once the pull
    request carries that notice, and a head continued to another rebase owes
    none.
    """
    staged = staging(finish)
    if finish.retry is not None:
        staged.set(_prompt_delivery.PINNED_LAST_ACTION_COMMENT_ID, finish.retry)
        staged.set(_base_sync_state._AWAITING_HUMAN, False)
        staged.set(_base_sync_state._PARK_REASON, None)
    _attempts._clears_the_attempt(staged)
    staged.set(_ROUND, 0)
    if staged.carries(FAILED_VERIFICATION):
        staged.set(FAILED_VERIFICATION, None)
    return staged


def prepares(
    finish: LandedFinish,
    staged: PinnedState,
    write: _commits.ReportWrite,
    **reserves: bool,
) -> FinishOutcome | None:
    """None where `staged` would land as `write` now, measured over the fresh comment; REFUSED otherwise.

    Asked ahead of an effect that depends on the write -- a notice, an event,
    a relabel -- so none is made for a record that could not follow it. What
    posting a notice writes is reserved at the widest a comment id is recorded
    at, over the ledger the fresh comment carries (`reserves`): `notice` is
    one on the issue thread, which enters the ledger and moves the watermark,
    and `ledger_entry` one on the pull request, which only enters the ledger.
    """
    commit = _commits.ReportCommit(finish.gh, finish.issue, finish.state)
    return _stopped(finish, commit.prepares(staged, write.on_the_publication(), **reserves))


def lands(
    finish: LandedFinish,
    staged: PinnedState,
    write: _commits.ReportWrite,
    observed: ProofReading | None = None,
) -> FinishOutcome | None:
    """Land `staged` as `write` over the fresh comment: None where it landed, laid over the tick's state.

    REFUSED where it was refused with nothing written, and UNCONFIRMED where it
    went out and nothing confirmed it. `observed` collects the movement a
    refusal read (`_stopped`).
    """
    commit = _commits.ReportCommit(finish.gh, finish.issue, finish.state)
    return _stopped(finish, commit.lands(staged, write.on_the_publication()), observed)


def abandons(finish: LandedFinish, stage: Callable[[PinnedState], bool]) -> bool | None:
    """Stage an abandonment on a copy of the tick's state with `stage`, and land it as `ABANDONMENT`.

    Whether what `stage` staged fit -- the transaction retired into history,
    or only dropped -- or None where the write did not land.
    """
    staged = staging(finish)
    fits = stage(staged)
    return fits if lands(finish, staged, ABANDONMENT) is None else None


def parks(finish: LandedFinish) -> FinishOutcome:
    """Park `finish`'s landing for want of room for its debt, prepared before the park's notice is posted.

    Nothing is reset and nothing is cleared: the pull request already carries
    the head, and the attempt is what the reply brings back to record the debt
    and finish the route once somebody has made room. A park that would not
    land posts nothing.
    """
    staged = staging(finish)
    staged.set(_base_sync_state._AWAITING_HUMAN, True)
    staged.set(_base_sync_state._PARK_REASON, _FOR_THE_DEBT)
    stopped = prepares(finish, staged, PARK, notice=True)
    if stopped is not None:
        return stopped
    message = _debt.unrecorded(finish)
    _guards._park_awaiting_human(finish.gh, finish.issue, staged, message, reason=_FOR_THE_DEBT)
    staged.set(_base_sync_state._PARK_REASON, _FOR_THE_DEBT)
    return lands(finish, staged, PARK) or FinishOutcome.PARKED


def _stopped(
    finish: LandedFinish,
    outcome: _commit_models.CommitOutcome,
    observed: ProofReading | None = None,
) -> FinishOutcome | None:
    """None where `outcome` prepared or landed; what the finish stops at otherwise, logged.

    A refusal that names a record the evidence is bound through read that
    record moved, and that reading is appended to `observed` as the movement
    it is (`_BOUND_MOVED`): the guard read it once, and whatever reads the
    comment after may find it put back.
    """
    stopped = _UNLANDED.get(outcome.status)
    if stopped is not None:
        log.warning(
            "issue=#%d a write finishing its landed base rewrite of %.8s did not land (%s); "
            "posting, relabeling, and clearing nothing behind it",
            finish.issue.number, finish.head, (outcome.refusal or outcome.status).value,
        )
    if observed is not None and _BOUND.intersection(outcome.fields):
        observed.observes(_BOUND_MOVED)
    return stopped
