# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Finish a captured late developer revision the dispatcher's recovery admitted, with no developer run.

The developer a human's guidance buys under a late adjudication is captured as
it returns on a READY or VERIFIED report (`late_revision_road`), and a live
hold, a capture never confirmed, or a lost tick keeps that return from its
reconciliation. Every later `decomposing` tick would otherwise read the same
guidance as fresh and resume the developer over it again, or re-read the
checkout on a bare continue and re-measure it with the report lost. The
recovery hands an applicable capture on that road here
(`completion_recovery.ROUTE_OWNERS`), ahead of the late coordinator, so it is
finished instead, and before anything could launch another revision or an
adjudicator.

What the admission held it to is what the revision was launched over: the
adjudication still live (`completion_prerequisites`), the cycle, the
generation, the frozen pair, the phase, the late comment watermark and the
replies owed a whole quote -- what selected the guidance its prompt quoted, so
a reply an operator made owed since is one the run was never handed -- the
route bookkeeping a hold on the pair owes, so a handoff recorded since is one
the run did not answer, the publication group, the pull request, and the
code-publication receipt still
spelled as the launch read them, the requirements still the ones the run was
handed -- so guidance written since is an edit the capture no longer answers -- the
checkout still on the commit the report is about, and any pull request on the
run's branch at a head the run started on, reported on, or the receipt names,
or still the discussion's plan. A cancelled cycle answers no adjudication and
a restarted one drops the capture with the rest of its record, so neither
revives it.

The owner, the obligations, and the guidance are then asked again here, as
the revision's own tick asked them. A close a poll latched since ends the
cycle (`captured_revision_closes.stops`) with nothing of the run finished: a
cancelled cycle is settled on its own road and never reaches this recovery
again, and a restart's projection drops the capture with the rest of that
cycle. The
reading the run was handed is taken again off the thread cut at the newest
trusted comment it counted (`late_revision_road.read_through`), so nothing
written after the launch is consumed, and it has to hash to the
requirements the run was handed; a thread that will not read, or a cut that
does not, holds the tick with nothing written. Everything the revision's own
tick would have written past the run's charge and accounting was withheld, so
it is staged now, from the capture and that reading alone: the command that
ran pinned and the conversation settled as that run's would be
(`implementing/captured_completion`), the agent action stamped, the park the
guidance answered taken down, and the reading consumed on every baseline it
moves (`late_revision._read_by`). A candidate a split already acted on is
refused as before the launch (`late_revision_obligations`), its capture
withdrawn behind that park. Otherwise the checkout is reconciled as the
revision's own tick reconciles it
(`late_revision_reconciliation._reconcile_revised_candidate`), handed a
result rebuilt from the capture: a clean tree, the commit it stands on
re-frozen -- a report-only revision's unchanged commit vouched for by that
report -- and measured again under the ceiling as it stands now. A
re-measured candidate advances the generation once, its guidance consumed,
the replies it was owed repaid, and any operator authorization withdrawn, in
the very commit that hands the report to the delivery for that candidate
(`late_revision_landing.lands_the_revision`) -- or, where the comment has no
room for that commit, none of it is written and the capture is kept for a
later dispatch to hand on once room is freed. A reconciliation that parks over
a clean commit it only could not measure lands its park in that same kind of
commit, the report handed on beside it for the bare continue that re-measures
the commit; any other park is written first and the capture withdrawn behind
it. The transfer is decided on the split's children and ledgers as the
recovery read them, so a child or an entry recorded while the candidate was
measured refuses it, and the next dispatch parks over that obligation.

All of it runs inside `implementing/captured_rereads.rereads`
(`captured_revision_closes.rereading`), asked of every
strict edit made while the capture is still pending (`every_edit`), and every
write made then is one: the transfer, the withdrawal, and the park -- landed
through a guarded commit decided, as the transfer is, on every record the
handoff was frozen over (`late_revision_landing.lands_the_park`), rather than
the direct whole-state write, which walks to the comment on its own and would
land the guidance consumed without asking. Each is asked behind the strict
edit's own walk to the comment -- the admission, the comment once more, the
admission again, and last whether the issue was closed for the cycle
(`captured_revision_closes.unlatched`): latched so by a poll, or read so by any
fetch of the issue the recovery made, from the dispatcher's admission on
(`captured_revision_closes.seeing`) -- so a control applied, a relabel, a
close latched or made, an edit, or a move landing behind any reading the
recovery took, or behind that walk, writes nothing at all of the revision: no
park, no consumption, no handoff. A close latched or read there ends the cycle
in the same dispatch, over the comment read again, however the recovery
returns (`captured_revision_closes.rereading`), and one that reading does
not confirm ended stays latched for the cycle, so a reopening a later read
shows revives nothing of it. Once the capture
is no longer pending, what is left is the owner read behind it -- the claim it
settles, the park it takes over an unreadable owner, the park notice it
releases, the re-measured candidate's notice -- and that read asks of the issue
it fetches (`captured_revision_guards.holds`): a control or a relabel there
writes and says none of it, the claim left standing for the tick after the
control comes off. Each notice its settlement says asks the issue once more
right behind that settlement's own write (`late_owner._may_post`), since that
write is the last thing the recovery's question was asked behind; one held
there stays owed on the record.

No developer or adjudicator is launched, no run charged, no verdict recorded or
child created, no label moved, and nothing published: the re-measured
candidate is the late gate's to adjudicate or hand back on the next tick, its
report owed through the delivery's binding, size gate, and publication as any
report is, and a later launch still meets every budget it always did.
"""
from __future__ import annotations

import logging
from functools import partial
from pathlib import Path

from orchestrator.workflow.engine import completion_recovery_models as _recovery_models, usage as _usage
from orchestrator.workflow.late_split import state as _late_state
from orchestrator.workflow.stages.decomposition import (
    captured_revision_closes as _closes,
    captured_revision_guards as _guards,
    late_content as _late_content,
    late_parks as _late_parks,
    late_revision as _late_revision,
    late_revision_obligations as _late_obligations,
    late_revision_reconciliation as _late_reconciliation,
    late_revision_road as _road,
)
from orchestrator.workflow.stages.decomposition.late_content_models import _LateContentSignal
from orchestrator.workflow.stages.decomposition.late_models import _LateContext
from orchestrator.workflow.stages.implementing import captured_completion as _captured_completion

log = logging.getLogger("orchestrator.workflow")

_LAST_AGENT_ACTION = "last_agent_action_at"


def recovers(admitted: _recovery_models.AdmittedCompletion) -> bool:
    """Reconcile the admitted revision's checkout as its own tick would have; True, since this tick is its."""
    admitted = _closes.seeing(admitted)
    context = _LateContext(
        gh=_guards.committing(admitted), spec=admitted.spec, issue=admitted.issue, state=admitted.state,
        generation=_late_state.read_late_generation(admitted.state),
        owner_holds=partial(_guards.holds, admitted),
    )
    if _closes.stops(context):
        return True
    signal = _handed_reading(admitted, context)
    if signal is None:
        log.warning(
            "issue=#%d could not read again the guidance its captured late revision was handed, as it was "
            "handed; holding the tick with nothing written",
            admitted.issue.number,
        )
        return True
    rebuilt = _captured_completion._rebuilt_result(admitted.capture)
    log.info(
        "issue=#%d finishing the captured late revision of agent invocation %d/%s; no developer is "
        "launched for it",
        admitted.issue.number, admitted.capture.invocation.ordinal, admitted.capture.invocation.nonce,
    )
    _captured_completion._settles_the_session(context.state, admitted.capture, rebuilt)
    context.state.set(_LAST_AGENT_ACTION, _usage._now_iso())
    with _closes.rereading(admitted, context):
        if _late_obligations._stranded_by_effects(context, rebuilt) is None:
            _late_parks._answer_park(context)
            repays = _late_revision._read_by(context, signal, rebuilt)
            _late_reconciliation._reconcile_revised_candidate(
                context, Path(admitted.capture.run.worktree), rebuilt, repays=repays,
            )
    return True


def _handed_reading(admitted: _recovery_models.AdmittedCompletion, context: _LateContext) -> _LateContentSignal | None:
    """The reading the revision was handed, taken again off the thread cut where it counted; None where it cannot be.

    The cut keeps every comment the launch's reading could have seen: those
    numbered up to the newest trusted comment it counted, and any whose
    number nothing can compare. Read under the generation the admission held
    to its launch, it partitions and fingerprints as the launch did, and it is
    the reading only where it hashes to the requirements the run was handed.
    """
    issue = admitted.issue
    cut = _thread_through(issue, _road.read_through(admitted.capture))
    if cut is None:
        return None
    text = (issue.title or "", issue.body or "")
    signal = _late_content._signal_of(text, cut, context.state, context.generation)
    if signal.requirements_hash != admitted.capture.handoff.requirements_revision:
        return None
    return signal.delivered()


def _thread_through(issue, through: int | None) -> list | None:
    """The thread as one read of it, cut to what a reading counting up to `through` saw; None where it cannot be."""
    if through is None:
        return None
    try:
        read = list(issue.get_comments())
    except Exception:  # noqa: BLE001 - a thread nobody could read holds the capture, never consumes or retires it
        return None
    return [issue_comment for issue_comment in read if _counted_within(issue_comment, through)]


def _counted_within(issue_comment, through: int) -> bool:
    """Whether the launch's reading could have seen `issue_comment`: numbered up to `through`, or not comparably."""
    number = getattr(issue_comment, "id", None)
    return not isinstance(number, int) or number <= through
