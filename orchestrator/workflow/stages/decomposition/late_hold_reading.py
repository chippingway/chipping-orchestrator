# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Choose and read the pull request a late candidate may hold.

A recorded hold outranks publication context, which outranks the issue
pointer. Only that last path requires discussion-plan provenance, and an
unreadable pull request supplies no permission to edit its description.
"""
from __future__ import annotations

import logging

from github.Issue import Issue

from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.late_split import formats as _formats, payloads as _payloads
from orchestrator.workflow.late_split.models import LateGeneration
from orchestrator.workflow.stages.decomposition.late_models import (
    _HeldPr,
    _HeldPrHold,
)
from orchestrator.workflow.stages.implementing import handler as _implementing

log = logging.getLogger("orchestrator.workflow")


# Whichever pull request this issue currently records. Shared with every other
# stage that reads it, and it names a plan only sometimes -- which is why the
# provenance beside it decides whether the hold may touch the description. It
# is the last place a target is looked for, since a record naming one of its
# own names it better.
_PR_NUMBER = "pr_number"


def _refused(generation: LateGeneration) -> _HeldPrHold:
    """The answer every refusal here gives: nothing marked, caller parks.

    Spelled once because it is one decision read six ways -- a pull request
    nobody could read, a hold nobody could move, a body nobody could preserve,
    an edit GitHub declined. What follows any of them is an agent started
    against work a human might be looking at through a pull request this
    failed to mark, so all of them stop the tick in exactly the same place.
    """
    return _HeldPrHold(generation=generation, failed=True)


def _hold_subject(
    state: PinnedState, generation: LateGeneration,
) -> int | None:
    """Which pull request this generation's hold is taken on, if any.

    Three sources, in the order each stops being answerable by the one after
    it. A hold already recorded names its own pull request and outranks the
    rest: the preserved body beside that identity is the only copy of a
    description there is, so a tick that went looking for a target instead
    could take a second hold and overwrite it -- which is exactly what an
    issue re-pointed at another change would otherwise arrange. It outranks
    them only because a hold the record has MOVED OFF has already been
    released by the time this is asked, and the slot it held is free. A
    publication entry names the pull request the work is already on, proved
    open by the gate and frozen there because nothing here could re-derive it.
    Failing both, the issue's own record is the only pull request there is,
    and it is the one whose provenance has to be established before a word of
    it is replaced.
    """
    if generation.plan_pr_number is not None and (
        generation.plan_pr_body is not None
    ):
        return generation.plan_pr_number
    if generation.publication.is_complete:
        return generation.publication.published_pr_number
    return _payloads.as_identity(state.get(_PR_NUMBER))


def _may_be_held(
    gh: GitHubClient,
    issue: Issue,
    state: PinnedState,
    generation: LateGeneration,
    held_pr: _HeldPr,
) -> bool:
    """Whether THIS snapshot is a pull request this generation may mark.

    One answer for each way a target is named, and each is settled by the
    record that named it rather than derived a second time. A hold already
    taken is one this generation is entitled to keep: whether the description
    could be replaced was decided on the snapshot that WAS replaced, and
    re-asking would strand a "do not merge" notice on a pull request no retry
    would ever re-apply to and no release could put a body back on. A pull
    request the publication entry names is the one the candidate was measured
    against, which the gate proved open and froze. Anything else is whatever
    the issue currently records, and that has to be shown to be its plan.
    """
    if generation.plan_pr_number == held_pr.number and (
        generation.plan_pr_body is not None
    ):
        return True
    if generation.publication.published_pr_number == held_pr.number and (
        generation.publication.is_complete
    ):
        return True
    return _plan_provenance(gh, issue, state, held_pr)


def _plan_provenance(
    gh: GitHubClient, issue: Issue, state: PinnedState, held_pr: _HeldPr,
) -> bool:
    """Whether THIS snapshot of the recorded pull request is the plan.

    The question only a target taken off `pr_number` has to answer. Read
    through the implementing stage's own answer rather than re-derived, so
    what counts as a plan is decided in one place: while the discussion's
    plan path stands nothing has pushed, and past that handoff the recorded
    plan commit is compared against the pull request's head.

    Asked about the snapshot the hold is holding, which is what removes the
    window between deciding and acting: that owner takes no reading of its
    own, so the head it answers about is the head this hold is holding.
    """
    is_plan = _implementing._recorded_pr_is_the_plan(state, held_pr.head_sha)
    if not is_plan:
        log.info(
            "issue=#%d PR #%d is not this issue's plan; leaving its "
            "description alone",
            issue.number, held_pr.number,
        )
    return bool(is_plan)


def _readable_held_pr(
    gh: GitHubClient, issue: Issue, pr_number: int,
) -> _HeldPr | None:
    """Read the pull request to hold, or None if GitHub could not be asked.

    The fetch and every field the hold decides on are read together, inside
    one guard, because a PyGithub pull request is lazy: `get_pr` asks GitHub
    nothing and the request that can fail is the first attribute read. A guard
    around the fetch alone would catch almost nothing -- the failure would
    land on the head, the state, or the body instead, halfway through deciding
    whether to replace a human's description, and escape as an exception no
    tick could park on.

    Fail closed: a pull request that cannot be read is one the hold cannot be
    proven on, and the alternative to parking is spawning an agent while a
    human still sees an unmarked, apparently-ready change.
    """
    try:
        return _read_held_pr(gh, pr_number)
    except Exception:
        log.exception(
            "issue=#%d could not read PR #%d for the late hold",
            issue.number, pr_number,
        )
        return None


def _read_held_pr(gh: GitHubClient, pr_number: int) -> _HeldPr:
    """Fetch one pull request and read every field a decision is made on.

    Every read is here so every read is inside the caller's guard. The head
    defaults to empty rather than raising on a shape without one, and text
    that is not a whole object id reads as empty too: a head nobody can name
    is not the plan commit either way, and it is not one this domain would
    record, since the pinned write and both sinks take a commit or nothing.
    What must not happen is the read itself escaping, so the shape is answered
    here and the refusal is made where the head is needed -- by the capture,
    which will not take a hold it cannot record a head for, and not by the
    release, which asks the body and never the head above it.
    """
    held_pr = gh.get_pr(pr_number)
    return _HeldPr(
        pull_request=held_pr,
        number=held_pr.number,
        body=held_pr.body or "",
        head_sha=_payloads.as_hex(
            getattr(held_pr.head, "sha", ""), _formats.COMMIT_LENGTHS,
        ) or "",
        pr_state=gh.pr_state(held_pr),
    )
