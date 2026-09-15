# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Frozen size-gate calls, publication entries, route spending, and gate verdicts.

A call carries the exact candidate, publication, and rewrite its caller
proved. Spending applies only the fields that caller named, and the close
latch is read from the shared observation registry for this issue.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from github.Issue import Issue

from orchestrator.config import models as _config_models
from orchestrator.github import client as _client, pinned_state as _pinned_state
from orchestrator.workflow.engine import observations as _observations
from orchestrator.workflow.late_split import (
    payloads as _payloads,
)
from orchestrator.workflow.late_split.rewrite_values import (
    LateRewrite,
)
from orchestrator.workflow.state import WorkflowLabel


@dataclass(frozen=True)
class _RecordedPublication:
    """The pull request this issue's record names, or why it names none.

    Three answers rather than two, because a field that is NOT THERE and one
    that is there and will not type are different facts about an issue.
    Absent is one that has published nothing: the first push of all is what
    OPENS a pull request, so there is none for a barrier before it to hold it
    to, and the pre-relabel window leaves the same shape.

    DAMAGED is the record disagreeing with itself -- a hand edit, an older
    write, a value this build cannot read back -- and reading it as an absence
    is exactly how a barrier fails open. Every identity here is read
    fail-closed, so an unusable one comes back as no identity at all: waved
    through for that, a push onto a pull request a human has just merged goes
    out as though the issue never had one, force-moving a terminal branch or
    opening a second pull request over work the first already carries.
    Neither is undoable, and what refusing instead costs is the poll that
    asks again once somebody repairs the comment.
    """

    number: int = 0
    damaged: bool = False

    @classmethod
    def named_by(cls, raw: object) -> _RecordedPublication:
        """What a recorded field says, told apart from what it fails to say.

        The RAW value is what this is handed, because the typed read is what
        loses the difference: `null` and a missing key are the absence this
        domain writes, and anything else the comment carries is a value it
        MEANT to name a publication with.
        """
        if raw is None:
            return cls()
        number = _payloads.as_identity(raw)
        return cls(number=number) if number else cls(damaged=True)


@dataclass(frozen=True)
class _Spends:
    """The route bookkeeping a hold closes on its caller's behalf.

    A hold is the end of the tick for the caller: the commit is on the branch,
    the issue is on `workflow:decomposing`, and the caller returns without
    pushing, relabelling, or counting anything. But the round IS spent -- the
    head a reviewer rejected is superseded either way -- and no later tick of
    that stage can count it, because an authorized settlement publishes the
    accepted commit itself and the resumed stage finds nothing left to push.

    So the caller says up front what its hold owes, and the hold writes it in
    the same durable write that carries the measurement, AHEAD of the relabel.
    Applied by the caller afterwards instead, it would be lost to a crash in
    exactly the window the relabel opens: the issue is already the
    adjudication's and nothing goes back for the count.

    Spelled as pinned fields rather than as a call into the route's own owner,
    so a stage's bookkeeping stays that stage's to describe and this owner
    stays free of the stage packages that import it.
    """

    fields: tuple = ()


# What a caller with no route bookkeeping behind it owes, which is every
# publication taken before there is a pull request to spend a round on.
_SPENDS_NOTHING = _Spends()


def _spend(state: _pinned_state.PinnedState, spends: _Spends) -> None:
    """Close the route bookkeeping a caller said its hold owed.

    Spelled beside the record rather than at either site that applies it, so
    the routed hold and the recovery that publishes what a crash interrupted
    write the same fields the same way. Both are the same claim -- this is
    what the tick that reached the gate would have done -- and only the moment
    differs: the hold writes it ahead of its own relabel, the recovery once
    the push it makes has landed.
    """
    for key, spent in spends.fields:
        state.set(key, spent)


@dataclass(frozen=True)
class _PublicationEntry:
    """The publication a gate call was entered on, or why there is none.

    What tells a candidate the remote already carries from one nothing has
    published, and the only three facts about it a reconciliation could not
    re-derive: the stage the gate is taking the issue out of, which the
    adjudication label replaces the moment it is applied; the pull request the
    work already has, which the hold beside it names only because this entry
    named it first; and the head that pull request was left standing on, which
    the next push to the branch moves. All three are read once, before any
    effect, and travel frozen for the same reason every other late field does.

    Absent where the gate was entered before anything was published, which is
    what the whole implementing seam is, and refused with its reason where the
    three could not be established -- `is_frozen` is what a caller asks, since
    a group short of any one of them is a publication nothing could name.
    """

    stage: WorkflowLabel | None = None
    pr_number: int = 0
    published_sha: str = ""
    refusal: str = ""

    @property
    def is_frozen(self) -> bool:
        """Whether this entry names a publication a record may carry."""
        return not self.refusal


@dataclass(frozen=True)
class _Gate:
    """The one candidate a gate call is deciding about.

    The worktree travels with the issue because the two are read together at
    every step and neither is derivable from the other here: the commit is
    proved, the base is frozen, and the diff is counted in that checkout,
    while the record, the park, and the label all belong to the issue.
    """

    gh: _client.GitHubClient
    spec: _config_models.RepoSpec
    issue: Issue
    state: _pinned_state.PinnedState
    worktree: Path
    # Whether a developer ran on this tick. Nothing in the checkout can be a
    # run's output where none did, which is what makes a head that moved off
    # the recorded candidate something that moved rather than fresh work.
    reconciling: bool = False
    # Whether this tick is answering a reading a PREVIOUS one recorded. The
    # narrower of the two, and the one the switch is asked against: a rebase,
    # a resolution, and a recovery push are each work no developer ran for
    # and work the gate has never seen, so reading "no developer ran" as
    # "already in the gate" would measure candidates `DECOMPOSE=off` exists
    # to publish untouched.
    answering: bool = False
    # The commit the caller named as the one it means to publish, where it
    # read one for itself. Empty where the caller has none -- a bounce over a
    # checkout it did not just write, a recovery answering a recorded pair --
    # and the head this owner proves is the whole of the answer there.
    candidate: str = ""
    # The publication this call was entered on, where there is one. It is the
    # whole of what makes this gate reusable past the initial push: nothing
    # else here changes when the work already has a pull request, and every
    # record the call writes carries the group rather than reading as an entry
    # taken before anything was published.
    entry: _PublicationEntry | None = None
    # What this call's caller owes for the candidate, whichever way it goes.
    # A hold closes it ahead of the relabel it makes, and a landed push closes
    # it in the write that carries the receipt -- one durable write either
    # way, since past that write nothing on the comment names the round any
    # more. Empty for every publication with no round behind it, and for the
    # implementing seam, which has no reviewer to have spent one.
    spends: _Spends = _SPENDS_NOTHING
    # The rewrite this candidate came out of, where the caller made one. It
    # is the only evidence a permit may be granted on, and the only account
    # anything later has of how an exemption came to license a commit no
    # human ever saw. It is the caller's because everything in it is gone
    # from the checkout and the remote by the time this owner could ask.
    rewrite: LateRewrite | None = None
    # Whether a rewrite permit is the ONLY thing that may let this candidate
    # publish. Off for every ordinary caller, and on for the crash recovery,
    # which reaches this gate holding a transfer it already knows about.
    permit_only: bool = False

    @property
    def close_was_observed(self) -> bool:
        """Whether a poll has read this issue closed since the tick opened.

        The process-wide latch rather than the issue object, and the two are
        different facts. The object is a snapshot the tick opened with, and
        everything a publication spends between that fetch and its push -- a
        remote read, a diff, a worktree probe -- is time a poll on another
        worker can find the issue closed in. The latch is what that poll
        leaves behind, so this is the only reading that can answer for the
        window rather than for the moment the fetch happened.

        Costs no request, which is why it can be asked as late as the step it
        guards rather than once at the door.
        """
        return _observations.close_observed(self.spec.slug, self.issue.number)


@dataclass(frozen=True)
class _Entered:
    """The terms the CALLER entered this gate call on.

    Every field is something this owner could read for itself and must not, or
    could not know at all. A stage read back off a cached issue names the
    label of the last write made through that object -- on one a same-tick
    relabel did not go through, the label the fetch carried rather than the
    one the relabel wrote -- and a head read again is not the head the caller
    pinned its own decision to.
    `reconciling` says no developer ran on this tick, which is what tells a
    checkout that MOVED from a resumed developer's fresh commit. `answering`
    is the narrower claim behind it -- that this call is answering a reading a
    previous tick RECORDED -- and it is what the switch is asked against, so a
    rebase or a recovery push that no developer ran for is still the new work
    `DECOMPOSE=off` publishes untouched. `spends` is the route bookkeeping a
    hold has to close on the caller's behalf. `rewrite` is the before-state a
    caller that REPLACED a commit destroyed getting here, which is the one
    thing no reading taken now could recover.

    Empty is the ordinary answer and means the caller established none of it:
    the label is current, the remote has not been read, a run has just
    finished, and there is no reviewer round behind the push.
    """

    stage: WorkflowLabel | None = None
    head: str = ""
    # The branch this publication will be PUSHED to, which the caller resolves
    # for itself. It is the other half of naming a publication: a pull request
    # standing on the commit in hand says nothing about where the push would
    # land unless it is open on the branch that push names, and the record
    # those two are read off can disagree with itself -- a `branch` a hand
    # edit moved, or a `pr_number` from a cycle whose branch was different.
    # Frozen against the read, an entry can never describe one pull request
    # while the push behind it moves another.
    branch: str = ""
    # The commit the caller means to publish, where it read one for itself.
    # This owner proves the checkout's head independently, and between the
    # caller's read and that one the worktree is writable -- so a commit
    # landing in the window would be measured, pushed, and recorded here while
    # the caller went on to stamp the id IT read. Named, the two are one
    # decision and a checkout that moved refuses before anything is persisted.
    candidate: str = ""
    reconciling: bool = False
    answering: bool = False
    spends: _Spends = _SPENDS_NOTHING
    # What the caller REWROTE to arrive at the candidate above, where it
    # rewrote anything. It is the evidence a change a human already
    # adjudicated may be recognized in a commit that did not exist when they
    # ruled on it, and it is handed in rather than read because a rewrite
    # destroys its own before-state.
    rewrite: LateRewrite | None = None
    # Whether the permit is the whole of what may license this publication.
    #
    # Off is the ordinary answer and the one every publishing seam gives: a
    # permit that refuses leaves the candidate to the cumulative reading, and
    # a count under the ceiling publishes the same commit on the count rather
    # than on the exemption. That is right for a caller DECIDING whether to
    # publish a rewrite it has just made.
    #
    # On is the recovery, and it is right there for the opposite reason. It
    # holds a transfer it already knows about -- a permission the grant left,
    # or evidence re-derived from the record -- and what it is finishing is a
    # publication, not deciding one. Measured instead, a count under the
    # ceiling would report the recovery as landed with the verdict still on
    # the commit a human ruled on, and a count over it would route an
    # adjudicated change into a second adjudication with the pull request
    # already open over the work.
    permit_only: bool = False


# What a caller that established nothing hands in.
_UNENTERED = _Entered()


@dataclass(frozen=True)
class _GateVerdict:
    """What the gate decided, and the exact commit it decided about.

    The SHA travels because the caller's next step is a PUSH, and a push that
    named nothing would publish whatever the checkout points at when it runs.
    Everything this gate does is a claim about one object id -- it proved that
    commit, measured that commit, and recorded that commit -- so handing back
    a bare "go ahead" would drop the one fact the publication needs to be the
    same event the measurement was about.

    Empty where this gate has nothing to name: a candidate the switch kept
    out of it was never proved here, so there is no commit THIS answer can be
    published under. The publication resolves the checkout's own head there
    rather than pushing an unnamed branch -- the switch keeps candidates out
    of the measurement, not out of the record of what went out.

    `permitted_sha` is the second commit and answers a different question: not
    "may this publish" but "did a rewrite permit prove out for it on THIS
    tick". It is empty for every road but one, the ordinary measurement's
    included -- a permit that refused leaves the candidate to the cumulative
    gate, and a candidate the gate then lets through publishes on the count
    rather than on the exemption.

    The first two are separate because the write past the push turns on the
    second and only the second. A permission standing on the comment is
    evidence a permit was once granted, not that it still holds: a repointed
    pull request, a relabelled issue, a moved remote, or a contribution that
    no longer fingerprints alike each refuse it while the ordinary reading may
    still publish the same commit. Read off the record instead, that
    publication would rotate a human's verdict onto a rewrite this tick
    declined to vouch for.

    `basis` is what ADMITTED this candidate, carried as the wire value the
    approval group records. It travels for the reason the commit does: the
    caller's next step records a debt, and only the answer that let the
    candidate past can say what that debt rests on. Re-derived at the write
    instead, a proof that succeeded here and fails a moment later -- a store
    that stopped answering between the two readings -- would record an
    operator's bypass as ordinary unmeasured debt, which the tick after a
    crash then spends without asking anyone.

    Empty for every road that decided nothing to carry, and read back as the
    ordinary unmeasured basis there.

    `delivered_pr` is the fourth, and it travels for the same reason as the
    commit: only the answer that admitted this candidate read the pull request
    it is already standing on, and the seam behind it would otherwise resolve
    a branch for itself and reuse whatever pull request happened to be open on
    that. What the number buys is a push it can LEASE against the very commit
    the reading proved, and bookkeeping bound to the pull request that proof
    was about rather than to whatever a second lookup finds. Zero on every
    road that proved no such publication, which is every road but one.

    `refused` is the fifth, and only a `permit_only` caller can get it: the
    permit declined and nothing was measured in its place. It is a hold like
    any other -- the caller publishes nothing -- except that the gate has
    taken no park and made no route, so the caller owns what happens next.
    """

    held: bool
    candidate_sha: str = ""
    permitted_sha: str = ""
    basis: str = ""
    delivered_pr: int = 0
    refused: bool = False


# What every held answer is, since a hold names no commit: there is nothing
# for the caller to publish and nothing for it to publish it under.
_HELD = _GateVerdict(held=True)

# What a permit-only caller gets when its permit declines: nothing measured,
# nothing parked, nothing routed, and the answer handed back for the caller to
# fail closed on.
_REFUSED = _GateVerdict(held=True, refused=True)
