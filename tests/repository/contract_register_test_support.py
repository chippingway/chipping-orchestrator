# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""How the contract register reads: its checklist, its sections, and their parts.

`docs/contracts.md` is required reading before any change, and every other page
reaches a contract through its section heading's anchor. The checks over it
hold the register's shape rather than its wording -- which anchors exist, that
each checklist row still says what its section's Rule says, and that each
section keeps its parts in order -- so what a rule states stays free to change
with the contract it records.
"""
from __future__ import annotations

import re

from tests.repository.doc_link_test_support import heading_anchor

CONTRACTS_PAGE = "docs/contracts.md"
SECTION_PARTS = ("Rule", "Why", "Limits", "Specs", "Checks")

_CHECKLIST_ROW = re.compile(r"^\| \[(C-\d{2})\] \| (.*) \|$", re.MULTILINE)
_SECTION_HEADING = re.compile(r"^## ((C-\d{2}): .+)$", re.MULTILINE)
_REFERENCE = re.compile(r"^\[(C-\d{2})\]: #(\S+)$", re.MULTILINE)
_PART = re.compile(r"^\*\*(\w+):", re.MULTILINE)
_RULE = re.compile(r"^\*\*Rule: (.+)\*\*$", re.MULTILINE)
_NEXT_HEADING = "\n## "
_LISTING_DRIFT = "checklist and sections list different IDs"
_ROW_DRIFT = "checklist row differs from its Rule"
_PART_DRIFT = "parts are missing or out of order"


def contract_sections(text: str) -> list[tuple[str, str, str]]:
    """Each contract's ID, heading anchor, and body, in page order."""
    return [_section(text, heading) for heading in _SECTION_HEADING.finditer(text)]


def register_problems(text: str) -> list[str]:
    """Every place the checklist, the reference links, and the sections disagree."""
    sections = contract_sections(text)
    section_ids = [section[0] for section in sections]
    problems = [] if _checklist_ids(text) == section_ids else [_LISTING_DRIFT]
    for section in sections:
        problems.extend(_section_problems(section, text))
    return problems


def _checklist_ids(text: str) -> list[str]:
    return [row[0] for row in _CHECKLIST_ROW.findall(text)]


def _section(text: str, heading: re.Match[str]) -> tuple[str, str, str]:
    # A body runs to the next second-level heading, so the last contract stops
    # at the maintenance section rather than taking it in.
    body = text[heading.end():].split(_NEXT_HEADING, 1)[0]
    return heading.group(2), heading_anchor(heading.group(1)), body


def _section_problems(section: tuple[str, str, str], text: str) -> list[str]:
    contract_id, anchor, body = section
    return [
        f"{contract_id}: {message}"
        for held, message in (
            (_rule(body) == _entry(_CHECKLIST_ROW, text, contract_id), _ROW_DRIFT),
            (tuple(_PART.findall(body)) == SECTION_PARTS, _PART_DRIFT),
            (_entry(_REFERENCE, text, contract_id) == anchor, f"reference link misses #{anchor}"),
        )
        if not held
    ]


def _entry(pattern: re.Pattern[str], text: str, contract_id: str) -> str | None:
    return dict(pattern.findall(text)).get(contract_id)


def _rule(body: str) -> str:
    rule = _RULE.search(body)
    return rule.group(1) if rule else ""
