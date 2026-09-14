# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a docs pass leaves on the PR, and the order it is written in.

Both surviving outcomes end the same way -- stamp the watermarks, post the
notice, hand off -- but the push comes first and gates everything after it. A
failed push parks instead of advancing, because a `docs_verdict` stamped over
a commit that never reached the remote would tell the next tick the docs are
published when the reviewer would never see them in the diff. That is also why
a `DOCS: NO_CHANGE` verdict over a recovered commit still routes through the
push path rather than the clean one.

`docs_checked_sha` records the head the verdict was formed against and the
silent-park counter is reset alongside it, so a park streak that predates a
successful pass cannot later rotate a healthy session. The PR notice itself is
best-effort: a comment failure must not strand an issue whose branch is already
published and whose state is already stamped.

Every terminal success ends the same way too, and the order is the whole of the
crash contract: stamp, announce, persist, relabel -- one durable write, and the
relabel behind it. The notice comes before the write because posting one
RECORDS it: the comment id lands in `orchestrator_comment_ids`, which is what
keeps the watermark walk and the in_review feedback scan from reading our own
post as human feedback, and there is nothing behind the write to carry it. The
write comes before the relabel because `in_review` repairs nothing it is
handed: relabelled first, a crash in between leaves the merge gate reading the
head the pass BEGAN on and a verdict nobody wrote, on a stage whose own handler
never looks at either.

Two windows are left and both fail toward doing the work again rather than
skipping it. A tick that posted its notice and died over the write comes back
with nothing on the record saying so, and the tick that finishes the handoff
from the receipt announces it a second time. And a tick whose relabel did not
land comes back to a pass this write already called finished, with the receipt
it dropped: nothing tells that state from a `validating` approval handing the
same head back, so the pass runs again rather than handing off on a receipt
that could belong to either.
"""
from __future__ import annotations

import logging

from orchestrator import config
from orchestrator.git.measurement import commits as _measurement_commits
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import comments as _comments, messages as _messages
from orchestrator.workflow.late_split import (
    formats as _formats,
    payloads as _payloads,
)
from orchestrator.workflow.stages.documenting import (
    handoff as _handoff,
    models as _models,
    parks as _parks,
    state as _state,
)
from orchestrator.workflow.stages.implementing import (
    late_gate_models as _late_gate_models,
    late_push as _late_push,
    late_records as _late_records,
)

log = logging.getLogger("orchestrator.workflow")


# The revision a checkout's own head is named by.
_HEAD = "HEAD"


# What a `DOCS: NO_CHANGE` verdict tells the pull request, with the agent's own
# justification quoted under it where it supplied one.
_NO_CHANGE_NOTICE = (
    ":books: documenting pass: no docs changes required.\n\n{justification}"
)


def _stamp_docs_verdict(
    state: PinnedState, checked_sha: str, verdict: str,
) -> None:
    """Stamp the docs watermarks after a terminal success: record the
    evaluated head, the verdict (`updated` / `no_change`), and reset the
    silent-park counter.

    The receipt is dropped in the same breath, and it has to be: it says a
    published pass still owes a handoff, and this write is what records that
    pass as finished. Held past this write to cover the relabel behind it, it
    outlives the handoff whenever the write that would have dropped it does
    not land -- and the state that leaves is indistinguishable from the one a
    failed relabel leaves, since both carry the same commit, the same verdict,
    and the same head. A later `validating` approval at that same head then
    reads it as a pass still pending, skips the docs pass the approval just
    bought, and hands the issue to `in_review` a second time. Between two
    readings nothing can tell apart, running the pass is the safe one.
    """
    state.set("docs_checked_sha", checked_sha)
    state.set("docs_verdict", verdict)
    state.set("silent_park_count", 0)
    state.set(_state._SETTLED_DOCS_SHA, None)


def _post_docs_notice(ctx: _models._DocumentingContext, note: str) -> None:
    """Post a docs-pass notice on the PR, best-effort (a comment failure must
    not block the handoff)."""
    try:
        _comments._post_pr_comment(ctx.gh, int(ctx.pr_number), ctx.state, note)
    except Exception:
        log.exception(
            "issue=#%s could not post docs notice to PR #%s",
            ctx.issue.number, ctx.pr_number,
        )


def _push_docs_and_advance(
    ctx: _models._DocumentingContext,
    wt,
    after_sha: str,
    notice: str,
    entered_head: str = "",
) -> None:
    """Push docs commit(s) and hand off to `in_review`.

    On push failure, park with `push_failed` instead of advancing. On
    success, stamp the docs watermarks (`docs_checked_sha`,
    `docs_verdict=updated`), post `notice` on the PR, and route to
    `in_review`. Writes pinned state; the caller returns unconditionally.

    A docs commit is a candidate for a pull request the remote already carries
    like any other, so the size gate stands in front of this push too. It is
    the last one before a human is asked to merge, which is what makes it
    matter rather than what makes it an exception: a pass that took the diff
    past the ceiling would put an unadjudicated pull request in front of the
    person who merges it. A held candidate ends the tick -- the gate has
    parked the issue or handed it to the adjudication, and the `in_review`
    handoff below would move it off the state the gate just set -- but the
    pass itself is over, so the head it produced is handed to the gate as the
    receipt this stage is owed. Written inside the gate's routed write, ahead
    of the relabel, the resumed tick below reads it back and finishes the
    handoff; without it that tick would find a branch in sync with its remote,
    read it as an issue no docs pass has run for, and spawn a second one over
    a commit the first pass already published.

    The same receipt covers the push that was ALLOWED, because the gate writes
    it whichever way the answer went -- so a push that landed and a process
    that died before this stage could record it comes back to a receipt naming
    the published commit rather than to a pass nothing remembers.
    """
    published = _late_push._publishes(
        _late_records._gate(ctx.gh, ctx.spec, ctx.issue, ctx.state, wt),
        ctx.branch,
        _late_gate_models._Entered(
            # The commit this pass made, so the gate measures and pushes THAT
            # rather than whatever the checkout became between the two reads
            # -- which the stamp below would then record as documented.
            candidate=after_sha,
            # The head the pull request was standing on before the pass ran.
            # Left for the gate to read afterwards, a pull request somebody
            # pushed to while the agent was out becomes the lease and this
            # force-push drops it -- the last push before a human is asked to
            # merge, so what it would drop is what that human would not see.
            head=entered_head,
            spends=_late_gate_models._Spends(fields=(
                (_state._SETTLED_DOCS_SHA, after_sha),
            )),
        ),
    )
    if published.held:
        ctx.gh.write_pinned_state(ctx.issue, ctx.state)
        return
    if not published.landed:
        _parks._park_documenting(
            ctx,
            f"{config.HITL_MENTIONS} git push failed; see "
            "orchestrator logs.",
            "push_failed",
        )
        return
    _stamp_docs_verdict(ctx.state, after_sha, "updated")
    _post_docs_notice(ctx, notice)
    _handoff._advance_after_docs_push(ctx.gh, ctx.issue, ctx.state)


_SETTLED_DOCS_NOTICE = (
    ":books: documenting pass: docs commit `{commit}` is already on this pull "
    "request; this tick finished the handoff it was still owed. No second "
    "pass was run."
)


def _finished_settled_docs(
    ctx: _models._DocumentingContext, wt, ahead: int,
) -> bool:
    """Finish a docs pass whose commit the pull request already carries.

    The receipt says the pass is over: an agent ran, it committed, and the
    only thing left between that commit and `in_review` is the handoff. The
    gate HELD the commit, and an authorized settlement publishes it from the
    adjudication and hands the label back here. Or the gate ALLOWED the push,
    it landed, and the tick died before this stage could record it -- the
    receipt goes down in the gate's own write either way, which is ahead of
    everything this stage does with a landed push.

    It is the write that RECORDS the pass which drops it, so a receipt read
    here is one no handoff has been made for. Kept past that write to cover
    the relabel behind it as well, it would outlive the handoff whenever the
    write that dropped it did not land -- and a later approval at that same
    head would consume it, skipping the docs pass it just bought.

    Running the docs agent again instead of finishing from a live receipt
    would commit a second time over work that is already published, which the
    gate would measure and could route to an adjudication.

    `ahead` is what says the commit reached the remote, and it is asked
    because the receipt cannot: a verdict that parked, or a human who moved
    the label by hand, leaves the same receipt over a commit still on disk
    only. Ahead of the remote the receipt is left exactly where it is and the
    recovered-commit path below republishes it through the gate, which is the
    one road that measures it again.

    In sync is not the same claim as CARRYING it. A replacement host rebuilds
    the checkout from a pull request that has moved on, and what it gets is a
    branch level with its remote and standing on somebody else's head -- so
    the receipt is proved against the commit the checkout is on, not merely
    against the counters. That proof carries the remote with it: the caller
    fetched the branch before counting and parks a checkout behind it, so a
    head that is in sync AND is the settled commit says the remote is
    standing there too.

    Fail closed on every other reading. A receipt that is not a whole object
    id is not one a checkout can be compared to, and a head this host cannot
    peel is not one anything may be compared against -- both leave the
    receipt exactly where it is for a tick that can prove it.
    """
    settled = _payloads.as_hex(
        ctx.state.get(_state._SETTLED_DOCS_SHA), _formats.COMMIT_LENGTHS,
    )
    if not settled or ahead > 0 or not _standing_on(wt, settled):
        return False
    _stamp_docs_verdict(ctx.state, settled, "updated")
    _post_docs_notice(ctx, _SETTLED_DOCS_NOTICE.format(commit=settled))
    _handoff._advance_after_docs_push(ctx.gh, ctx.issue, ctx.state)
    return True


def _standing_on(wt, settled: str) -> bool:
    """Whether this checkout is the commit a settled receipt names.

    Proved rather than read, because everything past it is a claim about one
    object id: a revision this host cannot peel is not a head that matches
    anything, and a host that never had the commit answers exactly that.
    """
    proved = _measurement_commits._prove_candidate_commit(wt, _HEAD)
    if proved.is_frozen and proved.sha == settled:
        return True
    log.error(
        "the checkout at %s stands on %s rather than the settled docs commit "
        "%s; leaving the receipt for a tick that can prove it",
        wt, proved.sha or "an unreadable head", settled,
    )
    return False


def _route_documenting_no_change(
    ctx: _models._DocumentingContext,
    wt,
    run: _models._DocumentingRun,
    after_sha: str,
    body: str,
) -> None:
    """Route a `DOCS: NO_CHANGE` verdict to `in_review`.

    A recovered local commit (`ahead > 0`) that the resumed dev added
    nothing to must still reach the remote before advancing -- otherwise
    the reviewer agent at validating would never see the docs in the diff
    -- so push it via the updated path. Otherwise persist the clean
    no-change verdict against the evaluated head and advance. Writes
    pinned state; the caller returns unconditionally.
    """
    if run.ahead > 0:
        _push_docs_and_advance(
            ctx, wt, after_sha,
            ":books: documenting pass: pushed recovered docs "
            "commit(s) after no-change confirmation.",
            entered_head=run.entered_head,
        )
        return
    # Persist the SHA the dev evaluated even on a "nothing changed" outcome.
    # The fresh-spawn and awaiting-human resume shapes both write
    # `docs_checked_sha = before_sha` BEFORE the spawn (so a no-change outcome
    # there leaves it correct); setting it here too makes the post-condition
    # explicit and covers any future entry path that bypasses them.
    # `after_sha == before_sha` in this branch by construction (no commit).
    _stamp_docs_verdict(ctx.state, after_sha, "no_change")
    _post_docs_notice(ctx, _NO_CHANGE_NOTICE.format(
        # Quoted where the agent supplied a justification, so the PR carries
        # the reasoning rather than only the verdict.
        justification=_messages._as_blockquote(body.strip()) if body.strip()
        else "",
    ).rstrip())
    _handoff._advance_after_docs_no_change(ctx.gh, ctx.issue, ctx.state)


def _documenting_commit_notice(recovered: bool) -> str:
    """The `:books:` push notice, distinguishing a recovered commit from a
    fresh docs commit."""
    if recovered:
        return ":books: documenting pass: pushed recovered docs commit(s)."
    return ":books: documenting pass: pushed docs commit."
