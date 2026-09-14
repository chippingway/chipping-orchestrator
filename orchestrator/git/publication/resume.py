# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The squash a process died part way through, finished or put back.

A squash is the one rewrite here that leaves the branch unable to say what
happened to it. It collapses the commits a reviewer approved into a single
object with the same tree, so the branch it leaves behind and the branch a
developer simply made one commit on read identically -- and read identically,
the interrupted one takes the nothing-to-squash road and is reported as a
success nobody counted and nothing published, with reviewer-approved work
reaching the merge button neither measured nor on the remote.

What tells them apart is the record the squash wrote before it ran: the head
it was collapsing, the base it was collapsing over, and how many commits went
in. This owner is what reads it back, and what it answers is which of seven
states the branch is actually in.

* An UNTOUCHED original branch. The head the record names is the head the
  checkout is on, so the reset never landed -- the record went down and the
  process died before anything destructive ran. Nothing is owed: the record is
  dropped and the ordinary squash runs over the commits that are still there.
* A branch something MOVED while the collapse was outstanding. The head is no
  longer the one the record names and the branch carries more than one commit,
  so work nobody here made is on it: the recovery owns the tick from the
  moment a record goes down, so no route in this workflow put it there.
  Squashing afresh would collapse that work in with the rest and force-push it
  onto the pull request as history a reviewer approved, so it refuses and
  keeps the claim -- saying which way the branch went, since an operator
  looking for the approved commits finds them under the stray work where the
  recorded head is still reachable and only in the reflog where it is not.
* A branch carrying NOTHING over its base, which is the one shape that road
  could not be trusted with. There is no collapse left to finish and no
  history left to squash, so the retry would report success having measured
  and published nothing while the remote still carries the history the record
  says was collapsed. It refuses instead.
* A squash COMPLETED locally and never pushed. The publication is resumed:
  entered on the recorded head, leased against it, and handed the pair the
  record holds so the transfer that carries an adjudication's exemption is
  decided on the same evidence the interrupted tick would have offered.
* A squash the gate AUTHORIZED -- a permission and a debt naming it -- whose
  push never went out. The same resume, and the permit behind it is re-asked
  in full rather than believed: nothing is remeasured and nothing is
  readjudicated, but nothing is taken on trust either.
* A squash ALREADY PUBLISHED. A durable receipt says this issue's own push put
  the pull request where it stands, so the resume is entered on the rewritten
  commit itself and the publication is the leased no-op it should be -- which
  is what lets the receipt, the debt, and the exemption settle without the
  work being measured or adjudicated a second time.
* A settled receipt whose HANDOFF never finished. The same state one step on,
  and the same answer: the count the record still holds is what the notice and
  the relabel behind this call are owed, and nothing else on the issue has it.

No road here is taken over a tree this host cannot PROVE clean, the one that
hands the branch back to the ordinary squash included. The probes that ran
before this call refuse on what git NAMED, so a status that established
nothing reads to them as a clean tree -- and an install with `DECOMPOSE=off`
freezes no entry either, so nothing behind this would prove a tree before the
rewrite and the push. The barrier that does read the recorded pull request on
every install reads only whether it has ended, which proves no tree.

Nothing is resumed on a record's SHAPE alone. A whole-looking record is one
somebody could have written, not one this repository ever produced, so the
three things it claims are proved against the objects before any of it is
acted on: both recorded ends peel to commits this host really holds, the
history between them really is the number of commits the record counts, and
the commit on the branch carries the tree the recorded head left -- which is
what a squash produces, exactly and by construction.
A record that fails any of them leaves the branch untouched and refuses:
every other refusal here knows what the branch is standing on and can put it
back, while this one is the answer to not knowing.

Everything else refuses, and refuses without inventing a repair. A remote
somebody else moved, a pull request a human closed, and a tree that stopped
being provably clean each come back from the publication as the refusal that
reading took, and the branch is put back only where nothing durable names what
is on it -- the same rule a fresh squash's own hold is answered by. A record
this build cannot read WHOLE is refused rather than ignored: a comment
claiming a collapse it cannot produce describes a branch nobody can account
for, and waving it past is precisely the nothing-to-squash road this owner
exists to close.
"""
from __future__ import annotations

from contextlib import suppress
from pathlib import Path

from orchestrator.git import commands
from orchestrator.git.measurement import commits as _measurement_commits
from orchestrator.git.publication import models, planning, rewrite
from orchestrator.git.verification import status as _worktree_status

# Which recorded end a reading could not produce, so an operator told the
# record names an object nobody holds knows which one.
_RECORDED_HEAD = "the head it says it collapsed"

_RECORDED_BASE = "the base it says it collapsed over"

# Why a resumed collapse could not be finished, spelled as the park comment
# reads it: what an operator has to reconcile differs by which of them it is.
_UNREADABLE_COLLAPSE = (
    "this issue records a squash it may not have finished and the record of "
    "it is not one this build can read, so the branch cannot be told from one "
    "with nothing to squash"
)


_VANISHED_COLLAPSE = (
    "this issue records a squash of `{head}` and the branch carries nothing "
    "over its base at all, so there is no collapse here to finish and no "
    "history left to squash afresh"
)


_UNPROVABLE_TREE = (
    "the worktree is not provably clean, so what a resumed push would publish "
    "is not what this record is about"
)


_ABSENT_END = "{side} (`{end}`) is not a commit this host holds"


_MISCOUNTED_HISTORY = (
    "the record says `{head}` collapsed {recorded} commits over `{base}` and "
    "this host counts {counted}"
)


_UNEQUAL_COLLAPSE = (
    "the branch stands on `{squashed}`, which does not carry the tree `{head}` "
    "left, so it is not the collapse this record describes"
)


_UNCOLLAPSED_PARENTS = (
    "the branch stands on `{squashed}`, which was made on {parents} rather "
    "than on the `{base}` this record says was collapsed over -- the same "
    "tree over another base is a commit that reverts whatever that base added"
)


_UNREADABLE_SHAPE = (
    "neither the tree `{head}` carries nor the shape of `{squashed}` could be "
    "read, so nothing here can say the branch is the collapse recorded"
)


_UNRELATED_PAIR = (
    "the record says `{head}` was collapsed over `{base}`, and `{base}` is "
    "not a commit `{head}` was ever built on"
)


_UNCOLLAPSED_BRANCH = (
    "the record says `{head}` was collapsed from {recorded} commits and the "
    "branch is standing on that head over {standing} -- so something rewrote "
    "it while the record went on naming the tip it had before"
)


_UNBURIED_COLLAPSE = (
    "the record says `{head}` was collapsed and the branch stands on "
    "`{standing}`, which was not built on it -- so the collapse was replaced "
    "rather than buried, and squashing afresh would take it with the rest"
)


_BURIED_COLLAPSE = (
    "the record says `{head}` was collapsed and the branch stands on "
    "`{standing}`, which was committed on top of it -- so something moved "
    "this branch on while the collapse was outstanding, and nothing here "
    "accounts for what it added"
)


def _resumed_squash(
    gate, branch: str, plan: planning._SquashPlan,
) -> models._SquashOutcome | None:
    """Finish the squash this issue began, or None where none is outstanding.

    Asked BEFORE the count of commits on the branch is read as a verdict,
    because a collapsed branch and a branch with nothing to collapse carry the
    same one commit and only the record tells them apart.

    None is the ordinary answer and means the branch is this call's to squash,
    and it is only ever reached over a record this repository can still show.
    Nothing is decided by comparing the record to the branch first: the ends
    it names are peeled, the pair it claims is proved to be one, the history
    between them is walked against the count, and the tree the classification
    would be made over has to be provably clean. Every road past that -- the
    one that DROPS the record and hands the branch back to the ordinary
    squash included -- rests on it.

    That order is the whole of the safety. A record whose head was edited to
    the commit a finished collapse left reads as a rewrite that never
    happened, so the shortcut for one would drop it and hand on a branch of
    ONE commit -- which is the nothing-to-squash road reporting success over a
    remote still carrying the history the record names. Proved first, the same
    record is refused: the walk between its ends does not come to the number
    it counts.

    The claim this build cannot read whole is the other refusal, and it comes
    first because it is the one thing the proof cannot be taken over. The
    branch it is about may be a completed collapse, and there is no reading
    here that could say: waved past, it is reported as a success that measured
    and published nothing.

    The tree is part of the same proof for a reason the probes ahead of this
    call cannot cover: they refuse on what git NAMED, so a status that
    established nothing reads to them as a clean tree -- and handing on from
    there is what puts an unreadable worktree into a rewrite, since
    `DECOMPOSE=off` freezes no entry and so nothing behind it proves a tree
    either. The barrier that reads the recorded pull request on every install
    reads only whether it has ended, which is no tree proof.
    """
    from orchestrator.workflow.stages.implementing import late_collapse_state

    recorded = late_collapse_state._recorded_collapse(gate.state)
    if recorded is None:
        if late_collapse_state._claims_a_collapse(gate.state):
            return rewrite._squash_failure(_UNREADABLE_COLLAPSE)
        return None
    unprovable = _unprovable_claim(gate, recorded)
    if unprovable:
        return rewrite._squash_failure(unprovable)
    return _outstanding_collapse(gate, branch, plan, recorded)


def _outstanding_collapse(
    gate, branch: str, plan: planning._SquashPlan, recorded,
) -> models._SquashOutcome | None:
    """What a proved record is owed over the branch in front of it.

    One commit the checkout has MOVED onto is the collapse this record is
    about, and finishing it is the whole of the recovery. The one branch the
    record may simply be DROPPED over is the one it still describes exactly --
    untouched, on the head it names, over the commits it counted -- which is
    the tick that died before the reset ever ran. Everything else is a branch
    this record cannot account for, and refuses.

    The drop rides the caller's own durable write, since a process dying
    before that write comes back to the same branch and the same answer. It is
    safe to hand on because the branch is the one the record was written over:
    the ordinary squash collapses exactly the commits an approval was given
    for, and it cannot report success without pushing them -- it goes through
    the entry, the rewrite, and the push, and refuses if any of them will not
    have it.
    """
    from orchestrator.workflow.stages.implementing import late_collapse_state

    if plan.count == 1 and plan.original_head != recorded.head:
        return _finished_collapse(gate, branch, plan.original_head, recorded)
    unaccountable = _unaccountable_branch(gate, plan, recorded)
    if unaccountable:
        return rewrite._squash_failure(unaccountable)
    late_collapse_state._forgets_the_collapse(gate.state)
    return None


def _unaccountable_branch(gate, plan: planning._SquashPlan, recorded) -> str:
    """Why this branch is not one the record may simply be dropped over.

    Four shapes reach here and only ONE of them is stale, which is the branch
    the record still describes exactly: standing on the head it names, over
    the commits it counted. The reset never ran, nothing else touched the
    branch, and the ordinary squash reads what is there as what it is.

    What tells that shape from the rest is never the commit count on its own:
    a count says nothing about which commits, and every one of these was
    reachable by a record somebody edited as much as by a tick that died. A
    head that matches over a different number of commits is a branch something
    rewrote while the record went on naming its old tip, which is what a
    record edited onto a finished collapse looks like: one commit, counted as
    three.

    A branch with NOTHING over its base is the shape the ordinary squash could
    not be trusted with. There is no collapse left to finish and no history
    left to squash, while the remote still carries every commit the record
    names -- so handed on, the nothing-to-squash road reports success over
    exactly that.

    And a branch that MOVED off the recorded head is refused whichever way it
    went, because nothing here can say who moved it. This recovery owns the
    tick from the moment a record goes down, so no route in this workflow
    resumes a developer or publishes over a branch carrying one: something
    outside it did. Squashing afresh would collapse that work in with the rest
    and force-push it onto the pull request as history a reviewer approved.
    The two are still told apart in the notice, because what an operator does
    next differs: a head still REACHABLE from the branch has the approved
    commits under whatever was committed over them, and one the branch
    REPLACED has them only in the reflog.
    """
    if plan.original_head == recorded.head:
        if plan.count == recorded.count:
            return ""
        return _UNCOLLAPSED_BRANCH.format(
            head=recorded.head, recorded=recorded.count, standing=plan.count,
        )
    if not plan.count:
        return _VANISHED_COLLAPSE.format(head=recorded.head)
    if not _is_ancestor(gate.worktree, recorded.head, plan.original_head):
        return _UNBURIED_COLLAPSE.format(
            head=recorded.head, standing=plan.original_head,
        )
    return _BURIED_COLLAPSE.format(
        head=recorded.head, standing=plan.original_head,
    )


def _finished_collapse(
    gate, branch: str, squashed: str, recorded,
) -> models._SquashOutcome:
    """Publish the commit an interrupted squash left, or put the branch back.

    The publication is the one a fresh squash makes, reached through the same
    tail: the entry is frozen over the head this collapse accounts for, the
    commit already on the branch is what goes out, and the record supplies
    exactly what the plan behind an uninterrupted squash would have -- the
    pair the transfer is decided on and the count the handoff announces. So an
    already-landed collapse costs a leased no-op rather than a fresh reading,
    and the receipt, the debt, and the exemption settle without the work being
    measured or adjudicated a second time.

    An entry that REFUSED is the one answer that tail never sees, because it
    happens before there is a publication to make: a pull request a human
    closed while the process was down, a remote off both heads this collapse
    accounts for, a tree that stopped being provably clean. It is answered
    here on the same rule the tail answers a refused publication by, so an
    operator gets one shape for "this collapse could not be finished"
    whichever reading found it. Where something durable names the commit on
    the branch -- a receipt, a debt, a live generation -- the reset is the
    destructive step and the branch is left exactly as this call found it, and
    a human reconciles the remote. Where nothing does, the collapse is a local
    commit nobody measured and nobody published, so the branch goes back onto
    the head the record named and the record goes with it -- which is what
    leaves the retry the approved commits to squash afresh rather than one
    commit it would report as having nothing to squash.
    """
    from orchestrator.workflow.stages.implementing import late_squash_proof

    unrecovered = _unrecovered_collapse(gate, recorded, squashed)
    if unrecovered:
        return rewrite._squash_failure(unrecovered)
    gated = rewrite._gated_rewrite()
    entry = gated._resumed_entry(gate, recorded, squashed)
    if entry.is_frozen:
        return rewrite._published_squash(
            gate, branch, entry, squashed, recorded,
        )
    if late_squash_proof._rewrite_stands(gate, squashed):
        return rewrite._squash_failure(entry.refusal)
    return rewrite._rollback_squash(
        gate, recorded.head,
        "a publication the size gate refused", entry.refusal,
    )


def _unrecovered_collapse(gate, recorded, squashed: str) -> str:
    """Why the commit on the branch is not the collapse recorded, or "".

    Asked once the record has proved its own claims, and it is the other half
    of the same question: that one shows the repository can produce what the
    record describes, this one shows the branch is standing on the object that
    describing it would have produced.

    A squash is exact about both things. It rewinds the branch onto the base
    with the index intact and commits it again, so what comes out carries the
    TREE of the head it replaced and has that base as its ONE parent. Neither
    proves it alone. A tree says nothing about the history under it: the same
    tree re-parented onto a base that has since advanced is a commit that
    REVERTS everything that base added, and published on the strength of the
    tree it would take those files off the pull request under an exemption a
    human granted something else. And a parent says nothing about the content.

    So the shape is read whole: the tree the recorded head carries, against
    the tree and the complete parent list of the commit actually on the
    branch. A reading that did not happen refuses, since an unreadable
    repository would otherwise prove any commit is the collapse of any other,
    and a commit with no parents or with more than one is not a collapse this
    workflow makes.
    """
    made = commands._git_hardened(
        "log", "-1", "--format=%T %P", "--end-of-options", squashed,
        cwd=gate.worktree,
    )
    replaced = commands._git_hardened(
        "rev-parse", "--verify", "--end-of-options",
        f"{recorded.head}^{{tree}}", cwd=gate.worktree,
    )
    shape = (made.stdout or "").split()
    carried = (replaced.stdout or "").strip()
    if made.returncode != 0 or replaced.returncode != 0 or not shape:
        return _UNREADABLE_SHAPE.format(squashed=squashed, head=recorded.head)
    if not carried or shape[0] != carried:
        return _UNEQUAL_COLLAPSE.format(
            squashed=squashed, head=recorded.head,
        )
    if tuple(shape[1:]) != (recorded.base_sha,):
        return _UNCOLLAPSED_PARENTS.format(
            squashed=squashed, base=recorded.base_sha,
            parents=" ".join(shape[1:]) or "nothing",
        )
    return ""


def _unprovable_claim(gate, recorded) -> str:
    """Why this repository cannot show the record's own claims, or "".

    What a whole-looking record has to earn before ANY road acts on it, the
    one that decides it is stale and drops it included. A record is the only
    account there is of a collapse, so every classification made against one
    -- including "nothing was rewritten, drop it" -- is a claim about objects
    this host either has or has not.

    The TREE comes first because it invalidates the rest: a classification
    made over a checkout nothing could describe is not a classification, and
    the probes ahead of this call refuse on what git NAMED rather than proving
    the opposite.

    Both ENDS are peeled as objects. Git resolves a whole id to itself whether
    or not the store has ever seen it, so an end recorded on another host --
    or one somebody typed -- comes back from a comparison looking exactly like
    a commit that is here. What believing it would buy is a record dropped as
    stale over a collapse nothing can account for, or a push leased against a
    head nobody holds and a transfer decided over a base nothing can produce.

    Then the ANCESTRY between them, because the count behind it is not one. A
    walk between two unrelated histories reports a number like any other, and
    a hand-edited base with the count adjusted to match would read as a whole
    record describing a collapse this branch never had -- so the pair is
    required to be a pair: the base reachable from the head it is said to have
    been collapsed over.

    The COUNT is walked last and is believed no more than the rest. It is the
    one field of the record that is not an object id, so nothing else here
    would catch a value somebody edited -- and what it becomes is the number a
    human is told their history was collapsed from.
    """
    if not _worktree_status._worktree_status(gate.worktree).is_clean:
        return _UNPROVABLE_TREE
    for side, end in (
        (_RECORDED_HEAD, recorded.head), (_RECORDED_BASE, recorded.base_sha),
    ):
        proved = _measurement_commits._prove_candidate_commit(
            gate.worktree, end,
        )
        if not proved.is_frozen:
            return _ABSENT_END.format(side=side, end=end)
    if not _is_ancestor(gate.worktree, recorded.base_sha, recorded.head):
        return _UNRELATED_PAIR.format(
            base=recorded.base_sha, head=recorded.head,
        )
    # A walk that did not happen, or one whose output is not a number,
    # stays None rather than becoming zero: an unreadable repository would
    # otherwise agree with a record claiming nothing was collapsed.
    walked = commands._git_hardened(
        "rev-list", "--count",
        f"{recorded.base_sha}..{recorded.head}", cwd=gate.worktree,
    )
    counted = None
    if walked.returncode == 0:
        with suppress(ValueError):
            counted = int((walked.stdout or "").strip())
    if counted != recorded.count:
        return _MISCOUNTED_HISTORY.format(
            head=recorded.head, recorded=recorded.count,
            base=recorded.base_sha, counted=counted,
        )
    return ""


def _is_ancestor(worktree: Path, ancestor: str, descendant: str) -> bool:
    """Whether one commit is really reachable from another.

    The reading a count cannot stand in for. `rev-list --count A..B` answers
    over two histories that never met just as readily as over a pair, so a
    number agreeing with a record proves the record was written by somebody
    rather than that it describes this branch.

    Fails closed on anything but a positive answer: git reports reachability
    with an exit status, and a walk that could not be taken at all shares its
    non-zero shape with "no". Neither is a proof, and the roads asking this
    one are the two that would otherwise act on a history nobody showed them.
    """
    asked = commands._git_hardened(
        "merge-base", "--is-ancestor", ancestor, descendant, cwd=worktree,
    )
    return asked.returncode == 0
