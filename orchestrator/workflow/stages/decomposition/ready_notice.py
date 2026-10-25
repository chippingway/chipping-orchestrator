# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The notice a `ready` reroute owes its thread, said once whichever tick finishes the reroute.

A reroute records what its notice is owed beside its reset (`minted`): the
children the reset stopped tracking, whether the baseline it compared against
was missing rather than moved, and a receipt minted for the notice, which the
notice carries in a hidden marker. Two ticks may say it (`says`): the `ready`
tick behind its relabel to `decomposing`, and -- where that one was held, or
never got that far -- the `decomposing` tick ahead of retiring the marker. Each
looks for the receipt on its thread reading first, and a comment of this
orchestrator's carrying it is the notice already said, so it is said once
however often the issue comes back to `ready` before the marker is retired.

A `paused` or `backlog` applied while the tick ran stops the notice
(`ready_readings.held`), and the caller goes no further -- asked first, so a
notice already on the thread settles nothing past a hold either: the reroute
is still owed, and the tick after the hold comes off finishes it. A post that
fails is logged and left to the next tick that finishes the reroute while the
marker stands: the `decomposing` tick tries it again ahead of retiring the
marker, as does a `ready` tick an operator's relabel back brings first. Once
a retirement lands behind a post that failed again, the notice is abandoned
-- nothing reads the marker after it -- so a thread that will not take a
comment costs the reroute that one retry and never holds it; a post whose
answer was lost after it landed is found by its receipt rather than said
twice. A record carrying no receipt of the minted shape -- a
hand edit -- names nothing to look for, and its notice is said, as is a
member of any other shape read as naming no child and no missing baseline.
"""
from __future__ import annotations

import logging
import re
import secrets

from github.Issue import Issue

from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import comments as _comments, drift as _drift
from orchestrator.workflow.stages.decomposition import ready_readings as _readings, state as _state

log = logging.getLogger("orchestrator.workflow")

# The members of the reroute record: the children the reset stopped tracking,
# whether no baseline stood to compare against, and the notice's receipt.
_ORPHANS = "orphans"

_UNBASELINED = "unbaselined"

_RECEIPT = "receipt"

# How many random bytes a receipt is minted from, and how it is spelled: two
# lowercase hex digits a byte.
_RECEIPT_BYTES = 8

_RECEIPT_SPELLING = re.compile("[0-9a-f]{16}")

# The hidden marker the notice carries its receipt in, closed right after the
# receipt so no receipt that is a prefix of another claims a comment.
_RECEIPT_MARKER = "<!--orchestrator-ready-reroute:receipt={receipt}-->"

_UNBASELINED_NOTICE = (
    ":pencil2: this issue's record carries no baseline of the requirements it was created with, so nothing "
    "proves they still say what its split cut it for; re-running decomposer against the current body."
)

_ORPHANED = (
    " The previously-tracked children ({orphans}) will be ORPHANED -- the orchestrator no longer tracks "
    "them; please close any that no longer apply to the updated requirements."
)


def minted(orphans: list, *, unbaselined: bool) -> dict:
    """The reroute record a reset lands with: the children it orphans, why it ran, and a fresh receipt."""
    return {_ORPHANS: orphans, _UNBASELINED: unbaselined, _RECEIPT: secrets.token_hex(_RECEIPT_BYTES)}


def says(gh: GitHubClient, issue: Issue, state: PinnedState, owed: object, comments: list) -> bool:
    """Say the notice the reroute recorded as `owed`, unless `comments` already carries it; whether it is settled.

    False only where a hold stands, with nothing said -- whether or not the
    notice is already on the thread, since what the caller does past a
    settled notice is an effect of its own. Posting records the comment in
    this orchestrator's ledger on `state`, for the caller's next write to
    carry.
    """
    if _readings.held(gh, issue):
        return False
    recorded = owed if isinstance(owed, dict) else {}
    marker = _marker(recorded)
    if marker and _readings.found(gh, state, comments, marker) is not None:
        return True
    try:
        _comments._post_issue_comment(gh, issue, state, f"{_rendered(recorded)}\n\n{marker}".rstrip())
    except Exception:
        log.exception(
            "issue=#%d could not announce its reroute to decomposing; the reroute stands unannounced",
            issue.number,
        )
    return True


def _marker(recorded: dict) -> str:
    """The hidden marker carrying the receipt `recorded` names; empty where it names none of the minted shape."""
    receipt = recorded.get(_RECEIPT)
    if isinstance(receipt, str) and _RECEIPT_SPELLING.fullmatch(receipt):
        return _RECEIPT_MARKER.format(receipt=receipt)
    return ""


def _rendered(recorded: dict) -> str:
    """What the reroute recorded tells the thread: why it ran, and the children it orphaned."""
    named = recorded.get(_ORPHANS)
    if not isinstance(named, list):
        named = []
    orphans = [number for number in named if _state._names_an_issue(number)]
    if recorded.get(_UNBASELINED) is not True:
        return _drift._drift_to_decomposing_notice(orphans)
    if not orphans:
        return _UNBASELINED_NOTICE
    return _UNBASELINED_NOTICE + _ORPHANED.format(orphans=_state._issue_ref_list(orphans))
