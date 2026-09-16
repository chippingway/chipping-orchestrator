# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The commits the orchestrator creates on a branch itself, and how.

There are two. A squash collapses the approved commits into one the
orchestrator authors, and the documenting stage replaces the docs commit it
publishes with one whose subject names its pull request. Both are created in a
checkout an agent can write the config of, so both go through the one hardened
envelope spelled here -- detached global and system config, with hooks,
fsmonitor, and signing turned off -- rather than through copies that could each
lose a different protection.

The replacement is bound to the commit it replaces, never to whatever HEAD is
by the time it lands. It is built from that commit's own tree, parents, and
author, so nothing but its message and committer differ, and HEAD is moved onto
it only by a compare-and-swap against that commit: a checkout something
committed on in the meantime refuses the move instead of having the newer
commit rewritten and handed on in the docs commit's place. `git commit --amend`
cannot make that promise, since it rewrites whatever HEAD is when it runs.

The message a replacement starts from is read off the same object, and both
that read and the rebuild carry the bytes git stored: text capture translates a
CR LF pair, and a lone CR, into LF on the way in, and a body read that way and
written back would be one nobody wrote. Which subject a squash is given is
``titles``'s question, and the reference a published subject ends in is
``pr_references``'s.
"""
from __future__ import annotations

import os
import re
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from orchestrator import config
from orchestrator.git import commands

# The overrides every orchestrator commit is created under, in a checkout whose
# config an agent can write.
_COMMIT_OVERRIDES = (
    "-c", "core.hooksPath=/dev/null",
    "-c", "core.fsmonitor=",
    "-c", "commit.gpgsign=false",
)

# How a message's bytes ride as text and back. Git promises nothing about the
# encoding of a message, so a byte that is not UTF-8 is carried as a surrogate
# and written back as the byte it was.
_MESSAGE_ENCODING = "utf-8"

# The header lines a replacement is rebuilt from. Each is matched against the
# header block alone, so a message line that reads like one cannot answer.
_TREE_RE = re.compile(r"^tree ([0-9a-f]+)$", re.MULTILINE)
_PARENT_RE = re.compile(r"^parent ([0-9a-f]+)$", re.MULTILINE)
_AUTHOR_RE = re.compile(
    r"^author (.*) <([^<>\n]*)> (\d+ [+-]\d{4})$", re.MULTILINE,
)

# What the reflog says moved HEAD onto a replacement.
_REPLACEMENT_REFLOG = "orchestrator: name the pull request in the commit subject"


@dataclass(frozen=True)
class _Amendment:
    """What replacing one commit with a new message came to.

    `sha` is the replacement HEAD was moved onto, and empty wherever HEAD was
    not moved. `moved` says the compare-and-swap refused: HEAD was no longer
    the commit being replaced, or something else held it. `error` is git's own
    line for whichever step refused.
    """

    sha: str = ""
    moved: bool = False
    error: str = ""


def _orchestrator_commit_env(
    author: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Return the hardened identity every orchestrator commit is created under.

    The squash commit is authored and committed as the orchestrator. A
    replacement keeps the author of the commit it replaces, handed in as
    `author`, so only its committer is the orchestrator's.
    """
    return {
        **os.environ,
        **commands._GIT_NO_PROMPT_ENV,
        "GIT_AUTHOR_NAME": config.AGENT_GIT_NAME,
        "GIT_AUTHOR_EMAIL": config.AGENT_GIT_EMAIL,
        "GIT_COMMITTER_NAME": config.AGENT_GIT_NAME,
        "GIT_COMMITTER_EMAIL": config.AGENT_GIT_EMAIL,
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_SYSTEM": os.devnull,
        "GIT_CONFIG_NOSYSTEM": "1",
        **(author or {}),
    }


def _orchestrator_git(
    worktree: Path, *git_args: str,
) -> subprocess.CompletedProcess:
    """Create a commit with hooks, fsmonitor, and signing disabled."""
    return subprocess.run(
        ["git", *_COMMIT_OVERRIDES, *git_args],
        cwd=str(worktree),
        capture_output=True,
        text=True,
        env=_orchestrator_commit_env(),
        check=False,
    )


def _commit_parts(worktree: Path, revision: str) -> tuple[str, str] | None:
    """`revision`'s header block and its whole message, or None.

    Read off the commit object rather than through `git log`, whose output a
    repository-local `log.showSignature` or `i18n.logOutputEncoding` would
    change, and as bytes rather than as text, whose newline translation would
    change the message itself -- a caller writes back what it reads here.
    Hardened, so a planted replacement object cannot answer for the commit
    either.
    """
    read = commands._git_hardened_bytes(
        "cat-file", "commit", revision, cwd=worktree,
    )
    if read.returncode != 0:
        return None
    # A commit object is its headers, one empty line, then the message; no
    # header line is empty, since a continued value starts with a space.
    headers, _, message = (read.stdout or b"").partition(b"\n\n")
    return (
        headers.decode(_MESSAGE_ENCODING, commands._UNDECODABLE_BYTES),
        message.decode(_MESSAGE_ENCODING, commands._UNDECODABLE_BYTES),
    )


def _commit_message(worktree: Path, revision: str) -> str | None:
    """The whole message `revision` carries, byte for byte, or None.

    None is a read that did not happen, which a caller must not take for a
    message that needs nothing.
    """
    parts = _commit_parts(worktree, revision)
    return parts[1] if parts else None


def _amend_commit_message(
    worktree: Path, commit: str, message: str,
) -> _Amendment:
    """Replace `commit` at HEAD with a commit carrying `message` instead.

    The replacement is built from `commit` by id, and HEAD is moved onto it
    only if HEAD is still `commit` when the move lands -- so the id that comes
    back is the one commit a caller may publish in `commit`'s place, and a HEAD
    read afterwards is no substitute for it. The index is never read: anything
    staged stays staged and out of the replacement.
    """
    replacement = _replacement(worktree, commit, message)
    if not replacement.sha:
        return replacement
    swapped = commands._git_hardened(
        "update-ref", "-m", _REPLACEMENT_REFLOG,
        "HEAD", replacement.sha, commit,
        cwd=worktree,
    )
    if swapped.returncode != 0:
        return _Amendment(moved=True, error=(swapped.stderr or "").strip())
    return replacement


def _replacement(worktree: Path, commit: str, message: str) -> _Amendment:
    """Create `commit` over again carrying `message`, without moving any ref.

    Its tree, its parents, and its author's identity and date are `commit`'s
    own. A commit object that cannot be read, or one missing a header it is
    rebuilt from, is refused rather than guessed at.
    """
    headers = (_commit_parts(worktree, commit) or ("", ""))[0]
    tree = _TREE_RE.search(headers)
    author = _AUTHOR_RE.search(headers)
    if tree is None or author is None:
        return _Amendment(error=f"commit {commit} could not be read")
    parents = [
        argument
        for parent in _PARENT_RE.findall(headers)
        for argument in ("-p", parent)
    ]
    # The message goes in on stdin as the bytes it was read as: an argument
    # cannot carry every byte a message may hold, and nothing on this path may
    # translate one.
    created = subprocess.run(
        [
            "git", *_COMMIT_OVERRIDES,
            "commit-tree", tree.group(1), *parents, "-F", "-",
        ],
        cwd=str(worktree),
        input=message.encode(_MESSAGE_ENCODING, commands._UNDECODABLE_BYTES),
        capture_output=True,
        env=_orchestrator_commit_env({
            "GIT_AUTHOR_NAME": author.group(1),
            "GIT_AUTHOR_EMAIL": author.group(2),
            # The raw `<seconds> <offset>` form, which git reads back exactly.
            "GIT_AUTHOR_DATE": f"@{author.group(3)}",
        }),
        check=False,
    )
    if created.returncode != 0:
        return _Amendment(
            error=created.stderr.decode(_MESSAGE_ENCODING, "replace").strip(),
        )
    return _Amendment(sha=created.stdout.decode(_MESSAGE_ENCODING).strip())
