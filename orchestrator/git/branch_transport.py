# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Token-bearing branch fetches and the branch push, run under a credential session.

The two fetches and the push share this module because they are one transport
read at branch level: each resolves a token through `credentials`, opens a
session around it, and spawns git with the environment that session built and
an argv naming nothing but the `x-access-token` URL. What the token stays out
of is that argv -- git reads it from `$GIT_TOKEN` through the askpass script
instead, so it never reaches the world-readable `/proc/<pid>/cmdline`. The
session carries it here because this module needs it for the one thing the
environment cannot do: scrubbing it back out of the stderr a failed call is
logged with, and out of the stderr a fetch hands its caller -- what a caller
carries into a record and reports somewhere else has to be as safe to print as
what this module logs.

What a branch is at on the remote is asked through `ref_transport` beside this
one, which owns every remote read and write named by a whole refname. The lease
is where the two part: a branch push may look the remote up for itself, because
a branch is a moving thing whose current tip is the honest expectation, while a
ref update there states what the caller established was there and has no form
that overwrites whatever it finds.
"""
from __future__ import annotations

import logging
import subprocess
from pathlib import Path

from orchestrator.config import models as _config_models
from orchestrator.git import commands, credentials, locks, ref_transport

# The channel is named for the git-plumbing domain rather than for this
# module's path: operators filter the rendered `orchestrator.git_plumbing`
# prefix and attach handlers to it, so every fetch and push refusal reports
# where their filters already point.
log = logging.getLogger("orchestrator.git_plumbing")

_FETCH = "fetch"

_PUSH = "push"

# What a push publishes when the caller names no commit of its own: whatever
# the worktree is on now, which is right for every caller that just made the
# work it is publishing.
_HEAD = "HEAD"

# What a caller is told when the token could not be resolved at all, and when
# the checkout it would run in carries config that could redirect the call.
# Stated as text a human reads because they are what a failed transport hands
# back in place of git's own stderr: neither refusal ever spawned git, and a
# caller reporting "no reason" for either would send an operator to the wrong
# thing entirely. Neither quotes the offending config -- what a worktree
# carries is agent-written, and a diagnostic that travels is not where it
# belongs.
_NO_TOKEN = "GITHUB_TOKEN missing"

_UNSAFE_WORKTREE_CONFIG = "unsafe transport config in worktree .git/config"

_UNSAFE_TARGET_CONFIG = "unsafe transport config in target_root .git/config"


def _failed_fetch(stderr: str) -> subprocess.CompletedProcess:
    """Return the stable failure shape shared by authenticated fetches."""
    return subprocess.CompletedProcess(
        args=[commands._GIT, _FETCH], returncode=1, stdout="", stderr=stderr,
    )


def _authed_fetch(
    spec: _config_models.RepoSpec, refspec: str, *, cwd: Path
) -> subprocess.CompletedProcess:
    """Authenticated, hardened `git fetch` -- the same security envelope as
    `_push_branch`.

    Used for fetches from inside an agent-writable worktree where any
    of the following vectors could leak GIT_TOKEN to an attacker host:
      * a planted credential helper in the worktree's `.git/config`,
      * a planted `core.hooksPath` / `core.fsmonitor` that runs an
        attacker-controlled binary with GIT_TOKEN in env,
      * a planted `url.<host>.insteadOf` rewrite in the worktree's
        local config OR in `~/.gitconfig` redirecting fetch to an
        attacker-controlled host,
      * a planted `http.proxy` / `http.sslVerify=false` (or other
        `http.*` TLS/proxy key) in the worktree's local config routing
        the token-bearing fetch through an attacker proxy or disabling
        certificate verification.

    The auth URL carries only the username (`x-access-token`); the
    token itself is read from $GIT_TOKEN by a tempfile askpass script
    so it never appears in argv. Global/system git config is detached
    via `GIT_CONFIG_GLOBAL=/dev/null` / `GIT_CONFIG_SYSTEM=/dev/null`
    so url-rewrite rules planted there cannot apply. We also refuse to
    run if the worktree's local config carries any url-rewrite rule or
    `http.*` transport setting (`_unsafe_local_transport_config`),
    mirroring `_push_branch`'s pre-flight check.

    `refspec` is the fetch refspec; pass an explicit form like
    `+refs/heads/<branch>:refs/remotes/origin/<branch>` so single-branch
    clones still update the remote-tracking ref instead of leaving the
    fetched payload only in FETCH_HEAD.

    The fetch updates the parent clone's `refs/remotes/<remote>/...`
    namespace from inside an agent-writable worktree, which means it
    grabs the parent's ref-update lock under `<git-dir>/packed-refs.lock`
    and `<git-dir>/refs/remotes/<remote>/<branch>.lock`. Two concurrent
    `_authed_fetch` calls from different worktrees of the same
    `target_root` (the common shape during fan-out of multiple
    `resolving_conflict` issues) race those lock files and one fails
    with `Unable to create '...': File exists.`, parking the issue.
    The actual subprocess call is therefore held under the
    per-target_root lock; the pre-flight URL-rewrite check stays
    outside the lock since it only reads the worktree's own
    `.git/config`.
    """
    # Resolve the token from `spec.slug` rather than the cached
    # `config.GITHUB_TOKEN` (which was looked up once for `config.REPO`),
    # so a multi-repo deployment with one token file per slug under
    # `~/.config/<owner>/<repo>/token` fetches with the right repo's token.
    # Mirrors `_push_branch`'s per-spec token resolution; without this,
    # `_handle_resolving_conflict` would fail conflict resolution for any
    # repo other than the legacy `REPO` (or use the wrong token).
    token = credentials._resolved_git_token(spec, _FETCH)
    if not token:
        return _failed_fetch(_NO_TOKEN)
    unsafe = commands._unsafe_local_transport_config(cwd)
    if unsafe:
        log.error(
            "refusing to fetch into %s: worktree .git/config has "
            "transport-hijacking config: %s", cwd, unsafe,
        )
        return _failed_fetch(_UNSAFE_WORKTREE_CONFIG)
    with credentials._git_auth_session(
        spec, token, include_identity=True,
    ) as auth_session, locks._target_root_lock(spec.target_root):
        fetched = subprocess.run(
            [
                *commands._AUTHED_GIT_PREFIX,
                _FETCH, "--quiet", auth_session.auth_url, refspec,
            ],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            env=auth_session.env,
            check=False,
        )
        # Scrubbed here rather than at each caller, because this is the last
        # frame that still holds the token: what a fetch hands back is logged
        # by some callers and carried into a reported record by others.
        fetched.stderr = credentials._scrubbed(
            fetched.stderr, auth_session.token,
        )
        return fetched


def _authed_target_fetch(
    spec: _config_models.RepoSpec, branch: str
) -> subprocess.CompletedProcess:
    """Authed `git fetch` into `spec.target_root` using the per-spec token.

    Replaces the plain `git fetch <remote_name> <branch>` invocations the
    worktree creators (`_ensure_worktree` / `_ensure_pr_worktree` /
    `_ensure_decompose_worktree`) and the per-tick base refresh
    (`_refresh_base_and_worktrees`) used to run. The plain form relied on
    git's ambient credential helper or session state, which fails under
    systemd (`GIT_TERMINAL_PROMPT=0` disables the fallback prompt) and
    has no way to pick a per-repo token when the local clone has several
    GitHub-pointing remotes whose `slug` differs from the
    `~/.config/<owner>/<repo>/token` of the configured `REPO`.

    The `spec.remote_name` field selects the local remote namespace --
    refs land under `refs/remotes/<spec.remote_name>/<branch>` -- while
    `spec.slug` selects which GitHub repo / token to authenticate with.
    Without this split, a `REPOS` row like
    `geserdugarov/lance-private|...|private-cache|private` would try to
    use the cached single-repo `config.GITHUB_TOKEN` (looked up once for
    `config.REPO`) and fail to fetch even with a correct per-spec token
    file in place.

    An explicit refspec `+refs/heads/<branch>:refs/remotes/<remote_name>/<branch>`
    is used so single-branch / narrowed clones still update the
    remote-tracking ref instead of leaving the fetched payload only in
    FETCH_HEAD -- the worktree creators then anchor `git worktree add`
    on `<remote>/<branch>` without surprise.

    Same security envelope as `_push_branch` / `_authed_fetch`: token
    delivered via GIT_ASKPASS (never argv), global/system git config
    detached so url-rewrite rules planted in `~/.gitconfig` cannot
    redirect the fetch to an attacker-controlled host, hooks /
    fsmonitor / credential helpers blocked via `-c` overrides. The
    target_root is normally operator-owned, but a linked worktree
    (which the agent does write) can still mutate the parent clone's
    local config via `git config --local`, and local config still
    applies even with GIT_CONFIG_GLOBAL/SYSTEM detached. Mirror the
    `_authed_fetch` / `_push_branch` pre-flight refusal: bail out if
    `target_root`'s local config carries any
    `url.<host>.(insteadOf|pushInsteadOf)` rule or `http.*` proxy/TLS
    setting that could redirect the token-bearing fetch to an
    attacker-controlled host or strip TLS verification
    (`_unsafe_local_transport_config`).

    Serialized via `_target_root_lock` (`RLock` so a caller already
    holding it -- the worktree creators -- re-enters cleanly) for the
    same `.git/config.lock` reason described on `_ensure_worktree`.
    """
    token = credentials._resolved_git_token(spec, _FETCH)
    if not token:
        return _failed_fetch(_NO_TOKEN)
    unsafe = commands._unsafe_local_transport_config(spec.target_root)
    if unsafe:
        log.error(
            "refusing to fetch into %s: target_root .git/config has "
            "transport-hijacking config: %s", spec.target_root, unsafe,
        )
        return _failed_fetch(_UNSAFE_TARGET_CONFIG)
    refspec = (
        f"+refs/heads/{branch}:refs/remotes/{spec.remote_name}/{branch}"
    )
    with credentials._git_auth_session(spec, token) as auth_session, locks._target_root_lock(spec.target_root):
        fetched = subprocess.run(
            [
                *commands._AUTHED_GIT_PREFIX,
                _FETCH, "--quiet", auth_session.auth_url, refspec,
            ],
            cwd=str(spec.target_root),
            capture_output=True,
            text=True,
            env=auth_session.env,
            check=False,
        )
        # Scrubbed for the reason `_authed_fetch` is: this frame is the last
        # one holding the token, and what a fetch reports travels.
        fetched.stderr = credentials._scrubbed(
            fetched.stderr, auth_session.token,
        )
        return fetched


def _remote_branch_tip(
    spec: _config_models.RepoSpec, worktree: Path, branch: str,
) -> str | None:
    """Ask the REMOTE what `branch` is at, ignoring every local ref.

    For the caller that has to measure an agent's work against a base it
    cannot have moved. `refs/remotes/<remote>/<base>` looks like that base but
    is a local ref in an object store the agent's worktree shares, so an agent
    that commits code, repoints that ref at its own commit, and then commits
    the plan leaves a base-relative diff showing only the plan -- while the
    branch it would publish carries both. The remote's own answer is the one
    nothing on this host can rewrite.

    None on any failure -- a missing token, a worktree whose config could
    hijack the transport, or an unreachable remote -- and "" when the branch
    does not exist there. A caller pinning a base treats both as "no base was
    established", which is the only safe reading for a check that gates a push.

    A caller asking whether its own work is still out there has to tell them
    apart, and the discussion stage's publication does: "" is the remote saying
    that branch is not there, which is what lets a record of an unfinished
    publication finally be spent, while None established nothing and keeps it.
    Collapsing the two would drop the record of a plan on every reading that
    failed.

    What the failure SAID is not on this answer. A caller that has to report a
    reading rather than act on one asks `_remote_branch_read` beside this,
    which is the same read with git's own line still attached.
    """
    return _remote_branch_read(spec, worktree, branch).sha


def _remote_branch_read(
    spec: _config_models.RepoSpec, worktree: Path, branch: str,
) -> ref_transport._RefRead:
    """The same read, with the one line saying why it established nothing.

    For the caller that has to REPORT a reading it could not take, rather than
    only act on one. A size measurement is that caller: a base it cannot freeze
    parks the issue for a human, and "the remote would not name the base" sends
    an operator looking at everything from an expired token to a repository the
    installation was never granted. The line git wrote says which, and it is
    already scrubbed of the token by the transport that ran it.

    The two refusals that never reach git answer for themselves, because
    neither leaves an operator anywhere to look otherwise: a token this
    deployment could not resolve for the repository, and a checkout whose own
    config could send a token-bearing read somewhere else.
    """
    token = credentials._resolved_git_token(spec, "read the remote branch tip")
    if not token:
        return ref_transport._RefRead(detail=_NO_TOKEN)
    unsafe = commands._unsafe_local_transport_config(worktree)
    if unsafe:
        log.error(
            "refusing to read %s from the remote: worktree .git/config has "
            "transport-hijacking config: %s", branch, unsafe,
        )
        return ref_transport._RefRead(detail=_UNSAFE_WORKTREE_CONFIG)
    with credentials._git_auth_session(spec, token) as auth_session:
        return ref_transport._remote_ref_read(
            auth_session, worktree, branch, f"refs/heads/{branch}",
        )


def _push_with_auth(
    auth_session: credentials._GitAuthSession,
    worktree: Path,
    branch: str,
    force_with_lease: str | None,
    revision: str,
) -> bool:
    """Push one branch through an established askpass session."""
    ref = f"refs/heads/{branch}"
    remote_sha = (
        ref_transport._remote_ref_read(
            auth_session, worktree, branch, ref,
        ).sha
        if force_with_lease is None
        else force_with_lease
    )
    if remote_sha is None:
        return False
    push_result = subprocess.run(
        [
            *commands._AUTHED_GIT_PREFIX,
            _PUSH,
            f"--force-with-lease={ref}:{remote_sha}",
            auth_session.auth_url,
            f"{revision}:{ref}",
        ],
        cwd=str(worktree),
        capture_output=True,
        text=True,
        env=auth_session.env,
        check=False,
    )
    if push_result.returncode == 0:
        return True
    scrubbed = credentials._scrubbed(
        push_result.stderr, auth_session.token,
    )
    log.error("git push failed for %s: %s", branch, scrubbed)
    return False


def _push_branch(
    spec: _config_models.RepoSpec, worktree: Path, branch: str,
    *,
    force_with_lease: str | None = None,
    revision: str | None = None,
) -> bool:
    """Push via GIT_ASKPASS so the token never appears in argv.

    `revision`, when provided, is the exact commit to publish, and it exists
    for every caller that decided to push by INSPECTING one. Nearly all of
    them do. The `discussion` stage's plan publication reads a branch and
    proves it carries the agreed plan and nothing else; the `implementing`
    stage's publication decides on one commit ahead of the push -- the one the
    size gate measured or an authorized settlement accepted, or the one the checkout is
    standing on where the gate proved none -- and names the push, the receipt
    it records, and the proof it takes once the pull request is open against
    that same commit. Every push onto a pull request the remote ALREADY
    carries names one too, and for the same reason: the size gate measures
    before each of them and hands back the commit it measured -- the dev-fix
    publication and the bounce behind it, both validating recoveries, the
    three conflict publications, the base sync's auto-rebase and its crash
    recovery, and the final docs pass.
    `HEAD` between the reading and the push is not necessarily what was proven
    -- another tick, an operator, or a stray agent can move it -- and pushing
    whatever HEAD says would publish work no check ever saw while the record
    named the commit that passed. Naming the SHA closes that window in the
    only place it can be closed: a revision the local repo no longer has is
    refused by git rather than substituted.

    The two initial publications have no fallback here, which is a fact about
    them rather than about this helper: a checkout that cannot name the commit
    it is on is refused by its own caller before this is reached, because a
    push named against nothing would send whatever the branch had become and
    leave the receipt and both proofs with no commit to compare against.

    What reaches this function with no `revision` is one push and only one: a
    gated one on an install running with `DECOMPOSE=off` whose checkout would
    not prove its own head. The switch keeps candidates out of the
    MEASUREMENT rather than out of a push that knows what it is publishing, so
    the commit is named off the checkout there too -- only a reading that
    failed outright falls through, publishing whatever the worktree currently
    is with the receipt and the post-push proof skipped, since neither has a
    commit to be about.

    `force_with_lease`, when provided, is the SHA the caller expects the
    remote ref to be at. The push then uses
    `--force-with-lease=refs/heads/<branch>:<sha>` against that exact SHA,
    so a concurrent update to the remote rejects the push instead of being
    silently clobbered, and no `ls-remote` of our own is taken. Any caller
    that DECIDED to push by reading the remote belongs on this path: the
    squash/rewrite, which pins the pre-rewrite HEAD it approved; the
    `discussion` stage's plan publication, which pins the tip it
    established the branch was safe to move; the conflict and base-sync
    publications, each pinning the SHA it read for itself -- the pre-rebase
    head, or the pull-request head it validated as this orchestrator's own;
    and every push the size gate let through, which pins the head the pull
    request was standing on when the reading was taken, so a pull request
    somebody pushed to since rejects work measured against the head it used
    to be on.
    Pinning is what prevents the
    "out-of-band update happened in the window between the reading and the
    push" race -- a fresh `ls-remote` would treat the unexpected new remote
    SHA as the lease value and silently overwrite it, which for a
    publication being retried after a crash means overwriting whoever
    pushed to the branch in between.

    When `force_with_lease` is None (the default), the function reads the
    current remote SHA via `ls-remote` and uses that as the lease. This is
    the normal-push path: the orchestrator owns the
    `orchestrator/<slug>/issue-<n>` namespace, but a self-restart between commit
    and push can leave the worktree on a different SHA than what was
    already pushed -- e.g. a `resume=False` rerun of codex amending
    equivalent work. A plain push then fails non-fast-forward and parks
    the issue. The lease lets the retry succeed while still refusing to
    clobber a concurrent foreign update (the lease check compares against
    what we observed, not a stale remote-tracking ref).

    The push target URL carries only the username (`x-access-token`); the
    token itself is read from the GIT_TOKEN env var by a tempfile askpass
    script. This keeps the PAT out of `/proc/<pid>/cmdline`, which is
    world-readable on Linux. The refspec is explicit either way -- so no
    upstream is set and no remote URL is stored in .git/config -- and which
    one it is follows `revision`: `<revision>:refs/heads/<branch>` where a
    caller named the commit it means, and `HEAD:refs/heads/<branch>` where
    none did.

    The worktree is shared with the codex agent, so anything in `.git/hooks/`
    or `.git/config` is attacker-controlled. The agent also writes as the same
    OS user, so it can plant `~/.gitconfig` (or anything pointed at by
    XDG_CONFIG_HOME) before we push. We harden the push so a planted pre-push
    hook, credential helper, fsmonitor, url-rewrite rule, or http proxy /
    TLS override cannot observe GIT_TOKEN or redirect the push to an
    attacker-controlled host:
      * `core.hooksPath=/dev/null` disables `.git/hooks/*` and any hooksPath
        override the agent set in the local config.
      * `credential.helper=` (empty) clears all inherited credential helpers
        so a repo-local helper script never executes with GIT_TOKEN in env.
      * `core.fsmonitor=` disables any fsmonitor program git would otherwise
        spawn for index-touching operations.
      * `GIT_CONFIG_GLOBAL=/dev/null` and `GIT_CONFIG_SYSTEM=/dev/null` block
        global/system config entirely, so url.<host>.insteadOf or
        pushInsteadOf rules planted in `~/.gitconfig` (or `/etc/gitconfig`)
        cannot rewrite our auth URL and exfiltrate the askpass token.
      * We also refuse to push if the local config contains any url
        insteadOf/pushInsteadOf rewrite or any `http.*` transport setting
        (`_unsafe_local_transport_config`). A rewrite redelivers the token
        to whatever host the agent picked; a local `http.proxy` /
        `http.sslVerify=false` (or URL-scoped `http.<url>.*` variant, which a
        command-line `-c http.proxy=` override cannot beat) would tunnel the
        token-bearing push through an attacker proxy or disable TLS
        verification. Env-var proxies (`https_proxy`) are operator-set and
        stay honored -- only agent-writable config-file transport is rejected.
    """
    # Resolve the token from `spec.slug` rather than the cached
    # `config.GITHUB_TOKEN` (which was looked up once for `config.REPO`),
    # so a multi-repo deployment with one token file per slug under
    # `~/.config/<owner>/<repo>/token` pushes with the right repo's token.
    # Single-repo deployments see identical behavior because
    # `_resolve_github_token(REPO)` returns the same value.
    token = credentials._resolved_git_token(spec, _PUSH)
    if not token:
        return False
    unsafe = commands._unsafe_local_transport_config(worktree)
    if unsafe:
        log.error(
            "refusing to push %s: worktree .git/config has "
            "transport-hijacking config: %s", branch, unsafe,
        )
        return False
    with credentials._git_auth_session(spec, token) as auth_session:
        # An empty expected SHA means the remote ref must not exist, which
        # preserves the create-branch lease behavior.
        return _push_with_auth(
            auth_session, worktree, branch, force_with_lease, revision or _HEAD,
        )
