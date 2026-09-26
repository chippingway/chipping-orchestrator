# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a reviewer round writes onto the pinned comment, and the room kept for it.

A round writes onto the comment the developer report it reviews settled on,
at three points. Before the spawn it writes the configured reviewer spec and
the subject the reviewer is handed (`_records_the_launch`), durably and ahead
of the launch, so a round that dies mid-review still says what it was shown.
At the launch the circuit writes the lifetime run charge. On the return the
round writes the usage the reviewer ran up, the session it ran as, when it
returned, and the subject it was handed, again, as the one a reviewer really
read (`_records_the_return`) -- and, where it approves, the subject the
approval covers in that same write.

A developer report is accepted only where the comment its settlement leaves
has room for every one of those (`reserves_the_round`). Otherwise a report
accepted at the ceiling is followed by a launch whose charge GitHub refuses on
every tick, or by an approval refused after the reviewer it cost has run. Each
is replayed through the writer that makes it, at the widest it can be written:
the subject at `ReviewSubject.widest`, the charge at the widest count this
domain records with a fingerprint as wide as the digest a launch is named by,
and the session at the width of the UUID every session id is read as. Each
REPLACES what stands under its key, so the widest of each bounds what any
number of later rounds leaves.

The usage meters are the one part of the return not reserved. They are running
totals every agent run on the issue folds, put down by the developer run whose
report this is wherever its usage parsed, and a fold grows them by digits
rather than by a record -- which no measurement in this repository models for
any run.
"""
from __future__ import annotations

import hashlib
from uuid import UUID

from orchestrator import config
from orchestrator.github.pinned_state import PinnedState
from orchestrator.observability.usage.metrics import UsageMetrics
from orchestrator.workflow.engine import (
    issue_usage as _issue_usage,
    report_record_values as _record_values,
    review_subjects as _review_subjects,
    run_ledger as _run_ledger,
    run_ledger_values as _run_ledger_values,
    usage as _usage,
)

_REVIEW_AGENT = "review_agent"

_LAST_REVIEW_SESSION_ID = "last_review_session_id"

_LAST_REVIEW_AT = "last_review_at"

# A launch is charged under the SHA-256 hex digest of what it is, so this is as
# wide as any fingerprint the charge records.
_WIDEST_FINGERPRINT = "f" * len(hashlib.sha256().hexdigest())

# A reviewer never resumes, so the session id it is recorded with is the one
# read off its output, which is always a UUID -- and every UUID is spelled at
# this one width.
_WIDEST_SESSION_ID = str(UUID(int=0))


def _records_the_launch(
    state: PinnedState, subject: _review_subjects.ReviewSubject,
) -> None:
    """Stage the configured reviewer spec and the subject the reviewer is handed.

    The reviewer is spawned fresh every round with no resume, so both are
    overwritten every round, and a config flip mid-flight cannot rewrite
    which spec ran a round or what it was shown. The caller writes.
    """
    state.set(_REVIEW_AGENT, config.REVIEW_AGENT_SPEC)
    _review_subjects.record_reviewed(state, subject)


def _records_the_return(
    state: PinnedState,
    usage: UsageMetrics | None,
    session_id: str | None,
    subject: _review_subjects.ReviewSubject,
) -> None:
    """Stage what a returned reviewer leaves: its usage, its session, when, and what it read.

    The subject is the one the launch wrote, recorded again because only this
    write says a reviewer was really handed it: the launch's own goes down
    before the run budget is asked, so a launch that budget refused leaves it
    beside a reviewer nobody invoked. A run that yielded no session id leaves
    the last one standing. The caller writes.
    """
    _issue_usage._accumulate_issue_usage(state, usage)
    if session_id:
        state.set(_LAST_REVIEW_SESSION_ID, session_id)
    state.set(_LAST_REVIEW_AT, _usage._now_iso())
    state.set(_review_subjects.RETURNED_SUBJECT, subject.recorded())


def reserves_the_round(state: PinnedState) -> None:
    """Stage every record a reviewer round writes, each at its widest.

    For a measurement, never for a write: `report_record_state` asks it of the
    comment a settlement would leave. The approval goes down without the
    stamps it retires, since the docs pass and the ready ping behind it write
    them back.
    """
    widest = _review_subjects.ReviewSubject.widest()
    _records_the_launch(state, widest)
    # The charge adds one to the count it finds, so it is left one short of
    # the widest and charged through the ledger's own writer.
    state.set(
        _run_ledger_values.AGENT_RUNS_USED, _record_values.MAX_RECORDED_NUMBER - 1,
    )
    _run_ledger._reserve_run(state, _WIDEST_FINGERPRINT)
    _records_the_return(state, None, _WIDEST_SESSION_ID, widest)
    state.set(_review_subjects.APPROVED_SUBJECT, widest.recorded())
