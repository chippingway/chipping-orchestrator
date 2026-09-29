# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The parks a returned reviewer's verdict takes when it may not be acted on, and the funnel every such park takes.

Two refusals stop a verdict of a subject that still stands, and both are the
reviewer's round to redo rather than a developer's to answer. An approval that
relies on no evidence that passed and is current parks under
`reviewer_unverified` (`parks_unverified`) before the verify gate, the approval
record, or the squash. A verdict the pinned comment has no room to persist,
with the evidence transaction its commands were minted as, parks under
`reviewer_unrecorded` (`parks_unrecorded`) before anything is published or
acted on: a disposition nothing durable backs would be answered again by a
second reviewer the moment the tick died, which is the rerun the persisted
verdict exists to prevent.

Neither retries itself. A bare `/orchestrator continue` buys a fresh reviewer
(`awaiting._reviewer_retry_awaiting_action`), and a reply with words in it is
requirements the report never saw, which reach the developer first as on every
reviewer-side park.

No road files any park here yet, and each entry is called directly: the
dormant disposition service (`review_disposition`) answers a verdict it could
not persist, or an approval its evidence does not back, without parking, and
the approval arc (`approval`, `verify`) still files its failed verify gate's
and failed squash's parks itself.

Both, and the park a failed verify gate takes over an approval, go down
through `parks_over_the_subject`, since each is a park of a reviewed subject
that only means anything while that subject stands. A park is measured before
its notice is posted, at the widest it writes -- the notice's ledger entry and
the watermark it stamps at the widest id, beside the flags or beside the
verdict an unread subject leaves waiting -- since a notice posted over a write
GitHub then refuses leaves neither a verdict nor a park durable, and the next
tick's reviewer answers the round again. A comment with no room for the park
beside what the returned run staged takes it over the comment as it stands
instead: the run's usage and session go unrecorded, a smaller loss than a park
that never lands. One with no room even for that posts and writes nothing, and
says so.

The notice is a request of its own, long enough for a push or another road's
settlement to land, and a park over either is a human asked to answer for a
review of work the pull request no longer carries. So the subject is resolved
again behind it, and the comment read last against the one the tick last read
or wrote (`review_comment._records_stand`) -- the state an unverified
approval's park began over, the reading a returned run was resolved over for
an unrecorded verdict's, the verify gate's for a failed gate's -- so what the
returned run staged is this tick's own and lands with the park. A report or
verdict record moved there carries everything the comment changed since -- a
report settlement's spent round beside its records -- and, like an evidence
record another road recorded or settled there, the issue pointed at another
pull request, or a head read whole that is another, lands no park: the write
drops the verdict, and the next tick's reviewer is handed the subject as it
stands. A subject nobody could read is no proof it moved, nor that it still
stands: it lands no park either, and the verdict is left waiting for a later
tick to resolve again. A notice nothing identified may have reached nobody, so
no park lands behind it either, and the verdict waits as it was for a later
tick to park again rather than a human being held to a question nobody may
have seen. An identified notice stays recorded as the orchestrator's own
whichever way. A comment that will not read writes nothing, and nor does a
write that, carrying what moved there, no longer fits: another road's write
can spend the room the park was measured with. Only a park that lands sets the
flags, drops the verdict it refuses, and -- once its write is down -- reports
the human wait (`park_awaiting_human`), since that record is the moment the
issue enters one. The write that lands is composed over the comment as it
stands whichever way the records went, so a field another road wrote behind
the notice -- a round spent by a reply -- is kept rather than written back over
by the state in hand, and one both moved keeps both moves where they add up or
only advance -- the run's usage beside that road's, the thread read as far as
either read it (`state._keeps_both_moves`).

The park a failed squash takes (`parks_the_failed_squash`) is filed here too,
beside the funnel rather than through it: the recovery of a squash an earlier
tick did not finish reaches it with no reviewer run, so it is held behind its
notice to the report, evidence, and verdict records in hand
(`handoff._holds_its_records`) rather than to a subject. It is measured before
its notice -- keeping any verdict it does not retire, a later round's on that
recovery road -- and lands only behind one identified, as the funnel's parks
do, but is never taken over the comment as it stands: its write is what makes
the squash's own record drop durable, so a comment with no room for it is
posted on and written to not at all -- the tick that died before its write,
which the squash already answers.
"""
from __future__ import annotations

import logging

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

_AWAITING_HUMAN = "awaiting_human"

# The agent role the reviewer's own parks are reported as.
_REVIEWER = "reviewer"


def parks_unverified(
    gh: GitHubClient,
    issue: Issue,
    state: PinnedState,
    run: _models._ReviewerRun,
    refusal: str,
) -> None:
    """Park an approval that relies on no valid evidence, dropping the verdict it left.

    Measured against `state` as the park begins: the verdict is persisted
    and proved over the comment it carries, with nothing staged beside it.
    """
    words = (
        "the reviewer approved without the verification evidence an approval "
        f"requires: {refusal}. The approval was not acted on; {_RETRY}"
    )
    parks_over_the_subject(
        gh, issue, state, run.measured_over(state.data),
        (_state._REASON_REVIEWER_UNVERIFIED, words, _REVIEWER),
    )


def parks_unrecorded(
    gh: GitHubClient,
    issue: Issue,
    state: PinnedState,
    run: _models._ReviewerRun,
    why: str,
) -> None:
    """Park a verdict that could not be persisted, `why` in `review_disposition`'s words, acting on nothing.

    Measured against the reading the returned run was resolved over, so what
    that run staged and could not persist beside its verdict -- its usage and
    session -- lands with the park.
    """
    words = (
        f"the reviewer's verdict could not be recorded on the pinned comment: {why}. "
        "Nothing it returned was published or acted on; free room on the pinned "
        f"comment where it has none, then {_RETRY}"
    )
    parks_over_the_subject(gh, issue, state, run, (_state._REASON_REVIEWER_UNRECORDED, words, _REVIEWER))


def parks_over_the_subject(
    gh: GitHubClient,
    issue: Issue,
    state: PinnedState,
    run: _models._ReviewerRun,
    park: tuple[str, str, str | None],
) -> None:
    """File `park` over the subject `run` was handed, in one write, where it fits and that subject still stands.

    `park` is the reason, the notice's words, and the agent role the park is
    reported as, with the round, session, and pull request it ran for; a park
    of no agent's (None) reports its reason alone.

    `run.resolved_over` is the comment as the tick last read or wrote it, with
    the report and verdict records the verdict was proved over. Behind the
    notice, a field the state in hand spells otherwise than that reading is
    this tick's own to write -- what the returned run staged among them -- and
    one the comment spells otherwise is another road's, carried.
    """
    reason = park[0]
    held = (park, _verdicts.read_returned_verdict(state))
    # With no room beside what the returned run staged, the park is taken
    # over the comment as it stands, the run's usage and session unrecorded.
    parked = state if _park_fits(state, reason, held[1]) else _review_comment._read(
        gh, issue, state, "park a verdict with no room for what its run staged",
    )
    if parked is None or not _park_fits(parked, reason, held[1]):
        log.error(
            "issue=#%d has no room on its pinned comment even for the %s park; "
            "posting and writing nothing", issue.number, reason,
        )
        return
    # A park over the comment as it stands writes nothing but that reading,
    # so that reading is what it is measured against.
    measured = run if parked is state else run.measured_over(parked.data)
    lands = _behind_the_notice(gh, issue, parked, measured, held)
    if lands is None:
        return
    # What moved behind the notice was carried whole, and another road's
    # write can have spent the room this one was measured with.
    if not _report_record_state.fits_the_comment(parked.data):
        log.error(
            "issue=#%d has no room on its pinned comment for the %s park beside "
            "what moved there behind its notice; writing nothing", issue.number, reason,
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
    what the squash's tail holds: the verdict of the approval whose squash it
    was, the only one the park retires -- the recovery of a squash an earlier
    tick did not finish holds none -- and the comment it last read or wrote,
    the park's write composed over the comment as read behind its notice.
    An approval's squash is held to the subject that approval was of, resolved
    again behind the notice ahead of the comment's own reading: a push or an
    edit landing while it was posted is work nobody reviewed, so no park asks
    a human about it -- the verdict is dropped for a fresh reviewer -- and a
    subject nobody could read lands no park either, keeping the verdict.
    """
    reason = _state._REASON_SQUASH_FAILED
    if not _park_fits(state, reason, held.verdict):
        log.error(
            "issue=#%d has no room on its pinned comment for the %s park; "
            "posting and writing nothing", issue.number, reason,
        )
        return
    notice = _posts_the_notice(gh, issue, state, words)
    stands = held.subject is None or _review_coverage._subject_still_stands(
        gh, issue, state, held.subject,
    )
    if not _handoff._holds_its_records(gh, issue, state, "park its failed squash over the records it holds", held):
        return
    lands = notice is not None and stands is True
    if lands:
        state.set(_AWAITING_HUMAN, True)
        state.set(_state._PARK_REASON, reason)
    else:
        log.warning(
            "issue=#%d landed no %s park: its notice left no id, or the subject "
            "its approval is about moved or would not read behind it; writing "
            "what the tick staged without parking", issue.number, reason,
        )
    if lands or stands is False:
        _verdicts.drops_the_verdict(state, only=held.verdict)
    if not _report_record_state.fits_the_comment(state.data):
        log.error(
            "issue=#%d has no room on its pinned comment for the %s park beside "
            "a verdict it does not retire; writing nothing", issue.number, reason,
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
    held: tuple,
) -> bool | None:
    """Post the park's notice, then settle its write over the subject standing behind it; None to write nothing.

    `held` is the park and the verdict the state in hand carried as it began,
    the only one it drops. True where the park lands: the notice was posted
    and identified, the subject resolved again whole as the one `run` was
    handed, and no report, verdict, or evidence record moved on the comment
    since `run` read it. False where it does not: that verdict is dropped
    where the subject moved -- one another road put in its place is left for
    that road -- and left as it waited where the subject would not read or
    the notice left no id.
    """
    park, owned = held
    posted = _posts_the_notice(gh, issue, parked, park[1])
    stands = _review_coverage._subject_still_stands(gh, issue, parked, run.subject.recorded())
    # Composed over the comment as it stands whether or not the records moved:
    # the notice is time another road can write any field -- a round spent
    # by a reply -- and the park would write the state in hand back over it.
    records = _review_comment._records_stand(gh, issue, parked, run.resolved_over, persisted=True)
    if records is None:
        return None
    if _review_comment._moved(parked.data, run.resolved_over, _review_comment._EVIDENCE_RECORDS):
        # Evidence another road recorded or settled behind the notice is a
        # subject nobody reviewed, as surely as a push.
        records = False
    if posted is not None:
        # Where the records moved, what the comment changed was carried
        # whole, its own ledger included, which knows nothing of the notice
        # this park just posted.
        _comments._track_orchestrator_comment(parked, posted)
    if records and stands is None:
        log.info(
            "issue=#%d could not read the subject its reviewer's verdict is "
            "about behind its park notice; keeping the verdict for a later "
            "tick rather than parking", issue.number,
        )
        return False
    if records and stands and posted is None:
        log.warning(
            "issue=#%d could not confirm the notice of its %s park was posted; "
            "keeping the verdict for a later tick rather than parking with "
            "nobody told", issue.number, park[0],
        )
        return False
    _verdicts.drops_the_verdict(parked, only=owned)
    if records and stands:
        parked.set(_AWAITING_HUMAN, True)
        parked.set(_state._PARK_REASON, park[0])
        return True
    log.info(
        "issue=#%d the subject its reviewer's verdict is about moved while its "
        "park notice was posted; dropping the verdict for a fresh reviewer "
        "rather than parking", issue.number,
    )
    return False


def _posts_the_notice(gh: GitHubClient, issue: Issue, parked: PinnedState, words: str) -> int | None:
    """Post the park's notice and record the thread read through it; the notice's id, or None.

    The notice of the park a failed squash takes as well
    (`parks_the_failed_squash`). Read only as far as the orchestrator's own
    comments go (`park_watermarks`), since a park follows a run long enough
    for a human to have written something nobody has read -- which is also
    why the mark is harmless where no park lands behind the notice.
    """
    said_before = _comments._orchestrator_ids(parked)
    notice = _comments._post_issue_comment(gh, issue, parked, f"{config.HITL_MENTIONS} {words}")
    _park_watermarks._stamp_read_this_far(gh, issue, parked, said_before)
    return getattr(notice, "id", None)


def _park_fits(state: PinnedState, reason: str, owned: _verdicts.ReturnedVerdict | None) -> bool:
    """Whether the comment has room for whichever write a park on `state` ends in, measured at its widest.

    Its notice's ledger entry and the watermark it stamps go down either way:
    beside the park's flags where the park lands, and beside the verdict kept
    as it waited where the subject behind the notice would not read. The
    park that lands retires only `owned`, the verdict it holds, and only where
    it is still the one waiting, so it is measured keeping any other -- a later
    round's beside the recovery of a squash an earlier tick did not finish,
    which holds none. The comment measured here is the one the notice is
    posted over; a write that carries what moved behind it is measured again.
    """
    widest = _record_values.MAX_RECORDED_NUMBER
    kept = PinnedState(comment_id=state.comment_id, state_data=dict(state.data))
    _comments._reserve_comment_slot(kept, widest)
    kept.set("last_action_comment_id", widest)
    landed = PinnedState(comment_id=state.comment_id, state_data=dict(kept.data))
    _verdicts.drops_the_verdict(landed, only=owned)
    landed.set(_AWAITING_HUMAN, True)
    landed.set(_state._PARK_REASON, reason)
    return all(_report_record_state.fits_the_comment(written.data) for written in (kept, landed))
