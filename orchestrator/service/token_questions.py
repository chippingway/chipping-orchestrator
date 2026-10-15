# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A repository's token in an onboarding: kept where it is stored, otherwise asked for and proved in memory.

The service reads a repository's token from ``tokens.token_file``, so where
that file exists already the question is not asked: the file is kept as it
is, and the token is read off it only to ask GitHub whose it is. Otherwise
the token is typed at the hidden prompt ``token_prompt`` holds, and an
exported ``GITHUB_TOKEN`` is offered as what an empty answer takes, without
showing it. The answer is held to ``tokens.validate_token`` and proved with
the read-only call ``set-token`` makes, and a refusal of either is printed
beneath the question, which is asked again. Nothing is written here: the token
is handed back in memory, for the onboarding to save once it is confirmed.

Whose token it is -- the login an onboarding offers as the authors' default
-- is asked of GitHub with one more read-only call, and a token GitHub does
not say that of answers with no login rather than a refusal: proving it reads
the repository is what the question asks.
"""
from __future__ import annotations

import os
import sys
from functools import partial
from pathlib import Path

from orchestrator.service.questions import question_text, retried
from orchestrator.service.token_probe import ProbeError, owner_login, reach_repository
from orchestrator.service.token_prompt import ask_hidden
from orchestrator.service.tokens import token_file, validate_token
from orchestrator.service.validation import FieldError

# Where a token is offered from, named in place of the token itself.
_EXPORTED = "GITHUB_TOKEN"
_KEPT = "{0}: keeping {1}{2}\n"
_REACHED = "      the token reaches {0}{1}\n"

# The token to save, none where the stored one is kept, and whose it is.
_Answered = tuple[str | None, str | None]


def ask_token(question: str, repository: str, exported: str | None) -> _Answered:
    """The token ``repository`` is to be given, and the login it belongs to.

    The token is ``None`` where the repository's token file is kept, and
    otherwise the one typed after ``question`` -- or ``exported`` for an
    empty answer -- once it reads the repository.
    """
    stored = token_file(repository)
    if os.path.lexists(stored):
        owner = _stored_owner(stored)
        sys.stdout.write(_KEPT.format(question, stored, _owned(owner)))
        return None, owner
    offered = f"exported {_EXPORTED}" if exported else None
    prompt = question_text(f"{question} (input hidden)", offered)
    token = retried(partial(_proved, prompt, repository, exported))
    owner = _owner(token)
    sys.stdout.write(_REACHED.format(repository, _owned(owner)))
    return token, owner


def _proved(prompt: str, repository: str, exported: str | None) -> str:
    """The token typed after ``prompt``, or ``exported`` for none, once GitHub lets it read ``repository``."""
    token = validate_token(ask_hidden(prompt) or exported or "")
    try:
        reach_repository(token, repository)
    except ProbeError as refused:
        # The probe's diagnostic masks the token and chains nothing behind it.
        raise FieldError(str(refused)) from None
    return token


def _owner(token: str) -> str | None:
    """The login of the account ``token`` belongs to, where GitHub says."""
    try:
        return owner_login(token)
    except ProbeError:
        return None


def _stored_owner(stored: Path) -> str | None:
    """The login the token kept in ``stored`` belongs to, where it reads and GitHub says."""
    try:
        token = validate_token(stored.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return _owner(token)


def _owned(owner: str | None) -> str:
    """Whose token it is, as the line reporting it ends."""
    return f" (owner: {owner})" if owner else ""
