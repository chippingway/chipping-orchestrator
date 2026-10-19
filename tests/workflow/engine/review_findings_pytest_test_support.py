# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""pytest's headings as it prints them, and a caller reading pytest's output as `review_findings_failures` does.

`correlated` reads the output as the lead naming a check's failures does, the
findings' entries aside: it reads each line pytest's summary may report a
failure on, names its test ID by the sections the output holds, takes the
section the line reports, and then takes each section no line took by its own
title.
"""
from __future__ import annotations

from functools import partial

from orchestrator.workflow.engine.review_findings_pytest import COLLECTION, PytestOutput
from orchestrator.workflow.engine.review_findings_summary import SummaryLine

SUMMARY_HEADING = "=========================== short test summary info ============================\n"
ERRORS_HEADING = "==================================== ERRORS ====================================\n"
FAILURES_HEADING = "=================================== FAILURES ===================================\n"
QUIET_PROGRESS = "F                                                                        [100%]\n"
INTERRUPTED = "!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!"
MODULE = "tests/test_failure_with_a_long_module_name_to_fill_the_terminal.py"

# Failures pytest 9 printed with `--tb=line`, each below what it captured from
# its test: an exception group holding one exception, whose line traceback
# gives that exception's repr and the group's name; one holding two, whose
# gives the group's own exception; and a later failure, marked.
_CAPTURED = "----------------------------- Captured stdout call -----------------------------\ncaptured stdout\n"
GROUPS_LINE = (
    f"{FAILURES_HEADING}  + Exception Group Traceback (most recent call last):\n"
    '  |   File "/tmp/run/test_probe.py", line 3, in test_group\n'
    '  |     raise ExceptionGroup("group", [ValueError("inner")])\n  | ExceptionGroup: group (1 sub-exception)\n'
    "  +-+---------------- 1 ----------------\n    | ValueError: inner\n    +------------------------------------\n"
    f"{_CAPTURED}/tmp/run/test_probe.py:3: ValueError('inner') [single exception in ExceptionGroup]\n"
    "  + Exception Group Traceback (most recent call last):\n  | ExceptionGroup: grouped failure (2 sub-exceptions)\n"
    "  +-+---------------- 1 ----------------\n    | ValueError: inner\n    +---------------- 2 ----------------\n"
    "    | TypeError: other\n    +------------------------------------\n"
    f"{_CAPTURED}/tmp/run/test_probe.py:7: ExceptionGroup: grouped failure (2 sub-exceptions)\n"
    "E   RuntimeError: later failure\n/tmp/run/test_probe.py:10: RuntimeError: later failure\n"
)

# What a summary line reads as and took: the failure it reports, the phase of
# the section it took -- "" for a test's own -- and that section's exception,
# None where it took none.
Taken = tuple[SummaryLine, str, str | None]

# The title and exception of each section no summary line took.
_Left = list[tuple[str, str]]


def correlated(output: str) -> tuple[list[Taken], _Left]:
    """What each summary line of `output` reads as and took, and each section none took."""
    read = PytestOutput(output.split("\n"))
    taken = [_taking(read, line, run) for line, run in read.summary]
    return [took for took in taken if took], _left(read)


def _taking(read: PytestOutput, line: str, run: int) -> Taken | None:
    """What `line` of `run` reads as and takes; None where it reports no failure."""
    summary = SummaryLine.read(line, partial(_named, read, run))
    return None if summary is None else (summary, *_took(read, summary, run))


def _left(read: PytestOutput) -> _Left:
    """Each section of `read` no line took, taking each by its own title in turn."""
    left: _Left = []
    for section in read.sections:
        own = read.take({section.title}, "", section.run)
        if own is not None:
            left.append((own.title, own.raised))
    return left


def _named(read: PytestOutput, run: int, node: str, error: str) -> tuple[int, ...]:
    """How surely `node` is the ID of a summary line of `run`: by a section showing `error`, the earlier the surer.

    Else by a title of that run naming its test, or -- for a path alone,
    which names none -- the path a collection's section titles.
    """
    number = read.showing(node, error, run)
    if number is not None:
        return 2, -number
    named = read.name(node) or node
    return (1,) if (named, run) in read.titled else ()


def _took(read: PytestOutput, summary: SummaryLine, run: int) -> tuple[str, str | None]:
    """The phase and exception of the section `summary` takes: a test's, a setup's or teardown's, or a collection's."""
    if not summary.node:
        return "", None
    if not summary.errored:
        title = f"{read.name(summary.node)} {summary.subtest}".rstrip()
        section = read.take({title, ""}, summary.error, run)
        return "", None if section is None else section.raised
    phase, raised = read.phase(summary.node, summary.error, run)
    if phase:
        return phase, raised
    collected = read.collection(summary.node, summary.error, run)
    return ("", None) if collected is None else (COLLECTION, collected)
