# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Exact-ref reads and the lease-pinned writes over the authenticated transport.

The read and the two writes sit on one owner because they are one contract: a
caller establishes what the remote says one named ref is at and then states
that reading back as the lease its write is pinned to. There is no form here
that overwrites whatever it finds, which is what an immutable ref namespace is
owned through -- an empty lease says the ref must not exist, and any other
value says it must still be exactly what was read.

One question, because one question is what a lease can be pinned to: what the
remote holds a fully-qualified ref at. What it carries under a PATTERN is asked
through `ref_discovery` beside this module, and is nobody's lease -- a listing
says which artifacts are out there, and every one of them still has to be read
by name before anything may be written over it.

The read is asked of the remote rather than of a local ref because the object
store a worktree shares is writable by the agent running in it: a local ref
that looks like the answer proves nothing, while the remote's own answer is the
one nothing on this host can rewrite. It is the lower half of every leased
remote question the git layer asks -- the branch transport beside this module
spends it on `refs/heads/<branch>`.

Every call runs under the whole token-bearing envelope: a token resolved per
repository through `credentials`, an askpass session that keeps it out of the
world-readable `/proc/<pid>/cmdline`, global and system config detached, hooks,
credential helpers, and fsmonitor disabled by `-c`, and a refusal when the
worktree's local config carries a url rewrite or an `http.*` setting that could
redirect the call to an attacker-controlled host. The session carries the token
back here for the one thing the environment cannot do: scrubbing it out of the
stderr a failed call is logged with -- and handed back on, since the caller that
has to explain a reading it could not take is a long way from the process that
took it.

What policy the leases serve -- which namespace, and what an existing ref at
another commit means -- belongs to the callers. `git/snapshots/` owns the
immutable namespace the create and the delete were written for; the terminal
artifact reclamation under `git/worktrees/` spends the same delete on a branch
it has proved.
"""
from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path

from orchestrator.config import models as _config_models
from orchestrator.git import commands, credentials, locks

# The channel is named for the git-plumbing domain rather than for this
# module's path: operators filter the rendered `orchestrator.git_plumbing`
# prefix and attach handlers to it, so every read and update refusal reports
# where their filters already point.
log = logging.getLogger("orchestrator.git_plumbing")

_PUSH = "push"

# What a read that failed with nothing on its stderr says for itself, so a
# detail is empty only where a read SUCCEEDED and answered "no such ref".
_SAID_NOTHING = "git reported no reason"


@dataclass(frozen=True)
class _RefRead:
    """What the remote says a ref is at, and why a read that failed did.

    The two fields answer different callers. `sha` is the reading -- a commit
    id, "" where the remote does not carry the ref at all, and None where the
    read established nothing -- and it is the only thing a lease or a freeze
    may be pinned to. `detail` is the one line of git's own stderr that says
    WHY nothing was established, carried so a caller reporting a failure to an
    operator can say which of the many ways a token-bearing read fails this
    one was: a rejected token, an unreachable host, a repository the token
    cannot see. It is scrubbed of the token before it is set, because a
    diagnostic that leaks the secret is one no caller could safely log.

    Empty exactly where `sha` is not None: a read that answered, even with "",
    has nothing to explain.
    """

    sha: str | None = None
    detail: str = ""


@dataclass(frozen=True)
class _RefUpdate:
    """One lease-pinned write to a fully-qualified ref, and what it is called.

    Carried as a record rather than as four arguments because the four are one
    decision: the ref names what is being written, the refspec says whether
    that is a commit or a deletion, the lease says what the caller established
    was there first, and the name is what a refusal is reported as. A caller
    assembling three of them and forgetting the fourth would be pushing
    without a lease, which is the one thing this transport does not do.
    """

    ref: str
    refspec: str
    expected: str
    operation: str


def _remote_ref_read(
    auth_session: credentials._GitAuthSession,
    worktree: Path,
    label: str,
    ref: str,
) -> _RefRead:
    """Return what the remote says `ref` is at through an open session.

    "" where the remote does not carry that ref at all, and None where the read
    established nothing, so a caller can tell an answer apart from a failure.
    `label` is what a failed read is reported as -- the branch a caller asked
    about rather than the refname it was spelled as.

    A failure is reported to the operator AND handed back. The log line is
    where somebody watching the plumbing sees it; the record is for the caller
    that has to say why a decision it owns could not be taken, minutes later
    and somewhere else, where nothing has this stderr any more. Both spend the
    same scrubbed text, so the token cannot reach either.
    """
    ls_remote = subprocess.run(
        [*commands._AUTHED_GIT_PREFIX, "ls-remote", auth_session.auth_url, ref],
        cwd=str(worktree),
        capture_output=True,
        text=True,
        env=auth_session.env,
        check=False,
    )
    if ls_remote.returncode != 0:
        scrubbed = credentials._scrubbed(
            ls_remote.stderr, auth_session.token,
        )
        log.error("git ls-remote failed for %s: %s", label, scrubbed)
        return _RefRead(
            detail=commands._first_reported_line(scrubbed) or _SAID_NOTHING,
        )
    for output_line in (ls_remote.stdout or "").splitlines():
        parts = output_line.strip().split()
        if len(parts) >= 2 and parts[1] == ref:
            return _RefRead(sha=parts[0])
    return _RefRead(sha="")


def _remote_ref_sha(
    spec: _config_models.RepoSpec, worktree: Path, ref: str,
) -> str | None:
    """Ask the REMOTE what one fully-qualified ref resolves to.

    The read every snapshot decision is made on, and it is taken from the
    remote rather than from a local ref for the reason the branch tip read is:
    the object store a worktree shares is writable by the agent that runs in
    it, so a local ref that looks like the snapshot proves nothing about what
    the remote actually carries.

    Three answers, and the caller has to tell them apart. A SHA is the ref as
    the remote holds it. "" is the remote saying it does not carry that ref at
    all, which is what makes an absent-is-success deletion and a create that
    may proceed possible. None established nothing -- a missing token, a
    worktree whose config could hijack the transport, an unreachable remote --
    and a caller that created or deleted on the strength of it would be acting
    on a reading nobody gave.
    """
    token = credentials._resolved_git_token(spec, "read the remote ref")
    if not token:
        return None
    unsafe = commands._unsafe_local_transport_config(worktree)
    if unsafe:
        log.error(
            "refusing to read %s from the remote: worktree .git/config has "
            "transport-hijacking config: %s", ref, unsafe,
        )
        return None
    with credentials._git_auth_session(spec, token) as auth_session:
        return _remote_ref_read(auth_session, worktree, ref, ref).sha


def _push_ref(
    spec: _config_models.RepoSpec,
    worktree: Path,
    *,
    ref: str,
    revision: str,
    expected: str,
) -> bool:
    """Publish one exact commit under one fully-qualified ref.

    `expected` is the SHA the caller established the remote ref was at, and it
    is required rather than optional: this is the transport an immutable ref
    namespace is written through, so it has no form that overwrites whatever
    happens to be there. An empty string is the lease saying the ref must not
    exist, which is how a snapshot is created; any other value is the lease
    saying it must still be exactly what the caller read.

    The revision is named rather than pushed as `HEAD`, for the reason the
    branch push takes one: what is published is a commit somebody proved, and
    HEAD between the proof and the push is not necessarily still it.
    """
    return _authed_ref_update(spec, worktree, _RefUpdate(
        ref=ref,
        refspec=f"{revision}:{ref}",
        expected=expected,
        operation=_PUSH,
    ))


def _delete_remote_ref(
    spec: _config_models.RepoSpec, worktree: Path, *, ref: str, expected: str,
) -> bool:
    """Delete one fully-qualified ref the caller has just read.

    Pinned to what that read said, for the reason the create is: a ref
    somebody re-pointed between the read and the delete is not the ref this
    caller decided was reclaimable, and deleting it would destroy an artifact
    nobody adjudicated. A caller that found nothing there has nothing to
    delete and never reaches this.
    """
    return _authed_ref_update(spec, worktree, _RefUpdate(
        ref=ref,
        refspec=f":{ref}",
        expected=expected,
        operation="delete",
    ))


def _authed_ref_update(
    spec: _config_models.RepoSpec, worktree: Path, update: _RefUpdate,
) -> bool:
    """Run one lease-pinned ref update under the whole transport envelope.

    The same envelope the branch push runs under -- per-spec token, askpass so
    the token never reaches argv, global and system config detached, hooks,
    credential helpers, and fsmonitor disabled by `-c`, and a refusal when the
    local config carries a url rewrite or an `http.*` setting that could
    redirect the token-bearing push -- because this call carries the same token
    to the same host.

    Held under the target-root lock, which the branch push does not need and
    this does: the namespace it writes is the one a verifying fetch reads back
    into the shared clone, so a concurrent fetch of the same namespace from
    another worktree of this target root would race the update it is proving.
    """
    token = credentials._resolved_git_token(spec, f"{update.operation} {update.ref}")
    if not token:
        return False
    unsafe = commands._unsafe_local_transport_config(worktree)
    if unsafe:
        log.error(
            "refusing to %s %s: worktree .git/config has "
            "transport-hijacking config: %s",
            update.operation, update.ref, unsafe,
        )
        return False
    with credentials._git_auth_session(spec, token) as auth_session:
        with locks._target_root_lock(spec.target_root):
            updated = subprocess.run(
                [
                    *commands._AUTHED_GIT_PREFIX,
                    _PUSH,
                    f"--force-with-lease={update.ref}:{update.expected}",
                    auth_session.auth_url,
                    update.refspec,
                ],
                cwd=str(worktree),
                capture_output=True,
                text=True,
                env=auth_session.env,
                check=False,
            )
        if updated.returncode == 0:
            return True
        log.error(
            "git %s failed for %s: %s",
            update.operation,
            update.ref,
            credentials._scrubbed(updated.stderr, auth_session.token),
        )
    return False
