# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a landed base rewrite's finish says about it: the pull-request notice and the `base_rebased` event.

Said once per publication, by whichever finish first gets that far, and the
announcement mark the finish writes behind them is what keeps a later one from
saying it again (`rewrite_finish`). What is said depends on whose push put
the remote where it stands. The tick that published its own rebase reports
how far the pull request was behind the base and the head it now stands on,
and a recovery the head it pushed again. A head this tick sent nothing for --
one a recovery observed, or a publication refused because the remote already
stood on it, whichever road reached it -- is reported as already published.
Both recovery notices say whether the base has advanced past that head since,
in which case another rebase comes first. The texts and the event's payload
are the ones every finish has always produced, and live issues and the
analytics sink already carry them, so each road's are spelled here exactly as
they always have been.

The notice is best effort: a post that fails is logged, and the publication it
was about is recorded all the same. A post that lands enters the ledger of
this orchestrator's comments on the state the caller stages, so the write that
records the announcement carries it.
"""
from __future__ import annotations

import logging

from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import comments as _comments
from orchestrator.workflow.engine.rewrite_finish_models import FinishRoad, LandedFinish
from orchestrator.workflow.state import WorkflowLabel, stage_name

log = logging.getLogger("orchestrator.workflow")

# How much of a commit id a notice names.
_SHORT_SHA = 8


def method(finish: LandedFinish) -> str:
    """How the landed head reached its finish, as the `base_rebased` event names it."""
    if not finish.pushed:
        return "crash_recovery_relabel_only"
    if finish.road is FinishRoad.PUBLICATION:
        return "auto_clean_rebase"
    return "crash_recovery_pushed"


def announces(finish: LandedFinish, staged: PinnedState) -> None:
    """Post the notice of `finish`'s landing and emit its `base_rebased` event.

    The notice's comment is recorded on `staged`, the state the announcement
    write is made from. The event reports the round the reviewer is asked to
    spend afresh on the landed head, which every finish resets.
    """
    try:
        _comments._post_pr_comment(finish.gh, finish.pr_number, staged, notice(finish))
    except Exception:
        log.exception(
            "issue=#%s could not post the notice of its landed base rewrite to PR #%s",
            finish.issue.number, finish.pr_number,
        )
    finish.gh.emit_event(
        "base_rebased",
        issue_number=finish.issue.number,
        stage=stage_name(finish.label),
        pr_number=finish.pr_number,
        sha=finish.head,
        method=method(finish),
        review_round=0,
        retry_count=finish.state.get("retry_count"),
    )


def notice(finish: LandedFinish) -> str:
    """The pull-request notice `finish`'s landing is announced with."""
    if finish.pushed and finish.road is FinishRoad.PUBLICATION:
        return _published(finish)
    short_head = finish.head[:_SHORT_SHA]
    if finish.pushed:
        said = (
            f":mag: Recovered an interrupted auto-rebase for PR #{finish.pr_number}; "
            f"pushed the recovered head `{short_head}`."
        )
        current = f"{said} Routing `{finish.label}` -> `{WorkflowLabel.VALIDATING}`."
    else:
        said = (
            f":mag: Recovered an interrupted auto-rebase for PR #{finish.pr_number}; "
            f"the new head `{short_head}` was already published before the orchestrator restart."
        )
        current = (
            f"{said} Routing `{finish.label}` -> `{WorkflowLabel.VALIDATING}` "
            "so the reviewer re-runs against the rewritten branch."
        )
    if not finish.behind:
        return current
    return (
        f"{said} Base advanced again by {finish.behind} commit(s) since the interrupted "
        f"rebase; rebasing once more before routing to `{WorkflowLabel.VALIDATING}`."
    )


def _published(finish: LandedFinish) -> str:
    """The notice of a rebase this tick published itself, which routes it to review."""
    spec = finish.spec
    short_head = finish.head[:_SHORT_SHA]
    return (
        f":mag: PR was {finish.lag} commit(s) behind `{spec.remote_name}/{spec.base_branch}`; "
        "orchestrator auto-rebased the branch and re-pushed it. "
        f"Routing `{finish.label}` -> `{WorkflowLabel.VALIDATING}` so the reviewer re-runs "
        f"against the new head (`{short_head}`)."
    )
