# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a docs pass leaves on the PR, and the order it is written in.

Both surviving outcomes end the same way -- a completion lands: stamp the
watermarks, post the notice, hand off. A pass that published nothing goes to
`in_review` (`handoff._hand_off_to_in_review`). A pass that published a docs
commit changed the content the approval, its evidence, and the developer
report were about, so it goes back to `validating` for a report of the
published head and a fresh review (`handback._hands_back_for_review`). The
push comes first and gates everything after it. A failed push parks instead
of advancing, because a stamp over a commit that never reached the remote
would tell the next tick the docs are published when the reviewer would never
see them in the diff. That is also why a `DOCS: NO_CHANGE` verdict over a
recovered commit still routes through the push path rather than the clean one.

`docs_checked_sha` records the head the verdict was formed against and the
silent-park counter is reset alongside it, so a park streak that predates a
successful pass cannot later rotate a healthy session. What this owner decides
is which head the stamp names, which verdict it carries, and what the notice
says. The order the stamp, the notice, its write, and the relabel go out in,
what a write that is refused or never confirmed stops, and the notice being
best-effort -- a comment failure must not strand an issue whose branch is
already published -- are the completion's own.

The receipt the gate leaves (`docs_settled_sha`) is what a later tick finishes
a published pass's handoff from, and it is told apart from an unpublished
candidate two ways. Where the code-publication receipt names it as published
on the pinned pull request and no park stands, it is handed back at once, ahead
of the approval it outdated (`_finishes_a_published_pass`): that receipt is the
proof the hand-back's debt is read off. Otherwise by the checkout
(`_finished_settled_docs`): a commit still ahead of the remote is republished
through the gate, and only one the branch is level with AND standing on is
handed off without a second pass.

Ahead of all of it, `subject` gives the docs commit its pull request's
reference, and the id that hands back is the only one anything past it names:
an amendment is a NEW commit, so an id taken before it would name a commit the
branch no longer carries.
"""
from __future__ import annotations

import logging

from orchestrator import config
from orchestrator.git.measurement import commits as _measurement_commits
from orchestrator.workflow.engine import messages as _messages
from orchestrator.workflow.late_split import (
    formats as _formats,
    payloads as _payloads,
)
from orchestrator.workflow.stages.documenting import (
    handback as _handback,
    handoff as _handoff,
    models as _models,
    parks as _parks,
    state as _state,
    subject as _subject,
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


def _push_docs_and_advance(
    ctx: _models._DocumentingContext,
    wt,
    after_sha: str,
    notice: str,
    entered_head: str = "",
) -> None:
    """Push docs commit(s) and hand them back to `validating` for a report and a review.

    On push failure, park with `push_failed` instead of advancing. On
    success, hand the commit that went out to the hand-back
    (`handback._hands_back_for_review`), which stamps `docs_checked_sha`,
    records the report debt the publication leaves and the evidence and
    approval it invalidates, posts `notice` on the PR, and routes to
    `validating` behind a write that landed. Writes pinned state; the caller
    returns unconditionally.

    A docs commit is a candidate for a pull request the remote already carries
    like any other, so the size gate stands in front of this push too. It is
    the last one before a human is asked to merge, which is what makes it
    matter rather than what makes it an exception: a pass that took the diff
    past the ceiling would put an unadjudicated pull request in front of the
    person who merges it. A held candidate ends the tick -- the gate has
    parked the issue or handed it to the adjudication, and the hand-back
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
    the push replaces rides beside it (`docs_settled_lease`), since the report
    debt the hand-back records is owed from that head, and the
    code-publication receipt's own lease is rewritten by any later
    republication -- a recovery pushing the docs commit over itself among them.

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
            # The receipt the handoff is owed, and the head this push replaces,
            # which the report debt that handoff records is owed from: the
            # code-publication receipt's own lease is rewritten by any later
            # republication, the docs commit's over itself included.
            spends=_late_gate_models._Spends(fields=(
                (_state._SETTLED_DOCS_SHA, candidate),
                (_state._SETTLED_DOCS_LEASE, entered_head),
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
    _handback._hands_back_for_review(ctx, candidate, notice)


_SETTLED_DOCS_NOTICE = (
    ":books: documenting pass: docs commit `{commit}` is already on this pull "
    "request; this tick finished the handoff it was still owed. No second "
    "pass was run."
)


def _finished_settled_docs(
    ctx: _models._DocumentingContext, wt, ahead: int,
) -> bool:
    """Finish a docs pass whose commit the pull request already carries, handing it back for review.

    The receipt says the pass is over: an agent ran, it committed, and the
    only thing left between that commit and `validating` is the hand-back. The
    gate HELD the commit, and an authorized settlement publishes it from the
    adjudication and hands the label back here. Or the gate ALLOWED the push,
    it landed, and the tick died before this stage could record it, or the
    completion that would have recorded it was refused or went out and never
    landed -- the receipt goes down in the gate's own write either way, which
    is ahead of everything this stage does with a landed push.

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

    True once the hand-back is handed the receipt, whether or not its write
    landed: the tick is handled either way, and a write that did not land
    leaves the receipt standing for the next tick to read. The report debt it
    records is read off the code-publication receipt the publication wrote --
    the gate's own, or the settlement's -- rather than off this checkout. A
    receipt that code-publication receipt proves is answered ahead of this
    road on an unparked tick (`_finishes_a_published_pass`), so what reaches it
    is a park's reply over a published pass, or a receipt nothing proves.
    """
    settled = _payloads.as_hex(
        ctx.state.get(_state._SETTLED_DOCS_SHA), _formats.COMMIT_LENGTHS,
    )
    if not settled or ahead > 0 or not _standing_on(wt, settled):
        return False
    _handback._hands_back_for_review(
        ctx, settled, _SETTLED_DOCS_NOTICE.format(commit=settled),
    )
    return True


def _finishes_a_published_pass(ctx: _models._DocumentingContext) -> bool:
    """Hand back a pass whose publication the receipts prove, ahead of every question about its approval.

    The docs receipt names the commit the pass produced, and the
    code-publication receipt beside it names that very commit as published
    onto the pull request the issue pins (`handback._publication_proved`) --
    which, with the lease recorded beside the docs receipt, is the proof the
    report debt the hand-back records is read off, so nothing here reads the
    checkout. A lease that does not read holds the hand-back there.
    The approval was of the head before that commit, so whether it still
    stands is no question for this pass: asked first, an evidence context or a
    report that moved since would send the issue back to `validating` with no
    debt recorded, and the reviewer road would park for the very report the
    debt exists to fetch.

    Only an unparked issue: a park standing over a published pass -- a
    checkout that moved or was dirtied under the push -- is a human's to
    answer, and its reply comes back through `_finished_settled_docs`, which
    proves the checkout first. A receipt that proves no publication is left to
    that road too. True once the hand-back is handed the receipt, whether or
    not its write landed.
    """
    settled = _payloads.as_hex(
        ctx.state.get(_state._SETTLED_DOCS_SHA), _formats.COMMIT_LENGTHS,
    )
    if not settled or ctx.state.get(_state._AWAITING_HUMAN):
        return False
    if not _handback._publication_proved(ctx.state, settled):
        return False
    _handback._hands_back_for_review(
        ctx, settled, _SETTLED_DOCS_NOTICE.format(commit=settled),
    )
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
    -- so push it via the updated path, which hands it back to `validating`
    like any published docs commit. Otherwise hand the clean no-change
    verdict against the evaluated head to the completion, which lands it and
    advances. Writes pinned state; the caller returns unconditionally.
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
    _handoff._hand_off_to_in_review(ctx, after_sha, "no_change", _NO_CHANGE_NOTICE.format(
        # Quoted where the agent supplied a justification, so the PR carries
        # the reasoning rather than only the verdict.
        justification=_messages._as_blockquote(body.strip()) if body.strip()
        else "",
    ).rstrip())


def _documenting_commit_notice(recovered: bool) -> str:
    """The `:books:` push notice, distinguishing a recovered commit from a
    fresh docs commit."""
    if recovered:
        return ":books: documenting pass: pushed recovered docs commit(s)."
    return ":books: documenting pass: pushed docs commit."
