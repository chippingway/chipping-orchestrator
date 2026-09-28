# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The report a head this stage rewrote is owed, recorded once its push is proved.

A clean rebase, a rebase the dev finished by resolving its conflicts, and
commits an earlier tick left unpushed each move the pull request onto a commit
no developer report is about: the conflict prompt asks the agent for none, and
the report the issue last settled names the head the push replaced. Handed to
`validating` as they stand, the reviewer road refuses that report and parks for
a human whose reply only restarts a report of a commit this orchestrator made.
So each records the report debt (`workflow/engine/report_rewrite_debt.py`), and
the validating hold asks the developer for that report with nobody involved.

What names the rewrite is the code-publication receipt and nothing else. The
size gate writes it in the durable write that records the push -- the commit
that reached the remote, the head it replaced, and the pull request it went
onto -- so it proves the head is this stage's publication over the head the
push was leased against, where the caller's own readings would only claim it.
One naming another commit, another pull request, or no head replaced proves no
rewrite and records none, and the reviewer road then holds the report it finds
to the head -- which is the refusal a head nobody proved is owed.

The receipt says the same on the tick that pushed and on one a crash or an
adjudication sent back here, but only a receipt the tick KNOWS to be about a
rewrite of this stage's may be read that way. A round that finished leaves the
settled-round receipt beside it, which brings the next tick back through the
tail. A recovered push that lands still behind base finishes no round, so it
hands the gate the head it publishes instead (`conflict_preamble_sha`), in the
same write that carries the receipt on landing and the one a hold makes ahead
of its relabel. The next tick records the debt from it once the receipt names
that head and the pull request still stands on it, and drops it either way
once the receipt names it: a head the pull request has since left is owed
nothing.

The debt goes down in a write of its own, ahead of the relabel, because the
label is what hands the head on: a process ending between the two would leave
`validating` with a rewritten head and no debt behind it, and the reviewer
road would park for the very report the debt exists to fetch. A write that
would change nothing is not made. For the same reason a proved debt the
pinned comment has no ROOM for holds the handoff: that is not a head nobody
proved, which the reviewer road answers, but a debt this stage owes and could
not write down -- so the round parks and every later tick tries the write
again before anything else, handing the round on once it fits.
"""
from __future__ import annotations

import logging

from orchestrator.git.worktrees import naming as _naming
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import report_rewrite_debt as _rewrite_debt
from orchestrator.workflow.late_split import formats as _formats, payloads as _payloads
from orchestrator.workflow.stages.conflicts import (
    models as _models,
    parks as _conflict_parks,
    state as _state,
)
from orchestrator.workflow.stages.implementing import (
    late_gate_models as _late_gate_models,
    late_publication_state as _late_publication_state,
)

log = logging.getLogger("orchestrator.workflow")


def _owes_the_preamble(sha: str):
    """What a recovered push that precedes a rebase hands the gate to write down.

    The head it publishes and nothing else. It closes no round -- the rebase
    behind it owns that -- but the head is on the pull request once the push
    lands, and the gate's write is the only one a crash after it cannot take.
    Written on a hold too, ahead of the relabel, where the adjudication may
    publish the head long after this tick; until a receipt names it the field
    asserts nothing.
    """
    return _late_gate_models._Spends(fields=((_state._PREAMBLE_SHA, sha),))


def _records_the_owed_preamble(ctx: _models._ConflictContext, tip: str) -> bool:
    """Record the debt a published preamble's own write left owed; False where its handoff has to wait.

    `tip` is the head the pull request was just fetched standing on. Nothing
    is done until the publication receipt names the preamble's head: before
    that the push has not landed, or is still the adjudication's. Once it
    does, the debt is recorded where the pull request still stands on that
    head and the field dropped with it -- or dropped alone where somebody has
    since moved the pull request off it, since that head is owed nothing.
    """
    owed = _payloads.as_hex(ctx.state.get(_state._PREAMBLE_SHA), _formats.COMMIT_LENGTHS)
    if not owed or _late_publication_state._published_commit(ctx.state) != owed:
        return True
    if tip == owed:
        return _records_the_rewrite(ctx, owed)
    log.info(
        "issue=#%d resolving_conflict: PR #%s has moved off %s, which an "
        "earlier push published; it owes that head no report",
        ctx.issue.number, ctx.state.get("pr_number"), owed[:8],
    )
    ctx.state.set(_state._PREAMBLE_SHA, None)
    ctx.gh.write_pinned_state(ctx.issue, ctx.state)
    return True


def _records_the_rewrite(ctx: _models._ConflictContext, sha: str) -> bool:
    """Make durable the report debt a push of `sha` leaves; False where the handoff has to wait.

    Carried through the retargeting the debt owner owns, so a second rewrite
    of the head a standing debt names moves it onto `sha` and keeps the head
    the settled report is about. A standing claim this rewrite cannot extend
    -- one nobody can read, or one about a head somebody else pushed -- is
    left exactly as it is, and so is a receipt that proves no rewrite: both
    let the round go on, and the reviewer road holds the report it finds to
    the head. A proved debt the comment has no room for does not: the round
    parks, and the caller stops.

    A preamble head still standing on the comment goes once the debt is down:
    this push is the one the pull request carries now, and any head that field
    names is either this one or one the pull request never received.
    """
    before = dict(ctx.state.data)
    if not _stages_the_rewrite(ctx, sha):
        return False
    if ctx.state.get(_state._PREAMBLE_SHA) is not None:
        ctx.state.set(_state._PREAMBLE_SHA, None)
    if ctx.state.data != before:
        ctx.gh.write_pinned_state(ctx.issue, ctx.state)
    return True


def _stages_the_rewrite(ctx: _models._ConflictContext, sha: str) -> bool:
    """Stage the debt the receipt proves a push of `sha` left; False where it parked for want of room."""
    rewrite = _published_rewrite(ctx, sha)
    if rewrite is None:
        log.warning(
            "issue=#%d resolving_conflict: the code-publication receipt does "
            "not prove %s a rewrite this stage published; recording no "
            "report debt for it", ctx.issue.number, sha or "an unnamed head",
        )
        return True
    if _rewrite_debt.records_rewrite(ctx.state, rewrite):
        log.info(
            "issue=#%d resolving_conflict: PR #%d stands on %s, rewritten from "
            "%s; it is owed a report of that head",
            ctx.issue.number, rewrite.pr_number, sha[:8], rewrite.previous_head[:8],
        )
        return True
    if _outgrows_the_comment(ctx.state, rewrite):
        _conflict_parks._park_unrecorded_debt(ctx, sha, rewrite.previous_head)
        return False
    log.warning(
        "issue=#%d resolving_conflict: the report debt standing on PR #%d "
        "cannot be carried onto %s; leaving it as it is",
        ctx.issue.number, rewrite.pr_number, sha,
    )
    return True


def _outgrows_the_comment(state: PinnedState, rewrite: _rewrite_debt.RewriteDebt) -> bool:
    """Whether the debt owner refused `rewrite` for nothing but the comment's room.

    Asked once it has refused. Its other refusals are answered here as
    themselves -- a record that would not read back as written, a standing
    claim nobody can read, and one this rewrite cannot extend -- so whatever
    is left is the room the comment has. A refusal this reading does not know
    is answered as room too, which holds the handoff rather than letting a
    proved rewrite through without its debt.
    """
    if _rewrite_debt.RewriteDebt.read(rewrite.recorded()) != rewrite:
        return False
    if not _rewrite_debt.carries_rewrite_debt(state):
        return True
    standing = _rewrite_debt.read_rewrite_debt(state)
    return standing is not None and standing.retargeted(state, rewrite) is not None


def _published_rewrite(
    ctx: _models._ConflictContext, sha: str,
) -> _rewrite_debt.RewriteDebt | None:
    """The rewrite the code-publication receipt proves this stage published as `sha`, or None.

    All three members, each read fail-closed: the commit has to be `sha`, the
    pull request the one the issue pins, and the head it replaced a whole
    commit id -- the head the push was leased against, which is the head the
    settled report is about when the report follows the pull request. The
    branch is the one every push of this stage resolves, which is the branch a
    report subject names.
    """
    state = ctx.state
    number = _late_publication_state._recorded_pull_request(state)
    previous = _late_publication_state._published_lease(state)
    proved = (
        sha,
        number,
        previous,
        _late_publication_state._published_commit(state) == sha,
        _late_publication_state._published_pull_request(state) == number,
    )
    if not all(proved):
        return None
    return _rewrite_debt.RewriteDebt(
        pr_number=number,
        branch=_naming._resolve_branch_name(state, ctx.spec, ctx.issue.number),
        previous_head=previous,
        rewritten_head=sha,
    )
