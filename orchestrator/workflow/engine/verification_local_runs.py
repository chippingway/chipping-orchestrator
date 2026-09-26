# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What one local `VERIFY_COMMANDS` run is worth as evidence, bound to its target.

Only a run `VerifyResult.is_reusable` vouches for is evidence: every
configured command ran, in order, exited 0, and was followed by a status read
that PROVED the worktree clean and by readings of the tested commit and tree
unchanged, under the context revision its commands and timeout mint. That is
what lets the transcript stand for the committed tree and nothing else.

A run that failed is not bound, however genuine its failure. The runner reads
the worktree after a zero exit only, so a command that rewrote tracked files
and then exited nonzero leaves no proof the failure was the committed tree's
rather than its own edit's -- and evidence that cannot say which tree it
describes is not evidence. A failure stays actionable where it already is: the
verify gate parks on it with the command and its output. Nor is anything else
bound: an empty configuration ran nothing and is not evidence that anything
passed, and a timeout, a dirty tree, or a moved HEAD or tree cannot say which
tree it tested.

Nothing is counted or inferred: the commands published are exactly the ones
that ran, with the already-redacted, already-bounded output each one earned. A
command the published format refuses -- a transcript carrying the fence that
closes it, say -- binds nothing either, because an artifact that cannot be
posted is not evidence anybody can be shown.
"""
from __future__ import annotations

from orchestrator.git.verification import models as _verify_models
from orchestrator.github import verification_evidence as _evidence
from orchestrator.workflow.engine import verification_records as _records

LocalRunEvidence = tuple[_records.EvidenceBinding, tuple[_evidence.VerifiedCommand, ...]]


def local_run_evidence(
    run: _verify_models.VerifyResult, target: _records.EvidenceTarget,
) -> LocalRunEvidence | None:
    """The binding and commands `run` is evidence of for `target`, or None."""
    if not run.is_reusable:
        return None
    try:
        commands = tuple(
            _evidence.VerifiedCommand(
                command=outcome.command,
                exit_status=outcome.exit_code,
                output=outcome.output,
            )
            for outcome in run.attempted_commands
        )
    except _evidence.ArtifactRefusedError:
        return None
    binding = _records.EvidenceBinding(
        target=target,
        source=_evidence.EvidenceSource.ORCHESTRATOR_EXECUTED,
        tested_sha=run.commit,
        tested_tree=run.tree_identity,
        context_revision=run.context_revision,
    )
    return binding, commands
