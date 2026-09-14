# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a remote carries under a pattern, over the authenticated transport.

The one question about a remote that starts from no name at all. Every read
the transport beside this owns is asked about a refname somebody already has --
a branch the clone still carries, a snapshot ref a record names -- so a branch
whose local ref was deleted, or whose whole clone was rebuilt, is invisible to
all of them while the remote still carries it. This asks the remote what it
holds under a namespace and gets those names back, which is the only way an
artifact this host no longer names is found.

Its own owner because nothing is pinned to what it says. A single-ref read is
half of a lease -- the caller states the reading back as the value its write
must still find -- and the writes that spend one sit beside it for that reason.
A listing pins nothing: it opens the question of which artifacts exist, and
every decision about one of them is taken afterwards, by a caller that has to
establish each name on its own.

The read is asked of the remote rather than of the local ref store for the
reason every read here is: the object store a worktree shares is writable by
the agent running in it, so a local ref that looks like the answer proves
nothing, while the remote's own answer is the one nothing on this host can
rewrite.

The call runs under the whole token-bearing envelope: a token resolved per
repository through `credentials`, an askpass session that keeps it out of the
world-readable `/proc/<pid>/cmdline`, global and system config detached, hooks,
credential helpers, and fsmonitor disabled by `-c`, and a refusal when the
worktree's local config carries a url rewrite or an `http.*` setting that could
redirect the call to an attacker-controlled host. The session carries the token
back here for the one thing the environment cannot do: scrubbing it out of the
stderr a failed listing is logged with.

Which namespace is asked about, and what a name found there means, belongs to
the caller. The artifact discovery under `git/worktrees/` owns the
orchestrator's own branch namespace and is what spends this listing, on the
half of its scan the host cannot answer.
"""
from __future__ import annotations

import logging
import subprocess
from pathlib import Path

from orchestrator.config import models as _config_models
from orchestrator.git import commands, credentials

# The channel is named for the git-plumbing domain rather than for this
# module's path: operators filter the rendered `orchestrator.git_plumbing`
# prefix and attach handlers to it, so a listing that answered nothing reports
# where their filters already point.
log = logging.getLogger("orchestrator.git_plumbing")


def _remote_ref_listing(
    auth_session: credentials._GitAuthSession,
    worktree: Path,
    pattern: str,
) -> tuple[str, ...] | None:
    """Every refname the remote carries under `pattern`, through an open session.

    The empty tuple where the remote carries none, and None where the listing
    established nothing, so a caller cannot read a failed call as a remote
    holding nothing under that namespace.

    `--refs` is asked for so a tag's peeled entry cannot arrive as a refname
    of its own; the pattern is passed as git's own, which matches across `/`
    and so covers a namespace however many components deep its members are.

    A line that does not carry both fields is dropped rather than refused,
    which is the safe direction for the one thing this listing is spent on: a
    name that never arrives is an artifact nobody goes on to act on, while a
    listing refused wholesale over one odd line would take every healthy name
    beside it down too.
    """
    listed = subprocess.run(
        [
            *commands._AUTHED_GIT_PREFIX,
            "ls-remote", "--refs", auth_session.auth_url, pattern,
        ],
        cwd=str(worktree),
        capture_output=True,
        text=True,
        env=auth_session.env,
        check=False,
    )
    if listed.returncode != 0:
        log.error(
            "git ls-remote failed for %s: %s",
            pattern, credentials._scrubbed(listed.stderr, auth_session.token),
        )
        return None
    named = (
        output_line.strip().split() for output_line in
        (listed.stdout or "").splitlines()
    )
    return tuple(parts[1] for parts in named if len(parts) >= 2)


def _remote_ref_names(
    spec: _config_models.RepoSpec, worktree: Path, *, pattern: str,
) -> tuple[str, ...] | None:
    """Ask the REMOTE which refs it carries under one pattern.

    The read that finds an artifact this host holds no copy of, and the entry
    point every caller of this owner takes: the refusals in front of the
    listing -- a token nobody could resolve, a worktree whose config could
    hijack the transport -- are the same ones a token-bearing read owes
    anywhere, and a caller reaching the listing without them would carry the
    token past both.

    Two answers a caller must keep apart: the empty tuple is the remote
    answering that it holds nothing under the pattern, and None is a read that
    established nothing -- a missing token, a worktree whose config could
    hijack the transport, an unreachable remote. A caller that took the second
    for the first would conclude a repository has no artifacts left because
    nobody could ask it.
    """
    token = credentials._resolved_git_token(spec, "list the remote refs")
    if not token:
        return None
    unsafe = commands._unsafe_local_transport_config(worktree)
    if unsafe:
        log.error(
            "refusing to list %s from the remote: worktree .git/config has "
            "transport-hijacking config: %s", pattern, unsafe,
        )
        return None
    with credentials._git_auth_session(spec, token) as auth_session:
        return _remote_ref_listing(auth_session, worktree, pattern)
