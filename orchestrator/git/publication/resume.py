# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Git evidence for an interrupted squash.

Before workflow can resume or discard a collapse claim, the checkout must be
clean and the recorded history must exist with the recorded ancestry and count.
A recovered squash also needs the original tree and the recorded base as its
sole parent.
"""
from __future__ import annotations

from contextlib import suppress
from pathlib import Path

from orchestrator.git import commands
from orchestrator.git.measurement import commits as _measurement_commits
from orchestrator.git.publication import planning
from orchestrator.git.verification import status as _worktree_status

# Which recorded end a reading could not produce, so an operator told the
# record names an object nobody holds knows which one.
_RECORDED_HEAD = "the head it says it collapsed"

_RECORDED_BASE = "the base it says it collapsed over"

# Why a resumed collapse could not be finished, spelled as the park comment
# reads it: what an operator has to reconcile differs by which of them it is.
_VANISHED_COLLAPSE = (
    "this issue records a squash of `{head}` and the branch carries nothing "
    "over its base at all, so there is no rewrite here to finish and no "
    "history left to rewrite afresh"
)


_UNPROVABLE_TREE = (
    "the worktree is not provably clean, so what a resumed push would publish "
    "is not what this record is about"
)


_ABSENT_END = "{side} (`{end}`) is not a commit this host holds"


_MISCOUNTED_HISTORY = (
    "the record says `{head}` was rewritten over `{base}` from a history of "
    "length {recorded} and this host walks {counted}"
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
    "the record says `{head}` was rewritten from a history of length "
    "{recorded} and the branch is standing on that head over {standing} -- so "
    "something rewrote it while the record went on naming the tip it had "
    "before"
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


def _unaccountable_branch(worktree: Path, plan: planning._SquashPlan, recorded) -> str:
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
    not be trusted with. There is no rewrite left to finish and no history
    left to rewrite, while the remote still carries every commit the record
    names -- so handed on, the nothing-to-rewrite road reports success over
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
    if not _is_ancestor(worktree, recorded.head, plan.original_head):
        return _UNBURIED_COLLAPSE.format(
            head=recorded.head, standing=plan.original_head,
        )
    return _BURIED_COLLAPSE.format(
        head=recorded.head, standing=plan.original_head,
    )


def _unrecovered_collapse(worktree: Path, recorded, squashed: str) -> str:
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
        cwd=worktree,
    )
    replaced = commands._git_hardened(
        "rev-parse", "--verify", "--end-of-options",
        f"{recorded.head}^{{tree}}", cwd=worktree,
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


def _unprovable_claim(worktree: Path, recorded) -> str:
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
    if not _worktree_status._worktree_status(worktree).is_clean:
        return _UNPROVABLE_TREE
    for side, end in (
        (_RECORDED_HEAD, recorded.head), (_RECORDED_BASE, recorded.base_sha),
    ):
        proved = _measurement_commits._prove_candidate_commit(
            worktree, end,
        )
        if not proved.is_frozen:
            return _ABSENT_END.format(side=side, end=end)
    if not _is_ancestor(worktree, recorded.base_sha, recorded.head):
        return _UNRELATED_PAIR.format(
            base=recorded.base_sha, head=recorded.head,
        )
    # A walk that did not happen, or one whose output is not a number,
    # stays None rather than becoming zero: an unreadable repository would
    # otherwise agree with a record claiming nothing was collapsed.
    walked = commands._git_hardened(
        "rev-list", "--count",
        f"{recorded.base_sha}..{recorded.head}", cwd=worktree,
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
