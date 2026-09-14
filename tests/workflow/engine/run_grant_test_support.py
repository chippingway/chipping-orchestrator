# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The thread and the ledger the add-agent-runs command is read against.

The park's own fixtures live beside its owner
(`run_limit_test_support`); what is here is the half this command adds to
them -- an issue that has actually spent what it was allowed, the comment
somebody wrote on its thread, and the counts that buy runs beside the ones
that buy none. Three suites read them: the grammar that turns a line into a
request, the owner that spends on one, and the dispatcher's, since the command
is answered by the hold rather than by a stage.
"""
from __future__ import annotations

from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import run_grant_request as _run_grant_request
from tests.support.fakes import FakeComment, FakeUser
from tests.workflow.engine.run_limit_seeds import ALLOWANCE, parked_state
from tests.workflow.engine.run_limit_test_support import USED_FIELD, WATERMARK

# What one buyable request asks for, and the ceiling it leaves behind on an
# issue that has already spent everything it was allowed. The number is read
# by the grammar and by the park alike, so both are pinned to the same one.
ADDED = 3

GRANTED_ALLOWANCE = ALLOWANCE + ADDED

VALID = f"/orchestrator add-agent-runs {ADDED}"

# Two asks in one batch. Both sit above the watermark a park consumed, so
# either is unread, and the receipt each earns is scoped to the one that
# carried it -- which is what the pair are here to tell apart.
FIRST_ASK = WATERMARK + 1

SECOND_ASK = WATERMARK + 2

# Comfortably past `sys.int_info.default_max_str_digits`, the length at which
# the interpreter refuses to build an integer out of a decimal string.
_OVERLONG_DIGITS = 5000

# A count is the whole of what this command says, so everything that is not
# one whole number inside the bound reads the same way: nothing bought.
UNBUYABLE = (
    "",
    "0",
    "000",
    "-3",
    "+3",
    "3.5",
    "three",
    "0x3",
    "\N{ARABIC-INDIC DIGIT THREE}",
    str(_run_grant_request.MAX_RUNS_PER_COMMAND + 1),
    # A count no bound could hold, and one `int()` refuses to convert at all
    # past the interpreter's own limit -- so it has to be turned away before
    # it is converted rather than raised over.
    "9" * _OVERLONG_DIGITS,
)

# The default id a command comment carries: above the watermark a park
# consumed, and below the ids the fake client mints for what it posts itself,
# so a receipt written in answer to one always sorts after it.
COMMAND_ID = WATERMARK + 5

# The id of a comment somebody writes while a tick is answering the command
# below it: above the batch that tick read, and below the ids the fake client
# mints for what the orchestrator posts itself. That order is the race -- the
# comment exists before the receipt does, and no read here has seen it.
RACING_COMMENT_ID = COMMAND_ID + 1

# The author every command here is written by unless it is the outsider's.
# The allowlist is empty by default, so what this login pins is which comment
# was said by whom rather than whether it was trusted.
OPERATOR = "geserdugarov"


def spent_state(**fields) -> PinnedState:
    """A parked issue that has spent every run of a full allowance.

    The count is what this command is read against: what it buys is measured
    from the runs already spent, so a fixture that had spent none would pin an
    allowance the arithmetic cannot tell from the request.
    """
    return parked_state(**{USED_FIELD: ALLOWANCE, **fields})


def command(text: str, *, comment_id: int = COMMAND_ID, author: str = OPERATOR):
    """One thread comment, as an operator or an outsider wrote it."""
    return FakeComment(id=comment_id, body=text, user=FakeUser(author))
