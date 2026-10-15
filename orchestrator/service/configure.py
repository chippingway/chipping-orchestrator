# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""``configure``: an installed package's ``.env``, written from answers alone.

``configure`` writes ``~/.config/chipping-orchestrator/.env`` from the basic
template this version ships, the file the installed package loads its settings
from. Six settings are set on the template's own lines for them -- ``REPOS``,
``HITL_HANDLE``, ``ALLOWED_ISSUE_AUTHORS``, ``DEV_AGENT``, ``REVIEW_AGENT``,
and ``DECOMPOSE_AGENT`` -- so every comment explaining them is kept, and
``LOG_DIR`` is appended at the end, where the template's comments say it is,
naming the absolute log directory ``paths`` gives an installed package.
Nothing written comes from a token, and the template holds none.

Only the clone and the authors have to be given. The repository, its remote,
and the base branch are read off the clone's GitHub remote by
``clone_defaults``, the people to mention default to the authors, and the
agents to the template's own routing. The authors have no default: they decide
whose issues and comments the orchestrator trusts.

Everything is checked before anything is written, in this order: the package
must not run from a source checkout, which reads a ``.env`` of its own; no
``.env`` may be in the way, since this one is never overwritten; each answer
passes its field's validator, the refusal naming the option it was given as;
and only then is the clone read for the rest of its entry, whose clone and
branch fields are refused under their options too where the entry cannot
carry them -- the entry ``entry_answers`` makes, as it does for ``add-repo``.
The file is then written whole with mode 0600, in a directory created with
mode 0700 as is each parent missing above it.

The core is ``configure``, which takes the answers as typed -- an option's
value or an answer collected at a prompt -- so a command line and an onboarding
calling it in process write the same file. Nothing here imports
``orchestrator.config``: the file is written on a host with no configuration,
where importing it would exit.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from orchestrator.service import paths
from orchestrator.service.dotenv_text import assign, assignment
from orchestrator.service.entry_answers import answered_entry, checked
from orchestrator.service.private_files import private_directory, write_private
from orchestrator.service.templates import BASIC_TEMPLATE, template_text
from orchestrator.service.validation import validate_agent, validate_logins

COMMAND = "configure"

# The routing the basic template ships with, one agent per role.
DEFAULT_DEV_AGENT = "claude"
DEFAULT_REVIEW_AGENT = "codex"
DEFAULT_DECOMPOSE_AGENT = "claude"

_EXISTING = (
    f"{{0}} already exists, and {COMMAND} never overwrites it; edit that "
    "file, or move it aside to write a new one"
)


@dataclass(frozen=True)
class ConfigureAnswers:
    """What ``configure`` is told, each answer as it was typed.

    The names are the command's options; ``None`` takes that option's
    default.
    """

    clone: str
    authors: str
    repo: str | None = None
    base_branch: str | None = None
    notify: str | None = None
    dev_agent: str = DEFAULT_DEV_AGENT
    review_agent: str = DEFAULT_REVIEW_AGENT
    decompose_agent: str = DEFAULT_DECOMPOSE_AGENT


class ConfigureRefusal(Exception):
    """Why ``configure`` writes nothing, other than a field it refused."""


def _settings_text(answers: ConfigureAnswers, search_path: str) -> str:
    """The basic template with each setting ``configure`` sets set in place.

    Every answer passes its validator before the clone is read for the rest
    of its entry: the entry comes last.
    """
    authors = checked("--authors", validate_logins, answers.authors)
    notify = checked("--notify", validate_logins, answers.notify) or authors
    text = template_text(BASIC_TEMPLATE)
    for key, setting in (
        ("HITL_HANDLE", ",".join(notify)),
        ("ALLOWED_ISSUE_AUTHORS", ",".join(authors)),
        ("DEV_AGENT", checked("--dev-agent", validate_agent, answers.dev_agent, search_path)),
        ("REVIEW_AGENT", checked("--review-agent", validate_agent, answers.review_agent, search_path)),
        ("DECOMPOSE_AGENT", checked("--decompose-agent", validate_agent, answers.decompose_agent, search_path)),
        ("REPOS", answered_entry(answers.clone, answers.repo, answers.base_branch).render()),
    ):
        text = assign(text, key, setting)
    return text


def _write(settings_file: Path, text: str) -> None:
    """Write ``text`` as ``settings_file``, ``LOG_DIR`` appended, never over a file.

    The directory is made private first, with any parent missing above it.
    """
    log_dir = assignment("LOG_DIR", str(paths.log_dir()))
    try:
        private_directory(settings_file.parent)
    except OSError as error:
        raise ConfigureRefusal(f"{settings_file.parent} cannot be created ({error})") from error
    try:
        write_private(settings_file, f"{text}\n{log_dir}\n", replace=False)
    except FileExistsError as raced:
        raise ConfigureRefusal(_EXISTING.format(settings_file)) from raced
    except OSError as error:
        raise ConfigureRefusal(f"{settings_file} cannot be written ({error})") from error


def configure(
    answers: ConfigureAnswers,
    *,
    search_path: str,
    package_root: Path = paths.PACKAGE_ROOT,
) -> Path:
    """Write the installed package's ``.env`` from ``answers``; return its path.

    ``search_path`` is the ``PATH`` each agent has to be found on: the one
    the service will run with, which is not necessarily the caller's own.
    Raises ``ConfigureRefusal`` or ``FieldError``, with the whole diagnostic as
    its text, having written nothing.
    """
    refusal = paths.source_checkout_refusal(COMMAND, package_root)
    if refusal is not None:
        raise ConfigureRefusal(refusal)
    settings_file = paths.settings_file()
    if os.path.lexists(settings_file):
        raise ConfigureRefusal(_EXISTING.format(settings_file))
    _write(settings_file, _settings_text(answers, search_path))
    return settings_file
