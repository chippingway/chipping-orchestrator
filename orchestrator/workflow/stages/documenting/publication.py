# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a docs pass leaves on the PR, and the order it is written in.

Both surviving outcomes end the same way -- a completion lands straight into
`in_review`, its final head verified and recorded apart from the approval it
followed (`final_completion`): stamp the watermarks, post the notice, hand
off. A pass that published a docs commit is verified on that commit
(`final_completion._completes_published`); one that published nothing leaves
the pull request on the head the approval moved here, and the evidence that
approval rests on is proved to still answer for it first (`retention`), the
completion then naming that evidence as retained
(`final_completion._completes_unchanged`) and decided on every record that
proof read as well. Neither is a review: no report is asked for, no review
round spent, and no reviewer launched. The push comes first and gates
everything after it. A failed push parks instead of advancing, because a
stamp over a commit that never reached the remote would tell the next tick
the docs are published when a human asked to merge would never see them in
the diff. That is also why a `DOCS: NO_CHANGE` verdict over a recovered
commit still routes through the push path rather than the clean one.

`docs_checked_sha` records the head the verdict was formed against and the
silent-park counter is reset alongside it, so a park streak that predates a
successful pass cannot later rotate a healthy session. What this owner decides
is which head the stamp names, which verdict it carries, and what the notice
says. The order the stamp, the notice, its write, and the relabel go out in,
what a write that is refused or never confirmed stops, and the notice being
best-effort -- a comment failure must not strand an issue whose branch is
already published -- are the completion's own.

The receipt the gate leaves (`docs_settled_sha`), and the lease beside it
naming the head the pass was entered on, are what a later tick finishes a
published pass's completion from (`owed_completion`).

Ahead of all of it, `subject` gives the docs commit its pull request's
reference, and the id that hands back is the only one anything past it names:
an amendment is a NEW commit, so an id taken before it would name a commit the
branch no longer carries.
"""
from __future__ import annotations

from orchestrator import config
from orchestrator.workflow.engine import messages as _messages
from orchestrator.workflow.stages.documenting import (
    final_completion as _final_completion,
    models as _models,
    parks as _parks,
    retention as _retention,
    state as _state,
    subject as _subject,
)
from orchestrator.workflow.stages.implementing import (
    late_gate_models as _late_gate_models,
    late_push as _late_push,
    late_records as _late_records,
)

# What a `DOCS: NO_CHANGE` verdict tells the pull request, with the agent's own
# justification quoted under it where it supplied one.
_NO_CHANGE_NOTICE = (
    ":books: documenting pass: no docs changes required.\n\n{justification}"
)


def _push_docs_and_advance(
    ctx: _models._DocumentingContext,
    wt,
    after_sha: str,
    notice: str,
    entered_head: str = "",
) -> None:
    """Push docs commit(s), verify the head that went out, and complete the pass into `in_review`.

    On push failure, park with `push_failed` instead of advancing. On
    success, hand the commit that went out to its completion
    (`final_completion._completes_published`), which verifies that commit,
    records the completion apart from the approval, stamps
    `docs_checked_sha`, posts `notice` on the PR, and routes to `in_review`
    behind a write that landed. Writes pinned state; the caller returns
    unconditionally.

    A docs commit is a candidate for a pull request the remote already carries
    like any other, so the size gate stands in front of this push too. It is
    the last one before a human is asked to merge, which is what makes it
    matter rather than what makes it an exception: a pass that took the diff
    past the ceiling would put an unadjudicated pull request in front of the
    person who merges it. A held candidate ends the tick -- the gate has
    parked the issue or handed it to the adjudication, and the completion
    below would move it off the state the gate just set -- but the
    pass itself is over, so the head it produced is handed to the gate as the
    receipt this stage is owed. Written inside the gate's routed write, ahead
    of the relabel, the resumed tick below reads it back and finishes the
    handoff; without it that tick would find a branch in sync with its remote,
    read it as an issue no docs pass has run for, and spawn a second one over
    a commit the first pass already published.

    The same receipt covers the push that was ALLOWED, because the gate writes
    it whichever way the answer went -- so a push that landed and a process
    that died before this stage could record it comes back to a receipt naming
    the published commit rather than to a pass nothing remembers. The head
    the push replaces rides beside it (`docs_settled_lease`), since that is
    the head the pass was entered on, which its completion records and the
    ready ping proves the approved commit links to; the code-publication
    receipt's own lease is rewritten by any later republication -- a recovery
    pushing the docs commit over itself among them.

    Every one of those ids is the commit `subject._referenced_docs_commit`
    hands back before the gate is entered, `docs_checked_sha` among them: under
    `PR_REF_IN_SUBJECT` the record is re-anchored on that commit, so a hold, a
    failed push, and a receipt each go down naming what this pass publishes.
    With the switch off the anchor is the head the pass began at, which is what
    every road that publishes a subject as it was written records.
    """
    candidate = _subject._referenced_docs_commit(ctx, wt, after_sha)
    if candidate is None:
        return
    anchored = ctx.state.get(_state._CHECKED_DOCS_SHA)
    if config.PR_REF_IN_SUBJECT:
        # What this pass publishes is the commit `subject` handed back, and
        # every write from here down carries the record as it stands: the
        # gate's own routed write for a held candidate, the approval a push
        # that fails leaves for the retry, and the receipt a landed one rides.
        # Anchored anywhere else -- on the head the pass began at, or on
        # whatever an earlier one left where this road anchors nothing of its
        # own -- each of those goes down naming a commit the rest of the record
        # does not describe. Asked of the switch rather than of the id, since a
        # subject that needed no amendment is published by the head already
        # read and has to be named by the record just the same. The stamp below
        # writes the same id again, so a pass that gets that far agrees with
        # what a hold already said.
        ctx.state.set(_state._CHECKED_DOCS_SHA, candidate)
    published = _late_push._publishes(
        _late_records._gate(ctx.gh, ctx.spec, ctx.issue, ctx.state, wt),
        ctx.branch,
        _late_gate_models._Entered(
            # The commit this pass made, as its subject was amended above, so
            # the gate measures and pushes THAT rather than whatever the
            # checkout became between the two reads -- which the stamp below
            # would then record as documented.
            candidate=candidate,
            # The head the pull request was standing on before the pass ran.
            # Left for the gate to read afterwards, a pull request somebody
            # pushed to while the agent was out becomes the lease and this
            # force-push drops it -- the last push before a human is asked to
            # merge, so what it would drop is what that human would not see.
            head=entered_head,
            # The receipt the completion is owed, and the head this push
            # replaces, which that completion records as the head the pass was
            # entered on: the code-publication receipt's own lease is
            # rewritten by any later republication, the docs commit's over
            # itself included.
            spends=_late_gate_models._Spends(fields=(
                (_state._SETTLED_DOCS_SHA, candidate),
                (_state._SETTLED_DOCS_LEASE, _entered_lease(ctx, entered_head)),
            )),
        ),
    )
    if published.held:
        if ctx.state.get(_state._SETTLED_DOCS_SHA) != candidate:
            # A hold is two states wearing one answer. Where the gate ROUTED
            # this candidate it left the receipt naming it, and the record
            # describes a commit an adjudication still publishes. Where it
            # REFUSED instead -- a tree it could not prove, a pull request
            # nobody could read, a checkout standing somewhere else -- nothing
            # was measured, recorded, or published, so the head the pass was
            # anchored on before it ran goes back rather than the pass claiming
            # one it never put anywhere.
            ctx.state.set(_state._CHECKED_DOCS_SHA, anchored)
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
    _final_completion._completes_published(ctx, candidate, notice)


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
    the human asked to merge would never see the docs in the diff -- so push
    it via the updated path, which verifies and completes it like any
    published docs commit. That is a publication, so the evidence shortcut
    below is never its to take.

    Otherwise the head is the one the approval moved here, and the
    verification evidence that approval rests on is proved to still answer
    for it first (`retention._retains`), behind the completion's watermark
    walk, which it takes, so no request of the pull request comes between
    that proof and the writes it licenses: proved, the clean no-change
    verdict against the evaluated head goes to the completion, which records
    that evidence as the one the unchanged head rests on and lands it --
    decided as well on every record that proof read -- and advances
    (`final_completion._completes_unchanged`). A proof that refused --
    missing evidence included -- withholds the handoff, invalidates the
    evidence, and hands the issue back to `validating`; one nobody could take
    holds it. Writes pinned state; the caller returns unconditionally.
    """
    if run.ahead > 0:
        _push_docs_and_advance(
            ctx, wt, after_sha,
            ":books: documenting pass: pushed recovered docs "
            "commit(s) after no-change confirmation.",
            entered_head=run.entered_head,
        )
        return
    notice = _NO_CHANGE_NOTICE.format(
        # Quoted where the agent supplied a justification, so the PR carries
        # the reasoning rather than only the verdict.
        justification=_messages._as_blockquote(body.strip()) if body.strip()
        else "",
    ).rstrip()
    if ctx.state.get(_state._SETTLED_DOCS_SHA) == after_sha:
        # The head is a docs commit this approval's pass already published,
        # and the resumed pass found nothing to add to it: it is completed as
        # the publication it is, verified on its own head.
        _final_completion._completes_published(ctx, after_sha, notice)
        return
    if not _retention._retains(ctx, after_sha):
        return
    # Persist the SHA the dev evaluated even on a "nothing changed" outcome.
    # The fresh-spawn and awaiting-human resume shapes both write
    # `docs_checked_sha = before_sha` BEFORE the spawn (so a no-change outcome
    # there leaves it correct); setting it here too makes the post-condition
    # explicit and covers any future entry path that bypasses them.
    # `after_sha == before_sha` in this branch by construction (no commit).
    _final_completion._completes_unchanged(ctx, after_sha, notice)


def _entered_lease(ctx: _models._DocumentingContext, entered_head: str) -> str:
    """The head the pass whose commit replaces `entered_head` was entered on, which the docs receipt's lease records.

    Ordinarily `entered_head` itself. Where the docs receipt still standing
    names `entered_head` -- this approval's pass published that docs commit,
    and its run did not pass, so the pass resumed over it -- the pass was
    entered on the head that receipt's lease names, which is what its
    completion links to the approved commit; the push itself is still leased
    against `entered_head`.
    """
    standing = ctx.state.get(_state._SETTLED_DOCS_LEASE)
    if entered_head and ctx.state.get(_state._SETTLED_DOCS_SHA) == entered_head and standing:
        return standing
    return entered_head


def _documenting_commit_notice(recovered: bool) -> str:
    """The `:books:` push notice, distinguishing a recovered commit from a
    fresh docs commit."""
    if recovered:
        return ":books: documenting pass: pushed recovered docs commit(s)."
    return ":books: documenting pass: pushed docs commit."
