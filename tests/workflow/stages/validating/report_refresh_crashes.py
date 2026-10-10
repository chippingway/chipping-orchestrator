# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The windows the publication behind a report refresh opens, driven as failures.

The refresh records its report before anything is posted, then binds it to the
publication and posts it under a receipt, then settles it in one write. So
there are four places for it to stop short: GitHub refusing the post, GitHub
landing it and the response being lost, the process ending before the binding,
and the process ending on the settlement's own write with the comment already
posted. Each leaves the report owed on the pinned comment for a later tick.

A process ending is spelled as a raise the case swallows, so what a test reads
afterwards is exactly the durable state a crash would have left. Each window is
opened on the case's own pull request and the head it stands on, so the
rebased world and the journey that squashes and rebases it share them.
"""
from __future__ import annotations

import contextlib
from unittest.mock import patch

from orchestrator.workflow.engine import (
    report_binding as _report_binding,
    report_settlement_state as _settlement,
)


class _Crashed(RuntimeError):
    """The process ending where a case says it ends."""


@contextlib.contextmanager
def refusing_the_post(case):
    """GitHub refuses the report's comment for as long as the tick runs."""
    case.github.report_failures.refused.add(case.pull_request.number)
    yield
    case.github.report_failures.refused.discard(case.pull_request.number)


@contextlib.contextmanager
def losing_the_response(case):
    """GitHub lands the report's comment and the response to the post is lost."""
    case.github.report_failures.lost.add(case.pull_request.number)
    yield
    case.github.report_failures.lost.discard(case.pull_request.number)


@contextlib.contextmanager
def dying_before_the_binding(case):
    """A process that ends between the report's own write and its binding.

    The report is recorded as a delivery and nothing has been posted, which
    the next tick's hold binds and settles for itself.
    """
    with patch.object(
        _report_binding, "binds_the_delivery", side_effect=_Crashed,
    ), contextlib.suppress(_Crashed):
        yield


@contextlib.contextmanager
def dying_on_the_settlement(case):
    """A process that ends on the write that would settle the posted report.

    The comment is on the pull request and the transaction still names it
    owed, which is the window a receipt exists to close. The settlement is a
    guarded commit, landed through the strict edit, so that is where the
    process ends.
    """
    edits = case.github.edit_pinned_state
    with patch.object(
        case.github, "edit_pinned_state", _DiesOnTheSettlement(edits, case.pull_request.head.sha),
    ), contextlib.suppress(_Crashed):
        yield


class _DiesOnTheSettlement:
    """The pinned edits a tick makes, ending on the one settling a report of `head`, the rewritten head."""

    def __init__(self, edits, head: str) -> None:
        self._edits = edits
        self._head = head

    def __call__(self, issue, state, **options):
        settled = _settlement.read_current_report(state)
        if settled is not None and settled.subject.source_sha == self._head:
            raise _Crashed
        return self._edits(issue, state, **options)
