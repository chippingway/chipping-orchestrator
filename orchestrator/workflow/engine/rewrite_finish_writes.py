# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The guarded commits a landed base rewrite's finish writes through, and the park it takes for want of room.

A finish writes the pinned comment at points requests apart -- behind the
notice and the audit event, around the relabel -- each decided on a reading of
the comment. Written whole from the state in hand, each would put back every
field another road moved since. So each lands through the guarded commit
(`pinned_commit`) under the tick-state guard the developer report's commits use
(`report_commits.ReportCommit`): captured over the reading the caller's state
was last synced with, owning every field the tick staged since beside the
fields each write declares, decided on the records each write declares and on
the pinned fields the publication is resolved from
(`ReportWrite.on_the_publication`), and keeping every other field -- unknown
ones included -- as the fresh reading carries it.

Four writes, and each lists what it has to land exactly among the records it
is decided on as well as among its own, since a field staged as it was read is
no move of the write's and would otherwise be left to whatever another road
did with it. `CHECKPOINT` makes the report debt durable and, on a finish that
announces, the reset round and the announcement mark beside it, the notice's
ledger entry reserved over the fresh ledger and kept beside it; it is decided
on the attempt being finished, the report records and claim the debt was
staged over, the park's flags, and the round. `EVIDENCE` makes the landed
head's evidence decision durable ahead of its route
(`rewrite_finish_evidence`): the current evidence retired into history, the
transaction a fresh or carried result is recorded as, with the revision floor
it raises, and the notice a failed run is owed (`rewrite_finish_failures`) --
or a transaction an earlier finish recorded abandoned, with the approval a
carry takes -- or, with no room for that, dropped and the attempt's recorded
base tip blanked (`rewrite_finish_captured`) -- decided on the attempt, the debt,
and every record the evidence is bound through (`verification_durable`), so a
report, a review subject, or an evidence record another road moved while the
commands ran refuses it.
`FINISH` retires the attempt, resets the round, spends a human's retry, and
clears a failure notice the route no longer owes, decided on the attempt, the
park's flags, the round, the claim the checkpoint made durable, and every
record the evidence is bound through -- so the head is routed only with
evidence decided over the records the comment still carries, a transaction
an earlier finish recorded and the evidence step left unchanged included: a
report, review subject, or evidence record another road moved since refuses
the route rather than letting it carry a decision about a review nobody is
handed any more. `PARK`
records the park a debt with no
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
still be written over it.
"""
from __future__ import annotations

import logging
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
from orchestrator.workflow.engine.rewrite_finish_failures import FAILED_VERIFICATION
from orchestrator.workflow.engine.rewrite_finish_models import FinishOutcome, LandedFinish
from orchestrator.workflow.engine.verification_carries import ABANDONS

log = logging.getLogger("orchestrator.workflow")

_ROUND = _base_sync_state._REVIEW_ROUND

_ATTEMPT = frozenset(_attempts._ATTEMPT_KEYS)

_PARK_FLAGS = frozenset((_base_sync_state._AWAITING_HUMAN, _base_sync_state._PARK_REASON))

# The records a rewrite's debt is staged over: the report records whose settled
# subject it follows, and the claim already standing.
_CLAIM = frozenset((*_commits.REPORT_RECORDS, _rewrite_debt.REWRITE_DEBT))

CHECKPOINT = _commits.ReportWrite(
    owned=frozenset((_rewrite_debt.REWRITE_DEBT, _ROUND, _base_sync_state._PENDING_ANNOUNCED_SHA)),
    decided_on=_CLAIM | _ATTEMPT | _PARK_FLAGS | {_ROUND},
)

EVIDENCE = _commits.ReportWrite(
    owned=frozenset((
        _evidence_records.PENDING_EVIDENCE,
        _evidence_records.CURRENT_EVIDENCE,
        _evidence_records.EVIDENCE_HISTORY,
        _evidence_records.REVISION_FLOOR,
        FAILED_VERIFICATION,
        *ABANDONS,
        _base_sync_state._PENDING_REWRITE_BASE,
    )),
    decided_on=frozenset(_durable._BOUND_RECORDS) | _ATTEMPT | {_rewrite_debt.REWRITE_DEBT},
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
    *,
    notice: bool = False,
    ledger_entry: bool = False,
) -> FinishOutcome | None:
    """None where `staged` would land as `write` now, measured over the fresh comment; REFUSED otherwise.

    Asked ahead of an effect that depends on the write -- a notice, an event,
    a relabel -- so none is made for a record that could not follow it. What
    posting a notice writes is reserved at the widest a comment id is recorded
    at, over the ledger the fresh comment carries: `notice` is one on the
    issue thread, which enters the ledger and moves the watermark, and
    `ledger_entry` one on the pull request, which only enters the ledger.
    """
    commit = _commits.ReportCommit(finish.gh, finish.issue, finish.state)
    prepared = commit.prepares(
        staged, write.on_the_publication(), notice=notice, ledger_entry=ledger_entry,
    )
    return _stopped(finish, prepared)


def lands(finish: LandedFinish, staged: PinnedState, write: _commits.ReportWrite) -> FinishOutcome | None:
    """Land `staged` as `write` over the fresh comment: None where it landed, laid over the tick's state.

    REFUSED where it was refused with nothing written, and UNCONFIRMED where it
    went out and nothing confirmed it.
    """
    commit = _commits.ReportCommit(finish.gh, finish.issue, finish.state)
    return _stopped(finish, commit.lands(staged, write.on_the_publication()))


def parks(finish: LandedFinish) -> FinishOutcome:
    """Park `finish`'s landing for want of room for its debt, prepared before the park's notice is posted.

    Nothing is reset and nothing is cleared: the pull request already carries
    the head, and the attempt is what the reply brings back to record the debt
    and finish the route once somebody has made room. A park that would not
    land posts nothing.
    """
    reason = _base_sync_state._REASON_AUTO_BASE_REBASE_UNRECORDED_DEBT
    staged = staging(finish)
    staged.set(_base_sync_state._AWAITING_HUMAN, True)
    staged.set(_base_sync_state._PARK_REASON, reason)
    stopped = prepares(finish, staged, PARK, notice=True)
    if stopped is not None:
        return stopped
    message = _debt.unrecorded(finish)
    _guards._park_awaiting_human(finish.gh, finish.issue, staged, message, reason=reason)
    staged.set(_base_sync_state._PARK_REASON, reason)
    return lands(finish, staged, PARK) or FinishOutcome.PARKED


def _stopped(finish: LandedFinish, outcome: _commit_models.CommitOutcome) -> FinishOutcome | None:
    """None where `outcome` prepared or landed; what the finish stops at otherwise, logged."""
    stopped = _UNLANDED.get(outcome.status)
    if stopped is not None:
        why = outcome.refusal or outcome.status
        log.warning(
            "issue=#%d a write finishing its landed base rewrite of %.8s did not land (%s); "
            "posting, relabeling, and clearing nothing behind it",
            finish.issue.number, finish.head, why.value,
        )
    return stopped
