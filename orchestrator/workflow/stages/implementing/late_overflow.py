# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The publication a gate call taken PAST the first push is entered on.

The same gate one seam further on. A developer resumed on review feedback, on a
human's comment, or on an edited issue body; a commit an earlier park stranded;
a deferred push or one a timeout killed the disposition before it saw; a
conflict resolution; a base refresh; a final documentation pass. Each of them
puts a commit on a checkout a pull request was opened from, and what the push
that follows produces is not that commit's own diff -- it is everything the
pull request comes to with the commit in it.

Nothing about the measurement, the record, or the verdict is this owner's, and
neither is the push: `late_gate` beside it is the order the size questions are
asked in and answers them the same way for both seams, and `late_push` spends
what it hands back. What is HERE is the entry -- the three facts a call taken
past publication has that one taken before it does not, and the refusals that
make freezing them fail closed rather than open.

The entry is frozen BEFORE any effect and travels with the record because a
reconciliation could re-derive none of it. The stage is gone the moment the
adjudication label replaces it. The pull request is the one the work already
has, and it is recorded here rather than read back off the hold beside it: that
record names whichever pull request the cycle marked, which is this one only
because this entry named it first. And the head is the tip that pull request
was left standing on, which the next push to the branch moves. Recorded, a
later tick can say which publication a generation was entered on; re-read, it
would answer with whatever the issue has become.

Seven readings refuse rather than report, and each of them is a push this gate
would otherwise wave through on evidence nobody took. A tree that is not
PROVABLY clean is one whose diff is not the diff a push would publish -- and a
`git status` that established nothing names no paths, which is what a clean
tree names too. A pull request nothing could read, or one that is closed or
merged, is not a publication a measurement means anything against -- and all
three of those readings are taken inside one refusal, since a fetched pull
request is a lazy object and the requests that fail are the attribute accesses
behind the lookup. A pull request whose head lives in another REPOSITORY is
somebody's fork: forks carry this repository's ref names over this
repository's commits, so every term below would agree while the branch the
push names was never the one that pull request is about. A pull request open
on a BRANCH other than the one this publication will push is the record
disagreeing with itself: the number and the branch are two fields on one
pinned comment, and an entry frozen on the head alone would have the
settlement, the receipt and the relabel all spent against a publication the
push never touches. A head the CALLER named that is no whole object id, or
that is not the head this pull request is standing on, is a disagreement
between two readings of one fact rather than a choice between them: preferring
either would freeze a tip the branch would not be pushed onto. And a head that
has MOVED off what a live record froze is somebody else's push landing between
the freeze and this tick: the frozen pair no longer describes what this branch
would add to that pull request, so the reading is refused and the record is
left standing rather than re-entered over a publication it was never taken on.

Two readings here answer no entry at all. A pull request that has merged or
been closed is a terminal state the ISSUE's own flag cannot show, and both
sides of an effect need it: the reconciliation that hands a tick back reads it
fail-OPEN, so a remote that would not answer costs a poll rather than
stranding an issue, and the barrier immediately before a push reads the same
fact fail-CLOSED, since what falling through costs there is a branch nothing
can put back.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from orchestrator import config
from orchestrator.git.verification import status as _worktree_status
from orchestrator.github.client import GitHubClient
from orchestrator.workflow.late_split import (
    formats as _formats,
    payloads as _payloads,
    state as _late_state,
)
from orchestrator.workflow.late_split.models import LateGeneration
from orchestrator.workflow.stages.implementing import (
    late_approval_reading as _late_approval_reading,
    late_gate_models as _late_gate_models,
    late_park_notices as _late_park_notices,
    late_publication_state as _late_publication_state,
    late_records as _records,
    state as _state,
)
from orchestrator.workflow.state import WorkflowLabel
from orchestrator.workflow.transitions import publishes_onto_a_pull_request

log = logging.getLogger("orchestrator.workflow")


# What a pull request has to be for a candidate to be measured against it.
_OPEN = "open"


# What the moved-publication refusal is logged and reported as. It is not a
# reading that failed but a reading nothing may be taken over, so it is named
# rather than borrowing one of the measurement failures.
_MOVED_HEAD = "the pull request moved under the frozen pair"


# Why an entry could not be frozen, spelled as the park comment reads it.
_NO_SOURCE_STAGE = (
    "it is not on a workflow state that publishes onto a pull request the "
    "remote already carries"
)


_NO_PULL_REQUEST = "it records no pull request to measure against"


_UNREADABLE_PULL_REQUEST = "pull request #{number} could not be read"


_CLOSED_PULL_REQUEST = "pull request #{number} is {state} rather than open"


# What a pull request open on some other branch is refused as. The record's
# own two fields disagreeing is exactly the shape this catches, so both are
# named: the branch the push is about to take, and the one the pull request
# the SAME record points at is open on.
_DISAGREEING_BRANCH = (
    "pull request #{number} is open on `{read}` rather than on `{expected}`, "
    "which is the branch this publication would push"
)


# What a pull request whose head lives somewhere else is refused as. A fork
# can carry the same ref name at the same commit, so neither of the two below
# tells it from this repository's own publication.
_FOREIGN_REPOSITORY = (
    "pull request #{number} has its head in `{read}` rather than in "
    "`{expected}`, so it is not a publication this issue could have made"
)


_UNREADABLE_HEAD = (
    "pull request #{number} names no head this reading could use"
)


_UNNAMEABLE_HEAD = (
    "the head this call was entered on is not a whole object id, so there is "
    "nothing to pin a push against"
)


_DISAGREEING_HEAD = (
    "this call was entered on `{expected}` and pull request #{number} stands "
    "at `{read}`, so the two do not describe the same publication"
)


_UNPROVABLE_TREE = (
    "the worktree is not provably clean, so the diff a push would publish is "
    "not the diff anything here could measure"
)


_ENTRY_PARK = (
    "{mentions} the commit in this issue's worktree has not been pushed: "
    "before a candidate joins a pull request the remote already carries, what "
    "that pull request would come to is measured against a ceiling of "
    "{threshold} -- and this issue could not be entered into that reading "
    "because {refusal}. Nothing was pushed and nothing was discarded. Clear "
    "what the entry needs and the next tick takes the reading again."
)


# How a frozen publication can fail to be the one this tick reads. Each is
# spelled as the park comment reads it, because what an operator has to
# reconcile differs by which of them moved.
_DAMAGED_PUBLICATION = (
    "the record says it was entered on a publication and cannot name all of "
    "it, so there is nothing to compare this one against"
)


_PR_CHANGED = (
    "it was measured against pull request #{frozen} and this issue now "
    "records #{read}"
)


_STAGE_CHANGED = (
    "it was entered from `{frozen}` and this issue is on `{read}`"
)


_HEAD_CHANGED = (
    "pull request #{number} was standing at `{frozen}` and stands at "
    "`{read}` now"
)


_MOVED_PUBLICATION_PARK = (
    "{mentions} this issue's committed candidate was measured against a "
    "publication this tick cannot confirm is the same one: {disagreement}. "
    "The pair this issue froze no longer describes what that pull request "
    "would come to, so nothing was pushed and nothing was discarded. "
    "Reconcile the branch with what landed -- or repair the pinned comment -- "
    "then commit again so the candidate is measured afresh."
)


def _frozen_entry(
    gate: _late_gate_models._Gate, entered: _late_gate_models._Entered,
) -> _late_gate_models._PublicationEntry:
    """The publication this call is entered on, or the reason there is none.

    Read in the order the refusals matter in, so a park names the first thing
    that was missing rather than a later step standing in for it. The tree
    comes first because it is the cheapest and the one that invalidates every
    reading behind it: a candidate measured beside uncommitted changes is not
    the candidate a push would publish, and a `git status` that established
    nothing is not a clean tree either. Then the stage, then the pull request
    and the head on it.

    Two of the three are the CALLER's where it has them, and both for the same
    reason: a fact this owner would re-read is a fact that can have moved
    since the caller acted on it.

    The stage, because the label is a cached object, current only on the
    object the last relabel went through. A route that relabels remotely and
    then publishes in the same tick -- the reviewer's `CHANGES_REQUESTED`,
    which flips to `fixing` before the dev spawn -- knows the state it moved
    to, and a record built from an object that missed the flip would name the
    state the issue has LEFT and a settled verdict would continue there.
    Whatever the caller names is still checked, and against the exact
    predicate rather than the transition graph: the five states that publish
    onto a pull request the remote already carries, not every label with an
    edge to the adjudication. `ready`, `blocked`, and `umbrella` each have one
    for reasons of their own and no pull request behind any of them, and
    `implementing`'s own push is what OPENS the pull request -- so an entry
    frozen from one of those would record a group a later reconciliation
    measures and pushes on a stage that never committed the candidate.

    The head, because a caller that established one has already decided on it.
    The conflict and base-sync publications each read the remote themselves
    and pin their push to what they read; freezing anything else would leave
    the immediate push refusing a head that moved while a later one -- a
    settled adjudication's -- pinned to the head that moved and overwrote it.
    What is frozen is what the push will be pinned against, so both roads fail
    closed on the same fact.
    """
    if not _worktree_status._worktree_status(gate.worktree).is_clean:
        return _late_gate_models._PublicationEntry(refusal=_UNPROVABLE_TREE)
    stage = entered.stage or gate.gh.workflow_label(gate.issue)
    if not publishes_onto_a_pull_request(stage):
        return _late_gate_models._PublicationEntry(refusal=_NO_SOURCE_STAGE)
    number = _payloads.as_identity(gate.state.get(_state._PR_NUMBER))
    if not number:
        return _late_gate_models._PublicationEntry(refusal=_NO_PULL_REQUEST)
    return _entered_on(
        gate, stage, number, entered,
        _this_issues_own(gate, entered, number),
    )


def _this_issues_own(
    gate: _late_gate_models._Gate, entered: _late_gate_models._Entered, number: int,
) -> frozenset:
    """The commits a publication standing here would be this issue's own push.

    A caller naming the head it began at is claiming the publication has not
    moved since, and there is one move that is not somebody else's: this
    issue's OWN push having landed. A tick that pushed and died before its
    record went down comes back to a pull request standing on the very commit
    it was about, and refusing that as a disagreement would stop the
    reconciliation that exists to finish it -- for a remote that is exactly
    where this issue put it.

    Three ways to be that commit, and every one of them is a DURABLE record
    of a push this workflow decided on or made -- which is the whole of what
    makes the carve-out safe. Two stand alone: the commit an approval says is
    still owed a push, and the pair a frozen record is being reconciled
    against. An approval is dropped by the write that pays it and a generation
    is retired by the write that approves it, so neither outlives the window
    it describes.

    The caller's own candidate is deliberately NOT among them. It is a commit
    this tick read off a checkout a moment ago, and it says nothing about how
    the remote came to be standing on it: on a fresh attempt no push of this
    workflow's has run at all, so a pull request that moved from the head the
    caller began at onto the candidate moved because something ELSE put it
    there -- an agent that pushed its own commit is the plain case -- and
    waving it through would measure and route the very candidate this gate
    exists to hold back. The one thing that tells the two apart is a record,
    and the caller does not have one.

    The publication receipt is the record that does, and it is admitted only
    with the head it REPLACED beside it. Alone it would be no evidence: it is
    the last commit this stage put on the remote and is never cleared, so a
    pull request a rewrite or a revert moved BACK onto a commit published
    rounds ago would read as this tick's own push having landed -- and a
    checkout standing on that same commit is not evidence either, since a
    rewind can put the branch and the pull request back on it together. What
    dates a receipt to THIS attempt is the head it was pinned to: a push made
    from the head this call was entered on, which is one the caller froze and
    a rewind cannot supply. Matched, the window is exactly the one it exists
    for -- a push that landed and a process that died before the relabel
    behind it -- and a receipt naming any other head answers for nothing.

    The pull request the receipt names is the third term, and it is the one
    the other two cannot supply: a branch pushed from this head before, onto a
    publication since closed and REPLACED by another on the same ref, satisfies
    both of them while the pull request being frozen is not the one that push
    went to. Held to the number this call is freezing, the carve-out is about
    one publication and no other.
    """
    recorded = _late_state.read_late_generation(gate.state)
    receipt = _late_publication_state._publication_from(gate.state, entered.head, number)
    return frozenset(filter(None, (
        _late_approval_reading._approved_commit(gate.state),
        recorded.candidate_sha,
        receipt if receipt == entered.candidate else "",
    )))


def _entered_on(
    gate: _late_gate_models._Gate,
    stage: WorkflowLabel,
    number: int,
    entered: _late_gate_models._Entered,
    landed: frozenset,
) -> _late_gate_models._PublicationEntry:
    """Freeze the pull request this call is entered on, or say why not.

    The state is asked whoever named the head, because what makes a cumulative
    measurement mean anything is that there IS a live pull request for the
    candidate to join: a closed or merged one has nowhere for the push to
    land, so a count against it would adjudicate a question nobody can act on.

    The head is the caller's where it established one, and it is CHECKED
    against this read rather than substituted for it. Both are whole object
    ids or there is no head at all -- evidence a later tick could not compare
    anything to is not evidence -- and the two have to be the same commit,
    because they are two readings of one fact: the tip the caller pinned its
    own decision to, and the tip the publication is standing on. Where they
    disagree the pull request moved between the caller's reading and this one,
    which is somebody else's push landing mid-tick: preferring either would
    freeze a head that is not what the branch would be pushed onto, and an
    oversized candidate would be persisted and routed on evidence already
    overtaken. So it refuses, and a caller that established nothing is the
    only one this read answers for on its own.

    All THREE reads are taken inside one refusal, because a fetched pull
    request is a lazy object: `get_pr` returns without asking GitHub anything,
    and the request that would fail is the attribute access behind it -- the
    state, or the head. Guarding only the lookup leaves the two that do the
    talking to raise out of a gate whose whole contract is to fail closed, and
    an exception on the road to a park is a park nobody takes.
    """
    reading = _PublicationReading.taken(gate.gh, number)
    if reading.refusal:
        return reading.refusal
    if reading.state != _OPEN:
        return _late_gate_models._PublicationEntry(
            refusal=_CLOSED_PULL_REQUEST.format(
                number=number, state=reading.state,
            ),
        )
    if not gate.gh.is_own_repository(reading.head_repo):
        return _late_gate_models._PublicationEntry(
            refusal=_FOREIGN_REPOSITORY.format(
                number=number,
                read=reading.head_repo,
                expected=gate.gh.repo_slug,
            ),
        )
    return reading.standing_head(number, stage, entered, landed)


@dataclass(frozen=True)
class _PublicationReading:
    """One pull request as this tick found it, or the refusal that found none.

    Both facts together because both are requests and both fail together: what
    a caller may act on is a reading where every one of them came back, and a
    reading where any did not is one refusal rather than a state with a head
    missing from it.

    Taken through the constructor below rather than by a caller reading the
    fields off a fetched object, because a fetched pull request is LAZY: the
    lookup asks GitHub nothing and the requests that can fail are the
    attribute accesses behind it. A `try` around the lookup alone leaves those
    two to raise out of a gate whose whole contract is to fail closed, and an
    exception on the road to a park is a park nobody takes.
    """

    state: str = ""
    head: str | None = None
    # The branch that head is the tip OF, which is the other half of naming a
    # publication: a pull request standing on the commit in hand says nothing
    # about where a push would land unless it is the branch that push names.
    head_branch: str | None = None
    # The repository that branch lives in, which is what makes the two above
    # identify anything at all: a fork carries the same ref names over the same
    # commits, so a pull request from one satisfies every other term here while
    # pointing at a branch no push of this issue's has ever touched.
    head_repo: str | None = None
    # The fetched pull request the three above were read off, for the one
    # caller that needs the OBJECT rather than a fact about it. Carried out of
    # the guarded read instead of fetched again beside it, because a second
    # lookup is a second moment: a pull request this reading proved open can
    # be closed by the time another answers, and the object that answer hands
    # back is one nothing here checked. Out of the comparison, since two
    # readings of one pull request describe the same publication however
    # PyGithub spells the object.
    pull_request: object | None = field(default=None, compare=False)
    refusal: _late_gate_models._PublicationEntry | None = None

    def standing_head(
        self,
        number: int,
        stage: WorkflowLabel,
        entered: _late_gate_models._Entered,
        landed: frozenset,
    ) -> _late_gate_models._PublicationEntry:
        """The head this call freezes, or why the two readings name none.

        The BRANCH comes first, because it is what makes every answer below
        it about the same publication. The number and the branch are two
        fields on one pinned comment and they can disagree: a `branch` a hand
        edit moved, or a `pr_number` left over from a cycle that ran on
        another ref. Frozen on the SHA alone, an entry describing a pull
        request on branch B would license a push that names branch A -- so the
        settlement, the receipt and the relabel would all be spent against a
        publication this push never touched. It is refused rather than
        preferred either way, since neither field is evidence the other is
        wrong.

        Three refusals follow rather than a preference. A pull request naming
        no usable head is one nothing can be pinned against. A caller-named
        head that is not a whole object id is the same failure one step
        earlier -- it is not dropped in favour of the read, because a caller
        that established a head made its own decision on it and a fallback
        would pin the push to a fact that decision was never taken over. And
        two whole ids that are not the same commit are a publication that
        moved while this tick was in flight.

        With one exception, and it is not a preference either: a tip a
        DURABLE record says this issue put there is this issue's OWN push
        having landed, which is the window the receipt and the approval exist
        for. Refusing it would stop the reconciliation that finishes that
        window over a remote sitting exactly where this issue put it. A tip
        that merely happens to be the commit in hand is not that -- nothing
        on the record says a push of ours made it the tip -- and it refuses
        with every other head somebody else moved.

        What is frozen is what the publication is STANDING on, which is what
        the caller's head was checked against rather than a second name for
        it. The two are one commit on every ordinary call; where the carve-out
        let them differ, the tip is what says whether the push has anything
        left to send.
        """
        if entered.branch and self.head_branch != entered.branch:
            return _late_gate_models._PublicationEntry(
                refusal=_DISAGREEING_BRANCH.format(
                    number=number, read=self.head_branch,
                    expected=entered.branch,
                ),
            )
        observed = _payloads.as_hex(self.head, _formats.COMMIT_LENGTHS)
        if not observed:
            return _late_gate_models._PublicationEntry(
                refusal=_UNREADABLE_HEAD.format(number=number),
            )
        named = _payloads.as_hex(entered.head, _formats.COMMIT_LENGTHS)
        if entered.head and not named:
            return _late_gate_models._PublicationEntry(refusal=_UNNAMEABLE_HEAD)
        if named and named != observed and observed not in landed:
            return _late_gate_models._PublicationEntry(
                refusal=_DISAGREEING_HEAD.format(
                    expected=named, number=number, read=observed,
                ),
            )
        return _late_gate_models._PublicationEntry(
            stage=stage, pr_number=number, published_sha=observed,
        )

    @classmethod
    def is_over(cls, gh: GitHubClient, number: int) -> bool:
        """Whether this pull request has already merged or been closed.

        The terminal state an ISSUE's own flag cannot show: a merge leaves the
        issue open until a stage terminal reads it and finalizes the work,
        while everything a reconciliation does in between ends in a push onto
        exactly this pull request -- which the freeze above refuses to enter a
        call on, so such a tick would park a human over a publication that is
        finished.

        Read fail-OPEN, which is the other way round from everything else
        here and is the point: a reading that did not come back says nothing
        about whether the publication is over, and answering True on one would
        strand every issue whose remote was briefly unreachable. So an
        unreadable pull request, and a caller naming none at all, both leave
        the tick to the road that takes its own reading and parks with the
        reason it fails for.
        """
        reading = cls._of(gh, number)
        return reading is not None and reading.state != _OPEN

    @classmethod
    def still_open(cls, gh: GitHubClient, number: int) -> bool:
        """Whether this pull request is one a push may still land on.

        The same reading as `is_over` beside it and the opposite failure
        direction, because the two answer for opposite sides of an effect.
        That one guards a tick handing itself back, where a remote that would
        not answer has to fall through or every briefly unreachable issue
        would strand. This one stands immediately before a PUSH, where the
        alternative to refusing is rewriting a branch whose pull request
        somebody merged -- so a reading that did not come back answers False,
        and what that costs is the poll that takes it again.

        A caller naming no pull request answers False too, which is not a
        refusal of the ordinary road: the only callers here are the ones that
        already hold a number, so one that has gone missing between the
        reading that produced it and the push is the record disagreeing with
        itself.

        The OPEN state and nothing else, which is all a barrier about endings
        has to know. A caller acting on the pull request itself asks
        `standing_exactly_on` below instead, since where a publication is
        standing is a different question from whether it has ended.
        """
        reading = cls._of(gh, number)
        return reading is not None and reading.state == _OPEN

    @classmethod
    def standing_exactly_on(
        cls, gh: GitHubClient, number: int, branch: str, head: str,
    ):
        """The pull request `number` still standing exactly there, or None.

        The whole publication identity re-read rather than the open state
        alone, because what the caller does with the answer is finish
        bookkeeping ABOUT a publication: it writes the receipt naming this
        commit and hands a reviewer this pull request. Open is only one of
        the terms that has to still hold -- a head somebody moved between the
        proof and here leaves the receipt naming a commit the branch no
        longer carries, a branch or a repository that disagrees was never the
        publication the proof was about, and every one of them is a reviewer
        sent to work this issue did not publish.

        The object handed back is the one the reading was taken OFF, not a
        second fetch of the same number: a caller that checked one answer and
        then acted on another has acted on a pull request nothing proved, and
        the window between the two is exactly where somebody moves it.

        None for every disagreement and for a reading that did not come back,
        because what the caller does with None is hold: nothing is written,
        the record stays as it stands, and the next poll asks again.

        Every term the freeze and the delivery proof are held to, asked once
        more off this one reading: open, in this repository, on the branch the
        push named, and standing on the commit it sent.
        """
        reading = cls._of(gh, number)
        if reading is None:
            return None
        observed = _payloads.as_hex(reading.head, _formats.COMMIT_LENGTHS)
        stands = (
            reading.state == _OPEN
            and gh.is_own_repository(reading.head_repo)
            and reading.head_branch == branch
            and observed == head
        )
        return reading.pull_request if stands else None

    @classmethod
    def taken(cls, gh: GitHubClient, number: int) -> _PublicationReading:
        """Ask the remote for a pull request's state and head, or refuse."""
        try:
            return cls._facts(gh, number)
        except Exception:
            log.warning(
                "pull request #%d could not be read for the size gate",
                number, exc_info=True,
            )
        return cls(
            refusal=_late_gate_models._PublicationEntry(
                refusal=_UNREADABLE_PULL_REQUEST.format(number=number),
            ),
        )

    @classmethod
    def _of(cls, gh: GitHubClient, number: int) -> _PublicationReading | None:
        """One numbered pull request as it reads now, or None for no reading.

        The shared half of the two answers above, so each of them spells only
        the direction it fails in. None is "this host cannot say", which
        covers a caller naming no pull request at all and a request that did
        not come back.
        """
        if not number:
            return None
        reading = cls.taken(gh, number)
        return reading if reading.refusal is None else None

    @classmethod
    def _facts(cls, gh: GitHubClient, number: int) -> _PublicationReading:
        """The lookup and the lazy reads behind it, as one reading."""
        pull_request = gh.get_pr(number)
        head = getattr(pull_request, "head", None)
        return cls(
            pull_request=pull_request,
            state=gh.pr_state(pull_request),
            head=getattr(head, "sha", None),
            head_branch=getattr(head, "ref", None),
            head_repo=getattr(
                getattr(head, "repo", None), "full_name", None,
            ),
        )


def _refused_entry(
    gate: _late_gate_models._Gate,
    recorded: LateGeneration,
    entry: _late_gate_models._PublicationEntry,
) -> bool:
    """Park a call that could not be entered, and publish nothing.

    Reported under the record the issue already has rather than under one
    minted for the refusal, and deliberately not persisted: a generation
    naming a cycle and no candidate freezes nothing and reads as a live cycle
    to the guard that ends one when the issue is closed. Where there is no
    record at all the identity is minted for the report exactly as every other
    refusal in this domain mints one, so the failure reaches both sinks under
    a correlation a later freeze writes again.

    The record it goes down against carries no publication group, and that is
    the honest answer rather than a gap: the entry is what would have said
    which pull request the reading was about, and it is the thing that just
    failed to prove itself. A refusal claiming a publication it could not
    describe is the record this domain refuses at its own boundary.
    """
    log.error(
        "issue=#%d cannot be entered into the size gate for the pull request "
        "it already has (%s); refusing to push a candidate nobody measured",
        gate.issue.number, entry.refusal,
    )
    return _late_park_notices._parked(
        gate, _records._reportable(gate, recorded), entry.refusal,
        _ENTRY_PARK.format(
            mentions=config.HITL_MENTIONS,
            threshold=config.MAX_ADDED_LINES,
            refusal=entry.refusal,
        ),
    )


def _moved_publication(
    gate: _late_gate_models._Gate,
    recorded: LateGeneration,
    entry: _late_gate_models._PublicationEntry,
) -> bool:
    """Refuse a live record whose publication is not the one it was frozen on.

    The frozen group is what makes a cumulative reading repeatable: the record
    says which pull request the pair was measured against, which stage it was
    entered from, and what that pull request was standing on.

    All three are compared, not just the head, because the head alone is not
    an identity: a branch reused across two pull requests can put the same
    commit at the tip of both, and a count taken against one would be settled
    against the other under the same generation.

    A record that carries the MARKER and cannot show all three is refused
    rather than skipped. That is the case a comparison has nothing to compare
    -- a hand edit, an older write, a field that would not type, a stage no
    publication is entered from -- and skipping it is what lets the entry this
    tick read be stamped over the evidence the reading was actually taken on,
    so an old count is acted on under a publication nobody measured it
    against.

    Refused, the record is left exactly as it stands. Not re-entered:
    overwriting the group with what was read now would hide the very
    disagreement this exists to catch. A record with no marker at all is one
    nothing was frozen for, which is every pre-publication generation.
    """
    if not recorded.publication.post_publication:
        return False
    disagreement = _publication_disagreement(recorded, entry)
    if not disagreement:
        return False
    log.error(
        "issue=#%d was frozen on a publication this tick cannot confirm "
        "(%s); refusing to measure or push against it",
        gate.issue.number, disagreement,
    )
    return _late_park_notices._parked(
        gate, _records._reportable(gate, recorded), _MOVED_HEAD,
        _MOVED_PUBLICATION_PARK.format(
            mentions=config.HITL_MENTIONS, disagreement=disagreement,
        ),
    )


def _publication_disagreement(
    recorded: LateGeneration, entry: _late_gate_models._PublicationEntry,
) -> str:
    """How the frozen publication differs from the one read now, or "".

    Named rather than counted, because the park has to tell a human which one
    moved -- a pull request somebody pushed to, a number the issue was
    repointed at, and a stage a relabel moved are three different things to
    reconcile.
    """
    if not recorded.publication.is_complete:
        return _DAMAGED_PUBLICATION
    if recorded.publication.published_pr_number != entry.pr_number:
        return _PR_CHANGED.format(
            frozen=recorded.publication.published_pr_number, read=entry.pr_number,
        )
    if recorded.publication.source_stage != entry.stage:
        return _STAGE_CHANGED.format(
            frozen=recorded.publication.source_stage, read=entry.stage,
        )
    if recorded.publication.published_sha != entry.published_sha:
        return _HEAD_CHANGED.format(
            number=entry.pr_number,
            frozen=recorded.publication.published_sha,
            read=entry.published_sha,
        )
    return ""
