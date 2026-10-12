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

The notice and the event are each said once per landed head, though the
announcement mark lands only behind them (`announces`), and each is
recovered on its own. The pull request's conversation is read first, and a
comment of ours already announcing the head -- one an earlier finish posted
before its checkpoint was refused, went unconfirmed, or the process died -- is
that notice made: entered in the ledger and not posted again. The event
is recorded on the attempt in a write of its own right behind it
(`pending_auto_base_rebase_announced_event`, `rewrite_finish_writes.ANNOUNCED_EVENT`):
a finish finding that record files nothing again, and one finding none files
the event -- a finish lost after its notice and before its event included --
unless the event stream itself already carries a `base_rebased` for the head
(`github.events.filed`: the client's in-memory tail, or the audit log's), a
process lost between filing the event and recording it, which it records
rather than files again. A conversation nobody could read, or a post that
raised and is not found on the conversation read again, holds the finish with
nothing filed, for the next tick to ask again. A notice that lands enters the
ledger of this orchestrator's comments on the state the caller stages, so the
write that records the announcement carries it.

A landed head whose configured verification failed is said once more, and
ahead of its announcement (`failure`): the finish's evidence step records and
posts that notice before the landing is announced, so the failing command, how
it failed, and the tail of what it printed -- worded as the approval's own
verify gate words a failure (`stages/validating/verify.py`) -- stay actionable
on the pull request although nothing records them as evidence. That notice is
not best effort: it is recorded before it is posted and neither the
announcement nor the route goes on until the pull request carries it
(`rewrite_finish_failures`); only its wording is here.
"""
from __future__ import annotations

import copy
import logging
from dataclasses import replace

from orchestrator.git.base_sync import state as _base_sync_state
from orchestrator.git.verification.models import VerifyResult
from orchestrator.github import comments as _github_comments, events as _github_events
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    comments as _comments,
    messages as _messages,
    pinned_commit as _commit,
    rewrite_finish_writes as _writes,
)
from orchestrator.workflow.engine.rewrite_finish_models import FinishOutcome, FinishRoad, LandedFinish
from orchestrator.workflow.stages.validating import verify as _verify
from orchestrator.workflow.state import WorkflowLabel, stage_name

log = logging.getLogger("orchestrator.workflow")

# How much of a commit id a notice names.
_SHORT_SHA = 8

# How every road's announcement of a landing opens.
_ANNOUNCES = ":mag:"

# The attempt's record of the `base_rebased` event a finish filed for its head.
_FILED = _base_sync_state._PENDING_ANNOUNCED_EVENT

_REBASED = "base_rebased"


def method(finish: LandedFinish) -> str:
    """How the landed head reached its finish, as the `base_rebased` event names it."""
    if not finish.pushed:
        return "crash_recovery_relabel_only"
    if finish.road is FinishRoad.PUBLICATION:
        return "auto_clean_rebase"
    return "crash_recovery_pushed"


def announces(finish: LandedFinish, staged: PinnedState) -> FinishOutcome | None:
    """Say `finish`'s landing once -- its notice, then its `base_rebased` event; None to land the checkpoint.

    The notice's comment is recorded on `staged`, the state the announcement
    write is made from, whether this tick posted it or found an earlier
    finish's on the conversation (`_found`) -- which is that notice made, so
    it is not posted again. The event is filed unless the attempt records it
    filed (`_files`). HELD, with nothing filed, where the conversation would
    not read, or where the post raised and the conversation read again does
    not show it; the outcome of the event's record where that did not land.
    """
    readable, found = _found(finish)
    if readable and found is None:
        try:
            _comments._post_pr_comment(finish.gh, finish.pr_number, staged, notice(finish))
        except Exception:
            log.exception(
                "issue=#%s could not post the notice of its landed base rewrite to PR #%s",
                finish.issue.number, finish.pr_number,
            )
            readable, found = _found(finish)
            if found is None:
                return FinishOutcome.HELD
            _comments._track_orchestrator_comment(staged, found)
        return _files(finish, staged)
    if not readable:
        return FinishOutcome.HELD
    _comments._track_orchestrator_comment(staged, found)
    log.info(
        "issue=#%d finds the notice of its landed base rewrite of %.8s already on PR #%d; not posting it again",
        finish.issue.number, finish.head, finish.pr_number,
    )
    return _files(finish, staged)


def _files(finish: LandedFinish, staged: PinnedState) -> FinishOutcome | None:
    """File `finish`'s `base_rebased` event once, recorded on the attempt right behind it; None to go on.

    The event reports the round the reviewer is asked to spend afresh on the
    landed head, which every finish resets. An attempt already recording it
    filed for this head files nothing again, and neither does one whose event
    the stream already carries for the head (`github.events.filed`) -- a
    process lost between filing it and recording it -- which is recorded now.
    The record lands in a write of its own (`rewrite_finish_writes.ANNOUNCED_EVENT`)
    before anything else is asked; the tick's state and `staged`, the
    checkpoint's own, take in that record and nothing else the write read, so
    the checkpoint behind it is still decided on every other record as the
    tick read it. A record that did not land is where the finish stops.
    """
    if finish.state.get(_FILED) == finish.head:
        log.info(
            "issue=#%d finds the base_rebased event of %.8s already filed; not filing it again",
            finish.issue.number, finish.head,
        )
        return None
    if _github_events.filed(finish.gh, _REBASED, issue_number=finish.issue.number, sha=finish.head):
        log.info(
            "issue=#%d finds the base_rebased event of %.8s on the event stream; recording it, filing nothing",
            finish.issue.number, finish.head,
        )
    else:
        finish.gh.emit_event(
            _REBASED,
            issue_number=finish.issue.number,
            stage=stage_name(finish.label),
            pr_number=finish.pr_number,
            sha=finish.head,
            method=method(finish),
            review_round=0,
            retry_count=finish.state.get("retry_count"),
        )
    # Landed over a copy of the tick's state, so the tick takes in the record
    # alone: every other field it was decided on stays as the tick read it,
    # and a move another road made before the record still refuses the
    # checkpoint behind it.
    held = copy.deepcopy(finish.state)
    recorded = _writes.staging(finish)
    recorded.set(_FILED, finish.head)
    stopped = _writes.lands(replace(finish, state=held), recorded, _writes.ANNOUNCED_EVENT)
    finish.state.withheld = finish.state.withheld or held.withheld
    if stopped is None:
        finish.state.set(_FILED, finish.head)
        _commit.takes_in(finish.state, {_FILED: finish.head}, (_FILED,))
        staged.set(_FILED, finish.head)
    return stopped


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


def failure(finish: LandedFinish, run: VerifyResult) -> str:
    """The pull-request notice of the configured verification `finish`'s landed head failed.

    The output is quoted exactly as the runner left it, redacted and then
    truncated, since redacting a tail again cannot catch a secret the cut
    split. No evidence is recorded for the head, so the fresh reviewer it is
    routed to runs the verification itself.
    """
    short_head = finish.head[:_SHORT_SHA]
    said = (
        ":x: The configured verification failed on the rebased head "
        f"`{short_head}`: {_verify._verify_failure_detail(run)}. Nothing is recorded "
        f"as verification evidence for it; routing to `{WorkflowLabel.VALIDATING}`, where the "
        "fresh reviewer runs the verification itself."
    )
    output = (run.output or "").rstrip()
    if not output:
        return said
    return f"{said}\n\n_Verify output (tail):_\n\n{_messages._as_blockquote(output)}"


def _found(finish: LandedFinish) -> tuple[bool, int | None]:
    """Whether `finish`'s pull-request conversation read, and the id of a comment of ours announcing its head on it.

    An announcement is a comment of this orchestrator's -- its author held to
    this deployment (`github.comments.authored_by_us`), since text on a public
    thread is trivially copied -- opening as every road's notice opens and
    naming the landed head as every road's notice names it, whichever road's
    wording it carries.
    """
    gh = finish.gh
    try:
        thread = gh.pr_conversation_thread(gh.get_pr(finish.pr_number))
    except Exception:
        log.exception(
            "issue=#%d could not read PR #%d for an announcement of its landed base rewrite of %.8s",
            finish.issue.number, finish.pr_number, finish.head,
        )
        return False, None
    short_head = finish.head[:_SHORT_SHA]
    named = f"`{short_head}`"
    announced = (
        posted.id for posted in thread
        if (posted.body or "").startswith(_ANNOUNCES) and named in posted.body
        and _github_comments.authored_by_us(posted, bot_login=getattr(gh, "_bot_login", None))
    )
    return True, next(announced, None)


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
