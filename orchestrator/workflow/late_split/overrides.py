# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The one oversized candidate an operator authorized to publish as it stands.

An oversized candidate has two ways past the size gate, and both are a
human's. The first is a settlement somebody authorized, whose commit the
`exemption` owner beside this records; an adjudicator ruling the change one
coherent whole is not itself one of them, since a `single` verdict parks for
that decision rather than making it. The second is this record. An operator
who has read the change can say,
in a comment on the issue, that it publishes unsplit -- and that gesture has
to outlive the process that read it, the generation it was made under, and the
tick that would act on it, or the gate measures the same candidate past the
same ceiling on the next poll and asks the same question again.

This record is that authorization made durable, and every term of it follows
from what it IS: a bypass of the one gate that stops unreviewed bulk reaching
a pull request. A bypass may license exactly what a human looked at and
nothing beside it, so the record is bound to the candidate rather than
declared over the issue -- a flag would authorize whatever the worktree ends
on next, and a commit alone would authorize whatever that commit turns out to
contribute once a base moved under it.

So it names the whole of what was authorized. The exact candidate SHA, which
is the commit a human read. The frozen base it was read over, since the same
commit contributes something else over another one. The canonical digest of
the contribution between that pair and the scheme the digest was taken under,
which together are what says the change on the branch is still the change that
was authorized. And the measurement that made the candidate oversized in the
first place: the additions counted, and the ceiling they were counted against.

Those last two are recorded HERE rather than read off the generation beside
them, and that is the point of them. The generation is cleared when the cycle
that earned this record ends, and the ceiling is a knob an operator retunes --
so a record that pointed at either would answer differently later, about a
decision that was made once. What a human authorized is a change of THIS size
against THAT ceiling, and a record carrying both is one a later reader can
still hold the authorization to.

The comment is what makes the authorization attributable. A bypass of the size
gate is licensed by a gesture somebody made in a place anybody can go and
read, so the record names that comment by its id: a caller offering an
authorization it cannot locate is offering an unattributable field on a pinned
comment, which is the one thing this record may not become. Whether the author
was trusted is proved before the write rather than stored beside it -- the
allowlist is an operator's own and moves, and the durable half of the evidence
is which comment was acted on.

Read fail-closed, whole or not at all, and more strictly than the exemption
beside it. There, the exact-SHA field is a claim that stands alone and the
identity is what a damaged member costs. Here every member IS the
authorization: a field that is missing, one that is not the shape its field
takes, a digest taken under a scheme this build does not compute, a comment id
that is not an identity, and a measurement that is not one -- including a
record whose additions are not strictly past its own threshold, which
describes a candidate the gate would have published untouched -- each read
back as no authorization at all. What that costs is a measurement, which is
the answer a damaged bypass has to give.

The write refuses the same values rather than recording them, for the reason
every other late writer does: a caller handed a term it cannot vouch for has
an authorization in hand and nowhere to put it, and recording one would move
the failure onto a reader whose only move is to let unmeasured work publish.
The whole group goes down in one statement and replaces whatever stood there,
so a record is never half about one candidate and half about another.

The keys sit outside `LATE_STATE_KEYS` for the reason the exemption's do: this
is what a generation is cleared AGAINST, and a clear that took it would send
the authorized candidate back into the adjudication a human already answered.
Everything else on the pinned comment is left exactly as found -- the fields
this owner names and no others -- so an unknown field, and the exemption
group beside it, are preserved verbatim by both the write and the clear.

What the record does not do is publish anything. It is durable evidence, and
what a candidate publishes under is decided where publications are.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from types import MappingProxyType

from orchestrator.git.measurement.models import FINGERPRINT_FORMAT
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.late_split import formats as _formats, payloads as _payloads

# The commit an operator authorized and the base it was authorized over.
# Spelled here because this is the record's owner, and deliberately not among
# the keys `clear_late_generation` drops.
LATE_OVERRIDE_CANDIDATE_SHA = "late_override_candidate_sha"

LATE_OVERRIDE_BASE_SHA = "late_override_base_sha"

# What that pair contributes, and the scheme the digest was taken under. The
# version travels with the digest wherever one is recorded: two ids taken
# under different rules are not comparable, and nothing about the ids
# themselves would say so.
LATE_OVERRIDE_FINGERPRINT = "late_override_fingerprint"

LATE_OVERRIDE_FINGERPRINT_FORMAT = "late_override_fingerprint_format"

# The reading that made the candidate oversized: what it adds, and the ceiling
# it was counted against. Both are recorded rather than referred to, because
# the generation carrying them is cleared and the ceiling is a knob -- and an
# authorization neither of them can be read back from is one nothing could
# hold to what a human actually decided.
LATE_OVERRIDE_ADDITIONS = "late_override_additions"

LATE_OVERRIDE_THRESHOLD = "late_override_threshold"

# The comment the authorization was made in, which is what makes it
# attributable: a bypass of the size gate is licensed by one gesture, at one
# address anybody can go and read.
LATE_OVERRIDE_COMMENT_ID = "late_override_comment_id"

# What each recorded hex field has to be, at its exact length: both ends of the
# authorized diff are whole git object ids, and the fingerprint is a whole
# digest. An abbreviation is not a commit this domain froze and a truncated
# digest is not a hash of anything, so neither is a value a comparison could be
# made on.
_HEX_SHAPES = MappingProxyType({
    LATE_OVERRIDE_CANDIDATE_SHA: _formats.COMMIT_LENGTHS,
    LATE_OVERRIDE_BASE_SHA: _formats.COMMIT_LENGTHS,
    LATE_OVERRIDE_FINGERPRINT: _formats.DIGEST_LENGTHS,
})

# Everything one authorization leaves on the pinned comment, taken as one
# group because it is written, read, and dropped as one: a record short of any
# member describes a bypass this issue cannot show the terms of.
_OVERRIDE_KEYS = (
    *_HEX_SHAPES,
    LATE_OVERRIDE_FINGERPRINT_FORMAT,
    LATE_OVERRIDE_ADDITIONS,
    LATE_OVERRIDE_THRESHOLD,
    LATE_OVERRIDE_COMMENT_ID,
)


@dataclass(frozen=True)
class LateOversizedPublication:
    """The terms one operator authorized an oversized candidate on.

    Handed in by the caller that proved them, because every field is something
    no reading taken later could recover on its own: the base is the pair's
    frozen end rather than whatever the checkout stands over now, the digest
    is taken between that pair, and the count is the reading the gate stopped
    on rather than one re-taken over a branch that has been writable since.

    `comment_id` is the trusted comment the authorization was made in. The
    caller proves the author before it offers one -- an allowlist is an
    operator's own and moves, so what belongs on the record is which comment
    was acted on rather than a copy of a judgement made about its author.

    Every field defaults to a value this domain refuses, so a caller that
    omitted one is told it has no authorization to record rather than
    recording a record about nothing.
    """

    candidate_sha: str = ""
    base_sha: str = ""
    fingerprint: str = ""
    additions: int = 0
    threshold: int = 0
    comment_id: int = 0

    @property
    def unusable_terms(self) -> str:
        """Why these are not terms an authorization may be written on, or "".

        One answer for every term, because a caller that cannot name any of
        them has the same problem: it is asking this domain to record evidence
        a later reader could not check, and that reader's move on unreadable
        evidence is to let unmeasured work reach a pull request.

        Asked of the terms themselves rather than beside the writer, since
        what makes a group unusable is a fact about the group: the same answer
        is owed whether it is about to be recorded or was handed in by a
        caller that has not decided yet.

        A refusal names the term and the type it arrived as, never the value.
        An exception message is read by a log, and a log is one step over from
        the surfaces a refusal about an unvouched-for value was protecting.
        """
        named = (
            (self.candidate_sha, _formats.COMMIT_LENGTHS),
            (self.base_sha, _formats.COMMIT_LENGTHS),
            (self.fingerprint, _formats.DIGEST_LENGTHS),
        )
        for given, lengths in named:
            if not _formats.is_hex_of(given, lengths):
                return f"an authorized publication is not one ({type(given).__name__})"
        return self._unusable_measurement

    @property
    def _unusable_measurement(self) -> str:
        """Why the reading behind these terms is not one, or "".

        The half of the answer above that is about numbers rather than about
        object ids, spelled apart because it is where the domain rule lives: a
        record at or under its own threshold describes a candidate the gate
        publishes untouched, which is a decision nobody had to make and so no
        authorization to record.
        """
        for counted in (self.additions, self.threshold):
            if not _formats.whole_number(counted) or counted < 0:
                return f"an authorized measurement is not one ({type(counted).__name__})"
        if self.additions <= self.threshold:
            return "an authorized publication is not one the gate would stop"
        if not _formats.whole_number(self.comment_id) or self.comment_id <= 0:
            return (
                "an authorizing comment is not an identity "
                f"({type(self.comment_id).__name__})"
            )
        return ""


@dataclass(frozen=True)
class LatePublicationOverride:
    """One authorized oversized publication, once every field proved out.

    Handed out whole or not at all, so nothing downstream has to decide what
    half of a bypass means. `fingerprint_format` sits beside the publication
    rather than inside it because it is this build's own answer rather than
    the caller's: what it says is which scheme the digest was taken under, and
    only the owner that takes one can say that.
    """

    publication: LateOversizedPublication
    fingerprint_format: int


def read_publication_override(
    state: PinnedState,
) -> LatePublicationOverride | None:
    """Return the oversized publication this issue authorizes, or None.

    None wherever the record cannot vouch for itself, which is every way it
    can fail to: a field that is missing, a group where only some of them are
    there, a value that is not the shape its field takes, a digest taken under
    a scheme this build does not compute, a comment id that names no comment,
    a count that is not a measurement, and a record whose additions are not
    strictly past the threshold recorded with them.

    That last one is refused for the same reason as the rest rather than as a
    curiosity. A candidate at or below its ceiling is one the gate publishes
    untouched, so a record claiming to authorize one describes a decision
    nobody had to make -- and a group that cannot describe a decision anybody
    made is not evidence a bypass may be granted on.

    What each of those costs is a measurement, and that is the whole of the
    cost: the candidate goes to the gate the way any unauthorized one does,
    and a human whose comment nothing could read is asked again.
    """
    recorded = {
        key: _payloads.as_hex(state.get(key), lengths)
        for key, lengths in _HEX_SHAPES.items()
    }
    counted = {
        key: _payloads.as_count(state.get(key))
        for key in (LATE_OVERRIDE_ADDITIONS, LATE_OVERRIDE_THRESHOLD)
    }
    # Both are read as identities because both start at 1: a comment id names
    # no comment below that, and a digest scheme this build could compute is
    # never numbered there either.
    numbered = {
        key: _payloads.as_identity(state.get(key))
        for key in (LATE_OVERRIDE_COMMENT_ID, LATE_OVERRIDE_FINGERPRINT_FORMAT)
    }
    if not all(recorded.values()) or None in counted.values():
        return None
    if numbered[LATE_OVERRIDE_FINGERPRINT_FORMAT] != FINGERPRINT_FORMAT:
        return None
    if numbered[LATE_OVERRIDE_COMMENT_ID] is None:
        return None
    if counted[LATE_OVERRIDE_ADDITIONS] <= counted[LATE_OVERRIDE_THRESHOLD]:
        return None
    return LatePublicationOverride(
        publication=LateOversizedPublication(
            candidate_sha=recorded[LATE_OVERRIDE_CANDIDATE_SHA],
            base_sha=recorded[LATE_OVERRIDE_BASE_SHA],
            fingerprint=recorded[LATE_OVERRIDE_FINGERPRINT],
            additions=counted[LATE_OVERRIDE_ADDITIONS],
            threshold=counted[LATE_OVERRIDE_THRESHOLD],
            comment_id=numbered[LATE_OVERRIDE_COMMENT_ID],
        ),
        fingerprint_format=numbered[LATE_OVERRIDE_FINGERPRINT_FORMAT],
    )


def record_publication_override(
    state: PinnedState, publication: LateOversizedPublication,
) -> None:
    """Record what an operator authorized this oversized candidate on.

    Refuses every term it could not vouch for rather than recording it: an end
    that is not a whole git object id, a digest that is not a whole one, a
    count nothing measured, a comment that is not one, and a measurement at or
    under its own ceiling, which is not an oversized publication to authorize.
    Writing any of those would move the failure onto a reader that has a
    candidate in hand and no sound grounds to let it publish.

    The whole group goes down in one statement and replaces whatever stood
    there, so a record is never half about one candidate and half about
    another -- which is exactly what a member left behind by a narrower write
    would make it, since these fields match by name and a later reader would
    take the survivor for part of the record beside it.

    The digest scheme is this build's own rather than the caller's, for the
    reason it is everywhere else here: it says which rules the digest beside
    it was taken under, and only the owner that takes one can answer that.

    Staged rather than persisted, like every other writer in this domain. What
    makes an authorization durable is the caller's own write, which is what
    lets it land together with whatever else that caller is recording, or not
    at all.
    """
    refusal = publication.unusable_terms
    if refusal:
        raise _formats.InvalidLateValue(refusal)
    recorded = {
        LATE_OVERRIDE_CANDIDATE_SHA: publication.candidate_sha,
        LATE_OVERRIDE_BASE_SHA: publication.base_sha,
        LATE_OVERRIDE_FINGERPRINT: publication.fingerprint,
        LATE_OVERRIDE_FINGERPRINT_FORMAT: FINGERPRINT_FORMAT,
        LATE_OVERRIDE_ADDITIONS: publication.additions,
        LATE_OVERRIDE_THRESHOLD: publication.threshold,
        LATE_OVERRIDE_COMMENT_ID: publication.comment_id,
    }
    for key, given in recorded.items():
        state.set(key, given)


def carry_publication_override(
    state: PinnedState, from_sha: str, to_sha: str, base_sha: str,
) -> None:
    """Move an authorization onto the commit a rewrite replaced its own with.

    Written wherever the exemption beside it moves, and never on its own,
    because the two are one claim in two halves: the exemption says which
    commit may publish without a reading, and this says whose gesture licensed
    it. Left behind, the rewritten commit would carry a verdict with no
    authorization standing for it, and the gate would stop a publication an
    operator has already decided.

    What moves is the pair the digest was taken between and nothing else. The
    additions, the ceiling they were counted against, and the comment the
    authorization was made in are what a human decided rather than facts about
    an object, and they are the same decision over either commit. The digest
    moves unchanged for the same reason: the permit that licenses a rewrite is
    granted only over contributions that fingerprint alike, so the digest
    already describes the rewritten pair.

    Silent where there is nothing to move -- a comment carrying no
    authorization this build can read whole, and one whose authorization is
    about some other commit. Neither is a record this write may repair or
    redirect: an authorization is bound to the candidate a human read, and one
    pointed at a commit nobody granted it for is the shape it may never take.
    """
    override = read_publication_override(state)
    if override is None or override.publication.candidate_sha != from_sha:
        return
    record_publication_override(state, replace(
        override.publication, candidate_sha=to_sha, base_sha=base_sha,
    ))


def clear_publication_override(state: PinnedState) -> None:
    """Drop the whole authorization, leaving every other field alone."""
    for key in _OVERRIDE_KEYS:
        state.data.pop(key, None)


def is_authorized(state: PinnedState, candidate_sha: str) -> bool:
    """Whether THIS commit is the one an operator authorized to publish.

    The whole record has to read back and the recorded candidate has to BE the
    commit in hand. Both halves matter and neither is the other's proxy: a
    commit made on top of the authorized one is work nobody read, and a record
    whose terms cannot be checked is a bypass nobody can show the grounds for.
    Either way the answer is False, and what False costs is the measurement
    the gate would have taken anyway.

    Both sides are held to being a whole object id, so a candidate the caller
    could not name answers False rather than matching a field by accident.
    """
    override = read_publication_override(state)
    if override is None:
        return False
    return override.publication.candidate_sha == _payloads.as_hex(
        candidate_sha, _formats.COMMIT_LENGTHS,
    )
