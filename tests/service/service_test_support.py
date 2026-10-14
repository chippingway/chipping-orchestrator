# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What the service tests share: the words a setup refuses with, clone remotes, and a fake GitHub."""
from __future__ import annotations

import json
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from orchestrator.service import token_probe
from orchestrator.service.validation import FieldError
from tests.support.git import _run_git

# What a fake GitHub answers a path with: a status and the JSON document it
# carries -- or, as bytes, a body that is not JSON -- or the error the
# standard library raises for a request it could not make or nobody answered.
FakeAnswer = tuple[int, object] | Exception


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


class FakeGitHub:
    """Stands in for ``token_probe.http_get``, answering each API path from a table.

    Every request is recorded as the URL and the token it carried, so a test
    reads back how many calls a step made, to where, and with which token. A
    path the table does not name fails the test rather than reaching GitHub.
    """

    def __init__(self, answers: Mapping[str, FakeAnswer]) -> None:
        self.answers = answers
        self.requests: list[tuple[str, str]] = []

    def __call__(self, url: str, token: str) -> tuple[int, bytes]:
        self.requests.append((url, token))
        answer = self.answers[url.removeprefix(token_probe.API_ROOT)]
        if isinstance(answer, Exception):
            raise answer
        status, document = answer
        if isinstance(document, bytes):
            return status, document
        return status, json.dumps(document).encode()


@contextmanager
def fake_github(answers: Mapping[str, FakeAnswer]) -> Iterator[FakeGitHub]:
    """Answer every probe from ``answers`` while the block runs."""
    github = FakeGitHub(answers)
    with patch.object(token_probe, "http_get", github):
        yield github
