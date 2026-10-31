# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Whether a record a reviewer's change request's round froze still reads, told by the record's name.

A frozen record that moved is proved stale only where the record's own reader
takes its new spelling (`completion_prerequisites`); one no reader takes is
damage, and holds the capture. These are the readers for the records a change
request's roads freeze beside its verdict and pull request -- the feedback
anchor a failed run's `/orchestrator continue` replays, the stamp an in_review
relabel leaves on a round it routes to `workflow:fixing`, the code-publication
receipt a resume over unpushed work stands on, and the settled report and
verification evidence the request was reviewed over -- each read as its own
owner reads it, absent reading as gone and `null` read as that owner reads it:
gone where it is the record's resting state, damage where no writer leaves it.
The settled report and its handoff read only as the pair one settlement writes
(`settled_report_reads`), and current evidence and its handoff likewise, so a
current record beside no handoff that describes it is damage too, never a
report or evidence settled since. The receipt's members read only where the
receipt group does (`stages/implementing/late_receipt_damage`, resolved when
called), since its three members are one record. The same readers say whether
the settled report a held change request was reviewed over, and the evidence
it claims, can be read at all (`settled_report_reads`, `evidence_unread`), so
damage there holds its capture rather than reading as a report or evidence
another revision superseded.
"""
from __future__ import annotations

import importlib
from types import MappingProxyType

from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    completion_frozen as _frozen,
    report_record_values as _record_values,
    report_records as _report_records,
    report_settlement_state as _settlement,
    stage_targets as _stage_targets,
    verification_record_state as _evidence_state,
    verification_records as _evidence_records,
    verification_settlement_state as _evidence_settlement,
)
from orchestrator.workflow.engine.report_replay_guards import companions_disagree
from orchestrator.workflow.engine.verification_current import handoff_describes

_FEEDBACK_ANCHOR = "pending_fix_reviewer_comment_id"

_PENDING_FIX_AT = "pending_fix_at"

_CURRENT_REPORT = _report_records.CURRENT_REPORT

_REPORT_HANDOFF = _report_records.REPORT_HANDOFF

_CURRENT_EVIDENCE = _evidence_records.CURRENT_EVIDENCE

_PENDING_EVIDENCE = _evidence_records.PENDING_EVIDENCE

_EVIDENCE_HISTORY = _evidence_records.EVIDENCE_HISTORY

_EVIDENCE_HANDOFF = _evidence_records.EVIDENCE_HANDOFF

_REVISION_FLOOR = _evidence_records.REVISION_FLOOR

# Every verification evidence record a claim is judged over.
_EVIDENCE = (_CURRENT_EVIDENCE, _PENDING_EVIDENCE, _EVIDENCE_HISTORY, _EVIDENCE_HANDOFF, _REVISION_FLOOR)


def settled_report_reads(state: PinnedState) -> bool:
    """Whether the settled report and its handoff read as the pair one settlement wrote, or as no settlement yet.

    A settlement writes the two in one write and nothing clears either
    (`report_settlement_state`), so a current report has to read beside the
    handoff its settlement wrote and the handoff beside it: either one
    without the other, one spelled as nothing its reader takes -- `null`
    included -- or a pair naming another pull request, revision, or commit
    (`report_replay_guards.companions_disagree`) is damage, never a report
    settled since.
    """
    if not _settlement.carries_settled_record(state):
        return True
    current = _settlement.read_current_report(state)
    handoff = _settlement.read_handoff(state)
    if current is None or handoff is None:
        return False
    return not companions_disagree(current, handoff)


def _settled_evidence_reads(state: PinnedState) -> bool:
    """Whether the current evidence and its handoff read as a settlement or an invalidation left them.

    A settlement writes the two in one write and an invalidation clears the
    current record alone (`verification_settlement_state`), so current
    evidence has to read beside the handoff its settlement wrote
    (`verification_current.handoff_describes`): one beside no handoff, an
    unreadable one, or another settlement's is neither move, but damage, and
    so is either record spelled as nothing its reader takes.
    """
    if state.get(_CURRENT_EVIDENCE) is None:
        return not state.carries(_EVIDENCE_HANDOFF) or _evidence_settlement.read_evidence_handoff(state) is not None
    current = _evidence_settlement.read_current_evidence(state)
    return current is not None and handoff_describes(state, current)


# Each record's reader, by the record's name, following its own owner on what
# `null` is. The anchor and the in_review stamp are cleared to `null` by the
# round that closes them, pending evidence by the settlement that ends it, and
# current evidence by an invalidation, so `null` is each one's resting state
# and reads as gone. Nothing writes `null` into the settled report pair, the
# evidence handoff, the evidence history, or the revision floor -- a
# settlement replaces each -- so there a key holding `null` is a truncated
# write or a hand edit, damage, as each of their owners reads it
# (`report_settlement_state.carries_settled_record`,
# `verification_settlement_state.read_evidence_history`,
# `verification_record_state._latest_revision`). The settled report and its
# handoff, and current evidence and its handoff, are each read as the pair one
# settlement writes (`settled_report_reads`, `_settled_evidence_reads`).
READS = MappingProxyType({
    _FEEDBACK_ANCHOR: lambda state: (
        state.get(_FEEDBACK_ANCHOR) is None
        or _record_values.as_recorded_number(state.get(_FEEDBACK_ANCHOR)) is not None
    ),
    _PENDING_FIX_AT: lambda state: isinstance(state.get(_PENDING_FIX_AT), str | None),
    **dict.fromkeys(
        (_frozen.PUBLISHED_COMMIT, _frozen.PUBLISHED_LEASE, _frozen.PUBLISHED_PULL_REQUEST),
        lambda state: not importlib.import_module(_stage_targets._LATE_RECEIPT_DAMAGE_OWNER)._damaged_receipt(state),
    ),
    **dict.fromkeys((_CURRENT_REPORT, _REPORT_HANDOFF), settled_report_reads),
    _PENDING_EVIDENCE: lambda state: (
        state.get(_PENDING_EVIDENCE) is None or _evidence_state.read_pending_evidence(state) is not None
    ),
    _EVIDENCE_HISTORY: lambda state: _evidence_settlement.read_evidence_history(state) is not None,
    **dict.fromkeys((_CURRENT_EVIDENCE, _EVIDENCE_HANDOFF), _settled_evidence_reads),
    _REVISION_FLOOR: lambda state: (
        not state.carries(_REVISION_FLOOR)
        or _record_values.as_recorded_number(state.get(_REVISION_FLOOR)) is not None
    ),
})


def evidence_unread(state: PinnedState) -> bool:
    """Whether the verification evidence a claim is judged over is claimed in a shape nobody can read.

    Any of its records spelled as nothing its reader takes, current evidence
    beside no handoff that describes it, or a latest revision nobody can say
    (`verification_record_state._latest_revision`) is damage: what a claim's
    standing reads as settled or lost over it is no proof either way.
    """
    damaged = not all(READS[field](state) for field in _EVIDENCE)
    return damaged or _evidence_state._latest_revision(state) is None
