# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The report a rewritten head is owed, asked for and settled with no human.

A rewrite this orchestrator published -- a rebase, a conflict resolution, or
commits an earlier tick left unpushed -- leaves the pull request on a commit the
settled report is not about (`report_rewrite_debt`), and the reviewer road
would refuse that report and park for a human whose reply only restarts a
report of a commit this orchestrator made itself. So the report hold asks here
once no other report is owed, ahead of every reviewer, and this owner either
releases the review or asks the developer for the report itself.

Either answer is about requirements, so the requirements are read first. The
baseline the drift check proved is what a paying report has to answer and what
a fresh one is stamped with, and the drift check stands down for an edit behind
a reviewer round it owes, or a reply with words that bought one. Such a change
is one no settled report has seen, so paying on it would clear the debt over a
report of the requirements before it, and asking for a report now would stamp
one with requirements the issue no longer has. Both hold instead, with the note
the drift check stood down for dropped, and the next tick's drift resume
answers the change -- its own report of this head pays the debt, and after an
`ACK:` the next refresh asks under the new baseline.

A settled report pays the debt where it is about the head the pull request
stands on, was published as a report of its own, and answers the requirements
the issue carries now -- and only once it still reads intact where it
settled, since a claim dropped over a report somebody edited away would hand
the reviewer road nothing to stop on. Dropped, the reviewer runs on that tick.
A report the thread has moved out of reach pays nothing and holds nothing: the
reviewer road parks for it exactly as it would with no debt at all.

Where the debt is instead owed a fresh report (`RewriteDebt.owes_a_refresh`),
the developer is resumed on a prompt asking for that report alone. So it is
where the settled report is of the approved commit this orchestrator's
approval squash collapsed into the head the debt replaced -- of neither head
the debt names, so owed nothing on its own -- but only once that lineage is
proved (`report_squash_lineage`) and the report re-reads intact at its
location, and only against the requirements the issue carries now. That report
is left as it is: it still names the commit it was written about. A lineage
nothing proves, a report moved out of reach, and requirements that moved leave
it to the reviewer road's refusal, and a tree or location nobody could read
holds with nobody run. Both are owed only on the branch the issue pins now:
the resume runs in that branch's checkout and the report it writes is bound
there, so a debt the pin has moved off is left to the reviewer road's refusal
rather than answered with a report the pull request would never settle.

Either refresh runs only over a world frozen first. The code-publication
receipt has to be sound as a whole and name the rewritten head, since the
report is bound to the publication it names and the reconciliation that settles
it only holds, with nobody told, over a receipt group it cannot read. And the
checkout has to stand on that head, clean, since the report describes what it
holds: the one the resume will run in, inspected where it stands and recreated
only where it is gone, because the recreation reclaims an existing directory
with no commits past the base, loose work and all. A reading nobody could take
holds; a definite refusal parks for a human under `report_undeliverable`, as
the hold does, before any agent runs. What the run leaves is read by
`report_refresh_outcomes`, over the same world read again.

A run nothing launched, one a shutdown interrupted, and one a live pause
stopped write nothing, and the next tick asks again. Every other run ends the
tick, even one whose report settles: the next tick finds it paid and runs the
reviewer, so one tick never spends two agents.
"""
from __future__ import annotations

import logging

from github.Issue import Issue

from orchestrator.config import models as _config_models
from orchestrator.git.worktrees import naming as _naming
from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    drift as _drift,
    guards as _guards,
    prompt_delivery as _prompt_delivery,
    prompts as _prompts,
    report_rewrite_debt as _rewrite_debt,
    report_squash_lineage as _squash_lineage,
    usage as _usage,
)
from orchestrator.workflow.stages.implementing import (
    late_receipt_damage as _receipt_damage,
    resume as _dev_resume,
    worktree as _resume_worktree,
)
from orchestrator.workflow.stages.validating import (
    report_refresh_models as _models,
    report_refresh_outcomes as _outcomes,
    report_settlement as _settlement,
    review_report as _review_report,
    state as _validating_state,
)

log = logging.getLogger("orchestrator.workflow")

_DAMAGED_RECEIPT = (
    "the code-publication receipt cannot be read (`{member}`), so no report of "
    "`{head}`, the head this orchestrator rewrote the pull request onto, can be "
    "settled onto it -- repair that field on the pinned comment before you reply"
)

_UNRECEIPTED = (
    "the code-publication receipt does not name `{head}`, the head this "
    "orchestrator rewrote the pull request onto, so no report of it can be "
    "bound to the pull request"
)

_UNFROZEN = (
    "the checkout cannot be frozen on `{head}`, the head this orchestrator "
    "rewrote the pull request onto: {detail}"
)


def _rewrite_holds_the_review(
    gh: GitHubClient,
    spec: _config_models.RepoSpec,
    issue: Issue,
    state: PinnedState,
) -> bool:
    """Pay a rewritten head's report debt, or hold the reviewer while its report is asked for.

    The pull request's head is read the way the reviewer's subject reads it,
    and a head nobody could read holds, since the next tick is as likely to
    read it. What that head's claim is owed is `_answers_the_debt`'s.
    """
    if not _rewrite_debt.carries_rewrite_debt(state):
        return False
    head = _review_report._pull_request_head(gh, issue, _rewrite_debt.pinned_pull_request(state))
    if head is None:
        return True
    return _answers_the_debt(gh, spec, issue, state, head)


def _answers_the_debt(
    gh: GitHubClient,
    spec: _config_models.RepoSpec,
    issue: Issue,
    state: PinnedState,
    head: str,
) -> bool:
    """Drop the debt the settled report pays, or refresh the report it is owed; whether the review is held.

    A claim neither paid nor owed a refresh of `head` -- one nobody can read,
    one on another branch than the issue pins, another pull request or branch
    than the settled report's, a head somebody else pushed, a settled report
    of neither head the claim names -- holds nothing here: the reviewer road
    holds the report it finds to the head, and parks for one that is not
    about it. The one settled report of neither head that is owed a refresh is
    the approved commit an approval squash collapsed, and only once that is
    proved (`_refreshes_a_squashed_report`). Either of the other two waits
    first for requirements the drift check stood down for
    (`_waits_for_the_drift_road`).
    """
    debt = _rewrite_debt.read_rewrite_debt(state)
    pinned_branch = _naming._resolve_branch_name(state, spec, issue.number)
    if debt is not None and debt.branch != pinned_branch:
        # The resume runs in the pinned branch's checkout and the report it
        # writes is bound to that branch, which a debt the pin moved off is
        # not about.
        debt = None
    paying = _rewrite_debt.pays_the_debt(state, head)
    if not paying and (debt is None or not debt.owes_a_refresh(state, head)):
        squashed = debt is not None and debt.owes_a_refresh(state, head, squashed=True)
        return squashed and _refreshes_a_squashed_report(gh, spec, issue, state, debt)
    if _waits_for_the_drift_road(gh, issue, state):
        return True
    if paying:
        return _pays_the_debt(gh, issue, state, head)
    _refreshes_the_report(_models._ReportRefresh(
        gh, spec, issue, state, debt,
        requirements=str(state.get(_prompt_delivery.PINNED_USER_CONTENT_HASH) or ""),
    ))
    return True


def _waits_for_the_drift_road(
    gh: GitHubClient, issue: Issue, state: PinnedState,
) -> bool:
    """Hold for requirements the drift check stood down for, dropping the note it stood down for.

    The note is what makes the drift check stand down, and the change is what
    has to be answered before any report pays for this head or is asked about
    it -- dropped, the next tick's drift resume answers it.
    """
    if _drift._detect_user_content_change(gh, issue, state) is None:
        return False
    _validating_state._discharges_the_owed_round(state)
    gh.write_pinned_state(issue, state)
    log.info(
        "issue=#%d requirements moved past the baseline a report of its "
        "rewritten head answers; holding for the drift road", issue.number,
    )
    return True


def _pays_the_debt(
    gh: GitHubClient, issue: Issue, state: PinnedState, head: str,
) -> bool:
    """Drop a debt the settled report pays once it reads intact where it settled; whether the review is held.

    The re-read is the one the reviewer road takes of the report it hands
    over, so a location nobody could read holds for the next tick, and a report
    the thread moved out of reach -- edited, removed, or out of step with its
    handoff -- holds nothing and is left to that road's refusal, with the debt
    standing behind it. The write that drops the debt goes out before the
    reviewer road, so no road behind it reads the paid claim back.
    """
    report, refusal = _review_report._settled_report(
        gh, state, _rewrite_debt.pinned_pull_request(state),
    )
    if report is None:
        return not refusal
    _rewrite_debt.drops_rewrite_debt(state)
    gh.write_pinned_state(issue, state)
    log.info(
        "issue=#%d settled a report of its pull request's head %s; its "
        "rewrite's report debt is paid", issue.number, head[:8],
    )
    return False


def _refreshes_a_squashed_report(
    gh: GitHubClient,
    spec: _config_models.RepoSpec,
    issue: Issue,
    state: PinnedState,
    debt: _rewrite_debt.RewriteDebt,
) -> bool:
    """Refresh the report a proved approval squash leaves owed; whether the review is held.

    Asked of a debt owed a refresh only should the squash be proved: the
    settled report is of a commit the debt never names, so the squash's
    lineage is what links it to the debt. PROVED asks for a fresh report of
    the head the debt published, with the settled report left as it is. A
    lineage nothing proves holds nothing, and the reviewer road refuses the
    stale report as it always did; a tree nobody could read holds with nobody
    run, since the next tick is as likely to read it. Then the drift wait
    every refresh takes, and then the settled report is re-read at its
    location as the reviewer road reads it, since the proof was taken off the
    pinned record alone: a report the thread moved out of reach is left to
    that road's refusal, and a location nobody could read holds.
    """
    proof = _squash_lineage.lineage_verdict(spec, issue.number, state, debt.rewritten_head)
    if not proof.proved:
        if proof.holds:
            log.info(
                "issue=#%d could not read its approval squash's lineage: %s; "
                "holding the review", issue.number, proof.refusal,
            )
        return proof.holds
    if _waits_for_the_drift_road(gh, issue, state):
        return True
    report, refusal = _review_report._settled_report(
        gh, state, _rewrite_debt.pinned_pull_request(state),
    )
    if report is None:
        return not refusal
    _refreshes_the_report(_models._ReportRefresh(
        gh, spec, issue, state, debt,
        requirements=str(state.get(_prompt_delivery.PINNED_USER_CONTENT_HASH) or ""),
        approved=report.source_sha,
    ))
    return True


def _refreshes_the_report(refresh: _models._ReportRefresh) -> None:
    """Ask the developer for a fresh report of the rewritten head, over a world frozen first.

    A refusal parks before anything runs; a reading nobody could take holds.
    """
    refusal = _frozen_refusal(refresh)
    if refusal:
        refresh.parks(refusal)
    if refusal != "":
        return
    log.info(
        "issue=#%d PR #%d stands on %s, which this orchestrator rewrote from "
        "%s; asking the developer for a report of it",
        refresh.issue.number, refresh.debt.pr_number, refresh.head[:8],
        refresh.debt.previous_head[:8],
    )
    worktree, agent_result, paused = _dev_resume._resume_dev_with_text(
        refresh.gh, refresh.spec, refresh.issue, refresh.state,
        _prompts._build_report_refresh_prompt(
            refresh.issue, refresh.debt.previous_head, refresh.head, refresh.approved,
        ),
        pause_guard=True,
    )
    if _guards._ignore_if_never_invoked(refresh.issue, agent_result) or paused:
        return
    if _guards._ignore_if_interrupted(refresh.issue, agent_result):
        return
    refresh.state.set("last_agent_action_at", _usage._now_iso())
    _outcomes._disposes_the_refresh(refresh, worktree, agent_result)


def _frozen_refusal(refresh: _models._ReportRefresh) -> str | None:
    """Why the report cannot be asked about the rewritten head: "" where it can, None where unread.

    The receipt first, whole and then by the commit it names, since it costs
    no request. Then the checkout the resume will run in, reused where it
    stands -- a clean tree is proved there, not assumed of a directory put back
    in its place.
    """
    damaged = _receipt_damage._damaged_receipt(refresh.state)
    if damaged:
        return _DAMAGED_RECEIPT.format(member=damaged, head=refresh.head)
    if _settlement._receipt_commit(refresh.state) != refresh.head:
        return _UNRECEIPTED.format(head=refresh.head)
    worktree = _resume_worktree._ensure_resume_worktree(
        refresh.spec, refresh.issue, refresh.state,
    )
    detail = _outcomes._checkout_refusal(worktree, refresh.head)
    if detail:
        return _UNFROZEN.format(head=refresh.head, detail=detail)
    return detail
