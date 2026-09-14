# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What trusted answers to late parks earn and the watermark they consume.

Certification, reverted edits, and question replies preserve their distinct
effects. Consumption rebaselines the same frozen generation and persists
the reply watermark; a bare continue cannot answer a decomposer question.
"""
from __future__ import annotations

from orchestrator.workflow.engine import comments as _comments, messages as _messages
from orchestrator.workflow.stages.decomposition import (
    late_authorize as _late_authorize,
    late_content as _late_content,
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

    A revert with nothing to act on is an answer nobody had to write: the
    candidate matches the issue again, so the park is cleared and the recorded
    verdict -- taken against exactly these requirements -- still stands.
    Leaving the park standing would not be harmless, either: `awaiting_human`
    is the flag that suppresses the announcement a question verdict earns, so
    a reverted edit would silence a question recorded and never said out loud.
    """
    if signal.guidance:
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

    A bare continue is refused rather than absorbed. It carries no answer, and
    letting it through would leave the workflow choosing between a `single` it
    was never told to record and a spawn asking the same question again --
    which is why the command is consumed, the refusal is posted once, and the
    park stays exactly where it is.
    """
    if signal.guidance:
        _late_session._drop_late_result(context.state)
        context.answering = True
        _late_parks._answer_park(context)
        _comments._post_issue_comment(
            context.gh, context.issue, context.state, _REOPENED_NOTICE,
        )
        return _consumed(context, signal)
    if signal.bare_continue:
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

    Both of them, because two different readers walk the same thread. This
    mode's own fingerprints stop the comment coming back as fresh guidance;
    the shared `last_action_comment_id` stops the later validating ->
    in_review handoff finding it as fresh PR feedback and routing the pull
    request to `fixing` over an answer this mode has already spent. Every path
    that reads a reply arrives here, so neither watermark can be left behind
    by one of them.
    """
    context.generation = _late_content._rebaselined(
        context.generation, signal.fingerprint,
    )
    _late_park_state._mark_replies_read(
        context, signal.fingerprint.comment_watermark_id,
    )
    _late_park_state._persist(context)
    return _LateContentSettlement(disposition=disposition, persisted=True)
