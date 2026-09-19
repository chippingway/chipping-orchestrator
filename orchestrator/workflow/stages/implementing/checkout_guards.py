# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Proving a checkout is still the thing that was measured, and refusing it.

What a push sends is a COMMIT; what the handoff passes on is the CHECKOUT, and
every stage past it works from that checkout without reading it again. The
reviewer treats a head ahead of the pushed branch as unpushed work to publish,
the squash rewrites what is on the tree, and the docs pass commits over it --
so a worktree that stopped being what the size gate measured reaches a merge
through a force-push no measurement ever saw.

Each proof has two halves, because the head answers only half of what "this
checkout" is. The commit is one: a head sitting anywhere but the commit the
publication is about is refused. The tree is the other, and it is why a
reading taken once at the top of the disposition is not enough -- work can
appear beside a commit without moving it, so every proof about the commit
passes while the checkout stops being the thing that was measured.

Both halves are asked twice, on either side of a push, because the window is
the requests in between and the worktree is writable while they run. Before
the push a refusal costs nothing: nothing is on the remote, no pull request is
open, and the commit is where the developer left it. After it the publication
STANDS and only the handoff stops, so the branch and its pull request stay
right while review never reads the descendant.

Every refusal here parks under the one reason a moved checkout earns, and
every one of them is settled by the worktree rather than by words -- put back
on the named commit, or cleaned, and the next tick finishes what stopped with
nothing re-run and no agent spawned.

WHEN each of these is asked is the publication owner's, along with what the
commit they are asked about is recorded as. This owner decides only what a
proof looks at and what its refusal says.
"""
from __future__ import annotations

import logging
from pathlib import Path

from github.Issue import Issue

from orchestrator import config
from orchestrator.git.measurement import commits as _measurement_commits
from orchestrator.git.verification import status as _worktree_status
from orchestrator.github import client as _client, pinned_state as _pinned_state
from orchestrator.workflow.engine import guards as _guards
from orchestrator.workflow.stages.implementing import (
    late_approval_state as _late_approval_state,
    models as _models,
    state as _state,
)

log = logging.getLogger("orchestrator.workflow")

# How the checkout's own head is named wherever this stage resolves one. Every
# reading goes through the same proof the size gate read it with -- resolved,
# peeled, and hardened -- so no two of them can disagree about what commit a
# worktree is on while one decides whether the other may publish.
_HEAD = "HEAD"

_MOVED_CHECKOUT_PARK = (
    "{mentions} this issue's worktree is on `{head}`, not the commit the size "
    "gate measured and approved (`{approved}`), so nothing was published: "
    "handing review a checkout the gate never saw is how an unmeasured "
    "implementation reaches a merge. Nothing was discarded and the branch is "
    "untouched. Put the worktree back on `{approved}` and it publishes by "
    "itself on the next tick, with nothing re-run and no agent spawned, or "
    "leave it where it is and reply with the change you want made."
)

# How many loose paths a refusal names before it starts counting instead.
_NAMED_PATHS = 10

_DIRTIED_BEFORE_PUSH_PARK = (
    "{mentions} this issue's worktree is on {commit} -- the commit this "
    "publication was about -- but {loose}, so nothing was published. What a "
    "push sends is the COMMIT, and every stage past the handoff reads the "
    "CHECKOUT: review would be handed a tree carrying work the pull request "
    "does not show, and the squash and the docs pass would commit it or "
    "destroy it. Nothing was discarded and the branch is untouched. Commit "
    "the loose work as its own candidate, or clear it, and this one publishes "
    "by itself on the next tick with nothing re-run and no agent spawned -- "
    "or leave it and reply with the change you want made."
)

_MOVED_AFTER_PUSH_PARK = (
    "{mentions} this issue's branch was published at `{published}` and its "
    "pull request carries it, but the worktree moved to `{head}` while that "
    "was happening -- so the issue was not handed to review. What review "
    "reads is the checkout, and every stage past the handoff rewrites it: a "
    "worktree left on a commit nobody measured reaches a merge through a "
    "squash or a docs pass, one force-push later. Nothing was discarded and "
    "the published branch is untouched. Put the worktree back on "
    "`{published}` and the handoff finishes by itself on the next tick, with "
    "nothing re-run and no agent spawned, or leave it where it is and reply "
    "with the change you want made."
)

_DIRTIED_AFTER_PUSH_PARK = (
    "{mentions} this issue's branch was published at `{commit}` and its pull "
    "request carries it, but {loose} -- so the issue was not handed to "
    "review. What review reads is the checkout, and every stage past the "
    "handoff rewrites it: uncommitted work beside a published branch is "
    "squashed away or committed on top, one force-push later, with nothing "
    "having measured it. Nothing was discarded and the published branch is "
    "untouched. Commit the loose work as its own candidate, or clear it, and "
    "the handoff finishes by itself on the next tick with nothing re-run and "
    "no agent spawned -- or leave it and reply with the change you want made."
)


def _park_for_the_checkout(
    gh: _client.GitHubClient,
    issue: Issue,
    state: _pinned_state.PinnedState,
    message: str,
) -> None:
    """Hold the issue for a checkout nothing may be handed over from.

    Under the reason a moved checkout earns, because every refusal that
    reaches here is the same one a field over: what stops is the HANDOFF,
    what settles it is the worktree rather than words, and the recovery that
    watches for it asks the checkout the questions this stage publishes on --
    the commit it is on, and whether what is around that commit can be proved
    to be nothing. The comment is what tells an operator which of them it is;
    the reason is the control field, and a second one would need a second
    recovery to mean anything different.

    The refusal with no commit to record is the one that stays put: the
    quiet republication is keyed off the commit a park writes down, and a
    checkout that could not say what it is on writes none -- so that park
    waits for a human, and their reply resumes the session as any other
    unpublishable checkout's does.
    """
    _guards._park_awaiting_human(
        gh, issue, state, message, reason=_state._CANDIDATE_MOVED,
        bounded=True,
    )
    state.set(_state._PARK_REASON, _state._CANDIDATE_MOVED)


def _loose_work(tree: _worktree_status._WorktreeStatus) -> str:
    """Say what a tree reading refused on, in the words the refusal needs.

    A reading that never HAPPENED is the one an operator would otherwise be
    told nothing about. It names no paths, so a message built from the list
    alone reads as "0 uncommitted changes" and sends them looking through a
    tree for a file that was never the problem -- while what they have to
    clear is a `git status` that will not run or an index bit that makes what
    it does report worthless.
    """
    if not tree.paths:
        return (
            "its state could not be read (`git status` failed, or an index "
            "entry is marked `assume-unchanged`/`skip-worktree`)"
        )
    shown = tree.paths[:_NAMED_PATHS]
    named = ", ".join(f"`{path}`" for path in shown)
    elided = len(tree.paths) - len(shown)
    if elided:
        named = f"{named}, … ({elided} more)"
    return f"it now carries uncommitted changes: {named}"


def _moved_off_the_candidate(
    gh: _client.GitHubClient,
    issue: Issue,
    state: _pinned_state.PinnedState,
    approved: _models._ApprovedWork,
    worktree: Path,
) -> bool:
    """Refuse a handoff whose checkout is not the commit that was approved.

    The window is small and the consequence is not: the size gate reads the
    worktree, and between that reading and this write a descendant the timeout
    cleanup raced, a second process, or an operator can move `HEAD`. The push
    itself is safe -- it names the approved commit -- but the checkout is what
    every stage past this one works from, and one sitting on an unmeasured
    descendant is an implementation that reaches review, a squash, and a merge
    without the gate ever having seen it.

    So the tick stops here. Nothing is pushed and no pull request is opened,
    which keeps the recovery cheap: the commit is still in the worktree, the
    branch is untouched, and a checkout put back on the approved commit
    republishes it unchanged -- while one deliberately left on the descendant
    is measured as the fresh candidate it is on the next run.

    Asked only where the GATE approved a commit. A candidate the switch kept
    out of it was never proved there, so there is nothing this proof could
    compare a head to -- the intent the caller settles resolves the head
    itself, and the proof taken once the pull request is open holds the
    checkout to whichever of the two named the commit that went out.
    """
    if not approved.candidate_sha:
        return False
    proved = _measurement_commits._prove_candidate_commit(worktree, _HEAD)
    head = proved.sha
    if proved.is_frozen and head == approved.candidate_sha:
        return False
    log.error(
        "issue=#%s worktree is on %s rather than the approved commit %s; "
        "refusing to hand an unmeasured checkout to review",
        issue.number, head or "an unreadable head", approved.candidate_sha,
    )
    _guards._park_awaiting_human(
        gh, issue, state,
        _MOVED_CHECKOUT_PARK.format(
            mentions=config.HITL_MENTIONS,
            approved=approved.candidate_sha,
            head=head or "an unreadable head",
        ),
        reason=_state._CANDIDATE_MOVED,
        bounded=True,
    )
    state.set(_state._PARK_REASON, _state._CANDIDATE_MOVED)
    # What the refusal is waiting on, written where something can act on it.
    # Nothing else on the issue still names this commit -- the record it came
    # from was retired ahead of the effects it licensed -- so without it the
    # park names a SHA in prose and the operator who does exactly the right
    # thing gets no acknowledgement for it: ordinary ticks stay parked and a
    # bare continue is refused as one with no guidance on it.
    #
    # The whole approval group, because this refusal stands exactly where the
    # publication would have minted one: the debt an unmeasured candidate owes
    # on this seam is written past this line, and a candidate admitted by a
    # receipt or an exemption reaches here with nothing yet recorded. Written
    # as the commit alone, the tick that comes back to this park would have to
    # infer whose decision the push it is about to make rests on.
    _late_approval_state._owes_a_publication(state, approved.candidate_sha)
    return True


def _dirtied_before_the_push(
    gh: _client.GitHubClient,
    issue: Issue,
    state: _pinned_state.PinnedState,
    published: str,
    worktree: Path,
) -> bool:
    """Refuse a publication whose tree stopped being provably clean.

    The half of the same race the head proof cannot see. Cleanliness was
    proved once, at the top of the disposition, and everything between that
    reading and this one is time an agent's descendant, a second process, or
    an operator can write in -- with `HEAD` never moving, so every proof taken
    against the commit passes. What goes out is right; what is wrong is the
    CHECKOUT, and the checkout is what the handoff passes on. Review reads a
    dirty tree as work to publish, the squash rewrites what is on it, and the
    docs pass commits over it, so uncommitted work that slipped in here
    reaches a merge with nothing having measured it -- and the stage this
    hands to takes no reading of its own.

    So the tick stops before the push rather than after: nothing is on the
    remote, no pull request is open, and the commit is exactly where the
    developer left it. The commit was made durable before this is asked, so a
    checkout whose tree is cleaned republishes it on the next tick with
    nothing re-run.
    """
    tree = _worktree_status._worktree_status(worktree)
    if tree.is_clean:
        return False
    loose = _loose_work(tree)
    log.error(
        "issue=#%s worktree carries work no push would publish (%s) while on "
        "%s; refusing to publish an unproven checkout",
        issue.number, loose, published,
    )
    _park_for_the_checkout(
        gh, issue, state,
        _DIRTIED_BEFORE_PUSH_PARK.format(
            mentions=config.HITL_MENTIONS,
            commit=f"`{published}`",
            loose=loose,
        ),
    )
    return True


def _moved_after_the_push(
    gh: _client.GitHubClient,
    issue: Issue,
    state: _pinned_state.PinnedState,
    published: str,
    worktree: Path,
) -> bool:
    """Refuse the handoff when the checkout left the commit that was pushed.

    The window the pre-push proof cannot cover. The push, the pull-request
    lookup, and the open are all requests, and the worktree is writable while
    they run -- a descendant the timeout cleanup raced is the commonest thing
    to move it. What went out is exactly the commit that was named, so the
    branch and the pull request are right; what is wrong is the CHECKOUT, and
    the checkout is what every stage past this one works from. The reviewer
    reads a head ahead of the pushed branch as unpushed work to publish, the
    squash rewrites what is on it, and the docs pass commits on top -- so a
    worktree left on an unmeasured descendant reaches a merge through a
    force-push no measurement ever saw.

    So the handoff stops rather than the publication being taken back. The
    commit is on the remote and its pull request carries it, which is what the
    receipt the caller records ahead of this says; the label does not move, so
    review never reads the descendant; and the park names the commit the
    checkout has to go back to. Putting it back republishes with nothing
    re-run, and leaving it there measures it as the fresh candidate it is on
    the next run.

    What the commit is RECORDED as owing is the caller's, for the reason the
    dirty reading beside this one gives: the two sides of the gate promise
    different things about the head the republication would be pinned to.
    """
    proved = _measurement_commits._prove_candidate_commit(worktree, _HEAD)
    if proved.is_frozen and proved.sha == published:
        return False
    head = proved.sha or "an unreadable head"
    log.error(
        "issue=#%s worktree moved to %s after %s was pushed; refusing to hand "
        "an unmeasured checkout to review", issue.number, head, published,
    )
    _guards._park_awaiting_human(
        gh, issue, state,
        _MOVED_AFTER_PUSH_PARK.format(
            mentions=config.HITL_MENTIONS, published=published, head=head,
        ),
        reason=_state._CANDIDATE_MOVED,
        bounded=True,
    )
    state.set(_state._PARK_REASON, _state._CANDIDATE_MOVED)
    return True


def _dirtied_after_the_push(
    gh: _client.GitHubClient,
    issue: Issue,
    state: _pinned_state.PinnedState,
    published: str,
    worktree: Path,
) -> bool:
    """Refuse the handoff when the tree stopped being clean around the push.

    The window the pre-push reading cannot cover, asked of the tree the way
    the proof beside it is asked of the head: the push, the pull-request
    lookup, and the open are three requests long, and the worktree is writable
    for all of them. A descendant the timeout cleanup raced is the commonest
    thing to write there, and it does not have to commit to do damage -- an
    unstaged edit beside a published branch is squashed away or committed on
    top by the stages past the handoff, neither of which measured it.

    So the publication stands and the handoff stops, exactly as it does for a
    head that moved: the branch is on the remote, its pull request carries the
    commit, and the label does not move. What the commit is RECORDED as is the
    caller's, because the two sides promise different things about the remote:
    an initial publication's push opens the pull request and reads the remote
    for itself, while a push onto one the remote already carries knows exactly
    which head it left the branch on and can pin the republication to it.
    """
    tree = _worktree_status._worktree_status(worktree)
    if tree.is_clean:
        return False
    loose = _loose_work(tree)
    log.error(
        "issue=#%s worktree carries work no push published (%s) after %s went "
        "out; refusing to hand an unproven checkout to review",
        issue.number, loose, published,
    )
    _park_for_the_checkout(
        gh, issue, state,
        _DIRTIED_AFTER_PUSH_PARK.format(
            mentions=config.HITL_MENTIONS,
            commit=f"`{published}`",
            loose=loose,
        ),
    )
    return True
