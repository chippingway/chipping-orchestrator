# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Consume trusted oversized-candidate decisions and record their publication terms.

The command must name the parked candidate and answer its recorded single
verdict. Refusals retain their comment marker and consume only the reading
that supplied the decision.
"""
from __future__ import annotations

import logging

from orchestrator import config
from orchestrator.github.comments import carries_own_marker
from orchestrator.workflow.engine import comments as _comments
from orchestrator.workflow.late_split import (
    formats as _formats,
    overrides as _overrides,
    payloads as _payloads,
)
from orchestrator.workflow.late_split.models import LateVerdict
from orchestrator.workflow.stages.decomposition import (
    late_authorization_proof as _late_authorization_proof,
    late_content as _late_content,
    late_content_models as _late_content_models,
    late_park_state as _late_park_state,
    late_parks as _late_parks,
    late_revision as _late_revision,
    late_run_reading as _late_run_reading,
)
from orchestrator.workflow.stages.decomposition.late_models import _LateContext
from orchestrator.workflow.stages.decomposition.late_result_models import _LateDisposition

log = logging.getLogger("orchestrator.workflow")

# What the two refusals below both end on. A human whose command this park
# could not act on is owed the command that would have worked, spelled against
# the candidate actually waiting -- so it is written once and shared, rather
# than twice with a chance of drifting apart.
_HOW_TO_DECIDE = (
    "Post `/orchestrator authorize-oversized {candidate}` as the entire "
    "comment to publish it as it stands, or reply with the change to make "
    "and the developer is resumed against it."
)

# Stamped on the answer one refused reply earns, and scoped to the reading it
# was written for. The sentence and the write that consumes what it answers
# cannot be made one operation, so a tick that says it and then fails to record
# it reads the same reply again on the next poll -- and the receipt already on
# the thread is what keeps that second reading from saying the same thing
# twice. An HTML comment, so it is invisible in the rendered thread. A reply
# written AFTER the failed write moves the scope, which is right: a second
# request is a second decision and is owed its own answer.
_REFUSED_MARKER = (
    "<!--orchestrator-authorize-oversized-refused"
    ":issue={issue}:read={read}-->"
)

_WRONG_CANDIDATE = (
    "{mentions} that authorization names a commit this issue is not waiting "
    "on, so nothing was published and nothing was recorded. The candidate "
    "parked for a decision is `{candidate}`. " + _HOW_TO_DECIDE
)

_NO_RECORDED_VERDICT = (
    "{mentions} that authorization arrived over an adjudication this issue "
    "can no longer show: nothing on the record says `{candidate}` was read as "
    "one change, so there is no verdict to publish on and nothing was "
    "recorded. The commit, its worktree and any pull request it stands under "
    "are exactly as they were, and the candidate goes back to be adjudicated "
    "again -- this issue stops for whatever that answers rather than for a "
    "decision nothing can show you the grounds for."
)

_CONTINUE_REFUSED = (
    "{mentions} `/orchestrator continue` is not a decision to publish an "
    "oversized change unsplit, so this issue is still parked on one. "
    + _HOW_TO_DECIDE
)


def _answered_single(
    context: _LateContext, signal: _late_content_models._LateContentSignal,
) -> _late_content_models._LateContentSettlement:
    """What a reply to a parked unsplittable candidate is worth.

    Guidance outranks an authorization in the same batch, and deliberately.
    The two say opposite things -- one that the change publishes as it is, the
    other that it has to be different -- and the safe reading of a human who
    wrote both is the one that publishes nothing: the developer is resumed,
    the candidate is re-frozen and re-measured, and whatever comes back is
    adjudicated again. An operator who meant the authorization says it on its
    own, which is the only shape it is ever read from anyway.

    A reply that is none of the three leaves the park exactly where it is.
    """
    if signal.guidance:
        return _late_revision._revise_from_guidance(context, signal)
    if signal.authorization is not None:
        return _authorized(context, signal, signal.authorization)
    if signal.bare_continue:
        return _refused(
            context, signal, _CONTINUE_REFUSED.format(
                mentions=config.HITL_MENTIONS,
                candidate=context.generation.candidate_sha,
            ),
        )
    return _late_content_models._LateContentSettlement()


def _authorized(
    context: _LateContext,
    signal: _late_content_models._LateContentSignal,
    authorization: _late_content_models._LateAuthorization,
) -> _late_content_models._LateContentSettlement:
    """Record what an operator authorized this candidate to publish on.

    Nothing is published here, which is the whole shape of it: what this
    writes is evidence, and what a candidate publishes under is decided where
    publications are. The tick carries straight on to the verdict it already
    had, so the settlement happens on this same poll -- and a process that
    dies in between comes back to a cleared park, a durable authorization, and
    the same recorded `single`, which is exactly enough to finish.

    The record, the park coming down, and the reply being consumed ride one
    write. Any of them alone is a state the next tick would read wrong: the
    record without the park cleared says a human is still owed a question they
    have answered, the park without the record sends the candidate back into
    the adjudication they just answered, and the record without the watermark
    leaves the same comment able to authorize whatever is parked next.
    """
    generation = context.generation
    if not _names_the_candidate(authorization, generation):
        return _refused(context, signal, _WRONG_CANDIDATE.format(
            mentions=config.HITL_MENTIONS,
            candidate=generation.candidate_sha,
        ))
    if not _answered_by_the_record(context, generation):
        return _refused(
            context,
            signal,
            _NO_RECORDED_VERDICT.format(
                mentions=config.HITL_MENTIONS,
                candidate=generation.candidate_sha,
            ),
            still_waiting=False,
        )
    contribution = _late_authorization_proof._proved_contribution(context)
    if contribution is None:
        return _late_content_models._LateContentSettlement()
    log.info(
        "issue=#%d had its oversized candidate %s authorized to publish "
        "unsplit by a trusted operator in comment %d; recording the terms "
        "and settling the verdict already on the record",
        context.issue.number,
        context.generation.candidate_sha,
        authorization.comment_id,
    )
    _overrides.record_publication_override(
        context.state,
        _overrides.LateOversizedPublication(
            candidate_sha=contribution.candidate_sha,
            base_sha=contribution.base_sha,
            fingerprint=contribution.digest,
            additions=context.generation.additions,
            threshold=context.generation.threshold,
            comment_id=authorization.comment_id,
        ),
    )
    _late_parks._answer_park(context)
    _consume(context, signal)
    _late_park_state._persist(context)
    return _late_content_models._LateContentSettlement(persisted=True)


def _names_the_candidate(
    authorization: _late_content_models._LateAuthorization, generation,
) -> bool:
    """Whether the commit this command names is the one parked.

    Asked against the record as it stands NOW rather than against anything the
    command carried. A commit an operator copied out of a notice about an
    earlier candidate is the ordinary way this fails: the developer was
    resumed, the work was re-frozen, and the sentence they were replying to is
    about a commit no longer under adjudication.

    Held to being a whole object id on the way in, so an abbreviation is
    refused as the mismatch it is rather than compared as text. Nothing here
    abbreviates, so nothing here reads one back.
    """
    return _payloads.as_hex(
        authorization.candidate_sha, _formats.COMMIT_LENGTHS,
    ) == generation.candidate_sha


def _answered_by_the_record(context: _LateContext, generation) -> bool:
    """Whether the answer this command would publish is still on the record.

    Asked for the same reason the settlement asks for it: what the command
    authorizes is the publication of an adjudication already taken, so an
    issue whose record cannot show one has nothing for it to license. Reached
    only where that record was hand-edited or lost, and answered rather than
    ignored, because the human is owed the reason -- and because the park has
    to come down with that answer, which is what the refusal below does.
    """
    recorded = _late_run_reading._read_late_run(context.state)
    return recorded.verdict == LateVerdict.SINGLE and recorded.answers(
        generation,
    )


def _refused(
    context: _LateContext,
    signal: _late_content_models._LateContentSignal,
    said: str,
    *,
    still_waiting: bool = True,
) -> _late_content_models._LateContentSettlement:
    """Say why this reply changed nothing, and leave the issue where it goes.

    Consumed on the way out, which is what makes the sentence once per REPLY
    rather than once per tick: the park is answered by a human, so it stands
    until one arrives, and repeating the refusal every poll would bury the
    notice explaining what they are actually being asked.

    The consumption is a second operation, though, and a tick that says its
    sentence and then fails to record it reads the same reply again. So the
    sentence carries a receipt scoped to the reading it answers, and the
    thread is asked for that receipt before it is written a second time --
    the same at-most-once discipline every other answer in this repository
    has, and the reason a duplicate costs a poll rather than a duplicate.

    `still_waiting` is whether the park this answered is still what the issue
    is stopped for. A command naming another commit and a bare continue both
    leave it standing: the same decision is owed, and the notice above this
    sentence still says what it is. An authorization over an adjudication the
    record cannot show does NOT, and that difference is not cosmetic. There is
    no decision to be owed until something adjudicates the candidate again,
    and `awaiting_human` is exactly the flag that suppresses the announcement
    a categorized question earns -- so a park left standing over the
    replacement run would cost a human the one sentence nothing else will ever
    say, and would leave a split creating children under a claim that the
    issue is waiting. It comes down with the answer, and the tick carries on
    to the adjudication this sentence promises.
    """
    marker = _REFUSED_MARKER.format(
        issue=context.issue.number,
        read=signal.fingerprint.comment_watermark_id,
    )
    if not _already_answered(context, marker):
        _comments._post_issue_comment(
            context.gh, context.issue, context.state, f"{said}\n\n{marker}",
        )
    if not still_waiting:
        _late_parks._answer_park(context)
    _consume(context, signal)
    _late_park_state._persist(context)
    return _late_content_models._LateContentSettlement(
        disposition=_LateDisposition.PARKED if still_waiting else None,
        persisted=True,
    )


def _already_answered(context: _LateContext, marker: str) -> bool:
    """Whether this thread already carries OUR answer to this reading.

    Both halves of the receipt are asked -- the scoped marker and the author
    -- since an HTML comment is plain text anybody may paste, and read from
    anybody it would silence a sentence a human is owed.
    """
    return carries_own_marker(
        context.issue.get_comments(),
        marker,
        bot_login=getattr(context.gh, "_bot_login", None),
    )


def _consume(context: _LateContext, signal: _late_content_models._LateContentSignal) -> None:
    """Record the conversation this tick acted on as read, both ways.

    The generation's own fingerprints stop the command coming back as a fresh
    authorization on the next poll, which for a record that bypasses the size
    gate is the difference between a decision and a standing permission. The
    issue-wide `last_action_comment_id` stops the stage this settlement hands
    the issue to reading the same comment as fresh feedback it has to resume
    somebody over.
    """
    context.generation = _late_content._rebaselined(
        context.generation, signal.fingerprint,
    )
    _late_park_state._mark_replies_read(
        context, signal.fingerprint.comment_watermark_id,
    )
