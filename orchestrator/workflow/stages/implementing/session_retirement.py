# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The developer conversations retired for good, and the pins that may not bring one back.

`session`'s rotations retire a transcript for being long or quiet. They drop
the pinned id and nothing remembers it, which is all a healthy conversation
that grew too big needs. A conversation a run showed to have FAILED needs more:
its backend can hand the same id back on a later spawn, and the counters the
rotations read are zeroed by publication and by the rotations themselves, so a
retirement held in those or in the pin alone is undone by the next commit that
ships. It is recorded in a field nothing else writes
(`state._DEV_SESSION_RETIREMENT`) instead:

* `_retire_dev_session` records the id -- every pinned id, where it is handed
  none -- marks a fresh conversation owed, and clears the active and legacy
  pins the way every rotation does (`_clear_dev_session_pins`), keeping the
  pinned `dev_agent` command.
  Retiring a conversation already recorded only unpins it where something
  pinned it again, so the primitive is idempotent per conversation.
* `_retired_session_reason` is asked first by the planned and resolved reads
  on `session`: an id the record names, or any id pinned while recovery is
  owed, is never resumed, whatever the counters say.
* `_held_retirement` counts that pin as retired too, and every road that
  clears it records it first (`_clear_dev_session_pins`), so a record nobody
  can fully read -- which may name no id of its own -- still refuses the
  conversation it was owed over once the pin is gone. Both pin fields count
  (`session_read._pinned_session_ids`): a legacy `codex_session_id` is hidden
  from the session read once `dev_agent` is pinned, which a first spawn does
  before its run, and is still a conversation the recovery was owed over.
* `_pin_dev_session` is the write every fresh developer conversation is
  pinned through (`session._persist_dev_session_after_run`, which the first
  spawn on `spawn` calls as well as a resume). A missing id and a
  retired one are refused with recovery left owed, so the next run is fresh
  again; a distinct id is pinned with its own resume budget and ends the
  recovery. The retired ids stay recorded after that, a late restart's
  projection included (`decomposition/late_restart_state`): it drops the pins
  through `_clear_dev_session_pins` and `dev_agent` with the cycle, and keeps
  this record. The one continuation an incomplete AGY run earns (`execution`)
  is refused a retired id the same way, before that pin is asked.
* `_commit_dev_session_retirement` lands the same retirement on the pinned
  comment through the guarded commit (`engine/pinned_commit.py`), over a fresh
  reading and owning only the fields a retirement writes, with every id the
  tick's own record names retired over that reading too. It survives a tick
  whose own write is discarded, without carrying that tick's watermarks or the
  park it was about to clear, and without dropping a conversation the tick
  retired and never wrote; the tick takes back what it landed, so its own
  write does not drop an id another road retired meanwhile.

Nothing here decides THAT a conversation failed, and nothing touches the
worktree, the branch, the retry gates, or the run ledger: the caller that
classified the result names the conversation and the reason -- for an
exhausted account quota, `quota_retirement`, through the guarded commit as
every developer attempt returns.
"""
from __future__ import annotations

import copy
import logging

from github.Issue import Issue

from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    pinned_commit as _pinned_commit,
    pinned_commit_models as _commit_models,
)
from orchestrator.workflow.stages.implementing import (
    session_read as _session_read,
    state as _state,
)

log = logging.getLogger("orchestrator.workflow")

_SESSION_IDS = "session_ids"

_REASON = "reason"

_RECOVERY_PENDING = "recovery_pending"

# Why the pin a fresh conversation was owed over is retired, where the record
# owing it says no reason of its own.
_OWED_PIN = "pinned while a fresh conversation was owed"

# Every field a retirement writes: its record, the two pins it clears, the
# command it pins in place of a legacy one, and the per-session counters it
# zeroes. The guarded commit owns exactly these, so everything else on the
# comment -- a park, a watermark, the run ledger -- is the fresh reading's.
_RETIREMENT_FIELDS = frozenset((
    _state._DEV_SESSION_RETIREMENT,
    _state._DEV_SESSION_ID,
    _state._CODEX_SESSION_ID,
    _state._DEV_AGENT,
    _state._SILENT_PARK_COUNT,
    _state._DEV_RESUME_COUNT,
))


def _retirement(state: PinnedState) -> tuple[list[str], str | None, bool]:
    """The ids retired on this issue oldest first, the last reason, and whether recovery is still owed.

    Read fail-closed. Only an absent key retired nothing; a record not spelled
    the way this module writes it -- `null`, not an object, `session_ids` not a
    list of non-empty strings, a `reason` neither a string nor null, a
    `recovery_pending` that is not a boolean -- is a retirement nobody can
    fully read. Every id it still names stays retired, a lone string standing
    in for the list included, and a fresh conversation is owed whatever its
    flag says, until a write spells it readable again.
    """
    if not state.carries(_state._DEV_SESSION_RETIREMENT):
        return [], None, False
    stored = state.get(_state._DEV_SESSION_RETIREMENT)
    if not isinstance(stored, dict):
        return [], None, True
    listed = stored.get(_SESSION_IDS)
    retired = [listed] if isinstance(listed, str) and listed else []
    if isinstance(listed, list):
        retired = [session_id for session_id in listed if isinstance(session_id, str) and session_id]
    pending = stored.get(_RECOVERY_PENDING)
    if retired != listed or not isinstance(pending, bool):
        pending = True
    reason = stored.get(_REASON)
    if reason is None or isinstance(reason, str):
        return retired, reason, pending
    return retired, None, True


def _held_retirement(state: PinnedState) -> tuple[list[str], str | None, bool]:
    """The record as `_retirement` reads it, with every pin a fresh conversation is owed over retired too.

    Such a pin is never resumed (`_retired_session_reason`), but nothing names
    it once a road clears or replaces it -- a record nobody can read may name no
    id at all -- so a fresh run handing the same conversation back would be taken
    for the recovery and resumed next. Counted here, it is refused like any
    retired id, and `_clear_dev_session_pins` and `_pin_dev_session` record it
    before the pin goes. Both pin fields count, the legacy one a pinned
    `dev_agent` hides from the session read included
    (`session_read._pinned_session_ids`).
    """
    retired, reason, pending = _retirement(state)
    pinned = _session_read._pinned_session_ids(state) if pending else []
    held = [session_id for session_id in pinned if session_id not in retired]
    if held:
        return [*retired, *held], reason or _OWED_PIN, pending
    return retired, reason, pending


def _retired_session_reason(state: PinnedState, session_id: str | None) -> str | None:
    """Why the record forbids resuming the pinned `session_id`, or None where it does not."""
    if session_id is None:
        return None
    retired, reason, pending = _retirement(state)
    if session_id in retired:
        return f"conversation retired ({reason})"
    if pending:
        return f"a fresh conversation is owed ({reason})"
    return None


def _clear_dev_session_pins(state: PinnedState) -> None:
    """Clear the pinned dev session id (and legacy `codex_session_id`) and both per-session counters.

    Preserves the stored `dev_agent` spec when one is already pinned --
    a retired session is a transcript problem, not a backend-selection
    problem, so the fresh spawn that follows must replay the exact same
    backend+args. Writing the parsed backend back here would silently
    strip the configured CLI args from the spec and switch a `codex -m
    gpt-5.5 -c '...'` issue back to bare `codex` on the next resume.

    When the issue is on the legacy `codex_session_id` schema (no
    `dev_agent` ever written), pin `dev_agent="codex"` BEFORE clearing
    the legacy field. Without this, the next `_read_dev_session` would
    fall through to the config default and a `DEV_AGENT=claude` flip
    would silently switch the issue from codex to claude on retry.

    Clearing the legacy field too leaves no pin of the dropped session
    anywhere, so where a fresh conversation is owed the record names both
    pins first (`_held_retirement`), spelled readable as it goes. A pin
    dropped with nothing owed is recorded nowhere: only the id
    `_retire_dev_session` is handed joins the record then.
    """
    retired, reason, pending = _held_retirement(state)
    if pending:
        state.set(_state._DEV_SESSION_RETIREMENT, {
            _SESSION_IDS: retired, _REASON: reason, _RECOVERY_PENDING: True,
        })
    stored_spec = state.get(_state._DEV_AGENT)
    if not stored_spec and state.get(_state._CODEX_SESSION_ID) is not None:
        state.set(_state._DEV_AGENT, "codex")
    state.set(_state._DEV_SESSION_ID, None)
    state.set(_state._CODEX_SESSION_ID, None)
    state.set(_state._SILENT_PARK_COUNT, 0)
    # The resume budget is per-session; clearing the session resets it so the
    # fresh spawn that follows starts its own count from zero.
    state.set(_state._DEV_RESUME_COUNT, 0)


def _retire_dev_session(state: PinnedState, session_id: str | None, reason: str) -> None:
    """Record `session_id` as retired for good, owe a fresh conversation, and clear the pins.

    `session_id` is the conversation the failed run ran as, or None where the
    run named none; either way the next run must open a new one. Handed none,
    the retirement names every conversation either pin field holds in its
    place: the failure is no other conversation's it could name, and a pin
    cleared unnamed could be handed back by the fresh run and pinned as the
    recovery. A conversation the record already names is not retired a second
    time: a recovery that has since pinned a distinct conversation keeps it,
    and only a pin naming the retired id again -- in either field -- is
    cleared. The pins are cleared before the record owes a fresh conversation,
    so a pin is recorded beside a named `session_id` only where an earlier
    retirement already owed one over it.
    """
    if session_id and session_id in _retirement(state)[0]:
        if session_id in _session_read._pinned_session_ids(state):
            _clear_dev_session_pins(state)
        return
    named = [session_id] if session_id else _session_read._pinned_session_ids(state)
    _clear_dev_session_pins(state)
    retired = _retirement(state)[0]
    retired.extend(name for name in named if name not in retired)
    state.set(_state._DEV_SESSION_RETIREMENT, {
        _SESSION_IDS: retired, _REASON: reason, _RECOVERY_PENDING: True,
    })


def _pin_dev_session(state: PinnedState, session_id: str | None) -> bool:
    """Pin the conversation a fresh spawn returned, with its own resume budget; whether it was pinned.

    A spawn that returned no id, or handed a retired id back, pins nothing and
    leaves any recovery owed, so the next run is a fresh conversation again
    rather than a resume of the one that failed. A distinct id ends the
    recovery; the ids already retired stay recorded, so none is pinned later --
    every pin the recovery was owed over among them (`_held_retirement`),
    which the distinct id is pinned in place of, so no id the record names is
    left pinned beside it. A refused id that is still pinned in either field
    -- an unparked tick's first spawn runs fresh beside whatever the comment
    pinned, a legacy pin included -- is unpinned, as a retirement of a
    conversation already recorded unpins it, so the record names it.
    """
    retired, reason, pending = _held_retirement(state)
    if not session_id or session_id in retired:
        if pending:
            log.info(
                "dev session %r is not a fresh conversation; recovery from the retired one stays pending",
                session_id,
            )
        if session_id and session_id in _session_read._pinned_session_ids(state):
            _clear_dev_session_pins(state)
        return False
    if pending:
        _clear_dev_session_pins(state)
        state.set(_state._DEV_SESSION_RETIREMENT, {
            _SESSION_IDS: retired, _REASON: reason, _RECOVERY_PENDING: False,
        })
    state.set(_state._DEV_SESSION_ID, session_id)
    state.set(_state._DEV_RESUME_COUNT, 0)
    return True


def _commit_dev_session_retirement(
    gh: GitHubClient,
    issue: Issue,
    state: PinnedState,
    session_id: str | None,
    reason: str,
) -> _commit_models.CommitOutcome:
    """Retire `session_id` on the tick's `state` and land that retirement alone on the pinned comment.

    For a caller whose own whole-state write may never happen -- a live pause,
    a refused disposition -- and whose state carries moves that are not the
    retirement's to publish: a watermark staged over consumed replies, a park
    it was about to clear. The retirement is staged over a fresh reading and
    committed owning only `_RETIREMENT_FIELDS`, so every other field stays as
    that reading carries it. The command the tick pinned before its run rides
    along where the comment has none yet, since the conversation being retired
    ran under it and the recovery has to run under it too. Every conversation
    `state` records as retired is retired over that reading first, in the
    order `state` records it: the tick may have retired one on its state alone
    and never written it, and a commit staged over the comment's record alone
    would land without it, hand that record back to `state` in place of the
    tick's own, and leave the conversation free to be pinned again. A
    retirement handed no conversation names every one that reading pins as
    well, before anything there is cleared: the comment may pin one the tick
    never read, and cleared unnamed it could be pinned again.

    `state` carries the retirement whatever the commit answers, so a write the
    tick does make carries it as well. A commit that lands puts every field it
    owns on `state` as the comment now spells it, leaving the rest of what the
    tick staged alone: the comment's record can name a conversation another
    road retired since the tick read it, which the tick's own write would
    otherwise drop and leave free to be pinned again. A refusal writes nothing
    -- a comment that will not read, was never pinned, or moved an owned field
    meanwhile -- and is answered for the caller to weigh, as is an edit nobody
    confirmed.
    """
    _retire_dev_session(state, session_id, reason)
    fresh = _pinned_commit.reread(gh, issue, _commit_models.PinnedCommit.capture(state))
    if isinstance(fresh, _commit_models.CommitOutcome):
        return fresh
    staged = PinnedState(comment_id=fresh.comment_id, state_data=copy.deepcopy(fresh.data))
    if not staged.get(_state._DEV_AGENT) and state.get(_state._DEV_AGENT):
        staged.set(_state._DEV_AGENT, state.get(_state._DEV_AGENT))
    if not session_id:
        _retire_dev_session(staged, None, reason)
    for retired_id in _retirement(state)[0]:
        _retire_dev_session(staged, retired_id, reason)
    _retire_dev_session(staged, session_id, reason)
    outcome = _pinned_commit.commit(
        gh, issue, _commit_models.PinnedCommit.capture(fresh, owned=_RETIREMENT_FIELDS), staged.data,
    )
    if outcome.status is _commit_models.CommitStatus.COMMITTED:
        for field in _RETIREMENT_FIELDS:
            state.data.pop(field, None)
            if outcome.reading.carries(field):
                state.set(field, copy.deepcopy(outcome.reading.get(field)))
        _pinned_commit.takes_in(state, outcome.reading.data, _RETIREMENT_FIELDS)
    return outcome
