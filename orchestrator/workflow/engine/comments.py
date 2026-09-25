# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Issue and pull-request comments stamped and tracked as orchestrator output.

The hidden marker survives eviction from the bounded id ledger. Both identify
our comments without treating a shared token account as exclusively automated.
A developer report carries the marker in its own rendering and enters the
ledger on whichever reading finds it on the thread; a verification artifact
does the same through `verification_comments`, which records into this one.
Callers persist the modified ledger; prompt_context owns trusted thread reads."""
from __future__ import annotations

from github.Issue import Issue
from github.PullRequest import PullRequest

from orchestrator.github import comments as _trust, pull_request_reports as _pr_reports
from orchestrator.github.client import GitHubClient
from orchestrator.github.developer_reports import DeveloperReport
from orchestrator.github.pinned_state import PinnedState

_ORCH_COMMENT_ID_CAP = 500

# The pinned field the comment-id ledger lives in. Named because a caller
# measuring a write it has not made yet has to see what this ledger already
# holds, and a second spelling of the field is a reservation that could be
# reading a different one.
_ORCH_COMMENT_IDS = "orchestrator_comment_ids"

_ORCH_COMMENT_MARKER = _trust.ORCHESTRATOR_COMMENT_MARKER


def _orchestrator_ids(state: PinnedState) -> set[int]:
    """Set of comment ids the orchestrator itself posted on this issue/PR.
    Used to filter the orchestrator's own messages out of "new feedback"
    scans without falling back to author-login matching -- a PAT shared
    with a human reviewer's GitHub account would otherwise have its real
    review comments swallowed as bot noise (and the PR pinged ready for
    human merge over them).
    """
    raw = state.get(_ORCH_COMMENT_IDS) or []
    return {int(comment_id) for comment_id in raw}


def _track_orchestrator_comment(state: PinnedState, comment_id: int) -> None:
    """Record that this orchestrator posted one comment, once.

    Idempotent, because the ledger is a SET of ids kept in a bounded list and
    a second entry for one comment buys nothing while costing a slot. Callers
    layer -- a road that posts through a wrapped client and then through
    `_post_issue_comment` records the same id twice -- so an id already here
    keeps the position it has: what the bound evicts is the oldest comment
    rather than the least recently re-recorded.
    """
    raw = state.get(_ORCH_COMMENT_IDS)
    ids = list(raw) if isinstance(raw, list) else []
    identified = int(comment_id)
    if identified in ids:
        return
    ids.append(identified)
    if len(ids) > _ORCH_COMMENT_ID_CAP:
        ids = ids[-_ORCH_COMMENT_ID_CAP:]
    state.set(_ORCH_COMMENT_IDS, ids)


def _reserve_comment_slot(state: PinnedState, widest: int) -> None:
    """Reserve what recording one more comment will cost this ledger.

    For a caller MEASURING a write that has not happened yet, rather than one
    recording a comment that has. Publishing a report records the comment it
    landed as, so a measurement taken before that publication has to carry the
    entry it will add.

    The writer above is idempotent, which is right for it and wrong here: an id
    the ledger already holds reserves nothing at all, and the measurement then
    under-counts by exactly the entry the real publication goes on to add. So
    the id reserved is one this ledger does NOT hold.

    `widest` is the width the caller's domain records an id at, and the search
    walks DOWN from it. A real comment id is never wider, so the entry reserved
    is never narrower than the one that lands; and the walk is bounded by the
    entries this ledger carries, which the cap above bounds in turn, so it
    stays at that width and ends within a step per entry.
    """
    raw = state.get(_ORCH_COMMENT_IDS)
    held = {
        entry for entry in raw if isinstance(entry, int)
    } if isinstance(raw, list) else set()
    reserved = widest
    while reserved in held:
        reserved -= 1
    _track_orchestrator_comment(state, reserved)


def _with_orch_marker(body: str) -> str:
    """Append the hidden orchestrator-comment marker to `body` (idempotent).

    Every orchestrator-posted comment carries this marker so the
    user-content hash can identify bot comments even after their id has
    been evicted from the bounded `orchestrator_comment_ids` cap. The
    marker is an HTML comment, invisible in rendered Markdown.
    """
    if _ORCH_COMMENT_MARKER in body:
        return body
    return f"{body}\n\n{_ORCH_COMMENT_MARKER}"


def _post_issue_comment(
    gh: GitHubClient, issue: Issue, state: PinnedState, body: str,
):
    """Post an issue comment AND record its id in pinned state so future
    `_handle_in_review` ticks recognize it as orchestrator-authored even when
    the PAT login is shared with a human reviewer. Caller is still responsible
    for `gh.write_pinned_state` -- this only mutates the in-memory state.

    The body is augmented with `_ORCH_COMMENT_MARKER` so the user-content
    hash can identify bot comments by marker (id-cap-resistant) in
    addition to by id (works for tracked-and-not-yet-evicted comments).
    """
    issue_comment = gh.comment(issue, _with_orch_marker(body))
    cid = getattr(issue_comment, "id", None)
    if cid is not None:
        _track_orchestrator_comment(state, int(cid))
    return issue_comment


def _post_pr_comment(
    gh: GitHubClient, pr_number: int, state: PinnedState, body: str,
):
    """PR-conversation comment counterpart to `_post_issue_comment`. Both
    surfaces share the IssueComment id namespace, so a single id list covers
    them. Inline review comments and PR review summaries live in different id
    spaces but the orchestrator never posts to those, so they need no entry.

    The body is augmented with `_ORCH_COMMENT_MARKER` for the same reason
    as `_post_issue_comment`: the user-content hash needs to identify
    bot comments even after their id has been evicted from the bounded
    `orchestrator_comment_ids` cap. PR-conversation comments do not feed
    into `_compute_user_content_hash` directly (the hash reads
    `issue.get_comments()`, not the PR's), but marker symmetry across
    surfaces keeps the filter rules uniform and avoids accidental
    inconsistency when a future tweak does start reading PR comments.
    """
    pr_comment = gh.pr_comment(pr_number, _with_orch_marker(body))
    cid = getattr(pr_comment, "id", None)
    if cid is not None:
        _track_orchestrator_comment(state, int(cid))
    return pr_comment


def _publish_developer_report(
    gh: GitHubClient, pr: PullRequest, state: PinnedState, report: DeveloperReport,
) -> _pr_reports.ReportLookup:
    """Publish one developer report onto `pr` and record its comment as ours.

    Recorded whenever the reading shows the report on the thread, not only
    after the post that made it. A post whose response was lost hands back no
    id, so the retry that finds the comment an earlier attempt landed is the
    ledger's one chance to learn it; readings after that add nothing, since
    recording an id twice keeps one entry. Caller is still responsible for
    `gh.write_pinned_state`.

    The marker is not appended here: the report's own rendering carries it,
    because that rendering is what a retry compares byte for byte.

    The id is read off the LOOKUP rather than off the object it carries. That
    read is a request on a worker holding an uncompleted object, and this runs
    inside a dispatch guard where one that raised would leave by an exception
    rather than by an answer -- out of the tick entirely. It happens here,
    before the caller ever sees the reading, so a boundary the caller put
    around its own read would be the second one and this the raise.
    """
    lookup = gh.publish_developer_report(pr, report)
    posted_id = lookup.landed_id
    if lookup.presence is _pr_reports.ReportPresence.PRESENT and posted_id is not None:
        _track_orchestrator_comment(state, posted_id)
    return lookup
