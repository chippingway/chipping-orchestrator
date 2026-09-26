# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The pinned comment read afresh before evidence is declared current.

An artifact post is a request long enough for another road to write the pinned
comment: a developer report settling a later revision, a reviewer recording
the subject it was handed, another evidence transaction replacing this one.
Nothing in the state the tick holds sees any of it, and a settlement composed
over that state would declare evidence current for a subject the comment no
longer carries -- and write the replaced records back over the newer ones.

So the comment is read again, and it has to be the comment this tick read and
still carry every record the evidence is bound through exactly as the state in
hand spells them: the developer report's transaction and settled pair, the
review subjects, and this domain's own records. Compared as the comment's JSON
spells them, so a field written `null` where there was none, or `true` where
there was `1`, is a move. The records that move are the caller's to refuse
over; the fresh reading comes back with them, since it is the one comment any
write may still be laid over.

A comment that will not read or parse, or is no longer the one the state was
read from, holds: nobody could say what it carries, and a write over it would
pin a second comment or replace one nobody read.
"""
from __future__ import annotations

import json
import logging

from github.Issue import Issue

from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    report_evidence_models as _evidence_models,
    report_records as _report_records,
    review_subjects as _review_subjects,
    verification_records as _records,
)

log = logging.getLogger("orchestrator.workflow")

# Every record the evidence is bound through: the pull request, the developer
# report's transaction and settled pair, the review subjects, and this
# domain's own four records.
_BOUND_RECORDS = (
    "pr_number",
    _report_records.PENDING_REPORT,
    _report_records.DELIVERED_REPORT,
    _report_records.CURRENT_REPORT,
    _report_records.REPORT_HANDOFF,
    _review_subjects.REVIEW_SUBJECT,
    _review_subjects.RETURNED_SUBJECT,
    _records.PENDING_EVIDENCE,
    _records.CURRENT_EVIDENCE,
    _records.EVIDENCE_HISTORY,
    _records.EVIDENCE_HANDOFF,
)


def durable_comment(
    gh: GitHubClient, issue: Issue, state: PinnedState,
) -> tuple[PinnedState | None, _evidence_models.ReportEvidence | None]:
    """The comment read afresh, and the refusal its records earn, if any.

    `(comment, None)` where it carries every bound record as `state` does,
    `(comment, DEFER)` where one moved, and `(None, HOLD)` where it will not
    read or parse or is not the comment `state` was read from.
    """
    durable = _read(gh, issue, state)
    if durable is None:
        return None, _evidence_models.ReportEvidence(
            _evidence_models.ReportEvidenceVerdict.HOLD,
            "the pinned comment could not be read again as the one this tick read",
        )
    moved = [
        field for field in _BOUND_RECORDS
        if _spelled(durable.data, field) != _spelled(state.data, field)
    ]
    if not moved:
        return durable, None
    return durable, _evidence_models.ReportEvidence(
        _evidence_models.ReportEvidenceVerdict.DEFER,
        f"the pinned comment's {moved[0]} moved while the artifact was posted",
    )


def _read(gh: GitHubClient, issue: Issue, state: PinnedState) -> PinnedState | None:
    """The comment `state` was read from, read afresh and parsed, or None logged."""
    try:
        durable = gh.read_pinned_state(issue)
    except Exception:
        log.exception(
            "issue=#%d could not read its pinned comment again before settling "
            "verification evidence", issue.number,
        )
        return None
    if not durable.parsed or durable.comment_id != state.comment_id:
        return None
    return durable


def _spelled(recorded: dict, field: str) -> tuple:
    """Whether one field is on the comment, and how its JSON spells it."""
    return field in recorded, json.dumps(recorded.get(field), sort_keys=True)
