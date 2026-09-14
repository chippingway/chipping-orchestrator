# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The squash this issue began, answered before anything else runs an agent.

A collapse record is written before the reset that makes one and dropped by
whatever finishes or undoes it, so a comment still carrying one says a rewrite
of this branch is outstanding. What that costs depends entirely on when the
question is asked.

Asked only on the approval road, it is not asked at all on any tick whose
reviewer times out, crashes, or votes `CHANGES_REQUESTED`. A collapse the
remote already carries then never gets the notice, the watermarks, and the
relabel its handoff owes; a record this build cannot read never gets the park
it owes; and the dev is resumed on a branch standing on a commit nobody
accounted for, with `fixing` next.

So it is asked HERE, and it is the same tail the approval road runs: what the
branch is owed does not depend on which reading sent the tick. An issue with
nothing recorded answers False in one dict lookup and costs the stage nothing.

It sits ABOVE every route that can produce an agent -- the drift resume and
the awaiting-human branch both -- because a branch mid-rewrite is not one any
agent may be pointed at. A body edit would otherwise resume the dev on a
checkout standing on a commit this stage has not accounted for, and the
recovery would never be reached again on an ordinary tick: past a refusal the
issue is parked, and the human's reply is claimed by the awaiting-human branch
and spent on the dev instead of on the collapse it is about.

Owning the tick that early is what makes the park its own to answer. The
refusals this recovery takes ARE parks, and it retries them on every tick:
what the notice asks for is a branch reconciled or a comment repaired, and
what says that happened is the recovery getting further, not a reply. Nothing
is re-mentioned while one stands, so the retry costs the thread nothing.

A park the size gate worded behind it is the other kind, and that one is held
rather than re-entered: the gate posts a notice for every reading it cannot
take, so running the recovery back into it would mention a human every poll.
It waits for the reply, and the reply is then spent on the recovery rather
than on a dev resumed over a branch standing mid-rewrite.

Only the terminals sit above it, because a pull request a human merged or an
issue somebody closed is not one to rewrite for at all.

The checkout is read where it is there and rebuilt only where it is not, which
is the one thing this route may not borrow from the reviewer road. That road
ensures a worktree, and ensuring one force-removes a checkout carrying no
commits over its base -- which is exactly what a collapse rewound and not yet
recommitted looks like, with every change it was about in the index. Rebuilt
there, the staged collapse, the tree a human was asked to reconcile, and any
repair they had staged all go, and the record is left over a branch sitting on
its base. A host that lost the worktree has nothing to preserve, so one is
built and the recovery reads whichever history the remote has -- the collapse,
which it finishes, or the commits it was made from, which it squashes afresh.

The handoff a settled collapse leaves is answered beside it, and it needs no
checkout at all. A push that landed and an announcement that went out end the
claim, but the relabel behind them is a second call: failed, it leaves an
issue on `validating` whose branch is already approved, squashed, and
published, and the reviewer below would be a second review of exactly that.
The record left in the claim's place names the commit the move is owed over,
and it is acted on only while the pull request is still standing on it --
anything that moved the publication on has moved the work past the round this
record was about, and it goes rather than sending the branch on unread.
"""
from __future__ import annotations

import logging
from pathlib import Path

from github.Issue import Issue

from orchestrator import config
from orchestrator.git.worktrees import (
    creation as _worktree_creation,
    naming as _naming,
    paths as _worktree_paths,
)
from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.late_split import (
    collapses as _collapses,
    handoffs as _late_handoffs,
)
from orchestrator.workflow.stages.implementing import (
    late_records as _late_records,
)
from orchestrator.workflow.stages.validating import (
    approval as _approval,
    models as _models,
    state as _state,
)

log = logging.getLogger("orchestrator.workflow")

# The park flag every road here reads, and the one reason among them this
# recovery words itself.
_AWAITING_HUMAN = "awaiting_human"


def _recovers_a_recorded_collapse(
    gh: GitHubClient,
    spec: config.RepoSpec,
    issue: Issue,
    state: PinnedState,
) -> bool:
    """Finish a squash this issue began, or say there is none to finish.

    True is a tick this route owned: the collapse was resumed and handed on,
    the branch was put back and a human told, the size gate took the issue, a
    park nobody has answered yet was left exactly as it stands, or the label a
    finished handoff still owed was moved. Whichever of those it was, nothing
    below may run -- the branch an agent would be pointed at is one this stage
    has just decided about.

    False is every other issue on every other tick, and it costs two lookups
    on the pinned comment. Presence rather than readability is what the first
    of them asks, because a record this build cannot read whole is exactly the
    claim that has to reach the refusal rather than be waved past.
    """
    if _collapses.carries_pending_collapse(state):
        return _finished_collapse(gh, spec, issue, state)
    return _finished_handoff(gh, issue, state)


def _finished_collapse(
    gh: GitHubClient,
    spec: config.RepoSpec,
    issue: Issue,
    state: PinnedState,
) -> bool:
    """Take the recovery, or hold the tick for a park it did not word."""
    if _held_by_another_park(gh, spec, issue, state):
        return True
    # The subject the size gate decides about, built over the checkout this
    # route read rather than one rebuilt a layer down: what a recovery may do
    # with a worktree is exactly what `_checkout_of` decided.
    _approval._squashed_and_handed_off(
        _late_records._gate(
            gh, spec, issue, state, _checkout_of(spec, issue, state),
        ),
        _naming._resolve_branch_name(state, spec, issue.number),
    )
    return True


def _checkout_of(
    spec: config.RepoSpec, issue: Issue, state: PinnedState,
) -> Path:
    """The checkout this recovery reads, never one it rebuilt over.

    A worktree already on disk is taken exactly as it stands, and that is the
    whole of what this owner may do with one. The sharpest shape a collapse is
    interrupted in is the branch rewound and not yet recommitted: HEAD is the
    base, so the checkout carries nothing over it, and every change the squash
    was about is in the INDEX. `_ensure_worktree` reuses a checkout only where
    it carries unpushed COMMITS and force-removes it otherwise -- which here
    would take the staged collapse, the tree a human was asked to reconcile,
    and any repair they had staged, and leave the record standing over a
    branch sitting on its base with nothing left to find.

    One is built only where there is none. A host that lost the worktree has
    nothing to preserve, and the recovery then reads whichever history the
    remote has -- the collapse, which it finishes, or the commits it was made
    from, which it squashes afresh.

    A path that is there and is not a checkout is left to the probes below,
    which refuse on what they cannot read: this owner does not repair a
    worktree, and rebuilding one would be the destructive step all over again.
    """
    standing = _worktree_paths._worktree_path(spec, issue.number)
    if standing.exists():
        return standing
    return _worktree_creation._ensure_worktree(
        spec, issue.number,
        branch=_naming._resolve_branch_name(
            state, spec, issue.number,
        ),
    )


def _held_by_another_park(
    gh: GitHubClient,
    spec: config.RepoSpec,
    issue: Issue,
    state: PinnedState,
) -> bool:
    """Whether a park this recovery did not word is still holding the tick.

    A collapse reaches a park through this recovery or through the size gate
    behind it, and the two are answered differently.

    Its OWN park is retried on every tick. The notice tells a human to
    reconcile the branch or repair the comment, and what says they did is the
    recovery running again and getting further -- so waiting for a reply would
    leave a condition that has already been answered standing until somebody
    happened to say so. Nothing is re-posted for it: the park's own writer
    recognizes the reason it filed and stays quiet.

    The gate's park is not this route's to re-enter. It posts a fresh notice
    for every reading it cannot take, so a tick that ran the recovery back
    into it would mention a human every poll. It is held until they reply, and
    the reply then clears the park, is marked consumed, and the recovery is
    taken again -- rather than being spent by the awaiting-human branch on a
    dev resumed over a branch standing mid-rewrite.
    """
    if not state.get(_AWAITING_HUMAN):
        return False
    if state.get(_state._PARK_REASON) == _state._REASON_SQUASH_FAILED:
        return False
    awaiting = _models._AwaitingValidation.build(gh, spec, issue, state)
    if not awaiting.comments:
        return True
    awaiting.clear_park()
    awaiting.consume_comments()
    return False


def _finished_handoff(
    gh: GitHubClient, issue: Issue, state: PinnedState,
) -> bool:
    """Move the label a finished squash's handoff never got to move.

    Reached only where nothing claims an outstanding rewrite, because there is
    none: the push landed, the notice went out, and the watermarks are seeded.
    What is left is a label that says `validating` over work this stage has
    already approved and published, and the reviewer below is what that costs.

    The record has to name a commit before any of that: it is spent on a
    comparison against the head the pull request is standing on, and a value
    that is not a whole object id is one no comparison could be made over --
    which on the road where there is no pull request to read is a relabel
    taken past the reviewer on nothing at all. Such a value is dropped and the
    tick carries on to the round it would have skipped.

    The record is spent only while the pull request is still standing on the
    commit it names. Anything else -- a docs pass that pushed, a fix round, a
    rebase -- has moved the publication past the round this record was about,
    so the record is dropped and the tick carries on to the reviewer rather
    than sending unread work on to `documenting`. That drop rides whatever
    write the rest of the tick makes, since a tick that writes nothing comes
    back to the same reading and answers it the same way. A pull request
    nobody could read decides neither way, and the tick is held for the next
    one to ask again.
    """
    settled = _late_handoffs.read_settled_handoff(state)
    if not settled:
        # Present and unreadable is not the same as absent, and it is the one
        # value nothing may be moved over: a label taken past the reviewer on
        # a string that cannot name a commit is one no comparison could ever
        # have caught. It goes, and the round below runs.
        _late_handoffs.clear_settled_handoff(state)
        return False
    standing = _publication_stands_on(gh, issue, state, settled)
    if standing is None:
        return True
    if not standing:
        _late_handoffs.clear_settled_handoff(state)
        return False
    _approval._hands_to_documenting(gh, issue, state)
    return True


def _publication_stands_on(
    gh: GitHubClient, issue: Issue, state: PinnedState, settled: str,
) -> bool | None:
    """Whether the pull request is still on the commit the handoff settled.

    None where the pull request could not be read at all, which is neither
    answer: a handoff moved on a reading nobody took would relabel over work
    this route cannot see, and one dropped on it would send the branch to a
    reviewer for the same reason. An issue with no pull request has nothing
    that could have moved, so the label is owed as recorded.

    The HEAD is read inside the same guard as the lookup, because a fetched
    pull request is lazy: it asks GitHub nothing, and the request that can
    fail is this attribute read. Left outside, the one failure this reading is
    about would escape the route instead of holding the record.
    """
    pr_number = state.get(_approval._PR_NUMBER)
    if pr_number is None:
        return True
    try:
        standing = gh.get_pr(int(pr_number)).head.sha
    except Exception as error:  # noqa: BLE001 - a read nobody took is not a publication that moved
        log.warning(
            "issue=#%s could not read PR #%s to finish a settled squash "
            "handoff: %s", issue.number, pr_number, error,
        )
        return None
    return (standing or "") == settled
