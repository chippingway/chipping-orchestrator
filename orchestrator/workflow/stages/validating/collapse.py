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
record was about, and it goes rather than sending the branch on unread. A
commit is not the whole of what was approved, though: a developer report that
changed on that same commit is work no reviewer has read, and so is an issue
edited since, so the record is also acted on only while the report recorded
as current is the one the approval covered and still reads, at its location,
as it settled, and the issue read afresh still carries the requirements the
approval was given. And it is acted on only over the approval's evidence
answering for that commit: carried there by the squash tail, settled by the
reconciliation ahead of this stage, and proved whole again here before the
label moves -- or, where the tail could not read what deciding the carry
needs, decided here by the same rule (`squash_evidence`), the move left for
the next tick. That proof goes ahead of the approval's coverage, so the pull
request is read last, immediately ahead of the move.
"""
from __future__ import annotations

import logging
from pathlib import Path

from github.Issue import Issue

from orchestrator.config import models as _config_models
from orchestrator.git.worktrees import (
    creation as _worktree_creation,
    naming as _naming,
    paths as _worktree_paths,
)
from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import verification_durable as _durable, verification_proof as _proof
from orchestrator.workflow.late_split import (
    collapses as _collapses,
    handoffs as _late_handoffs,
)
from orchestrator.workflow.stages.implementing import (
    late_records as _late_records,
)
from orchestrator.workflow.stages.validating import (
    approval as _approval,
    handoff as _handoff,
    models as _models,
    review_coverage as _review_coverage,
    squash_evidence as _squash_evidence,
    state as _state,
)

log = logging.getLogger("orchestrator.workflow")

# The park flag every road here reads, and the one reason among them this
# recovery words itself.
_AWAITING_HUMAN = "awaiting_human"


def _recovers_a_recorded_collapse(
    gh: GitHubClient,
    spec: _config_models.RepoSpec,
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
    on the pinned comment and a reading of the current evidence record.
    Presence rather than readability is what the first of them asks, because
    a record this build cannot read whole is exactly the claim that has to
    reach the refusal rather than be waved past. The last is for evidence
    carried onto a head it did not run on whose review no longer stands,
    which is invalidated here ahead of any round (`_retires_an_unanswered_carry`).

    Neither road holds a returned verdict: no reviewer ran behind them, so a
    verdict persisted since the approval they finish -- a later round's -- is
    left for the road that finishes it, and holds the relabel
    (`approval._hands_to_documenting`). Each is measured from the comment as
    this tick read it (`handoff._Held`).
    """
    held = _handoff._Held(None, comment=dict(state.data))
    if _collapses.carries_pending_collapse(state):
        return _finished_collapse(gh, spec, issue, state, held)
    return _finished_handoff(gh, spec, issue, state, held) or _retires_an_unanswered_carry(gh, issue, state)


def _retires_an_unanswered_carry(gh: GitHubClient, issue: Issue, state: PinnedState) -> bool:
    """Invalidate evidence carried onto a head that no longer answers for it; True where the tick went on it.

    An approval squash's carry answers for the head it was carried onto only
    on the approval's word, and every reader about to move that approval on
    refuses one the approval's claim no longer names, or whose review subject
    no longer stands (`squash_evidence.carry_unanswered`): the documenting
    stage hands the issue back here, the ready ping is held, and `in_review`
    hands a stale approval back. This stage owns the carry, so it is
    invalidated here, ahead of any round it could be handed to, and the
    approval it was carried for with it (`squash_evidence._invalidates`), so
    no reader takes that approval for one recorded before approvals named
    evidence; an approval another road recorded in its place, of another
    subject, stands. That is staged on the comment read afresh, held to every
    record the evidence is bound through -- the report debt its review
    subject stands only without among them -- and to the approval's claim
    (`squash_evidence.CARRY_ANSWERS_ON`), and committed guarded by that
    reading (`verification_durable`), owning only what it retires
    (`squash_evidence.INVALIDATES`) -- every other field, a returned verdict
    or a usage total among them, is kept as the comment carries it -- in a
    commit of its own, the tick spent on it so the round below starts from the
    comment as written. A comment that moved, before that reading or under the
    commit, or will not read, and a commit nobody confirmed, hold the tick for
    the next to ask again. A retirement the comment has no room for leaves the
    record, which every reader refuses, and the approval is still retired in
    that commit -- the comment only shrinks by it -- so restoring the room
    later moves nothing on over it; the tick carries on, and a comment already
    carrying that refusal is sent nothing.
    """
    if not _squash_evidence.carry_unanswered(state):
        return False
    durable, refused = _durable.durable_comment(gh, issue, state, _squash_evidence.CARRY_ANSWERS_ON)
    if refused is None:
        guard = _durable.guarded(durable, _squash_evidence.INVALIDATES, _squash_evidence.CARRY_ANSWERS_ON)
        retired = _squash_evidence._invalidates(durable)
        log.log(
            logging.INFO if retired else logging.ERROR,
            "issue=#%s its carried verification evidence no longer answers for the review it was carried "
            "for; %s, and retiring the approval it was carried for where that still stands",
            issue.number, "invalidating it" if retired else "no room to invalidate it",
        )
        refused = _durable.lands(gh, issue, state, guard, durable)
        if refused is None:
            return retired
    log.info(
        "issue=#%s is not invalidating the carried verification evidence that no longer "
        "answers: %s", issue.number, refused.refusal,
    )
    return True


def _finished_collapse(
    gh: GitHubClient,
    spec: _config_models.RepoSpec,
    issue: Issue,
    state: PinnedState,
    held: _handoff._Held,
) -> bool:
    """Take the recovery, or hold the tick for a park it did not word."""
    if _held_by_another_park(gh, spec, issue, state):
        return True
    # The subject the size gate decides about, built over the checkout this
    # route read rather than one rebuilt a layer down: what a recovery may do
    # with a worktree is exactly what `_checkout_of` decided. No reviewer ran
    # on this road, so a squash made afresh references the pull request the
    # pinned comment records.
    _approval._squashed_and_handed_off(
        _late_records._gate(
            gh, spec, issue, state, _checkout_of(spec, issue, state),
        ),
        _naming._resolve_branch_name(state, spec, issue.number),
        state.get(_approval._PR_NUMBER),
        held,
    )
    return True


def _checkout_of(
    spec: _config_models.RepoSpec, issue: Issue, state: PinnedState,
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
    spec: _config_models.RepoSpec,
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
    gh: GitHubClient,
    spec: _config_models.RepoSpec,
    issue: Issue,
    state: PinnedState,
    held: _handoff._Held,
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

    The report and the requirements are asked before the pull request: a
    developer report settled on this commit after the approval -- or one the
    approval's record no longer agrees with, or the approved one edited or
    removed at its location since -- is a subject nobody reviewed, and so is
    an issue whose requirements are not the revision the approval was given
    and the baseline holds. Either way the record goes on the same terms as a
    moved head, and the round below answers it: the reviewer for a report,
    the drift check for an edit. A location or an issue nobody could read
    holds the tick, as an unread pull request does. The move itself is taken
    only where the pinned comment, read again after every one of those
    requests, still carries the report, pull-request, verdict, and evidence
    records in hand and the review subjects this tick read, and no returned
    verdict waits beside the handoff (`approval._hands_to_documenting`).

    And only over evidence answering for the commit it names, which is asked
    first: the same rule the squash tail holds its own move to
    (`squash_evidence`). A carry that tail recorded is published and settled
    by this tick's reconciliation ahead of this handler, and before the label
    moves over it that settled carry is proved whole again -- the trees, the
    applicable review subject, the context, the publication, the report, and
    the requirements -- so the label moves, with no second reviewer, only
    where it still answers. A refusal invalidates it and drops the record in
    a write of its own, for the round below on the next tick, whatever else
    moved beside it: evidence a moved context, tree, or head leaves behind is
    retired on this road as on the tail's. One that reconciliation refused is
    abandoned with its approval, which the approval's coverage refuses, and
    the record goes for the round below; one it stood down on with the carry
    still owed -- no room on the comment to settle into, before the post or
    behind it -- holds the tick with the record kept, for a later tick to
    settle it (`squash_evidence.carried_onto`).
    Where the tail could not decide -- a pull request or artifact nobody
    could read -- the carry is decided here, over the same proofs, and
    recorded or refused in a write of its own laid over the comment as read
    then, the move left for the next tick; a reading nobody could take again
    holds the tick.

    The proof is requests of its own, long enough for a push, so the coverage
    above is asked behind it rather than ahead: the pull request is the last
    thing read before the move, and the comment read behind it has to still
    carry the review subjects the proof was taken over. A record the coverage
    drops takes a settled carry onto its commit with it, since that evidence
    answers for the commit only on the approval's word
    (`squash_evidence.SquashEvidence.drops_the_handoff`).
    """
    settled = _late_handoffs.read_settled_handoff(state)
    if not settled:
        # Present and unreadable is not the same as absent, and it is the one
        # value nothing may be moved over: a label taken past the reviewer on
        # a string that cannot name a commit is one no comparison could ever
        # have caught. It goes, and the round below runs.
        _late_handoffs.clear_settled_handoff(state)
        return False
    carried = _squash_evidence.carried_onto(_proof.ProofReading(gh, spec, issue, state), settled)
    if not carried.answers:
        if not carried.holds and _handoff._holds_its_records(
            gh, issue, state, "record what the evidence its approval rests on owes the squash", held,
        ):
            carried.stages(state, issue.number)
            gh.write_pinned_state(issue, state)
        return True
    standing = _handoff_stands(gh, issue, state, settled)
    if standing:
        _approval._hands_to_documenting(gh, issue, state, held)
    elif standing is False:
        carried.drops_the_handoff(state)
    return standing is not False


def _handoff_stands(
    gh: GitHubClient, issue: Issue, state: PinnedState, settled: str,
) -> bool | None:
    """Whether what the settled handoff was owed over still stands, None unread.

    The approval -- the evidence it was proved over still the current,
    passing evidence where it was proved over any, the report it covered
    still the current one, still reading at its location as it settled, and
    the issue still carrying the requirements it was given -- and the pull
    request, still standing on the commit the handoff named
    (`review_coverage._approval_holds`).
    """
    covered = _review_coverage._approval_holds(gh, issue, state, settled)
    if covered is False:
        log.info(
            "issue=#%s carries verification evidence, a developer report, "
            "requirements, or a head its approval did not cover; dropping the "
            "settled squash handoff for the round below", issue.number,
        )
    return covered
