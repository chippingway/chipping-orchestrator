# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The pinned comment a review is bound to, and read against when it returns.

A validating tick that resolves its reviewer's subject does so from the state
it read when it began, and a report settling since -- a later revision on the
very head, by another road -- is recorded on the pinned comment and nowhere in
hand, while the report the tick resolved still reads, exactly as it settled,
where it was. Nothing at that report's own location tells the two apart; only
the records on the comment do.

So `review_report` binds a resolved subject only to a comment read afresh that
carries the report records the state in hand carries, and points the issue at
the pull request the subject was resolved at (`_resolved_over`), and the
in_review ready ping and the unmergeable park beside it ask the same once
mergeability is read (`_records_in_hand`); the squash tail holds each of its
writes to those records and more (`handoff._holds_its_records`). Where the
comment moved them, or will not read or parse, the answer is the one that hands
nothing over and writes nothing: every write from there would be laid over
records the tick never read, putting back the report they replaced. So is a
fresh reading of another comment than the one the state in hand was read from
-- the pinned comment replaced, or gone -- since the tick's write goes to the
comment it read and would pin a second one. The reading that agreed goes on
with the subject, and is laid over the state in hand before the round writes
anything, measured from the comment as the tick read it
(`_ResolvedSubject.lays_over`): what another road wrote while the subject was
resolved -- a run it charged and folded, a notice it posted -- is on it and
nowhere in hand, and every later reading is measured from it, so none would see
that move. It then takes in the round's own launch charge once that charge is
down (`_ResolvedSubject.carrying`): the charge lands on the state in hand only
the fields it wrote, which read against the comment without them would be taken
for this tick's own, and written back over a later charge another road wrote.

`_records_stand` reads the comment against that reading again, as the reviewer
returns, once more behind the subject resolved again for its verdict, and once
more behind that after an approval is verified, before anything the run leaves
is written -- a park for a timeout or a missing verdict as much as the record of
a verdict. It watches the report's records and the pull request the issue
points at, since a verdict about one pull request is no review of another the
issue points at now. The reviewer's return, the approval arc behind its
verify gate, the approval proof, the disposition service and the
change-request handoff behind it wherever they hold a verdict to its subject
(`review_coverage._verdict_still_stands`), and the recovery of a verdict an
earlier tick left waiting (`review_resume`) ask it of more (`persisted`): the
returned verdict persisted (`review_verdicts`) beside them, since one another
road persisted, dropped, or replaced since is no longer the one any write
behind this may act on or write over -- the disposition measures a returned
run from the return's reading on, so a verdict another round persisted while
the reviewer ran is caught there or nowhere. Records that moved
refuse the verdict. Either way every write made from the state behind the
reading is laid over the comment as it stands, so everything the comment
changed since is carried onto the state in hand: a later report settled over the one the reviewer was handed, the
workflow verification evidence another road recorded or settled -- which that
service holds the verdict's evidence claim to, over the comment as read last,
rather than calling a settlement of the very evidence it claims a move -- a
round a reply bought, a run another road charged, or the thread it read
through, none of which a write may put back. Where the records stand, a field
this tick changed too is its own write's to say. A field both changed that adds
up or only advances keeps both changes instead -- a usage total, its cost tags,
a comment-id watermark (`state._keeps_both_moves`) -- and the ledger of the
orchestrator's own comments is merged rather than carried or kept: every road
adds to it, and an id either side recorded is a comment every later prompt has
to know as the orchestrator's, kept once among the newest its bound holds --
a ledger already past the bound is cut to it even where the merge adds nothing
-- while an entry naming no comment is dropped from both sides, so no later
scan of the ledger fails on it. The
reading hands back the comment as it found it (`_Reread.read`), which is what a
later reading of the same run is measured against, since a move this tick kept
beside another road's, measured again from the older comment, would be kept
twice. A road that makes further requests behind the last reading and writes
after them -- a change request's developer run -- lays the state in hand whole
over whatever landed in between, which only a reading of its own would keep;
the approval's squash tail takes one ahead of each of its writes
(`handoff._holds_its_records`), save across the squash itself. Records are
compared as the comment's JSON spells them, so one written
`null` where there was none, or a revision spelled `true` where it was `1`, is
a move. A comment that will not read or parse, or is no longer the one the
state was read from, carries nothing, and the answer is the one that writes
nothing: the run is charged, and the next tick spawns a reviewer over whatever
the comment carries then.

A tick settling the round a reply bought asks its reading whether another road
recorded a park there meanwhile (`_Reread.parks_anew`): its flags moved, which
that tick keeps as the reading spells them (`_Reread.keeps_the_park`). A park
recorded again for the same reason shows only in its notice, which nothing on
the comment names, and a comment another road posted that names the human a
park waits on may be one, so the tick writes nothing and asks again.

Nothing here parks or posts.
"""
from __future__ import annotations

import json
import logging
from collections.abc import Iterable
from dataclasses import dataclass, replace
from types import MappingProxyType

from github.Issue import Issue

from orchestrator import config
from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    comments as _comments,
    pinned_commit as _pinned_commit,
    report_records as _records,
    review_evidence_prompts as _evidence_prompts,
    review_subjects as _review_subjects,
    verification_records as _evidence_records,
)
from orchestrator.workflow.stages.validating import (
    approved_evidence as _approved_evidence,
    review_verdicts as _verdicts,
    state as _state,
)

log = logging.getLogger("orchestrator.workflow")

# Every record a developer report's transaction moves on the pinned comment:
# one in flight, the delivery it binds, and the settled pair a settlement
# replaces.
_REPORT_RECORDS = (
    _records.PENDING_REPORT,
    _records.DELIVERED_REPORT,
    _records.CURRENT_REPORT,
    _records.REPORT_HANDOFF,
)

# The pull request the issue points at, which every road posting or pushing
# for it reads off the pinned comment.
_PR_NUMBER = "pr_number"

# What a subject is bound to beyond the report when it is resolved: the pull
# request the issue points at, which it was resolved at.
_BOUND_RECORDS = (*_REPORT_RECORDS, _PR_NUMBER)

# What a persisted verdict stands on in the comment beyond the report: the
# pull request the issue points at, and the returned verdict itself. The
# evidence it claims is judged by the claim.
_VERDICT_RECORDS = (*_BOUND_RECORDS, _verdicts.RETURNED_VERDICT)

# Every record a verification transaction, its settlement, or its retirement
# writes.
_EVIDENCE_RECORDS = (
    _evidence_records.CURRENT_EVIDENCE,
    _evidence_records.PENDING_EVIDENCE,
    _evidence_records.EVIDENCE_HISTORY,
    _evidence_records.EVIDENCE_HANDOFF,
    _evidence_records.REVISION_FLOOR,
)

# The records an approval and the evidence it rests on answer through: the
# review subject the latest reviewer was handed, the one the reviewer that
# returned was handed, the one the approval covers, and the evidence claim the
# approval rests on -- which evidence carried across its squash answers for
# its head on. Every road about to move the approval on watches them across
# its requests, so one another road replaced or removed meanwhile is neither
# acted on nor written back over.
_APPROVAL_RECORDS = (
    _review_subjects.REVIEW_SUBJECT,
    _review_subjects.RETURNED_SUBJECT,
    _review_subjects.APPROVED_SUBJECT,
    _approved_evidence.APPROVED_EVIDENCE,
)

# What `_records_in_hand` holds a road acting on an approval to.
_IN_HAND_RECORDS = (*_BOUND_RECORDS, *_EVIDENCE_RECORDS, *_APPROVAL_RECORDS)

# What `_records_stand` watches: the report's records and the pull request
# the issue points at, or -- for a caller holding a persisted verdict -- the
# verdict beside them.
_WATCHED = MappingProxyType({False: _BOUND_RECORDS, True: _VERDICT_RECORDS})

# What a field the comment does not carry reads as, apart from one it carries
# as `null`.
_ABSENT = object()

# A park as the pinned comment records it: whether one stands, and why.
_PARK = ("awaiting_human", "park_reason")


@dataclass(frozen=True)
class _ResolvedSubject:
    """A subject a reviewer may be handed, and the comment it was resolved over."""

    subject: _review_subjects.ReviewSubject
    # The pinned comment as it was read once the subject was resolved, which
    # carries the very report records the subject was resolved from: what
    # the verdict's return measures the comment against.
    resolved_over: dict
    # The workflow verification evidence proved current for that subject,
    # handed over beside it once the launch is recorded; None for none.
    evidence: _evidence_prompts.HandedEvidence | None = None

    def lays_over(self, state: PinnedState, read: dict) -> None:
        """Carry onto `state` what the comment this subject was bound to changed since the tick read it as `read`.

        The binding reading is the first the round takes again, and every
        later one is measured from it: a run another road charged and folded
        while the subject was resolved, the thread it read through, a notice it
        posted, are on it and nowhere in hand, and left out of `state` here no
        later reading would see them move -- the round's writes would put the
        values the tick read back over them. The report records and the pull
        request agree by then (`_resolved_over`), so a field both changed is
        this tick's own to say, or keeps both moves where they add up or only
        advance (`_Reread.lays_over`). A field the comment already spells as
        `state` does -- one this tick wrote earlier in the tick -- has nothing
        to carry, and measured from `read` it would read as both roads' move
        and be kept twice. No road ahead of a reviewer on its tick folds a run
        of its own, so the totals `state` holds are the ones the tick read or
        wrote.
        """
        fields = {*read, *self.resolved_over, *state.data}
        agreed = fields.difference(_moved(self.resolved_over, state.data, fields))
        since = {field: spelled for field, spelled in read.items() if field not in agreed}
        since.update(
            (field, self.resolved_over[field]) for field in agreed if field in self.resolved_over
        )
        _Reread(stood=True, read=self.resolved_over).lays_over(state, since)

    def carrying(self, before: dict, state: PinnedState) -> _ResolvedSubject:
        """This subject, over its comment with every field `state` changed since `before` taken into it.

        For a write that lands on `state` only the fields it wrote on the
        comment -- the run circuit's launch charge -- whatever `state` changed
        since `before` is what the comment says now. Left out of the reading,
        each would read as a field this tick staged and never wrote, and a
        later reading keeping this tick's own moves would write it back over
        a newer one another road wrote. Compared as the comment's JSON spells
        them (`_moved`).
        """
        comment = dict(self.resolved_over)
        for field in _moved(state.data, before, {*before, *state.data}):
            written = state.data.get(field, _ABSENT)
            if written is _ABSENT:
                comment.pop(field, None)
            else:
                comment[field] = written
        return replace(self, resolved_over=comment)


@dataclass(frozen=True)
class _Reread:
    """What reading the comment again against the one a subject was measured over found."""

    # Whether the records the subject stands on are where they were.
    stood: bool
    # The comment as this reading found it, which is what a later reading of
    # the same run is measured against: this one already took in every move
    # the comment made up to here, and a move this tick kept beside another
    # road's, measured again from the older comment, would be kept twice.
    read: dict

    def lays_over(self, state: PinnedState, since: dict) -> None:
        """Carry onto `state` what the comment changed since `since`, as the write behind this reading has to keep it.

        Every field the comment changed, save one `state` changed too: that
        keeps both changes where they add up or only advance
        (`state._keeps_both_moves`), and is otherwise this tick's own where
        the records stood and the comment's where they moved. The ledger of
        the orchestrator's own comments is merged instead, every entry either
        side holds that names no comment dropped.
        """
        # Every field the comment changed since `since`, as `_moved` spells a
        # change: a field Python calls equal -- `true` over `1` -- is still
        # carried rather than written back over by the run's own write...
        fields = _moved(
            self.read, since, {*since, *self.read} - {_comments._ORCH_COMMENT_IDS},
        )
        # What the comment says of each of them is the comment's from here on,
        # however this tick's own move of one is kept beside it: a guarded
        # commit behind this reading counts from it rather than as the tick's.
        _pinned_commit.takes_in(
            state, self.read, {*fields, _comments._ORCH_COMMENT_IDS},
        )
        # ...save one this tick changed too.
        for field in _moved(state.data, since, fields):
            if _state._keeps_both_moves(state, field, self.read, since) or self.stood:
                fields.remove(field)
        for field in fields:
            written = self.read.get(field, _ABSENT)
            if written is _ABSENT:
                state.data.pop(field, None)
            else:
                state.set(field, written)
        # The ledger is a set every road adds to, so it is merged rather than
        # carried or kept whole: an id either side recorded is a comment every
        # later prompt has to know as the orchestrator's, and one this state's
        # own posts evicted is evicted again. An entry naming no comment -- a
        # hand edit -- is nobody's post, on either side: it is dropped rather
        # than read as one, or left for every later scan of the ledger to fail
        # on (`comments._orchestrator_ids`). What is left holds each id once,
        # within the bound, however long either side's ledger ran
        # (`comments._track_orchestrator_comment`).
        own = state.get(_comments._ORCH_COMMENT_IDS)
        if isinstance(own, list):
            state.set(_comments._ORCH_COMMENT_IDS, [entry for entry in own if _state._is_whole(entry)])
        elif own is not None:
            state.data.pop(_comments._ORCH_COMMENT_IDS)
        ledger = self.read.get(_comments._ORCH_COMMENT_IDS)
        if not isinstance(ledger, list):
            ledger = []
        _comments._track_orchestrator_comment(state, *sorted(
            entry for entry in ledger if _state._is_whole(entry)
        ))

    def parks_anew(self, gh: GitHubClient, issue: Issue, since: dict, posted: set[int]) -> bool | None:
        """Whether another road recorded a park on this reading since the comment read as `since`; None untold.

        `posted` is the orchestrator's comments this reading carries that the
        road asking never recorded -- another road's posts. A park recorded is
        its flags moved (`_PARK`). One standing for the very reason `since`
        had, flags alike, shows only in the notice it posted, and nothing on
        the comment names a notice: every park's notice opens by naming the
        human it waits on (`config.HITL_MENTIONS`), but so may a status line
        another road posts, so one of `posted` that does cannot be told from a
        park, and answers None -- as does a thread those comments are on that
        will not read -- for the caller to write nothing and ask again over
        the comment as it stands then. A comment that names nobody is no
        park's notice, and parks nothing.
        """
        if _moved(self.read, since, _PARK):
            return True
        if not (posted and self.read.get(_PARK[0])):
            return False
        try:
            thread = gh.comments_after(issue, min(posted) - 1)
        except Exception:
            log.exception(
                "issue=#%d could not read the comments another road posted while "
                "its park was answered, to tell a park's notice among them", issue.number,
            )
            return None
        addressed = any(
            said.id in posted and (said.body or "").startswith(config.HITL_MENTIONS)
            for said in thread
        )
        if addressed:
            log.warning(
                "issue=#%d another road posted a comment naming the human while its "
                "park was answered, which may be a park's notice; writing nothing", issue.number,
            )
            return None
        return False

    def keeps_the_park(self, state: PinnedState) -> None:
        """Put the park on `state` as this reading spells it, a flag it does not carry dropped."""
        _pinned_commit.takes_in(state, self.read, _PARK)
        for field in _PARK:
            state.data.pop(field, None)
            spelled = self.read.get(field, _ABSENT)
            if spelled is not _ABSENT:
                state.set(field, spelled)


def _resolved_over(
    gh: GitHubClient,
    issue: Issue,
    state: PinnedState,
    purpose: str = "bind the report its reviewer is handed",
) -> dict | None:
    """The comment a subject resolved from `state` is bound to, or None.

    None where the comment will not read or parse, is not the one `state` was
    read from, carries other report records than `state` does, or points the
    issue at another pull request than `state` does -- a subject resolved at
    one pull request bound to a comment naming another would be judged, and
    acted on, over the wrong one. The caller ends the tick without writing.
    `purpose` is what the caller was about to do, for the log.
    """
    durable = _read(gh, issue, state, purpose)
    if durable is None:
        return None
    if not _moved(durable.data, state.data, _BOUND_RECORDS):
        return dict(durable.data)
    log.warning(
        "issue=#%d its pinned comment does not carry the records this tick "
        "holds -- the developer report's, or the pull request it points at -- "
        "so it will not %s; writing nothing this tick", issue.number, purpose,
    )
    return None


def _records_in_hand(
    gh: GitHubClient, issue: Issue, state: PinnedState, purpose: str,
) -> bool:
    """Whether the comment carries the report, evidence, and approval records `state` does, and points where it does.

    Asked by a road about to act on an approval of the report `state` records
    as current, and to write `state` beside it, after requests long enough for
    another road to settle a later report or verification revision, record a
    later verification transaction, point the issue at another pull request,
    or replace or remove a review subject or the approval's evidence claim
    (`_APPROVAL_RECORDS`). False where it moved them, will not read or parse, or is no
    longer the comment `state` was read from; the caller then acts on nothing
    and writes nothing, so the next tick reads what the issue carries then and
    answers it -- rather than moving a label, or writing a pointer or a
    revision floor back, under an approval of work the issue no longer
    carries. `purpose` is what the road was about to do, for the log.
    """
    durable = _read(gh, issue, state, purpose)
    if durable is None:
        return False
    if not _moved(durable.data, state.data, _IN_HAND_RECORDS):
        return True
    log.warning(
        "issue=#%d its pinned comment does not carry the developer report, "
        "pull request, verification evidence, or approval records this tick "
        "holds, so it will not %s; writing nothing this tick", issue.number, purpose,
    )
    return False


def _records_stand(
    gh: GitHubClient,
    issue: Issue,
    state: PinnedState,
    resolved_over: dict,
    *,
    persisted: bool = False,
) -> _Reread | None:
    """Whether the comment still carries the records the subject had -- the report's, and a persisted verdict's.

    Its answer is `stood`: True where they stand, False where they moved and
    the verdict is not acted on. Either way the write behind this is laid over
    the comment as it stands: every field the comment changed since
    `resolved_over` is carried onto `state` -- evidence records included, which
    a caller holding a persisted verdict judges its claim over -- save, where
    they stand, one `state` changed itself, which is that write's own to say.
    A field both changed keeps both changes where they add up or only advance
    -- a usage total, its cost tags, a comment-id watermark
    (`state._keeps_both_moves`) -- and the ledger of the orchestrator's own
    comments is merged (`comments._track_orchestrator_comment`). `read` is the
    comment as this reading found it, for a later reading of the same run to
    be measured against. None where the comment will not read or parse, or is
    not the one `state` was read from, which carries nothing -- a record read
    back empty is no settlement to keep -- and the caller ends the tick without
    writing. It watches the report's records and the pull request the issue
    points at (`_BOUND_RECORDS`); `persisted` is for a caller holding a
    persisted verdict to its subject, and watches the verdict beside them
    (`_VERDICT_RECORDS`).
    """
    durable = _read(
        gh, issue, state, "see whether a report settled while the reviewer ran",
    )
    if durable is None:
        return None
    reread = _Reread(
        stood=not _moved(durable.data, resolved_over, _WATCHED[persisted]),
        read=dict(durable.data),
    )
    reread.lays_over(state, resolved_over)
    if not reread.stood:
        log.warning(
            "issue=#%d the records its reviewer's verdict stands on moved on the "
            "pinned comment since its subject was resolved; keeping them and not "
            "acting on the verdict", issue.number,
        )
    return reread


def _read(
    gh: GitHubClient, issue: Issue, state: PinnedState, purpose: str,
) -> PinnedState | None:
    """The comment `state` was read from, read afresh and parsed, or None logged.

    None as well where the fresh reading is another comment -- the pinned
    comment replaced, or gone -- since every write the tick makes goes to the
    comment `state` names: made over one that is no longer pinned, it would
    pin a second comment beside the one every later reader takes.
    """
    try:
        durable = gh.read_pinned_state(issue)
    except Exception:
        log.exception(
            "issue=#%d could not read its pinned comment to %s; ending the "
            "tick with nothing written", issue.number, purpose,
        )
        return None
    if not durable.parsed:
        log.error(
            "issue=#%d its pinned comment will not parse where it is read to "
            "%s; ending the tick with nothing written", issue.number, purpose,
        )
        return None
    if durable.comment_id != state.comment_id:
        log.warning(
            "issue=#%d its pinned comment is %s where this tick read %s, so it "
            "will not %s; ending the tick with nothing written",
            issue.number, durable.comment_id, state.comment_id, purpose,
        )
        return None
    return durable


def _moved(durable: dict, in_hand: dict, fields: Iterable[str]) -> list[str]:
    """The fields two readings of the comment spell differently.

    Compared as the comment's JSON spells them rather than as Python values,
    which call a field written `null` equal to one missing and a revision `1`
    equal to `true`: each of those is a different record to its reader, so a
    concurrent write of either is a move, not agreement.
    """
    return [
        field for field in fields
        if (field in durable, json.dumps(durable.get(field), sort_keys=True))
        != (field in in_hand, json.dumps(in_hand.get(field), sort_keys=True))
    ]
