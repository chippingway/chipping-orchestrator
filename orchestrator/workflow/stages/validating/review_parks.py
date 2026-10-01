# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The parks a returned reviewer's verdict takes when it may not be acted on, and the funnel every such park takes.

Two refusals stop a verdict of a subject that still stands, and both are the
reviewer's round to redo rather than a developer's to answer. An approval that
relies on no evidence that passed and is current parks under
`reviewer_unverified` (`parks_unverified`) before anything acts on it. A
verdict the pinned comment has no room to persist (`NO_ROOM`), or that would
not read back as written (`UNREADABLE`), parks under `reviewer_unrecorded`
(`parks_unrecorded`) before anything is published or acted on: a disposition
nothing durable backs would be answered again by a second reviewer the moment
the tick died, which is the rerun the persisted verdict exists to prevent. The
two causes are spelled here, and the disposition service answers with one of
them (`review_disposition.Prepared.unrecorded`), because the park's notice
asks a different thing of a human for each: room freed on the pinned comment
is what lets a verdict with no room be recorded, and it does nothing for one
in words no record can carry, which a fresh reviewer simply writes again. No
live round parks here yet: the disposition service asks for either park, and
no live round reaches it -- only the recovery of a record an issue already
carries (`review_resume`), which may park a waiting approval unverified but
never persists a verdict, so never parks one unrecorded.

Neither retries itself. A bare `/orchestrator continue` buys a fresh reviewer
(`awaiting._reviewer_retry_awaiting_action`), and a reply with words in it is
requirements the report never saw, which reach the developer first as on every
reviewer-side park.

Both go down through `parks_over_the_subject`, since each is a park of a
reviewed subject that only means anything while that subject stands -- and so
does the park a failed verify gate takes over an approval (`approval`, worded
by `verify`), holding the approval of its run's round and subject where one
waits and reporting no agent's run, since a failure over a head nobody
reviewed is a fresh reviewer's to answer rather than a human's. Each names
the verdict it holds, the only one it may drop, rather than taking whatever the
comment has waiting: an unverified approval's park holds the approval its run
returned -- the waiting verdict of that round and subject, and nothing is
posted or written where none waits -- and an unrecorded verdict's park holds
none. A park is measured before its notice is posted, at its own write -- its
flags beside the notice's ledger entry and the watermark it stamps, each at the
widest id, and the verdict it refuses dropped -- since a notice posted over a
park GitHub then refuses leaves no park durable, and for a verdict nothing
recorded the next tick's reviewer answers the round again. The write that keeps
a waiting verdict instead, where nothing behind the notice proves a move, can
be the wider of the two, and is measured behind the notice with the rest:
measured up front, a waiting approval on a nearly full comment would never be
parked, and nobody would ever be told. A comment with no room for the park
beside what the returned run staged takes it over the comment as it stands
instead: the run's usage and session go unrecorded, a smaller loss than a park
that never lands. That reading is one more request, so where it no longer
carries the records the tick last read the verdict stands on, nothing is posted
or written, and the next tick answers what moved. One with no room even for the
park posts and writes nothing, and says so.

The notice is a request of its own, long enough for a push or another road's
settlement to land, and a park over either is a human asked to answer for a
review of work the pull request no longer carries. So the subject is resolved
again behind it, and the comment read last against the one the tick last read
or wrote (`review_comment._records_stand`) -- the state an unverified
approval's park began over, the reading a returned run was resolved over for an
unrecorded verdict's -- so what the returned run staged is this tick's own and
lands with the park. A report, verdict, or pull-request record moved there, or
an evidence record another road recorded or settled there, like a head read
whole that is another, lands no park: the write drops the verdict held, and the
next tick's reviewer is handed the subject as it stands. A subject nobody could
read is no proof it moved, nor that it still stands: it lands no park either,
and the verdict is left waiting for a later tick to resolve again. A notice
nothing identified may have reached nobody, so no park lands behind it either,
and where nothing moved the verdict waits as it was for a later tick to park
again rather than a human being held to a question nobody may have seen; a
move proved behind it still drops the verdict held, since no notice makes a
review of work the pull request no longer carries one to ask a human about. An
identified notice stays recorded as the orchestrator's own whichever way.

A comment that will not read writes nothing, and nor does a write that,
carrying what moved there, no longer fits: another road's write can spend the
room the park was measured with, and the write keeping a waiting verdict was
never measured before the notice. The verdict waits then, for a later tick
whose notice asks again. Only a park that lands sets the flags and drops the
verdict it refuses -- an unrecorded verdict's park holds none, and drops no
record it finds, one no reader takes included -- and it reports the human wait
(`park_awaiting_human`) only once its write is down, since that record is the
moment the issue enters one. The write that lands is composed over the comment
as it stands whichever way the records went, so a field another road wrote
behind the notice -- a round spent by a reply -- is kept rather than written
back over by the state in hand, one both moved keeps both moves where they add
up or only advance -- the run's usage beside that road's, the thread read as
far as either read it (`state._keeps_both_moves`) -- and the ledger of the
orchestrator's own comments is merged, the notice among them.

The park a failed squash takes (`parks_the_failed_squash`) is filed here too,
beside the funnel rather than through it: the recovery of a squash an earlier
tick did not finish reaches it with no reviewer run, so behind its notice it is
held to the report, pull-request, verdict, and evidence records in hand
(`handoff._holds_its_records`) rather than to a run's reading -- and to the
subject the approval behind the squash was of, where one was. It is measured
before its notice, keeping any verdict it does not retire -- a later round's
on that recovery road -- and lands only behind a notice that was identified,
over that subject still standing, as the funnel's parks do. Where the records
moved behind the notice, nothing but the notice's ledger entry and the end of
the verdict held is written; where the subject moved, the verdict held is
dropped and no park lands; and where the subject would not read, or the notice
left no id, what the squash left is written with the verdict kept and no park.
It is never taken over the comment as it stands with less beside it: its write
is what makes the squash's own record drop durable, so a comment with no room
for it is posted on and written to not at all -- the tick that died before its
write, which the squash recovery already answers.
"""
from __future__ import annotations

import logging
from dataclasses import replace

from github.Issue import Issue

from orchestrator import config
from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    comments as _comments,
    guards as _guards,
    park_watermarks as _park_watermarks,
    report_record_state as _report_record_state,
    report_record_values as _record_values,
)
from orchestrator.workflow.stages.validating import (
    handoff as _handoff,
    models as _models,
    review_comment as _review_comment,
    review_coverage as _review_coverage,
    review_records as _review_records,
    review_verdicts as _verdicts,
    state as _state,
)
from orchestrator.workflow.state import stage_name

log = logging.getLogger("orchestrator.workflow")

_RETRY = "reply `/orchestrator continue` to run a fresh reviewer."

# Why a returned verdict went unrecorded, in words for the park that answers it.
UNREADABLE = "its verdict would not read back as written (words UTF-8 cannot carry, for example)"

NO_ROOM = "the pinned comment has no room for its verdict or the verification evidence it declared"

_AWAITING_HUMAN = "awaiting_human"

# The agent role the reviewer's own parks are reported as.
_REVIEWER = "reviewer"

# What a park of a verdict stands on in the comment: the report's records, the
# pull request the issue points at, the verdict itself, and the verification
# evidence. Any of them another road moved since the tick last read or wrote
# the comment is a subject nobody reviewed, or a verdict other than the one the
# park refuses.
_HELD_TO = (*_review_comment._VERDICT_RECORDS, *_review_comment._EVIDENCE_RECORDS)


def parks_unverified(
    gh: GitHubClient,
    issue: Issue,
    state: PinnedState,
    run: _models._ReviewerRun,
    refusal: str,
) -> None:
    """Park the approval `run` returned, relying on no valid evidence, `refusal` saying why, and drop it.

    The approval this park holds is the verdict `state` has waiting, and only
    where that is this run's -- an approval of the round and subject `run` was
    handed: any other verdict is not this park's to refuse or to drop, so
    where none is, nothing is posted or written. Measured against `state` as
    the park begins: the verdict is persisted and proved over the comment it
    carries, with nothing staged beside it.
    """
    waiting = _verdicts.read_returned_verdict(state)
    returned = (run.round_n, _verdicts.APPROVED, run.subject.recorded())
    if waiting is None or (waiting.round_n, waiting.verdict, waiting.subject) != returned:
        log.warning(
            "issue=#%d has no approval of its reviewer's round %s waiting to park "
            "as unverified; posting and writing nothing", issue.number, run.round_n,
        )
        return
    words = (
        "the reviewer approved without the verification evidence an approval "
        f"requires: {refusal}. The approval was not acted on; {_RETRY}"
    )
    parks_over_the_subject(
        gh, issue, state, replace(run, resolved_over=dict(state.data)),
        (_state._REASON_REVIEWER_UNVERIFIED, words, _REVIEWER, waiting),
    )


def parks_unrecorded(
    gh: GitHubClient,
    issue: Issue,
    state: PinnedState,
    run: _models._ReviewerRun,
    why: str,
) -> None:
    """Park a verdict that could not be persisted, `why` -- `NO_ROOM` or `UNREADABLE` -- saying why, acting on nothing.

    The notice asks for room on the pinned comment only where room is what
    refused the verdict. The park holds no verdict, since none was recorded,
    so it drops none: one the comment has waiting stays exactly as it is.
    `run.resolved_over` is the comment as the tick last
    read it, so what the returned run staged beside the verdict it could not
    persist -- its usage and session -- is this tick's own move and lands with
    the park.
    """
    remedy = "free room on the pinned comment, then " if why == NO_ROOM else ""
    words = (
        f"the reviewer's verdict could not be recorded on the pinned comment: {why}. "
        f"Nothing it returned was published or acted on; {remedy}{_RETRY}"
    )
    parks_over_the_subject(gh, issue, state, run, (_state._REASON_REVIEWER_UNRECORDED, words, _REVIEWER, None))


def parks_over_the_subject(
    gh: GitHubClient,
    issue: Issue,
    state: PinnedState,
    run: _models._ReviewerRun,
    park: tuple[str, str, str | None, _verdicts.ReturnedVerdict | None],
) -> None:
    """File `park` over the subject `run` was handed, in one write, where it fits and that subject still stands.

    `park` is the reason, the notice's words, the agent role the park is
    reported as, with the round, session, and pull request it ran for -- a
    park of no agent's (None) reports its reason alone -- and the verdict the
    park holds, the only one it drops: named by the caller rather than read
    off whatever the comment has waiting, and None for a park that holds
    none, which drops nothing.

    `run.resolved_over` is the comment as the tick last read or wrote it, with
    the report and verdict records the verdict was proved over. Behind the
    notice, a field the state in hand spells otherwise than that reading is
    this tick's own to write -- what the returned run staged among them -- and
    one the comment spells otherwise is another road's, carried.
    """
    reason = park[0]
    parked = state
    if not _park_fits(state, reason, park[3]):
        # With no room beside what the returned run staged, the park is taken
        # over the comment as it stands, the run's usage and session unrecorded.
        parked = _review_comment._read(gh, issue, state, "park a verdict with no room for what its run staged")
    if parked is None:
        return
    if parked is not state and _review_comment._moved(parked.data, run.resolved_over, _HELD_TO):
        log.warning(
            "issue=#%d its pinned comment moved what its reviewer's verdict "
            "stands on before the %s park was posted; posting and writing "
            "nothing", issue.number, reason,
        )
        return
    if not _park_fits(parked, reason, park[3]):
        log.error(
            "issue=#%d has no room on its pinned comment even for the %s park; "
            "posting and writing nothing", issue.number, reason,
        )
        return
    # A park over the comment as it stands writes nothing but that reading,
    # so that reading is what it is measured against.
    baseline = dict(run.resolved_over if parked is state else parked.data)
    lands = _behind_the_notice(gh, issue, parked, replace(run, resolved_over=baseline), park)
    # What moved behind the notice was carried whole, and another road's
    # write can have spent the room this one was measured with.
    if lands is None or not _report_record_state.fits_the_comment(parked.data):
        log.error(
            "issue=#%d wrote nothing behind the notice of its %s park: its "
            "pinned comment would not read, or has no room for that write "
            "beside what moved there", issue.number, reason,
        )
        return
    gh.write_pinned_state(issue, parked)
    if lands:
        gh.emit_event(
            "park_awaiting_human",
            issue_number=issue.number,
            stage=stage_name(gh.workflow_label(issue)),
            reason=reason,
            **_guards._screened_correlation({} if park[2] is None else {
                "agent_role": park[2],
                "session_id": state.get(_review_records._LAST_REVIEW_SESSION_ID),
                "review_round": run.round_n,
                "retry_count": _guards._safe_int(state.get("retry_count")),
                "pr_number": _guards._safe_int(run.pr_number),
            }),
        )


def parks_the_failed_squash(
    gh: GitHubClient,
    issue: Issue,
    state: PinnedState,
    words: str,
    held: _handoff._Held,
) -> None:
    """File the park a failed squash takes, in one write, where it fits and the records in hand stand behind its notice.

    `words` say where the failure left the branch (`approval`), and `held` is
    what the squash's tail holds (`handoff._Held`): the verdict of the
    approval whose squash it was, the only one the park retires -- the
    recovery of a squash an earlier tick did not finish holds none -- the
    subject that approval was of, resolved again behind the notice ahead of
    the comment's own reading, and the comment as the tail last read it, which
    the park's write is laid over. A push or an edit landing while the notice
    was posted is work nobody reviewed, so no park asks a human about it and
    the verdict is dropped for a fresh reviewer; a subject nobody could read
    lands no park either, and keeps the verdict.
    """
    reason = _state._REASON_SQUASH_FAILED
    if not _park_fits(state, reason, held.verdict):
        log.error(
            "issue=#%d has no room on its pinned comment for the %s park; "
            "posting and writing nothing", issue.number, reason,
        )
        return
    posted = _posts_the_notice(gh, issue, state, words)
    stands = True
    if held.subject is not None:
        stands = _review_coverage._subject_still_stands(gh, issue, state, held.subject)
    if not _handoff._holds_its_records(gh, issue, state, "park its failed squash over the records it holds", held):
        return
    lands = posted is not None and stands is True
    if lands:
        state.set(_AWAITING_HUMAN, True)
        state.set(_state._PARK_REASON, reason)
    else:
        log.warning(
            "issue=#%d landed no %s park: its notice left no id, or the subject "
            "its approval is about moved or would not read behind it; writing "
            "what the squash left without parking", issue.number, reason,
        )
    if lands or stands is False:
        _verdicts.drops_the_verdict(state, only=held.verdict)
    if not _report_record_state.fits_the_comment(state.data):
        log.error(
            "issue=#%d has no room on its pinned comment for the %s park beside "
            "what moved there behind its notice; writing nothing", issue.number, reason,
        )
        return
    gh.write_pinned_state(issue, state)
    if lands:
        gh.emit_event(
            "park_awaiting_human",
            issue_number=issue.number,
            stage=stage_name(gh.workflow_label(issue)),
            reason=reason,
        )


def _behind_the_notice(
    gh: GitHubClient,
    issue: Issue,
    parked: PinnedState,
    run: _models._ReviewerRun,
    park: tuple,
) -> bool | None:
    """Post the park's notice, then settle its write over the subject standing behind it; None to write nothing.

    `park` is as `parks_over_the_subject` takes it, the verdict it holds the
    only one it drops. True where the park lands: the notice was posted
    and identified, the subject resolved again whole as the one `run` was
    handed, and no record the park stands on moved on the comment since `run`
    read it. False where it does not: that verdict is dropped where the
    subject or those records moved -- one another road put in its place is
    left for that road -- whether or not the notice left an id, and left as it
    waited where nothing proved a move and the subject would not read or the
    notice left no id.
    """
    posted = _posts_the_notice(gh, issue, parked, park[1])
    stands = _review_coverage._subject_still_stands(gh, issue, parked, run.subject.recorded())
    # Laid over the comment as it stands whether or not the records moved:
    # the notice is time another road can write any field -- a round spent by
    # a reply -- and the park would write the state in hand back over it.
    reread = _review_comment._records_stand(gh, issue, parked, run.resolved_over, persisted=True)
    if reread is None:
        return None
    # Evidence another road recorded or settled behind the notice is a subject
    # nobody reviewed, as surely as a push.
    moved = _review_comment._moved(reread.read, run.resolved_over, _HELD_TO)
    if not moved and stands is None:
        log.info(
            "issue=#%d could not read the subject its reviewer's verdict is "
            "about behind its park notice; keeping the verdict for a later "
            "tick rather than parking", issue.number,
        )
        return False
    if not moved and stands and posted is None:
        log.warning(
            "issue=#%d could not confirm the notice of its %s park was posted; "
            "keeping the verdict for a later tick rather than parking with "
            "nobody told", issue.number, park[0],
        )
        return False
    _verdicts.drops_the_verdict(parked, only=park[3])
    if moved or not stands:
        log.info(
            "issue=#%d the subject its reviewer's verdict is about moved while "
            "its park notice was posted; dropping the verdict for a fresh "
            "reviewer rather than parking", issue.number,
        )
        return False
    parked.set(_AWAITING_HUMAN, True)
    parked.set(_state._PARK_REASON, park[0])
    return True


def _posts_the_notice(gh: GitHubClient, issue: Issue, parked: PinnedState, words: str) -> int | None:
    """Post the park's notice and record the thread read through it; the notice's id, or None.

    The notice of the park a failed squash takes as well
    (`parks_the_failed_squash`), and of the park a handed change request's
    developer launch takes where nothing says whether it ran
    (`review_handoffs.HandedLaunch.parks`), which is measured through
    `_park_fits` too and settles behind its notice for itself, since it holds
    the feedback anchor its continue replays. Read only as far as the orchestrator's own
    comments go (`park_watermarks`), since a park follows a run long enough
    for a human to have written something nobody has read -- which is also
    why the mark is harmless where no park lands behind the notice.
    """
    said_before = _comments._orchestrator_ids(parked)
    notice = _comments._post_issue_comment(gh, issue, parked, f"{config.HITL_MENTIONS} {words}")
    _park_watermarks._stamp_read_this_far(gh, issue, parked, said_before)
    return getattr(notice, "id", None)


def _park_fits(state: PinnedState, reason: str, owned: _verdicts.ReturnedVerdict | None) -> bool:
    """Whether the comment has room for the park's own write on `state`, measured at its widest.

    That write sets the park's flags beside its notice's ledger entry and the
    watermark it stamps, each at the widest id, and drops only `owned`, the
    verdict it holds, and only where it is still the one waiting -- so it is
    measured keeping any other, and keeping whatever record stands where it
    holds none. The writes a park may end in instead -- the verdict dropped
    where its subject moved, or kept where nothing proved a move -- are
    measured behind the notice, with what moved there, and not made where they
    do not fit.
    """
    widest = _record_values.MAX_RECORDED_NUMBER
    landed = PinnedState(comment_id=state.comment_id, state_data=dict(state.data))
    _comments._reserve_comment_slot(landed, widest)
    landed.set("last_action_comment_id", widest)
    _verdicts.drops_the_verdict(landed, only=owned)
    landed.set(_AWAITING_HUMAN, True)
    landed.set(_state._PARK_REASON, reason)
    return _report_record_state.fits_the_comment(landed.data)
