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
`proves_before_a_park`), and the workflow hands them in on every recovery
context it builds: each recovery road's (`rewrite_recovery.recovers`) -- a
reset's tail, both replay parks, and a label the refresh does not drive among
them --, the abort over a checkout whose lag could not be counted
(`rewrite_recovery.answers_an_unreadable_checkout`), the eligibility gate's
park of an ineligible label (`base_rewrite`), and the dispatcher's stranded
park of an anchor it holds a handler back for (`answers_a_held_anchor`),
whose holds that post nothing ask the same proof. The holds behind a
publication gate that held the landed road's leased no-op or the retry's
reissued push are recorded here too (`lands_a_hold`): their proof taken
first, and only what the tick staged since its reading landed, as `HOLD`,
over the comment read afresh -- the write the ordinary publication's gate
hold lands as too (`rewrite_publication`). A park made again over a record
that never landed takes in the notice the conversation already carries
rather than saying it twice (`rewrite_recovery_notices`).

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
settled behind it reads it as movement. A blank refused or never confirmed
holds the tick with nothing reset or cleaned, and the tick's state, which
still carries the tip, is withheld from every whole-state write behind it, so
a blank that landed with its answer lost is never put back. A reset git
refused moved nothing, and the git owner
stages the tip back for the park that keeps the attempt, so the evidence
stands for that park's proof as it did before.

A park that keeps the attempt keeps the evidence with it for the reply that
brings the recovery back, and that evidence is proved before the park
(`proves_before_a_park`) -- but its notice is a request after that proof, long
enough for another road to settle a later report, which the park's record then
keeps as the fresh comment carries it. So the evidence is proved once more
behind the notice (`lands_a_park`) -- landed, refused, or raised -- and a
report moved meanwhile is movement read under it, invalidated or recorded
against it before the tick ends; one the park's own commit carried, landed or
sent with its answer lost -- or one its strict edit found moved under it and
was refused over, a base tip blanked there beside the rest of the attempt as
the tick read it among them (`rewrite_landing_retirement.moved_under`) -- is
handed to that proof as read (`_moved`), so putting the earlier report or the
tip back before the reply revives nothing. Behind a record
refused or sent with its answer lost, the evidence the comment carries now is
laid over the tick's state first (`rewrite_landing_retirement.reconciles`),
so a successor another road settled while the notice was posted is proved on
its own binding rather than left unread behind the tick's older reading. A checkout
gone from disk has nothing to prove the landing over, so its evidence is
retired on the state the park writes -- and the reset recorded against it
first, in a write of its own, so a park write that fails or never lands
leaves no evidence a checkout put back would take up as current.
"""
from __future__ import annotations

import logging

from orchestrator.git.base_sync import (
    attempt_records as _attempt_records,
    attempts as _attempts,
    recovery_holds as _recovery_holds,
    state as _base_sync_state,
)
from orchestrator.git.base_sync.models import _AutoRebaseRecoveryContext
from orchestrator.workflow.engine import (
    pinned_commit_models as _commit_models,
    prompt_delivery as _prompt_delivery,
    report_commits as _commits,
    rewrite_finish_writes as _writes,
    rewrite_landing_retirement as _retirement,
    rewrite_recovery_notices as _notices,
    verification_records as _evidence_records,
)
from orchestrator.workflow.engine.report_evidence_models import ReportEvidence, ReportEvidenceVerdict

log = logging.getLogger("orchestrator.workflow")

_PARK_FLAGS = frozenset((_base_sync_state._AWAITING_HUMAN, _base_sync_state._PARK_REASON))

# What a park's record read where the record it landed or sent, or the comment
# its refused edit read, carried one the evidence's binding rests on that
# another road moved while its notice was posted.
_MOVED_UNDER_THE_NOTICE = ReportEvidence(
    ReportEvidenceVerdict.DEFER, "a record the evidence's binding rests on moved while a park's notice was posted",
)

# What a recovery hold records: whatever the tick staged since its reading --
# a publication gate's own record of the no-op it held -- decided on the
# attempt it keeps, so every evidence record stays as the comment carries it.
# Its strict edit keeps the comment a refusal read (`reads_a_move`), which the
# proof behind it reads for movement (`_moved`).
HOLD = _commits.ReportWrite(
    owned=frozenset(), decided_on=frozenset(_attempts._ATTEMPT_KEYS),
).reading_moves(True)

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
    a record the evidence's binding rests on
    (`rewrite_finish_writes.BINDING_RECORDS`) spelled otherwise than the tick
    read it, in the record that landed, in the one sent with its answer lost,
    which is never laid over the tick's state, or in the comment its strict
    edit found moved under it and was refused over -- that is movement read,
    handed to the proof as its answer, so a record put back between the
    park's commit and the proof revives nothing. A notice whose post raised --
    refused, or posted with its answer lost -- records nothing, and the proof
    is taken before the error goes on, over the evidence the comment carries
    by then (`rewrite_landing_retirement.reconciles`), so a report moved while
    it was posted is read moving all the same -- under a successor another
    road settled meanwhile too, proved on its own binding.
    """
    state = context.state
    try:
        _notices.parks_awaiting_human(context, message, reason)
    except Exception:
        if context.worktree.is_dir():
            _retirement.reconciles(context)
            _retirement.retires_unproved(context)
        raise
    state.set(_base_sync_state._PARK_REASON, reason)
    if state.synced is None:
        context.gh.write_pinned_state(context.issue, state)
        return
    _lands_then_proves(context, PARK, "park")


def lands_a_hold(context: _AutoRebaseRecoveryContext) -> None:
    """Prove what a recovery hold keeps, then record the hold over the comment read afresh, as `HOLD`.

    A publication gate that held the landed road's leased no-op
    (`rewrite_landed`) or the retry's reissued push (`rewrite_retry`) keeps
    the attempt, so its evidence is proved first
    (`rewrite_landing_retirement.retires_unproved`). The gate's answer is long
    enough for another road to record a newer transaction, so only what the
    tick staged since its reading lands, every other field kept as the fresh
    comment carries it, and a record refused or never confirmed withholds the
    tick's state. Behind the record the evidence is proved once more, over the
    move the record itself carried, as behind every park (`lands_a_park`). A
    state nothing was read into is written whole.
    """
    _retirement.retires_unproved(context)
    if context.state.synced is None:
        context.gh.write_pinned_state(context.issue, context.state)
        return
    _lands_then_proves(context, HOLD, "hold")


def answers_a_held_anchor(held: _AutoRebaseRecoveryContext) -> None:
    """Answer an anchor the dispatcher holds a handler back for, handed the workflow's proof and park.

    The git owner's answer (`git/base_sync/recovery_holds._answers_a_held_anchor`)
    restores a checkout, clears the attempt, or parks it stranded; that park
    keeps the attempt, so it asks the proof first (`proves_before_a_park`) and
    is recorded as every recovery park is (`lands_a_park`).
    """
    _recovery_holds._answers_a_held_anchor(held, proves_before_a_park, lands_a_park)


def proves_before_a_park(context: _AutoRebaseRecoveryContext) -> bool:
    """Whether a recovery park that keeps the attempt may go on, what it keeps proved first; the answer every road gets.

    The proof is the recovery's (`rewrite_landing_retirement.retires_unproved`),
    over a transaction a finish captured and evidence one settled alike. A
    checkout gone from disk has no reading to prove the landing over, so the
    evidence is retired on the state the park writes -- and recorded against
    first (`records_the_reset`), in a write of its own, so that a park write
    refused, never confirmed, or cut short by a lost process leaves every later
    proof reading the evidence moved however the checkout is put back. A
    record that does not land holds the tick with nothing parked.
    """
    if not context.worktree.is_dir() and not records_the_reset(context):
        return False
    return _retirement.retires_unproved(context)


def records_the_reset(context: _AutoRebaseRecoveryContext) -> bool:
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
    the blank reads it as movement. An attempt with no tip proves no base for
    any evidence already. True where nothing needed recording or the blank
    landed; False, logged, where it was refused or went unconfirmed, for the
    git owner to hold with nothing reset or cleaned -- the tick's state
    withheld by the commit (`ReportCommit.withholds`), so its stale tip is
    never written back over a blank that landed unconfirmed.
    """
    if not _attempt_records._recorded_onto(context.state):
        return True
    commit = _commits.ReportCommit(context.gh, context.issue, context.state)
    staged = commit.staging()
    staged.set(_base_sync_state._PENDING_REWRITE_BASE, None)
    landed = commit.lands(staged, _writes.INVALIDATION)
    if landed.status is _commit_models.CommitStatus.COMMITTED:
        log.info("issue=#%d recorded the reset ahead of it by blanking the attempt's base tip", context.issue.number)
        return True
    log.warning(
        "issue=#%d the reset could not be recorded ahead of it over the evidence records the tick read (%s); "
        "nothing is reset until a later tick records it",
        context.issue.number, (landed.refusal or landed.status).value,
    )
    return False


def _lands_then_proves(context: _AutoRebaseRecoveryContext, write: _commits.ReportWrite, named: str) -> None:
    """Land the tick's state as `write` over the comment read afresh, then prove once more what it keeps.

    Whether the record landed or not, the proof behind it -- taken only over a
    checkout on disk -- is handed the move the record carried or its strict
    edit was refused over (`_moved`), under whichever evidence still stands
    behind it (`rewrite_landing_retirement.receipts`). A record that did not
    land has the evidence the comment carries now laid over the tick's state
    first (`rewrite_landing_retirement.reconciles`), so a successor another
    road recorded or settled meanwhile -- one the record took in, or one its
    refusal or lost answer left out of the tick's state -- is proved on its
    own binding, and invalidated over movement read under it however soon that
    is put back. `named` is the record, logged where it did not land.
    """
    state = context.state
    read = {key: _commit_models.spelled(state.data, key) for key in _writes.BINDING_RECORDS}
    held = _retirement.receipts(state)
    attempt = _retirement.attempt_as_read(state)
    landed = _commits.ReportCommit(context.gh, context.issue, state).lands(state, write)
    if landed.status is not _commit_models.CommitStatus.COMMITTED:
        log.warning(
            "issue=#%d the %s of its auto-rebase recovery did not land (%s); nothing is recorded, "
            "and the next tick's recovery answers the comment as it then stands",
            context.issue.number, named, (landed.refusal or landed.status).value,
        )
        _retirement.reconciles(context)
    if context.worktree.is_dir():
        _retirement.retires_unproved(context, _moved(context, landed, read, held, attempt))


def _moved(
    context: _AutoRebaseRecoveryContext,
    landed: _commit_models.CommitOutcome,
    read: dict,
    held: frozenset[str],
    attempt: _commit_models.PinnedCommit | None,
) -> ReportEvidence | None:
    """The movement a record's commit, `landed`, read under the evidence `context.state` carries behind it; or None.

    What it read is the record the commit made of the comment -- landed, or
    sent with no answer -- or, where it was refused, the comment its refusal
    was read over: the one its strict edit found moved under it, a report
    another road settled right at that edit among what it carries
    (`pinned_commit_models.CommitOutcome.seen`); nothing where the refusal
    read no comment. `read` is the binding records as the tick read them, and
    `held` the receipts the tick's state carried before the record. A binding
    record `reading` spells otherwise than `read` is movement under the
    evidence the tick held (`_MOVED_UNDER_THE_NOTICE`); a review or report
    record it spells off the binding of any evidence it records for the head
    is movement under that evidence (`rewrite_landing_retirement.moved_under`)
    -- a successor another road settled among it -- and so is the base tip of
    `attempt`, the attempt the tick read, read blank or repointed beside every
    other member of it: a blank another road recorded right at the record's
    strict edit and put back behind it. Only movement under
    evidence still standing is handed to the proof, as read, even where what
    carried it is put back before the proof reads the comment again; a
    successor nothing was read moving under is proved on its own readings.
    """
    reading = landed.reading or landed.seen
    moves = _retirement.moved_under(reading, attempt)
    if reading is not None:
        carried = {key: _commit_models.spelled(reading.data, key) for key in read}
        if carried != read:
            moves = {**dict.fromkeys(held, _MOVED_UNDER_THE_NOTICE), **moves}
    standing = sorted(_retirement.receipts(context.state))
    under = [moves[receipt] for receipt in standing if receipt in moves]
    return under[0] if under else None
