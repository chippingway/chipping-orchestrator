# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Restore held pull-request descriptions and settle displaced hold targets.

Only an exact cycle-owned hold is restored. A failed restoration of an
open pull request refuses the handoff to a different publication target.
"""
from __future__ import annotations

import logging
from dataclasses import replace

from github.Issue import Issue

from orchestrator.github.client import GitHubClient
from orchestrator.workflow.late_split.models import LateGeneration
from orchestrator.workflow.stages.decomposition import (
    late_hold_reading as _late_hold_reading,
    late_hold_text as _late_hold_text,
)
from orchestrator.workflow.stages.decomposition.late_models import (
    _HeldPr,
    _HeldPrHold,
)

log = logging.getLogger("orchestrator.workflow")


_OPEN_PR_STATE = "open"


def _stale_hold(generation: LateGeneration) -> bool:
    """Whether the recorded hold marks a pull request this record has left.

    One record says it: a publication entry naming a pull request the hold
    does not. That entry is the gate's own proof of which change the candidate
    is measured against, so a hold standing anywhere else is marking a change
    nothing is adjudicating -- and, worse, leaving the one that IS adjudicated
    open with nothing on it saying so.

    `pr_number` moving is deliberately NOT this answer. It names whichever
    pull request the issue currently records rather than the change under
    adjudication, and a hold that chased it would come off a pull request over
    a pointer somebody re-aimed.
    """
    if generation.plan_pr_number is None or generation.plan_pr_body is None:
        return False
    if not generation.publication.is_complete:
        return False
    return generation.publication.published_pr_number != generation.plan_pr_number


def _settled_stale_hold(
    gh: GitHubClient, issue: Issue, generation: LateGeneration,
) -> LateGeneration | None:
    """Release a hold this record has moved off, or refuse to move it.

    Returns the record with the hold's slot free where there was nothing to
    settle or the release landed, and None where it did not -- which parks the
    caller, since the alternative is a second hold taken over the only copy of
    the first one's description.

    The slot is cleared in memory and not written on its own. What persists it
    is the capture of the NEW hold, one write carrying all three fields, so no
    tick is ever left reading a record that has forgotten both. A crash before
    that write leaves the old identity standing over a description already put
    back, which the next tick releases again for nothing: the body is no
    longer this cycle's hold, so the release reports nothing and the migration
    runs on.
    """
    if not _stale_hold(generation):
        return generation
    log.info(
        "issue=#%d holds PR #%d while its publication entry names PR #%d; "
        "restoring the first before marking the second",
        issue.number,
        generation.plan_pr_number,
        generation.publication.published_pr_number,
    )
    release = _release_hold(gh, issue, generation)
    if release.failed:
        return None
    return replace(
        release.generation,
        plan_pr_number=None,
        plan_pr_head="",
        plan_pr_body=None,
    )


def _release_hold(
    gh: GitHubClient, issue: Issue, generation: LateGeneration,
) -> _HeldPrHold:
    """Take this generation's hold off the PR it marked, if it still is.

    Which pull request is asked is the generation's own record, not whichever
    one the issue currently points at: the hold was taken on exactly the
    pull request `plan_pr_number` names, the body beside it is the only copy
    of the description that hold displaced, and a `pr_number` the issue has
    since been re-pointed at is a different change nothing here marked.

    Neither provenance nor the recorded head is re-asked. Provenance decided
    whether the description could be replaced, and it was decided on the
    snapshot that was replaced; asking again means a human pushing onto the
    branch while the adjudication ran would leave the "do not merge" notice
    standing forever on a pull request nothing is adjudicating any more. The
    head is that argument one field over: it says which change wore the
    notice, never whose the words under it are. What proves the current text
    is this generation's to overwrite is the marker in it, which is a fact
    about the body rather than about the head above it.

    Only a REUSABLE pull request can hold the caller up. `failed` is what
    parks it, and what parking is for is a change a human can still merge
    while it wears a "do not merge" notice this generation put there -- which
    is a description of an OPEN pull request and of no other kind. One a human
    has already merged or closed is settled, so its description is tidied on a
    best-effort basis and an edit GitHub refuses is logged and stepped over
    rather than being allowed to hold an accepted candidate back for good. A
    pull request that could not be read at all fails closed with the open
    ones: what could not be read might be open.

    Everything else leaves the generation exactly as it arrived with nothing
    touched -- nothing recorded, a body somebody rewrote while the hold stood,
    and one already released, since a preserved copy that is no longer what
    the description says is stale and a human's own words are not this
    generation's to replace.
    """
    pr_number = generation.plan_pr_number
    if pr_number is None or generation.plan_pr_body is None:
        return _HeldPrHold(generation=generation)
    held_pr = _late_hold_reading._readable_held_pr(gh, issue, pr_number)
    if held_pr is None:
        return _late_hold_reading._refused(generation)
    if not _late_hold_text._wears_our_hold(generation, held_pr.body):
        log.info(
            "issue=#%d PR #%d does not carry this cycle's hold "
            "verbatim; leaving its description alone",
            issue.number, pr_number,
        )
        return _HeldPrHold(generation=generation)
    return _restored_body(gh, issue, generation, held_pr)


def _restored_body(
    gh: GitHubClient,
    issue: Issue,
    generation: LateGeneration,
    held_pr: _HeldPr,
) -> _HeldPrHold:
    """Write the preserved description back, and say whether it had to land.

    The reusability of the pull request is what decides that, and it is read
    off the same snapshot the edit is made against. A refused edit on an open
    one is a hold still standing on a change somebody can merge, so the caller
    parks; a refused edit on one already merged or closed is untidy and
    nothing more, so the accepted candidate goes on publishing.
    """
    reusable = held_pr.pr_state == _OPEN_PR_STATE
    try:
        gh.edit_pr_body(held_pr.pull_request, generation.plan_pr_body)
    except Exception:
        log.exception(
            "issue=#%d could not restore the description of PR #%d "
            "(state=%s)",
            issue.number, held_pr.number, held_pr.pr_state,
        )
        return _HeldPrHold(generation=generation, failed=reusable)
    return _HeldPrHold(generation=generation)
