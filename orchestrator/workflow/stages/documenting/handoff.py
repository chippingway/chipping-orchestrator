# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The relabel to `in_review`, and the handoff that brought the issue here.

The one this stage was handed is the shorter story and it opens the tick. A
`validating` approval settles a finished squash into `late_collapse_handoff_sha`
and moves the label behind that write, so a record still standing when this
stage runs is one whose relabel DID land and whose cleanup write did not. This
stage running is the proof of that, and it is the only proof there is -- the
label history cannot tell a move that never happened from one this stage later
unwound -- so the record is ended here rather than left for a validating tick
to read as a move it still owes and answer a re-review by relabelling the
unchanged head straight back.

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
from orchestrator.workflow.stages.validating import watermarks as _validating_watermarks
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


def _ends_the_validating_handoff(
    gh: GitHubClient, issue: Issue, state: PinnedState,
) -> None:
    """Drop the record of a handoff this stage having the issue proves landed.

    The approval before this one ends its collapse claim and leaves the commit
    the relabel is owed over in its place, then moves the label. A record
    still here is that move having landed with the write that would have
    dropped it having failed -- and the route that reads it back in
    `validating` cannot tell such a record from one whose move never happened.
    Left standing, a drift unwind that sends this issue back for a re-review
    is answered by relabelling the unchanged head straight here again, and the
    review that unwind exists to ask for never runs.

    Its own write rather than a staged mutation, because most roads out of a
    documenting tick return without one -- and there is nothing to compose it
    with: the record is not this stage's to act on, only to end. A write that
    fails ends the tick with everything else durable exactly as it was, and
    the next documenting tick makes it.

    Nothing is written for the ordinary issue, which carries no such record:
    the approval that handed it here dropped its own.
    """
    if not _late_handoffs.read_settled_handoff(state):
        return
    _late_handoffs.clear_settled_handoff(state)
    gh.write_pinned_state(issue, state)


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
