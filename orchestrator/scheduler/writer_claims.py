# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Which process on this host may write one repository issue right now.

The scheduler's own guards are between threads: a duplicate submit is refused
because this process's sets already hold the issue, and a family drain skips an
issue this process is tracking. A second poller on the same host keeps sets of
its own, and the issue is not its own: one pinned comment and one label set on
GitHub are read and rewritten by every process pointed at the repository, and a
pinned comment is replaced whole. So two pollers each acting on what it read
would leave whichever wrote last, with nothing on GitHub able to refuse it.

The claim is one exclusive `flock` per issue key, taken without waiting. A
process that gets it is the only writer of that issue on this host until it
gives it back; a process that does not is a contender, and a contender is to
do nothing for the issue this time and ask again on a later polling pass. It
never waits, because what it would wait out is another poller's whole handler
-- an agent run included -- and every other issue in its tick would wait with
it. Every dispatch path takes it for the issue it dispatches, a family
handler for each child it writes, and the per-tick base refresh for each
worktree it syncs -- one key and one namespace for all three, so a refresh
contends with a dispatch, and with another poller's refresh, exactly as two
dispatches do.

It is exclusive between this process's own threads too: a key one thread holds
as a writer is refused to a second writer here exactly as it is to another
process, and logged as `held_here`. The one thing let in beside a writer is a
holder that asks to be (`alongside`), which is for the durable half of a close
a poll observed: a receipt COMMENT, written beside whatever worker of this
process is running the issue -- a comment rather than a pinned write, so it
drops nothing that worker records. It is granted wherever this process already
holds the key, and is an ordinary attempt against every other process where it
does not. Either kind keeps the lock until the last holder here lets go.

Keyed by the repository's identity and the issue number, and nothing else, so
different issues never contend and one repository's issue never contends with
another repository's issue of the same number. The identity is the numeric id
GitHub assigns the repository -- the client's `repo_id` -- and never a name:
the configured slug is an operator's spelling, and even the `owner/name`
GitHub answers is the one it answered when a poller fetched the repository,
so a poller started before a rename and one started after it would each name
the repository differently and hold "the" claim on two files. The id is the
same for both, and for every spelling of the repository's name.

Only a lock somebody HOLDS is contention. A namespace that cannot be opened, a
filesystem that does not implement `flock`, or a lock table with no room says
nothing about another process -- and unlike the artifact presence in
`runtime/exclusion.py`, which lets a poller go on polling unclaimed, an issue
writer that cannot be coordinated on is withheld: the claim answers refused,
exactly as it answers a contender, and the reason is logged as a warning. A
presence that does not work costs a tidying job; a writer that does not work
would cost an issue's record.

Released on every exit. The descriptor is unlocked and closed however the body
ends, and the kernel drops the lock with the file description if the process
dies, so a crash leaves no claim behind -- only the file. The descriptor is
not inheritable, so an agent this process spawns while holding the claim does
not carry it past this process's own exit.

What the file carries is the lock, and a few lines about the hold holding it.
Every acquisition reads what the last hold left, then empties the file and
names itself on it by a token this process draws at import, before anything
else is done under it; and every hold that ends in its own process's hands
stamps the moment it let go on the file, on the host's monotonic clock, just
before it unlocks. So a note a hold left is gone once the next holder has
the file, and the note of a hold that stamped its release is never read at
all, not even in the instant a new holder has the lock and has not yet
emptied the file (`claim_notes`). And a holder that finds another process's
token there learns when another poller last held the issue: that hold's
stamp, or -- where it left none, because it died holding the claim -- the
moment it is found, since it ended by then and nothing says sooner. That
is what lets a holder decide whether a close its own poll read is still about
the record it now holds (`claim_notes`): a poll that read the issue after the
last such moment was reading what that hold left. A hold counts as of the
moment it ended, so a poller restarted over the namespace its predecessor
used is not held up by the tokens that predecessor left.
Beside the token, a hold may note what a contender cannot see from outside --
the late cycle it is retiring. Each of those records is a whole line or
nothing: a write that lands only part of one, as a file-size limit or a full
disk makes it, is cut back and reported as failed. What a reader cannot take
for whole -- a line with no end, left by a holder killed mid-write, or a file
no hold has signed -- says a hold may have been there and nothing more, so it
is read as one that ended when it is found, never as the stamp or the note its
first bytes would spell. That includes an empty file, even one this process
created a moment before: between its open and its lock another process can
have held the key and a third emptied the file and failed to sign it, and an
empty file says nothing of which happened. What it costs is a reading taken
before an issue's first claim on this host, which loses its tie to the record.

The files are never unlinked, by this module or by anything else while a poller
runs. A lock lives on the inode, and a path unlinked while one process holds its
inode would be recreated as a new inode the next process locks freely: both
would then hold "the" claim. What that costs is one small file per issue key
this host has ever claimed.

The namespace is `WORKTREES_DIR/.issue-writer-claims`, for the reason the
artifact lock sits under `WORKTREES_DIR`: the pollers that share a checkout
root are the ones that already coordinate on that host's artifacts, and they
are the ones that participate here. It is hidden for the same reason that lock
is, since the directory's other entries are what the artifact scans read, and a
dotted name is neither a repository root nor an `issue-<n>` checkout.

This supplies no cross-host coordination. Two hosts, two checkout roots, or a
namespace on a filesystem that does not honour `flock` between the processes
sharing it are not coordinated by it, and are not a supported topology; nor
are pollers that do not read one monotonic clock, as processes in separate
time namespaces do not. It is also separate from the artifact presence:
holding a writer claim says nothing about whether a maintenance pass may act,
and holding the presence says nothing about which process may write an issue.
"""
from __future__ import annotations

import contextlib
import fcntl
import logging
import os
import threading
import time
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

from orchestrator import config

log = logging.getLogger("orchestrator.scheduler")

_NAMESPACE_NAME = ".issue-writer-claims"

# Why a claim was refused, as the skip line spells it.
_HELD_HERE = "held_here"
_HELD_ELSEWHERE = "held_elsewhere"

# The line every acquisition opens the file with, and this process's token on
# it: drawn once, so no other process -- a restarted one reusing this pid
# included -- can ever be taken for this one. And the line a hold that lets go
# closes it with: the moment it did, on the clock `_Holdings.moment` reads.
# Each is a `key=value` line, as every line a hold leaves is.
_HOLDER = "holder"
_RELEASED = "released"
HOLDER_LINE = f"{_HOLDER}="
RELEASED_LINE = f"{_RELEASED}="
_TOKEN_BYTES = 16
_TOKEN = os.urandom(_TOKEN_BYTES).hex()


@dataclass(frozen=True)
class _Left:
    """What the last hold on a key left on its file, as the next reader finds it.

    A record is a whole `key=value` line, the last of a key winning. What a
    write cut short leaves -- a file-size limit, a full disk, a holder killed
    mid-write -- has no line end: a hold whose writing did not finish, which
    says it was there and nothing about when it ended, so it is read as no
    record. A cut `released=1` is not a stamp, nor a cut `retiring-cycle=4` a
    note.
    """

    fields: Mapping[str, str]
    unfinished: bool

    @classmethod
    def read(cls, text: str) -> _Left:
        """The whole records in `text`, and whether anything unfinished trails them."""
        *whole, tail = text.split("\n")
        fields = dict(line.partition("=")[::2] for line in whole)
        return cls(fields, unfinished=bool(tail))

    def ended_elsewhere(self, now: int) -> int | None:
        """When the hold this was left by ended, if it was another process's.

        Its release stamp where it signed the file, stamped it whole, and
        finished everything it wrote, and `now` otherwise -- a holder that
        died holding the claim, whose last write did not finish, or who never
        signed the file at all had ended by the time it is found, and nothing
        says how much sooner. Only a hold of this process's own is `None`: an
        empty file is no proof that nobody held the key, since one this
        process just created can have been held and emptied before its lock.
        """
        holder = self.fields.get(_HOLDER, "")
        if holder == _TOKEN:
            return None
        released = self.fields.get(_RELEASED, "")
        if holder and released.isdecimal() and not self.unfinished:
            return int(released)
        return now

    @property
    def standing(self) -> bool:
        """Whether these are the records of a hold that has not let go.

        Signed by a hold, and not stamped by it as released. The next holder
        has the lock a moment before it empties the file, so a hold's records
        stay on it after its release; the stamp is what says they are over.
        A hold killed holding the claim, or whose stamp could not be written,
        reads as standing until the next holder empties the file -- the last
        hold to write the issue until then.
        """
        return bool(self.fields.get(_HOLDER)) and _RELEASED not in self.fields


@dataclass
class _Holding:
    """One key this process has locked, and who here is inside it."""

    claim_file: TextIO
    writing: bool
    holders: int = 1

    @classmethod
    def taken(cls, path: Path, *, writing: bool) -> tuple[_Holding, _Left] | None:
        """The key's file with a lock on it and what the last hold left, or `None`.

        Opened for appending, creating it and the namespace if missing, so
        nothing is truncated under a holder, and emptied only once the lock is
        this one's: whatever the file says is what the last hold left, and that
        hold is over. What it left comes back with the file, and this process's
        own token is written in its place. `None` is contention and nothing
        else: `BlockingIOError` is exactly what a non-blocking request that
        would have waited raises. Every other `OSError` is raised, because none
        of them is a holder -- a signature that cannot be written included,
        whose emptied file the next reader takes for a hold that ended when it
        is found. The file is closed on both of those ways out, so a refused
        claim keeps no descriptor.
        """
        path.parent.mkdir(parents=True, exist_ok=True)
        with contextlib.ExitStack() as opened:
            claim_file = opened.enter_context(path.open("a+", encoding="utf-8"))
            try:
                fcntl.flock(claim_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return None
            claim_file.seek(0)
            left = _Left.read(claim_file.read())
            claim_file.truncate(0)
            holding = cls(claim_file, writing=writing)
            holding.recorded(f"{HOLDER_LINE}{_TOKEN}\n")
            opened.pop_all()
        return holding, left

    def recorded(self, line: str) -> None:
        """Add one whole record to the file, or none and raise.

        Written past the file object's buffer, so a failed write leaves nothing
        for a later flush or the close to add behind another record. A write
        that lands only part of the line is cut back to where it began and
        raised as a failure, so a record is a whole line or nothing and the
        next one never runs into its remains. Were the cut to fail as well,
        what is left has no line end, so a reader takes it for unfinished, and
        a record written after it runs into it as a line that spells no stamp
        and no note.
        """
        descriptor = self.claim_file.fileno()
        record = line.encode()
        began = os.fstat(descriptor).st_size
        written = os.write(descriptor, record)
        if written < len(record):
            os.ftruncate(descriptor, began)
            raise OSError(f"wrote {written} of {len(record)} bytes of a claim record")


class _Holdings:
    """Every key this process holds, so its threads meet on one lock each.

    A second `flock` on a second open file description of the same file is
    refused even inside one process, so a holder here that let another thread
    open the file again would have it refused as if another process held it.
    The lock is taken once per key, and the threads that hold it are counted.
    """

    def __init__(self) -> None:
        self._held: dict[Path, _Holding] = {}
        self._elsewhere: dict[Path, int] = {}
        self._lock = threading.Lock()

    def moment(self) -> int:
        """Now, on the clock every hold on this host stamps its release with.

        `CLOCK_MONOTONIC`, which POSIX keeps on one reading for every process
        on a host from its start-up on: nothing sets it and it never steps
        back, so a release one poller stamped orders against a moment another
        reads. It starts again when the host does, which `_found` answers.
        """
        return time.clock_gettime_ns(time.CLOCK_MONOTONIC)

    def join(self, path: Path, *, alongside: bool) -> str | None:
        """Take the key for one holder here, or say why it was refused.

        Asked under one lock for every thread of this process, so a key is
        either held here or attempted against the others, never both at once.
        Raises what the namespace or the lock raises.
        """
        with self._lock:
            holding = self._held.get(path)
            if holding is None:
                taken = _Holding.taken(path, writing=not alongside)
                if taken is None:
                    return _HELD_ELSEWHERE
                fresh, left = taken
                self._found(path, left)
                self._held[path] = fresh
                return None
            if holding.writing and not alongside:
                return _HELD_HERE
            holding.holders += 1
            holding.writing = holding.writing or not alongside
            return None

    def noted(self, path: Path, line: str) -> bool:
        """Add one line to a key a writer of this process holds.

        Refused -- `False`, and nothing written -- where no writer here holds
        the key: a file this process has not locked is another hold's, and an
        `alongside` holder writes no record a note could be about. Raises what
        the write raises, a write cut short included, having left no part of
        the line behind.
        """
        with self._lock:
            holding = self._held.get(path)
            if holding is None or not holding.writing:
                return False
            holding.recorded(line)
            return True

    def undisturbed_since(self, path: Path, moment: int) -> bool:
        """Whether every hold of the key by another poller found here had ended before `moment`.

        Found at this process's own acquisitions, so a hold another poller
        makes is found no later than this process next takes the key -- and
        never missed: the hold an acquisition finds is the last before it, and
        ended no sooner than any other poller's hold since this process last
        took the key. Asked by a holder of the key, it answers for every hold
        up to its own.
        """
        with self._lock:
            ended = self._elsewhere.get(path)
        return ended is None or ended < moment

    def leave(self, path: Path, *, alongside: bool) -> None:
        """Give one holder's share back, and the lock with the last of them.

        The last holder stamps the moment it let go on the file first, so the
        next process to take the key knows when this hold ended. A stamp that
        cannot be written, or is cut short, leaves the hold reading as one
        that died holding the claim, which costs a later poll only its
        reading's tie to the record, so it is logged rather than raised: the
        lock still goes. Unlocked explicitly before the close rather than
        left to it, so the claim ends with the body even where some other
        descriptor shares this file description.
        """
        with self._lock:
            holding = self._held[path]
            holding.holders -= 1
            holding.writing = holding.writing and alongside
            if holding.holders:
                return
            self._held.pop(path)
            stamp = f"{RELEASED_LINE}{self.moment()}\n"
            with holding.claim_file:
                try:
                    holding.recorded(stamp)
                except OSError as error:
                    log.warning("writer claim release at %s was not stamped (%s)", path, error)
                finally:
                    fcntl.flock(holding.claim_file, fcntl.LOCK_UN)

    def _found(self, path: Path, left: _Left) -> None:
        """Note when the hold an acquisition found on the key ended, if it was another poller's.

        As `_Left.ended_elsewhere` answers it. A stamp later than now was taken
        before the host last started, when this process did not yet exist, so
        it is older than anything this process has read and is noted as
        nothing.
        """
        now = self.moment()
        ended = left.ended_elsewhere(now)
        if ended is not None and ended <= now:
            self._elsewhere[path] = max(ended, self._elsewhere.get(path, ended))


_holdings = _Holdings()


def claim_path(repo_id: int, issue_number: int) -> Path:
    """The file one issue key is claimed on, read off the configuration now.

    Read at the call rather than bound at import, so a process coordinates
    over the checkout root it was started with.
    """
    return _namespace() / f"repo-{int(repo_id)}-issue-{int(issue_number)}.lock"


def _namespace() -> Path:
    """The one directory every participating poller on this host claims in."""
    return config.WORKTREES_DIR / _NAMESPACE_NAME


def _attempted(issue_key: str, path: Path, *, alongside: bool) -> bool:
    """Try for one key's claim once, and say why if it was not granted."""
    try:
        refusal = _holdings.join(path, alongside=alongside)
    except OSError as error:
        log.warning(
            "writer claim skip %s reason=unusable (%s at %s); "
            "withholding the issue rather than writing it uncoordinated",
            issue_key, error, path,
        )
        return False
    if refusal is not None:
        log.info("writer claim skip %s reason=%s", issue_key, refusal)
    return refusal is None


@contextlib.contextmanager
def issue_writer(
    repo_id: int,
    issue_number: int,
    *,
    alongside: bool = False,
    repo_name: str = "",
) -> Iterator[bool]:
    """Hold one issue's writer claim for the body, or say it was refused.

    `repo_id` is the repository's numeric id, as the client's `repo_id`
    answers it; `repo_name` only names the repository in the skip line, and
    keys nothing. `True` is this process alone writing the issue on this host
    until the body ends. `False` is a contender or a claim that could not be
    worked with, and a caller answers both the same way: it does nothing for
    the issue that it would need the claim for, and a later polling pass asks
    again.

    `alongside` asks to be let in beside a writer of this process's own,
    which is what the durable half of an observed close needs and nothing
    else does; against every other process it is the same exclusive attempt.
    """
    path = claim_path(repo_id, issue_number)
    named = repo_name or "?"
    issue_key = f"repo={named} repo_id={repo_id} issue=#{issue_number}"
    if not _attempted(issue_key, path, alongside=alongside):
        yield False
        return
    try:
        yield True
    finally:
        _holdings.leave(path, alongside=alongside)
