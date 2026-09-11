# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What the humans have said since the candidate was frozen, and what it earns.

One question asked of every tick that reaches a live oversized generation:
have the requirements moved, and has anybody answered? The fingerprints beside
this owner say which; this one decides what each answer is worth.

Drift outranks every answer, and that is the whole rule. An edit to the title,
the body, or a comment already counted into the baseline changes what the
candidate is supposed to be, and an answer that arrived in the same window was
written about the scope as it stood before -- applying it would adjudicate a
reply against requirements it never saw. So the first tick that sees drift
parks and consumes nothing: the frozen commit, the late session, the
generation record, and any hold it took are all left exactly as they were,
because none of them is wrong, only unadjudicable until a human says what the
edit meant.

Once that park stands, the human's reply is what resolves it, and the two
kinds of reply mean opposite things. A bare `/orchestrator continue` is a
certificate: the committed work still answers the updated issue, so the
fingerprints are re-baselined onto the content as it now reads and the same
frozen candidate goes on to be adjudicated -- against the updated
requirements, which is why a verdict recorded before the edit is dropped
rather than reused. Substantive guidance is not a certificate -- it says the
work itself has to change, so the original developer session is resumed
against it and the candidate is re-frozen and re-measured from what comes
back.

Guidance means the same thing when nothing is parked at all. An adjudication
in flight, or one that already recorded a verdict, is still work a human can
ask to be different -- so the developer is resumed there too, and the
re-measured candidate that comes back is what retires a verdict taken over
work the human has since changed. The only reply with nothing to do is a bare
continue arriving where no park is waiting on it.

The other park this owner answers is the categorized question, and it is the
one place the two replies are not symmetric. Only substantive guidance
reopens it: the recorded outcome is dropped so the adjudicator runs again
against the human's answer. A bare continue may not, because a question is not
a step that failed and "proceed" is not an answer to "which half of this is in
scope" -- it is refused, and the issue stays parked on the question it is
really waiting on.

The last park it routes is the one an adjudicator's `single` leaves, and it
is routed rather than answered: what ends that park is a decision to publish
an oversized change unsplit, which is a third kind of reply entirely and whose
proof, record, and refusals are `late_authorize`'s beside this. Guidance means
there what it means everywhere -- the work has to change, so the developer is
resumed and the candidate is re-measured -- which is why that owner is handed
the whole reply rather than only the command in it.

Everything this owner stages, it persists. The parks are external effects
that go out after the durable write, and the one branch that stages nothing --
an unchanged, un-answered park -- deliberately writes nothing at all, so an
issue waiting on a human costs no comment write per tick.
"""
from __future__ import annotations

import logging

from orchestrator.workflow.engine import comments as _comments, messages as _messages
from orchestrator.workflow.stages.decomposition import (
    late_authorize as _late_authorize,
    late_content as _late_content,
    late_park_state as _late_park_state,
    late_parks as _late_parks,
    late_revision as _late_revision,
    late_session as _late_session,
)
from orchestrator.workflow.stages.decomposition.late_models import (
    _LateContentSettlement,
    _LateContentSignal,
    _LateContext,
    _LateDisposition,
)

log = logging.getLogger("orchestrator.workflow")

_AWAITING_HUMAN = "awaiting_human"

_PARK_REASON = "park_reason"

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

_DRIFT_PARK = (
    "the requirements changed after this issue's oversized committed "
    "candidate was frozen, so its adjudication is on hold. Nothing was "
    "discarded -- the frozen commit, the late session, the recorded "
    "generation, and any hold on its pull request all stand. Reply "
    "`/orchestrator continue` if the committed work still answers the "
    "updated issue, or with the change to make and the developer is resumed "
    "against it."
)

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


def _reconcile_late_content(
    context: _LateContext,
) -> _LateContentSettlement:
    """Settle what the humans have said about this frozen candidate.

    A settlement with no disposition is the only answer that lets adjudication
    carry on. Every other one is the whole of what the tick did.

    A generation with no baseline yet is taking one: the content as it stands
    is what the candidate was frozen against, so it is recorded and nothing is
    drift. Only once a baseline exists is there anything to compare.
    """
    signal = _late_content._read_content_signal(
        context.issue, context.state, context.generation,
    )
    if not signal.baselined:
        return _baselined(context, signal)
    if signal.drifted:
        return _drifted(context, signal)
    return _undrifted(context, signal)


def _baselined(
    context: _LateContext, signal: _LateContentSignal,
) -> _LateContentSettlement:
    """Record the requirements this candidate was frozen against."""
    context.generation = _late_content._rebaselined(
        context.generation, signal.fingerprint,
    )
    _late_park_state._persist(context)
    return _LateContentSettlement(persisted=True)


def _drifted(
    context: _LateContext, signal: _LateContentSignal,
) -> _LateContentSettlement:
    """Answer a candidate whose requirements moved out from under it.

    The park comes first and consumes nothing, so an answer that arrived in
    the same window is still unread when the human comes back to it. Only once
    the park stands does a reply resolve it, and which reply it is decides
    whether the frozen candidate is certified or the developer is resumed.
    """
    if _standing_park(context) != _late_park_state.PARK_CONTENT_DRIFT:
        return _parked_drift(context)
    if signal.guidance:
        return _late_revision._revise_from_guidance(context, signal)
    if signal.bare_continue:
        return _certified(context, signal)
    return _LateContentSettlement(disposition=_LateDisposition.PARKED)


def _undrifted(
    context: _LateContext, signal: _LateContentSignal,
) -> _LateContentSettlement:
    """Answer a candidate whose requirements are the ones it was frozen on.

    What the issue is waiting on decides what a fresh trusted comment means. A
    drift park has been answered by the edit going back, though guidance that
    came with it is still guidance; a revision park is settled by re-reading
    the checkout; and a categorized question by the answer to it.

    An issue waiting on nothing is the case with no park to read, and guidance
    means there what it means everywhere else: the work has to change, so the
    developer is resumed against it. Folding it into the baseline instead
    would consume a human's instruction without acting on it -- and with a
    verdict already recorded, leave that verdict standing over work the human
    just asked to be different. A bare continue is the one reply that lands
    here with nothing to do: no park is waiting on it and no candidate needs
    certifying, so it is consumed and the tick carries on.
    """
    answers = _park_answer(_standing_park(context))
    if answers is not None:
        return answers(context, signal)
    if signal.guidance:
        return _late_revision._revise_from_guidance(context, signal)
    if signal.bare_continue:
        return _consumed(context, signal)
    return _LateContentSettlement()


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


def _parked_drift(context: _LateContext) -> _LateContentSettlement:
    """Hold the candidate while a human says what the edit meant."""
    log.info(
        "issue=#%d the requirements moved under frozen candidate %s; "
        "parking without discarding it",
        context.issue.number, context.generation.candidate_sha,
    )
    _late_parks._park(
        context, _DRIFT_PARK, reason=_late_park_state.PARK_CONTENT_DRIFT,
    )
    return _LateContentSettlement(
        disposition=_LateDisposition.PARKED, persisted=True,
    )


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


def _standing_park(context: _LateContext) -> str | None:
    """The reason this issue is parked on right now, or None if it is not.

    Read off what the tick FOUND rather than off what it has staged: the
    coordinator retires the parks a fresh attempt supersedes before this owner
    runs, and none of the parks answered here is one of those.
    """
    if not context.state.get(_AWAITING_HUMAN):
        return None
    standing = context.state.get(_PARK_REASON)
    return standing if isinstance(standing, str) else None
