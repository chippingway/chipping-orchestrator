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
tree it tested. Nor is a run on any commit but the head its target answers
for: fresh evidence is about that head, and answering for another one is a
carry-forward decision, made on the trees, that a local run never makes.

Nothing is counted or inferred: the commands published are exactly the ones
that ran, with the already-redacted, already-bounded output each one earned. A
command the published format refuses -- a transcript carrying the fence that
closes it, say -- binds nothing either, and nor does text UTF-8 cannot carry
or a transcript too long for one artifact to carry, because an artifact that
cannot be posted is not evidence anybody can be shown. That length is measured under the widest
receipt and revision any record can carry, so no transaction minted for what
binds here renders a longer artifact than the one measured. What is left to
the recorder is the room the pinned comment has for the record beside
everything else the issue carries (`verification_record_state`).

Dormant: the verify gate does not hand its result here yet, so no local run is
bound or recorded as evidence until a producer asks (`verification_records`).
"""
from __future__ import annotations

import uuid

from orchestrator.git.verification import models as _verify_models
from orchestrator.github import verification_artifacts as _artifacts, verification_evidence as _evidence
from orchestrator.workflow.engine import report_record_values as _record_values, verification_records as _records

LocalRunEvidence = tuple[_records.EvidenceBinding, tuple[_evidence.VerifiedCommand, ...]]

# The widest identity a record carries: an issue and a revision at the widest
# either is recorded at, and a nonce of the one length it is minted at.
_WIDEST_REVISION = _record_values.MAX_RECORDED_NUMBER

_WIDEST_RECEIPT = _records.RECEIPT.format(
    issue=_WIDEST_REVISION, revision=_WIDEST_REVISION, nonce=uuid.UUID(int=0).hex,
)


def local_run_evidence(
    run: _verify_models.VerifyResult, target: _records.EvidenceTarget,
) -> LocalRunEvidence | None:
    """The binding and commands `run` is evidence of for `target`, or None.

    Eligibility of the run and its artifact alone; recording the transaction
    minted from it still has to find room on the pinned comment.
    """
    if not run.is_reusable or run.commit != target.target_head:
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
    return (binding, commands) if _renders(binding, commands) else None


def _renders(
    binding: _records.EvidenceBinding, commands: tuple[_evidence.VerifiedCommand, ...],
) -> bool:
    """Whether the artifact of `binding` and `commands` fits one comment at the widest identity.

    False as well for text UTF-8 cannot carry -- a lone surrogate a decoder
    let through -- which raises where the artifact's evidence is hashed.
    """
    widest = _records.PendingEvidence(
        receipt=_WIDEST_RECEIPT, revision=_WIDEST_REVISION, binding=binding, commands=commands,
    )
    try:
        return bool(_artifacts.render_verification_artifact(widest.artifact))
    except (_evidence.ArtifactRefusedError, UnicodeEncodeError):
        return False
