# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Every question an onboarding asks, in order, and the setup its answers make.

``ask_setup`` asks, at the terminal it is handed:

- the first repository's questions, from ``repository_questions``: its clone,
  its name, its branch, and its token;
- the logins whose issues the orchestrator acts on, offering the login of the
  account the first repository's token belongs to, and the logins to mention
  when a human is needed, offering that answer -- each held to
  ``validate_logins``;
- the agents, from ``agent_questions``, each looked for on the ``PATH`` the
  service will run with: the absolute entries of the shell's, as
  ``environment`` captures them;
- another repository, as often as that is answered yes: the same four
  questions, the clone offered no default and a repository already given
  refused;
- and last, whether to write the files the answers make, each named: the
  token file of each repository given a token, and the installed ``.env``.

It writes nothing. A no to the last question answers ``None``, and Ctrl+C or
the end of the input at any question raises what the question raised.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import TextIO

from orchestrator.service import paths
from orchestrator.service.agent_questions import ask_agents
from orchestrator.service.environment import captured_path
from orchestrator.service.questions import ask_until, confirm
from orchestrator.service.repository_questions import RepositoryAnswers, ask_repository
from orchestrator.service.tokens import token_file
from orchestrator.service.validation import validate_logins


@dataclass(frozen=True)
class SetupAnswers:
    """Everything an onboarding was answered with, each answer as accepted.

    The logins are joined the way ``configure`` is told them, the agents
    keyed by the ``configure`` answer each sets, and ``search_path`` is the
    ``PATH`` they were found on.
    """

    repositories: tuple[RepositoryAnswers, ...]
    authors: str
    notify: str
    agents: Mapping[str, str]
    search_path: str


def ask_setup(shell: Mapping[str, str], stdin: TextIO) -> SetupAnswers | None:
    """The setup asked for at ``stdin``, or ``None`` where writing it is declined."""
    first = ask_repository(stdin, shell, ())
    authors = ask_until(stdin, "[5/6] GitHub logins whose issues the orchestrator may act on", _logins, first.owner)
    search_path = captured_path(shell.get("PATH", ""))
    setup = SetupAnswers(
        (first,),
        authors,
        ask_until(stdin, "[6/6] GitHub logins to mention when a human is needed", _logins, authors),
        ask_agents(stdin, search_path),
        search_path,
    )
    while confirm(stdin, "Add another repository?", default=False):
        setup = _with_another(setup, shell, stdin)
    return setup if confirm(stdin, f"\nWrite {_listed(setup)}?", default=True) else None


def _with_another(setup: SetupAnswers, shell: Mapping[str, str], stdin: TextIO) -> SetupAnswers:
    """``setup`` with one more repository asked for after its own."""
    chosen = tuple(answered.repository for answered in setup.repositories)
    return replace(setup, repositories=(*setup.repositories, ask_repository(stdin, shell, chosen)))


def _logins(answer: str) -> str:
    """The logins ``answer`` lists, joined as ``configure`` is told them."""
    return ",".join(validate_logins(answer))


def _listed(setup: SetupAnswers) -> str:
    """Each file writing ``setup`` writes, named as a sentence names them."""
    named = [
        str(token_file(answered.repository))
        for answered in setup.repositories
        if answered.token is not None
    ]
    named.append(str(paths.settings_file()))
    if len(named) < 3:
        return " and ".join(named)
    *before, last = named
    listed = ", ".join(before)
    return f"{listed}, and {last}"
