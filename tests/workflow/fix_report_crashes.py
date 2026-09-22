# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The windows a fix round's handover opens, driven as a process ending.

Each is an ordering the round chose on purpose, so each is worth crashing in.
The report is written durably ahead of the size gate, and the relabel comes
last of all -- so a round that answered in CODE opens three windows rather than
one, and what tells them apart is how far its publication got. The first is
between the report's write and the gate: the commit is in the checkout, nothing
has measured or pushed it, and a tick that handed the report on from there
would be handing on a report about work no pull request carries. The second is
past the push and before the BINDING: the commit is on the pull request, the
record is still a delivery, and nothing of the handover has been charged. The
third is past the settlement and before the relabel: the report is published,
the readers and the round the record froze are applied, and the issue is still
sitting on `workflow:fixing` under a raised mark -- which the next tick has to
recognise rather than resume a developer over. The fourth is behind a park's
own write, which is where a park that left its feedback unread would have the
next tick resume the developer over it again.

A process ending is spelled as a raise the case swallows, so what a test reads
afterwards is exactly the durable state a crash would have left.
"""
from __future__ import annotations

import contextlib
from unittest.mock import patch

from orchestrator.workflow.engine import (
    report_binding as _report_binding,
    report_delivery as _report_delivery,
)
from orchestrator.workflow.stages.validating import dev_fix as _dev_fix

# The reason the park a report this workflow cannot deliver is filed under.
_UNDELIVERABLE = _report_delivery.UNDELIVERABLE_REPORT


@contextlib.contextmanager
def dying_before_the_publication():
    """A process that ends between the report's own write and the gate.

    The earliest of the four, and the only one a round that answered in code
    can reach: the report is on the pinned comment and the commit it describes
    is in the checkout, with nothing having measured or pushed it. Raised from
    the publication rather than from the record before it, so what stands
    afterwards is a report about work the pull request has not got.
    """
    with patch.object(
        _dev_fix, "_publish_dev_fix", _Dies(),
    ), contextlib.suppress(_Crashed):
        yield


@contextlib.contextmanager
def dying_before_the_relabel(case):
    """A process that ends between the report's settlement and the relabel.

    The window past the publication: the report is on the pull request and the
    write that settled it applied the readers and the round the record froze,
    leaving the mark that says so. Raised from the relabel itself, so
    everything the round made durable before it stands exactly as a crash
    would have left it -- a settled round under `workflow:fixing`.
    """
    with patch.object(
        case.github, "set_workflow_label", _Dies(),
    ), contextlib.suppress(_Crashed):
        yield


@contextlib.contextmanager
def dying_before_the_binding():
    """A process that ends between the round's push and the report's binding.

    The window between those two: the commit is on the pull request and its
    receipt is written, and nothing has bound the report to it yet -- so
    nothing of the handover is charged, and the record is still the delivery a
    later tick re-proves the checkout for. Raised from the binding rather than
    from the push before it, so everything the tick made durable stands
    exactly as a crash would have left it.
    """
    with patch.object(
        _report_binding, "binds_and_publishes", _Dies(),
    ), contextlib.suppress(_Crashed):
        yield


@contextlib.contextmanager
def dying_after_the_park(case):
    """A process that ends on the write a caller takes behind a park's own.

    What it leaves is the intermediate state the undeliverable-report park is
    durable in: the notice posted, its flags written, and nothing a caller
    meant to add behind it.
    """
    writes = case.github.write_pinned_state
    with patch.object(
        case.github, "write_pinned_state", _DiesBehindTheReportPark(writes),
    ), contextlib.suppress(_Crashed):
        yield


class _Crashed(RuntimeError):
    """The process ending where a case says it ends."""


class _Dies:
    """A step that never runs, because the process ended before it."""

    def __call__(self, *_args, **_kwargs):
        raise _Crashed


class _DiesBehindTheReportPark:
    """The pinned writes a tick makes, ending on the one behind the park's.

    Armed by the reason the undeliverable-report park files itself under
    rather than by the count or by `awaiting_human`, because a tick answering
    a park is already carrying both: the write under test is the one that
    records THIS park, and what a crash may not lose is whatever a caller
    would have added behind it.
    """

    def __init__(self, writes) -> None:
        self._writes = writes
        self._parked = False

    def __call__(self, issue, state):
        if self._parked:
            raise _Crashed
        self._parked = state.get("park_reason") == _UNDELIVERABLE
        return self._writes(issue, state)
