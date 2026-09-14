# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The carriers one late adjudication hands between its owners.

The late mode is additive: an oversized committed candidate is adjudicated
under the same `workflow:decomposing` label the initial decomposer runs under,
by a separate set of owners that share these records. They sit together
because each of them crosses a boundary the call stack alone would lose it
across -- the tick's own subject, which advances as the generation is
persisted; what reconciling the hold on the pull request its candidate stands
on left behind; the run this issue is locked to as the pinned comment records
it; what one late reply decided; what a fresh read said about the issue that
reply belongs to; the split that reading cleared for the transaction which
creates its children; what the requirements behind the frozen candidate
currently hash to and what the humans have said about them since; and what the
whole call did with the tick it was given.

`_LateRun` is the durable half. It records what the failure contract calls the
late agent's own facts -- the role it ran as, the backend spec it is locked
to, the session it opened, the cycle, generation, and exact source commit it
was spawned against, and the result it completed with -- so a tick that
crashed after a finished run reads the answer back rather than paying for a
second one, which would not be free and would be free to decide differently.
The result it records is the WHOLE of what the verdict decided, the child
manifest of a split and the explanation of what stopped a `single` from being
one included; the part deliberately left out is the agent's rationale for
accepting the change, which is prose nothing acts on. An outcome the pinned
comment cannot hold is refused entire rather than shortened, because half an
answer read back later is worse than none.

`_LateDisposition` is not a durable vocabulary and is spelled as a plain
`Enum` for that reason: nothing writes it to the pinned comment or to a sink,
so a member renamed here is a refactor rather than the migration a `StrEnum`
member in this domain would be.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from github.Issue import Issue

from orchestrator.config import models as _config_models
from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.late_split.events import LateVerdictCategory
from orchestrator.workflow.late_split.models import LateGeneration, LateVerdict

# The role a late adjudication is recorded under. It is the decomposer's --
# the question being answered is a decomposition question -- and it is stored
# beside the run rather than assumed, because the same coordinator owns the
# developer revision a trusted answer earns, which records its own role.
_DECOMPOSER_ROLE = "decomposer"

# What a `single` with no explanation beside it answers with. A fresh reply
# that omits one is refused where it is read, so the absence a reader meets is
# always a RECORD's: live issues carry results written before this domain kept
# an explanation, and those still decide this candidate. So it has a sentence
# of its own rather than an empty string a reader would render as nothing.
# Re-running the adjudicator to recover the prose is the one thing it must not
# cost: a second run is not free and is free to decide differently.
UNRECORDED_SPLIT_BLOCKER = (
    "no explanation of what stopped a split was recorded with this verdict"
)


class _LateDisposition(Enum):
    """What one late-adjudication call did with the tick it was given."""

    NOT_LATE = "not_late"
    PARKED = "parked"
    DEFERRED = "deferred"
    DECIDED = "decided"
    REVISED = "revised"
    SETTLED = "settled"
    CANCELLED = "cancelled"


class _OwnerState(Enum):
    """What a fresh read said about the issue an adjudication belongs to.

    Three answers rather than two, because "could not ask" is not "still
    open". A run finishes minutes to hours after the issue was fetched, and
    everything a verdict earns -- a publication, a snapshot, a supersession,
    an activation -- is an effect on an issue somebody may have closed in
    between. `UNREADABLE` is what the tick fails closed to: it costs one
    poll, while treating it as open costs work done on an issue nobody wants.
    """

    OPEN = "open"
    CLOSED = "closed"
    UNREADABLE = "unreadable"


@dataclass(frozen=True)
class _LateAdjudication:
    """What one late reply decided, once its fenced block was believed.

    A verdict is always present -- a reply that could not produce one is a
    parse error and never becomes one of these -- and the rest is what that
    verdict is allowed to carry. `children` is the manifest a `split`
    proposes, held in memory for the tick that acts on it, each slice of it
    carrying the addition budget it was proposed at: the issue created from
    that slice states the size, so the number travels with the manifest.

    `split_blocker` is the `single` verdict's own: what the agent said made
    splitting unsafe or unavailable, verbatim. It is what a reader shows
    somebody deciding what to do about an oversized candidate, and it is kept
    apart from `rationale` -- the prose arguing the change is acceptable as
    one -- because they answer different questions and only this one survives
    the pinned comment.
    """

    verdict: LateVerdict
    category: LateVerdictCategory | None = None
    rationale: str = ""
    question: str = ""
    split_blocker: str = ""
    children: tuple[dict, ...] = ()

    @property
    def split_blocker_explanation(self) -> str:
        """What this verdict says stopped a split, or that nothing says.

        Asked instead of the field, so every reader of a `single` gets a
        sentence: an outcome recorded before this domain kept one answers
        with the stand-in rather than with nothing, which is the only way the
        field is ever empty on this verdict, since a reply that declared it
        without an explanation never became one of these. Empty on the other
        two verdicts, which are not answers about a split that did not
        happen.
        """
        if self.verdict != LateVerdict.SINGLE:
            return ""
        return self.split_blocker or UNRECORDED_SPLIT_BLOCKER

    @property
    def child_count(self) -> int | None:
        """How many children a split proposed, and nothing for the others.

        The verdict event's contract, answered where the manifest is: a child
        count belongs to a `split` and to no other verdict, in both
        directions.
        """
        if self.verdict != LateVerdict.SPLIT:
            return None
        return len(self.children)


@dataclass(frozen=True)
class _LateRun:
    """The late run one issue is locked to, as pinned state records it.

    The spec is the whole configured command rather than the backend alone,
    for the reason every other role's pin is: a resume has to land on the CLI
    that issued the session id, and configured args are part of what a later
    run must reproduce.

    The result is the whole of what the verdict decided, not a marker for it.
    A `single` carries the explanation of what stopped a split, because that
    is the one thing a human deciding about an oversized candidate cannot get
    from anywhere else once the run is over; a `question` carries the category
    it was asked under and the sentence it asked, because announcing it is the
    outcome's own external effect and a crash between recording and posting
    has to be able to finish it; a `split` carries the child manifest and the
    budget each slice of it was proposed at, because that manifest IS what the
    split decided and the issues it becomes state those sizes -- a record
    without them would refuse the re-run while the answer it stands for was
    gone.
    """

    role: str = _DECOMPOSER_ROLE
    spec: str = ""
    backend: str = ""
    extra_args: tuple[str, ...] = ()
    session_id: str | None = None
    cycle_id: int = 0
    source_sha: str = ""
    generation: int = 0
    verdict: LateVerdict | None = None
    category: LateVerdictCategory | None = None
    question: str = ""
    split_blocker: str = ""
    children: tuple[dict, ...] = ()

    @property
    def is_actionable(self) -> bool:
        """Whether the recorded outcome is one a caller could act on.

        Asked per verdict, because what "complete" means differs by verdict
        and a half-written one is worse than none: a `question` with no
        sentence and no category suppresses the next spawn and then announces
        nothing, and a `split` with no children suppresses it and then names
        no children to create. Either would leave the issue decided, silent,
        and going nowhere -- so an incomplete record is not an answer, and the
        adjudicator runs again.

        A `single` is complete on its verdict alone, and the explanation
        beside it does not change that: it is what a reader shows rather than
        what a caller acts on, so a result recorded before this domain kept
        one is still this candidate's answer. Reading it as incomplete would
        buy a second agent run to recover prose.
        """
        if self.verdict == LateVerdict.SINGLE:
            return True
        if self.verdict == LateVerdict.QUESTION:
            return bool(self.question) and self.category is not None
        if self.verdict == LateVerdict.SPLIT:
            return bool(self.children)
        return False

    def ran_against(self, generation: LateGeneration) -> bool:
        """Whether this record's run was the one spawned for THIS candidate.

        All three parts of the identity are required, because any of them
        alone would let a stale record through. The generation counter is not
        unique on its own: a restart mints a fresh CYCLE and puts the counter
        back to where it started, so generation 1 of cycle 4 is a different
        attempt from generation 1 of cycle 3 -- and these run fields survive a
        late-generation clear, which is exactly the window a repeated counter
        would be read in. The commit is required beside them because a
        candidate replaced within one generation is a different question.

        Asked of two things, which is why it is separate from the verdict. A
        recorded ANSWER is this candidate's only when the run that produced it
        was; and a pinned SESSION may be resumed only when the conversation it
        holds is about this candidate, since resuming one opened against a
        commit that has since been replaced would hand the agent a transcript
        describing work nobody is adjudicating.
        """
        if not self.source_sha:
            return False
        return (
            self.cycle_id == generation.cycle_id
            and self.generation == generation.generation
            and self.source_sha == generation.candidate_sha
        )

    def answers(self, generation: LateGeneration) -> bool:
        """Whether a recorded result already decides THIS candidate.

        A record that is not actionable is unanswered whatever identity it
        carries: re-adjudicating costs one more agent run, while acting on a
        verdict whose substance nothing kept would cost whatever that verdict
        was about.
        """
        return self.is_actionable and self.ran_against(generation)



@dataclass(frozen=True)
class _HeldPr:
    """One pull request a hold is taken on, read once and under one guard.

    A PyGithub pull request is lazy: the object a fetch returns has asked
    GitHub nothing, and the request that can fail is the FIRST attribute read.
    A caller that guarded only the fetch would therefore guard almost nothing
    -- the failure lands later, on the head, the state, or the body, in the
    middle of deciding whether to replace a human's description.

    So every field a decision is made on is read where the fetch is guarded
    and carried here as a plain value. What is left of the pull request is the
    handle the edit is made against, and that write has a guard of its own.
    """

    pull_request: object
    number: int
    body: str
    head_sha: str
    pr_state: str


@dataclass(frozen=True)
class _HeldPrHold:
    """What reconciling the cycle-marked hold left behind.

    `held` and `failed` are not opposites. A generation with no reusable open
    pull request to mark is neither -- there is nothing to hold and nothing
    went wrong -- and the caller spawns exactly as it would have.

    `displaced` is the third answer, and it is the one that looks like the
    second and is not: an open pull request this generation DID hold, wearing
    a description a human wrote over the notice. Their words are left
    alone -- overwriting them is what the release below already refuses -- but
    the change is now mergeable with nothing on it saying an adjudication is
    open, which is exactly the state the hold exists to prevent. So it stops a
    spawn as `failed` does, while a result already recorded may still be
    settled: settling releases a hold that is already gone, and starting a new
    agent would leave a human free to merge under it.
    """

    generation: LateGeneration
    held: bool = False
    failed: bool = False
    displaced: bool = False


@dataclass(frozen=True)
class _StagedPark:
    """A park recorded but not yet said out loud.

    What every exit a COMPLETED run takes hands forward. The park itself has
    to be durable before anything is posted -- a comment GitHub refuses would
    otherwise take the run's result down with it and buy a second run of an
    agent that already finished -- and the owner read between the write and
    the notice is what decides whether the notice is owed at all, since
    nothing is said to a thread whose issue this tick could not prove is open.
    """

    message: str
    reason: str


@dataclass
class _LateContext:
    """The one tick a late adjudication runs inside.

    Mutable in six fields. `generation` is replaced as each step persists
    what it reached, so every owner after that step reads the record the pinned
    comment now holds rather than the one the tick opened on. `retired_park`
    is what this tick cleared, kept because clearing a park is not the same as
    the human it named never having been told: a park retired here and re-taken
    for the same reason is the same park, and repeating its notice would say
    the same thing to the same thread again.

    `answering` is set by the step that reopens a categorized question and read
    by the spawn several steps later: a run carrying a human's answer RESUMES
    the conversation that asked, rather than opening a fresh one that would
    have to be told what it had asked before it could be told the answer. It
    rides the tick rather than the pinned comment because it is a fact about
    this call and not about the issue -- and a tick that dies before the spawn
    simply pays for a fresh conversation, which still reads the answer in the
    thread its prompt quotes.

    `staged_park` is the fourth: the notice a park this tick recorded still
    owes the issue, held between the durable write and the owner read that
    decides whether it may be posted. It rides the tick for the same reason
    `answering` does -- a tick that dies before releasing it leaves the park
    itself standing, and whatever re-takes that park announces it then.

    `already_published` is the sixth, and it is the answer to the one window an
    authorized settlement cannot repair from the record alone. The push that
    decision licenses happens before the relabel and the retirement, so a
    tick that died in between comes back to a live generation whose pull
    request is standing on the accepted candidate rather than on the head the
    reading was frozen at. That is this settlement's own push having landed,
    not somebody else's -- and the proof reads it where the pull request is
    read, several steps before the push it makes unnecessary.

    `displaced_hold` is the fifth, and it travels the length of the call: the
    hold is reconciled at the top and what it found only matters at the spawn,
    several steps down. An open pull request whose notice a human removed may
    not have an agent started under it, but may still have an answer this
    issue already recorded settled -- so the fact is carried rather than acted
    on where it is learned.
    """

    gh: GitHubClient
    spec: _config_models.RepoSpec
    issue: Issue
    state: PinnedState
    generation: LateGeneration
    retired_park: str | None = None
    answering: bool = False
    staged_park: _StagedPark | None = None
    displaced_hold: bool = False
    already_published: bool = False


@dataclass(frozen=True)
class _GuardedSplit:
    """A split outcome that has passed the post-agent owner guard.

    The handoff to the transaction that creates the children, and the only
    shape that transaction accepts one in: a split reaches it having been
    decided AND having been re-checked against an owner read taken after the
    agent finished, so nothing can create children under an issue somebody
    closed while the adjudication ran.

    Both fields are carried rather than re-read. The generation is the record
    as the guard left it -- the phase it reached included -- and the children
    are the manifest the verdict decided on, so the transaction acts on the
    exact answer that was guarded rather than on whatever the pinned comment
    says by the time it looks.
    """

    generation: LateGeneration
    children: tuple[dict, ...]


@dataclass(frozen=True)
class _LateAdjudicationRun:
    """What one call to the late coordinator did, and what it decided.

    `run` is the record pinned state holds once this call is over, read back
    rather than assembled, so a caller reading a session id off it is reading
    the one a later resume would land on rather than the one the tick opened
    with.

    `adjudication` is present on every `DECIDED` answer, whether this tick's
    own agent produced it or a crashed one already had: a recovered outcome is
    rebuilt from the record, which carries the whole of what each verdict
    decided. Only the agent's rationale for accepting the change is missing
    from a rebuilt one -- prose the pinned comment deliberately does not
    keep.

    `guarded_split` is set on exactly one path: a `split` verdict that a fresh
    owner read found open. It is absent everywhere else, so a caller cannot
    reach the child-creating transaction from an outcome the guard never
    cleared.
    """

    disposition: _LateDisposition
    generation: LateGeneration
    run: _LateRun
    adjudication: _LateAdjudication | None = None
    guarded_split: _GuardedSplit | None = None


@dataclass(frozen=True)
class _LateFingerprint:
    """What the requirements behind a frozen candidate currently hash to.

    Two digests and the watermark one of them covers from, because the two
    questions a late generation asks about content are different questions. A
    title or body edit changes what the candidate is supposed to BE. Trusted
    conversation arriving after the baseline is a human answering, and which
    comments are new is a thing only an identifier can say -- so the watermark
    travels with the digest rather than being re-derived from it.

    The watermark is a ratchet the reader maintains rather than a maximum
    recomputed from the thread: a comment a human deleted must not put it back
    down and let already-consumed conversation read as fresh guidance.
    """

    title_body_hash: str
    comment_hash: str
    comment_watermark_id: int | None = None


@dataclass(frozen=True)
class _LateAuthorization:
    """One operator command authorizing an oversized candidate to publish.

    The commit as the human WROTE it rather than one this domain has vouched
    for: what a malformed argument earns is an answer on the thread, and a
    reader handed nothing at all could not tell that request from a line
    nobody typed.

    The comment is carried beside it because it is half of what the durable
    record is: a bypass of the size gate is licensed by one gesture at one
    address anybody can go and read, so what is recorded is which comment was
    acted on rather than a copy of a judgement about its author.
    """

    candidate_sha: str
    comment_id: int


@dataclass(frozen=True)
class _LateContentSignal:
    """What the human's content says about a candidate under adjudication.

    `guidance` is the trusted comments past the watermark that carry something
    to act on, in thread order, so the developer resume quotes what a human
    actually wrote. A bare `/orchestrator continue` is deliberately not one of
    them -- it is an operator control with no answer in it -- which is why it
    is reported separately rather than as one more comment.

    Untrusted authors, bots, and the orchestrator's own comments are not here
    at all: they are filtered out where the thread is read, so nothing an
    outsider posts becomes guidance, moves the watermark, or shifts a digest.

    `authorization` is the operator command that publishes an oversized
    candidate as it stands, reported apart from the guidance for the same
    reason the bare continue is: it is a control rather than a requirement,
    and handing it to a developer would answer a question about scope with a
    commit id. The last one a batch carries is the one reported -- a human who
    wrote it twice meant the second -- and only the whole comment is ever one.

    `baselined` is what keeps "nothing to compare against" apart from "the
    requirements moved". A generation whose baseline has still to be taken
    reports both drift flags -- an absent digest equals nothing -- and reading
    that as a scope edit would park the very first tick of every late
    adjudication.
    """

    fingerprint: _LateFingerprint
    baselined: bool = False
    title_body_drifted: bool = False
    conversation_drifted: bool = False
    guidance: tuple = ()
    bare_continue: bool = False
    authorization: _LateAuthorization | None = None

    @property
    def drifted(self) -> bool:
        """Whether the requirements themselves moved under the candidate.

        Either fingerprint answers it. A title or body edit is the obvious
        one; a counted comment edited or deleted after the fact is the same
        event with no new comment to read it out of, so it is answered the
        same way rather than being lost.
        """
        return self.title_body_drifted or self.conversation_drifted


@dataclass(frozen=True)
class _LateContentSettlement:
    """What reconciling the human's content did with this tick.

    A `disposition` of None is the only answer that lets adjudication carry
    on; every other one is the whole of what the tick did and the coordinator
    returns it. `persisted` says whether this owner already wrote what it
    staged, so a caller holding a staged retirement of its own knows whether
    it still owes a write.
    """

    disposition: _LateDisposition | None = None
    persisted: bool = False
