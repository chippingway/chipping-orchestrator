# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Plain and hardened git execution plus local transport probing.

The argv prefixes live here because every git invocation is assembled from
them: the hardened prefix extends the authenticated one that the
token-bearing fetch and push leaves run under, so the two cannot drift.

Output is decoded with `surrogateescape` rather than strictly. A repository
path is bytes on this platform, and git hands back exactly the bytes it has --
so a committed file whose name is not valid UTF-8 makes a strict decode raise
inside `subprocess` itself, before any caller can read a return code. What that
costs is the whole point: the probes reading these paths are the ones that
refuse to publish a branch carrying anything unexpected, and a raise there
takes the tick out rather than parking the artifact that caused it. Decoded
with surrogates, such a path comes back as a path -- unequal to whatever the
caller permitted, which is the answer it was asking for.

The hardened runner also has an undecoded form, because decoding at all is
more than one kind of caller can afford: text capture folds a CR LF pair and a
lone CR into a single LF, which is lossy about a path and therefore about
anything hashed over one. A caller taking a digest spends
`_git_hardened_bytes` and hashes exactly what git wrote; every other caller
reads the text. Where what git writes is an agent-sized amount of content
rather than a listing of it, the streaming owner beside this one takes the
request on stdin and hands the answer over a chunk at a time, assembling none
of it -- spawned on the prefix and the environment assembled here rather than
on copies of them, so what hardens one call hardens every one of them.
"""
from __future__ import annotations

import os
import subprocess
from collections.abc import Mapping
from pathlib import Path
from types import MappingProxyType

from orchestrator import config

_GIT_NO_PROMPT_ENV: Mapping[str, str] = MappingProxyType({
    "GIT_TERMINAL_PROMPT": "0",
})

_GIT = "git"

_GIT_CONFIG_FLAG = "-c"

_WORK_TREE_FLAG = "--work-tree"

# How git's own output is turned into text. Paths are bytes on this platform
# and nothing guarantees they are UTF-8, so a byte that is not decodable is
# carried as a surrogate instead of raising out of `subprocess.run`.
_UNDECODABLE_BYTES = "surrogateescape"

_AUTHED_GIT_PREFIX = (
    _GIT,
    _GIT_CONFIG_FLAG, "core.hooksPath=/dev/null",
    _GIT_CONFIG_FLAG, "credential.helper=",
    _GIT_CONFIG_FLAG, "core.fsmonitor=",
)

_HARDENED_GIT_PREFIX = (
    *_AUTHED_GIT_PREFIX,
    _GIT_CONFIG_FLAG, "commit.gpgsign=false",
    _GIT_CONFIG_FLAG, "rebase.autoStash=false",
    # The graft file is disabled by pointing it at /dev/null, which git reads
    # as a graft file that happens to be empty and warns about on every call.
    # The deprecation notice is true and useless here, and it would otherwise
    # ride out on the stderr an operator is shown when an operation fails.
    _GIT_CONFIG_FLAG, "advice.graftFileDeprecated=false",
)

# The two ways a repository can be told to serve one object in place of
# another. Both are honored by every command that reads history, both live in
# the clone the agent's worktree shares, and neither is config: `refs/replace/`
# is a ref namespace and the graft file is a plain file in the git dir, so
# detaching global config and overriding `-c` settings does not touch either.
_NO_OBJECT_REPLACEMENT_ENV: Mapping[str, str] = MappingProxyType({
    "GIT_NO_REPLACE_OBJECTS": "1",
    "GIT_GRAFT_FILE": os.devnull,
})

_UNSAFE_TRANSPORT_CONFIG_RE = (
    r"^(url\..*\.(insteadof|pushinsteadof)|http\..*)$"
)


def _work_tree_arg(worktree: Path) -> str:
    """The argument naming `worktree` as the tree a command acts on.

    Working-tree operations state their tree rather than let git discover it,
    because `core.worktree` in a linked worktree's own `config.worktree` --
    which an agent enables by writing `extensions.worktreeConfig` into the
    clone it shares -- points discovery at any directory it likes, and a `-c
    core.worktree=` override does not win against it. A read left to discovery
    reports on that other directory and a reset writes into it.

    The path is spelled absolutely because git resolves a relative one against
    the cwd of the command carrying it, and every caller here runs with `cwd`
    set to the worktree itself. `config.WORKTREES_DIR` is relative whenever it
    is configured that way -- as the default derived from a relative
    `TARGET_ROOT` is -- so the flag would name a path under the worktree that
    does not exist, and git would answer "this operation must be run in a work
    tree" for every command carrying it. The probes read that exit code as an
    unreadable checkout, which is a verdict about the tree rather than about
    the flag, so a healthy one gets parked with no tick able to un-park it.
    """
    return f"{_WORK_TREE_FLAG}={worktree.resolve()}"


def _git(*args: str, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [_GIT, *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        errors=_UNDECODABLE_BYTES,
        env={**os.environ, **_GIT_NO_PROMPT_ENV},
        check=False,
    )


def _first_reported_line(output: str) -> str:
    """The one line of a failed call's output a caller carries away with it.

    One line, because what travels beside a typed failure is a diagnostic a
    human reads rather than a transcript: git names what went wrong first and
    spends the lines after it on advice, hints, and the remote's banner, none
    of which says anything the first line has not. A record carrying all of it
    would put a screenful of text everywhere the reason it stands beside is
    reported.

    Blank leading lines are skipped rather than answered with, since a call
    whose output opens with one would otherwise report nothing at all, and ""
    is reserved for a call that really said nothing.
    """
    for line in output.splitlines():
        reported = line.strip()
        if reported:
            return reported
    return ""


def _git_hardened(
    *args: str,
    cwd: Path,
    env_extra: Mapping[str, str] | None = None,
) -> subprocess.CompletedProcess:
    """`_git` plus the agent-hostile-environment hardening from `_push_branch`.

    Used for local git operations inside a worktree the agent can write to: a
    planted `core.hooksPath`, `core.fsmonitor`, or url rewrite rule in
    the worktree's `.git/config` (or in `~/.gitconfig`) would otherwise
    execute attacker code mid-operation or redirect a transient fetch to an
    attacker-controlled host, and a planted replacement object or graft would
    have git answer for a commit nobody wrote. Drops global/system git config so url
    `insteadOf` rewrites and host-wide hooks cannot apply, and disables
    repo-local hooks / fsmonitor / credential helpers / commit signing via
    `-c` overrides. No askpass is wired in -- this helper is for local-only
    operations (rebase, diff, rev-parse); push remains the only call site
    that handles GIT_TOKEN.

    Injects `GIT_AUTHOR_*` / `GIT_COMMITTER_*` env vars (matching the
    agent spawn's `agent_env`) so a `git rebase` that needs to replay
    commits doesn't fail with "Committer identity unknown" -- stripping
    global config also strips any `user.name` / `user.email` set there,
    and env vars take precedence over config.

    Object replacement is turned off for the same reason the config is
    detached, and it is the sharper of the two: an agent that writes
    `refs/replace/<commit>` or a line in `info/grafts` changes what git says a
    commit's tree and history ARE, without touching the commit anybody named.
    A check that reads a branch here and a push that sends the same SHA would
    then be talking about two different things -- the reading measured against
    a synthetic stand-in, the push carrying the real commits. Refs and the
    graft file are not config, so nothing above disables them; the two env
    vars here do.

    `env_extra` is applied last, over both the process environment and the
    hardening above, and exists for what git reads from the environment rather
    than from config -- where a `-c` on the command line does not win. A caller
    that has to PIN one of those (which tree `.gitattributes` are read from,
    whether the system-wide ones are consulted at all) states it here, so what
    this process happened to inherit cannot answer for it instead.
    """
    return subprocess.run(
        [*_HARDENED_GIT_PREFIX, *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        errors=_UNDECODABLE_BYTES,
        env=_hardened_env(env_extra),
        check=False,
    )


def _git_hardened_bytes(
    *args: str,
    cwd: Path,
    env_extra: Mapping[str, str] | None = None,
) -> subprocess.CompletedProcess:
    """`_git_hardened` with git's output left as the bytes git wrote.

    The same argv prefix and the same environment; only the capture differs,
    and it differs for the one kind of caller that cannot use the decoded
    form: one that hashes what git produced. Text capture decodes under
    whatever encoding this process's locale names, and then puts the result
    through universal newlines -- so a CR LF pair and a lone CR both come out
    as a single LF. A path is bytes and a carriage return is one of the bytes
    it may contain, which makes that translation a collision: two committed
    paths that differ only there decode to one string, and a digest taken over
    it is evidence about neither of them.

    Both streams come back as bytes, since `text` is what decodes either one.
    A caller wanting stderr as a line for a human decodes it itself, where
    lossy is harmless.

    `env_extra` is what it is on `_git_hardened`: the pins for what git reads
    from the environment rather than from config, where an override on the
    command line does not win.

    Output a caller cannot afford to hold in one piece, and a request too long
    to pass on the command line, both belong to
    `streaming._git_hardened_streamed` instead.
    """
    return subprocess.run(
        [*_HARDENED_GIT_PREFIX, *args],
        cwd=str(cwd),
        capture_output=True,
        env=_hardened_env(env_extra),
        check=False,
    )


def _hardened_env(
    env_extra: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """The environment a hardened git call is spawned under.

    Assembled once for every hardened runner -- the two here and the streamed
    one beside them -- rather than beside any of them. What each entry is for
    is on `_git_hardened`; what matters here is that there is a single copy of
    it, since a second one is free to lose a protection the first still has
    and nothing about the call site would show it.
    """
    return {
        **os.environ,
        **_GIT_NO_PROMPT_ENV,
        **_NO_OBJECT_REPLACEMENT_ENV,
        "GIT_AUTHOR_NAME": config.AGENT_GIT_NAME,
        "GIT_AUTHOR_EMAIL": config.AGENT_GIT_EMAIL,
        "GIT_COMMITTER_NAME": config.AGENT_GIT_NAME,
        "GIT_COMMITTER_EMAIL": config.AGENT_GIT_EMAIL,
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_SYSTEM": os.devnull,
        "GIT_CONFIG_NOSYSTEM": "1",
        **(env_extra or {}),
    }


def _unsafe_local_transport_config(cwd: Path) -> str:
    """Return non-global git config in `cwd` that could hijack token transport.

    Scans the exact config view a token-bearing fetch/push honors: the local
    config plus any `include.path` file it pulls in and, when
    `extensions.worktreeConfig` is set, the per-worktree `config.worktree` --
    with global/system config detached (the same `GIT_CONFIG_GLOBAL`/`SYSTEM`
    envelope the fetch/push runs under). It deliberately does NOT scope to
    `--local`: a `git config --local` probe reads only the raw local file, so
    it misses `include.path` targets and per-worktree config that the real
    command still resolves and honors. Returns the matching
    `git config --get-regexp` lines joined for logging, or "" when the config
    view is clean; callers refuse to run any GIT_TOKEN-bearing git command
    while the result is non-empty.
    """
    probe = subprocess.run(
        [_GIT, "config", "--get-regexp", _UNSAFE_TRANSPORT_CONFIG_RE],
        cwd=str(cwd), capture_output=True, text=True,
        errors=_UNDECODABLE_BYTES,
        env={
            **os.environ,
            **_GIT_NO_PROMPT_ENV,
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_SYSTEM": os.devnull,
            "GIT_CONFIG_NOSYSTEM": "1",
        },
        check=False,
    )
    if probe.returncode == 0 and probe.stdout.strip():
        return probe.stdout.strip()
    return ""
