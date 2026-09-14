# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Pinned conflict-replay provenance and its two-step writes.

Record the exempt input pair before the rebase destroys it, then the output
commit before publication can lose a receipt. Reads require whole commits
and the publication identity; an unfinished record cannot prove an output.
"""
from __future__ import annotations

from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.late_split import (
    exemption_reading as _exemption_reading,
    formats as _formats,
    payloads as _payloads,
)
from orchestrator.workflow.stages.conflicts import (
    models as _models,
    state as _state,
)


def _records_the_replay(
    ctx: _models._ConflictContext, replayed: _models._Replayed, pr_number,
) -> None:
    """Make what a rebase is about to replace durable, before it runs.

    The two facts the replay destroys, put where a LATER tick can read them: a
    crash between the rebase and the size gate leaves the replayed commit on
    the branch with nothing on the comment explaining it, and the tick that
    finds it there cannot tell a replay from a resolution an agent wrote.

    The PULL REQUEST goes down with them and for the same reason. A rewrite is
    evidence about one publication, and `pr_number` is a field a later tick can
    find pointing somewhere else -- a plan pull request merged and replaced, a
    hand edit, a reuse. Left to be read at recovery time, this branch's replay
    would be offered as a rewrite of whatever pull request the issue had come
    to record, and another open one standing on the same head would satisfy
    every check the permit makes.

    Written only for a branch standing on the commit this issue EXEMPTS, since
    that is the only branch a transfer could ever be granted for -- anywhere
    else the record would be a request spent to protect nothing. Written only
    where every end was read, for the reason a partial claim is refused
    everywhere else here.

    The commit the replay produces is not on it yet and cannot be: it does not
    exist until the rebase has run. `_records_the_replayed_commit` stamps it,
    and until it does this group names no replay any reader may act on.
    """
    number = _payloads.as_identity(pr_number)
    if not (number and replayed.head and replayed.base_sha):
        return
    if not _exemption_reading.is_exempt(ctx.state, replayed.head):
        return
    ctx.state.set(_state._REPLAY_FROM_SHA, replayed.head)
    ctx.state.set(_state._REPLAY_FROM_BASE_SHA, replayed.base_sha)
    ctx.state.set(_state._REPLAY_PR_NUMBER, number)
    ctx.state.set(_state._REPLAY_TO_SHA, None)
    ctx.gh.write_pinned_state(ctx.issue, ctx.state)


def _records_the_replayed_commit(
    ctx: _models._ConflictContext, replayed: _models._Replayed, rebased: str,
) -> None:
    """Stamp the commit a replay produced onto the record it completes.

    The field a later tick matches the branch against, and the reason a stale
    record is inert rather than dangerous: a group naming a commit the checkout
    is not standing on describes a replay that is not the one in hand, so an
    agent's resolution and a rerouted fix commit are answered from nothing.

    Made durable BEFORE the size gate is entered, which is the whole point of
    the write: the window this record exists for is the one between the rebase
    and the permission that gate's own grant persists.

    Silent unless the group standing here is the one this replay began, so a
    tick whose branch was never exempt spends no request -- and a record some
    other head left is not completed with a commit it has nothing to do with.
    """
    if not rebased or not _began_this_replay(ctx.state, replayed):
        return
    ctx.state.set(_state._REPLAY_TO_SHA, rebased)
    ctx.gh.write_pinned_state(ctx.issue, ctx.state)


def _forgets_the_replay(state: PinnedState) -> None:
    """Drop a replay record the publication behind it has spent.

    Staged rather than written, because every road that reaches it is already
    making a durable write of its own: a record left standing costs nothing --
    a later tick acts on it only where the branch is standing on the commit it
    names -- so it is cleared where clearing is free and never for its own
    request.
    """
    for key in _state._REPLAY_KEYS:
        state.set(key, None)


def _began_this_replay(state: PinnedState, replayed: _models._Replayed) -> bool:
    """Whether the group standing here is the one this replay just wrote."""
    recorded = _read_replay(state)
    return (
        recorded is not None
        and recorded.from_sha == replayed.head
        and recorded.from_base_sha == replayed.base_sha
    )


def _read_replay(state: PinnedState) -> _models._RecordedReplay | None:
    """The replay record on this comment, or None where there is none to read.

    Held to the shape each field takes for the reason every other pinned
    commit in this domain is: an abbreviation is not a commit, so a group
    carrying one describes a replay no later reader could check.

    The pair the replay came FROM and the pull request it was made against are
    what make a record readable at all -- without them there is nothing a
    reader could be about, and a number that cannot name a publication scopes
    no evidence to one. The commit it went TO is read the same way and comes
    back empty until the stamp lands, which is what leaves an unfinished
    record naming no branch: the caller acting on one asks for that commit by
    name and an empty answer matches nothing.
    """
    from_sha = state.get(_state._REPLAY_FROM_SHA)
    from_base_sha = state.get(_state._REPLAY_FROM_BASE_SHA)
    number = _payloads.as_identity(state.get(_state._REPLAY_PR_NUMBER))
    if not (number and _commit(from_sha) and _commit(from_base_sha)):
        return None
    to_sha = state.get(_state._REPLAY_TO_SHA)
    return _models._RecordedReplay(
        from_sha=from_sha,
        from_base_sha=from_base_sha,
        to_sha=to_sha if _commit(to_sha) else "",
        pr_number=number,
    )


def _commit(recorded) -> bool:
    """Whether one recorded end is a whole object id and not an abbreviation."""
    return _formats.is_hex_of(recorded, _formats.COMMIT_LENGTHS)
