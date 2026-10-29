# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A finished docs pass's completion, the relabel behind it, and the handoff that brought it here.

The one this stage was handed is the shorter story, and it is asked first
past the preconditions -- a merged or closed pull request ends the tick before
it -- save a pass this stage already finished, whose completion the records
prove owed (`owed_completion._finishes_an_owed_completion`), and ahead of
drift and the docs pass. A
`validating` approval retires its own verdict ahead of the relabel and ends its
own squash handoff (`late_collapse_handoff_sha`) behind it, so a returned
verdict or a handoff record still standing when this stage runs is that
approval's cleanup write having failed, the approval leaving its own record
over a report or evidence record that moved while the relabel ran, or another
road's record put down then -- and nothing here can tell which. Neither is this
stage's to act on or to end, so the issue goes back to `validating`, whose
recovery answers the handoff over the approval it names and whose verdict road
answers the verdict, before a docs pass runs over either. No record stands over
what moves once that handoff is ended, nor over a report edited in place at
its location, so the approval itself is asked too: one that no longer covers
the developer report the comment records as current, or that report as it
reads at its location now, or whose evidence no longer stands, goes back the
same way, and a report or evidence nobody could read holds the tick.

Every finished pass leaves the approval, its evidence claim, the squash, the
settled report, `review_round`, and the PR watermarks validating wrote
untouched and advances to `in_review`, its final head verified and recorded
beside the approval rather than in it (`final_completion`): a pushed docs
commit is content that approval was never of, and nothing says otherwise.
What every completion carries forward is `pr_last_comment_id`. The
awaiting-human resume moves the reply boundary `last_action_comment_id` past
the human reply that answered its park, and records as delivered what its
bounded docs prompt quoted (`engine/thread_delivery`); in_review reads the
issue thread against that delivered stretch as well, so a reply the prompt
quoted is answered whatever this handoff writes, and one its excerpt cut is
not. What a `pr_last_comment_id` validating seeded BEFORE it leaves behind is a
watermark the next stage re-reads the whole span under on every tick.

The ratchet reuses validating's own seed-walk so a PR-conversation comment
sitting between the old watermark and the delivered stretch is not swallowed:
the walk stops at the first unread non-orchestrator comment on either surface,
and the delivered stretch applies to the issue thread only. `max` keeps a
higher in_review watermark from regressing, and a PR fetch failure is
best-effort -- the handoff still advances, and in_review's own rescan is
debounced and correct on its own. A published pass's completion walks behind
its notice, and so seeds past it. A pass that changed nothing walks ahead of
the proof that the evidence still answers for its head instead
(`retention._retains`), since the walk requests the pull
request and its threads, and a push behind a request that proof came before
is one it never saw: its watermark stops short of its own notice, which
in_review's feedback scan drops by the ledger entry the write records.

Every terminal success ends in the one completion (`_completes`) into
`in_review` -- a pass that changed nothing through `_hand_off_to_in_review`,
one that published through `final_completion` -- and the order is the whole
of its crash contract: stamp, prepare, announce, land, relabel. The stamp
records the head the verdict was formed against and the verdict, resets the
silent-park streak, ends a park the pass answered, and consumes the receipt a
published pass leaves (`_stamp_docs_verdict`). It lands as a checkpoint. The
tick holds the issue writer claim from its first reading through its last
write, so no other orchestrator writer moves the comment meanwhile, and the
reading the tick last confirmed -- the one it took once the claim was held, or
what its own last write landed (`PinnedState.synced`) -- is the comment the
completion is decided over. So it goes through the tick-state guarded commit
(`report_commits.ReportCommit`) over that reading (`_COMPLETION`): owning the
stamp and whatever the tick staged since -- a run's usage, the notice's ledger
entry, the ratcheted watermark, each kept beside any other move by its own
rule -- and decided on the stamp's own records, the publication and the debt
of a push not yet landed, and every record the opening read the approval
over; a pass that changed nothing over evidence proved to still answer for its
head is decided as well on every record that proof read (`retention.UNCHANGED`).
A record that reads otherwise was moved by no write of this tick's, and
refuses it with nothing put back, adopted, or repaired. A completion recording
its final head's verification owns that record and a run's transaction, and is
decided on every record the evidence is bound through
(`final_completion._PUBLISHED`), on the same terms.

The write is prepared before the notice, with the notice's ledger entry and
the ratcheted watermark reserved at their widest, so a comment that would not
take it -- unreadable, replaced, moved, or full -- is announced nothing. The
notice comes before the write because posting one RECORDS it: the comment id
lands in `orchestrator_comment_ids`, which is what keeps the watermark walk
and the in_review feedback scan from reading our own post as human feedback,
and there is nothing behind the write to carry it. The relabel is the one
effect that takes the issue off the stage that could finish what a crash
interrupted, and `in_review` repairs nothing: relabelled ahead of the write,
the merge gate reads a `docs_checked_sha` naming the commit the pass began on
and a `docs_verdict` nobody wrote, and the ready ping never fires for that
head. So only a write GitHub confirmed licenses it.

Anything else stops the handoff where it stands -- nothing announced past a
refused preparation, nothing relabelled past a write refused or never
confirmed -- logged, with the tick's state withheld from every whole-state
write behind it, and the next tick reads what landed. A write that did not
land leaves the receipt standing over a published pass, and that tick
finishes the handoff from it, announcing it a second time where this one
already had -- the window a tick that died over the write leaves too. A write
that landed, unconfirmed or ahead of a relabel that failed, leaves a pass
already called finished with no receipt behind it, and what tells it from the
record a same-head re-entry leaves is the completion it recorded: still
following the approval this issue records, naming the stamped head, beside
the verdict that head earns. The next tick finishes the relabel from it with
nothing run (`owed_completion._established`); a pass handed on with its stamp
alone recorded none, so its next tick runs the pass again.
"""
from __future__ import annotations

import logging

from github.Issue import Issue

from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    comments as _comments,
    pinned_commit_models as _commit_models,
    report_commits as _commits,
    report_record_values as _record_values,
)
from orchestrator.workflow.late_split import handoffs as _late_handoffs
from orchestrator.workflow.stages.documenting import (
    failed_pass as _failed_pass,
    models as _models,
    state as _state,
)
from orchestrator.workflow.stages.implementing.state import _APPROVED_LEASE, _APPROVED_SHA
from orchestrator.workflow.stages.validating import (
    approved_evidence as _approved_evidence,
    review_comment as _review_comment,
    review_coverage as _review_coverage,
    review_verdicts as _verdicts,
    watermarks as _validating_watermarks,
)
from orchestrator.workflow.state import WorkflowLabel

log = logging.getLogger("orchestrator.workflow")

_PR_LAST_COMMENT_ID = "pr_last_comment_id"

# The verdict a pass that published nothing is stamped with.
_NO_CHANGE = "no_change"

# What a finished pass stamps: the head its verdict was formed against, the
# verdict, the silent-park streak it resets, the park it ends, and the
# receipt, its lease, and the launch record it consumes. Each has to land as
# stamped, so each is decided on as well: one staged as the reading already
# spelled it is no move of the write's, and would otherwise be kept as whatever
# the comment carries by then.
_STAMPED = frozenset((
    _state._CHECKED_DOCS_SHA,
    _state._DOCS_VERDICT,
    "silent_park_count",
    _state._AWAITING_HUMAN,
    _state._PARK_REASON,
    _state._SETTLED_DOCS_SHA,
    _state._SETTLED_DOCS_LEASE,
    _state._LAUNCHED_DOCS_SHA,
))

# The completion of a finished pass, landed as a checkpoint over the reading
# the tick last confirmed. It owns the stamp, the watermark the ratchet moves,
# and the ledger entry its notice adds, beside whatever the tick staged since
# that reading. It is decided on the stamp; on the publication it is about --
# the pull request, the branch, the receipt of what reached the remote -- and
# the debt of a push not yet landed, which together tell a published pass from
# an unpublished candidate; and on every record the opening read the approval
# over, with the verdict and squash handoff only `validating` answers.
_COMPLETION = _commits.ReportWrite(
    owned=_STAMPED | {_PR_LAST_COMMENT_ID, _comments._ORCH_COMMENT_IDS},
    decided_on=frozenset((
        *_STAMPED,
        *_review_comment._IN_HAND_RECORDS,
        _verdicts.RETURNED_VERDICT,
        _late_handoffs.LATE_COLLAPSE_HANDOFF,
        _APPROVED_SHA,
        _APPROVED_LEASE,
    )),
).on_the_publication()

# What a guarded commit comes to that lets the handoff go on past it.
_GOES_ON = frozenset((_commit_models.CommitStatus.PREPARED, _commit_models.CommitStatus.COMMITTED))


def _in_review_watermark(
    gh: GitHubClient, issue: Issue, state: PinnedState,
) -> int | None:
    """The `pr_last_comment_id` the completion ratchets to, past issue-thread
    comments the docs pass already consumed during the final-docs hop, or
    None where there is nothing to ratchet.

    During documenting's awaiting-human resume the handler moves the reply
    boundary `last_action_comment_id` past the human reply that answered its
    park, and records as delivered what the bounded
    `_build_documentation_prompt` resume quoted. The final-docs handoff then
    relabels to `in_review`, which scans `comments_after(issue,
    pr_last_comment_id)` and drops what the delivered stretch
    (`engine/thread_delivery`) already covers -- so a quoted reply is
    answered either way, and what this ratchet does is stop a
    `pr_last_comment_id` validating seeded BEFORE the reply from leaving the
    next stage re-reading the whole span beneath it on every tick.

    Reuse `_latest_pr_comment_ids` (the same seed-walk validating uses
    at its approval handoff) so a PR-conversation comment with id
    between the prior `pr_last_comment_id` and the delivered stretch is NOT
    swallowed -- the walk stops at the first unread non-orchestrator
    comment on either surface. The stretch is applied to the issue thread
    only inside the walk, which is what keeps PR-conversation feedback
    visible to in_review's fresh-feedback scan. Ratchets via `max` so a previous in_review
    tick's higher watermark is never regressed.

    A PR fetch failure is treated as best-effort: log and skip, so the
    docs handoff itself still advances. In the worst case in_review
    will route to `fixing` and the rescan there is debounced and
    correct on its own.

    Only read: the walk requests the pull request and both threads, and
    the caller stages what it reached where its completion is to land.
    """
    pr_number = state.get("pr_number")
    if pr_number is None:
        return None
    try:
        pr = gh.get_pr(int(pr_number))
    except Exception as error:  # noqa: BLE001 - an unreadable PR leaves the watermark to in_review
        log.warning(
            "issue=#%s could not fetch PR #%s to ratchet "
            "`pr_last_comment_id` on the final-docs handoff: %s",
            issue.number, pr_number, error,
        )
        return None

    candidate, _ = _validating_watermarks._latest_pr_comment_ids(
        gh, issue, pr, state,
    )
    prev_wm = state.get(_PR_LAST_COMMENT_ID)
    if isinstance(prev_wm, int):
        candidate = (
            prev_wm if candidate is None
            else max(candidate, prev_wm)
        )
    return candidate


def _hands_back_what_validating_owes(
    gh: GitHubClient, issue: Issue, state: PinnedState,
) -> bool:
    """Send the issue back to `validating` over what only that stage answers; True where the tick is handled.

    Two of that stage's records can be standing when this one runs. The
    approval that moved the label here retired its own verdict ahead of the
    move and ends its own squash handoff behind it, but the relabel is a
    request of its own: another road can persist a later verdict, put a
    handoff of its own in place of that one, or settle a later report the
    approval then leaves its handoff standing over, while it runs -- and the
    write that ends the handoff can fail once the move has landed. From here none
    of those can be told apart, and a docs pass run over any of them documents
    a head a reviewer's verdict or an unfinished handoff says is not settled.

    So the label goes back, and nothing else is written: both records stay on
    the comment for the stage that reads them. A waiting verdict holds the
    label there for the road that finishes it. A handoff record reaches the
    recovery route ahead of the reviewer, which moves the label here again --
    ending the record behind that move -- only while the approval still
    covers the evidence it was proved over, the report, the requirements, and
    the head the record names, and
    otherwise drops it for the round it would have skipped. That is also what
    keeps this stage from ever running with a record standing: carried past
    here, a later return to `validating` for a re-review would be answered by
    relabelling the unchanged head straight back, and the review that return
    asks for would never run.

    The approval itself is asked beside them, because the handoff record is
    ended once the relabel lands, and a later report or evidence revision
    another road settles after that end, or the settled report a human edits
    or deletes in place, is one no record shows. One that no longer covers the
    developer report the comment records as current, or that report as it
    reads at its location now (`review_coverage._approval_stands`), or whose evidence no
    longer stands (`approved_evidence.stands`), is an approval of work that is
    not there, and the docs pass would document it as reviewed: it goes back
    too, for the reviewer. A report or evidence nobody could read proves
    nothing either way, and holds the tick without moving the label. Those
    readings are requests of their own, so the comment is read once more
    behind them (`_approval_still_stands`).

    A relabel that fails raises, as the handoff to `in_review` does: the
    records are still on the comment, and the next tick asks again. The
    ordinary issue carries neither record and an approval of what the
    comment carries, so it costs a reading of the report at its location --
    and of the evidence the approval's claim names, which every approval
    carries: one beside no claim rests on nothing and goes back.
    """
    owed = (
        _verdicts.read_returned_verdict(state) is not None
        or bool(_late_handoffs.read_settled_handoff(state))
    )
    standing = owed or _approval_still_stands(gh, issue, state)
    if standing is None:
        log.info(
            "issue=#%s could not read the developer report or verification "
            "evidence its approval rests on; holding the docs pass for the "
            "next tick", issue.number,
        )
        return True
    if not owed and standing:
        return False
    log.info(
        "issue=#%s carries a reviewer verdict, a squash handoff, or an "
        "approval of what it no longer carries, which `validating` still owes "
        "an answer; handing it back there ahead of the docs pass",
        issue.number,
    )
    gh.set_workflow_label(issue, WorkflowLabel.VALIDATING)
    return True


def _approval_still_stands(gh: GitHubClient, issue: Issue, state: PinnedState) -> bool | None:
    """Whether the approval that moved the label here still covers what the comment carries; None where unread.

    The report as recorded and as it reads at its location
    (`review_coverage._approval_stands`), and the evidence its proof rests on
    (`approved_evidence.stands`) -- and then the pinned comment, read last,
    since both are requests long enough for another road to settle a later
    report, persist a verdict, record a later verification revision, or
    replace or remove a review subject or the approval's evidence claim:
    where the report, pull-request, verdict, evidence, or approval records
    moved, the readings above were taken over records that are gone, and the
    approval does not stand. Whatever else another road wrote meanwhile is carried onto
    the state (`review_comment._records_stand`), so no write the docs pass
    makes puts it back.
    """
    standing = _review_coverage._approval_stands(gh, state) and _approved_evidence.stands(gh, state)
    if not standing:
        return standing
    read = dict(state.state_data)
    reread = _review_comment._records_stand(gh, issue, state, read, persisted=True)
    if reread is None:
        return None
    return reread.stood and not _review_comment._moved(
        reread.read, read, (*_review_comment._EVIDENCE_RECORDS, *_review_comment._APPROVAL_RECORDS),
    )


def _hand_off_to_in_review(
    ctx: _models._DocumentingContext,
    checked_sha: str,
    notice: str,
    write: _commits.ReportWrite,
) -> None:
    """Stamp a pass that published nothing, land it as a checkpoint, then move the issue to `in_review`.

    Its verdict is `no_change`, formed against `checked_sha`, and `notice` is
    what the pull request is told. `write` is the completion decided as well
    on every record the proof that the evidence still answers for that head
    read (`retention.UNCHANGED`). That proof took the ratchet's walk
    (`_in_review_watermark`) ahead of itself and staged what it reached: the
    walk requests the pull request and its threads, and a push behind a
    request the proof came before is one it never saw. So nothing here asks
    the pull request anything once the proof has answered, and the watermark
    stops short of the notice, which the ledger entry this write records
    keeps every later reader from taking for a human's. A pass that published
    a docs commit is verified and completed through the same completion
    (`final_completion._completes_published`).
    """
    _stamp_docs_verdict(ctx.state, checked_sha, _NO_CHANGE)
    _completes(ctx, write, notice, WorkflowLabel.IN_REVIEW, walks=False)


def _completes(
    ctx: _models._DocumentingContext,
    write: _commits.ReportWrite,
    notice: str,
    label: WorkflowLabel,
    *,
    walks: bool = True,
) -> None:
    """Land the completion staged on the tick's state as `write`, announcing `notice`, then relabel to `label`.

    The order is the whole of the crash contract. The completion is prepared
    over the fresh comment first, with the notice's ledger entry and the
    watermark the ratchet moves reserved at their widest, so a comment that
    would not take it is announced nothing. The notice goes out ahead of the
    write, whose ledger entry is what keeps every later reader from taking it
    for a human's, and best-effort: a comment failure must not strand an
    issue whose branch is already published. The ratchet's walk behind the
    notice (`walks`) seeds the watermark past it; a caller that took the walk
    itself, ahead of a decision nothing may be read behind, stages what it
    reached and walks nothing here. The relabel goes behind a write GitHub
    confirmed, and only behind one.

    A refused preparation, or a write refused or never confirmed, stops the
    handoff there (`_stops`), and a crash anywhere along it lands on an issue
    this stage still owns. A write that did not happen leaves the receipt the
    gate put down, and the next tick finishes the handoff from it. A write
    that landed with the relabel behind it never made leaves a pass this write
    already called finished and no receipt behind it: the next tick finishes
    the relabel from the completion it recorded
    (`owed_completion._established`), or, where it recorded none, runs the
    pass again rather than handing off on a stamp alone.
    """
    commit = _commits.ReportCommit(ctx.gh, ctx.issue, ctx.state)
    reserved = commit.staging()
    reserved.set(_PR_LAST_COMMENT_ID, _record_values.MAX_RECORDED_NUMBER)
    if _stops(ctx, commit.prepares(reserved, write, ledger_entry=True), "announcing"):
        return
    try:
        _comments._post_pr_comment(ctx.gh, int(ctx.pr_number), ctx.state, notice)
    except Exception:
        log.exception(
            "issue=#%s could not post docs notice to PR #%s",
            ctx.issue.number, ctx.pr_number,
        )
    if walks:
        walked = _in_review_watermark(ctx.gh, ctx.issue, ctx.state)
        if walked is not None:
            ctx.state.set(_PR_LAST_COMMENT_ID, walked)
    if _stops(ctx, commit.lands(ctx.state, write), "relabelling"):
        return
    ctx.gh.set_workflow_label(ctx.issue, label)


def _stamp_docs_verdict(
    state: PinnedState, checked_sha: str, verdict: str,
) -> None:
    """Stamp the docs watermarks after a terminal success: record the
    evaluated head, the verdict, and reset the silent-park counter.

    The verdict is `no_change` for a pass that published nothing and
    `updated` for one that published a docs commit (`final_completion`):
    `in_review`'s merge gate reads a head with a verdict beside it as one
    documented after its approval.

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

    A failed pass a paused tick recorded goes too: this pass finished, so the
    branch carries nothing a later tick must still park for. So does the
    receipt's lease, where it stands. And so does a park the pass answered --
    a reply over a published pass whose checkout moved, or whose verification
    did not pass, that this completion is the answer to -- since a park
    carried into `in_review` would hold every road there that waits on it.
    Each is dropped only where it is set, so an issue that never carried one
    is not given the key.
    """
    state.set(_state._CHECKED_DOCS_SHA, checked_sha)
    state.set(_state._DOCS_VERDICT, verdict)
    state.set("silent_park_count", 0)
    state.set(_state._SETTLED_DOCS_SHA, None)
    if state.get(_state._AWAITING_HUMAN):
        state.set(_state._AWAITING_HUMAN, False)
    for carried in (_state._SETTLED_DOCS_LEASE, _state._PARK_REASON):
        if state.get(carried) is not None:
            state.set(carried, None)
    _failed_pass._forget(state)


def _stops(ctx: _models._DocumentingContext, outcome: _commit_models.CommitOutcome, before: str) -> bool:
    """Whether `outcome` stops the handoff ahead of `before`: anything but a candidate measured or landed.

    Logged, with the tick's state withheld from every whole-state write behind
    it: a refusal wrote nothing, and an answer that was lost may or may not
    have landed, which only the next tick's reading can say. That includes a
    refusal for room over a comment still reading as the tick last confirmed
    it, which the guarded commit alone would leave writable
    (`ReportCommit.withholds`): nothing behind the handoff in this tick is owed
    that room, and the state carries the stamp the comment refused.
    """
    if outcome.status in _GOES_ON:
        return False
    ctx.state.withheld = True
    log.warning(
        "issue=#%d its final-docs completion came back %s; %s nothing, with the pinned comment left as it stands "
        "for the next tick to read",
        ctx.issue.number, (outcome.refusal or outcome.status).value, before,
    )
    return True
