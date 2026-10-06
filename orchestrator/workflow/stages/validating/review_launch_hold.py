# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a handed change request's developer launch is held to at the run circuit, the launch boundary.

The change-request handoff (`review_handoffs`) holds the launch it owes to
what stands before the relabel announcing it, where one is made, and once more
right before it hands the launch to the run circuit, but the circuit charges
and starts the launch requests after that last reading -- long enough for
another road to push, settle a later report, repoint the issue, drop or
replace the verdict, clear or repoint the feedback anchor, supersede the
evidence the request claims, or park the issue awaiting a human -- or start a
launch of this very identity without the owed count, which nothing tells from
this one. A developer launched over any of those answers a review of work the
pull request no longer carries, is one no failed run could replay the feedback
to, runs under a park nobody has answered, or is a second one. So the
launch goes to the circuit owed once (`run_charge_state.OwedLaunch`) behind
this hold, which the circuit asks where it writes: the whole subject resolved
again right behind the charge, and every reading the charge and its start are
written from judged against the comment the handoff last held the launch over
-- that very comment, not one pinned in its place since. Each reading it
accepts is laid over the state the developer's run is written back from, so
that run's writes keep whatever else another road wrote there. Nothing here
writes: a refusal launches nobody and leaves the verdict handed, for the next
entry to drop, retire, or hold over whatever moved.
"""
from __future__ import annotations

import logging
from collections.abc import Callable

from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import report_record_values as _record_values, run_ledger_values as _run_ledger_values
from orchestrator.workflow.engine.run_charge_state import OwedLaunch
from orchestrator.workflow.stages.validating import (
    models as _models,
    review_claims as _claims,
    review_comment as _review_comment,
    review_coverage as _review_coverage,
    review_verdicts as _verdicts,
)

log = logging.getLogger("orchestrator.workflow")

# What every reading the launch is charged and started from has to spell as the
# last one the hold took in did: the report records, the pull request the issue
# points at, and the park's flags -- a park another road recorded is a human's
# to answer, and a developer launched under it answers nobody's ask.
_HELD_RECORDS = (*_review_comment._BOUND_RECORDS, *_review_comment._PARK)


def owed_launch(
    context: _models._RequestedChanges,
    handed: _verdicts.ReturnedVerdict,
    rules_out_a_start: Callable[[PinnedState], bool],
) -> OwedLaunch:
    """The developer launch `handed` owes once, held to the comment as `context.state` carries it now.

    For a caller that has just held the launch to what stands, over the
    comment read again, and has carried that reading onto `context.state`:
    the first reading the circuit takes is measured against it, before the
    caller stages anything of its own over it. `rules_out_a_start` is the
    handoff's own reading of the run ledger (`review_handoffs.HandedLaunch.
    owed`), asked of every reading the circuit charges or starts from.
    """
    hold = _LaunchHold(context, handed, rules_out_a_start)
    return OwedLaunch(at=handed.handed, resolves=hold.resolves, stands=hold.stands)


class _LaunchHold:
    """What one handed change request's developer launch is held to, across the readings the circuit takes.

    Each reading it accepts is laid over the state the launch is made from,
    and remembered there as the comment's (`review_comment._Reread.lays_over`):
    the circuit carries onto that state only the fields its own writes
    changed. The guarded commits behind the developer's run -- the record of
    its report, its park, the hand-back, each retiring the request -- keep
    whatever another road wrote that the tick did not stage, but the size
    gate's own writes around a push still write that state whole, so anything
    else another road wrote there -- a run allowance granted, a usage total
    folded -- would be put back by them to the comment the handoff read. Every
    reading is measured against the last one this hold took in, since a move
    carried once and measured again from the older comment would be kept twice
    where it adds up.
    """

    def __init__(
        self,
        context: _models._RequestedChanges,
        handed: _verdicts.ReturnedVerdict,
        rules_out_a_start: Callable[[PinnedState], bool],
    ) -> None:
        self._context = context
        self._handed = handed
        self._rules_out_a_start = rules_out_a_start
        self._measured = dict(context.state.data)

    def resolves(self) -> bool:
        """Whether the whole subject the request was reviewed on resolves as it was recorded, right behind the charge.

        The head, the requirements, and the report at its location are nowhere
        on the pinned comment, so the circuit's reading of it cannot see a
        push, an edit of the issue, or a human editing the report in place:
        they are resolved again here, and the circuit reads the comment behind
        them. A subject nobody could read is no proof it stands either, and
        the launch waits for the next entry to ask again.
        """
        context = self._context
        resolved = _review_coverage._subject_still_stands(
            context.gh, context.issue, context.state, self._handed.subject,
        )
        if resolved is not True:
            log.warning(
                "issue=#%d the subject its reviewer's change request stands on "
                "did not resolve as recorded behind its developer's charge; "
                "launching nobody", context.issue.number,
            )
        return resolved is True

    def stands(self, reading: PinnedState) -> bool:
        """Whether the launch still stands on `reading`, a comment the circuit is about to write from, which it keeps.

        The reading is of the very comment the launch's state names: one
        pinned in its place since is where every later reader looks, and the
        writes behind the developer's run, made through the id that state
        holds, would land on a comment nobody reads. The verdict is still the
        one handed, not dropped or replaced by another road; the feedback
        anchor, read as the fixing stage's replay reads it, still names the
        post the verdict records; the report records, the pull request the
        issue points at, and the park's flags are where the last reading had
        them (`_HELD_RECORDS`) -- a park recorded meanwhile is another road's,
        for a human to answer; and the evidence
        the request claims is still the settled evidence, not superseded. Its
        run ledger rules out a start of this launch too -- one of its very
        identity STARTED with no owed count, or one whose record no reader
        takes, included -- save where the state in hand already records this
        launch's own start: the circuit merges every charge it takes back onto
        that state, so a continuation of the launch, a poisoned session's fresh
        retry or a recovery prompt, is its own. A reading that stands is laid
        over the launch's state, and is what the next one is measured against.
        """
        handed = self._handed
        own = _run_ledger_values._owed_started(self._context.state) == handed.handed
        anchor = _record_values.as_recorded_number(reading.get(_verdicts._FEEDBACK_ANCHOR))
        stands = reading.comment_id == self._context.state.comment_id
        stands = stands and (own or self._rules_out_a_start(reading))
        stands = stands and handed.anchor is not None and anchor == handed.anchor
        stands = stands and _verdicts.read_returned_verdict(reading) == handed
        if stands and handed.evidence is not None:
            stands = _claims.claim_standing(reading, handed.evidence) is _claims.ClaimStanding.SETTLED
        if stands and not _review_comment._moved(reading.data, self._measured, _HELD_RECORDS):
            accepted = _review_comment._Reread(stood=True, read=dict(reading.data))
            accepted.lays_over(self._context.state, self._measured)
            self._measured = accepted.read
            return True
        log.warning(
            "issue=#%d what its reviewer's change request stands on moved on "
            "the pinned comment, or another comment was pinned in its place, by "
            "the time its developer was charged; launching nobody",
            self._context.issue.number,
        )
        return False
