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
`proves_before_a_park`), handed in on every context the workflow builds: each
recovery road's (`rewrite_recovery.recovers`: a reset's tail, both replay
parks, a label the refresh does not drive), the uncounted lag's abort
(`rewrite_recovery.answers_an_unreadable_checkout`), the eligibility gate's
park of an ineligible label (`base_rewrite`), and the dispatcher's stranded
park of a held anchor (`answers_a_held_anchor`), whose quiet holds ask it too.
A publication gate's holds of the landed road's leased no-op or the retry's
reissued push land here (`lands_a_hold`): their proof taken first, as before a
park that keeps the attempt, what the tick staged before that proof kept
across every write it lands (`rewrite_recovery_staging`), and only what the
tick staged since its reading landed, as `HOLD`, over the comment read
afresh, like the ordinary gate hold (`rewrite_publication`). A park made again
over a record that never landed takes in the notice the conversation already
carries rather than saying it twice (`rewrite_recovery_notices`).
A clear of the attempt -- under a label the refresh does not drive, or of one
whose checkout never left the anchor -- is recorded as `CLEAR` over the
comment read afresh (`lands_a_clear`), so a successor another road settled
while the checkout was read refuses it, its revision floor kept.

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
a blank that landed with its answer lost is never put back. A reset git
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
ahead of a park or hold and behind one (`proves_before_a_park`): a quiet hold,
a standing park, or a refused record carries no staged retirement. With no
proof behind a quiet hold, the comment is read afresh behind the retirement:
evidence another road wrote back is retired once more, the tick held, as over
a successor or another attempt put in its place first, nothing reset. One gone
mid-proof is recorded and retired alike, every proof here given the reset's
recorder whatever the git owner's context -- the eligibility gate's has none.
"""
from __future__ import annotations

import json
import logging
from dataclasses import replace
from functools import partial

from orchestrator.git.base_sync import (
    attempts as _attempts,
    recovery_holds as _recovery_holds,
    state as _base_sync_state,
)
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
from orchestrator.workflow.engine.report_evidence_models import ReportEvidence
from orchestrator.workflow.engine.rewrite_recovery_readings import (
    LEFT_THE_CHECKOUT,
    AsksEveryReading,
    RecordsALostCheckout,
    asks_every_reading,
)
from orchestrator.workflow.engine.rewrite_recovery_staging import keeps_the_staging, lands_the_retirement

log = logging.getLogger("orchestrator.workflow")

_PARK_FLAGS = frozenset((_base_sync_state._AWAITING_HUMAN, _base_sync_state._PARK_REASON))

# What a recovery hold records: whatever the tick staged since its reading --
# a publication gate's own record of the no-op it held -- decided on the
# attempt it keeps, so every evidence record stays as the comment carries it.
# Its strict edit keeps the comment a refusal read (`reads_a_move`), which the
# proof behind it reads for movement.
HOLD = _commits.ReportWrite(
    owned=frozenset(), decided_on=frozenset(_attempts._ATTEMPT_KEYS),
).reading_moves(True)

# A clear's record under a label the refresh does not drive, decided on the
# attempt and the evidence records, so a successor settled meanwhile refuses it
# -- the write a retirement over a checkout gone from disk lands as too.
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

    Only what the tick staged lands; a successor settled while the checkout was
    read refuses it, its revision floor kept, the tick's state withheld for the
    next tick to answer. The checkout read off the landed head is movement all
    the same, so a clear not landing records the reset against the attempt as
    read (`records_the_reset`) and proves what the fresh comment carries with
    that move under each receipt held (`proves_before_a_park`): another finish's
    settlement of the run meanwhile invalidated whole, a successor under another
    receipt proved on its own. A state nothing was read into is written whole.
    """
    if context.state.synced is None:
        context.gh.write_pinned_state(context.issue, context.state)
        return True
    moved: dict[str, ReportEvidence] = {}
    commit = _commits.ReportCommit(
        asks_every_reading(context, partial(_retirement.moved_under, tick=context.state, into=moved)).gh,
        context.issue,
        context.state,
    )
    landed = commit.lands(context.state, CLEAR)
    if landed.status is _commit_models.CommitStatus.COMMITTED:
        return True
    log.warning(
        "issue=#%d the clear of its auto-rebase attempt did not land (%s); nothing is cleared, and the next "
        "tick answers the comment as it then stands",
        context.issue.number, (landed.refusal or landed.status).value,
    )
    read = PinnedState(
        comment_id=context.state.comment_id, state_data=json.loads(context.state.synced),
    )
    read.synced = context.state.synced
    moved.update(dict.fromkeys(_retirement.receipts(read), LEFT_THE_CHECKOUT))
    moving = replace(context, state=read)
    records_the_reset(moving)
    proves_before_a_park(moving, _retirement.reconciles(moving, moved))
    return False


def answers_a_held_anchor(held: _AutoRebaseRecoveryContext) -> bool:
    """Whether the dispatcher's hold of `held`'s anchor stops this tick, answered with the workflow's proof and park.

    The hold is the git owner's question (`git/base_sync/recovery_holds._recovery_holds_dispatch`),
    and its answer (`_answers_a_held_anchor`) restores a checkout, clears the
    attempt, or parks it stranded. That park and a hold keeping the attempt
    with nothing posted, on every poll that holds, ask the proof first
    (`proves_before_a_park`), the park recorded as every recovery park is
    (`lands_a_park`); a clear retires the evidence first and lands guarded
    (`lands_a_clear`). A checkout the question or the answer finds gone from
    disk has that loss recorded (`RecordsALostCheckout`), the handler held,
    and one either reads gone is that loss to the proof however soon it returns.
    """
    settles = partial(_retirement.retires_over_the_reset, held)
    owing = replace(held, settles_over_a_reset=settles, lands_a_clear=lands_a_clear)
    holds = True
    gone: list = []
    with RecordsALostCheckout(replace(held, records_before_a_reset=records_the_reset)):
        holds = _recovery_holds._recovery_holds_dispatch(
            held.issue, held.label or None, held.state, held.worktree, gone,
        )
        if holds:
            proves = partial(proves_before_a_park, lost=gone)
            _recovery_holds._answers_a_held_anchor(owing, proves, lands_a_park, gone)
    return holds


def proves_before_a_park(
    context: _AutoRebaseRecoveryContext, moved: dict[str, ReportEvidence] | None = None, *, lost=(),
) -> bool:
    """Whether a recovery park or hold that keeps the attempt may go on, what it keeps proved first.

    The proof is the recovery's (`rewrite_landing_retirement.retires_unproved`),
    over a transaction a finish captured and evidence one settled alike. A
    checkout gone from disk has no reading to prove the landing over, so the
    reset is recorded against the evidence and the evidence retired as over
    it, each in its own write (`records_the_reset`), so a park write refused,
    unconfirmed, cut short by a lost process, or never made -- a quiet hold's,
    or one a standing park skips -- leaves it retired however the checkout and
    base tip are put back. One not landing holds the tick with nothing parked.

    Behind a park's or hold's record, or a notice that raised, it is asked
    once more, `moved` the movement already read there -- handed only then --
    which a checkout on disk hands the proof as read. A checkout gone from
    disk by then, under the record's write or the notice's post among it,
    has the reset recorded and the evidence retired the same way.

    Asked ahead of a record, the proof keeps what the tick staged before it
    -- a gate's record of a hold, or a tip staged back behind a reset git
    refused -- across every write it lands, for the record behind, save what
    a proof write already carried (`rewrite_recovery_staging.keeps_the_staging`).
    Behind a record its staging is kept out of every write the proof lands.
    `lost`, where not empty, is a checkout the caller read gone from disk, the
    reset recorded and the evidence retired over it however soon it returned.
    """
    with keeps_the_staging(replace(context, records_before_a_reset=records_the_reset), ahead=moved is None) as proving:
        if proving.worktree.is_dir() and not lost:
            return _retirement.retires_unproved(proving, moved)
        return records_the_reset(proving, lost=lost)


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
    never written back over a blank that landed unconfirmed.
    Movement the record's commit read (`rewrite_landing_retirement.moved_under`)
    -- landed, refused, or sent with its answer lost -- is proved as read first,
    so a report moved or a tip blanked and put back under it revives nothing:
    behind a landed blank what moved is retired before the reset goes on, as a
    reset git then refuses stages the tip back, and a retirement not landing
    answers False, the blank recording that movement. Over a checkout gone from
    disk, nothing to prove it over, the evidence is retired as over a reset
    (`rewrite_recovery_staging.lands_the_retirement`) in its own `CLEAR` write,
    blank landed or not, even over a tip another road put back behind it; True
    there only where both landed and the comment reread behind carries back
    none of what it retired, nor a successor or another attempt in its place --
    over one `lost` names, its caller having read it gone, however soon it is
    back. One gone as the record is asked is movement under every evidence held.
    """
    moved: dict[str, ReportEvidence] = {}
    if not context.worktree.is_dir():
        moved.update(dict.fromkeys(_retirement.receipts(context.state), LEFT_THE_CHECKOUT))
    commit = _commits.ReportCommit(
        asks_every_reading(context, partial(_retirement.moved_under, tick=context.state, into=moved)).gh,
        context.issue,
        context.state,
    )
    staged = commit.staging()
    staged.set(_base_sync_state._PENDING_REWRITE_BASE, None)
    landed = commit.lands(staged, _writes.INVALIDATION)
    recorded = landed.status is _commit_models.CommitStatus.COMMITTED
    if recorded:
        log.info("issue=#%d recorded the reset ahead of it by blanking the attempt's base tip", context.issue.number)
    else:
        log.warning(
            "issue=#%d the reset could not be recorded ahead of it over the evidence records the tick read (%s); "
            "nothing is reset until a later tick records it",
            context.issue.number, (landed.refusal or landed.status).value,
        )
    if lost or not context.worktree.is_dir():
        log.warning(
            "issue=#%d the checkout is gone from disk; retiring what a finish captured or settled for the landed "
            "head as over a reset, in a write of its own", context.issue.number,
        )
        return lands_the_retirement(context, CLEAR) and recorded
    if moved:
        recorded = _retirement.retires_unproved(
            replace(context, records_before_a_reset=records_the_reset), _retirement.reconciles(context, moved),
        ) and recorded
    return recorded


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
