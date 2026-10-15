# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The agent each role runs, asked in an onboarding: the defaults kept, or each role asked in turn.

The three roles' defaults are the ones ``configure`` writes when it is told
none, shown with whether each is found on the ``PATH`` the service will run
with. One answer keeps them all -- the default answer where every one is
found -- and keeping one that is not found is refused with the message
``validation.validate_agent`` gives it, so a missing agent is reported before
anything is written. Answered no, each role is asked for in turn, its default
offered and its answer held to that same validator.

The answer is keyed by the ``configure`` option each role is set with, as
``configure.ConfigureAnswers`` names it.
"""
from __future__ import annotations

import sys
from collections.abc import Mapping
from functools import partial
from typing import TextIO

from orchestrator.service.configure import DEFAULT_DECOMPOSE_AGENT, DEFAULT_DEV_AGENT, DEFAULT_REVIEW_AGENT
from orchestrator.service.questions import ask_until, confirm, retried
from orchestrator.service.validation import AGENTS, FieldError, validate_agent

# Each role: what it does, the answer it sets, and the agent it runs by default.
_ROLES = (
    ("implement", "dev_agent", DEFAULT_DEV_AGENT),
    ("review", "review_agent", DEFAULT_REVIEW_AGENT),
    ("decompose", "decompose_agent", DEFAULT_DECOMPOSE_AGENT),
)
_CHOICES = "/".join(AGENTS)


def ask_agents(stdin: TextIO, search_path: str) -> Mapping[str, str]:
    """The agent each role runs, each found on ``search_path``, keyed by its ``configure`` answer."""
    sys.stdout.write(f"\nAgents: {_listed(search_path)}\n")
    if retried(partial(_kept, stdin, search_path)):
        return {answer: agent for _, answer, agent in _ROLES}
    return {
        answer: ask_until(
            stdin,
            f"Agent that {role}s ({_CHOICES})",
            partial(validate_agent, search_path=search_path),
            agent,
        )
        for role, answer, agent in _ROLES
    }


def _kept(stdin: TextIO, search_path: str) -> bool:
    """Whether the defaults are kept, refused where one kept is not found on ``search_path``.

    Keeping them is the default answer only where every one is found.
    """
    found = all(_found(agent, search_path) for _, _, agent in _ROLES)
    keep = confirm(stdin, "Keep these agents?", default=found)
    if keep:
        for _, _, agent in _ROLES:
            validate_agent(agent, search_path)
    return keep


def _found(agent: str, search_path: str) -> bool:
    """Whether ``agent`` is one the validator accepts on ``search_path``."""
    try:
        validate_agent(agent, search_path)
    except FieldError:
        return False
    return True


def _listed(search_path: str) -> str:
    """Each role's default agent, with whether it is found on ``search_path``."""
    shown = []
    for role, _, agent in _ROLES:
        found = "found" if _found(agent, search_path) else "not found on PATH"
        shown.append(f"{role}={agent} ({found})")
    return "  ".join(shown)
