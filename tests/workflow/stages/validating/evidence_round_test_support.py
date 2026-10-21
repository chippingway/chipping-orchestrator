# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The issue of `review_verdict_test_support`, ticked whole by the dispatcher.

A tick is the dispatcher's evidence reconciliation, then the validating
handler where that lets it on (`LiveRoundWorld.tick`), so a verdict comes back
through the live reviewer round rather than being handed to the disposition by
the case. The reviewer runs a case answers with report their usage the way a
real run does, on its output, so a fold reads back as the round makes it. What
a case reads back -- the order of the comments on the pull request's thread and
the commands each artifact there carries -- is spelled here too, beside the
labels the issue moved through and what it has spent, which the shared review
world reads (`tests/workflow/review_world.py`).
"""
from __future__ import annotations

from functools import partial
from unittest.mock import MagicMock

from orchestrator.workflow.stages.validating import handler as _validating
from tests.workflow import review_world as _review_world
from tests.workflow.repo_values import _TEST_SPEC
from tests.workflow.stages.validating import review_verdict_readings as _read, review_verdict_test_support as _world

HEAD = _world.HEAD

RUN_AGENT = _world.RUN_AGENT

# What a verification artifact's comment opens with on the pull request.
ARTIFACT_HEADING = "Workflow verification artifact"


def declared_reuse(revision: str) -> str:
    """An approval reusing the evidence at `revision` instead of running anything."""
    return f"LGTM\n\nVERIFICATION: REUSED sha256:{revision}\n\nVERDICT: APPROVED"


# A reviewer run returning a message, whose output reports the world's reviewer tokens.
reviewer = _review_world.reviewer


def reviewing_while(case, moves, message: str) -> MagicMock:
    """A reviewer run returning `message`, during which `moves` does another road's work on `case`."""
    return MagicMock(side_effect=partial(_reviews_after, case, moves, message))


def prompt(ran, call: int = 0) -> str:
    """The prompt one agent run of a tick was handed: its reviewer's, unless `call` says which."""
    runs = ran[RUN_AGENT].call_args_list
    return runs[call].args[1]


def _reviews_after(case, moves, message: str, *_asked, **_options):
    moves(case)
    return reviewer(message)


def _commands_of(artifact) -> tuple:
    return tuple((ran.command, ran.exit_status) for ran in artifact.commands)


class LiveRoundWorld(_world.ReviewVerdictWorld):
    """An issue on `workflow:validating` about to spawn its reviewer, ticked whole."""

    def tick(self, *agents, **run_options) -> dict:
        """One dispatcher tick on the issue, whose agent runs answer `agents` in order."""
        run_options.setdefault(RUN_AGENT, list(agents))
        run_options.setdefault("head_shas", (HEAD,))
        return self._run(self._dispatches, **run_options)

    def posted_before(self, first: str, second: str) -> bool:
        """Whether the pull request's first comment saying `first` precedes its first saying `second`."""
        bodies = [said.body for said in self.pull_request.issue_comments]
        saying = [[phrase in body for body in bodies] for phrase in (first, second)]
        return saying[0].index(True) < saying[1].index(True)

    def published(self) -> tuple:
        """The commands, with their exit statuses, of each artifact on the pull request, oldest first."""
        return tuple(_commands_of(found) for found in _read.artifacts(self))

    def _dispatches(self) -> None:
        if not _world.reconciles(self):
            _validating._handle_validating(self.github, _TEST_SPEC, self.issue)
