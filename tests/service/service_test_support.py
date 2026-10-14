# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What the service tests share: the words a setup refuses with, and clone remotes."""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from orchestrator.service.validation import FieldError
from tests.support.git import _run_git


def refusal(validator: Callable[..., object], *answer: object, **chosen: object) -> str:
    """The diagnostic ``validator`` refuses ``answer`` with.

    An answer it accepts fails the test that expected a refusal, naming what
    was accepted.
    """
    try:
        validator(*answer, **chosen)
    except FieldError as refused:
        return str(refused)
    raise AssertionError(f"{validator.__qualname__} accepted {answer!r} {chosen!r}")


def add_remote(clone: Path, name: str, url: str, default_branch: str | None = None) -> None:
    """Add a remote to ``clone``, recording ``default_branch`` as its HEAD the way a clone does."""
    _run_git("remote", "add", name, url, cwd=clone)
    if default_branch is not None:
        branch = f"refs/remotes/{name}/{default_branch}"
        _run_git("update-ref", branch, "HEAD", cwd=clone)
        _run_git("symbolic-ref", f"refs/remotes/{name}/HEAD", branch, cwd=clone)
