# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What one local `VERIFY_COMMANDS` run is worth as evidence, bound to its target.

Only two kinds of run are evidence, and each only on its own transcript. A
passing run is one `VerifyResult.is_reusable` vouches for: every configured
command ran, in order, exited 0 on the tested commit and tree, and the context
revision is the one its commands and timeout mint. A failing run is one whose
commands before the last each passed that same way and whose last exited
nonzero while leaving HEAD and its tree where they were -- a genuine failure of
the tested tree, which stays actionable evidence rather than disappearing.

Everything else binds nothing. An empty configuration ran nothing and is not
evidence that anything passed; a timeout, a dirty tree, or a moved HEAD or
tree is a run that cannot say which tree it describes; and a run that never
read its commit and tree has nothing to bind. Nothing is counted or inferred:
the commands published are exactly the ones that ran, with the status and the
already-redacted, already-bounded output each one earned.

A command the published format refuses -- a transcript carrying the fence that
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
    if not _transcript_is_evidence(run):
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


def _transcript_is_evidence(run: _verify_models.VerifyResult) -> bool:
    """Whether `run` passed whole, or failed on its last command and nowhere else."""
    if run.is_reusable:
        return True
    ran = run.attempted_commands
    if run.status != _verify_models.VERIFY_STATUS_FAILED or not ran:
        return False
    if not (run.commit and run.tree_identity and run.timeout):
        return False
    if run.context_revision != _verify_models._context_revision(
        run.configured_commands, run.timeout,
    ):
        return False
    *passed, failed = ran
    earlier = tuple(outcome.command for outcome in ran)
    return (
        earlier == run.configured_commands[:len(ran)]
        and all(_verify_models._passed_on(outcome, run.commit, run.tree_identity) for outcome in passed)
        and _failed_on(failed, run.commit, run.tree_identity)
    )


def _failed_on(
    outcome: _verify_models.VerifyCommandOutcome, commit: str, tree: str,
) -> bool:
    """Whether `outcome` exited nonzero and left `commit` and `tree` where they were."""
    readings = (outcome.head_before, outcome.head_after, outcome.tree_before, outcome.tree_after)
    exited = outcome.exit_code
    return (
        outcome.status == _verify_models.VERIFY_STATUS_FAILED
        and isinstance(exited, int)
        and exited != 0
        and readings == (commit, commit, tree, tree)
    )
