# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The record this host keeps of the quota retirement one issue owes, beside its writer claim.

`quota_retirement` decides when a conversation an exhausted account quota
stopped is retired, and lands it on the pinned comment. Until it lands, and
from before the launch that could owe it, the obligation is held here, so no
write that fails once the failure is known can lose it. An Antigravity launch
is armed first (`_OwedRetirement.armed`) under a token of its own, and a
launch that cannot be armed is not made. Its return settles the record where
no quota stopped it (`_OwedRetirement.cleared`), and a quota stop resolves it
to the conversation that must be retired -- the one the failure names, or the
launched one where it names none (`_OwedRetirement.owed`) -- which stands
until a commit lands it and the record is settled (`_OwedRetirement.settle`).

An arming nothing resolved -- its poller killed mid-run, an exception out of
the runner, a clear or a resolution the host would not take before a restart
-- says a launch went out and nothing about which conversation, if any, a
quota stopped: a fresh spawn's own id is unknown until it returns, and a
resumed run can report another. So, like a record that will not read, it is
never landed: every developer launch on the issue waits on it until the
poller holding its resolution writes it, or an operator writes the retirement
it owes or settles it.

A resolution the host would not take is held in this process (`_unwritten`)
with the token of the arming it resolves, and written again at each check --
but only while the host still reads that arming, or nothing at all because
something took the record away: a record another poller or an operator has
since resolved or settled, or one a later launch armed, has moved past it,
and the memory is dropped rather than land over a conversation pinned since.
That is why settling never removes the record: what a settled one says has to
be read by every poller, so it is written over in place.

The record is `repo-<id>-issue-<n>.quota-retirement` beside the issue's claim
file (`writer_claims.claim_path`), in the namespace every poller on this host
claims in, and is written only under that claim. Every write is in place, so a
directory that takes no new entry still takes it once it stands, and none
counts as made until it is on the host's disk (`_persisted`): a host that
crashes keeps the last state every launch since was allowed on, and one torn
mid-write reads as a record that will not read. A write the disk will not
flush is one the host would not take, which holds what it was made for. It
spells `{"armed": <id or null>, "launch": <token>}` while armed,
`{"session_id": <id or null>}` while a resolved retirement is owed, and `{}`
once settled. Another host sees none of it.
"""
from __future__ import annotations

import contextlib
import json
import logging
import os
import secrets
from dataclasses import dataclass
from pathlib import Path

from github.Issue import Issue

from orchestrator.github.client import GitHubClient
from orchestrator.scheduler import writer_claims as _writer_claims

log = logging.getLogger("orchestrator.workflow")

# What the record is named by beside the claim file, the keys an armed and a
# resolved one hold, what a settled one spells, and how much randomness tells
# one arming from another.
_RECORD_SUFFIX = ".quota-retirement"
_SESSION_ID = "session_id"
_ARMED = "armed"
_LAUNCH = "launch"
_SETTLED = "{}"
_LAUNCH_BYTES = 8

# The resolved retirements this host would not take a record of, by the path
# that record belongs at, each with the arming it resolves: kept in this
# process instead, so the launches behind one still wait across ticks, and
# written again at each check until the host takes it. And the token of the
# record this process armed for a launch that is still out. Each issue's entry
# is touched only under that issue's writer claim.
_unwritten: dict[Path, _OwedRetirement] = {}
_armed: dict[Path, str] = {}


@dataclass(frozen=True)
class _OwedRetirement:
    """A retirement one issue is owed and no commit has confirmed, as this host keeps it.

    `session_id` is the conversation it retires, None where neither the
    failure nor the launch named one. `launch` is the token of the arming it
    resolves, empty where it resolves none. One that does not say which
    conversation it retires is not `legible`: a record that will not read --
    torn by a crash or a full disk, bytes that are no UTF-8 JSON, something
    else standing at its name -- or an arming nothing here resolved. Neither
    is ever landed or settled by a poller that cannot say; every developer
    launch on the issue waits on it until an operator writes it again or
    settles it.
    """

    path: Path
    session_id: str | None
    legible: bool = True
    launch: str = ""

    @classmethod
    def recorded(cls, gh: GitHubClient, issue: Issue) -> _OwedRetirement | None:
        """The retirement this host holds owed for `issue`, or None where its record is settled or absent.

        This process's memory of a resolution wins only where the host has
        not moved past it (`_superseded`), and is written again when it does.
        """
        path = _located(gh, issue)
        try:
            encoded = path.read_bytes()
        except FileNotFoundError:
            encoded = None
        except OSError:
            log.warning("issue=#%d could not read the retirement it is owed at %s", issue.number, path, exc_info=True)
            encoded = b""
        found = None if encoded is None else cls._read(path, encoded)
        held = _unwritten.get(path)
        if held is not None and not _superseded(held, encoded, found):
            return held._kept()
        _unwritten.pop(path, None)
        return found

    @classmethod
    def armed(cls, gh: GitHubClient, issue: Issue, launched: str | None) -> bool:
        """Arm the record for a launch of `launched`, None for a fresh spawn, before it runs; whether it took.

        Asked where nothing is owed. False holds the launch: a quota stop it
        met would be kept in this process alone, which a restart drops. An
        arming the disk would not confirm may still be what the record reads,
        and it would hold every later launch on an operator for one that was
        never made, so the record is settled again -- as it stood -- before
        the launch is refused.
        """
        path = _located(gh, issue)
        launch = secrets.token_hex(_LAUNCH_BYTES)
        if _written(path, json.dumps({_ARMED: launched, _LAUNCH: launch})):
            _armed[path] = launch
            return True
        _written(path, _SETTLED)
        return False

    @classmethod
    def owed(cls, gh: GitHubClient, issue: Issue, session_id: str | None) -> _OwedRetirement:
        """Resolve the record to the retirement of `session_id` a quota stop leaves owed, written or held."""
        path = _located(gh, issue)
        return cls(path, session_id, launch=_armed.get(path, ""))._kept()

    @classmethod
    def cleared(cls, gh: GitHubClient, issue: Issue) -> None:
        """Settle the record this process armed for `issue`'s launch, now back with no quota stop.

        Only a record armed here is settled: a result handed in from
        elsewhere was launched past no arming, and the record may still owe
        another attempt's retirement. One that will not settle stays armed
        with nothing to resolve it: the attempt that came back still goes on
        to its disposition, and every later developer launch waits on an
        operator.
        """
        path = _located(gh, issue)
        if path in _armed:
            cls(path, None).settle()

    def settle(self) -> bool:
        """Write the record over in place as owing nothing; whether the host now owes nothing.

        Never removed: a settled record is what tells every other poller,
        and the memory of any resolution of it, that it is over. False is a
        record that still owes, which every developer launch waits on.
        """
        _unwritten.pop(self.path, None)
        _armed.pop(self.path, None)
        return _written(self.path, _SETTLED)

    def _kept(self) -> _OwedRetirement:
        """This retirement, written over the record in place -- or held in this process where it is not."""
        _armed.pop(self.path, None)
        if _written(self.path, json.dumps({_SESSION_ID: self.session_id})):
            _unwritten.pop(self.path, None)
        else:
            _unwritten[self.path] = self
        return self

    @classmethod
    def _read(cls, path: Path, encoded: bytes) -> _OwedRetirement | None:
        """The record `encoded` spells at `path`: None where it is settled, an illegible one where it names nothing.

        Bytes that are not UTF-8 JSON fail to decode as a `ValueError` like
        any other text that is no record. No write of an armed or a resolved
        record leaves a settled one, however it is cut short.
        """
        try:
            recorded = json.loads(encoded)
        except ValueError:
            recorded = None
        if not isinstance(recorded, dict):
            return cls(path, None, legible=False)
        if not recorded:
            return None
        if _ARMED in recorded:
            launch = recorded.get(_LAUNCH) or ""
            return cls(path, None, legible=False, launch=str(launch))
        session_id = recorded.get(_SESSION_ID, "")
        if session_id is None or (isinstance(session_id, str) and session_id):
            return cls(path, session_id)
        return cls(path, None, legible=False)


def _located(gh: GitHubClient, issue: Issue) -> Path:
    """Where this host keeps the retirement `issue` is owed: beside its writer claim."""
    return _writer_claims.claim_path(gh.repo_id, issue.number).with_suffix(_RECORD_SUFFIX)


def _superseded(held: _OwedRetirement, encoded: bytes | None, found: _OwedRetirement | None) -> bool:
    """Whether the host has moved past the resolution this process `held`: settled, resolved, or armed anew.

    `encoded` is what the record read as, None where it is gone. The memory
    stands over a record that is gone or will not read -- the very write it
    could not make may be what blocked it -- and over the arming it resolves.
    """
    if encoded is None:
        return False
    return found is None or found.legible or found.launch not in {"", held.launch}


def _written(path: Path, spelled: str) -> bool:
    """Whether `spelled` is on the host's disk over the record at `path`, the namespace made where it is missing."""
    try:
        _persisted(path, spelled.encode())
    except OSError:
        log.warning("could not persist %s over the quota retirement record at %s", spelled, path, exc_info=True)
        return False
    return True


def _persisted(path: Path, encoded: bytes) -> None:
    """Write `encoded` over the record in place and flush it to disk, with the directory entries that reach it.

    The record's bytes are flushed first, then its directory -- which holds
    the entry of a record this write made -- and that directory's parent,
    which holds the namespace's own entry where this write made it too. Raises
    where any of it fails: what the disk will not confirm, a crash can undo.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as record:
        record.write(encoded)
        record.flush()
        os.fsync(record.fileno())
    _synced(path.parent)
    _synced(path.parent.parent)


def _synced(directory: Path) -> None:
    """Flush `directory`'s entries to disk."""
    with contextlib.ExitStack() as opened:
        descriptor = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
        opened.callback(os.close, descriptor)
        os.fsync(descriptor)
