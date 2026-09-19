# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Reading a settled developer report again, where the settlement recorded it.

A settled record says what the pull request carried once; only a fresh reading
of the exact location says it still does. Asked by whoever would hand work on
BECAUSE its report already went out, and posting nothing: the content, the
header a publication of ours went out under, and who wrote it, each held to the
road the settlement says it took. The implementing stage's publication asks it
last before its handoff, for the report it settled and for the one a recovery
would hand on.
"""
from __future__ import annotations

import logging
from typing import Any

from orchestrator.github import (
    comments as _trust,
    developer_reports as _reports,
    pull_request_reports as _pr_reports,
)
from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    report_publishing as _publishing,
    report_records as _records,
    report_settlement_state as _settlement,
)

log = logging.getLogger("orchestrator.workflow")

# The readings that found something at a settled location, whether or not it
# still hashes: only these are worth judging, and every other is the answer.
_READ_PRESENCES = frozenset((
    _pr_reports.ReportPresence.PRESENT, _pr_reports.ReportPresence.CHANGED,
))


def still_carries(
    gh: GitHubClient, state: PinnedState, current: _records.CurrentReport,
) -> _pr_reports.ReportPresence:
    """Whether the report a settlement recorded still reads where it settled.

    Held to the road that settled it, since the digest proves a different thing
    on each. A VERIFIED location is the text itself: it has to hash to the
    digest still, under an author this deployment trusts, as the verification
    required. A PUBLISHED report is that text under a header of ours, in a
    comment: it has to re-render there, written by us, with the text digest
    and whole header -- pull request, commit, requirements, revision, and the
    handoff's receipt -- the settlement recorded. So a comment cut down to its
    bare text is CHANGED though it hashes, and so is a consistent rewrite that
    keeps the words while claiming another publication; nothing is recognized
    by a capped ledger of posted ids.

    A record that does not say which road it was is held to what its location
    allows: a description can only have been verified, and a comment is held to
    the rendering, the stricter of the two. UNCONFIRMED is a reading nobody
    could take, of the content or of who wrote it.
    """
    lookup = gh.reread_report_location(
        current.location, content_sha256=current.content_revision,
    )
    if lookup.presence not in _READ_PRESENCES:
        return lookup.presence
    if _settled_as(current) is _records.ReportMode.VERIFY:
        authored = _publishing._trusts_the_author(lookup.found)
        carried = lookup.presence is _pr_reports.ReportPresence.PRESENT
    else:
        authored = _wrote_it_ourselves(gh, lookup.found)
        carried = _renders_as_settled(lookup.found, state, current)
    if not carried or authored is False:
        return _pr_reports.ReportPresence.CHANGED
    if authored is None:
        return _pr_reports.ReportPresence.UNCONFIRMED
    return _pr_reports.ReportPresence.PRESENT


def _settled_as(current: _records.CurrentReport) -> _records.ReportMode:
    """The road a settled report is re-read by, recorded or not.

    A publication only ever lands as a comment, so an unrecorded road is read
    off the location: a description was verified, and a comment is held to the
    rendering -- which a comment that was verified fails, closed.
    """
    if current.mode is not None:
        return current.mode
    if current.location.comment_id is None:
        return _records.ReportMode.VERIFY
    return _records.ReportMode.PUBLISH


def _renders_as_settled(
    found: Any, state: PinnedState, current: _records.CurrentReport,
) -> bool:
    """Whether what stands at a published location is the report that settled.

    A comment, re-rendering exactly as a report, whose header and text digest
    are the settlement's own. Who wrote it is `_wrote_it_ourselves`'s question.
    """
    if current.location.comment_id is None:
        return False
    published = _reports.developer_report_from_comment(found, bot_login=None)
    return published is not None and (
        published.pr_number,
        published.source_sha,
        published.requirements_revision,
        published.report_revision,
        published.receipt,
        _reports.content_digest(published.text),
    ) == (
        current.subject.pr_number,
        current.subject.source_sha,
        current.subject.requirements_revision,
        current.report_revision,
        getattr(_settlement.read_handoff(state), "receipt", None),
        current.content_revision,
    )


def _wrote_it_ourselves(gh: GitHubClient, found: Any) -> bool | None:
    """Whether a published report is still this orchestrator's, or None unread.

    Ours by the login the client posts under, not by the allowlist: a
    deployment that lists its humans there need not list its own bot. A client
    with no login of its own has only the trust rule to hold an author to.
    None is an author nobody could read, which is not a stranger's.
    """
    bot_login = getattr(gh, "_bot_login", None)
    if bot_login is None:
        return _publishing._trusts_the_author(found)
    try:
        return _trust.authored_by_us(found, bot_login=bot_login)
    except Exception:
        log.exception("the author of a published developer report would not read")
        return None
