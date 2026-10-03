# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A developer report quoting a receipt, the same account in prose, and what refusing a report says.

The quoting report is the shape a careful developer writes: delimited
correctly, well inside the writing budget every report prompt sets, and
quoting a split child's hidden receipt in inline code as an example. Its prose
twin says the same thing with the receipt described rather than reproduced,
which is what the prompt asks for and what a recording accepts.

The words are spelled out here rather than read off the notice owner, so a
notice that drifts from what a human must be told fails where it is posted.
"""
from __future__ import annotations

from dataclasses import dataclass

from orchestrator.workflow.engine import prompt_notes as _prompt_notes
from orchestrator.workflow.stages.decomposition import split_receipts as _split_receipts

# The parent the quoted receipt names, and the slice it was stamped for.
_SPLIT_PARENT = 2_045

_SLICE = 0

# A whole split-child receipt, exactly as a split stamps one after a child's body.
QUOTED_RECEIPT = _split_receipts.receipt(_SPLIT_PARENT, "0123456789abcdef", _SLICE, None)

# The account both reports share, repeated until the report reads like a real
# one -- thousands of characters, and still well inside the writing budget.
_ACCOUNT = (
    "The rebased branch keeps the split-child adoption exactly as it was: a "
    "recovery recognizes only the next attributable open child on its birth "
    "label and records that child in one write of the parent's pinned state. "
)

_ACCOUNTS = 16

_VERIFIED = "Verified with `uv run pytest tests`, which passes on the rebased head."

QUOTING_REPORT = "".join((
    _ACCOUNT * _ACCOUNTS,
    f"A child is recognized by the receipt stamped after its body, `{QUOTED_RECEIPT}`. ",
    _VERIFIED,
))

PROSE_REPORT = QUOTING_REPORT.replace(
    f"`{QUOTED_RECEIPT}`",
    "the hidden split-child marker naming the parent, the attempt, the slice "
    "index, and the lineage the split owed",
)

# The most a developer report is asked to be, which the quoting report sits under.
WRITING_BUDGET = _prompt_notes._DEVELOPER_REPORT_CHAR_BUDGET

# Words only a refusal that MEASURED a size may use: a notice or log line
# carrying one over any other refusal sends its reader to shorten a report
# that was refused for something else.
SIZE_WORDS = ("characters", "too long", "shorter", "room", "GitHub accepts", "a recorded report may be")


@dataclass(frozen=True)
class Said:
    """What one refusal's notice and log line must say, and what neither may.

    `notice` is every fragment the notice carries, `logged` the fragment the
    log line carries, and `unsaid` the words neither may use.
    """

    notice: tuple[str, ...]
    logged: str
    unsaid: tuple[str, ...] = SIZE_WORDS

    def assert_said(self, case, notice: str, logged: str) -> None:
        """Fail `case` unless `notice` and `logged` say this and nothing it rules out."""
        for fragment in self.notice:
            case.assertIn(fragment, notice)
        case.assertIn(self.logged, logged)
        for word in self.unsaid:
            case.assertNotIn(word, notice)
            case.assertNotIn(word, logged)


# What refusing a quoted receipt says: which text refused the report, that no
# quotation excuses it, and the correction a reply should ask for -- with
# nothing about size, and never the receipt itself, since a notice is a comment
# of this orchestrator's own, where a quoted receipt reads as the step it names.
RECEIPT_REFUSAL = Said(
    notice=(
        "the literal text that opens every hidden receipt this orchestrator records its own steps with",
        "inline code, a fenced block, and a quotation included",
        "described in prose rather than quoted",
        "needs no new commit",
    ),
    logged="(reserved_receipt)",
    unsaid=(*SIZE_WORDS, QUOTED_RECEIPT),
)
