# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The one decision that publishes an oversized candidate a human has read.

The other side of the park beside this. `late_unsplit` is what the workflow
does when an adjudicator answers that an oversized change stays one change --
it stops, because the ceiling exists so unreviewed bulk does not reach a pull
request and an agent proposing to publish past it is the thing being guarded
against. This owner is what ENDS that stop: an operator who has read the
change saying, in a comment on the issue, that it publishes as it stands.

It is a dedicated command and not a reply, and every term of that follows from
what it licenses. A generic `/orchestrator continue` says "the step you
described failed for a reason nobody has to answer, do it again", which is not
a decision about a change anybody read -- so it is refused here rather than
absorbed. Ordinary prose is guidance: it says the work itself has to change,
which resumes the developer and re-measures whatever comes back, and reading
it as consent would publish a candidate on the strength of somebody agreeing
that something was hard. And the command names the exact commit, because a
bare "yes" would authorize whatever the worktree ends on next.

Only the WHOLE comment is the command. A line of it under a paragraph is a
paragraph that mentions it -- guidance, carried to the developer with
everything else the human wrote -- and that split is what makes the two
answers unambiguous rather than a matter of which the reader saw first.

Who may say it is the allowlist every other workflow-driving comment on a
public thread goes through, applied where the thread is read: an outsider's
comment is not in the reading this owner is handed, so nothing they post can
be an authorization, become guidance, or move a watermark. WHEN they may say
it is bounded the same way every reply is: a comment written before the park's
own notice is not an answer to it, since the human had not been told anything
yet, so a command posted ahead of the question it answers goes stale rather
than authorizing the candidate it happened to name.

What a command that IS all of those things earns is a proof and then a record.
The proof is the contribution recomputed here, between the frozen pair, in the
developer's own worktree -- not read off anything stored, because a digest a
caller handed in proves only that a caller had one. The record is the
`late_split/overrides` group, which is durable evidence and publishes nothing:
it names the candidate, the base it was read over, that recomputed digest and
the scheme it was taken under, the measurement that made the candidate
oversized, and the comment the authorization was made in.

That record and the park coming down and the reply being consumed are ONE
write, and they have to be. A park cleared without the record would send the
candidate straight back into the adjudication a human just answered; a record
without the consumed watermark would let the same comment authorize a second
candidate later; and either half landing alone is a state a crash could leave.
Past that write the tick carries on to the answer it already had, which is
where the publication is decided -- `late_settlement` asks this owner whether
an authorization still covers the candidate in hand, and settles the recorded
`single` where it does.

Everything that cannot be proved is answered on the thread and consumed --
once, under a receipt scoped to the reading it answers, because the sentence
and the write that consumes it are two operations and a tick can die between
them. Where those answers differ is what they leave standing. A command naming
another commit leaves the park exactly where it is: the same decision is owed,
and the notice explaining it is still the last word above the refusal. One
arriving over an adjudication the record can no longer show retires it, and
has to -- there is nothing to be owed until something adjudicates the
candidate again, and `awaiting_human` is the flag that suppresses the
announcement a categorized question earns, so a park left standing over that
run would cost a human the one sentence nothing else will ever say.

A contribution this host could not fingerprint is not answered at all --
nothing about it is the human's doing, the next tick takes the same reading
again, and consuming their command would lose an authorization they would have
to make twice.

The publication asks for that fingerprint AGAIN, and every term of the record
with it. The settlement can be reached by a later poll, on a later process,
and on a host that never held the content between the frozen pair -- so what
licenses it is the objects agreeing with the record rather than the record
agreeing with itself, which is the one thing a hand edit and a half-written
crash can both arrange.

What none of those terms can say is WHICH answer was authorized. They describe
a candidate, and a candidate can be adjudicated more than once: a certificate
over edited requirements throws the recorded verdict away and buys a fresh
one, and a revision advances the generation and buys another, both against
requirements a human has since changed. Every term here would still match, so
the record is bound to that answer by being DROPPED with it: `late_session`
drops it where a result is thrown away and again where the run replacing that
result is recorded, which is the statement of the rule no road gets around,
and `late_revision_reconciliation` drops it where a re-freeze mints a fresh
question. An authorization outliving the answer it was given for is the one
shape it may not take: it would license the next adjudication's `single` on a
permission nobody granted it.
"""
from __future__ import annotations

import logging

from orchestrator.config import settings as config
from orchestrator.git.measurement import fingerprint as _fingerprint
from orchestrator.git.worktrees import paths as _worktree_paths
from orchestrator.github.comments import carries_own_marker
from orchestrator.workflow.engine import comments as _comments
from orchestrator.workflow.late_split import (
    formats as _formats,
    overrides as _overrides,
    payloads as _payloads,
)
from orchestrator.workflow.late_split.models import LateVerdict
from orchestrator.workflow.stages.decomposition import (
    late_content as _late_content,
    late_park_state as _late_park_state,
    late_parks as _late_parks,
    late_revision as _late_revision,
    late_session as _late_session,
)
from orchestrator.workflow.stages.decomposition.late_models import (
    _LateAuthorization,
    _LateContentSettlement,
    _LateContentSignal,
    _LateContext,
    _LateDisposition,
)

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
    context: _LateContext, signal: _LateContentSignal,
) -> _LateContentSettlement:
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
    return _LateContentSettlement()


def _authorized(
    context: _LateContext,
    signal: _LateContentSignal,
    authorization: _LateAuthorization,
) -> _LateContentSettlement:
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
    contribution = _proved_contribution(context)
    if contribution is None:
        return _LateContentSettlement()
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
    return _LateContentSettlement(persisted=True)


def _names_the_candidate(
    authorization: _LateAuthorization, generation,
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
    recorded = _late_session._read_late_run(context.state)
    return recorded.verdict == LateVerdict.SINGLE and recorded.answers(
        generation,
    )


def _proved_contribution(context: _LateContext):
    """Recompute what the frozen pair contributes, or None if it cannot.

    Taken here rather than carried, and taken over the pinned pair rather than
    over whatever the checkout stands on. The worktree is writable for the
    whole of an adjudication and for the whole of the wait after it, so its
    head says nothing about what a human read; the frozen base and the frozen
    candidate are what the notice named and what the decision was made about.

    A reading this host cannot take leaves the park standing and the command
    unconsumed. Nothing about that is the operator's doing -- a store that
    cannot hand back the content between two commits it holds is repaired by
    an operator, not by a comment -- so the next tick takes the same reading
    again rather than asking a human to authorize the same change twice.
    """
    generation = context.generation
    contribution = _fingerprint._fingerprint_contribution(
        _worktree_paths._worktree_path(context.spec, context.issue.number),
        generation.base_sha,
        generation.candidate_sha,
    )
    if contribution.is_fingerprinted:
        return contribution
    log.warning(
        "issue=#%d cannot fingerprint what candidate %s contributes (%s); "
        "leaving the authorization unread and the candidate parked",
        context.issue.number,
        generation.candidate_sha,
        contribution.failure,
    )
    return None


def _publishes_unsplit(context: _LateContext) -> bool:
    """Whether an operator's authorization still covers THIS candidate.

    Asked by the settlement, of the record rather than of the thread: what a
    tick acts on is the durable evidence, so a process that died between the
    write and the publication finishes from what the write left.

    Every frozen term is compared, not the commit alone. The commit says which
    object was read; the base says what that object was read as CONTRIBUTING,
    and the two counts say the reading a human was shown when they decided. A
    generation that has moved under any of them is a different question from
    the one that was answered.

    Then the contribution is fingerprinted AGAIN and held to the digest the
    record carries, and that is the whole point of recording one. The terms
    above are the pinned comment agreeing with itself, which a hand edit, an
    older binary, and a record half-written by a crash can all arrange; the
    digest is the only term answered by the objects rather than by the record,
    so it is the only one that says the change about to publish is the change
    a human read. It is re-taken here rather than trusted from the tick that
    wrote it because the two are not the same tick: the publication can be
    reached by a later poll, on a later process, and on a host that never held
    the content between the pair.

    A reading this host cannot take is refused on the same footing as one that
    disagrees. Both leave the candidate where it stands with the authorization
    still on the record, and what that costs is a poll: the next tick takes
    the reading again, and a store somebody repairs publishes what they
    authorized without asking them to authorize it twice.

    WHICH answer was authorized is deliberately not asked here, because no
    term of the record could answer it: the same candidate can be adjudicated
    again, and every field would still match. What holds that line is the
    record being dropped with the answer it covers -- wherever a result is
    thrown away and wherever a re-freeze mints a fresh question -- so a record
    still readable here is one whose answer nothing has replaced.
    """
    override = _overrides.read_publication_override(context.state)
    if override is None:
        return False
    publication = override.publication
    if not _names_this_candidate(publication, context.generation):
        return False
    contribution = _proved_contribution(context)
    if contribution is None:
        return False
    if contribution.digest == publication.fingerprint:
        return True
    log.warning(
        "issue=#%d has an authorization for candidate %s whose contribution "
        "no longer fingerprints to the digest it was recorded on; leaving the "
        "candidate unpublished",
        context.issue.number,
        context.generation.candidate_sha,
    )
    return False


def _names_this_candidate(publication, generation) -> bool:
    """Whether the record's frozen terms are the ones on the record now.

    The cheap half of the question, asked first so a record about another
    candidate costs no reading at all. What it establishes is only that the
    two agree about which pair, how much, and against which ceiling -- the
    digest beside it is what establishes that the pair still contributes what
    a human was shown.
    """
    return (
        publication.candidate_sha == generation.candidate_sha
        and publication.base_sha == generation.base_sha
        and publication.additions == generation.additions
        and publication.threshold == generation.threshold
    )


def _refused(
    context: _LateContext,
    signal: _LateContentSignal,
    said: str,
    *,
    still_waiting: bool = True,
) -> _LateContentSettlement:
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
    return _LateContentSettlement(
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


def _consume(context: _LateContext, signal: _LateContentSignal) -> None:
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
