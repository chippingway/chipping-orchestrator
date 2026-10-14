# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A repository's GitHub token: read without an argument, proved, and kept private.

``set-token OWNER/NAME`` keeps the token a repository is reached with in
``token_file``, ``~/.config/<owner>/<name>/token``: the file the configuration
resolves that repository's token from when neither an exported
``GITHUB_TOKEN`` nor ``ORCHESTRATOR_TOKEN_FILE`` stands in front of it. The
token is read from standard input and never from the command line, whose
arguments end up in shell history and the process list: at a prompt that does
not echo it on a terminal -- ``token_prompt`` refuses rather than read one
that would -- or to the end of whatever a script pipes or redirects in. A
repository the command refuses is not quoted back either, since what stands
in its place may be the token.

Each step is callable alone, because onboarding asks for a token itself,
proves it while it is held only in memory, and writes nothing until the
operator confirms:

- ``validate_token`` holds an answer to the one shape GitHub issues tokens in,
  and refuses without ever quoting it, since the answer is a secret;
- ``token_probe.reach_repository`` proves it reads the repository;
- ``save_token`` writes it, or replaces the token already there.

``set_token`` runs them in that order, so a failed read, a refused token, or a
GitHub that does not answer leaves an existing token exactly as it was. The
write itself goes through ``private_files``, whole and renamed over the old
file, so an interrupted one leaves it too. ``.env`` is never touched: the
configuration refuses a token there.

Nothing here imports ``orchestrator.config``, or the GitHub client that reads
it: a first setup stores its token on a host where importing either would
exit.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import TextIO

from orchestrator.service.private_files import private_directory, write_private
from orchestrator.service.token_probe import ProbeError, reach_repository
from orchestrator.service.token_prompt import ask_hidden
from orchestrator.service.validation import FieldError, validate_repository

_COMMAND = "chipping-orchestrator set-token"

_NOT_A_REPOSITORY = (
    "the repository given is not written owner/name, and is not printed back "
    "in case it is the token; give a GitHub owner and repository name joined "
    "by one '/', such as acme/api, and the token on standard input"
)

# Owner-only, as the directory holding a token has to be to keep it from
# every other account on the host: `private_files` keeps a directory already
# there as it is, so the token's own is made so here.
_PRIVATE_DIRECTORY = 0o700

# One run of visible ASCII, the alphabet every GitHub token is written in. A
# blank or a line break inside means more than a token was given, and could
# not travel in the header the token is sent in.
_TOKEN = re.compile(r"[!-~]+")

# 128 + SIGINT: the status a shell reports for a command Ctrl+C stopped.
_INTERRUPTED = 130


def token_file(repository: str) -> Path:
    """Where the token for ``repository``, an ``owner/name``, is kept."""
    return Path.home() / ".config" / repository / "token"


def validate_token(raw: str) -> str:
    """The token ``raw`` holds, without the blanks around it."""
    token = raw.strip()
    if not token:
        raise FieldError("no token was given; give the repository's GitHub token")
    if _TOKEN.fullmatch(token) is None:
        raise FieldError(
            "the token holds a blank, a line break, or a character outside "
            "visible ASCII; give the token alone, on one line",
        )
    return token


def save_token(repository: str, token: str) -> Path:
    """Write ``token`` as ``repository``'s token file, and return its path.

    The file is mode 0600 and replaces any token there in one rename, so a
    reader finds the old token or the new one and never part of either. Its
    directory is made 0700 even where a looser one already stood, and each
    directory missing above it is created 0700, whatever the umask.
    """
    path = token_file(repository)
    private_directory(path.parent)
    path.parent.chmod(_PRIVATE_DIRECTORY)
    write_private(path, f"{token}\n", replace=True)
    return path


def set_token(repository: str, stdin: TextIO) -> int:
    """Run ``set-token``: prove the token ``stdin`` carries, then keep it.

    Answers 0 once the file is written, and 1 with the reason on standard
    error when any step refuses, with nothing written.
    """
    try:
        slug, path = _prove_and_save(repository, stdin)
    except KeyboardInterrupt:
        sys.stderr.write(f"\n{_COMMAND}: interrupted; nothing was written\n")
        return _INTERRUPTED
    except (FieldError, ProbeError, OSError) as refused:
        sys.stderr.write(f"{_COMMAND}: {refused}\n")
        return 1
    sys.stdout.write(f"The token reaches {slug}; saved it to {path}\n")
    return 0


def _prove_and_save(repository: str, stdin: TextIO) -> tuple[str, Path]:
    """The repository ``set-token`` names, and the token file it wrote for it.

    The repository is checked before anything is read, so a mistyped one
    costs no token, and the token is proved before anything is written.
    """
    try:
        slug = validate_repository(repository)
    except FieldError:
        # Neither the message nor the chain quotes the answer, as the
        # validator's own refusal does: it may be the token.
        raise FieldError(_NOT_A_REPOSITORY) from None
    token = _read_token(slug, stdin)
    reach_repository(token, slug)
    return slug, save_token(slug, token)


def _read_token(repository: str, stdin: TextIO) -> str:
    """The token for ``repository``, typed hidden on a terminal or read whole."""
    if stdin.isatty():
        try:
            typed = ask_hidden(f"GitHub token for {repository} (input hidden): ")
        except EOFError:
            typed = ""
        return validate_token(typed)
    # The decoding error is not chained: it quotes the bytes it stopped at,
    # which are part of the token.
    try:
        return validate_token(stdin.read())
    except UnicodeDecodeError:
        raise FieldError("standard input is not text; give the token alone, on one line") from None
