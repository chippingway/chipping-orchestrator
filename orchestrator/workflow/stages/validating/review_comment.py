# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The pinned comment a review is bound to, and read against when it returns.

A validating tick resolves its reviewer's subject from the state it read when
it began, and a report settling since -- a later revision on the very head, by
another road -- is recorded on the pinned comment and nowhere in hand, while
the report the tick resolved still reads, exactly as it settled, where it was.
Nothing at that report's own location tells the two apart; only the records on
the comment do.

So the comment is read once the subject is resolved, and has to carry the
report records the state in hand carries (`_resolved_over`). Where it moved
them, or will not read or parse, nothing is handed over and the tick ends
without writing: every write from there would be laid over records the tick
never read, putting back the report they replaced. The reading that agreed is
handed on with the subject.

It is read again as the reviewer returns and once more after an approval is
verified (`_records_stand`), before anything the run leaves is written --
a park for a timeout or a missing verdict as much as the record of a verdict.
Records that stand leave the state alone. Records that moved refuse the
verdict, and everything the comment changed since the subject was resolved is
carried onto the state in hand, so every write the run makes lays itself over
the newer settlement. A comment that will not read or parse carries nothing,
and the tick ends with nothing written: the run is charged, and the next tick
spawns a reviewer over whatever the comment carries then.

Nothing here parks or posts.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from github.Issue import Issue

from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    report_records as _records,
    review_subjects as _review_subjects,
    run_charge_state as _run_charge_state,
)

log = logging.getLogger("orchestrator.workflow")

# Every record a developer report's transaction moves on the pinned comment:
# one in flight, the delivery it binds, and the settled pair a settlement
# replaces.
_REPORT_RECORDS = (
    _records.PENDING_REPORT,
    _records.DELIVERED_REPORT,
    _records.CURRENT_REPORT,
    _records.REPORT_HANDOFF,
)


@dataclass(frozen=True)
class _ResolvedSubject:
    """A subject a reviewer may be handed, and the comment it was resolved over."""

    subject: _review_subjects.ReviewSubject
    # The pinned comment as it was read once the subject was resolved, which
    # carries the very report records the subject was resolved from: what
    # the verdict's return measures the comment against.
    resolved_over: dict


def _resolved_over(
    gh: GitHubClient, issue: Issue, state: PinnedState,
) -> dict | None:
    """The comment a subject resolved from `state` is bound to, or None.

    None where the comment will not read or parse, or carries other report
    records than `state` does; the caller ends the tick without writing.
    """
    durable = _read(gh, issue, "bind the report its reviewer is handed")
    if durable is None:
        return None
    if _records_agree(durable.data, state.data):
        return dict(durable.data)
    log.warning(
        "issue=#%d its pinned comment does not carry the developer report "
        "records this tick resolved the review from; holding the review for "
        "the next tick with nothing written", issue.number,
    )
    return None


def _records_stand(
    gh: GitHubClient, issue: Issue, state: PinnedState, resolved_over: dict,
) -> bool | None:
    """Whether the comment still carries the report records the subject had.

    True where they stand. False where they moved: everything the comment
    changed since `resolved_over` is carried onto `state`, and the verdict is
    not acted on. None where the comment will not read or parse, which carries
    nothing -- a record read back empty is no settlement to keep -- and the
    caller ends the tick without writing.
    """
    durable = _read(gh, issue, "see whether a report settled while the reviewer ran")
    if durable is None:
        return None
    if _records_agree(durable.data, resolved_over):
        return True
    _run_charge_state._merge_circuit_fields(resolved_over, durable, state)
    log.warning(
        "issue=#%d its developer report records moved on the pinned comment "
        "while the reviewer ran; keeping them and not acting on the verdict",
        issue.number,
    )
    return False


def _read(gh: GitHubClient, issue: Issue, purpose: str) -> PinnedState | None:
    """The pinned comment read afresh and parsed, or None logged."""
    try:
        durable = gh.read_pinned_state(issue)
    except Exception:
        log.exception(
            "issue=#%d could not read its pinned comment to %s; ending the "
            "tick with nothing written", issue.number, purpose,
        )
        return None
    if durable.parsed:
        return durable
    log.error(
        "issue=#%d its pinned comment will not parse where it is read to %s; "
        "ending the tick with nothing written", issue.number, purpose,
    )
    return None


def _records_agree(durable: dict, in_hand: dict) -> bool:
    """Whether two readings of the comment carry the same report records."""
    return all(
        durable.get(record) == in_hand.get(record) for record in _REPORT_RECORDS
    )
