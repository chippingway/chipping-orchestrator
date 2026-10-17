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

Eight writes, and each lists what it has to land exactly among the records it
is decided on as well as among its own, since a field staged as it was read is
no move of the write's and would otherwise be left to whatever another road
did with it. `CHECKPOINT` makes the report debt durable and, on a finish that
announces, the reset round and the announcement mark beside it, the notice's
ledger entry reserved over the fresh ledger and kept beside it, and the record
of the event -- staged before it is prepared, so the announcement is measured
whole over the fresh comment before anything is said; it is decided
on the attempt being finished, the report records and claim the debt was
staged over, the park's flags, the round, and the evidence records, and it
lands only once the landed head's evidence is resolved: a transaction another
road recorded beside the one the finish settled or retired -- one recorded
while the settlement's own answer came back among them -- refuses the
announcement before its notice is posted, and the attempt stands for the next
finish to answer it. `EVIDENCE` makes the landed head's
evidence decision durable ahead of its announcement and its route
(`rewrite_finish_evidence`): the current evidence retired into history, the
transaction a fresh or carried result is recorded as, with the revision floor
it raises and the attempt's receipt of it, and the notice a failed run is owed
(`rewrite_finish_failures`) --
decided on the attempt, the debt, and every record the evidence is bound
through (`verification_durable`), so a report, a review subject, or an
evidence record another road moved while the commands ran refuses it.
`ABANDONMENT` retires a recorded transaction no route may take -- one
something was read moving under, or one recorded for a head the base advanced
past -- where the abandonment staged on the comment read afresh and guarded by
that reading did not land (`rewrite_finish_captured`): staged on the tick's
own copy instead (`abandons`) and decided only on the records it retires and
the attempt, so one comment reading that failed or one move under the write
does not leave the transaction standing. It owns the base tip the replay was
recorded as made onto too, which an abandonment with no room for its history
entry blanks.
`INVALIDATION` invalidates settled evidence a reading established movement
under where the write staged on the comment read afresh would not land
(`rewrite_finish_readiness.invalidates`, asked only by the dormant
settled-evidence policy and the recovery's dormant answers): staged on the
tick's own copy and decided only on the evidence records and the attempt --
landed without the publication's pinned fields among them (`lands`,
`publication` False), so a pull request or branch another road repointed
meanwhile is kept as it wrote it rather than refusing the write -- so a failed
reading of the comment does not leave a decision standing that a later
reading, once the movement is put back, would take as current. It owns
the base tip the replay was recorded as made onto too, which an invalidation
with no room for its history entry blanks -- decided on the current record
as well, so a successor another road settled in that evidence's place is
never marked moved, however the bounded history reads.
`ANNOUNCED_EVENT` records the `base_rebased` event a finish is filing for
the landed head, on its own and right ahead of it, decided on the attempt
alone, so the event goes out only behind a write proving the attempt stands.
`RELABEL` records the relabel the route makes to `workflow:validating`, on its
own and right ahead of it, decided on the attempt and every bound record, so
a later finish reads that relabel made rather than making it twice -- written
only by a finish held to the dormant settled-evidence policy.
`FINISH` retires the attempt, resets the round, spends a human's retry, and
clears a failure notice the route no longer owes, decided on the attempt, the
park's flags, the round, the claim the checkpoint made durable, and every
record the evidence is bound through -- so the head is routed only with
evidence decided and settled over the records the comment still carries: a
report, review subject, or evidence record another road moved since refuses
the route rather than letting it carry a decision about a review nobody is
handed any more. `PARK` records the park a debt with no room takes, decided on
what the checkpoint would have been -- the round included, since how wide it is
decides which of the two writes the debt was measured on had no room.

A finish held to the dormant settled-evidence policy
(`rewrite_finish_models.LandedFinish.proves_settled`) decides three of them on
more records (`prepares`, `lands`): the checkpoint, the event's record, and the
park on every record the evidence is bound through, so a report or review
record -- or an evidence record -- another road moved while the notice was
posted refuses each rather than riding into it unread. That policy alone reads
a refusal naming one of the records settled evidence's binding rests on
beyond the evidence records themselves (`BINDING_RECORDS`) as the movement
under that evidence it is (`BINDING_MOVED`, `_stopped`) -- a record the strict
edit found moved under any of its writes among them, named even where it is
put back before the comment is read again -- has the comment any refusal of
moved records was read over, its preparation's or its strict edit's, asked
what it records moving under the evidence however soon it is put back
(`verification_proof.ProofReading.reads`) -- the fresh reading a refused edit
was derived over, and the record a write that landed or went out unconfirmed
made of the comment, among them -- and reuses a debt park the tick reads
standing, or lands one over its notice already said, rather than posting it
again (`parks`). Every other finish
decides those writes as above, reads any refusal over a bound record as
`_BOUND_MOVED`, and parks anew.

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
# announcement: a transaction recorded, settled, or retired on them since is
# evidence the announcement would otherwise go out over unresolved.
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

# An abandonment staged on the tick's own copy, where the comment read afresh
# would not take one: decided only on the records it retires and the attempt,
# so a review, report, or approval another road moved since lands as the fresh
# comment carries it rather than refusing it -- save a carry's approval the copy
# still names, which another road's move refuses as the conflict it is.
ABANDONMENT = _commits.ReportWrite(
    owned=frozenset((*ABANDONS, _base_sync_state._PENDING_REWRITE_BASE)),
    decided_on=frozenset((_evidence_records.PENDING_EVIDENCE, _evidence_records.EVIDENCE_HISTORY)) | _ATTEMPT,
)

# An invalidation of settled evidence staged on the tick's own copy, where the
# comment read afresh would not take one (`rewrite_finish_readiness.invalidates`),
# or the base tip it blanks where that has no room: decided only on the
# evidence records it retires, the transaction beside them, and the attempt --
# never on the publication's pinned fields (`lands`, `publication` False) -- so
# a review, report, or publication record another road moved -- the very
# movement the invalidation answers, often -- lands as the fresh comment
# carries it rather than refusing it, while a successor settled in place of
# that evidence refuses both.
INVALIDATION = _commits.ReportWrite(
    owned=frozenset((
        _evidence_records.CURRENT_EVIDENCE, _evidence_records.EVIDENCE_HISTORY, _base_sync_state._PENDING_REWRITE_BASE,
    )),
    decided_on=frozenset((
        _evidence_records.PENDING_EVIDENCE, _evidence_records.CURRENT_EVIDENCE, _evidence_records.EVIDENCE_HISTORY,
    )) | _ATTEMPT,
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

# The record of the relabel a finish held to the dormant settled-evidence
# policy is making, landed on its own right ahead of that relabel
# (`rewrite_finish_announced.relabels_once`), decided on the attempt and every
# bound record, so one another road moved refuses it.
RELABEL = _commits.ReportWrite(
    owned=frozenset((_base_sync_state._PENDING_RELABELLED,)),
    decided_on=_ATTEMPT | _BOUND,
)

# Those of them settled evidence's binding rests on beyond the evidence records
# themselves -- the pull request, a report or its debt, a review subject: a
# write that reads one of them moved has read movement under the evidence.
BINDING_RECORDS = _BOUND - _EVIDENCE_RECORDS

# The announcement's writes and the debt's park as a finish held to the
# dormant settled-evidence policy prepares and lands them: decided on every
# bound record besides, so one another road moved while the notice was posted
# refuses each rather than riding into it unread, and the comment that
# refusal read is asked what it records moving under the evidence. The
# checkpoint owns the record of the relabel its route lands behind it too, so
# its preparation measures that record where the coordinator stages it
# (`rewrite_finish._checkpoints`); staged as the tick read it, it is no move.
_SETTLED = MappingProxyType({
    CHECKPOINT: CHECKPOINT.deciding_on(*_BOUND).owning(_base_sync_state._PENDING_RELABELLED),
    ANNOUNCED_EVENT: ANNOUNCED_EVENT.deciding_on(*_BOUND),
    PARK: PARK.deciding_on(*_BOUND),
})

# What a refusal that read a record of `_BOUND` moved observed: movement under
# any transaction recorded for the head, which the caller hands to the last
# word as its proof, so a record put back before that word reads it again
# revives nothing (`rewrite_finish_captured.stands_before_the_route`).
_BOUND_MOVED = ReportEvidence(
    ReportEvidenceVerdict.DEFER, "a record the evidence is bound through moved under a write finishing the landing",
)

# The same reading, for a finish held to the dormant settled-evidence policy,
# where what moved is one of `BINDING_RECORDS`, and not only the evidence
# records themselves, whose movement is a newer transaction for the head to
# answer: settled evidence is invalidated over it
# (`rewrite_finish_readiness.invalidates_behind`).
BINDING_MOVED = ReportEvidence(
    ReportEvidenceVerdict.DEFER, "a record the evidence's binding rests on moved under a write finishing the landing",
)

# The answers whose record of the comment went out -- landed, or sent with its
# answer lost -- rather than only being measured.
_WRITTEN = frozenset((_commit_models.CommitStatus.COMMITTED, _commit_models.CommitStatus.UNCONFIRMED))

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
    observed: ProofReading | None = None,
    **reserves: bool,
) -> FinishOutcome | None:
    """None where `staged` would land as `write` now, measured over the fresh comment; REFUSED otherwise.

    Asked ahead of an effect that depends on the write -- a notice, an event,
    a relabel -- so none is made for a record that could not follow it. What
    posting a notice writes is reserved at the widest a comment id is recorded
    at, over the ledger the fresh comment carries (`reserves`): `notice` is
    one on the issue thread, which enters the ledger and moves the watermark,
    and `ledger_entry` one on the pull request, which only enters the ledger.
    `observed` collects the movement a refusal read (`_stopped`). A finish
    held to the settled-evidence policy prepares the write as that policy
    decides it (`_SETTLED`), its refusal of moved records carrying the fresh
    reading it read them on, so what that comment records is asked of it
    however soon it is put back.
    """
    commit = _commits.ReportCommit(finish.gh, finish.issue, finish.state)
    held = _SETTLED.get(write, write) if finish.proves_settled else write
    decided = held.on_the_publication().reading_moves(observed is not None and finish.proves_settled)
    return _stopped(finish, commit.prepares(staged, decided, **reserves), observed)


def lands(
    finish: LandedFinish,
    staged: PinnedState,
    write: _commits.ReportWrite,
    observed: ProofReading | None = None,
    *,
    publication: bool = True,
) -> FinishOutcome | None:
    """Land `staged` as `write` over the fresh comment: None where it landed, laid over the tick's state.

    REFUSED where it was refused with nothing written, and UNCONFIRMED where it
    went out and nothing confirmed it. `observed` collects the movement a
    refusal read (`_stopped`) -- for a finish held to the dormant
    settled-evidence policy, what the comment its strict edit read records
    too, however soon it is put back (`report_commits.ReportWrite.reads_a_move`).
    `publication` False decides it on what `write` declares alone, the
    publication's pinned fields kept as the fresh comment carries them -- for
    `INVALIDATION`, which only ever makes evidence the tick read count for less.
    A finish held to the settled-evidence policy lands the write as that
    policy decides it (`_SETTLED`).
    """
    commit = _commits.ReportCommit(finish.gh, finish.issue, finish.state)
    held = _SETTLED.get(write, write) if finish.proves_settled else write
    decided = held.on_the_publication() if publication else held
    decided = decided.reading_moves(observed is not None and finish.proves_settled)
    return _stopped(finish, commit.lands(staged, decided), observed)


def abandons(finish: LandedFinish, stage: Callable[[PinnedState], bool]) -> bool | None:
    """Stage an abandonment on a copy of the tick's state with `stage`, and land it as `ABANDONMENT`.

    Whether what `stage` staged fit -- the transaction retired into history,
    or only dropped -- or None where the write did not land.
    """
    staged = staging(finish)
    fits = stage(staged)
    return fits if lands(finish, staged, ABANDONMENT) is None else None


def parks(finish: LandedFinish, observed: ProofReading | None = None) -> FinishOutcome:
    """Park `finish`'s landing for want of room for its debt, prepared before the park's notice is posted.

    Nothing is reset and nothing is cleared: the pull request already carries
    the head, and the attempt is what the reply brings back to record the debt
    and finish the route once somebody has made room. A park that would not
    land posts nothing. `observed` collects the movement a refusal read
    (`_stopped`). A finish held to the settled-evidence policy reuses a park
    the tick reads standing for the debt where no reply it was handed answers
    it, holds where the issue's conversation would not read, and lands one
    over the notice an earlier finish posted -- past the watermark, or past a
    reply handed in again -- ahead of a park write that did not land
    (`rewrite_finish_debt.noticed`), filing its `park_awaiting_human` event
    only where the event stream lacks that park's own
    (`rewrite_finish_debt.files_the_park`), so neither is made twice; its
    park's event names the landed head and the notice; the evidence is still
    proved around it (`rewrite_finish_stops`).
    """
    staged = staging(finish)
    staged.set(_base_sync_state._AWAITING_HUMAN, True)
    staged.set(_base_sync_state._PARK_REASON, _FOR_THE_DEBT)
    noticed = _debt.noticed(finish, staged) if finish.proves_settled else None
    if isinstance(noticed, FinishOutcome):
        return noticed
    stopped = prepares(finish, staged, PARK, observed, notice=noticed is None)
    if stopped is None and noticed is not None:
        stopped = _debt.files_the_park(finish, noticed)
    if stopped is not None:
        return stopped
    if noticed is None:
        # A dormant park names its head and its notice, so a later finish that
        # finds this notice said asks the event stream for this park's event alone.
        named = {"sha": finish.head, "names_the_notice": True} if finish.proves_settled else {}
        message = _debt.unrecorded(finish)
        _guards._park_awaiting_human(finish.gh, finish.issue, staged, message, reason=_FOR_THE_DEBT, **named)
    staged.set(_base_sync_state._PARK_REASON, _FOR_THE_DEBT)
    return lands(finish, staged, PARK, observed) or FinishOutcome.PARKED


def _stopped(
    finish: LandedFinish,
    outcome: _commit_models.CommitOutcome,
    observed: ProofReading | None = None,
) -> FinishOutcome | None:
    """None where `outcome` prepared or landed; what the finish stops at otherwise, logged.

    A refusal that names a record the evidence is bound through read that
    record moved, and that reading is appended to `observed` as the movement
    it is (`_BOUND_MOVED`): the guard read it once, and whatever reads the
    comment after may find it put back. For a finish held to the dormant
    settled-evidence policy only the records a binding rests on beyond the
    evidence records count (`BINDING_RECORDS`), observed as `BINDING_MOVED`:
    another road recording, settling, or retiring a transaction moves none of
    them, so a settlement another finish made under the write is no movement
    under that transaction (`verification_durable.moves_only_the_evidence`) --
    but a review or report record that edit read moved beside it is, named off
    the comment the strict edit read (`lands`), and so is any movement that
    very comment records under the transaction, asked of it as it was read
    (`verification_proof.ProofReading.reads`): a mark in the evidence's handoff
    place, a revision spent past it, or a blank of the attempt's base tip.
    A refused edit is asked of the fresh reading its candidate was derived
    over too (`pinned_commit_models.CommitOutcome.fresh`), ahead of the
    comment the edit found: the tick may hold a successor it took in beside
    records older than its binding, so that fresh reading -- matching the
    tick's own on every record the write is decided on -- can still read the
    successor off its own binding, however soon the edit finds it put back.
    For the same reason a write that landed, or went out with its answer lost,
    is asked of the record it made of the comment (`CommitOutcome.reading`):
    the fresh comment with the write laid over it, which such a successor
    lands beside unrefused; what it reads moving is the caller's to answer
    even where the finish goes on
    (`rewrite_finish_readiness.invalidates_behind`).
    """
    stopped = _UNLANDED.get(outcome.status)
    if stopped is not None:
        log.warning(
            "issue=#%d a write finishing its landed base rewrite of %.8s did not land (%s); "
            "posting, relabeling, and clearing nothing behind it",
            finish.issue.number, finish.head, (outcome.refusal or outcome.status).value,
        )
    moved = _BOUND.intersection(outcome.fields)
    if finish.proves_settled:
        moved = BINDING_RECORDS.intersection(moved)
    if observed is None:
        return stopped
    if moved:
        observed.observes(BINDING_MOVED if finish.proves_settled else _BOUND_MOVED)
    written = outcome.reading if outcome.status in _WRITTEN else None
    for comment in filter(None, (written, outcome.fresh, outcome.seen)):
        observed.reads(comment)
    return stopped
