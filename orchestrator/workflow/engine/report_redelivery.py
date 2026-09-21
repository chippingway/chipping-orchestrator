# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Whether a run that moved no head is answering a report this issue owes.

Every stage reads a head that did not move as a session that came back with a
question, and for every ordinary run that is right. An issue holding a report it
could not deliver is the exception: it was never waiting for code. The commits
are already on the branch with nothing published from them or nothing bound to
them, and what its park asked for was a report it could record -- so the reply
that brings one has work to publish rather than a question to park on.

It is asked HERE rather than at either caller because both roads a reply can
take ask the same question -- the resume a park earns, and the drift resume an
edit earns -- and a rule written twice is one that comes to differ. It sits
apart from the recording beside it for the same reason the recording sits apart
from the publication: this is a reading about a LATER run and the branch it ran
over, while `report_delivery` is what one finished run's own report becomes.
"""
from __future__ import annotations

from pathlib import Path

from orchestrator.agents.models import AgentResult
from orchestrator.config import models as _config_models
from orchestrator.git.worktrees import creation as _worktree_creation
from orchestrator.github import pinned_state as _pinned_state
from orchestrator.workflow.engine import (
    report_delivery as _delivery,
    report_outcome_models as _outcome_models,
    report_outcomes as _outcomes,
)


def redelivers_an_owed_report(
    spec: _config_models.RepoSpec,
    state: _pinned_state.PinnedState,
    agent_result: AgentResult,
    worktree: Path,
) -> bool:
    """Whether this run answers a report this issue owes rather than a question.

    The one road on which a run that committed nothing still has work to
    publish.

    Three readings, asked in the order that spends least. The DEBT says what
    the issue is waiting on, so a run that reports on an issue owing nothing
    is the ordinary no-commit reply its stage already knows how to read -- and
    asking it first is what keeps every other tick from paying for the two
    below. The OUTCOME says the developer considers the work finished, so a
    question, a disagreement, or a run that fell short is still a question:
    what supersedes an undeliverable report is another report and nothing
    else. And the BRANCH has to carry something, because what this licenses is
    a publication: a checkout with nothing ahead of base would push an empty
    branch and open a pull request with no diff in it.
    """
    if not _delivery.owes_a_report(state):
        return False
    if isinstance(
        _outcomes._report_outcome_of_run(agent_result),
        _outcome_models._ReportRefusal,
    ):
        return False
    return _worktree_creation._has_new_commits(spec, worktree)
