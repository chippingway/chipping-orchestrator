# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""One handoff into the publication seam, and what it is held across.

The seam decides what a committed candidate earns, and on the road this owner
serves it decides it for an issue somebody is already waiting on. Its refusals
park under reasons of their own and its notices move the watermark past
whatever they find -- right on every other road, and on this one the operator's
own decision thrown away: the reason taken off is the one they answered, and
the watermark crosses the command they wrote.

So the park is held across the call and put back after it, and held on the
RECORD rather than in the frame that made the call. The seam's writes are
durable before it returns, so a rollback living in memory dies with the
process -- and the poll after a crash would find an issue waiting under a
reason nobody chose, over a watermark that has swallowed a decision, with
nothing anywhere saying what it had been.

Which makes that record the signature of a publication rather than of a park:
the write that moves the label out of this stage spends it, so a record still
carrying it is a handoff that did not publish. Both roads here read it and
both answer it the same way -- the call that came back with nothing pushed,
and the poll that finds a call caught halfway -- because neither has an
outcome to weigh. What the seam did to the park flags says nothing: every road
that clears them without publishing, a bounded transport miss and a close
among them, would otherwise read as a publication and leave an operator's
question dropped and their command consumed.

The reply that ended the park is written down across the call for the opposite
reason, and is spent on the outcome the rollback is never taken on. The seam
consumes the command itself wherever it records an authorization from it, and
two of its roads publish without reading the thread at all -- so the boundary
this park's own reading reached goes onto the record beside the park, and the
write that publishes spends it ahead of the label. Held in the frame instead,
a boundary would be lost by exactly the crash the park is written down for,
on an issue this stage never sees again.
"""
from __future__ import annotations

import logging
import secrets

from github.Issue import Issue

from orchestrator.agents.models import AgentResult
from orchestrator.config import models as _config_models
from orchestrator.git.worktrees import paths as _worktree_paths
from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.stages.implementing import (
    candidate_recovery as _candidate_recovery,
    checkout_recovery as _checkout_recovery,
    late_authorship as _authorship,
    late_command as _late_command,
    models as _models,
    session_read as _session_read,
    state as _state,
)

log = logging.getLogger("orchestrator.workflow")

# What the recovered work is described as where the seam wants a run to
# dispose. No agent produced it: what this hands over is a commit an
# operator authorized, and the sentence says which road it came down.
_AUTHORIZED_RECOVERY = (
    "(orchestrator recovery: publishing the candidate an operator authorized)"
)

# What says who is waiting on this issue and for what, plus how far the thread
# they are waiting on has been read. The three travel together because a park
# put back without its watermark is one whose command has been consumed.
_PARK_FIELDS = (
    _state._AWAITING_HUMAN,
    _state._PARK_REASON,
    _state._LAST_ACTION_COMMENT_ID,
)


def _restores_the_held_park(
    gh: GitHubClient, issue: Issue, state: PinnedState,
) -> bool:
    """Take this park back off the seam, on the record rather than in memory.

    Owning the tick is the point of returning True. What this restores is the
    world the next poll is supposed to read, and acting on it in the same
    breath would act on a reading taken before any of it was true.

    The publication seam refuses for reasons of its own and parks under them
    DURABLY, before anything here gets its answer back. Held only in memory,
    the rollback dies with the process: the poll after a crash finds an issue
    waiting under the seam's reason, over a watermark its notice moved past
    the command, and the operator who fixes the checkout is asked to authorize
    the same commit a second time. So the three fields go down beside the
    receipt before the call, and this is the road that reads them back.

    Restored whatever the record says now, which is the rule the call site
    beside this one follows too: the field being on the record at all is the
    proof that no publication happened, since the write that moves the label
    is what spends it. Nothing the park flags say was decided by anybody --
    the seam clears them on roads that publish nothing, and a tick killed
    mid-call left them wherever it got to.

    Which makes putting it back the safe direction on both sides. A park put
    back over work the seam did publish costs a poll: the gate finds the
    commit already pushed and lets it through without a reading, and the
    command this restores is still the last fresh word, so nobody is asked
    twice. Left off, an operator's decision is consumed and gone -- and an
    issue the seam had already relabelled never comes back through here at
    all, since the dispatcher routes by label and this stage no longer holds
    it.

    The boundary staged beside the park is DROPPED rather than spent, on the
    same reading of what this record means. The write that publishes spends it
    ahead of the label, so one still standing under a held park is a reading
    whose call never got there -- and consuming to it would take the very
    command being put back.
    """
    held = state.get(_state._HELD_PARK)
    if not isinstance(held, dict) or not held:
        return False
    log.info(
        "issue=#%d comes back to a handoff that never finished; putting the "
        "park, its reason and its watermark back where the seam found them "
        "so a decision already made is not asked for twice", issue.number,
    )
    for field in _PARK_FIELDS:
        state.set(field, held.get(field))
    state.set(_state._HELD_PARK, None)
    state.set(_state._HELD_COMMAND, None)
    gh.write_pinned_state(issue, state)
    return True


def _settles_the_park(
    issue: Issue, state: PinnedState, held: dict,
) -> None:
    """What the seam's outcome leaves of this park, and of the reply behind it.

    One question decides both, and it is not what the record says about who is
    waiting: it is whether the PUBLICATION happened. The write that moves the
    label out of this stage spends everything the handoff staged, so a record
    that still carries the held park is a call that never reached it -- and
    one that does not is a branch on the remote and an issue this stage no
    longer holds.

    Read off the park flags instead, every road the seam takes that clears
    them WITHOUT publishing reads as a publication: a bounded transport miss
    counting a quiet retry, a close that ended the cycle, a record this commit
    is superseded by. Each of those leaves the operator still owed the answer
    they are waiting for, and each would have their command consumed and the
    park dropped -- so the exemption nobody stands behind publishes on the
    next poll under nobody's authority at all.

    So the park, its reason and its watermark go back exactly as this call
    found them wherever it did not publish, whatever the record says now and
    whatever the seam refused for. The notice the seam posted stays on the
    thread, which is what tells the operator what to fix, and the boundary
    staged beside the park is DROPPED rather than spent: consuming to it would
    take the very command being put back.

    Putting one back over work the seam did publish would cost a poll -- the
    gate finds the commit already pushed and lets it through without a
    reading, and the restored command is still the last fresh word, so nobody
    is asked twice -- which is why this fails in this direction.
    """
    if state.get(_state._HELD_PARK) is None:
        return
    log.info(
        "issue=#%d came back from the publication seam with nothing "
        "published (%s); putting the park, its reason and its watermark back "
        "where the seam found them so a decision already made is not asked "
        "for twice",
        issue.number, state.get(_state._PARK_REASON) or "no park at all",
    )
    for field in _PARK_FIELDS:
        state.set(field, held.get(field))
    state.set(_state._HELD_COMMAND, None)


def _holds_what_the_call_may_lose(
    state: PinnedState, held: dict, answer: _late_command._Answer | None,
) -> None:
    """Write down what the seam can take from this park before it is entered.

    Two facts about a call that has not happened yet, and the record is the
    only place either survives it. What the park WAS is what a later poll puts
    back where the seam refused under a reason of its own. How far the reading
    behind the command GOT is what the write ending this stage's hold on the
    issue spends, since two of the seam's roads publish without reading the
    thread at all and the reply that ended the park would go to the next stage
    unread.

    Both go down BEFORE the call because both windows are open by the time it
    returns: the seam's refusal is durable, and its label move is made, before
    anything here gets an answer back.

    A tick with no reply to spend records no boundary, which is the road a
    receipt still owed comes down. Its handoff has a park to put back and
    nothing to consume, and a boundary written from nothing would be one the
    next reading is measured against.
    """
    state.set(_state._HELD_PARK, held)
    state.set(
        _state._HELD_COMMAND, None if answer is None else answer.watermark,
    )


def _publishes_under_the_park(
    gh: GitHubClient,
    spec: _config_models.RepoSpec,
    issue: Issue,
    state: PinnedState,
    answer: _late_command._Answer | None,
) -> None:
    """Hand the committed work to the seam, and keep this park whatever it does.

    The seam refuses for reasons of its own -- a tree that stopped being
    provably clean between the reading above and its own, a candidate it could
    not measure -- and each refusal parks under a reason of its own and posts
    a notice that moves the watermark past whatever it finds. On every other
    road that is exactly right. Here it takes this park's reason off and
    consumes the command still standing, so an operator who fixes the checkout
    is asked to authorize the same commit again on an issue now waiting for a
    different reply.

    The questions above cannot close that on their own, because the sharpest
    of them is a RACE: the tree is read once here and again inside the seam,
    and everything between is time something can write in. So the park is put
    back rather than merely guarded -- whatever the seam refused for, and
    however it refused.

    Put back on one question, and it is not what the record says about who is
    waiting: it is whether the PUBLICATION happened. The write that moves the
    label out of this stage spends everything the handoff staged, so a record
    still carrying the held park is a call that never reached it. Read off the
    park flags instead, every road the seam takes that clears them WITHOUT
    publishing -- a bounded transport miss counting a quiet retry, a close
    that ended the cycle, a record this commit is superseded by -- would read
    as a publication and leave the operator's question dropped and their
    command consumed.

    So wherever nothing published, the pair that says who is waiting and for
    what goes back exactly as this call found it, and the watermark with it,
    since a command consumed is a decision thrown away -- the notice the seam
    posted stays on the thread, which is what tells the operator what to fix.
    The boundary staged beside them is DROPPED rather than spent there:
    consuming to it would take the very command being put back.

    Where the publication DID happen, that same write spent the boundary
    ahead of the label, which is why the reading behind the reply is handed in
    -- and written down with the park rather than applied on the way out,
    since the write that moves the label is the last one this stage makes on
    the issue.

    The checkout is named here rather than handed in, and that is not a
    convenience: the guard above read a tree, and the seam reads it again, so
    nothing about the earlier reading survives the call. What both name is the
    same path, which is a fact about this issue rather than about either read.

    The COMMIT does travel, and for the opposite reason. The guard above
    proved the checkout on the one this park is about, and the gate reads the
    head again for itself; between the two the worktree is writable, so a
    commit landing there would be measured and pushed as this park's while the
    command and the override name another. Named on the work, the gate refuses
    it before anything is persisted or pushed, and the park comes back.

    What the seam did not account for is left exactly where it is. A receipt
    still outstanding when the call returns names a sentence of ours the seam
    posted and no id write recorded, and it is the only thing the next poll
    can find that comment by -- so it outlives this call and is spent by the
    repair that puts the comment into the authorship ledger.

    Held on the RECORD rather than in this frame, because the seam's refusal
    is durable before this call returns and a rollback that lives in memory
    dies with the process. A tick killed in that window would otherwise leave
    an issue parked under the seam's reason, over a watermark past the command
    -- and no later poll could know what it had been. Written down, the poll
    after the crash puts it back and the operator is never asked twice.
    """
    held = {key: state.get(key) for key in _PARK_FIELDS}
    # All three go down BEFORE the call, because every window it opens is
    # already open by the time it returns: the seam writes its own refusal,
    # posts its own first sentence, and moves the label before anything here
    # gets an answer back. What the park WAS is what a later poll puts back;
    # how far its reading got is what the write past the label spends; and the
    # commitment is what a later poll finds the sentence by, which it can only
    # do if it was recorded before the seam could say anything at all.
    #
    # The sentences after the first mint and record their own, one at a time,
    # inside the client below: a single secret could not tell two of our own
    # apart afterwards.
    opening = secrets.token_hex(_authorship._PROOF_BYTES)
    _holds_what_the_call_may_lose(state, held, answer)
    _authorship._records_a_commitment(state, _authorship._commits_to(opening))
    gh.write_pinned_state(issue, state)
    saying = _authorship._StampsWhatItPosts(gh, issue, state, opening)
    _candidate_recovery._publish_committed_work(
        saying, spec, issue, state,
        _models._RecoveredWork(
            AgentResult(
                session_id=_session_read._read_dev_session(state)[-1],
                last_message=_AUTHORIZED_RECOVERY,
                exit_code=0,
                timed_out=False,
                stdout="",
                stderr="",
            ),
            _worktree_paths._worktree_path(spec, issue.number),
            _checkout_recovery._the_parked_candidate(state),
        ),
    )
    _settles_the_park(issue, state, held)
    # The held park goes; the receipts do NOT. Each is dropped by the write
    # that records the id of the comment it went out on, so one still standing
    # here is a sentence of ours the seam said and no id accounts for -- the
    # one API call a crash can land in. Cleared with the park, nothing would
    # ever put that comment in the authorship ledger, and the next poll reads
    # the orchestrator's own notice as a human asking for a change: a
    # developer paid to answer it, and the watermark moved past whatever a
    # human wrote underneath. What answers them instead is the repair the next
    # poll runs ahead of its own routing.
    state.set(_state._HELD_PARK, None)
    saying.forgets_an_unspoken_promise()
    gh.write_pinned_state(issue, state)
