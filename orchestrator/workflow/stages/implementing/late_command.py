# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Select trusted authorization-park replies and retain their consumption boundary.

The last trusted human reply supplies the decision. Stage comments may be
read through after it without consuming intervening human guidance.
"""
from __future__ import annotations

from dataclasses import dataclass

from github.Issue import Issue

from orchestrator.github.client import GitHubClient
from orchestrator.github.comments import carries_own_marker, filter_trusted
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.late_split import (
    payloads as _payloads,
)
from orchestrator.workflow.stages.implementing import (
    late_authorship as _authorship,
    late_command_reading as _late_command_reading,
    late_gate_models as _late_gate_models,
    parked_replies as _parked_replies,
    state as _state,
)

# The park an adjudicated candidate takes when nothing on the record says a
# human agreed to publish it. Its own reason because its recovery is neither a
# session retry nor another reading: what it is waiting for is a person, and
# every tick until one arrives measures the same pair to the same answer.
#
# Spelled on this owner because this is where it is READ -- the reply reading
# is the only thing that turns on it -- and published for the two seams that
# route a parked tick back to the gate: the door that asks whether one is
# standing before it believes its own record, and the recovery that brings a
# standing park to that door on a tick with no run to dispose.
PARK_UNAUTHORIZED_EXEMPTION = "late_unauthorized_exemption"


@dataclass(frozen=True)
class _Answer:
    """The last word a human has written on a standing authorization park.

    Only the LAST fresh reply is read, and that is the whole of the rule.
    Every earlier one has been superseded by it: an operator who names one
    commit and then another has decided about the second, and one who writes
    guidance and then the command has changed their mind toward publishing.
    Reading the batch as a set instead is what poisons a park -- a reply that
    matches nothing is never consumed on the seams that publish onto a pull
    request the remote already carries, so it would stand in every later batch
    and refuse a correct command forever.

    `named` is the commit that reply authorizes, whole or EMPTY. Empty is a
    command nobody could act on -- an abbreviation, or an argument that is not
    an object id at all, since nothing in this domain abbreviates -- and it is
    carried rather than dropped: it can never equal the candidate, so it takes
    the refusal road and the human gets the sentence and the command that
    would have worked. `comment_id` is the reply itself, which is the address
    a recorded authorization is attributable to.

    `watermark` is how far the READING got, which is a different fact from
    either: the furthest comment this owner actually looked at, ours and
    untrusted ones included. It travels because it is what an answer may
    consume and no more. A tick that read the tip of the thread and then
    consumed past whatever the tip has become would swallow a retraction
    posted in between -- unread, unanswered, and gone for good, while the
    authorization it was retracting published. Consumed to what was read, the
    retraction is still there for the next poll.
    """

    named: str
    comment_id: int
    watermark: int

    def read_through(self, gate: _late_gate_models._Gate, said: int) -> int:
        """How far a tick that answered this reply may say the thread is read.

        Up from what this reading reached, over OUR OWN comments and no
        further. A road that answers a command it may not act on posts its
        sentence into the window between the two, and ids ascend, so that
        sentence lands above the reply it answers and has to be consumed --
        left behind, the next poll reads the orchestrator's own words as
        somebody's fresh guidance and resumes a developer against them.

        Reached by its id alone, though, it would pay for that with the one
        thing this park exists to collect. An operator who reads the notice
        and posts the corrected command in that same window has their answer
        land BELOW ours, and a watermark set to ours consumes it unread -- so
        the park goes on standing over a command nobody will ever see again.
        So the first comment that is NOT ours ends the walk, whatever it says:
        the watermark is the only thing that can promise its author the next
        poll.

        Every id the walk passes is one nobody has to see again -- this tick
        wrote it, or an earlier one did and this reading examined it. A tick
        that posted nothing walks nothing and answers with what it read, which
        costs no request and is every other road here.

        The pinned comment is named by its ID, for the reason the reading
        behind this names it: told to find it by its marker instead, the read
        hides every comment that merely QUOTES that marker -- so a reply
        somebody pasted a payload into would be walked straight over and
        consumed unread.
        """
        if said <= self.watermark:
            return self.watermark
        reached = self.watermark
        for landed in gate.gh.comments_after(
            gate.issue,
            self.watermark,
            state_comment_id=gate.state.comment_id,
        ):
            identified = _payloads.as_identity(getattr(landed, _late_command_reading._COMMENT_ID, 0))
            if identified is None or identified > said:
                break
            if not _late_command_reading._ours(landed, gate.state):
                break
            reached = identified
        return reached


@dataclass(frozen=True)
class _Reading:
    """One look at a standing park's thread, and all three answers it holds.

    Spelled as one record because the three come from ONE fetch and mean
    nothing apart from each other. `answer` is the reply to act on, `spoke`
    says whether any fresh trusted word of somebody else's is there at all --
    an already-answered run-grant command is none -- and `furthest` is how far
    this look got -- ours, untrusted comments, and that command included,
    since what a watermark records is what has been LOOKED at.

    `answer` and `spoke` are deliberately not one field: a None answer is two
    different threads. Nothing new on it is a park with nothing to do but
    stand; a last word that is guidance belongs to the ordinary resume. Read
    from two fetches instead, a command landing between them is classified as
    guidance and consumed by a road that cannot act on it.

    `furthest` is what an answer may consume and no more. A tick that read the
    tip of the thread and then consumed past whatever the tip has become would
    swallow a reply posted in between -- a retraction of the very command
    being acted on included -- unread, unanswered and gone for good.
    """

    answer: _Answer | None
    spoke: bool
    furthest: int


def _read_the_park(
    gh: GitHubClient, issue: Issue, state: PinnedState,
) -> _Answer | None:
    """The command a human has written on this park, or None if none has.

    None for everything else, and each exclusion is its own answer. An issue
    parked for another reason is not this park's to end; a thread with nothing
    new on it is a human who has not replied yet; an outsider's comment is not
    in the reading at all, so nothing they post can authorize anything; a
    comment the orchestrator itself wrote is nobody's decision, and the park
    notice spells the command out ready to copy, so our own sentences are
    exactly what a reader matching on that syntax would mistake for one; and a
    last word that is not the whole command is guidance, which belongs to the
    ordinary resume that feeds it to the developer rather than to a bypass
    taken behind their back.

    A command nobody could ACT on is not one of those, and it is answered
    rather than dropped: the argument is held to a whole object id, and one
    that is not gets the same sentence a command for another commit gets. Read
    as guidance instead, an operator who abbreviated would be left with a
    silent park and a thread that never said why.

    The LAST fresh reply decides, because it is the last thing the human said.
    Guidance written after a command outranks it -- the safe reading of
    somebody who asked to publish and then asked for a change is the one that
    publishes nothing -- and a command written after guidance is the decision
    that replaced it. Read as a set instead, one stale reply would refuse
    every command posted behind it for as long as the park stood.

    Which makes naming the pinned comment by its ID part of that rule rather
    than a detail of the fetch. A read that has to find it by its marker
    instead treats every comment merely QUOTING that marker as the record --
    an operator pasting a payload back to ask about it, a retraction written
    under one -- and a reply hidden from this reading is a reply whose author
    never spoke. The stale command beneath it would become the last word and
    publish on consent that had been withdrawn.
    """
    if state.get(_state._PARK_REASON) != PARK_UNAUTHORIZED_EXEMPTION:
        return None
    if not state.get(_state._AWAITING_HUMAN):
        return None
    return _reads_the_thread(gh, issue, state).answer


def _reads_the_thread(
    gh: GitHubClient, issue: Issue, state: PinnedState,
) -> _Reading:
    """Everything one look at this park's thread can say, said at once.

    ONE fetch, because the two questions behind it decide opposite things and
    a road that asked them separately would answer from two different threads.
    Between a read finding no command and a second read finding somebody
    spoke, the command itself can land: the tick then classifies a thread
    whose last word IS the command as guidance, hands it to the ordinary
    resume, and the resume consumes it past the watermark and pays for a
    developer -- leaving the park standing over a decision nobody can read
    again. Answered from one snapshot, every classification is one some real
    state of the thread supports.

    The door above is the caller's. This owner answers what the thread says;
    whether anybody is waiting behind it is a fact about the record.

    A bare `/orchestrator add-agent-runs` is no word on this park, which is
    the one cut this reading shares with the frozen resume batch
    (`parked_replies`). It is a control the run-limit hold has answered, and a
    grant over a reply it could not consume leaves it unread -- still there
    when a later park like this one is taken. Read as a last word, it hides a
    command written just above it and hands the tick to a resume that drops
    the grant and delivers the command as prose; read as somebody speaking, it
    hands the tick to a resume with nothing to deliver. Everything else is
    read as before: our own comments by the id ledger alone, so a marker
    somebody pasted is still a reply that demotes the command under it.
    """
    examined = gh.comments_after(
        issue,
        state.get(_state._LAST_ACTION_COMMENT_ID),
        state_comment_id=state.comment_id,
    )
    replies = _parked_replies._answering(
        reply for reply in filter_trusted(examined) if not _late_command_reading._ours(reply, state)
    )
    furthest = _late_command_reading._furthest_read(
        examined, _payloads.as_identity(
            state.get(_state._LAST_ACTION_COMMENT_ID),
        ) or 0,
    )
    if not replies:
        return _Reading(answer=None, spoke=False, furthest=furthest)
    last = replies[-1]
    identified = _payloads.as_identity(getattr(last, _late_command_reading._COMMENT_ID, 0))
    if not _late_command_reading._is_the_command(last) or identified is None:
        return _Reading(answer=None, spoke=True, furthest=furthest)
    return _Reading(
        answer=_Answer(
            named=_late_command_reading._names(last),
            comment_id=identified,
            watermark=max(furthest, identified),
        ),
        spoke=True,
        furthest=furthest,
    )


def _reserved_for_the_park(reply, state: PinnedState) -> bool:
    """Whether this reply is a command only this park's own road may consume.

    The generic resume reads the thread again after the road that classifies
    this park has handed the tick back, and everything between the two reads
    is time an operator can write in. A command landing there is in the
    resume's batch and in nobody else's: it goes to a developer as prose and
    the watermark moves past it, so the park goes on standing over a decision
    nothing can ever read again -- and a second developer is paid for over an
    implementation that is committed already.

    Bounding the batch by what the classifying road READ would not close it,
    since the same window reopens between that bound and the next poll. What
    closes it is whose reply this is: while the park stands, the command
    belongs to the road that acts on it, and no other road may spend it.
    Guidance beside it is consumed and fed to the developer exactly as the
    park's own notice promises, and comment ids ascend, so a command left
    behind is one the next poll reads as the last fresh word.

    What the caller owes it is the whole TICK rather than one reply held out
    of a batch. A watermark is one number and the resume is not the last thing
    to move it: the run it starts parks, and that park stamps the thread read
    to the notice it posts, which lands above the command and takes it. So a
    batch ending in one of these is deferred entire, unconsumed, to the poll
    that can act on it.

    Whether it is the LAST fresh reply is the caller's to ask, and it has to.
    A command with guidance written over it has been replaced -- the safe
    reading of somebody who asked to publish and then asked for a change is
    the one that publishes nothing, which is this owner's own reading rule --
    so that batch is an ordinary resume rather than a tick to defer.

    Asked only while the park is standing. On any other issue the command is
    prose like anything else, and a reply nothing may ever consume is one
    that would sit in every later batch forever.
    """
    if state.get(_state._PARK_REASON) != PARK_UNAUTHORIZED_EXEMPTION:
        return False
    if not state.get(_state._AWAITING_HUMAN):
        return False
    return _late_command_reading._is_the_command(reply)


def _already_said(gate: _late_gate_models._Gate, marker: str) -> bool:
    """Whether this thread already carries OUR sentence under this receipt.

    Both halves of the receipt are asked -- the scoped marker and the author
    -- since an HTML comment is plain text anybody may paste, and read from
    anybody it would silence a sentence a human is owed.

    Which is the direction to fail in for THIS question and the wrong one for
    attribution, so the two are deliberately not the same read. Silencing a
    sentence costs a poll; claiming a comment costs whatever its author said.

    The pinned record is not in the reading, and leaving it there is how this
    silences the very sentences it exists to say once. A receipt is a FIELD on
    that record before it is a sentence on a thread, and the record is written
    as its own unescaped payload wherever escaping it would put the comment
    past GitHub's ceiling -- so on exactly those issues the receipt appears
    verbatim in the pinned comment's body, under our own login. Read there,
    every sentence a dying tick recorded and never said reads as one already
    said: the park notice a human is waiting for is never posted, and a
    command this park may not act on is consumed with no answer at all.
    """
    return carries_own_marker(
        _authorship._thread_beside_the_record(
            gate.issue, gate.state.comment_id,
        ),
        marker,
        bot_login=getattr(gate.gh, "_bot_login", None),
    )
