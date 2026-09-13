# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The park an adjudicated candidate with nobody behind it waits on.

What an oversized reading is owed where `late_authority` beside this says the
exemption naming the candidate has no operator authorization standing behind
it -- the record an older binary wrote, where a `single` verdict recorded an
exemption on its own, and the record a hand edit or a half-written crash
leaves. It is a HOLD rather than a route back to `workflow:decomposing`, and
that difference is the whole of what the compatibility is worth: the change
has already been ruled one change, so sending it back would pay for a second
adjudicator over an answered question and risk a `split` cutting children out
of work somebody decided ships whole. What is missing is a person, so the park
asks for one.

The ordinary cumulative reading is what reaches this owner, and that is the
whole of the contract: the generation handed in is the pair the gate froze and
the count it took, so the terms an authorization is recorded on are this
tick's rather than a number read back off the pinned comment. It also means
every way a reading can fail is answered where it always was -- the
measurement park, the typed failure on both sinks, the bounded quiet retry --
rather than a second time here. An issue already standing behind the park
comes back down the same road, which `late_recovery` drives on every poll.

The COUNT is deliberately not made durable. A generation carrying a reading
past its ceiling is exactly what this workflow means by an adjudication in
flight -- the dispatcher restores `workflow:decomposing` over one before any
stage sees the issue, the coordinator owns every later tick, and a fresh
adjudicator is paid for -- so a park that recorded one would be relabelled out
from under itself on the next poll and nothing could ever answer it. What
stays on the comment is the pair the freeze already recorded, and the reading
is re-taken by the tick that acts, which is the tick an authorization's terms
have to be written from anyway.

Nothing is deleted, migrated, or repaired to take it. The exemption, the
identity beside it, the approval naming the commit a push is owed for, and
every other field are left exactly as found: the record is what an
authorization would be checked against, and a park that tidied the pinned
comment on the way would destroy the evidence it exists to ask about.

What ends it is a trusted whole-comment `/orchestrator authorize-oversized
<commit>` naming the parked candidate, which `late_command` reads. Acted on
HERE rather than at the gate's door because this is the only place holding a
reading: an operator authorizes a change of THIS size against THAT ceiling,
and the terms of the record are the pair this call froze, the additions it
counted, and the ceiling it counted them against.

Every notice is worded on the side of publication the park was taken on,
because what a reply that is NOT the command is worth differs there. Before a
pull request exists the ordinary resume is still in front of the issue, so
prose reaches the developer and the sentence offers it. Past one it does not:
the debt reconciliation that brings a parked issue back to the gate stops the
tick ahead of the stage handler on every poll, so nothing would carry a
human's words to an agent, and a notice promising otherwise would have
somebody writing into a thread nothing reads.
"""
from __future__ import annotations

import logging
from types import MappingProxyType

from orchestrator import config
from orchestrator.git.measurement import fingerprint as _fingerprint
from orchestrator.workflow.engine import (
    comments as _comments,
    guards as _guards,
)
from orchestrator.workflow.late_split import (
    overrides as _overrides,
    payloads as _payloads,
    state as _late_state,
)
from orchestrator.workflow.late_split.models import LateGeneration
from orchestrator.workflow.stages.implementing import (
    late_command as _command,
    late_records as _records,
    state as _state,
)

log = logging.getLogger("orchestrator.workflow")

# The receipt each sentence this owner writes is stamped with, scoped to the
# one thing it is the answer to: the candidate a park was taken over, and the
# reply a refusal was written for. HTML comments, so both are invisible in the
# rendered thread.
#
# Each is what keeps a second poll from saying the same thing to the same
# people twice, because neither the sentence nor its consequence can be made
# one operation with the write that records it. Recorded BEFORE the sentence
# carrying it goes out, so the record says a sentence is outstanding and the
# thread says whether it landed: a receipt the thread carries is a sentence
# that was said, and one it carries nowhere is one still owed.
#
# Both halves of the thread's answer are asked -- the receipt and the author
# -- and that is the safe direction for SILENCING a sentence and the wrong one
# for claiming a comment. These strings are public text, deterministic from an
# issue and a commit, and recording one publishes it, since the record is
# itself a comment; the login beside it may be the operator's own. So read as
# proof of authorship a retraction written under a quoted receipt would be
# taken for one of ours and deleted from the reading -- publishing the
# authorization beneath it on consent withdrawn. Silencing a sentence costs a
# poll; claiming a comment costs whatever its author said. Attribution is
# `late_recovery`'s, on the one thing that can bear it: a secret it commits to
# by DIGEST before the seam is entered, stamped on every sentence that call
# posts -- these among them, since both are worded inside it.
_RECEIPTS = MappingProxyType({
    "parked": (
        "<!--orchestrator-unauthorized-exemption-parked:"
        "issue={issue}:candidate={scope}-->"
    ),
    "refused": (
        "<!--orchestrator-unauthorized-exemption-refused:"
        "issue={issue}:read={scope}-->"
    ),
})


def _receipt(gate: _records._Gate, said: str, scope) -> str:
    """The receipt one sentence of ours is stamped with, scoped to its subject."""
    return _RECEIPTS[said].format(issue=gate.issue.number, scope=scope)

# What every notice here ends on, worded on the side of publication the park
# was taken on. Before there is a pull request the ordinary resume is still in
# front of this issue, so prose reaches the developer and the sentence says so.
# Past one it is not: the debt reconciliation that brings a parked issue back
# to this gate stops the tick ahead of the stage handler on every poll, so
# nothing on that road would ever carry a human's words to an agent -- and a
# notice promising otherwise would have somebody writing into a thread nothing
# reads.
_HOW_TO_DECIDE = (
    "Post `/orchestrator authorize-oversized {candidate}` as the entire "
    "comment -- the whole comment and the commit spelled in full -- to "
    "publish it as it stands, or reply with the change to make and the "
    "developer is resumed against it."
)

_HOW_TO_DECIDE_PUBLISHED = (
    "Post `/orchestrator authorize-oversized {candidate}` as the entire "
    "comment -- the whole comment and the commit spelled in full -- and it "
    "joins the pull request. That command is the only reply this stage reads "
    "while the park stands: nothing else on the issue runs until the commit "
    "is published, so prose here reaches no agent."
)

_WRONG_CANDIDATE = (
    "{mentions} that command does not name the commit this issue is waiting "
    "on -- an abbreviation is refused too, since nothing here ever writes "
    "one -- so nothing was published and nothing was recorded. The candidate "
    "waiting on a decision is `{candidate}`. "
)

_PARK_NOTICE = (
    "{mentions} this issue's committed implementation adds {additions} lines "
    "against a ceiling of {threshold}, and the record that would let it past "
    "names the commit alone. It was written before an operator's own "
    "authorization was required at publication, so nothing here can show who "
    "agreed that `{candidate}` publishes as one change -- and an adjudicator "
    "answering that it should is exactly what the ceiling is there to catch. "
    "Nothing was pushed, nothing was discarded, and nothing on the record was "
    "removed: the commit is still in the worktree and the adjudication that "
    "accepted it is still recorded. "
)


def _authorizes_the_park(
    gate: _records._Gate, generation: LateGeneration,
) -> bool:
    """Whether a human has told this oversized candidate to publish as it is.

    The one answer an adjudicated candidate with nobody behind it can get, and
    the whole of what a tick does with it. False is held either way -- the
    park taken or re-taken, or a reply answered and consumed -- and True is a
    candidate the caller publishes exactly as it publishes one the reading let
    through.

    Reached from the verdict the ordinary reading settles, which is what makes
    the terms this owner records the gate's own: an operator authorizes a
    change of THIS size against THAT ceiling, and the pair, the additions and
    the ceiling on the generation handed in are the ones that reading took.
    """
    answer = _command._read_the_park(gate.gh, gate.issue, gate.state)
    if answer is None:
        return not _parked_for_authorization(gate, generation)
    if answer.named != generation.candidate_sha:
        return not _refused(gate, generation, answer)
    return _recorded_authorization(gate, generation, answer)


def _parked_for_authorization(
    gate: _records._Gate, generation: LateGeneration,
) -> bool:
    """Hold an adjudicated candidate nobody has authorized, and say so once.

    The answer an oversized reading gets where an exemption names the commit
    and no authorization does. It is a hold rather than a route because the
    question the adjudication answers has already been answered: the change
    was ruled one change, and sending it back would pay for a second
    adjudicator over that same question and risk a `split` cutting children
    out of work somebody already decided ships whole. What is missing is a
    person, so this asks for one.

    The COUNT is deliberately not made durable, and that is the difference
    between a park and an adjudication. A generation carrying a reading past
    its ceiling is exactly what this workflow means by "an adjudication in
    flight": the dispatcher restores `workflow:decomposing` over one, the
    coordinator owns every later tick of it, and a fresh adjudicator is paid
    for. A candidate waiting on an operator is none of those, so what stays on
    the comment is the pair the freeze already recorded and nothing else --
    the reading is re-taken on the tick that acts, which is the tick whose
    terms an authorization has to be written from anyway.

    Said ONCE per pair. The seams that publish onto a pull request the remote
    already carries re-enter this gate on every poll behind the park, so
    repeating the notice would mention the same people once a poll about a
    decision they have already been asked for -- and worse than that, over a
    watermark that has moved past the command one of them wrote in between,
    which throws the decision away.

    Which is why the park goes DOWN before the sentence goes out, carrying the
    receipt that sentence is about to be stamped with. Past that write the
    park alone answers "already said", and the receipt beside it is what says
    a tick died somewhere in between -- which side of the post it died on
    being the thread's question to answer, not the record's.

    The order bounds the damage either way round. A notice said and never
    recorded is suppressed by the park that went down first, and again by the
    thread carrying the receipt; a park recorded and never announced carries a
    receipt no comment does, so it is announced.

    Nothing is deleted. The exemption, the identity beside it, the approval
    that names the commit a push is owed for, and every other field stay
    exactly as they were found -- the record is what an authorization would be
    checked against, and a park that repaired the pinned comment on the way
    would destroy the evidence it exists to ask about.
    """
    receipt = _receipt(gate, "parked", generation.candidate_sha)
    standing = _stands_over(gate, generation)
    if standing and not _owes_the_notice(gate, receipt):
        _recorded_as_said(gate)
        return True
    log.warning(
        "issue=#%d exempts candidate %s on a record no operator "
        "authorization stands behind; holding %d lines against a ceiling of "
        "%d rather than publishing a bypass nobody granted",
        gate.issue.number, generation.candidate_sha,
        generation.additions, generation.threshold,
    )
    _held(gate, receipt)
    _guards._park_awaiting_human(
        gate.gh, gate.issue, gate.state,
        _PARK_NOTICE.format(
            mentions=config.HITL_MENTIONS,
            additions=generation.additions,
            threshold=generation.threshold,
            candidate=generation.candidate_sha,
        ) + _decided_by(gate, generation.candidate_sha) + f"\n\n{receipt}",
        reason=_command.PARK_UNAUTHORIZED_EXEMPTION,
    )
    gate.state.set(_state._PARK_REASON, _command.PARK_UNAUTHORIZED_EXEMPTION)
    gate.state.set(_state._HELD_RECEIPT, None)
    gate.gh.write_pinned_state(gate.issue, gate.state)
    return True


def _recorded_as_said(gate: _records._Gate) -> None:
    """Catch the record up with a thread that already carries our sentence.

    An outstanding receipt says a tick died between recording a sentence and
    recording having said it. Reaching here is the thread having answered
    which side of the post that was -- everything this owner owes has been
    said -- so the record is brought into line with it.

    Left standing instead, the receipt would have every later poll of a park
    nobody has answered read the whole thread again to reach the same
    conclusion, and would go on saying something is outstanding when nothing
    is. Dropping it costs one write, once.

    Nothing is owed at this point whichever sentence the receipt was for. The
    park's own notice would have taken the announcing road rather than this
    one, and the refusal's at-most-once guard asks the thread for its own
    scoped receipt rather than this field.
    """
    if gate.state.get(_state._HELD_RECEIPT) is None:
        return
    gate.state.set(_state._HELD_RECEIPT, None)
    gate.gh.write_pinned_state(gate.issue, gate.state)


def _owes_the_notice(gate: _records._Gate, receipt: str) -> bool:
    """Whether a sentence this park recorded is still owed to the thread.

    Two questions, and the record answers only the first. A park carrying no
    receipt has nothing outstanding -- the write past the post dropped it --
    so the ordinary quiet poll is answered without a request. A park still
    carrying one is a tick that died somewhere between recording the sentence
    and recording having said it, and WHICH side of the post it died on is a
    question only the thread can answer.

    So the thread is asked, on the same terms and for the same reason the
    refusal beside this one asks it: the receipt AND the author, which is the
    safe direction to fail in for a question about SILENCING a sentence.
    Read from anybody, a receipt somebody pasted would silence a notice a
    human is owed; read this way, the worst a reviewer sharing this token can
    do by quoting our notice back is cost a poll.

    What may never be built on THIS evidence is the opposite claim -- that
    some comment on the thread is OURS. The receipt is deterministic from the
    issue and the candidate, and recording it publishes it: the record is
    itself a comment, so the string is readable before the sentence it names
    exists, by the operator whose consent this park collects and from a login
    they may share with us. Claimed on that basis, a retraction they wrote
    under it would be deleted from every later reading and the authorization
    beneath it would become the last word and publish on consent withdrawn.

    Nothing here writes the id ledger that says a comment is ours. The one
    attribution `late_recovery` does make rests on a SECRET, minted per
    handoff into the publication seam and recorded there by its digest alone
    -- which is the claim this receipt cannot support and is not asked for.
    Every sentence this owner words goes out from inside that seam call, so
    the secret is on them too, beside the receipt this read is about.
    """
    if gate.state.get(_state._HELD_RECEIPT) != receipt:
        return False
    return not _command._already_said(gate, receipt)


def _held(gate: _records._Gate, receipt: str) -> None:
    """Make this park, and the receipt it is about to say, durable first.

    Both halves go down in one write and both are the same precaution. The
    park is what a restarted tick reads to know somebody is already waiting
    behind this candidate; the receipt is what tells a later poll that the
    sentence saying so never got out, and it can only do that if it was
    written down before the comment carrying it existed.

    The park's flags are set here rather than left to the guard below, because
    the guard sets them AFTER it posts -- which is the window this write
    exists to close.
    """
    gate.state.set(_state._AWAITING_HUMAN, True)
    gate.state.set(_state._PARK_REASON, _command.PARK_UNAUTHORIZED_EXEMPTION)
    gate.state.set(_state._HELD_RECEIPT, receipt)
    gate.gh.write_pinned_state(gate.issue, gate.state)


def _decided_by(gate: _records._Gate, candidate_sha: str) -> str:
    """What every notice here asks for, on the side of publication it is on.

    Both halves say the command and spell it out ready to copy; they differ
    about the OTHER reply, and the difference is what is actually true rather
    than a matter of tone.

    Before there is a pull request the ordinary resume is still in front of
    this issue: a reply that is not the command reaches the road that feeds
    guidance to the developer, so the notice offers it. Past one it does not. A parked issue on the stages that publish
    onto a pull request the remote already carries reaches this gate through
    the debt reconciliation, which stops the tick ahead of the stage handler
    on every poll -- so nothing there would carry a human's words to an agent,
    and a notice offering it would have somebody writing into a thread nothing
    reads.

    Read off the entry this call was taken on, which is the same fact the
    measurement park's own two wordings are chosen by.
    """
    asked = _HOW_TO_DECIDE if gate.entry is None else _HOW_TO_DECIDE_PUBLISHED
    return asked.format(candidate=candidate_sha)


def _stands_over(
    gate: _records._Gate, generation: LateGeneration,
) -> bool:
    """Whether this park is already up, over this very candidate.

    Both halves of the park are required. The flag and the reason say somebody
    is waiting behind this question rather than behind a timeout, a dirty
    tree, or a reading nobody could take; the recorded candidate says they are
    waiting behind THIS one.

    Read off the durable record, which the freeze ahead of this call has
    already written the pair onto -- so what is compared is the commit the
    park is about rather than a count nothing persists. A park a resumed
    developer's fresh commit has moved past never reaches this owner at all:
    the road in is an exemption naming the candidate in hand, and a hold
    routes the issue to the adjudication, which clears whatever park it
    supersedes on the way.
    """
    if gate.state.get(_state._PARK_REASON) != _command.PARK_UNAUTHORIZED_EXEMPTION:
        return False
    if not gate.state.get(_state._AWAITING_HUMAN):
        return False
    recorded = _late_state.read_late_generation(gate.state)
    return recorded.candidate_sha == generation.candidate_sha


def _recorded_authorization(
    gate: _records._Gate, generation: LateGeneration, answer: _command._Answer,
) -> bool:
    """Record what an operator authorized, take the park off, consume the reply.

    The terms are this gate's OWN reading and nothing the record already
    carried: the pair it froze, the additions it counted, the ceiling they
    were counted against, and the digest recomputed between that pair here --
    so what goes down is a change of this size against this ceiling, which is
    the claim an authorization has to be answerable as.

    A contribution this host cannot fingerprint records nothing and leaves the
    park and the command exactly where they are. Nothing about that is the
    operator's doing, so the next tick takes the same reading again rather
    than asking somebody to authorize the same change twice.

    The record, the park coming down, the reply being consumed, and any
    sentence this park still owed the thread ride ONE write, for the reason
    every other authorization does: the record without the park cleared says a
    human is owed a question they have answered, the park without the record
    sends the candidate straight back to it, the record without the watermark
    leaves the same comment able to authorize whatever is parked next -- and
    an outstanding receipt left behind is a notice a later poll would say onto
    an issue nobody is waiting on any more.
    """
    contribution = _fingerprint._fingerprint_contribution(
        gate.worktree, generation.base_sha, generation.candidate_sha,
    )
    if not contribution.is_fingerprinted:
        log.warning(
            "issue=#%d cannot fingerprint what the authorized candidate %s "
            "contributes (%s); leaving the authorization unread and the "
            "candidate parked",
            gate.issue.number, generation.candidate_sha, contribution.failure,
        )
        return False
    _overrides.record_publication_override(
        gate.state,
        _overrides.LateOversizedPublication(
            candidate_sha=contribution.candidate_sha,
            base_sha=contribution.base_sha,
            fingerprint=contribution.digest,
            additions=generation.additions,
            threshold=generation.threshold,
            comment_id=answer.comment_id,
        ),
    )
    log.info(
        "issue=#%d had its adjudicated candidate %s authorized to publish "
        "unsplit by a trusted operator in comment %d; recording the terms it "
        "was measured on and letting it past the gate",
        gate.issue.number, generation.candidate_sha, answer.comment_id,
    )
    _consumed(gate, answer)
    gate.state.set(_state._AWAITING_HUMAN, False)
    gate.state.set(_state._PARK_REASON, None)
    gate.state.set(_state._HELD_RECEIPT, None)
    gate.gh.write_pinned_state(gate.issue, gate.state)
    return True


def _refused(
    gate: _records._Gate, generation: LateGeneration, answer: _command._Answer,
) -> bool:
    """Say why this command changed nothing, and leave the park standing.

    A command naming a commit this issue is not holding is the ordinary way an
    authorization fails: an id copied out of a notice about work a resumed
    developer has since moved past. A bypass may license exactly what a human
    looked at, so it authorizes nothing -- and the human is owed the reason
    and the command that would have worked.

    Consumed on the way out, and that consumption is the point rather than a
    tidiness. The seams that publish onto a pull request the remote already
    carries reach this gate through a debt reconciliation that stops before
    their own handler, so nothing else on those issues ever moves the
    watermark: a reply left unconsumed would stand in every later batch and
    the correct command behind it would never be the last word.

    Consumed past the SENTENCE rather than past the reply, since the sentence
    is posted first and comment ids ascend. Left between the two, the answer
    this tick just wrote is what the next tick's readers find past the
    watermark -- and a resume reads whatever is there as a human's fresh word,
    so the developer would be resumed against the orchestrator's own refusal.

    The sentence and the write that consumes it are two operations, so the
    sentence carries a receipt scoped to the reply it answers and the thread
    is asked for that receipt before it is written a second time -- the same
    at-most-once discipline every other answer in this repository has.

    The receipt is RECORDED before the sentence carrying it goes out, so a
    tick dying in between leaves the record saying which sentence it was in
    the middle of. Read off a body or an author, that record could say
    nothing: a reviewer answering the refusal quotes the receipt back, and
    under a token shared with a human their reply carries our marker and our
    login both. Recorded first, the receipt says something neither can -- a
    comment carrying it exists only because we posted one. It is dropped by
    the write that consumes, so it stands for exactly as long as this tick
    owes the record a sentence.
    """
    log.info(
        "issue=#%d was told to authorize %s and is holding %s; answering the "
        "command and leaving the park where it stands",
        gate.issue.number, answer.named, generation.candidate_sha,
    )
    marker = _receipt(gate, "refused", answer.comment_id)
    said = 0
    if not _command._already_said(gate, marker):
        gate.state.set(_state._HELD_RECEIPT, marker)
        gate.gh.write_pinned_state(gate.issue, gate.state)
        sentence = _WRONG_CANDIDATE.format(
            mentions=config.HITL_MENTIONS,
            candidate=generation.candidate_sha,
        ) + _decided_by(gate, generation.candidate_sha)
        posted = _comments._post_issue_comment(
            gate.gh, gate.issue, gate.state, f"{sentence}\n\n{marker}",
        )
        # The id the consumption below needs, and the only thing that can
        # supply it: ids ascend, so this sentence lands above the reply it
        # answers, and a watermark left below it hands our own words to the
        # next poll as somebody's fresh guidance. Zero where the thread
        # already carried our receipt -- there is no new comment, and the one
        # there was in the reading that found it.
        said = _payloads.as_identity(getattr(posted, "id", 0)) or 0
    _consumed(gate, answer, said)
    gate.state.set(_state._HELD_RECEIPT, None)
    gate.gh.write_pinned_state(gate.issue, gate.state)
    return True


def _consumed(
    gate: _records._Gate, answer: _command._Answer, said: int = 0,
) -> None:
    """Record what this tick read as read, and its own answer with it.

    Staged rather than written, so it lands with whatever else the caller is
    recording or not at all: a watermark moved without the answer beside it
    would drop a command nobody acted on.

    It starts at the furthest comment the READING got to, which is what the
    reader hands back rather than a fresh look at the thread: a tick that
    consumed past whatever the tip has become since would swallow a reply
    posted in the meantime -- a retraction of the very command being acted on
    is the case that matters -- unread, unanswered and gone for good. Consumed
    to what was read, that reply is still there for the next poll, which is
    the most a reading taken before it can honestly offer.

    Then it reaches the answer this tick POSTED, and `read_through` beside the
    reading decides how far that is: over our own comments and no further,
    since a sentence of ours left unconsumed is read on the next poll as
    guidance nobody wrote, while a watermark jumped straight to its id would
    swallow the corrected command an operator posted in the same window.
    """
    gate.state.set(
        _state._LAST_ACTION_COMMENT_ID, answer.read_through(gate, said),
    )
