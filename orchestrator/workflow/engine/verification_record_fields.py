# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The pinned object a binding and a pending transaction are written as.

The pull-request half of a binding is written by the report domain's own
`report_record_fields`, under the same keys and read by the same reader: the
evidence target IS a report subject about the head the evidence is written
for, and two spellings of one group are how two readers come to disagree about
what a record binds. What the run adds sits beside it -- the review subject as
`review_subjects` records it, who witnessed the run, the commit and tree the
commands ran on, and the context they ran under.

Everything is read fail-closed and all-or-nothing, for the reason every pinned
record here is: a binding short of any member is no binding, since the
reconciliation proves them TOGETHER on a tick with no run behind it. The review
subject in particular has to agree with the binding around it -- the same pull
request and the same requirements revision -- because the artifact names one
requirements revision for both, and a subject about another pull request is
evidence answering for work it never saw.

Commands are read back through the published format's own type, so a record
holding a command the artifact would refuse -- a backtick, a line ending, a
closing fence in a transcript, a receipt marker of ours -- reads as damage here
rather than as an artifact refused after the tick has already proved the world.
"""
from __future__ import annotations

from typing import Any

from orchestrator.github import verification_evidence as _evidence
from orchestrator.workflow.engine import (
    report_record_fields as _report_fields,
    report_record_values as _record_values,
    verification_records as _records,
)
from orchestrator.workflow.late_split import formats as _formats, payloads as _payloads

_SUBJECT = "subject"

_SOURCE = "source"

_TESTED = "tested"

_TREE = "tree"

_CONTEXT = "context"

_RECEIPT = "receipt"

_REVISION = "revision"

_COMMANDS = "commands"

# One command as it is recorded: the command line, its exit status, and the
# transcript the artifact carries for it.
_COMMAND_MEMBERS = 3

# The run half of a binding, each member and the shape it has to be: the tested
# commit and its tree as whole object ids, the context as a whole digest.
_RUN_MEMBERS = (
    (_TESTED, _formats.COMMIT_LENGTHS),
    (_TREE, _formats.COMMIT_LENGTHS),
    (_CONTEXT, _formats.DIGEST_LENGTHS),
)


def binding_fields(binding: _records.EvidenceBinding) -> dict[str, Any]:
    """The pinned fields one binding is recorded as."""
    return {
        **_report_fields.subject_fields(binding.target.publication),
        _SUBJECT: dict(binding.target.subject),
        _SOURCE: str(binding.source),
        _TESTED: binding.tested_sha,
        _TREE: binding.tested_tree,
        _CONTEXT: binding.context_revision,
    }


def binding_from(recorded: dict) -> _records.EvidenceBinding | None:
    """The binding one record names, or None unless it names a whole one.

    The run half is read as the header of an artifact has to carry it: whole
    object ids for the commit and the tree, a whole digest for the context, and
    a witness this format names.
    """
    run = tuple(
        _payloads.as_hex(recorded.get(key), lengths) for key, lengths in _RUN_MEMBERS
    )
    target = _target_from(recorded)
    source = _payloads.as_member(_evidence.EvidenceSource, recorded.get(_SOURCE))
    if target is None or source is None or not all(run):
        return None
    # The run half in the binding's own member order: tested commit, tree, context.
    return _records.EvidenceBinding(target, source, *run)


def pending_object(pending: _records.PendingEvidence) -> dict[str, Any]:
    """The pinned object one transaction is recorded as."""
    return {
        _RECEIPT: pending.receipt,
        _REVISION: pending.revision,
        **binding_fields(pending.binding),
        _COMMANDS: [
            [ran.command, ran.exit_status, ran.output] for ran in pending.commands
        ],
    }


def pending_from(recorded: dict) -> _records.PendingEvidence | None:
    """The transaction one recorded object is, or None for damage."""
    receipt = _record_values.as_receipt(recorded.get(_RECEIPT))
    revision = _record_values.as_recorded_number(recorded.get(_REVISION))
    binding = binding_from(recorded)
    commands = _commands_from(recorded.get(_COMMANDS))
    if not receipt or not revision or binding is None or commands is None:
        return None
    return _records.PendingEvidence(
        receipt=receipt, revision=revision, binding=binding, commands=commands,
    )


def _target_from(recorded: dict) -> _records.EvidenceTarget | None:
    """The target a record's publication and review subject make, or None.

    The subject has to read whole through its own owner's reader, and has to
    be about this pull request and these requirements.
    """
    publication = _report_fields.subject_from(recorded)
    subject = recorded.get(_SUBJECT)
    if publication is None or not isinstance(subject, dict):
        return None
    target = _records.EvidenceTarget(publication=publication, subject=subject)
    identity = target.subject_identity
    if identity is None or identity[0] != publication.pr_number:
        return None
    if target.subject_requirements != publication.requirements_revision:
        return None
    return target


def _commands_from(raw: object) -> tuple[_evidence.VerifiedCommand, ...] | None:
    """The commands a record carries, each one the artifact would publish, or None."""
    if not isinstance(raw, list):
        return None
    try:
        commands = tuple(_command_from(entry) for entry in raw)
    except _evidence.ArtifactRefusedError:
        return None
    return None if None in commands else commands


def _command_from(entry: object) -> _evidence.VerifiedCommand | None:
    """One recorded command, or None where it is not one this format writes.

    Text UTF-8 cannot carry is refused beside the format's own refusals, which
    raise: the comment is JSON, and a lone surrogate reads back into a string
    that raises where the artifact is hashed.
    """
    if not isinstance(entry, list) or len(entry) != _COMMAND_MEMBERS:
        return None
    command, exit_status, output = entry
    texts = (command, output)
    if not all(isinstance(text, str) for text in texts):
        return None
    if not all(_record_values.carries_utf8(text) for text in texts):
        return None
    return _evidence.VerifiedCommand(
        command=command, exit_status=exit_status, output=output,
    )
