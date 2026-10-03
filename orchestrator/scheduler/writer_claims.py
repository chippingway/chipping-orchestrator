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
gives it back; a process that does not is a contender, and a contender does
nothing for the issue this time and asks again on a later polling pass. It
never waits, because what it would wait out is another poller's whole handler
-- an agent run included -- and every other issue in its tick would wait with
it.

It is exclusive between this process's own threads too: a key one thread holds
as a writer is refused to a second writer here exactly as it is to another
process, and logged as `held_here`. The one thing let in beside a writer is a
holder that asks to be (`alongside`): the durable half of a close a poll
observed is a receipt COMMENT, written beside whatever worker of this process
is running the issue -- a comment rather than a pinned write, so it drops
nothing that worker records -- and it is granted wherever this process already
holds the key, and is an ordinary attempt against every other process where it
does not. Either kind keeps the lock until the last holder here lets go.

Keyed by the repository's identity and the issue number, and nothing else, so
different issues never contend and one repository's issue never contends with
another repository's issue of the same number. The identity is the canonical
`owner/name` GitHub answers for the repository -- the client's `repo_slug`,
never the configured slug -- case-folded, since GitHub names a repository
case-insensitively. So two pollers configured with two spellings of one
repository, or with a renamed repository's old and new names, meet on one key.

Only a lock somebody HOLDS is contention. A namespace that cannot be opened, a
filesystem that does not implement `flock`, or a lock table with no room says
nothing about another process -- and unlike the artifact presence in
`runtime/exclusion.py`, which lets a poller go on polling unclaimed, an issue
writer that cannot be coordinated on is withheld: the claim answers refused,
the issue is skipped as a contended one is, and the reason is logged as a
warning. A presence that does not work costs a tidying job; a writer that does
not work would cost an issue's record.

Released on every exit. The descriptor is unlocked and closed however the body
ends, and the kernel drops the lock with the file description if the process
dies, so a crash leaves no claim behind -- only an empty file. The descriptor is
not inheritable, so an agent this process spawns while holding the claim does
not carry it past this process's own exit.

The files are never unlinked, by this module or by anything else while a poller
runs. A lock lives on the inode, and a path unlinked while one process holds its
inode would be recreated as a new inode the next process locks freely: both
would then hold "the" claim. What that costs is one empty file per issue key
this host has ever dispatched.

The namespace is `WORKTREES_DIR/.issue-writer-claims`, for the reason the
artifact lock sits under `WORKTREES_DIR`: the pollers that share a checkout
root are the ones that already coordinate on that host's artifacts, and they
are the ones that participate here. It is hidden for the same reason that lock
is, since the directory's other entries are what the artifact scans read, and a
dotted name is neither a repository root nor an `issue-<n>` checkout.

This supplies no cross-host coordination. Two hosts, two checkout roots, or a
namespace on a filesystem that does not honour `flock` between the processes
sharing it are not coordinated by it, and are not a supported topology. It is
also separate from the artifact presence: holding a writer claim says nothing
about whether a maintenance pass may act, and holding the presence says nothing
about which process may write an issue.
"""
from __future__ import annotations

import contextlib
import fcntl
import hashlib
import logging
import threading
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

from orchestrator import config

log = logging.getLogger("orchestrator.scheduler")

_NAMESPACE_NAME = ".issue-writer-claims"

# Wide enough that two repositories one host polls never share a key by
# accident, while the file name stays short enough for any filesystem.
_IDENTITY_DIGEST_WIDTH = 32

# Why a claim was refused, as the skip line spells it.
_HELD_HERE = "held_here"
_HELD_ELSEWHERE = "held_elsewhere"


@dataclass
class _Holding:
    """One key this process has locked, and who here is inside it."""

    claim_file: TextIO
    writing: bool
    holders: int = 1


class _Holdings:
    """Every key this process holds, so its threads meet on one lock each.

    A second `flock` on a second open file description of the same file is
    refused even inside one process, so a holder here that let another thread
    open the file again would have it refused as if another process held it.
    The lock is taken once per key, and the threads that hold it are counted.
    """

    def __init__(self) -> None:
        self._held: dict[Path, _Holding] = {}
        self._lock = threading.Lock()

    def join(self, path: Path, *, alongside: bool) -> str | None:
        """Take the key for one holder here, or say why it was refused.

        Asked under one lock for every thread of this process, so a key is
        either held here or attempted against the others, never both at once.
        Raises what the namespace or the lock raises.
        """
        with self._lock:
            holding = self._held.get(path)
            if holding is None:
                claim_file = _taken(path)
                if claim_file is None:
                    return _HELD_ELSEWHERE
                self._held[path] = _Holding(claim_file, writing=not alongside)
                return None
            if holding.writing and not alongside:
                return _HELD_HERE
            holding.holders += 1
            holding.writing = holding.writing or not alongside
            return None

    def leave(self, path: Path, *, alongside: bool) -> None:
        """Give one holder's share back, and the lock with the last of them.

        Unlocked explicitly before the close rather than left to it, so the
        claim ends with the body even where some other descriptor shares this
        file description.
        """
        with self._lock:
            holding = self._held[path]
            holding.holders -= 1
            holding.writing = holding.writing and alongside
            if holding.holders:
                return
            self._held.pop(path)
            with holding.claim_file:
                fcntl.flock(holding.claim_file, fcntl.LOCK_UN)


_holdings = _Holdings()


def claim_path(repo_identity: str, issue_number: int) -> Path:
    """The file one issue key is claimed on, read off the configuration now.

    Read at the call rather than bound at import, so a process coordinates
    over the checkout root it was started with. The repository is named by a
    digest of its case-folded identity, which is one safe file-name segment
    whatever GitHub answered and distinct for every distinct repository.
    """
    identity = repo_identity.casefold().encode("utf-8")
    digest = hashlib.sha256(identity).hexdigest()[:_IDENTITY_DIGEST_WIDTH]
    return _namespace() / f"{digest}-issue-{int(issue_number)}.lock"


def _namespace() -> Path:
    """The one directory every participating poller on this host claims in."""
    return config.WORKTREES_DIR / _NAMESPACE_NAME


def _taken(path: Path) -> TextIO | None:
    """The key's file with a lock on it, or `None` if another holds it.

    Opened for appending, creating it and the namespace if missing, so nothing
    is truncated under a holder; the file stays empty, since what it carries is
    the lock. `None` is contention and nothing else: `BlockingIOError` is
    exactly what a non-blocking request that would have waited raises. Every
    other `OSError` is raised, because none of them is a holder. The file is
    closed on both of those ways out, so a refused claim keeps no descriptor.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    claim_file = path.open("a", encoding="utf-8")
    try:
        fcntl.flock(claim_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        claim_file.close()
        return None
    except OSError:
        claim_file.close()
        raise
    return claim_file


def _attempted(
    repo_identity: str, issue_number: int, path: Path, *, alongside: bool,
) -> bool:
    """Try for one key's claim once, and say why if it was not granted."""
    try:
        refusal = _holdings.join(path, alongside=alongside)
    except OSError as error:
        log.warning(
            "writer claim skip repo=%s issue=#%s reason=unusable (%s at %s); "
            "withholding the issue rather than writing it uncoordinated",
            repo_identity, issue_number, error, path,
        )
        return False
    if refusal is not None:
        log.info(
            "writer claim skip repo=%s issue=#%s reason=%s",
            repo_identity, issue_number, refusal,
        )
    return refusal is None


@contextlib.contextmanager
def issue_writer(
    repo_identity: str, issue_number: int, *, alongside: bool = False,
) -> Iterator[bool]:
    """Hold one issue's writer claim for the body, or say it was refused.

    `repo_identity` is the repository's canonical `owner/name`, as the
    client's `repo_slug` answers it. `True` is this process alone writing the
    issue on this host until the body ends. `False` is a contender or a claim
    that could not be worked with, and a caller answers both the same way: it
    does nothing for the issue that it would need the claim for, and a later
    polling pass asks again.

    `alongside` asks to be let in beside a writer of this process's own,
    which is what the durable half of an observed close needs and nothing
    else does; against every other process it is the same exclusive attempt.
    """
    path = claim_path(repo_identity, issue_number)
    if not _attempted(repo_identity, issue_number, path, alongside=alongside):
        yield False
        return
    try:
        yield True
    finally:
        _holdings.leave(path, alongside=alongside)
