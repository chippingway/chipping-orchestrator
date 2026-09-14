# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The one refusal in this stage a human cannot answer with words.

What `checkout_guards` holds an issue for is a checkout it could not hand to
review -- one that had left the commit the size gate approved, or one carrying
work beside it that no push would publish -- and neither of those is a
question anybody can reply to. What settles them is the checkout being that
commit and nothing else again, which is an operator's own `git checkout`
between two ticks rather than a sentence on the thread.

So the park writes the approved commit down and this owner is the proof taken
against what it wrote. It is asked on every ordinary tick rather than on a
command, because the recovery is the checkout coming back and nothing else has
to happen for it -- and it is asked about the same two things the refusal was
taken on, since a proof narrower than the refusal it answers would republish
straight back into it.

The park an adjudicated candidate waits on an operator behind asks the same
question one field over, and asks it for the same reason: what the seam past
it would measure is whatever the checkout is standing on, so a head that has
moved is a candidate nobody authorized, published on its own count under a
command that named a different commit. Which commit that park is about is read
off the record rather than off an approval, since a publication that failed
retires the generation and leaves the terms a human agreed to behind.

What the answer LICENSES is the caller's: the republication of an approved
commit, the records it spends, and the relabel behind them all belong to the
disposition that reads this. This owner decides only whether the checkout is
the one that was decided about.
"""
from __future__ import annotations

import logging
from pathlib import Path

from github.Issue import Issue

from orchestrator.git.measurement import commits as _measurement_commits
from orchestrator.git.verification import status as _worktree_status
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.late_split import (
    exemption as _exemption,
    formats as _formats,
    overrides as _overrides,
    payloads as _payloads,
)
from orchestrator.workflow.stages.implementing import state as _state

log = logging.getLogger("orchestrator.workflow")

_HEAD = "HEAD"


def _restored_checkout(
    issue: Issue, state: PinnedState, worktree: Path,
) -> str:
    """The approved commit this checkout is back on, or "" if it is not.

    Both halves of "this checkout" are asked, because the park it answers is
    taken on either of them. A head somewhere else is one; a tree carrying
    work no push would publish -- or one nothing could read at all -- is the
    other, and it is the half that can be true with the head never having
    moved. Republishing on the head alone would take the very reading
    publication refused on and walk it straight back into the same refusal,
    posting a fresh notice every poll for a checkout that has not changed.

    Asked silently and answered silently. A park still waiting costs one local
    `rev-parse` and one `status` a tick and says nothing on the thread, which
    is what lets the question be asked every tick rather than only when a
    human asks it: the checkout coming back is enough on its own, and an
    operator who leaves it where it is is not told so once a poll.
    """
    approved = _payloads.as_hex(
        state.get(_state._APPROVED_SHA), _formats.COMMIT_LENGTHS,
    )
    if not approved:
        return ""
    proved = _measurement_commits._prove_candidate_commit(worktree, _HEAD)
    if not (proved.is_frozen and proved.sha == approved):
        log.debug(
            "issue=#%s is still not on the approved commit %s; leaving the "
            "park where it is", issue.number, approved,
        )
        return ""
    if _worktree_status._worktree_status(worktree).is_clean:
        return approved
    log.debug(
        "issue=#%s is back on the approved commit %s but its tree is not "
        "provably clean; leaving the park where it is",
        issue.number, approved,
    )
    return ""


def _off_the_parked_commit(state: PinnedState, worktree) -> str:
    """Why this checkout is not the commit the authorization park is about, or "".

    The one question the seam past that park cannot ask for it. It measures
    what the checkout is standing on, and a head that has moved off the parked
    commit is a fresh candidate: the exemption does not cover it, the override
    does not name it, so the policy's door is closed and the ordinary road
    measures it and publishes it on its own count. The push then carries a
    commit nobody authorized, under a command that named a different one.

    Which commit the park is about is read off the record rather than
    remembered, since the tick that took the park is long gone. A recorded
    override names it outright and is preferred for that reason -- it is the
    terms a human agreed to, written from the reading that measured them --
    and the exemption behind it answers a park no authorization has reached
    yet. Both are read fail-closed, so a field a hand edit truncated names no
    commit rather than a different one.

    A record naming NO commit is held too, and that is the safe direction
    rather than an omission: a park whose subject nothing can name is one
    nothing here may publish under, and the ordinary road below would publish
    whatever the checkout had become.
    """
    parked_over = _the_parked_candidate(state)
    if not parked_over:
        return "stands over a commit nothing on the record names"
    proved = _measurement_commits._prove_candidate_commit(worktree, _HEAD)
    if not proved.is_frozen:
        return "has a head this host could not read"
    if proved.sha != parked_over:
        return f"has moved off the authorized commit {parked_over}"
    return ""


def _the_parked_candidate(state: PinnedState) -> str:
    """The one commit this park's publication is about, or "" if none is.

    The override first, because it is the only one of the two that says a
    person agreed to something: it names the commit whose terms an operator
    authorized, and it outlives the generation a failed publication retires.
    The exemption answers the park that no authorization has reached yet,
    which is every park before the command arrives.
    """
    authorized = _overrides.read_publication_override(state)
    if authorized is not None:
        return authorized.publication.candidate_sha
    return _exemption.read_exemption(state) or ""
