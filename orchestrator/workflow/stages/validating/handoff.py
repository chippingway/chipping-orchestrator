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
records the state in hand carries, and to the review subjects, the
approval's evidence claim, the report debt a review subject stands only
without, the park, and the collapse record and its handoff as the comment
carried them when the tail last read or wrote it (`_holds_its_records`) --
what every proof since, the evidence's included, was taken over, what a carry
answers on, and what the tail itself clears or ends. Where they stand,
the state is laid over the comment as read then, measured from the comment as
the tail last read or wrote it (`_Held`): a field another road wrote meanwhile
-- a round spent by a reply -- is carried rather than written back over. The
write then lands as a guarded commit over the comment read afresh
(`_Held.lands`, `squash_writes.lands`), decided on every record the tail holds
-- those, with every record a report debt is read from -- exactly as that
reading spells them (`HELD_ON`), and owning what each write declares
(`RETIRES`, `HANDOFF`, `CARRIED`, `SQUASH_PARK`) beside what the tick staged:
a record another road moves after that reading refuses it as surely as one
moved before it, and every other field is the fresh reading's. A carry of the
evidence the approval rests on is held to that very candidate as well
(`_Held.settles`): where the fresh comment has no room to record or settle it, it is
invalidated in its place rather than recorded owed for good. The squash
writes the state in hand wherever it writes, which its own reply does not
say, so it is handed a client that holds each of those writes to the same
records, lays it over the comment first, and lands it through the same
commit, refusing one whose records moved or whose commit did not land, and
follows them (`squash_writes`): the reading behind it is measured from the
last of them -- from the reading before it, where it wrote none. Where the
records moved -- caught by that reading or refused by the commit -- nothing
the approval holds is written, and the tick's state is withheld from every
whole-state write behind it, but what every post leaves on the ledger is owed
all the same: the post is the orchestrator's, and a prompt keeps an
orchestrator comment only where that ledger vouches for it. So is the end of
the verdict the approval finishes where what moved is a record that approval
was proved over, a report owed among them -- retired over the comment as
read, in a guarded commit of its own, and only that verdict: one another road
put in its place stays. A park or a collapse record another road put down
keeps the verdict waiting, for the human or the recovery that answers it.
"""
from __future__ import annotations

import copy
import logging
from dataclasses import dataclass, replace
from functools import partial

from github.Issue import Issue

from orchestrator import config
from orchestrator.git.verification import (
    models as _verify_models,
    probes as _probes,
    status as _worktree_status,
)
from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    comments as _comments,
    pinned_commit_models as _commit_models,
    prompt_delivery as _prompt_delivery,
    report_commits as _commits,
    report_delivery as _report_delivery,
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

# What reading the comment again behind a write it refused is for.
_UNLANDED = "record what it posted behind a write the comment refused"

# The refusals a comment's room earns: a candidate past what one comment holds,
# and one the write's own check of its room refused.
_NO_ROOM = frozenset((_commit_models.CommitRefusal.OVERFLOW, _commit_models.CommitRefusal.INADMISSIBLE))

_AWAITING_HUMAN = "awaiting_human"

# A park's flags, which the handoff clears and a failed squash's park sets.
_PARK_FLAGS = frozenset((_AWAITING_HUMAN, _state._PARK_REASON))

# What the approval answers through beside the records in hand, measured from
# the comment as the tail last read or wrote it: the review subjects and its
# evidence claim, and the report debt a review subject stands only without --
# a report owed is one the pull request does not carry as the approval read it.
_APPROVED_OVER = (*_review_comment._APPROVAL_RECORDS, _report_delivery.OWED_REPORT)

# The records the approval was proved over, whose move refuses everything it
# holds and retires the verdict it finishes (`_holds_its_records`).
_PROVED_OVER = frozenset((*_HELD_RECORDS, *_APPROVED_OVER))

# What another road moving holds the tail with its verdict kept: a park, which
# a human answers, and a collapse record or its handoff, which only the squash
# recovery answers. Measured, as `_APPROVED_OVER` is, from the comment as the
# tail last read or wrote it, since the tail clears a park and ends a collapse
# itself -- and a park or a record laid over the state in hand from another
# road's write would be cleared or ended by the tail's next write unseen.
_HELD_APART = frozenset((*_PARK_FLAGS, *_squash_writes.COLLAPSE_RECORDS))

# What every guarded write of the tail is decided on, exactly as the reading it
# was decided over spells it: the records `_holds_its_records` holds the tail
# to -- the report's, the pull request, the returned verdict, the evidence, the
# review subjects, the approval's claim, the park, and the collapse record and
# handoff it reads and ends -- with every record a report debt is read from,
# as the evidence proofs bind them (`report_delivery.REPORT_DEBT`). A write
# staging one of them unchanged -- a park over a reading already parked, a drop
# of a verdict another road replaced -- would otherwise land beside another
# road's move of it unseen.
HELD_ON = frozenset((*_PROVED_OVER, *_HELD_APART, *_report_delivery.REPORT_DEBT))

# A write the squash makes of its own: the collapse it records ahead of its
# rewrite, or drops behind a rollback, and the size gate's records, which ride
# it as what the tick staged.
_THROUGH = _commits.ReportWrite(owned=_squash_writes.COLLAPSE_RECORDS, decided_on=HELD_ON)

# The end of the verdict the approval holds, beside whatever the tick staged:
# the run's records, a squash the gate held, a notice that went unposted.
RETIRES = _commits.ReportWrite(owned=frozenset((_verdicts.RETURNED_VERDICT,)), decided_on=HELD_ON)

# The handoff behind a published squash: the verdict retired, the approval it
# finishes recorded with its evidence claim, a park ended, and the collapse
# record ended into the commit the relabel is owed over. A carry the squash's
# evidence earns rides it as well (`squash_evidence.SquashEvidence.writes`).
HANDOFF = _commits.ReportWrite(
    owned=frozenset((
        _verdicts.RETURNED_VERDICT,
        _review_subjects.APPROVED_SUBJECT,
        _approved_evidence.APPROVED_EVIDENCE,
        *_PARK_FLAGS,
        *_squash_writes.COLLAPSE_RECORDS,
    )),
    decided_on=HELD_ON,
)

# What the evidence the approval rests on owes a head, recorded in a write of
# its own -- the carry, or the evidence invalidated with the handoff over it.
CARRIED = _commits.ReportWrite(owned=frozenset(), decided_on=HELD_ON)

# What a tail whose records moved still writes over the comment as it stands:
# its posts' ledger entries, merged, and the end of the verdict it holds, only
# where that is still the one waiting.
_POSTED = _commits.ReportWrite(
    owned=frozenset((_comments._ORCH_COMMENT_IDS, _verdicts.RETURNED_VERDICT)),
    decided_on=frozenset((_verdicts.RETURNED_VERDICT,)),
)

# The park a failed squash takes: its flags, the verdict it retires, and the
# ledger entry and the thread read through that posting its notice adds.
SQUASH_PARK = _commits.ReportWrite(
    owned=frozenset((
        _verdicts.RETURNED_VERDICT,
        *_PARK_FLAGS,
        _prompt_delivery.PINNED_LAST_ACTION_COMMENT_ID,
        _comments._ORCH_COMMENT_IDS,
    )),
    decided_on=HELD_ON,
)


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
    `gate_run` is the run the approval's verify gate made this tick, which
    its squash carries as orchestrator-executed evidence where it binds
    (`squash_evidence`) -- None on that recovery, which ran no gate.
    """

    verdict: _verdicts.ReturnedVerdict | None
    subject: dict | None = None
    comment: dict | None = None
    gate_run: _verify_models.VerifyResult | None = None

    @classmethod
    def of_the_approval(
        cls, state: PinnedState, run: _models._ReviewerRun, gate_run: _verify_models.VerifyResult | None = None,
    ) -> _Held:
        """What the approval `run` returned holds.

        Its subject, the verdict `state` has waiting if it is that, and
        `gate_run`, the run its verify gate made.
        """
        waiting = _verdicts.read_returned_verdict(state)
        subject = run.subject.recorded()
        if waiting is not None and (waiting.round_n, waiting.verdict, waiting.subject) != (
            run.round_n, _verdicts.APPROVED, subject,
        ):
            waiting = None
        return cls(waiting, subject, gate_run=gate_run)

    def lands(
        self, gh: GitHubClient, issue: Issue, state: PinnedState, write: _commits.ReportWrite,
    ) -> bool | None:
        """Commit what `state` staged as `write` over `issue`'s pinned comment, guarded; whether it landed.

        Through the guarded commit every write of the tail lands through
        (`squash_writes.lands`), decided on `HELD_ON` as the tick last synced
        with the comment. What landed is the comment the tail last wrote: a
        copy to its depth, since the state in hand goes on being staged on
        after the write, and a record it changes in place would otherwise read
        as the comment having changed it. What did not land wrote nothing, and
        the caller makes nothing that depends on it: None where the comment
        has no room for the candidate it would send -- past what one comment
        holds, or refused by the write's own check of its room
        (`write.admits`) -- False otherwise. A refusal naming a record the
        tail holds that moved under the commit itself is answered as a move
        `_holds_its_records` catches: what the tail posted is recorded over
        the comment as it stands then, and the verdict it holds retired where
        that record is one the approval was proved over.
        """
        landed = _squash_writes.lands(gh, issue, state, write)
        if landed.status is _commit_models.CommitStatus.COMMITTED:
            self.comment = copy.deepcopy(state.data)
            return True
        if landed.refusal in _NO_ROOM:
            return None
        durable = None
        if HELD_ON.intersection(landed.fields):
            durable = _review_comment._read(gh, issue, state, _UNLANDED)
        if durable is not None:
            proved = _PROVED_OVER.intersection(landed.fields)
            kept = self if proved else replace(self, verdict=None)
            _records_what_it_posted(gh, issue, state, durable, kept)
        return False

    def settles(self, gh: GitHubClient, issue: Issue, state: PinnedState, carried, write: _commits.ReportWrite) -> bool:
        """Land `write` with what `carried` owes the head staged beside it; whether it landed.

        `carried` is the decision on the evidence the approval rests on
        (`squash_evidence.SquashEvidence`), staged onto `state` and owned by
        the write that carries it. A carry is held to the complete candidate
        that write sends (`SquashEvidence.admits`): where the fresh comment --
        every write another road made since included -- has no room to record
        it, or to settle it, it is not recorded owed and unpublishable, but
        invalidated in its place, in a commit of its own over `state` as it
        stood before the carry was staged (`SquashEvidence.without_room`),
        which carries no transaction and so may fit where the carry did not.
        A decision that staged no carry is not retried: what it writes is
        already the least the write can carry.
        """
        unstaged = copy.deepcopy(state.data)
        carried.stages(state, issue.number)
        carrying = write.owning(*carried.writes).admitting(carried.admits)
        landed = self.lands(gh, issue, state, carrying)
        if landed is not None or carried.carry is None:
            return bool(landed)
        state.data = unstaged
        carried = carried.without_room()
        carried.stages(state, issue.number)
        carrying = write.owning(*carried.writes)
        return bool(self.lands(gh, issue, state, carrying))

    def follows(self, gate):
        """`gate`, its client holding each write of its issue's pinned comment to the records in hand, and following it.

        Handed to the squash, which writes the state in hand whole and whose
        reply does not say whether it wrote (`squash_writes`): each write is
        asked first whether the comment still carries the report,
        pull-request, verdict, and evidence records in hand, laid over it
        (`_holds_its_records`), and landed as a guarded commit of the squash's
        own records beside what the tick staged; once it lands, it is the
        comment the tail last wrote, and where it does not, that reading and
        the state are left as the write found them.
        """
        holds = partial(_holds_its_records, gate.gh, gate.issue, purpose=_SQUASH_WRITE, held=self)
        lands = partial(self.lands, gate.gh, gate.issue, write=_THROUGH)
        return _squash_writes.followed(gate, holds, lands, self)

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
    """Whether the comment still carries the report, pull-request, verdict, evidence, and approval records `state` does.

    Asked ahead of each write an approval's tail makes behind requests of its
    own, `purpose` naming the write. The review subjects and the approval's
    evidence claim (`review_comment._APPROVAL_RECORDS`) -- which the tail
    stages the last two of itself -- and the report debt a review subject
    stands only without are measured from `held.comment`, the comment as the
    tail last read or wrote it, the reading every proof since was taken over:
    a subject another road replaced or removed meanwhile is one the evidence
    carried or proved for the move may no longer answer for, a claim removed
    or replaced leaves a carry answering on nobody's word, and a report owed is
    one the pull request does not carry as the approval read it, whatever
    `state` still spells. So are the park and the collapse record and its
    handoff (`_HELD_APART`), which the tail clears and ends itself: laid over
    `state` from another road's write, the tail's next write would clear a park
    a human is to answer, or end a collapse the recovery is to finish, unseen.
    Where the records stand, `state` is laid over the comment as read,
    measured from `held.comment` -- or, where that is None, taken whole over
    it, only the ledger of the orchestrator's own comments merged
    (`review_comment._Reread.lays_over`) -- and that reading is what the next
    one is measured from. Where they moved, nothing `state` holds is written
    over them but what the tail posted -- and the end of the verdict it holds,
    where a record the approval was proved over moved
    (`_records_what_it_posted`) -- and `state` is withheld from every
    whole-state write behind this. A comment that will not read, or is no
    longer the one `state` was read from, is left as it stands.
    """
    durable = _review_comment._read(gh, issue, state, purpose)
    if durable is None:
        return False
    measured = state.data if held.comment is None else held.comment
    proved = _review_comment._moved(durable.data, state.data, _HELD_RECORDS) or _review_comment._moved(
        durable.data, measured, _APPROVED_OVER,
    )
    apart = held.comment is not None and _review_comment._moved(
        durable.data, held.comment, _HELD_APART,
    )
    if proved or apart:
        log.warning(
            "issue=#%s its pinned comment does not carry the developer report, "
            "pull request, verdict, verification evidence, review subject, approval "
            "claim, report debt, park, or collapse records this tick holds, so it will "
            "not %s; recording only the comments it posted, and retiring the verdict it "
            "holds where what moved is a record its approval was proved over",
            issue.number, purpose,
        )
        state.withheld = True
        _records_what_it_posted(
            gh, issue, state, durable, held if proved else replace(held, verdict=None),
        )
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
    nobody's post. Committed guarded by `durable` (`_POSTED`), decided on the
    verdict as it reads there and owning only the ledger and that verdict, so
    every other field is the fresh reading's. Nothing is written where neither
    changes the comment, or where the comment has no room for what does or
    moved the verdict under the commit.
    """
    ledger = durable.get(_comments._ORCH_COMMENT_IDS)
    posted = state.get(_comments._ORCH_COMMENT_IDS)
    if not isinstance(posted, list):
        posted = []
    ours = sorted(entry for entry in posted if _state._is_whole(entry))
    _comments._track_orchestrator_comment(durable, *ours)
    retired = _verdicts.drops_the_verdict(durable, only=held.verdict)
    if durable.get(_comments._ORCH_COMMENT_IDS) != ledger or retired:
        _squash_writes.lands(gh, issue, durable, _POSTED)


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
