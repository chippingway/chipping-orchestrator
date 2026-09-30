# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The relabel to `in_review`, and the handoff that brought the issue here.

The one this stage was handed is the shorter story, and it is asked first
past the preconditions -- a merged or closed pull request ends the tick before
it -- and ahead of drift and the docs pass. A
`validating` approval retires its own verdict ahead of the relabel and ends its
own squash handoff (`late_collapse_handoff_sha`) behind it, so a returned
verdict or a handoff record still standing when this stage runs is that
approval's cleanup write having failed, the approval leaving its own record
over a report or evidence record that moved while the relabel ran, or another
road's record put down then -- and nothing here can tell which. Neither is this
stage's to act on or to end, so the issue goes back to `validating`, whose
recovery answers the handoff over the approval it names and whose verdict road
answers the verdict, before a docs pass runs over either. An approval that
collapsed nothing leaves no handoff record to stand over what moved while its
relabel ran, so the approval itself is asked too: one that no longer covers
the developer report the comment records as current, or that report as it
reads at its location now, or whose evidence no longer stands, goes back the
same way, and a report or evidence nobody could read holds the tick.

Both docs outcomes -- a pushed commit and a confirmed no-change -- leave the
approval, squash, and PR watermarks validating wrote untouched and advance to
`in_review`. What they carry forward is `pr_last_comment_id`. The
awaiting-human resume advances `last_action_comment_id` past the human reply it
fed into the docs prompt, and in_review reads the issue thread against that
cursor as well, so the reply is answered whatever this handoff writes; what a
`pr_last_comment_id` validating seeded BEFORE it leaves behind is a watermark
the next stage re-reads the whole span under on every tick.

The ratchet reuses validating's own seed-walk so a PR-conversation comment
sitting between the old watermark and the consumed-through threshold is not
swallowed: the walk stops at the first unread non-orchestrator comment on
either surface, and the consumed-through bound applies to the issue thread
only. `max` keeps a higher in_review watermark from regressing, and a PR fetch
failure is best-effort -- the handoff still advances, and in_review's own
rescan is debounced and correct on its own.

The pinned write comes next and the relabel last, because the relabel is the
one effect that takes the issue off the stage that could finish what a crash
interrupted. `in_review` repairs nothing: relabelled first, a process dying
before the write leaves the merge gate reading a `docs_checked_sha` that names
the commit the pass began on and a `docs_verdict` nobody wrote, and the ready
ping never fires again for that head.
"""
from __future__ import annotations

import logging

from github.Issue import Issue

from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.late_split import handoffs as _late_handoffs
from orchestrator.workflow.stages.validating import (
    approved_evidence as _approved_evidence,
    review_comment as _review_comment,
    review_coverage as _review_coverage,
    review_verdicts as _verdicts,
    watermarks as _validating_watermarks,
)
from orchestrator.workflow.state import WorkflowLabel

log = logging.getLogger("orchestrator.workflow")


def _ratchet_in_review_watermark_for_final_docs(
    gh: GitHubClient, issue: Issue, state: PinnedState,
) -> None:
    """Ratchet `pr_last_comment_id` past issue-thread comments the docs
    pass already consumed during the final-docs hop.

    During documenting's awaiting-human resume the handler advances
    `last_action_comment_id` past the human reply it fed into the
    `_build_documentation_prompt` resume. The final-docs handoff then
    relabels to `in_review`, which scans `comments_after(issue,
    pr_last_comment_id)` and drops what that delivery cursor already
    covers -- so the consumed reply is answered either way, and what
    this ratchet does is stop a `pr_last_comment_id` validating seeded
    BEFORE the reply from leaving the next stage re-reading the whole
    span beneath it on every tick.

    Reuse `_latest_pr_comment_ids` (the same seed-walk validating uses
    at its approval handoff) so a PR-conversation comment with id
    between the prior `pr_last_comment_id` and the consumed-through
    threshold is NOT swallowed -- the walk stops at the first unread
    non-orchestrator comment on either surface. `consumed_through` is
    applied to the issue thread only inside the walk, which is what
    keeps PR-conversation feedback visible to in_review's
    fresh-feedback scan. Ratchets via `max` so a previous in_review
    tick's higher watermark is never regressed.

    A PR fetch failure is treated as best-effort: log and skip, so the
    docs handoff itself still advances. In the worst case in_review
    will route to `fixing` and the rescan there is debounced and
    correct on its own.
    """
    pr_number = state.get("pr_number")
    if pr_number is None:
        return
    try:
        pr = gh.get_pr(int(pr_number))
    except Exception as error:  # noqa: BLE001 - an unreadable PR leaves the watermark to in_review
        log.warning(
            "issue=#%s could not fetch PR #%s to ratchet "
            "`pr_last_comment_id` on the final-docs handoff: %s",
            issue.number, pr_number, error,
        )
        return

    candidate, _ = _validating_watermarks._latest_pr_comment_ids(
        gh, issue, pr, state,
    )
    prev_wm = state.get("pr_last_comment_id")
    if isinstance(prev_wm, int):
        candidate = (
            prev_wm if candidate is None
            else max(candidate, prev_wm)
        )
    if candidate is None:
        return
    state.set("pr_last_comment_id", candidate)


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

    The approval itself is asked beside them, because an approval that
    collapsed nothing leaves no handoff record, and its relabel is a request
    long enough for another road to settle a later report or evidence
    revision, or for a human to edit or delete the settled report in place,
    which no record shows. One that no longer covers the developer report
    the comment records as current, or that report as it reads at its
    location now (`review_coverage._approval_stands`), or whose evidence no
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
    and of the evidence, for an approval proved over any.
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
    report, persist a verdict, or record a later verification revision:
    where the report, pull-request, verdict, or evidence records moved, the
    readings above were taken over records that are gone, and the approval
    does not stand. Whatever else another road wrote meanwhile is carried onto
    the state (`review_comment._records_stand`), so no write the docs pass
    makes puts it back.
    """
    standing = _review_coverage._approval_stands(gh, state) and _approved_evidence.stands(gh, state)
    if not standing:
        return standing
    read = dict(state.data)
    reread = _review_comment._records_stand(gh, issue, state, read, persisted=True)
    if reread is None:
        return None
    return reread.stood and not _review_comment._moved(reread.read, read, _review_comment._EVIDENCE_RECORDS)


def _hand_off_to_in_review(
    gh: GitHubClient, issue: Issue, state: PinnedState,
) -> None:
    """Persist what the pass decided, then move the issue off this stage.

    The order is the whole of the crash contract. The relabel is what takes
    the issue out of `workflow:documenting`, and `in_review` repairs nothing
    it is handed: relabelled ahead of this write, a process dying in between
    leaves the merge gate reading a head whose `docs_checked_sha` still names
    the commit the pass STARTED on and whose `docs_verdict` was never written,
    so the ready ping never fires and no later tick of any stage goes back
    for it.

    Written first, a crash from here on lands on an issue this stage still
    owns. The write that did not happen leaves the receipt the gate put down,
    and the next tick finishes the handoff from it. The relabel that did not
    happen leaves a pass this write already called finished and no receipt
    behind it -- which is the same record a `validating` approval handing the
    same head back leaves, so the next tick runs the pass rather than handing
    off on evidence that could belong to either.
    """
    _ratchet_in_review_watermark_for_final_docs(gh, issue, state)
    gh.write_pinned_state(issue, state)
    gh.set_workflow_label(issue, WorkflowLabel.IN_REVIEW)


def _advance_after_docs_push(
    gh: GitHubClient, issue: Issue, state: PinnedState,
) -> None:
    """Route the issue forward after a successful docs push.

    Advance to `in_review` -- the approval comment, squash comment, and
    PR watermarks set by validating remain on state untouched, with the
    in-review issue-comment watermark ratcheted past anything the
    awaiting-human resume already consumed. Writes pinned state ahead of the
    relabel; the caller returns unconditionally.
    """
    _hand_off_to_in_review(gh, issue, state)


def _advance_after_docs_no_change(
    gh: GitHubClient, issue: Issue, state: PinnedState,
) -> None:
    """Route the issue forward after a clean no-change docs verdict.

    No commit landed, so the PR head is unchanged. Ratchet the in-review
    issue-comment watermark past any issue-thread reply the awaiting-human
    resume already consumed, persist the verdict, and advance to `in_review`.
    """
    _hand_off_to_in_review(gh, issue, state)
