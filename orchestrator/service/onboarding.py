# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Onboarding: the setup ``init`` asks for at a terminal, where no ``.env`` exists yet.

``init`` hands ``onboard`` its shell, its terminal, and the package root it
checked once it finds no installed ``.env`` and standard input is a terminal.
Onboarding is a thin layer over the setup commands: ``setup_questions`` asks
one question per setting, holding each answer to the validator those commands
hold the same field to, and ``onboard`` hands the answers to their cores in
process -- ``tokens.save_token`` for each token it was given, ``configure``
for the first repository, and ``add_repo`` for each further one -- so the
files it writes are the ones the scripted setup writes for the same answers.

Nothing is written until the last question, which names each file the answers
write, is answered yes. Ctrl+C or the end of the input at any question before
it, a terminal that cannot be read or cannot hide a token, and a no to it
leave the home exactly as they found it -- no ``.env``, token, unit, or
directory -- and refuse ``init`` saying so. A write that fails after that
refuses it too, keeping what the lines above it report written.
"""
from __future__ import annotations

import sys
from collections.abc import Mapping
from pathlib import Path
from typing import TextIO

from orchestrator.service import paths
from orchestrator.service.add_repo import AddRepoAnswers, AddRepoRefusal, add_repo
from orchestrator.service.configure import ConfigureAnswers, ConfigureRefusal, configure
from orchestrator.service.installation import InitRefusal
from orchestrator.service.setup_questions import SetupAnswers, ask_setup
from orchestrator.service.tokens import save_token
from orchestrator.service.validation import FieldError

_WELCOME = (
    "No configuration at {0}. Let's create it.\n"
    "Nothing is written until the last question; Ctrl+C leaves everything as it is.\n\n"
)
_ABANDONED = "onboarding stopped before its last question, so nothing was written; run init again to start over"
_UNREAD = "{0}; onboarding wrote nothing"
_DECLINED = (
    "nothing was written, as answered; run init again to start over, or write the "
    "setup without prompts with chipping-orchestrator set-token OWNER/NAME and "
    "chipping-orchestrator configure --clone PATH --authors LOGINS"
)
_STOPPED = (
    "{0}; onboarding stopped there, keeping what it wrote above -- finish the "
    "setup with set-token, configure, and add-repo, then run init again"
)
_SAVED = "Saved the token for {0} to {1}\n"

# What a write can fail with once the answers are confirmed: a token file that
# cannot be written, and each core's own refusal of a clone or a file that
# changed after it was asked about.
_WRITE_FAILURES = (OSError, ConfigureRefusal, AddRepoRefusal, FieldError)


def onboard(shell: Mapping[str, str], stdin: TextIO, package_root: Path) -> None:
    """Ask for the setup at ``stdin`` and write it once confirmed, or raise ``InitRefusal``.

    ``shell`` supplies the ``PATH`` the agents are looked for on and an
    exported ``GITHUB_TOKEN`` to offer; ``package_root`` is the one ``init``
    checked, which the setup cores refuse a source checkout at too.
    """
    sys.stdout.write(_WELCOME.format(paths.settings_file()))
    setup = _asked(shell, stdin)
    try:
        _write(setup, package_root)
    except _WRITE_FAILURES as failed:
        raise InitRefusal(_STOPPED.format(failed)) from failed


def _asked(shell: Mapping[str, str], stdin: TextIO) -> SetupAnswers:
    """The setup confirmed at ``stdin``, or the refusal of one stopped or declined there."""
    try:
        setup = ask_setup(shell, stdin)
    except (KeyboardInterrupt, EOFError):
        # The question stopped at is left without the line end an answer gives it.
        sys.stdout.write("\n")
        raise InitRefusal(_ABANDONED) from None
    except OSError as unread:
        raise InitRefusal(_UNREAD.format(unread)) from None
    if setup is None:
        raise InitRefusal(_DECLINED)
    return setup


def _write(setup: SetupAnswers, package_root: Path) -> None:
    """Save each token given, then write ``.env`` for the first repository and add each further one."""
    _save_tokens(setup)
    first, *further = setup.repositories
    settings_file = configure(
        ConfigureAnswers(
            clone=str(first.clone),
            authors=setup.authors,
            repo=first.repository,
            base_branch=first.base_branch,
            notify=setup.notify,
            **setup.agents,
        ),
        search_path=setup.search_path,
        package_root=package_root,
    )
    sys.stdout.write(f"Wrote {settings_file}\n")
    for answered in further:
        entry = add_repo(
            AddRepoAnswers(str(answered.clone), answered.repository, answered.base_branch),
            package_root=package_root,
        )
        sys.stdout.write(f"Added {entry.render()} to REPOS in {settings_file}\n")


def _save_tokens(setup: SetupAnswers) -> None:
    """Save each token ``setup`` was given, as ``set-token`` saves one."""
    for answered in setup.repositories:
        if answered.token is not None:
            saved = save_token(answered.repository, answered.token)
            sys.stdout.write(_SAVED.format(answered.repository, saved))
