# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a reused pull request's description says, and who may change it.

`find_open_pr` promises only that something is open on the branch, so the
description under a publication may be this stage's own, an operator's, the
`discussion` stage's plan, or ours re-described by a human. The verdict here is
the report-aware reading of it, taken afresh by number: a description that
closes this issue and names the session stands, and any other holds the work
for a human to name it.

Nothing here WRITES a description. GitHub offers no conditional write for one,
so a body built from a reading -- however fresh, and however carefully it keeps
every word -- goes out in a second request, and an edit somebody saved between
the two is written over with nothing to say it happened. The two lines a
publication needs are therefore quoted in the notice for the one party whose
edit cannot race itself. That covers the description a developer report of this
issue's lives in as well -- delivered, pending, settled, or a record too damaged
to say otherwise -- which is told apart only because the notice has to say so.

`publication` asks it twice: before the report is bound, which is told the
answer, and again last before the handoff, which it withholds on anything short
of True.
"""
from __future__ import annotations

import logging

from github.Issue import Issue

from orchestrator import config
from orchestrator.github import client as _client, pinned_state as _pinned_state
from orchestrator.workflow.engine import (
    report_delivery as _report_delivery,
    report_locations as _report_locations,
)
from orchestrator.workflow.stages.implementing import dev_pr as _dev_pr

log = logging.getLogger("orchestrator.workflow")

# What every notice here ends on: the two lines, quoted for copying, and what
# the reply does. Fenced so the attribution's own backticks survive the copy.
_REPAIR = (
    "Put these two lines at the top of the description, as ordinary text "
    "rather than as code:\n\n```\nResolves #{issue}\n\n{attribution}\n```\n\n"
    "Then reply, and the orchestrator resumes the session; the report it "
    "writes then is the one that gets published."
)

# A description somebody else wrote, which names nothing this issue needs.
_UNNAMED_PARK = (
    "{mentions} PR #{pr}'s description carries no reference closing this issue "
    "and no line naming the session that wrote the branch, so merging it would "
    "close nothing. This orchestrator does not rewrite a description: GitHub "
    "offers no way to write one that cannot overwrite an edit saved a moment "
    "earlier. The branch and the pull request stand as they are, and the work "
    "is held rather than handed to review. "
)

# The same, where a settled report lives in that description.
_CLAIMED_PARK = (
    "{mentions} PR #{pr}'s description is where this issue's developer report "
    "settled, and it carries no reference closing this issue and no line "
    "naming the session that wrote the branch. This orchestrator does not "
    "rewrite a description, a report's least of all, so the work is held "
    "rather than handed to review. Editing it moves that report off the text "
    "it was verified at, which the report the resumed session writes replaces. "
)


def _names_the_implementation(
    gh: _client.GitHubClient,
    issue: Issue,
    state: _pinned_state.PinnedState,
    pr,
) -> bool | None:
    """Whether the pull request's description closes this issue and names it.

    Judged on the description read again by number -- the object in hand is as
    old as whatever fetched it -- and never changed, whatever it says.

    True: it does. False: it does not and a report of this issue's claims it;
    while that report is still owed the binding is what parks the collision,
    and once it has settled no retry frees the description, so it parks here.
    None holds the tick: a description nobody could read, or a repository
    nobody could name for the qualified reference in it, which the next tick
    reads again; or a description nobody claims that names nothing, parked for
    a human.

    The verdict is taken inside the same boundary as the lookup, because the
    lookup asks GitHub nothing: PyGithub hands back a lazy pull request, and
    the request that can fail is the read of its body the verdict makes.
    """
    attribution = _dev_pr._dev_pr_attribution(state)
    try:
        described = _report_locations.describes_the_issue(
            gh.get_pr(pr.number), issue.number, attribution, gh.repo_slug,
        )
    except Exception:
        log.exception(
            "issue=#%s could not re-read PR #%d's description, or the "
            "repository a qualified reference in it has to name; holding "
            "rather than deciding on what nobody read", issue.number, pr.number,
        )
        return None
    if described:
        return True
    claimed = _report_locations.claims_the_description(state, pr.number)
    if claimed and _report_delivery.owes_a_report(state):
        log.warning(
            "issue=#%s has a developer report still owed on PR #%d's "
            "description, which names nothing this issue needs; leaving the "
            "collision to the binding", issue.number, pr.number,
        )
        return False
    log.warning(
        "issue=#%s holds PR #%d for a human: its description does not close "
        "this issue and name the session, and no description is rewritten",
        issue.number, pr.number,
    )
    notice = _CLAIMED_PARK if claimed else _UNNAMED_PARK
    _report_delivery.parks_an_undeliverable_report(
        gh, issue, state, (notice + _REPAIR).format(
            mentions=config.HITL_MENTIONS, pr=pr.number,
            issue=issue.number, attribution=attribution,
        ),
    )
    return False if claimed else None
