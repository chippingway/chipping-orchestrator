# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The stage roads that reach an agent, and the spent issue they are driven on.

The table is the point: a road added to the tree and not to it is a road
nothing here holds to the ledger, so the list beside the handlers is what a
reader checks the coverage against.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from types import MappingProxyType

from orchestrator.workflow.engine import (
    content_hash as _content_hash,
    run_ledger_values as _run_ledger_values,
)
from orchestrator.workflow.stages.decomposition import run as _decomposing
from orchestrator.workflow.stages.discussion import handler as _discussion
from orchestrator.workflow.stages.implementing import handler as _implementing
from orchestrator.workflow.stages.question import handler as _question
from orchestrator.workflow.stages.validating import handler as _validating
from tests.support.fakes import FakeGitHubClient, make_issue
from tests.workflow.fixtures import (
    LABEL_DECOMPOSING,
    LABEL_DISCUSSION,
    LABEL_IMPLEMENTING,
    LABEL_QUESTION,
    LABEL_VALIDATING,
    _open_pr_for,
)

RUN_AGENT = "run_agent"

# A ceiling the issue records for itself, already spent to the last run. The
# issue's own allowance rather than the setting, so a case is not deciding
# anything about a deployment it does not configure.
ALLOWANCE = 4

_DECOMPOSER_ISSUE_NUMBER = 1560

_REVIEWER_ISSUE_NUMBER = 1561

_REVIEW_PR_NUMBER = 21

_QUESTION_ISSUE_NUMBER = 1562

_DISCUSSION_ISSUE_NUMBER = 1563

_DEVELOPER_ISSUE_NUMBER = 1564

_DIRTY_FILES = "dirty_files"

# A tree with something in it nobody on this tick put there, and a head one of
# the two readings a round is measured between could not resolve. Each is a
# reading some road classifies a finished run by, and neither is about a run
# that never started.
_LEFTOVER_TREE = MappingProxyType({_DIRTY_FILES: ("notes.md",)})

_UNREADABLE_HEAD = MappingProxyType(
    {"head_shas": ("sha-before-the-round", "")},
)


@dataclass(frozen=True)
class SpawningRoad:
    """One handler that reaches an agent, and the issue that gets it there.

    `unclean` is the world the road would misread a refusal in -- the tree
    reading, or the head reading, its own disposition parks on.
    """

    role: str
    number: int
    label: str
    run_stage: Callable
    seed: dict = field(default_factory=dict)
    unclean: dict = field(default_factory=dict)


ROADS = (
    SpawningRoad(
        role="decomposer",
        number=_DECOMPOSER_ISSUE_NUMBER,
        label=LABEL_DECOMPOSING,
        run_stage=_decomposing._handle_decomposing,
        unclean=_LEFTOVER_TREE,
    ),
    SpawningRoad(
        role="reviewer",
        number=_REVIEWER_ISSUE_NUMBER,
        label=LABEL_VALIDATING,
        run_stage=_validating._handle_validating,
        seed={
            "pr_number": _REVIEW_PR_NUMBER,
            "branch": f"orchestrator/issue-{_REVIEWER_ISSUE_NUMBER}",
            "review_round": 0,
        },
        unclean=_LEFTOVER_TREE,
    ),
    SpawningRoad(
        role="question",
        number=_QUESTION_ISSUE_NUMBER,
        label=LABEL_QUESTION,
        run_stage=_question._handle_question,
        unclean=_LEFTOVER_TREE,
    ),
    SpawningRoad(
        role="discussion",
        number=_DISCUSSION_ISSUE_NUMBER,
        label=LABEL_DISCUSSION,
        run_stage=_discussion._handle_discussion,
        unclean=_UNREADABLE_HEAD,
    ),
    SpawningRoad(
        role="developer",
        number=_DEVELOPER_ISSUE_NUMBER,
        label=LABEL_IMPLEMENTING,
        run_stage=_implementing._handle_implementing,
        unclean=_LEFTOVER_TREE,
    ),
)


def spent_issue(road: SpawningRoad):
    """One issue on `road`'s label with its whole lifetime already spent."""
    gh = FakeGitHubClient()
    issue = make_issue(road.number, label=road.label, body="Where does X live?")
    gh.add_issue(issue)
    gh.seed_state(
        road.number,
        **{
            _run_ledger_values.AGENT_RUN_ALLOWANCE: ALLOWANCE,
            _run_ledger_values.AGENT_RUNS_USED: ALLOWANCE,
            # Seeded so a first-encounter drift baseline write is not what a
            # case about the spawn ends up measuring.
            "user_content_hash": _content_hash._compute_user_content_hash(issue, set()),
            **road.seed,
        },
    )
    # The pull request a seeded number names, since a road that reads it --
    # the reviewer's subject names its head -- would otherwise hold on a read
    # nobody could take rather than reach the charge this table is about.
    pr_number = road.seed.get("pr_number")
    if pr_number is not None:
        _open_pr_for(gh, issue_number=road.number, pr_number=pr_number)
    return gh, issue
