# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What an approved review posts on its pull request, what it seeds after, and what its writes are held to.

The three writes an approval puts on the thread are here -- the reviewer's
verdict, the squash notice, and the watermarks that follow that notice. The
watermarks are what keep the other two from being read back as human
feedback: in_review wakes on "PR feedback newer than the watermark", so an
approval that posted and seeded nothing would hand the next stage the
orchestrator's own announcements as fresh review and wake the dev on them.

The seed is two owners because it answers two different questions. The
snapshot half is about a read that can fail: taken behind the notice so the
walk steps past the notice's own id, and abandoned outright where the pull
request will not answer, since in_review still has its legacy watermark to
fall back on and an approved branch may not be stranded on a read. The ratchet
half is reached only past that, and answers what each of the three watermarks
becomes against what is already persisted.

The approval comment is the one post nothing is owed for. It carries no count,
nothing later reads it back, and a thread that would not take it is no reason
to hold a verified branch out of `documenting` -- so its failure is logged and
the road carries on.

Every write an approval's tail makes -- the squash, the handoff behind it, the
park a failed squash takes -- follows requests of its own, and each is held
first to the report, pull-request, returned-verdict, and verification-evidence
records the state in hand carries (`_holds_its_records`). Where they stand,
the state is laid over the comment as read then, measured from the comment as
the tail last read or wrote it (`_Held`): a field another road wrote meanwhile
-- a round spent by a reply -- is carried rather than written back over. The
squash writes the state in hand wherever it writes, which its own reply does
not say, so it is handed a client that holds each of those writes to the same
records and lays it over the comment first, refusing one whose records moved,
and follows them (`squash_writes`): the reading behind it is measured from
the last of them -- from the reading before it, where it wrote none. Where the records
moved, nothing the approval holds is written, but what every post leaves on
the ledger is owed all the same: the post is the orchestrator's, and a prompt
keeps an orchestrator comment only where that ledger vouches for it. So is the
end of the verdict the approval finishes, which rested on the records that
moved -- retired over the comment as read, and only that verdict: one another
road put in its place stays.
"""
from __future__ import annotations

import copy
import logging
from dataclasses import dataclass
from functools import partial

from github.Issue import Issue

from orchestrator import config
from orchestrator.git.verification import probes as _probes, status as _worktree_status
from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    comments as _comments,
    report_record_state as _report_record_state,
    review_subjects as _review_subjects,
)
from orchestrator.workflow.stages.validating import (
    approved_evidence as _approved_evidence,
    models as _models,
    review_comment as _review_comment,
    review_verdicts as _verdicts,
    squash_writes as _squash_writes,
    state as _state,
    watermarks as _watermarks,
)

log = logging.getLogger("orchestrator.workflow")

# What every write the tail makes is held to: the report, pull-request, and
# returned-verdict records, and the verification evidence the approval rests on.
_HELD_RECORDS = (*_review_comment._VERDICT_RECORDS, *_review_comment._EVIDENCE_RECORDS)

# What a write the squash makes is about to do, for the log where the records
# moved under it and it is refused.
_SQUASH_WRITE = "let its squash write the state in hand over it"


@dataclass
class _Held:
    """What an approval's tail holds across the requests and writes it makes.

    `verdict` is the returned verdict the approval behind the tail finishes --
    the approval its own run returned, of that round and subject -- and the
    only one any of its writes retires: None where none waits, and on the
    recovery of a squash an earlier tick did not finish, which holds none.
    `subject` is the review subject that approval was of, as recorded, which a
    park the tail takes is held to behind its notice -- None on that recovery,
    which holds no subject either. `comment` is the pinned comment as the tail
    last read or wrote it, which the next reading is measured from; None where
    that reading takes the state in hand whole over the comment instead.
    """

    verdict: _verdicts.ReturnedVerdict | None
    subject: dict | None = None
    comment: dict | None = None

    @classmethod
    def of_the_approval(cls, state: PinnedState, run: _models._ReviewerRun) -> _Held:
        """What the approval `run` returned holds: its subject, and the verdict `state` has waiting if it is that."""
        waiting = _verdicts.read_returned_verdict(state)
        subject = run.subject.recorded()
        if waiting is not None and (waiting.round_n, waiting.verdict, waiting.subject) != (
            run.round_n, _verdicts.APPROVED, subject,
        ):
            waiting = None
        return cls(waiting, subject)

    def wrote(self, state: PinnedState) -> None:
        """Take `state`, just written, as the comment the tail last wrote.

        A copy to its depth, since the state in hand goes on being staged on
        after the write, and a record it changes in place would otherwise
        read as the comment having changed it.
        """
        self.comment = copy.deepcopy(state.data)

    def follows(self, gate):
        """`gate`, its client holding each write of its issue's pinned comment to the records in hand, and following it.

        Handed to the squash, which writes the state in hand whole and whose
        reply does not say whether it wrote (`squash_writes`): each write is
        asked first whether the comment still carries the report,
        pull-request, verdict, and evidence records in hand, and laid over it
        (`_holds_its_records`); once it lands, it is the comment the tail last
        wrote.
        """
        holds = partial(_holds_its_records, gate.gh, gate.issue, purpose=_SQUASH_WRITE, held=self)
        return _squash_writes.followed(gate, holds, self.wrote)

    def checkout_stands(self, gate) -> bool | None:
        """Whether the gate's checkout still stands on the head the approval was of, clean; None where unread.

        Asked behind each request of the arc the checkout can move in -- the
        verify gate, which proves the tree only while its own commands run and
        reads nothing where none are configured, and the approval notice --
        because the squash, and the handoff where no squash rewrites anything,
        take the branch from this checkout: a commit made there since, or a
        change left in it, is work no reviewer read, and a checkout standing
        ahead of the pull request is one the documenting stage publishes as
        its own recovered work. True where the tail holds no subject: the
        recovery of a squash an earlier tick began, whose checkout the squash
        owner proves itself.
        """
        reviewed = _review_subjects.ReviewSubject.commit_recorded_in(self.subject)
        if reviewed is None:
            return True
        head = _probes._head_sha(gate.worktree)
        tree = _worktree_status._worktree_status(gate.worktree)
        if not head or not tree.readable:
            return None
        if head == reviewed and tree.is_clean:
            return True
        log.info(
            "issue=#%s its checkout stands on %s%s, not the %s its approval "
            "was of; not acting on that approval this tick", gate.issue.number,
            head, "" if tree.is_clean else " with uncommitted changes", reviewed,
        )
        return False

    def evidence_stands(self, gate) -> bool | None:
        """Whether the evidence the verdict held here was proved over still proves; None where it could not be read.

        Asked behind each request of the arc the artifact can move in, over
        the gate's pull request and checkout (`approved_evidence.refusal`).
        True where the tail holds no claim: the recovery of a squash an earlier
        tick did not finish, which holds no verdict. Every approval the
        disposition hands the arc was proved over the claim its verdict names.
        """
        claim = None if self.verdict is None else self.verdict.evidence
        if claim is None:
            return True
        refusal = _approved_evidence.refusal(gate.gh, gate.spec, gate.issue, gate.state, claim)
        if refusal:
            log.info(
                "issue=#%s the verification evidence its approval was proved "
                "over no longer proves: %s", gate.issue.number, refusal,
            )
        return None if refusal is None else not refusal

    def records_the_approval(self, state: PinnedState, subject) -> None:
        """Stage the approval this tail finishes: the subject it covers, and the evidence its verdict was proved over.

        Recorded together, so every later road that would move the approval
        on holds it to both (`approved_evidence.stands`). The caller's
        write carries them.
        """
        _review_subjects.record_approved(state, subject)
        _approved_evidence.records(state, None if self.verdict is None else self.verdict.evidence)


def _post_approval_comment(
    gh: GitHubClient,
    issue: Issue,
    state: PinnedState,
    reviewer_run: _models._ReviewerRun,
) -> None:
    if reviewer_run.pr_number is None:
        return
    try:
        _comments._post_pr_comment(
            gh,
            int(reviewer_run.pr_number),
            state,
            f":white_check_mark: {config.REVIEW_AGENT} review approved.",
        )
    except Exception:
        log.exception(
            "issue=#%s could not post approval to PR #%s",
            issue.number,
            reviewer_run.pr_number,
        )


def _squash_notice_posted(
    gh: GitHubClient,
    issue: Issue,
    state: PinnedState,
    pr_number,
    squashed_count: int,
) -> bool:
    """Tell the pull request how much history the force-push replaced.

    Nothing is owed where no history was replaced by less of it, which is
    every branch that reached approval with one commit on it -- whether that
    commit was left alone or rewritten to reference the pull request, since
    either way the branch carried one commit before and carries one now -- and
    every tick that finished a collapse an earlier one already announced. An
    issue with no pull request has nowhere to say it.

    A post that fails answers False rather than being swallowed, because the
    count behind it is recoverable state: it is on the pinned record of the
    collapse, and the caller keeps that record rather than dropping it over an
    announcement that never went out.
    """
    if pr_number is None or squashed_count <= 1:
        return True
    try:
        _comments._post_pr_comment(
            gh, int(pr_number), state,
            f":package: squashed {squashed_count} commits to 1",
        )
    except Exception:
        log.exception(
            "issue=#%s could not post squash notice to PR #%s; leaving the "
            "collapse recorded so a later tick can announce it",
            issue.number, pr_number,
        )
        return False
    return True


def _holds_its_records(
    gh: GitHubClient, issue: Issue, state: PinnedState, purpose: str, held: _Held,
) -> bool:
    """Whether the comment still carries the report, pull-request, verdict, and evidence records `state` does.

    Asked ahead of each write an approval's tail makes behind requests of its
    own, `purpose` naming the write. Where the records stand, `state` is laid
    over the comment as read, measured from `held.comment` -- or, where that
    is None, taken whole over it, only the ledger of the orchestrator's own
    comments merged (`review_comment._Reread.lays_over`) -- and that reading is
    what the next one is measured from. Where they moved, nothing `state` holds
    is written over them (`_records_what_it_posted`). A comment that will not
    read, or is no longer the one `state` was read from, is left as it stands.
    """
    durable = _review_comment._read(gh, issue, state, purpose)
    if durable is None:
        return False
    if _review_comment._moved(durable.data, state.data, _HELD_RECORDS):
        log.warning(
            "issue=#%s its pinned comment does not carry the developer report, "
            "pull request, verdict, or verification evidence records this tick "
            "holds, so it will not %s; recording only the comments it posted "
            "and retiring the verdict it holds", issue.number, purpose,
        )
        _records_what_it_posted(gh, issue, state, durable, held)
        return False
    read = dict(durable.data)
    _review_comment._Reread(stood=True, read=read).lays_over(
        state, read if held.comment is None else held.comment,
    )
    held.comment = read
    return True


def _records_what_it_posted(
    gh: GitHubClient, issue: Issue, state: PinnedState, durable: PinnedState, held: _Held,
) -> None:
    """Write over `durable` only the comments `state` records as posted, and the end of the verdict `held` holds.

    The records the approval was proved over moved, so a fresh reviewer
    answers the subject as it stands, while a verdict another road put in the
    place of the one held stays for that road. Each id is merged once among
    the newest the ledger's bound holds, and an entry naming no comment is
    nobody's post. Nothing is written where neither changes the comment, or
    where the comment has no room for what does.
    """
    ledger = durable.get(_comments._ORCH_COMMENT_IDS)
    posted = state.get(_comments._ORCH_COMMENT_IDS)
    if not isinstance(posted, list):
        posted = []
    ours = sorted(entry for entry in posted if _state._is_whole(entry))
    _comments._track_orchestrator_comment(durable, *ours)
    retired = _verdicts.drops_the_verdict(durable, only=held.verdict)
    if durable.get(_comments._ORCH_COMMENT_IDS) == ledger and not retired:
        return
    if _report_record_state.fits_the_comment(durable.data):
        gh.write_pinned_state(issue, durable)
        return
    log.error(
        "issue=#%s has no room on its pinned comment to record the comments "
        "its approval posted; leaving it as it stands", issue.number,
    )


def _seed_in_review_handoff_watermarks(
    gh: GitHubClient, issue: Issue, state: PinnedState, pr_number,
) -> None:
    """Take the snapshot the seed below is read off, or leave it unseeded.

    The caller runs this BEHIND the squash notice, so the snapshot carries
    that notice's own id and the walk steps past it. Taken ahead of the post,
    the notice would land above every watermark seeded here and reach
    in_review as fresh human PR feedback, waking the dev on an informational
    orchestrator post.

    A `get_pr` that will not answer is not fatal. in_review falls back to its
    legacy watermark, so the snapshot is abandoned and nothing is seeded
    rather than an approved branch being stranded on a read.
    """
    if pr_number is None:
        return
    try:
        pr = gh.get_pr(int(pr_number))
    except Exception as error:  # noqa: BLE001 - an unreadable PR falls back to the legacy watermark
        # Surface the failure but skip the traceback -- it adds no signal.
        log.warning(
            "issue=#%s could not snapshot PR #%s for in_review "
            "handoff: %s", issue.number, pr_number, error,
        )
        return
    _seed_in_review_pr_watermarks(gh, issue, state, pr)


def _seed_in_review_pr_watermarks(
    gh: GitHubClient, issue: Issue, state: PinnedState, pr,
) -> None:
    """Park the three in_review watermarks past this snapshot's leading run of
    orchestrator-authored comments.

    The seed keeps `_handle_in_review` from replaying the orchestrator's own
    automated comments ("picking this up", "PR opened", the approval just
    posted, the squash notice) as fresh PR feedback once the debounce expires.
    Concurrent human feedback posted during the prior stage is preserved:
    `_latest_pr_comment_ids` stops the seed walk at the first unread
    non-orchestrator comment on either surface, and `_ratchet_watermark` never
    regresses a watermark a prior in_review tick already advanced. Stopping
    that early on an unread PR comment is deliberately allowed to leave the
    value below a reply the dev already answered: in_review reads the issue
    thread against `last_action_comment_id` too, so the reply stays consumed
    without this seed having to cross the PR comment to say so.

    Inline review comments and review summaries live in namespaces the
    orchestrator never posts on, so the inline surface answers None and there
    is no seeded summary value; `_ratchet_watermark` defaults each to 0 so the
    in_review legacy migration treats them as already seeded and does NOT
    advance past human feedback submitted on those surfaces.
    """
    issue_wm, review_wm = _watermarks._latest_pr_comment_ids(gh, issue, pr, state)
    state.set(
        "pr_last_comment_id",
        _watermarks._ratchet_watermark(state.get("pr_last_comment_id"), issue_wm),
    )
    state.set(
        "pr_last_review_comment_id",
        _watermarks._ratchet_watermark(state.get("pr_last_review_comment_id"), review_wm),
    )
    state.set(
        "pr_last_review_summary_id",
        _watermarks._ratchet_watermark(state.get("pr_last_review_summary_id"), None),
    )
