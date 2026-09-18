# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a reused pull request's description says, and what may be done to it.

`find_open_pr` promises only that something is open on the branch, so the
description under a publication may be this stage's own, an operator's, the
`discussion` stage's plan, or ours re-described by a human. The verdict here is
the report-aware reading of it: a description that closes this issue and names
the session stands; any other gets those two lines ABOVE it, every word kept
beneath them -- written only while the description still reads as the one that
was judged, so an edit somebody saved in between is judged next rather than
written over. One a developer report of this issue's lives in -- delivered,
pending, settled, or a record too damaged to say otherwise -- is never touched,
since even an edit keeping every word moves it off the digest it was verified
at, and none is cut to make room past what GitHub accepts.

No caller asks it yet: the live reuse still answers through
`dev_pr._attribute_reused_pr`, which knows nothing of reports.
"""
from __future__ import annotations

import logging

from github.Issue import Issue

from orchestrator import config
from orchestrator.agents.models import AgentResult
from orchestrator.github import client as _client, pinned_state as _pinned_state
from orchestrator.workflow.engine import (
    report_delivery as _report_delivery,
    report_locations as _report_locations,
)
from orchestrator.workflow.stages.implementing import dev_pr as _dev_pr

log = logging.getLogger("orchestrator.workflow")

# GitHub holds a pull request's description to the same 65,536 characters it
# holds a comment to, so a description near that ceiling cannot take the two
# lines this implementation needs above it without something being cut.
_TOO_LONG_PARK = (
    "{mentions} PR #{pr}'s description is too long to have this issue's "
    "closing reference and the developer session's attribution put above it: "
    "with them it would be {length} characters, past the {limit} GitHub "
    "accepts, and this orchestrator will not cut what anybody wrote there. The "
    "branch and the pull request stand as they are; the work is held rather "
    "than handed to review, because merging it would close nothing. Shorten "
    "the description, then reply and the orchestrator resumes the session -- "
    "the report it writes then goes out with the description named."
)

# A description a settled report lives in, which names nothing this issue needs.
_CLAIMED_PARK = (
    "{mentions} PR #{pr}'s description is where this issue's developer report "
    "settled, and it carries no reference closing this issue and no line "
    "naming the session that wrote the branch. This orchestrator will not edit "
    "a description a report lives in, so the work is held rather than handed "
    "to review. Reply and the orchestrator resumes the session; once the "
    "report it writes is in a comment, those two lines go above what the "
    "description says, and every word of it is kept."
)


def _names_the_implementation(
    gh: _client.GitHubClient,
    issue: Issue,
    state: _pinned_state.PinnedState,
    agent_result: AgentResult,
    pr,
) -> bool | None:
    """Whether the pull request's description closes this issue and names it.

    Judged on the description read again by number -- the object in hand is as
    old as whatever fetched it -- since `find_open_pr` promises only that
    something is open on the branch: a crashed attempt of ours, an operator's,
    the `discussion` plan PR, or ours re-described by a human.

    True: it already does, and is left alone; or it did not, and has just had
    the two lines put ABOVE it, every word kept. False: a report of this
    issue's claims it, and no edit is safe -- parked where that report settled
    already. None holds the tick: a description nobody could read, one too
    long to take the lines, which parks, and one somebody edited between this
    reading and the write -- the new body was built from words that are no
    longer there, so nothing is written and the next tick judges what is.
    """
    try:
        current = gh.get_pr(pr.number)
    except Exception:
        log.exception(
            "issue=#%s could not re-read PR #%d's description; holding rather "
            "than deciding on one nobody read", issue.number, pr.number,
        )
        return None
    if _report_locations.describes_the_issue(
        current, issue.number, _dev_pr._dev_pr_attribution(state), gh.repo_slug,
    ):
        return True
    if _report_locations.claims_the_description(state, pr.number):
        log.warning(
            "issue=#%s is not editing PR #%d's body: a developer report of this "
            "issue's is published there, and any edit would move it",
            issue.number, pr.number,
        )
        # Owed, the report bound or settled next may free it; with nothing
        # owed, the report that claims it settled already and no retry frees it.
        if not _report_delivery.owes_a_report(state):
            _report_delivery.parks_an_undeliverable_report(
                gh, issue, state, _CLAIMED_PARK.format(
                    mentions=config.HITL_MENTIONS, pr=pr.number,
                ),
            )
        return False
    return _names_it_above(gh, issue, state, agent_result, current)


def _names_it_above(
    gh: _client.GitHubClient,
    issue: Issue,
    state: _pinned_state.PinnedState,
    agent_result: AgentResult,
    current,
) -> bool | None:
    """Put this implementation's lines above a description nobody claims.

    Every word of `current` -- the description as it was just judged -- is kept
    beneath them, so nothing is cut to fit GitHub's ceiling, and nothing is
    written once the description no longer reads as the one the body was built
    from: both hold the tick, the first parked for a human to shorten it.
    """
    described = getattr(current, "body", None)
    named = _dev_pr._build_pr_body(
        state, issue, agent_result,
        described if isinstance(described, str) else "",
    )
    if len(named) > _pinned_state.MAX_PINNED_BODY:
        _report_delivery.parks_an_undeliverable_report(
            gh, issue, state, _TOO_LONG_PARK.format(
                mentions=config.HITL_MENTIONS, pr=current.number,
                length=len(named), limit=_pinned_state.MAX_PINNED_BODY,
            ),
        )
        return None
    if not gh.edit_unchanged_pr_body(current.number, described, named):
        log.warning(
            "issue=#%s is not naming this implementation above PR #%d's "
            "description: it was edited after it was read; holding so the next "
            "tick judges what it says now", issue.number, current.number,
        )
        return None
    log.info(
        "issue=#%s named this implementation above PR #%d's description",
        issue.number, current.number,
    )
    return True
