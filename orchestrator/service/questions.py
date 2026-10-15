# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Questions asked at a terminal, each until its answer is accepted.

An onboarding asks one question per setting, worded the way ``question_text``
words it: the question, the default in brackets where there is one, and a
colon. An empty answer takes that default. ``ask_until`` hands the answer to
the setting's validator and, where that refuses it with ``FieldError``, prints
the validator's own message indented beneath the question and asks again, so
a prompt shows the words a setup command shows for the same answer, without
the option in front. ``retried`` is that loop for an answer read some other
way, as a token is at a hidden prompt, and ``confirm`` asks a yes-or-no
question, refusing any other answer the same way.

The question is written to standard output, and the answer read as one line
of the terminal the caller hands in. Ctrl+C raises ``KeyboardInterrupt``, as
at any prompt, and the end of the input -- Ctrl+D at an empty line --
``EOFError``, so the caller decides what an abandoned question means. Nothing
here imports from the package but ``validation``, whose refusal it retries.
"""
from __future__ import annotations

import sys
from collections.abc import Callable
from functools import partial
from typing import TextIO

from orchestrator.service.validation import FieldError

# Beneath the question, as far in as the text after its `[1/6] ` number.
_REFUSED = "      {0}\n"
_AGREEING = frozenset(("y", "yes"))
_DECLINING = frozenset(("n", "no"))


def question_text(question: str, default: str | None = None) -> str:
    """``question`` as it is asked: ``default`` in brackets where there is one, then a colon."""
    offered = f" [{default}]" if default else ""
    return f"{question}{offered}: "


def ask(stdin: TextIO, question: str, default: str | None = None) -> str:
    """The line answered to ``question`` at ``stdin``, without its blanks; ``default`` for an empty one."""
    sys.stdout.write(question_text(question, default))
    sys.stdout.flush()
    line = stdin.readline()
    if not line:
        raise EOFError
    return line.strip() or default or ""


def retried[Accepted](attempt: Callable[[], Accepted]) -> Accepted:
    """What ``attempt`` answers once it stops refusing, each refusal's message printed in between."""
    while True:
        try:
            return attempt()
        except FieldError as refused:
            sys.stdout.write(_REFUSED.format(refused))


def ask_until[Accepted](
    stdin: TextIO,
    question: str,
    accept: Callable[[str], Accepted],
    default: str | None = None,
) -> Accepted:
    """What ``accept`` makes of the first answer to ``question`` it does not refuse."""
    return retried(lambda: accept(ask(stdin, question, default)))


def confirm(stdin: TextIO, question: str, *, default: bool) -> bool:
    """Whether ``question`` is answered yes, an empty answer being ``default``."""
    choices = "Y/n" if default else "y/N"
    return ask_until(stdin, f"{question} [{choices}]", partial(_yes, default=default))


def _yes(answer: str, *, default: bool) -> bool:
    """Whether ``answer`` says yes; ``default`` where it says nothing."""
    word = answer.lower()
    if word in _AGREEING:
        return True
    if word in _DECLINING:
        return False
    if word:
        raise FieldError(f"{answer!r} is neither yes nor no; answer y or n")
    return default
