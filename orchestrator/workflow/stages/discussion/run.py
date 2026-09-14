# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""One agent round of a discussion, opening or resumed, and what it records.

The round runs in the issue's own `issue-N` worktree on its own branch rather
than in a scratch checkout of its own, because the design being discussed is
the design that branch will carry: an operator inspecting a park, and every
later round of the same conversation, look at the tree the discussion actually
read. Nothing here tears it down for that reason, and a resumed round reuses
the tree its predecessor left rather than rebuilding one over it.

Reusing that tree is why the checkout is evidence before it is a workspace, and
why nothing here runs until `round_evidence` has read it. Preparing a checkout
force-removes a dirty tree that carries no commits, so the restorer below is
exactly the step that would destroy the only evidence an operator has of a
round that died before it could park on what it wrote.

Which restorer prepares it is decided by what may be on the
remote: once a PR is open, the branch under discussion is the one it is open
against, and a pruned local ref has to come back from the PR head rather than
from the base branch. A publication in flight says the same thing before there
is a `pr_number` to read it off -- the marker is written before the push and
the number only after the PR -- so that window is settled by asking the remote
whether the branch is there. `_head_sha` is read after the checkout is settled and
before the spawn, because the branch may already carry commits from a stage the
issue passed through before an operator relabeled it here; a base-relative
probe would read those as this round's work and park the agent for something it
never did.

That read is why the SHA is written down rather than only held. A round can
end without any disposition at all -- a mid-run `paused` withholds every one of
them by contract, and a crash takes them with it -- and the next tick then
reuses the same checkout, so a commit the ended round made would become the new
round's own baseline and read as work the branch arrived carrying. Recording
the SHA before the spawn is what keeps that classifiable: on an issue this
stage does not have parked, a non-empty anchor means a round opened and never
finished, and comparing it to the tree says whether it left a commit behind.
On a parked one the same comparison says something narrower and just as
load-bearing -- whether the checkout is still the certified one -- and
`round_evidence` is what asks it, a tick late, for the rounds that never got to
ask it themselves.

The spec rides that same pre-spawn write, so a run that returns no session id
-- a CLI hiccup, an empty `-o` file -- still records which backend and args this
issue's discussion ran under. It is read back on every later round rather than
re-resolved, because every round after the first is the same conversation: a
`DECOMPOSE_AGENT` flip between two of them must not move it onto a backend that
never ran here, and must not hand a session id opened on one CLI to another.
The session id is staged when it arrives and reaches GitHub with the park it
belongs to, so a round nobody will ever see never leaves a conversation pointer
behind -- and the next round resumes the last one that was actually published.
"""
from __future__ import annotations

import logging
from pathlib import Path

from orchestrator.git import branch_transport as _branch_transport
from orchestrator.git.verification import probes as _verification_probes
from orchestrator.git.worktrees import (
    creation as _worktree_creation,
    naming as _naming,
    paths as _worktree_paths,
)
from orchestrator.workflow.engine import (
    run_charge_state as _run_charge_state,
    usage as _usage,
)
from orchestrator.workflow.stages.discussion import models as _models, session as _session, state as _state

log = logging.getLogger("orchestrator.workflow")


def _ensure_round_worktree(run: _models._DiscussionRun, branch: str) -> Path:
    """Prepare the checkout the round reads, restoring a pruned one in place.

    An issue arrives here from anywhere, and once it has a PR the branch it
    arrives on is the one that PR is open against. `_ensure_worktree` rebuilds
    a branch whose local ref has gone -- a host restart, a manual `git branch
    -D`, an operator's cleanup between ticks -- from `<remote>/<base>`, which
    would hand the round a tree with the PR's commits missing and have it
    discuss a design the issue is no longer on. Worse, the anchor written
    straight after would record that truncated tip as what the branch arrived
    carrying, so the relabel guard would later vouch for it.

    `_ensure_pr_worktree` anchors the same restore on `<remote>/<branch>`
    instead, which is where the commits an issue has already published live.
    """
    if _publication_on_the_remote(run, branch):
        return _worktree_creation._ensure_pr_worktree(
            run.spec, run.issue.number, branch=branch,
        )
    return _worktree_creation._ensure_worktree(
        run.spec, run.issue.number, branch=branch,
    )


def _publication_on_the_remote(
    run: _models._DiscussionRun, branch: str,
) -> bool:
    """True when this issue's branch may carry commits only the remote has.

    A recorded `pr_number` is the settled case: the issue is discussed on the
    branch that PR is open against, and rebuilding from `<remote>/<base>` would
    hand the round a tree with the PR's commits missing.

    A publication in flight is the unsettled one, and it is why this is not
    decided on `pr_number` alone. The marker is written durably BEFORE the
    push, and the PR number only after the PR is open, so a tick that died in
    between leaves an issue whose plan is pushed and whose PR is open with
    nothing pinned pointing at either. Lose the worktree and the local ref as
    well -- a host restart, an operator's cleanup, a fresh clone -- and a
    base-anchored restore would rebuild the branch without the published
    commit, refuse the publication it cannot find, and leave the conversation
    free to open another round over the top of a PR nobody retired.

    So the remote is asked, and only for the tick that has a marker standing.
    An answer of "no such branch" is the push that never landed, which the base
    restore is right for; an answer nobody could give is not absence, and
    reading it as one would rebuild over a plan that may well be published.
    """
    if run.state.get(_state._PR_NUMBER) is not None:
        return True
    if not run.state.get(_state._PUBLISHING_SHA):
        return False
    remote_tip = _branch_transport._remote_branch_tip(
        run.spec, run.spec.target_root, branch,
    )
    return remote_tip != ""


def _open_round_checkout(
    run: _models._DiscussionRun, *, resumed: bool,
) -> tuple[Path, str]:
    """Prepare the checkout the round reads, and record what it opened on.

    A resumed round takes the tree its predecessor read whenever it is still
    on disk. That is the tree the operator has been looking at while they
    composed the reply, and the handler's hold already established it is clean
    and still on the anchor -- which is exactly the tree `_ensure_worktree`
    force-removes and rebuilds, for no gain. Only a directory that has gone --
    a host restart, an operator's cleanup between ticks -- is restored, which
    is the same question an opening round asks of a branch it may not find.

    The anchor is staged here rather than by the caller because it is a
    statement about the checkout this just settled: the branch it resolved and
    the tip that branch was at once the tree was in hand. Both are read back
    by a later tick as one record, so neither is written without the other.

    The base goes with them, and it is read from the remote rather than off
    the local `<remote>/<base>` ref: that ref lives in the object store this
    worktree shares with the agent about to run in it, so an agent could move
    it onto its own code commit and have the publication check measure the
    plan against that. What the remote says cannot be rewritten from here --
    and what is recorded is an id this clone can still read, since the diff
    that spends it is local and a base the store lacks would fail it.

    The session pin goes with them, in the one direction knowable before the
    spawn: a resumed round keeps the id it is resuming, and a round resuming
    nothing drops whatever was there, because the conversation it opens has no
    id yet and the previous one's would otherwise be what a publication
    recovered from a crash here named.

    The open flag goes with them too, and it is what a RESUMED round would
    otherwise have no way to say. An opening round leaves the issue unparked,
    so an anchor found on an unparked issue already means "a round opened and
    never reported"; a resumed one runs with the previous park still durable,
    where that reading is unavailable -- a commit under a park is somebody
    else's until something says a round of this stage was in flight. Without
    it, a resumed round that wrote the agreed plan and was then paused or cut
    short would be reported to the humans as a violation to reset away.
    """
    branch = _naming._resolve_branch_name(
        run.state, run.spec, run.issue.number,
    )
    retained = _worktree_paths._worktree_path(run.spec, run.issue.number)
    worktree = (
        retained
        if resumed and retained.exists()
        else _ensure_round_worktree(run, branch)
    )
    head_before = _verification_probes._head_sha(worktree)
    run.state.set(_state._ROUND_BRANCH, branch)
    run.state.set(_state._ROUND_SHA, head_before)
    run.state.set(_state._ROUND_OPEN, True)
    run.state.set(_state._BASE_SHA, _pinned_base_sha(run, worktree))
    if not resumed and run.state.get(_state._DISCUSSION_SESSION_KEY):
        # A round that resumes nothing opens a NEW conversation, and the id it
        # will be known by does not exist yet. Dropping the pin before the
        # spawn is what stops a round cut short from leaving the PREVIOUS
        # round's id standing beside this one's commit: a publication
        # recovered from that would name a conversation that never saw the
        # plan it was publishing.
        run.state.set(_state._DISCUSSION_SESSION_KEY, None)
    # Any publication still marked in flight is superseded here. A round only
    # opens on a tree back at the anchor, so the commit such a marker names is
    # one the operator has already reset away; left standing, it would refuse
    # to publish whatever THIS round goes on to commit for not being it.
    run.state.set(_state._PUBLISHING_SHA, None)
    return worktree, head_before


def _pinned_base_sha(run: _models._DiscussionRun, worktree: Path) -> str:
    """The base commit this round's work will be measured against.

    Read once, before the agent can touch anything, and recorded so the tick
    that publishes measures against the same commit even when it is a later
    one recovering a round that never reported. An unanswerable read is stored
    as no base at all, which the publication check refuses on: a diff has to
    have two ends the agent did not choose.

    What the remote NAMES is only half of what that record has to be worth. The
    check that spends it is a local diff, and the base branch moves on its own:
    the tick fetches it once at the top, and this read can happen long after --
    a handler waits its turn in the scheduler, and every round of a long
    conversation asks again. An id this clone does not hold makes that diff
    fail, and a failed diff comes back as no paths at all, which is the same
    answer a branch that changes nothing gives. A plan written exactly as asked
    would be refused for a race nobody here lost.

    So the OBJECT is required, not just the name. One fetch of the base brings
    whatever the remote has now and every ancestor with it, which is where a
    tip read moments ago lives, and only an id the store then really holds is
    pinned. One still missing after that is a base this round cannot be judged
    against -- the remote rewrote it, or the fetch could not run -- and
    recording it anyway would spend the round on a reading nobody could take.
    """
    base_sha = _branch_transport._remote_branch_tip(
        run.spec, worktree, run.spec.base_branch,
    ) or ""
    if not base_sha or _base_object_available(run, worktree, base_sha):
        return base_sha
    log.warning(
        "issue=#%s base %s of %s is not in the local object store even after "
        "a fetch; the round opens with no base to be measured against",
        run.issue.number, base_sha, run.spec.base_branch,
    )
    return ""


def _base_object_available(
    run: _models._DiscussionRun, worktree: Path, base_sha: str,
) -> bool:
    """True when the pinned base is readable here, fetching once if it is not.

    The fetch lands in `target_root`, whose object store this linked worktree
    shares, so what it brings is readable from the checkout the diff will be
    taken in. Its exit status is deliberately not the answer: a fetch that
    reported success without bringing this commit leaves the caller in exactly
    the position a failed one does, so the store is asked again either way.
    """
    if _verification_probes._commit_present(worktree, base_sha):
        return True
    _branch_transport._authed_target_fetch(run.spec, run.spec.base_branch)
    return _verification_probes._commit_present(worktree, base_sha)


def _open_discussion_round(
    run: _models._DiscussionRun, replies: list | None = None,
) -> _models._DiscussionRound:
    """Run one discussion prompt, recording what it opened on.

    `replies` is the trusted batch a resumed round answers, and `None` on the
    conversation's opening round -- the two the caller can produce, since a
    batch with nothing in it never earns a round at all.

    The spec and the anchor are written before the spawn because they are what
    a round that never comes back is judged by, and the checkout record beside
    them carries the session this round runs under for the same reason. The
    consumed watermark is
    deliberately not in that write: a round that never comes back is replayed,
    and it has to be replayed against the same replies rather than against an
    answer already recorded as read. It is staged after it instead, beside the
    session id the spawn hands back, so both reach GitHub only with the park
    that reports what the round made of them.

    Both round shapes stage one, and each over what its OWN prompt read: a
    resume over the batch it quotes, a full-context round over the thread it
    rebuilt -- which it HAS to, or the comments it just answered would read as
    unanswered replies on the next tick and earn a second round about them.
    The prompt hands its own back rather than being asked a second time, since
    a thread re-read here is a thread minutes older than the one the agent was
    shown.
    """
    session = _session._locked_discussion_session(run.state)
    worktree, head_before = _open_round_checkout(
        run, resumed=replies is not None,
    )
    run.state.set(_state._DISCUSSION_AGENT_KEY, session.agent_spec)
    run.gh.write_pinned_state(run.issue, run.state)
    round_prompt = _session._build_round_prompt(run, session, replies)
    _session._consume_replies(run, round_prompt.consumed)
    discussion_result = _usage._run_agent_tracked(
        run.gh,
        _run_charge_state.AgentRunBudget(issue=run.issue, state=run.state),
        agent_role=_state._DECOMPOSER_ROLE,
        stage=_state._DISCUSSION_STAGE,
        backend=session.backend,
        prompt=round_prompt.text,
        cwd=worktree,
        agent_spec=session.agent_spec,
        resume_session_id=session.session_id if replies else None,
        extra_args=session.extra_args,
    )
    _record_round_session(run, discussion_result, opened_fresh=replies is None)
    return _models._DiscussionRound(
        agent_result=discussion_result, head_before=head_before,
    )


def _record_round_session(
    run: _models._DiscussionRun, discussion_result, *, opened_fresh: bool,
) -> None:
    """Stage the conversation the NEXT round resumes, or the absence of one.

    A resumed round that hands back nothing keeps the pin it ran under: the
    session it continued is the one that answered, and a CLI that simply did
    not echo the id back must not cost the conversation its thread.

    A round opened fresh is the opposite case and overwrites it either way,
    absence included. Whatever it opened is a NEW conversation, and an issue
    can reach a fresh round still carrying a pin -- relabeled out of this stage
    and back, it arrives unparked with the session id its previous discussion
    left. Kept, that id would have the next reply resume a conversation about a
    design the thread has moved on from; cleared, that reply rebuilds the full
    context instead, which is the recovery the sessionless path already exists
    for.
    """
    if discussion_result.session_id:
        run.state.set(
            _state._DISCUSSION_SESSION_KEY, discussion_result.session_id,
        )
    elif opened_fresh:
        run.state.set(_state._DISCUSSION_SESSION_KEY, None)
