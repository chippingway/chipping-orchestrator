# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A parent whose whole intent is covered by its children.

`umbrella` polls exactly like `blocked` -- same rejected / manually-closed
parks, same dep-graph activation walk -- and differs only in what "every child
resolved" earns. There is no implementation pass to re-enter, so the parent
resolves to `done` and closes instead of flipping to `ready`.

That missing implementation pass is also why the drift check matters more here
than anywhere else: no later stage will ever look at this issue's body again,
so a body edited while children ran would otherwise be closed against the
manifest it no longer describes.

It is also the last boundary at which anything the issue still owes a remote
can be settled, and the first at which the snapshot half CAN be. A parent that
became an umbrella through a late split owes two things -- the branch its
superseded candidate was committed on, and the immutable ref that candidate was
preserved under -- and nothing else ever brings a tick back to either, because
an umbrella polls its children and nothing else. So the all-resolved branch
reconciles what is owed before it closes anything: the branch unconditionally,
and the snapshot under the rule that owns it, since every recorded direct
consumer being terminal is exactly what all-resolved has just made true. The
child scan is handed over rather than re-taken, so proving that costs no
request of its own. A remote that refuses holds the parent open, because an
umbrella closed over an unreclaimed ref is an obligation nobody would ever
settle, while one still open is a retry every tick.

A parent that became an umbrella through a split entered PAST publication owes
one more thing, and it is a question rather than an obligation: the pull
request that split closed has to still be closed. Everything this handler does
for such a parent is licensed by that supersession -- the children it releases
are taking over the work that change carried, and the branch its terminal
reclaims is the one that change points at -- and the transaction that proved
it is several ticks gone. So the record's own publication group, which the
retirement keeps for exactly this, is asked again -- immediately in front of
each act it licenses, never once for the handler. The activation walk asks
before every relabel it makes; the reclamation asks before the delete; the
settlement the terminal waits on asks before anything is SAID; and the
completion asks once more immediately in front of the retirement write, which
is the boundary itself.

The last two are one question at two moments, and both are needed. It is the
answer no ledger carries -- a reclamation that finished owes nothing, so an
entry-driven terminal would fire over a change reopened afterwards, and the
write behind it drops the very group that could have said so. And the sentence
between them is a request of its own, so a reopen can land inside it: refusing
there costs a sentence already gone out, which is why THAT umbrella's sentence
is gated on the thread as well as on the stamp the retirement write puts down.
Only that one. Nothing refuses the others past their sentence, so none of them
pays for a comment listing or carries a receipt nothing would read -- and the
receipt names the cycle and generation, since an operator restarting a
rejected cycle keeps the thread and one scoped to the issue alone would
silence the sentence the cycle after it owes.

All-resolved is not the only reading that makes it true, which is why the same
settlement runs on the way OUT. A child rejected and a child closed by hand
both park this parent for a human, and both closed the child -- which is what
the reclamation rule reads. A park that returned before settling would leave
an owner sitting on a reclaimable ref for as long as the human took, and
nothing sweeps an open umbrella. So the parked path settles from the same
fresh scan that parked it, decides no terminal, and leaves the park exactly as
it was.
"""
from __future__ import annotations

import logging

from github.Issue import Issue

from orchestrator.config import models as _config_models, settings as config
from orchestrator.github import comments as _github_comments
from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    comments as _comments,
    guards as _guards,
    issue_usage as _issue_usage,
    observations as _observations,
    usage as _usage,
)
from orchestrator.workflow.late_split import endings as _endings, state as _late_state
from orchestrator.workflow.late_split.models import LateGeneration
from orchestrator.workflow.stages.decomposition import (
    activation as _activation,
    late_cancellation as _late_cancellation,
    late_cleanup as _late_cleanup,
    late_publication as _late_publication,
    models as _models,
    parents as _parents,
    state as _state,
)
from orchestrator.workflow.state import WorkflowLabel

log = logging.getLogger("orchestrator.workflow")

# Stamped into the sentence a resolved umbrella says, so a terminal refused
# after that sentence went out does not say it again on the next poll. Scoped
# to the exact cycle and generation, because the thread outlives both: an
# operator who takes a settled cancellation's terminal off starts a fresh
# cycle on the same issue, and a receipt naming only the issue would silence
# the sentence that cycle owes its humans. An HTML comment, so it is
# invisible in the rendered thread.
_RESOLVED_MARKER = (
    "<!--orchestrator-umbrella-resolved:issue={issue}"
    ":cycle={cycle}:generation={generation}-->"
)


def _handle_empty_umbrella(
    gh: GitHubClient, issue: Issue, state: PinnedState,
) -> None:
    if state.get(_state._AWAITING_HUMAN):
        return
    _guards._park_awaiting_human(
        gh, issue, state,
        f"{config.HITL_MENTIONS} `{WorkflowLabel.UMBRELLA}` without "
        "recorded children; "
        "manual relabel suspected.",
        reason="umbrella_no_children",
    )
    gh.write_pinned_state(issue, state)


def _complete_umbrella(
    gh: GitHubClient,
    spec: _config_models.RepoSpec,
    issue: Issue,
    state: PinnedState,
) -> None:
    """Say the umbrella is resolved, hand it `done`, and close it.

    `done` is the write that cannot be recovered from: it takes the issue off
    every label the closed-owner sweep queries, so nothing would ever visit it
    again. What makes it safe is not a correction behind it but the write
    AHEAD of it -- one pinned write that stamps the resolution and RETIRES the
    generation together, and past which there is no live cycle for a close to
    end.

    So the latch is asked for the last time immediately before that write,
    with no request standing between the answer and it, and a close observed
    there stops the terminal outright: the owner keeps `umbrella` with the
    mark down, and the ending retires it to `rejected` from a label the sweep
    still queries. A close arriving AFTER it is a human closing an issue this
    orchestrator had already finished -- every child resolved, every
    obligation reclaimed, the cycle over -- which is not a cancellation and
    leaves nothing to correct.

    Every window a crash can land in is one the next pass repairs. Before the
    pinned write the owner is on `umbrella` with a live cycle, which is what
    the sweep and the umbrella poll both already own. After it the owner is on
    `umbrella` with the resolution recorded and no cycle at all, and both of
    those passes finish the terminal from the record rather than starting the
    walk again -- which is also why the closing notice is said once, gated on
    the same stamp.

    That write is itself a request, so what the window observed is asked once
    more BEHIND it -- and taken as the window closes rather than before it, so
    no interval is left for a poll to latch a close in. There the answer is
    not a refusal but a reinstatement: the cycle goes back on the record from
    this call's own memory and is cancelled there, so a close observed while
    the cycle was still live is one the ending can still be entered from.
    """
    if state.get(_state._UMBRELLA_RESOLVED_AT) is None:
        _resolution_said(gh, issue, state)
    if _late_cancellation._latched_close_ends(gh, spec, issue, state):
        return
    state.set(_state._AWAITING_HUMAN, False)
    state.set(_state._PARK_REASON, None)
    state.set(_state._UMBRELLA_RESOLVED_AT, _usage._now_iso())
    if _late_cancellation._latched_close_ends(gh, spec, issue, state):
        return
    if _publication_holds_the_terminal(gh, issue, state):
        return
    live = _retired_cycle(state)
    retiring = _observations.retiring(spec.slug, issue.number, live.cycle_id)
    with retiring.held():
        gh.write_pinned_state(issue, state)
    if _reinstated(gh, issue, state, live, retiring):
        return
    _finished_umbrella(gh, issue)


def _publication_holds_the_terminal(
    gh: GitHubClient, issue: Issue, state: PinnedState,
) -> bool:
    """Whether the change this split closed still lets the terminal fire.

    Asked immediately in front of the retirement write, because that write IS
    the boundary: past it the publication group is gone, and the label and
    close behind it take the issue off every surface a tick would come back
    through. Nothing would ever ask again, and what would be left is an open
    change carrying superseded work under a parent this workflow had declared
    finished.

    The settlement the terminal waits on asks the same question before
    anything is said, so what reaches here is only a reopen that landed inside
    the resolution comment or the latches beside it -- each of them a request,
    and none of them a moment a reading taken in front of them survives.

    A refusal writes nothing at all. The record on the remote is exactly as
    this pass found it: the group intact, the cycle live, the label `umbrella`
    -- so the next tick asks earlier, where refusing costs nothing, and every
    tick after that until a human settles the pull request. The one thing
    already spent is the sentence, and the thread is what stops that repeating.
    """
    undone = _late_publication._release_undone(gh, issue, state)
    if not undone:
        return False
    log.error(
        "issue=#%s holds the terminal its children earned: %s",
        issue.number, undone,
    )
    return True


def _reinstated(
    gh: GitHubClient,
    issue: Issue,
    state: PinnedState,
    live: LateGeneration,
    retiring: _observations.RetiringCycle,
) -> bool:
    """Put back a cycle the retirement write dropped a moment too early.

    The write is a request like every other, so a poll can observe the close
    inside it -- and the reading that observation leaves is durable on the
    thread while the record it names has just stopped naming a cycle. What
    answers that HERE is the generation still in the call's own memory, which
    is the fastest answer there is and the only one a live process needs. The
    correlation the write records beside the clear -- see `_retired_cycle` --
    is for the process that never reaches this barrier at all.

    It goes back exactly as it was and is cancelled from there, so the owner
    keeps `umbrella` with the mark down and the ending retires it to
    `rejected` from a label the closed-owner sweep still queries. The
    terminal is not written: the label and the close below it are what this
    refuses, and everything already said stands.

    Asked OF the window rather than of the latch. The window decides what it
    observed as it closes, under the lock that closes it, so there is no
    interval between the answer and the exit for a poll to latch a close and
    post a receipt in -- and an umbrella with no cycle to retire carries a
    window that advertised nothing and observed nothing.
    """
    if not retiring.observed:
        return False
    log.warning(
        "issue=#%s was observed closed as its umbrella terminal retired "
        "cycle %d; putting that cycle back so the ending has something to "
        "run from",
        issue.number, live.cycle_id,
    )
    _late_cancellation._marked(gh, issue, state, live)
    return True


def _retired_cycle(state: PinnedState) -> LateGeneration:
    """Drop the identity of a cycle that finished, keeping what it recorded.

    The two ledgers are the only thing carried across, exactly as the
    authorized settlement's own retirement carries them: an obligation does
    not stop being owed because the identity written beside it was cleared,
    and the receipts naming the children this split made are what a restart
    reads. What goes is the cycle a close would have ended -- which is the
    whole point of doing it HERE, one write before the terminal label: past
    this there is no live cycle under `done` for anything to have to find.

    The generation it dropped travels back, because the write that makes it
    durable is a request and the barrier behind that request needs something
    to put back.
    """
    live = _late_state.read_late_generation(state)
    _late_state.write_late_generation(state, LateGeneration(
        resources=live.resources,
        consumers=live.consumers,
        opaque_resources=live.opaque_resources,
        opaque_consumers=live.opaque_consumers,
    ))
    if live.is_present:
        _endings.record_retired_cycle(state, live.cycle_id)
    return live


def _resolution_said(
    gh: GitHubClient, issue: Issue, state: PinnedState,
) -> None:
    """Say once that every child resolved, with what the issue cost.

    Gated on the stamp, which is what a resumed terminal has instead of
    memory: a pass that died between this comment and the write that records
    it says it again, and one that died after that write does not. That is
    every umbrella there has ever been, and it stays exactly that.

    A post-publication split's is gated on the THREAD as well, and only that
    one. What the second gate covers is a window only that road has: the
    barrier immediately in front of the retirement write can refuse a terminal
    whose sentence has already gone out, and an umbrella held on a reopened
    pull request would otherwise repeat itself on every poll for as long as a
    human took to settle it. Nothing refuses the others there, so none of them
    pays for a comment listing or carries a receipt nothing would read.

    Walked whole rather than from a watermark, for the reason the split's own
    announcement is: this post moves every watermark the mode keeps past
    itself, so a bounded scan would start above the very comment it looks for.
    """
    generation = _late_state.read_late_generation(state)
    if not generation.has_publication_context:
        _comments._post_issue_comment(
            gh, issue, state, _resolution_body(state),
        )
        return
    marker = _resolved_marker(issue, generation)
    if _resolution_on_thread(gh, issue, marker):
        return
    _comments._post_issue_comment(
        gh, issue, state, f"{_resolution_body(state)}\n\n{marker}",
    )


def _resolution_body(state: PinnedState) -> str:
    """The sentence a resolved umbrella owes its thread, and what it cost."""
    close_body = ":white_check_mark: all children resolved; closing umbrella issue."
    verdict = _issue_usage._format_issue_usage_verdict(state)
    if not verdict:
        return close_body
    return f"{close_body}\n\n{verdict}"


def _resolved_marker(issue: Issue, generation: LateGeneration) -> str:
    """The receipt this cycle's resolution sentence carries."""
    return _RESOLVED_MARKER.format(
        issue=issue.number,
        cycle=generation.cycle_id,
        generation=generation.generation,
    )


def _resolution_on_thread(
    gh: GitHubClient, issue: Issue, marker: str,
) -> bool:
    """Whether THIS cycle has already said its children all resolved.

    Ours, because an HTML comment is invisible in the rendered thread and
    anybody could otherwise post the marker that silences the one sentence
    saying this issue is finished.
    """
    return _github_comments.carries_own_marker(
        gh.comments_after(issue, None),
        marker,
        bot_login=getattr(gh, "_bot_login", None),
    )


def _finished_umbrella(gh: GitHubClient, issue: Issue) -> None:
    """Hand a resolved umbrella its terminal label and close it.

    Both are asked of a record that already says the terminal is due, so
    either can be repeated: a pass that died before the label leaves an owner
    the sweep and the umbrella poll both finish from here, and one that died
    before the close leaves an open `done` issue a human can see.
    """
    gh.set_workflow_label(issue, WorkflowLabel.DONE)
    _closed_umbrella(issue)


def _closed_umbrella(issue: Issue) -> None:
    """Close the issue an umbrella's terminal has just resolved."""
    try:
        issue.edit(state="closed")
    except Exception:
        log.exception(
            "issue=#%s could not close umbrella after children done",
            issue.number,
        )


def _completed_or_cancelled(
    gh: GitHubClient,
    spec: _config_models.RepoSpec,
    issue: Issue,
    state: PinnedState,
    scan: _models._ChildScan,
) -> None:
    """Resolve this umbrella, unless a close arrived while it was settling.

    Every child is resolved, so this is the last tick that could settle what
    the issue still owes a remote -- and the only one that will come back if
    it cannot. A refusal keeps the label, which is the retry.

    The settlement is itself remote work: a branch delete, a ref delete, a
    receipt on each child cut from a reclaimed ref. So the latch is asked
    AGAIN behind it, because `done` is the one write on this path that cannot
    be recovered from -- it takes the issue off every label the closed-owner
    sweep queries and closes it, and a cancellation that bypassed it would be
    stranded for good with nothing left to visit the issue.
    """
    if not _late_cleanup._settled_for_terminal(gh, spec, issue, state, scan):
        return
    if _late_cancellation._latched_close_ends(gh, spec, issue, state):
        return
    _complete_umbrella(gh, spec, issue, state)


def _handle_umbrella(gh: GitHubClient, spec: _config_models.RepoSpec, issue: Issue) -> None:
    """Poll children on an umbrella parent that has no implementation of
    its own.

    Mirrors `_handle_blocked` for the rejected/manually-closed checks and
    the dep-graph activation walk, but the all-done branch resolves the
    umbrella to `done` and closes the issue instead of flipping it to
    `ready` -- there is no implementation pass for an umbrella, so the
    only terminal path is "every child resolved -> close".
    """
    state = gh.read_pinned_state(issue)

    # An umbrella parent NEVER enters implementation -- it just closes when
    # every child resolves -- so a body edit cannot be picked up by any
    # later stage's drift check. Route it back to decomposing here so the
    # new manifest is re-derived against the updated body; without this
    # route-back, an edited umbrella would silently close to `done` against
    # the stale manifest once the old children finished.
    if _parents._route_parent_drift(gh, issue, state):
        return

    children = state.get(_state._CHILDREN) or []
    if not children:
        _handle_empty_umbrella(gh, issue, state)
        return

    scan = _parents._read_child_labels(gh, issue, children)
    if scan is None:
        return
    _acted_on_children(gh, spec, issue, state, scan)


def _acted_on_children(
    gh: GitHubClient,
    spec: _config_models.RepoSpec,
    issue: Issue,
    state: PinnedState,
    scan: _models._ChildScan,
) -> None:
    """Do what this reading of the children earns, if anything still may.

    Split from the read above because the read is where the poll gets its
    chance: a scan is a request per child, and everything here ACTS on what
    it found -- it reclaims a remote a settled split still owes, or it hands
    the issue `done` and closes it, or it releases a child to an agent. A
    close observed inside the scan reaches no other pass, so the barrier is
    the first thing past it.

    `done` is the worst of the three to get wrong, and it is why the barrier
    is here rather than one layer down: that write takes the issue off both
    labels the closed-owner sweep queries, so a cancellation it bypassed
    would never be recorded by anything.
    """
    if _late_cancellation._latched_close_ends(gh, spec, issue, state):
        return
    if _parents._parked_on_children(gh, spec, issue, state, scan):
        # Parked for a human, and still the owner of what its split put on the
        # remote. Every disposition that parks an umbrella closed the child it
        # names -- a rejection and a manual close both do -- so the rule that
        # owns the ref has just been satisfied by the very reading that
        # stopped the tick. Settling here is what keeps that from waiting on a
        # human: nothing else revisits an OPEN umbrella, so a parent parked
        # over a reclaimable ref would hold it for as long as the park stood.
        # It decides no terminal -- the park is the parent's answer, unchanged
        # -- and reports only what it actually did.
        _late_cleanup._settle(gh, spec, issue, state, scan)
        return
    if all(label == _state._DONE for label in scan.labels.values()):
        _completed_or_cancelled(gh, spec, issue, state, scan)
        return
    held = _activation._activate_ready_children(
        gh, spec, issue, state, scan,
    )
    _activation._log_held_children(
        issue, _state._UMBRELLA, scan.children, scan.labels, held,
    )
