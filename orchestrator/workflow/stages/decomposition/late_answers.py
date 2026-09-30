# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What trusted answers to late parks earn and the watermark they consume.

Certification, reverted edits, and question replies preserve their distinct
effects. Consumption rebaselines the same frozen generation and persists the
reply watermark and the issue-wide requirements baseline off that one reading;
a bare continue cannot answer a decomposer question.
"""
from __future__ import annotations

from orchestrator.workflow.engine import comments as _comments, messages as _messages
from orchestrator.workflow.stages.decomposition import (
    late_authorize as _late_authorize,
    late_owed_replies as _late_owed_replies,
    late_park_state as _late_park_state,
    late_parks as _late_parks,
    late_revision as _late_revision,
    late_session as _late_session,
)
from orchestrator.workflow.stages.decomposition.late_content_models import _LateContentSettlement, _LateContentSignal
from orchestrator.workflow.stages.decomposition.late_models import _LateContext
from orchestrator.workflow.stages.decomposition.late_result_models import _LateDisposition

# The parks whose retry is the revision's own post-run reconciliation rather
# than another developer run. A worktree the developer left changed, a
# candidate nobody could measure, and a commit the developer changed nothing
# about and vouched nothing for are all settled by a human reading the
# checkout, so a bare continue re-reads it instead of paying for an agent --
# and on the last of them that continue IS the acknowledgment the unchanged
# commit was missing. A park left out of this set would be no park at all: the
# next tick would fall through to adjudicating the very candidate it holds.
_REVISION_PARKS = frozenset((
    _late_park_state.PARK_REVISION_DIRTY,
    _late_park_state.PARK_REVISION_UNMEASURED,
    _late_park_state.PARK_REVISION_UNANSWERED,
))

_CERTIFIED_NOTICE = (
    ":white_check_mark: the frozen candidate was certified against the "
    "updated issue; resuming its adjudication."
)

_REOPENED_NOTICE = (
    ":arrows_counterclockwise: thanks -- re-running the late decomposer "
    "against your answer."
)

_REVERTED_NOTICE = (
    ":leftwards_arrow_with_hook: the edit was taken back; the frozen "
    "candidate matches this issue again and its adjudication is resuming."
)


def _park_answer(standing: str | None):
    """The owner that reads a reply to the park this issue is standing on.

    None for an issue standing on nothing of this mode's -- including a park
    another stage left, which is not this owner's to answer.

    The `single` park's answer is the one owned elsewhere. Ending it is a
    decision to publish past the size gate rather than a reading of what the
    humans have said, so what is here is the routing and what is there is the
    proof the decision costs.
    """
    if standing == _late_park_state.PARK_CONTENT_DRIFT:
        return _reverted
    if standing in _REVISION_PARKS:
        return _late_revision._retry_revision
    if standing == _late_park_state.PARK_QUESTION:
        return _answered_question
    if standing == _late_park_state.PARK_SINGLE_DECISION:
        return _late_authorize._answered_single
    return None


def _reverted(
    context: _LateContext, signal: _LateContentSignal,
) -> _LateContentSettlement:
    """Answer a drift park the requirements themselves took back.

    Guidance goes first, because taking the edit back does not withdraw it. A
    human who reverted the title and asked for a change still asked for the
    change, and the revert only decides which requirements it is asked
    against -- so it routes exactly as it would have under the park, and the
    developer run it buys is what invalidates a verdict taken before any of
    it. Absorbing it here instead would consume a human's instruction without
    acting on it and then reuse an answer nobody re-earned.

    Guidance the park's notice WITHHELD routes the same way, and the revert is
    what lets it. Written before the human was told the issue had parked, it
    was never an answer to the park -- but the park is not what ends here:
    the requirements taking the edit back are, and with nothing left standing
    those words are what any unanswered instruction is. Settling without them
    would fold them into every baseline and reuse a verdict no agent took
    over them, so they are quoted to the developer beside any fresh guidance.

    A revert with nothing to act on is an answer nobody had to write: the
    candidate matches the issue again, so the park is cleared and the recorded
    verdict -- taken against exactly these requirements -- still stands.
    Leaving the park standing would not be harmless, either: `awaiting_human`
    is the flag that suppresses the announcement a question verdict earns, so
    a reverted edit would silence a question recorded and never said out loud.
    """
    if signal.guidance or signal.withheld:
        return _late_revision._revise_from_guidance(context, signal)
    _late_parks._answer_park(context)
    _comments._post_issue_comment(
        context.gh, context.issue, context.state, _REVERTED_NOTICE,
    )
    return _consumed(context, signal)


def _certified(
    context: _LateContext, signal: _LateContentSignal,
) -> _LateContentSettlement:
    """Take the human's word that the frozen candidate still applies.

    The whole fingerprint moves onto the content as it now reads, which is
    what the certificate is: the same commit, the same generation, nothing
    about the candidate re-derived and no developer paid for.

    What the certificate does NOT cover is a verdict, so any recorded one is
    dropped and the adjudication is earned again. A human vouching for the
    commit has said nothing about an answer taken against the requirements
    that have since moved -- and acting on one would be the very thing the
    drift rule refuses, a step later: a split creating children that describe
    a scope nobody is asking for any more.

    Reached only with nothing withheld. Guidance the park's notice held back
    goes to the developer once a certificate answers the park, since the
    adjudication a certificate buys can still be stopped at any of its spawn
    gates -- and a consumption written ahead of those would spend words no
    agent had read.
    """
    _late_session._drop_late_result(context.state)
    _late_parks._answer_park(context)
    _comments._post_issue_comment(
        context.gh, context.issue, context.state, _CERTIFIED_NOTICE,
    )
    return _consumed(context, signal)


def _answered_question(
    context: _LateContext, signal: _LateContentSignal,
) -> _LateContentSettlement:
    """Reopen a categorized question, but only for a real answer.

    Dropping the recorded outcome is what reopens it: the record is exactly
    what suppresses the next spawn, so a question the human has now answered
    has to stop reading as an answer before the adjudicator will run again.
    The tick is marked as carrying an answer at the same time, so the run that
    follows continues the conversation that asked rather than opening one that
    would have to be told the question before it could be told the answer.

    The answer is consumed here, ahead of the spawn gates, so it is also
    recorded as owed a whole quote: the reopened run reads the thread through
    a bounded excerpt of its tail, and a long answer would otherwise be spent
    on a run that read only its end -- or, stopped at a gate, nothing.

    An answer beside guidance the question's notice WITHHELD goes to the
    developer instead, with both quoted. The adjudication an answer reopens
    is consumed for before it passes its spawn gates, so words written before
    the question was put would be spent on a run that may never start; the
    developer run is consumed for only once it has run.

    A bare continue is refused rather than absorbed. It carries no answer, and
    letting it through would leave the workflow choosing between a `single` it
    was never told to record and a spawn asking the same question again --
    which is why the command is consumed, the refusal is posted once, and the
    park stays exactly where it is.
    """
    if signal.guidance and signal.withheld:
        return _late_revision._revise_from_guidance(context, signal)
    if signal.guidance:
        _late_session._drop_late_result(context.state)
        context.answering = True
        _late_parks._answer_park(context)
        _comments._post_issue_comment(
            context.gh, context.issue, context.state, _REOPENED_NOTICE,
        )
        _late_owed_replies._owe(context, signal.guidance)
        return _consumed(context, signal)
    if signal.bare_continue:
        # Nothing handed over to consume: `_consumed` below settles the shared
        # watermark from this signal's own frozen fingerprint, which already
        # covers the command. The refusal itself needs no crossing either --
        # this mode reads the thread through the id ledger, so our own note is
        # dropped where it is read rather than skipped by a mark.
        _messages._refuse_parked_continue(
            context.gh, context.issue, context.state,
        )
        return _consumed(
            context, signal, disposition=_LateDisposition.PARKED,
        )
    return _LateContentSettlement()


def _consumed(
    context: _LateContext,
    signal: _LateContentSignal,
    *,
    disposition: _LateDisposition | None = None,
) -> _LateContentSettlement:
    """Fold fresh trusted conversation into the baselines that cover it.

    All three of them, in the one write: this mode's own fingerprints, the
    shared `last_action_comment_id`, and the issue-wide `user_content_hash`,
    each taken off the same frozen reading -- see `late_park_state` for which
    reader each one stops. Every park answer that reads a reply arrives here,
    so none of the three can be left behind by one of them. A reading handed
    on undelivered while it still withholds guidance moves the shared one
    alone: nothing this answer runs reads those words, so they are kept for
    the reading that will.
    """
    _late_park_state._consume_reading(context, signal)
    _late_park_state._persist(context)
    return _LateContentSettlement(disposition=disposition, persisted=True)
