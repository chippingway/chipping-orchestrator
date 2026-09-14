# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What the humans did with the plan, read off the pull request carrying it.

Three answers come back, and the two terminal ones share the tail every other
stage's terminals use -- the timestamp, the label, the usage receipt before the
write, the event, and the close -- because a discussion that finished is
finished the same way a review that finished is. A merged plan PR is the humans
agreeing to the design, which is `done`; one closed without merging is them
declining it, which is `rejected`. Both name `discussion` as the stage, since
that is the label the issue is sitting on and what an audit row has to
attribute the run to.

An OPEN one is the third answer, and it decides nothing. It changes nothing --
no label, no write, no comment -- and, crucially, it takes nothing down: the
worktree and the branches the plan lives on are what the pull request is open
against, and reaping them while a human is still reading the plan would close
their review out from under them. That holds whether or not the ISSUE is still
open, which is why a closed issue is handed here too rather than finalized on
the close.

A pull request that could not be fetched is that same hold: nothing is decided
on a read that failed, and the tick after this one asks again. What it must
never do is fall through, since "GitHub declined once" would otherwise open a
round on a design that has already been agreed.

Both callers in `terminal` reach the same finalize, and they bring different
amounts of the question with them. One hands over a number the publication
wrote down, and everything that number turns out to be is decided here. The
other recovered a number from a publication that opened a pull request and died
before recording it, and holds on its own for an open one and for a lookup
nobody could take -- so only a DECIDED pull request ever arrives from that side.
It writes the number to pinned state before handing it over, since the tail
below reads the number, and the branch it reaps, off that record.
"""
from __future__ import annotations

import logging

from orchestrator.workflow.engine import (
    terminal_context as _terminal_context,
    terminal_effects as _terminal_effects,
)
from orchestrator.workflow.stages.discussion import models as _models, state as _state

log = logging.getLogger("orchestrator.workflow")

# What `pr_state` calls a plan the humans took, and one they turned down.
# Anything else is a design still being read, which is neither.
_MERGED_PR_STATE = "merged"

_CLOSED_PR_STATE = "closed"

_MERGE_CLOSE_ERROR = "could not close after the plan PR merged"


def _drain_plan_pr(run: _models._DiscussionRun) -> bool:
    """Finalize on what the plan PR has become, or hold the tick where it is.

    Always True: whatever the pull request turns out to be, the conversation
    that produced it does not get another round. What varies is only whether
    this tick is also the one that writes the ending.
    """
    plan_pr = _plan_pr(run)
    if plan_pr is not None:
        _finalize_by_pr_state(run, plan_pr)
    return True


def _plan_pr(run: _models._DiscussionRun) -> object | None:
    """The pull request the plan was published on, or None having said why not.

    None is a read that did not happen rather than a pull request that is not
    there: the number was recorded by the publication in the same write as the
    plan path, so the only way this fails is GitHub declining to answer. The
    caller holds the tick on it, since every ending below the fetch is a claim
    about a pull request nobody could look at.
    """
    pr_number = int(run.state.get(_state._PR_NUMBER))
    try:
        return run.gh.get_pr(pr_number)
    except Exception:
        log.exception(
            "issue=#%s could not fetch plan PR #%d; holding the discussion "
            "until it can be read", run.issue.number, pr_number,
        )
        return None


def _finalize_by_pr_state(run: _models._DiscussionRun, plan_pr) -> None:
    """Take the terminal arc the humans' verdict on this pull request names.

    An open one names neither, and falls through changing nothing -- which is
    what every caller here wants of it, since the design is still being read.
    """
    context = _terminal_context._ReviewTerminalContext(
        gh=run.gh,
        spec=run.spec,
        issue=run.issue,
        state=run.state,
        pr=plan_pr,
        stage=_state._DISCUSSION_STAGE,
    )
    pr_status = run.gh.pr_state(plan_pr)
    if pr_status == _MERGED_PR_STATE:
        _terminal_effects._finalize_merged_pr(
            context,
            close_error=_MERGE_CLOSE_ERROR,
            close_if_open_only=True,
        )
    elif pr_status == _CLOSED_PR_STATE:
        _terminal_effects._finalize_rejected_pr(context)
