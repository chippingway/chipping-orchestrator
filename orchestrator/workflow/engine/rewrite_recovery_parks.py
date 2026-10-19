# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The park a base rewrite's recovery takes, landed over the comment read afresh rather than written whole.

Every recovery park posts its notice on the issue thread and then records
the park (`git/base_sync/persistence._parks_the_recovery`), and that record
is decided on the comment as the tick read it a notice earlier: long enough
for another road to settle and review a later report, or move an evidence
record. Written whole from the tick's state, the record would put each of
those back, and nothing on the comment would say so. The park over a landed
reset is where that costs the most, since the attempt it drops takes out with
it the evidence a finish captured or settled for the landed head
(`rewrite_landing_retirement.retires_over_the_reset`): written whole, it would
retire that evidence and put back the report it was superseded by beside it.

These are the answers a recovery context carries for that
(`_AutoRebaseRecoveryContext.lands_a_park`, `records_before_a_reset`,
`proves_before_a_park`, `lands_a_clear`), and they are dormant: no recovery
road, eligibility gate, or dispatcher hold the workflow builds a context for
is handed them yet, so every recovery park and clear is still written whole
and every reset made with nothing recorded ahead of it. So is the hold behind
a publication gate that held a recovery's push (`lands_a_hold`): its proof
taken first, as before a park that keeps the attempt, what the tick staged
before that proof kept across every write it lands (`rewrite_recovery_staging`),
and only what the tick staged since its reading landed, as `HOLD`, over the
comment read afresh, answering whether all of it landed; no recovery road
records its hold through it yet. A park made again over a record that never
landed takes in the notice the conversation already carries rather than
saying it twice (`rewrite_recovery_notices`). A clear of the attempt -- under
a label the refresh does not drive, or of one whose checkout never left the
anchor -- is recorded as `CLEAR` over the comment read afresh
(`lands_a_clear`), so a successor another road settled while the checkout was
read refuses it, its revision floor kept; and one written right behind a
clear that landed -- another attempt, or any record a binding rests on, a
revision floor raised alone among them -- holds the tick, its state withheld.

The park (`lands_a_park`) lands through the guarded commit
(`report_commits.ReportCommit`) as `PARK`: owning every field the tick staged
since its reading -- the park's flags, and the watermark and ledger its notice
moved, and over a landed reset the attempt with every record it abandoned and
the evidence retired beside it -- decided on the attempt, the park's flags,
and the evidence records as the tick read them, and keeping every other
field, a report or review record among them, as the fresh comment carries it.
A record refused or never confirmed is no park: the tick's state is withheld
from every whole-state write behind it (`ReportCommit.withholds`), its own
park flag still holding this tick's handlers back, and the next tick's
recovery reads the comment as it then stands, with the attempt it carries, and
answers it again. A state nothing was read into has no reading to guard it by
and is written whole, as every park always was.

A reset park moves the checkout before any of that is written, and with it
the landing a finish captured or settled evidence for the head over.
Abandoned or retired only in the park's write, or behind it, that evidence
would outlive a process lost between the reset and the write, or a write that
did not land, and a checkout put back on the head before the next poll would
prove it again -- settle a captured run, or route a settled one as current.
So the reset is recorded against it first (`records_the_reset`): the base tip
the attempt recorded its replay as made onto is blanked in a write of its own,
which only shrinks the comment, and with no tip nothing proves which base the
head was replayed onto, so every later proof of that evidence defers
(`rewrite_evidence_proof.standing_refusal`), abandoning a captured run and
invalidating a settled one whole once the comment has room. The blank is
made ahead of every reset whose attempt records a tip, whatever evidence the
tick read, and decided on every evidence record as the tick read them, so
evidence another road recorded or settled since refuses it, and evidence
settled behind it reads it as movement; a tip put back over one the tick read
blank refuses an unrecorded reset. A blank refused or never confirmed
holds the tick with nothing reset or cleaned, and the tick's state, which
still carries the tip, is withheld from every whole-state write behind it, so
a blank that landed with its answer lost is never put back. A blank that
landed is followed by the comment read afresh, and a tip put back or another
attempt pinned right behind it holds the reset the same way. A tick whose
state carries another attempt by then -- one a proof took in off the comment
-- blanks nothing and holds the same way, so no reset is recorded over the
tip a replacement attempt records. Movement the record reads is proved
before the reset goes on, and the comment read again behind each proof:
evidence standing there under a receipt read moving -- a successor, or the
run put back -- is proved again, until a reading carries none. The record
keeps what the tick staged as a proof keeps it, its usage landing in a write
of its own ahead of the record's own, wherever no proof keeps it already. A reset git
refused moved nothing, and the git owner
stages the tip back for the park that keeps the attempt, so the evidence
stands for that park's proof as it did before.

A park that keeps the attempt keeps the evidence with it for the reply that
brings the recovery back, so that evidence is proved before the park
(`proves_before_a_park`), and once more behind its notice and record
(`lands_a_park`) -- landed, refused, or raised -- since the notice is long
enough for another road to settle a later report. Movement the record's
commit read -- in the record it sent, the comment its strict edit found moved,
or the fresh reading behind that edit -- is read against each evidence's own
binding (`rewrite_landing_retirement.moved_under`) and handed to that proof as
read, so putting a report, the tip, or the evidence back before the reply
revives nothing, and a record no binding rests on is no movement. Behind a
record refused or sent with its answer lost, the comment's evidence is laid
over the tick's state first (`rewrite_landing_retirement.reconciles`), so a
successor another road settled meanwhile is proved on its own binding, and
that record's staging rides none of the proof's writes. A checkout gone from
disk has nothing to prove the landing over, so its evidence is retired as over
the reset recorded against it, each in its own write (`records_the_reset`),
ahead of a park or hold and behind one (`proves_before_a_park`), so a park or
hold whose record is refused, or never made, leaves it retired all the same.
The comment is reread behind that retirement: evidence written back is
retired again, the tick held, as over a successor or another attempt, nothing
reset. One a caller read gone or off the landing (`lost`, `heads_read`), one
the proof found gone mid-request or read off the landing, and one an earlier
proof read but no write recorded (`owed_events.loss_owed`) are recorded and
retired alike, however soon the checkout is back, the attempt owing that loss
to every later proof from the moment it is read. A retirement that does not
land withholds the tick's state, which may hold a successor's floor stale.
"""
from __future__ import annotations

import logging
from dataclasses import replace

from orchestrator.git.base_sync import attempts as _attempts, state as _base_sync_state
from orchestrator.git.base_sync.models import _AutoRebaseRecoveryContext
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    pinned_commit_models as _commit_models,
    prompt_delivery as _prompt_delivery,
    report_commits as _commits,
    rewrite_finish_writes as _writes,
    rewrite_landing_records as _landing_records,
    rewrite_landing_retirement as _retirement,
    rewrite_recovery_notices as _notices,
    verification_records as _evidence_records,
)
from orchestrator.workflow.engine.owed_events import loss_owed, owes_a_loss
from orchestrator.workflow.engine.report_evidence_models import ReportEvidence
from orchestrator.workflow.engine.rewrite_recovery_readings import (
    LEFT_THE_CHECKOUT,
    AsksEveryReading,
    RecordsALostCheckout,
    asks_every_reading,
    stands_as_recovered,
)
from orchestrator.workflow.engine.rewrite_recovery_staging import (
    adds_the_totals,
    keeps_the_staging,
    lands_the_retirement,
)
from orchestrator.workflow.engine.verification_durable import durable_comment

log = logging.getLogger("orchestrator.workflow")

_PARK_FLAGS = frozenset((_base_sync_state._AWAITING_HUMAN, _base_sync_state._PARK_REASON))

# The base tip the attempt recorded its replay as made onto, which the reset's record blanks.
_TIP = _base_sync_state._PENDING_REWRITE_BASE

# What a recovery hold records: whatever the tick staged since its reading --
# a publication gate's own record of the no-op it held -- decided on the
# attempt it keeps, so every evidence record stays as the comment carries it.
# Its strict edit keeps the comment a refusal read (`reads_a_move`), which the
# proof behind it reads for movement.
HOLD = _commits.ReportWrite(
    owned=frozenset(), decided_on=frozenset(_attempts._ATTEMPT_KEYS),
).reading_moves(True)

# A clear's record, decided on the attempt and evidence records so a successor settled meanwhile refuses it; a
# retirement over a checkout read gone lands as it too.
CLEAR = _commits.ReportWrite(
    owned=frozenset(),
    decided_on=frozenset(_attempts._ATTEMPT_KEYS) | {
        _evidence_records.PENDING_EVIDENCE,
        _evidence_records.CURRENT_EVIDENCE,
        _evidence_records.EVIDENCE_HISTORY,
    },
)

# A park's record, decided on the attempt it keeps or drops, the park's own
# flags, and the evidence records a landed reset retires beside the attempt,
# its strict edit keeping the comment a refusal read as the hold's does.
PARK = _commits.ReportWrite(
    owned=_PARK_FLAGS | {_prompt_delivery.PINNED_LAST_ACTION_COMMENT_ID},
    decided_on=frozenset(_attempts._ATTEMPT_KEYS) | _PARK_FLAGS | {
        _evidence_records.PENDING_EVIDENCE,
        _evidence_records.CURRENT_EVIDENCE,
        _evidence_records.EVIDENCE_HISTORY,
    },
).reading_moves(True)


def lands_a_park(context: _AutoRebaseRecoveryContext, message: str, reason: str) -> None:
    """Park `context`'s issue for a human with `message` and `reason`, recorded through the guarded commit as `PARK`.

    The notice is posted and the park staged on the tick's state as every
    auto-rebase park stages it (`git/base_sync/persistence._park_auto_rebase_failure`)
    -- or, where an earlier tick's park of the attempt posted it and its record
    never landed, the notice the conversation carries is taken in instead,
    nothing said twice (`rewrite_recovery_notices.parks_awaiting_human`) --
    and what lands is laid over that state, so whatever the recovery does behind
    it starts from the comment as it now stands. Behind it, whether it landed
    or not, evidence the park leaves standing beside the attempt is proved once
    more over the comment read afresh (`rewrite_landing_retirement.retires_unproved`),
    so a report another road settled while the notice was posted is read
    moving under it now rather than put back unread before the reply. Where
    the record the commit made of the comment already carried such a move --
    a record off the binding of evidence it is asked of, in the record that
    landed, in the one sent with its answer lost, which is never laid over the
    tick's state, or in the comment its strict edit found moved under it and
    was refused over, or the fresh reading behind that edit -- that is movement read,
    handed to the proof as its answer, so a record put back between the
    park's commit and the proof revives nothing. A notice whose post raised --
    refused, or posted with its answer lost -- records nothing, and the proof
    is taken before the error goes on, over the evidence the comment carries
    by then (`rewrite_landing_retirement.reconciles`), so a report moved while
    it was posted is read moving all the same -- under a successor another
    road settled meanwhile too, proved on its own binding. A checkout gone
    from disk behind the notice or the record has the reset recorded instead
    (`proves_before_a_park`).
    """
    state = context.state
    try:
        _notices.parks_awaiting_human(context, message, reason)
    except Exception:
        proves_before_a_park(context, _retirement.reconciles(context))
        raise
    state.set(_base_sync_state._PARK_REASON, reason)
    if state.synced is None:
        context.gh.write_pinned_state(context.issue, state)
        return
    _lands_then_proves(context, PARK, "park")


def lands_a_hold(context: _AutoRebaseRecoveryContext) -> bool:
    """Prove what a recovery hold keeps, then record the hold over the comment read afresh, as `HOLD`; whether it did.

    A publication gate that held a recovery's push -- the landed road's leased
    no-op (`rewrite_landed`), or the retry's reissued push (`rewrite_retry`)
    -- keeps the attempt, so its evidence
    is proved first, as before every park that keeps it
    (`proves_before_a_park`): over a checkout gone from disk the reset is
    recorded against it and it is retired, each in a write of its own, so a
    hold record refused or never confirmed leaves it retired. Where that proof
    does not land -- the reset not
    recorded among it -- nothing is recorded, for a later tick to answer. The
    gate's own record, staged on the tick's state before this is asked, is
    kept across every write that proof lands, so the hold's record still
    carries it. The gate's answer is long enough for another road to record a newer
    transaction, so only what the tick staged since its reading lands, every
    other field kept as the fresh comment carries it, and a record refused or
    never confirmed withholds the tick's state. Behind the record the evidence
    is proved once more, over the move the record itself carried, as behind
    every park (`lands_a_park`) -- or the reset recorded, over a checkout gone
    from disk by then. A state nothing was read into is written whole.
    True where the proof, the record, and the proof behind it all landed.
    """
    if not proves_before_a_park(context):
        return False
    if context.state.synced is None:
        context.gh.write_pinned_state(context.issue, context.state)
        return True
    return _lands_then_proves(context, HOLD, "hold")


def lands_a_clear(context: _AutoRebaseRecoveryContext) -> bool:
    """Record a clear the tick staged on `context.state` over the comment read afresh, as `CLEAR`; whether it landed.

    Only what the tick staged lands; a successor settled meanwhile refuses it, its floor kept. A clear not landing
    records the reset (`records_the_reset`) and proves the fresh comment with that move (`proves_before_a_park`).
    One that landed is followed by the comment read afresh: a successor, another attempt, or anything else the clear
    was decided on written right behind it -- a revision floor raised, or any other record a binding rests on moved,
    among them (`verification_durable.durable_comment`) -- or a comment that would not read holds the tick too, its
    state withheld, so no write of it puts back what that road wrote. A state nothing was read into is written whole.
    """
    if context.state.synced is None:
        context.gh.write_pinned_state(context.issue, context.state)
        return True
    moved: dict[str, ReportEvidence] = {}
    asked = asks_every_reading(
        context, lambda reading: _retirement.moved_under(reading, tick=context.state, into=moved),
    )
    landed = _commits.ReportCommit(
        asked.gh, context.issue, context.state,
    ).lands(context.state, CLEAR)
    if landed.status is _commit_models.CommitStatus.COMMITTED:
        refused = durable_comment(context.gh, context.issue, context.state, CLEAR.decided_on)[1]
        if refused is None:
            return True
        log.warning(
            "issue=#%d the clear of its auto-rebase attempt landed, but the comment read afresh behind it carries "
            "another road's records; holding, for the next tick to answer the comment as it then stands",
            context.issue.number,
        )
        context.state.withheld = True
        return False
    log.warning(
        "issue=#%d the clear of its auto-rebase attempt did not land (%s); nothing is cleared, and the next "
        "tick answers the comment as it then stands",
        context.issue.number, (landed.refusal or landed.status).value,
    )
    moving = replace(context, state=RecordsALostCheckout.as_read(context.state))
    moved.update(dict.fromkeys(_retirement.receipts(moving.state), LEFT_THE_CHECKOUT))
    records_the_reset(moving)
    proves_before_a_park(moving, _retirement.reconciles(moving, moved))
    return False


def proves_before_a_park(
    context: _AutoRebaseRecoveryContext, moved: dict[str, ReportEvidence] | None = None, *, lost=(),
) -> bool:
    """Whether a recovery park or hold that keeps the attempt may go on, what it keeps proved first.

    The proof is the recovery's (`rewrite_landing_retirement.retires_unproved`),
    over a transaction a finish captured and evidence one settled alike. A
    checkout gone from disk has no reading to prove the landing over, so the
    reset is recorded against the evidence and the evidence retired as over
    it, each in its own write (`records_the_reset`), so a park write refused,
    unconfirmed, cut short by a lost process, or never made leaves it retired
    however the checkout and base tip are put back. One not landing holds the
    tick with nothing parked.

    Behind a park's or hold's record, or a notice that raised, it is asked
    once more, `moved` the movement already read there -- handed only then --
    which a checkout on disk hands the proof as read. A checkout gone from
    disk by then, under the record's write or the notice's post among it,
    has the reset recorded and the evidence retired the same way.

    Asked ahead of a record, the proof keeps what the tick staged before it
    -- a gate's record of a hold, or a tip staged back behind a reset git
    refused -- across every write it lands, for the record behind, save what
    a proof write already carried, and save the totals among it -- usage --
    which ride none of the proof's writes and land first, in a write of their
    own read like every other the proof takes (`rewrite_recovery_staging.adds_the_totals`).
    Behind a record its staging is kept out of every write the proof lands.
    `lost` -- with `heads_read` and a loss still owed (`owed_events.loss_owed`)
    -- names a checkout read gone or off the evidence's head, or the replay's
    where the tick holds none, retired over it: recorded by the attempt's debt
    first, whatever the tick holds, and asked of the comment read afresh, so
    evidence absent from the tick's reading and put back meanwhile or later is
    retired too.
    """
    recorded = (_landing_records.captured(context.state), _landing_records.settled(context.state))
    landed = {record.binding.target.target_head for record in recorded if record}
    landed = landed or {context.pending_rewrite.sha}
    lost = [read for read in (*lost, *context.heads_read) if read not in landed]
    lost += [context.worktree] if loss_owed(context) else []
    with keeps_the_staging(replace(context, records_before_a_reset=records_the_reset), ahead=moved is None) as proving:
        if proving.worktree.is_dir() and not lost:
            read = dict(moved or {})
            adds_the_totals(proving, read)
            return _retirement.retires_unproved(proving, read)
        return records_the_reset(proving, lost=lost or (proving.worktree,))


def records_the_reset(context: _AutoRebaseRecoveryContext, *, lost=()) -> bool:
    """Record a reset about to move the checkout against evidence for the landed head; may the reset go on.

    The recovery's answer ahead of every reset (`_AutoRebaseRecoveryContext.records_before_a_reset`):
    where the attempt still records the base tip its replay was made onto,
    that tip is blanked through the guarded commit and laid over the tick's
    state -- whatever evidence the tick read, since the write is decided on
    every evidence record and the attempt as the tick read them
    (`rewrite_finish_writes.INVALIDATION`): a transaction a finish captured or
    evidence it settled, or one another road recorded or settled since that
    reading, so evidence the tick never saw refuses the reset rather than
    being left for a checkout put back to revive, and evidence settled behind
    the blank reads it as movement. A tip the tick read blank is held to the
    fresh comment too: one another road put back refuses the record and the
    reset; still blank, nothing is sent. True where the blank stood or
    landed; False, logged, where it was refused or went unconfirmed, for the
    git owner to hold with nothing reset or cleaned -- the tick's state
    withheld by the commit (`ReportCommit.withholds`), so its stale tip is
    never written back over a blank that landed unconfirmed. False and
    withheld too where the comment read afresh behind a landed blank carries
    its tip put back or another attempt, or would not read, so no reset moves
    the checkout off evidence nothing records moved, or under another attempt;
    and where the tick's state already carries another attempt -- one a proof
    took in off the comment -- with no blank written, so a replacement's tip
    is never blanked under a recovery of the attempt it replaced.
    Movement the record's commit read (`rewrite_landing_retirement.moved_under`)
    is proved as read first, so what moved is retired before the reset goes on,
    False where that does not land -- and the comment is read afresh once more
    behind that proof, so a tip put back or another attempt pinned while it made
    its own requests holds the reset as well, the tick's state withheld; evidence
    that reading carries under a receipt movement was read under -- a successor
    settled, or the run put back, right behind the proof -- is proved again, the
    comment read again behind each such proof until a reading carries none. What
    the tick staged is kept across these writes as a proof keeps it
    (`rewrite_recovery_staging.keeps_the_staging`), its usage landing first, in
    a write of its own whose readings the record proves, where no proof keeps
    it already.
    Over a checkout gone from disk, or one
    `lost` names however soon it is back, the loss is owed by the attempt the
    moment it is read, ahead of every write (`owed_events.owes_a_loss`), so a
    checkout back by the time those writes are refused still leaves evidence
    put back later retired over it; and the evidence is retired as over a
    reset in its own `CLEAR` write (`rewrite_recovery_staging.lands_the_retirement`),
    blank landed or not. True only where both landed and nothing it retired,
    no successor or other attempt, is read back; where either does not land,
    the tick's state is withheld from every whole-state write behind, since
    the comment may carry a successor and its floor, or a tip put back, by then.
    """
    with keeps_the_staging(context) as recording:
        moved: dict[str, ReportEvidence] = {}
        gone = bool(lost) or not recording.worktree.is_dir()
        if gone:
            owes_a_loss(recording)
            moved.update(dict.fromkeys(_retirement.receipts(recording.state), LEFT_THE_CHECKOUT))
        adds_the_totals(recording, moved)
        recorded = _blanks_the_tip(recording, moved)
        if gone or not recording.worktree.is_dir():
            owes_a_loss(recording)
            log.warning(
                "issue=#%d the checkout is gone from disk; retiring what a finish captured or settled for the landed "
                "head as over a reset, in a write of its own", recording.issue.number,
            )
            if not (lands_the_retirement(recording, CLEAR) and recorded):
                recording.state.withheld = True
                return False
            return True
        pending = moved.keys()
        while pending:
            recorded = _retirement.retires_unproved(
                replace(recording, records_before_a_reset=records_the_reset), _retirement.reconciles(recording, moved),
            ) and recorded and _blanks_the_tip(recording, moved, again=True)
            pending = recorded and _retirement.receipts(recorded) & moved.keys()
        return bool(recorded)


def _blanks_the_tip(
    context: _AutoRebaseRecoveryContext, moved: dict[str, ReportEvidence], *, again: bool = False,
) -> PinnedState | None:
    """Blank the attempt's base tip in a guarded write of its own; the comment read afresh behind it, or None to hold.

    What each reading it takes moves is kept in `moved`. The reading answered is the one the reset stands recorded
    on, for a caller to ask what still stands there.

    Whether it landed, logged either way; refused or unconfirmed, the commit withholds the tick's state. A tick whose
    state carries another attempt in place of the one `context` recovers writes nothing and holds, its state withheld,
    since the write is decided on the attempt as the tick holds it and would blank that attempt's tip. A blank that
    landed is followed by the comment read afresh, so a tip another road put back right behind it, an attempt it
    pinned there, or a comment that would not read holds the reset too -- no reset moving the checkout off evidence
    nothing records moved -- the tick's state withheld rather than written back over what that road wrote. `again`
    writes nothing and asks only that reading, for a caller whose proof made requests of its own since the blank.
    """
    asked = asks_every_reading(
        context, lambda reading: _retirement.moved_under(reading, tick=context.state, into=moved),
    )
    if not again:
        if not stands_as_recovered(context):
            log.warning(
                "issue=#%d the tick's state carries another auto-rebase attempt in place of the one its recovery "
                "recovers; nothing is recorded or reset, for the next tick to recover the attempt the comment carries",
                context.issue.number,
            )
            context.state.withheld = True
            return None
        commit = _commits.ReportCommit(asked.gh, context.issue, context.state)
        staged = commit.staging()
        staged.set(_TIP, None)
        landed = commit.lands(staged, _writes.INVALIDATION)
        if landed.status is not _commit_models.CommitStatus.COMMITTED:
            log.warning(
                "issue=#%d the reset could not be recorded ahead of it over the evidence records the tick read (%s); "
                "nothing is reset until a later tick records it",
                context.issue.number, (landed.refusal or landed.status).value,
            )
            return None
    durable = durable_comment(asked.gh, context.issue, context.state)[0]
    if durable is not None and not durable.get(_TIP) and stands_as_recovered(context, durable):
        log.info("issue=#%d the reset stands recorded ahead of it, the attempt's base tip blank", context.issue.number)
        return durable
    log.warning(
        "issue=#%d the reset was recorded, but the comment read afresh behind it carries its base tip back or no "
        "attempt this recovery recovers; nothing is reset until a later tick answers the comment as it then stands",
        context.issue.number,
    )
    context.state.withheld = True
    return None


def _lands_then_proves(context: _AutoRebaseRecoveryContext, write: _commits.ReportWrite, named: str) -> bool:
    """Land the tick's state as `write` over the comment read afresh, then prove once more what it keeps; both did.

    Whether the record landed or not, the proof behind it
    (`proves_before_a_park`) is handed the move the record carried or its refusal
    read (`rewrite_landing_retirement.moved_under`, against the binding of each
    evidence the tick held), each under the receipt it was read under, which the proof
    asks of the evidence standing behind it by that evidence's own receipt. A
    record that did not land has the evidence the comment carries now laid
    over the tick's state first (`rewrite_landing_retirement.reconciles`), so a
    successor another road recorded or settled meanwhile -- one the record
    took in, or one its refusal or lost answer left out of the tick's state --
    is proved on its own binding, and invalidated over movement read under it
    however soon that is put back; the move the refusal read is handed that
    reconciliation too, so evidence it read moving that the comment no longer
    carries by then is kept for the proof rather than laid away. Every
    comment the commit itself reads, the reread behind a refusal for room
    among them, is asked as it is read (`rewrite_recovery_readings.AsksEveryReading`).
    `named` is the record, logged where it did not land.
    """
    state = context.state
    held = (_landing_records.captured(state), _landing_records.settled(state))
    attempt = _retirement.attempt_as_read(state)
    moved: dict[str, ReportEvidence] = {}
    landed = _commits.ReportCommit(
        AsksEveryReading(
            context.gh,
            context.issue.number,
            lambda reading: _retirement.moved_under(reading, attempt, held, into=moved),
        ),
        context.issue,
        state,
    ).lands(state, write)
    if landed.reading is not None:
        _retirement.moved_under(landed.reading, attempt, held, into=moved)
    if landed.status is not _commit_models.CommitStatus.COMMITTED:
        log.warning(
            "issue=#%d the %s of its auto-rebase recovery did not land (%s); nothing is recorded, "
            "and the next tick's recovery answers the comment as it then stands",
            context.issue.number, named, (landed.refusal or landed.status).value,
        )
        moved = _retirement.reconciles(context, moved)
    return proves_before_a_park(context, moved) and landed.status is _commit_models.CommitStatus.COMMITTED
