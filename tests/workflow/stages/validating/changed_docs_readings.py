# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What the changed-docs journey's world answers with, and the windows a final docs pass's completion opens.

The verify runner answers a docs pass with a run of the configured suite on
exactly the docs commit (`docs_run`), or a failing one; and the approval's
squash, with `SQUASH_ON_APPROVAL` off, rewrites nothing and publishes the
approved head as it is (`leaves_the_branch`).

The completion is one write behind the pass's notice, and one relabel behind
that write. So past the push there are three places for it to stop short: the
process ending on the write with nothing of it landed, which leaves the
receipt the size gate put down; the write landing and its answer lost; and the
write confirmed with the relabel behind it failing -- the last two leave the
completion itself, with the issue still on `workflow:documenting`.

A process ending is spelled as a raise the case swallows, so what a test reads
afterwards is exactly the durable state a crash would have left. The
completion is told from every write a tick makes before it by what it carries:
the final-documentation completion record.
"""
from __future__ import annotations

import contextlib
from functools import partial
from unittest.mock import patch

from orchestrator import config
from orchestrator.git.publication.models import _SquashOutcome
from orchestrator.git.verification import models as _verify_models
from orchestrator.workflow.engine import final_docs_records as _final_docs
from orchestrator.workflow.state import WorkflowLabel
from tests.workflow import review_world as _world
from tests.workflow.fixtures import MEASURED_CANDIDATE_SHA

# The docs commit a docs pass publishes, which the size gate proves the
# checkout to.
DOCS_HEAD = MEASURED_CANDIDATE_SHA


# The configured suite's failure on the docs commit.
_FAILED_EXIT = 1


def docs_run(
    commit: str = DOCS_HEAD, exit_code: int = 0, output: str = _world.SUITE_OUTPUT,
) -> _verify_models.VerifyResult:
    """The configured suite run on `commit` under the configuration read now, exiting `exit_code`, printing `output`."""
    configured = tuple(config.VERIFY_COMMANDS)
    status = _verify_models.VERIFY_STATUS_OK if exit_code == 0 else _verify_models.VERIFY_STATUS_FAILED
    ran = _verify_models.VerifyCommandOutcome(
        command=_world.SUITE,
        status=status,
        exit_code=exit_code,
        output=output,
        head_before=commit,
        head_after=commit,
        tree_before=_world.TREE,
        tree_after=_world.TREE,
    )
    return _verify_models.VerifyResult(
        status=status,
        commit=commit,
        tree_identity=_world.TREE,
        configured_commands=configured,
        attempted_commands=(ran,),
        timeout=config.VERIFY_TIMEOUT,
        context_revision=_verify_models._context_revision(configured, config.VERIFY_TIMEOUT),
    )


failed_docs_run = partial(docs_run, exit_code=_FAILED_EXIT)

# A passing run whose output closes a code fence, which no verification
# artifact can quote, so it binds no evidence.
unrecordable_docs_run = partial(docs_run, output=f"{_world.SUITE_OUTPUT}\n```\n")


def leaves_the_branch(_gate, _branch, _pr_number) -> _SquashOutcome:
    """The approval's squash with `SQUASH_ON_APPROVAL` off: nothing rewritten, the approved head published as it is."""
    return _SquashOutcome(success=True)


class _Crashed(RuntimeError):
    """The process ending where a case says it ends."""


class _DiesOnTheCompletion:
    """The pinned edits a tick makes, ending on the one landing the completion -- or landing it and losing the answer.

    The completion is the first edit carrying a final-documentation
    completion. `lands` is the write going out and its answer lost: the edit
    is made and the process ends before anything is told of it.
    """

    def __init__(self, edits, *, lands: bool) -> None:
        self._edits = edits
        self._lands = lands

    def __call__(self, issue, state, **options):
        if state.get(_final_docs.FINAL_DOCS) is None:
            return self._edits(issue, state, **options)
        if self._lands:
            self._edits(issue, state, **options)
        raise _Crashed


class _DiesOnTheRelabel:
    """The relabels a tick makes, ending on the one moving the issue into review."""

    def __init__(self, relabels) -> None:
        self._relabels = relabels

    def __call__(self, issue, label):
        if label == WorkflowLabel.IN_REVIEW:
            raise _Crashed
        return self._relabels(issue, label)


@contextlib.contextmanager
def _on_the_completion(case, *, lands: bool):
    """The process ending on the completion's write, which lands first only where `lands`."""
    with patch.object(
        case.github, "edit_pinned_state", _DiesOnTheCompletion(case.github.edit_pinned_state, lands=lands),
    ), contextlib.suppress(_Crashed):
        yield


# The process ending on the completion's write with nothing of it landed, which
# leaves the receipt the gate put down; and the write landing with the process
# ending before its answer, which leaves the completion with no relabel.
dying_on_the_completion = partial(_on_the_completion, lands=False)

losing_the_completion = partial(_on_the_completion, lands=True)


@contextlib.contextmanager
def dying_on_the_relabel(case):
    """The completion's write confirmed and the process ending on the relabel behind it."""
    with patch.object(
        case.github, "set_workflow_label", _DiesOnTheRelabel(case.github.set_workflow_label),
    ), contextlib.suppress(_Crashed):
        yield
