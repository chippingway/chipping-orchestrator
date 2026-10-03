# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a prompt says about a developer report's scope and the receipts it may not quote.

The report covers the final change, its rationale, and unresolved risks, and
leaves the verification run out -- while every check stays owed -- so the scope
guidance names what the report includes, each account of verification it
leaves out, and the checks it does not excuse. A report carrying this
orchestrator's receipt prefix is refused however the copy is set off, so the
receipt guidance names that literal prefix, every way of quoting it that does
not excuse it, and prose as the way to describe a receipt instead. The
fragments are written out here rather than read off the notes, so a prompt
handed to a run that drifts from them fails where it is handed.
"""
from __future__ import annotations

from orchestrator.github.comments import RECEIPT_MARKER_PREFIX

REPORT_SCOPE = (
    "Include only the final change, its rationale, and unresolved risks",
    "Leave verification out of the report",
    "no verification or testing section",
    "no inventory of the commands you ran",
    "no summary of their results",
    "not what you run",
    "still carry out every check this task or the repository asks for",
    "name a check that still fails, or one you could not run, as an unresolved risk",
)

# Requests for an account of the verification run, which no report prompt makes.
VERIFICATION_ACCOUNT_REQUESTS = (
    "verification performed",
    "verification detail",
)

RECEIPT_RESTRICTION = (
    f"must not contain the literal text `{RECEIPT_MARKER_PREFIX}` anywhere",
    "inline code",
    "a fenced code block",
    "a quotation",
    "does not make it publishable",
    "a report carrying it is refused and nothing is published",
    "describe its format in prose instead of reproducing it",
)


def assert_teaches_report_scope(case, prompt: str) -> None:
    """Fail `case` unless `prompt` scopes the report and asks for no verification account."""
    for fragment in REPORT_SCOPE:
        with case.subTest(scope_fragment=fragment):
            case.assertIn(fragment, prompt)
    for request in VERIFICATION_ACCOUNT_REQUESTS:
        with case.subTest(verification_request=request):
            case.assertNotIn(request, prompt)


def assert_teaches_receipt_restriction(case, prompt: str) -> None:
    """Fail `case` unless `prompt` carries every fragment of the restriction."""
    for fragment in RECEIPT_RESTRICTION:
        with case.subTest(receipt_fragment=fragment):
            case.assertIn(fragment, prompt)
