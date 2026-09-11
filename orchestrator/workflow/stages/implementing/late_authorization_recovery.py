# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Recover an authorization park without consuming a decision that cannot publish.

A command authorizes one committed candidate. Before handing it to the
publication seam, prove the checkout exists, is clean, and still carries that
commit. An unpublishable checkout leaves the park and command exactly as
found, so restoring it never asks the operator for the same decision twice.
"""
from __future__ import annotations

import logging

from github.Issue import Issue

from orchestrator import config
from orchestrator.git.verification import probes as _verification_probes
from orchestrator.git.worktrees import paths as _worktree_paths
from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.stages.implementing import (
    checkout_recovery as _checkout_recovery,
    late_command as _late_command,
    late_parks as _late_parks,
    late_rollback as _rollback,
    state as _state,
)

log = logging.getLogger("orchestrator.workflow")


_AUTHORIZATION_PARK = _late_command.PARK_UNAUTHORIZED_EXEMPTION


def _try_recover_unauthorized_exemption_park(
    gh: GitHubClient, spec: config.RepoSpec, issue: Issue, state: PinnedState
) -> bool:
    """Republish an adjudicated candidate an operator has now authorized.

    The way out of the park the size gate takes when a commit is exempt on a
    record no human stands behind. What it was missing was a person rather
    than a reading, so what settles it is the command they wrote -- and the
    work is committed already, so this must never reach the spawn below.

    The command is recognized here and acted on where the READING is, because
    that is where the terms of an authorization come from: an operator
    authorizes a change of this size against this ceiling, and only the owner
    that counts one can say either. So this owes the routing and nothing else
    -- the committed work goes back through the same publication seam it came
    out of, and the gate answer decides what happens, including the sentence a
    command naming another commit earns.

    Every tick of a standing park comes through here, not only one carrying a
    command, because this is the only road that reaches the gate at all: an
    issue behind this park has committed work and no run to dispose, so
    nothing else would ever measure the candidate again or say a sentence the
    park still owes. What each tick costs is decided by what the thread says.

    A reply whose last word is not the command is left alone, and it is the
    ordinary resume that feeds it to the developer -- the notice on this side
    of publication offers exactly that. A thread with nothing new on it and
    nothing owed is held where it stands without a reading, a request, or a
    word: a park waiting on a person answers the same way every poll until one
    arrives, and re-measuring to say nothing would buy a diff a tick.

    The park flags are deliberately NOT cleared here. The write that records
    the authorization is the write that takes them off, so a tick that could
    not fingerprint the pair leaves the issue exactly as parked as it found
    it, rather than durably unparking an issue nothing published.

    The reading goes with the handoff for the other half of that. Where the
    seam records an authorization it consumes the command in the same write,
    but two of its roads publish without reading the thread at all -- a
    candidate the ceiling now lets through, and one an authorization already
    on the record covers -- and a command left standing on an issue that has
    moved to `validating` is read there as somebody's fresh feedback. What
    this reading can promise is the boundary it reached and nothing past it.

    A checkout that is GONE is the one road that publishes nothing and it
    writes nothing either, which is what separates this park from the
    measurement one beside it. There the answer was a bare continue, spent by
    the tick that read it, so re-parking under a reason of its own costs
    nobody anything. Here the answer is a decision a human made about one
    commit: a fresh park would take this park's reason off, and its notice
    would move the watermark past the command that is still standing -- so an
    operator who put the worktree back would be asked to authorize the same
    change a second time, on an issue now waiting for a different reply
    entirely. Held silently instead, the park, the command and the record are
    all still there, and the poll after the checkout comes back publishes on
    them. It still owns the tick, because the road below would pay for a
    developer over an implementation that is committed already.
    """
    if not _stands_on_the_park(state):
        return False
    read = _late_command._reads_the_thread(gh, issue, state)
    if _nothing_to_answer(read, state):
        # Guidance is handed back and silence is held, and the difference is
        # what the notice on this side of publication promised: a reply that
        # is not the command reaches the developer through the ordinary
        # resume, while a thread nobody has written on gets the same answer
        # every poll and buys no reading to say it. Both come off the one
        # reading above, since a command that landed between two of them is a
        # command handed to a road that cannot act on it and consumed there.
        return not read.spoke
    wt = _worktree_paths._worktree_path(spec, issue.number)
    unpublishable = _unpublishable_checkout(state, wt)
    if unpublishable:
        log.info(
            "issue=#%d was authorized to publish its adjudicated candidate "
            "and its checkout %s; holding the park and the command as they "
            "stand rather than asking for the same decision twice",
            issue.number, unpublishable,
        )
        return True
    _rollback._publishes_under_the_park(gh, spec, issue, state, read.answer)
    return True


def _stands_on_the_park(state: PinnedState) -> bool:
    """Whether somebody is waiting on this issue for an authorization."""
    return (
        bool(state.get(_state._AWAITING_HUMAN))
        and state.get(_state._PARK_REASON) == _AUTHORIZATION_PARK
    )


def _nothing_to_answer(
    read: _late_command._Reading, state: PinnedState,
) -> bool:
    """Whether this poll of a standing park has nothing of its own to do.

    False for the two ticks that owe something, and both are answered the same
    way: through a fresh reading of the candidate, since that is where the
    terms come from. A command is a decision to act on. A receipt still on the
    record is a sentence a dying tick never got out -- the notice this park
    was taken with, or the answer a refused command earned -- and the words
    of it are worded from the reading too.

    A publication still OWED is the third, and it is the one nobody says
    anything about. An approval on the record names a commit this stage
    decided to push and has not pushed -- what the gate's own reading retires
    a small candidate on, or what an authorized settlement records -- and it
    is dropped by the handoff that spends it, so one still standing is a push
    that did not land. The park it stands under says nothing about that: a
    publication refused after the flags came off puts them back without the
    trigger the tick was answering, and a park re-entered on a thread nobody
    has written on would hold a decided commit unpublished for as long as the
    issue lived.

    True leaves the tick to its caller, which either holds it where it stands
    or hands it to the resume, depending on whether anybody has spoken. The
    reading is handed in rather than taken here because that same reading is
    what decides which of those two the caller does, and a thread read twice
    can answer the two questions from two different threads.
    """
    if read.answer is not None:
        return False
    if _late_parks._approved_commit(state):
        return False
    return not state.get(_state._HELD_RECEIPT)


def _unpublishable_checkout(state: PinnedState, worktree) -> str:
    """Why an authorized candidate may not reach the seam yet, or "".

    Everything that seam would refuse, asked HERE instead -- and asked only on
    this road, because of what its refusal costs on this one. The seam parks
    under reasons of its own and the notice it posts moves the watermark past
    whatever it finds. On every other road that is exactly right. Here it
    would take this park's reason off and consume the command still standing
    on the thread, so an operator who fixed the checkout would be asked to
    authorize the same commit a second time, on an issue now waiting for a
    different reply entirely.

    The checkout has to be on this host, its tree has to be PROVABLY carrying
    nothing loose, and its head has to be the commit this park is about. A
    reading that established nothing is refused beside a tree that is dirty,
    since it is not evidence of a clean one -- and none of the three is
    anybody's decision, so each leaves the park, the command and the record
    exactly as found, and the poll after an operator fixes it publishes on the
    command they already wrote.

    The HEAD is asked because nothing below would ask it AGAINST this park on
    its own. A head that has moved is a candidate the exemption does not cover
    and the override does not name, which takes the ordinary road and
    publishes on its own count: an operator who authorized one commit would
    have another pushed under their command, and the thread would say the
    first one shipped. So the commit this reading proves is NAMED on the work
    handed over, and the gate holds its own head read to it -- the worktree is
    writable between the two, and asking here alone would leave that window
    open.

    Everything the seam refuses PAST this reading is answered by the park
    being put back rather than by a wider question here: the tree is read
    again inside the seam, so no reading taken before it can promise what that
    one finds.
    """
    if not worktree.exists():
        return "is not on this host"
    tree = _verification_probes._worktree_status(worktree)
    if not tree.is_clean:
        return (
            "carries work no push would publish" if tree.readable
            else "has a tree this host could not read"
        )
    return _checkout_recovery._off_the_parked_commit(state, worktree)
