# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a prompt says about the receipts a developer report may not quote.

A report carrying this orchestrator's receipt prefix is refused however the
copy is set off, so the guidance names that literal prefix, every way of
quoting it that does not excuse it, and prose as the way to describe a receipt
instead. The fragments are written out here rather than read off the note, so a
prompt handed to a run that drifts from them fails where it is handed.
"""
from __future__ import annotations

from orchestrator.github.comments import RECEIPT_MARKER_PREFIX

RECEIPT_RESTRICTION = (
    f"must not contain the literal text `{RECEIPT_MARKER_PREFIX}` anywhere",
    "inline code",
    "a fenced code block",
    "a quotation",
    "does not make it publishable",
    "a report carrying it is refused and nothing is published",
    "describe its format in prose instead of reproducing it",
)


def assert_teaches_receipt_restriction(case, prompt: str) -> None:
    """Fail `case` unless `prompt` carries every fragment of the restriction."""
    for fragment in RECEIPT_RESTRICTION:
        with case.subTest(receipt_fragment=fragment):
            case.assertIn(fragment, prompt)
