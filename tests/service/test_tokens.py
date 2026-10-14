# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""set-token: a token read from standard input, proved, then kept owner-only."""
from __future__ import annotations

import getpass
import io
import os
import sys
import termios
import unittest
from typing import NamedTuple
from unittest.mock import patch

from orchestrator.service import token_probe, tokens
from tests.service.service_test_support import FakeAnswer, fake_github
from tests.service.token_test_support import (
    LOOSE_FILE,
    OLD_TOKEN,
    REACHED,
    REPOSITORY,
    Terminal,
    TokenHomeTest,
    TokenRun,
    tree,
)

_TOKEN = "github_pat_11ABCDEFG0123456789_abcdefghijklmnop"
_PROVED = (f"{token_probe.API_ROOT}/repos/{REPOSITORY}", _TOKEN)
_PROMPT = "GitHub token for acme/api (input hidden): "
_REFUSED = "chipping-orchestrator set-token: "
_NO_TOKEN = f"{_REFUSED}no token was given; give the repository's GitHub token\n"
_NOT_ONE_TOKEN = (
    f"{_REFUSED}the token holds a blank, a line break, or a character outside "
    "visible ASCII; give the token alone, on one line\n"
)
_ECHOING = (
    f"{_REFUSED}this terminal cannot hide the token as it is typed, so none was "
    "read; pipe the token in or redirect a file in instead\n"
)
_EVERY_BIT = 0o777
# 128 + SIGINT, what a shell reports for a command Ctrl+C stopped.
_INTERRUPTED = 130


class _Refusal(NamedTuple):
    """Standard input set-token refuses, GitHub's answer, and the requests made."""

    given: str
    answer: FakeAnswer
    error: str
    requests: list[tuple[str, str]]


_REFUSALS = (
    _Refusal("", REACHED, _NO_TOKEN, []),
    _Refusal(" \n\t\n", REACHED, _NO_TOKEN, []),
    _Refusal(f"{_TOKEN}\n{_TOKEN}\n", REACHED, _NOT_ONE_TOKEN, []),
    _Refusal(f"token {_TOKEN}", REACHED, _NOT_ONE_TOKEN, []),
    _Refusal(
        _TOKEN,
        (401, {"message": "Bad credentials"}),
        (
            f"{_REFUSED}GitHub does not accept the token; it is mistyped, expired, "
            "or revoked (GitHub answered 401: Bad credentials)\n"
        ),
        [_PROVED],
    ),
    _Refusal(
        _TOKEN,
        ConnectionRefusedError("connection refused"),
        f"{_REFUSED}GitHub could not be reached (connection refused)\n",
        [_PROVED],
    ),
)


class PipedTokenTest(TokenHomeTest):
    """A script pipes the token in: it is read to the end with the blanks
    around it dropped, proved with one call for the repository, and written
    owner-only in an owner-only directory. Nothing else under the home is
    written -- no `.env` -- and the token is printed nowhere.
    """

    def test_the_token_is_proved_then_kept(self) -> None:
        run = self.set_token(io.StringIO(f"  {_TOKEN}\r\n"))

        self.assertEqual(run, TokenRun(
            0,
            f"The token reaches {REPOSITORY}; saved it to {self.path}\n",
            "",
            [_PROVED],
        ))
        self.assert_kept(_TOKEN)
        self.assertEqual(
            tree(self.home),
            [".config", ".config/acme", ".config/acme/api", ".config/acme/api/token"],
        )


class TerminalTokenTest(TokenHomeTest):
    """On a terminal the token is typed at a prompt that names the repository
    and does not echo, and standard input itself is never read. Ctrl+C there
    writes nothing and says so; Ctrl+D is an empty answer. A terminal whose
    echo cannot be turned off is refused before anything is read from it, so
    the token is neither shown nor taken, and the old one stays.
    """

    def test_the_hidden_prompt_supplies_the_token(self) -> None:
        with patch.object(getpass, "getpass", return_value=f"{_TOKEN}\n") as prompt:
            run = self.set_token(Terminal())

            prompt.assert_called_once_with(_PROMPT)
        self.assertEqual(run.status, 0, run.stderr)
        self.assertEqual(run.requests, [_PROVED])
        self.assertNotIn(_TOKEN, run.stdout)
        self.assert_kept(_TOKEN)

    def test_leaving_the_prompt_writes_nothing(self) -> None:
        for left, expected in (
            (KeyboardInterrupt, TokenRun(_INTERRUPTED, "", f"\n{_REFUSED}interrupted; nothing was written\n", [])),
            (EOFError, TokenRun(1, "", _NO_TOKEN, [])),
        ):
            with self.subTest(left=left), patch.object(getpass, "getpass", side_effect=left):
                self.assertEqual(self.set_token(Terminal()), expected)
                self.assertEqual(tree(self.home), [])

    def test_a_terminal_that_would_echo_is_refused(self) -> None:
        # Where getpass cannot turn echo off, it reads the line from standard
        # input with echo on; here that input holds the token it would show.
        self.keep_old_token()
        echoed = io.StringIO(f"{_TOKEN}\n")
        unhidden = termios.error("echo cannot be turned off")
        with patch.object(termios, "tcgetattr", side_effect=unhidden), patch.object(sys, "stdin", echoed):
            run = self.set_token(Terminal())

        self.assertEqual(run, TokenRun(1, "", _ECHOING, []))
        self.assertEqual(echoed.tell(), 0)
        self.assertEqual(self.path.read_text(), f"{OLD_TOKEN}\n")


class ReplacedTokenTest(TokenHomeTest):
    """A token that reaches its repository replaces the one kept before it,
    and the file and directory a looser setup left readable are made
    owner-only, with no temporary file left beside the token.
    """

    def test_the_new_token_replaces_the_old(self) -> None:
        self.keep_old_token()

        run = self.set_token(io.StringIO(_TOKEN))

        self.assertEqual(run.status, 0, run.stderr)
        self.assert_kept(_TOKEN)


class RefusedTokenTest(TokenHomeTest):
    """Input that holds no single token, and a token GitHub does not prove,
    leave the token already kept exactly as it was. Each refusal exits 1 with
    its reason on standard error, and neither stream ever carries the token.
    Input that is no token at all never reaches GitHub, and a repository that
    is not one -- the token, given in its place -- is refused unquoted before
    anything is read.
    """

    def test_a_refusal_keeps_the_old_token(self) -> None:
        self.keep_old_token()
        for refused in _REFUSALS:
            with self.subTest(given=refused.given, answer=refused.answer):
                run = self.set_token(io.StringIO(refused.given), refused.answer)

                self.assertEqual(run, TokenRun(1, "", refused.error, refused.requests))
                self.assertEqual(self.path.read_text(), f"{OLD_TOKEN}\n")

    def test_undecodable_input_is_refused(self) -> None:
        # Unquoted: the bytes it stopped at are part of the token.
        undecodable = io.TextIOWrapper(io.BytesIO(b"ghp_\xff\xfe"), encoding="utf-8")

        self.assertEqual(self.set_token(undecodable), TokenRun(
            1,
            "",
            f"{_REFUSED}standard input is not text; give the token alone, on one line\n",
            [],
        ))

    def test_a_refused_repository_is_not_quoted(self) -> None:
        with fake_github({}) as github, patch("sys.stderr", new_callable=io.StringIO) as stderr:
            self.assertEqual(tokens.set_token(_TOKEN, Terminal()), 1)
            self.assertEqual(github.requests, [])
            self.assertEqual(
                stderr.getvalue(),
                f"{_REFUSED}the repository given is not written owner/name, and is not printed "
                "back in case it is the token; give a GitHub owner and repository name joined "
                "by one '/', such as acme/api, and the token on standard input\n",
            )


class RestrictiveUmaskTest(TokenHomeTest):
    """The modes are set outright rather than left to the umask. Under one
    that clears every bit, a token kept for the first time and one replacing
    it are both written 0600, readable by their owner, and every directory
    the run created above them is 0700 rather than closed to that owner too.
    """

    def test_no_mode_is_left_to_the_umask(self) -> None:
        os.umask(_EVERY_BIT)
        for token in (OLD_TOKEN, _TOKEN):
            with self.subTest(token=token):
                run = self.set_token(io.StringIO(token))

                self.assertEqual(run.status, 0, run.stderr)
                self.assert_kept(token)
                self.assert_created_private()


class InterruptedWriteTest(TokenHomeTest):
    """A write that fails before its rename leaves the old token in place,
    with its mode, and takes its own temporary file with it, so nothing
    half-written is left beside the token.
    """

    def test_the_old_token_survives(self) -> None:
        self.keep_old_token()

        with patch.object(os, "replace", side_effect=OSError("disk full")):
            run = self.set_token(io.StringIO(_TOKEN))

        self.assertEqual(run, TokenRun(1, "", f"{_REFUSED}disk full\n", [_PROVED]))
        self.assertEqual(self.path.read_text(), f"{OLD_TOKEN}\n")
        self.assertEqual(self.path.stat().st_mode & LOOSE_FILE, LOOSE_FILE)
        self.assertEqual(tree(self.path.parent), ["token"])


if __name__ == "__main__":
    unittest.main()
