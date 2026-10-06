# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The guarded commits a reviewer round's launch and return, a returned verdict, and its parks land through.

A reviewer round writes the pinned comment at points minutes apart, each
decided on a reading of it: the launch on the reading its subject was bound
to, the return on the reading taken again as the reviewer came back, a
verdict on the one taken again behind its subject, a drop and a park on the
one taken last. Written whole from the tick's state, each would put back
every field another road moved since that reading -- a usage total, a
watermark, a report or evidence record, another round's verdict -- and
nothing on the comment would say so. So each lands through the guarded commit
(`pinned_commit`) over a fresh reading instead, under the tick-state guard
the developer report's commits use (`report_commits.ReportCommit`): captured
over the reading the tick last synced with the comment (`PinnedState.synced`),
which every reading of the round lays its moves into
(`review_comment._Reread.lays_over`), owning every field the tick staged since
beside the fields each write declares (`ReportWrite`), and keeping both moves
of a usage total, its cost tags, a comment-id watermark, and the ledger of the
orchestrator's own comments by the validating stage's own rule for each.
Every other field is the fresh reading's.

Each write is decided on records it holds the comment to, as that reading
spells them: the launch, a return, and a return's park on the developer
report's records, the pull request the issue points at, and the returned
verdict (`review_comment._VERDICT_RECORDS`); a verdict, its drop, and a
verdict's park on those and the verification evidence records besides
(`VERDICT_STANDS_ON`). Each is decided as well on the fields of its own it may
stage exactly as the reading spells them -- the launch's spec and subject, a
return's subject, a park's flags -- since the commit tells a write's own moves
by their difference from the capture, and a field staged unchanged is one a
concurrent write would otherwise move under it unseen: a launch repeated over
the same subject would run beside another road's spec or subject, and a park
staged over a tick that read the issue parked would land as a park another
road cleared. One that moved under the write -- a later report, a repoint,
another round's verdict put in place of the one held, evidence recorded or
settled, a replaced spec or subject, a cleared park -- refuses it, and so does a field it owns that another
road moved meanwhile, a comment that will not read or parse or was replaced,
and a candidate past what one comment holds. A refusal writes nothing, and
nothing that depends on the write is made: no reviewer is launched behind a
launch that did not land, no evidence published or verdict acted on behind
a verdict that did not, and no notice posted for a park whose record would
not land. A write GitHub took and never confirmed is answered the same way --
nothing acts on it -- and the records it may have left settle it on a later
tick: a launch's records written again over themselves with nothing sent, a
verdict and its transaction finished by that tick's reconciliation and
recovery with no second reviewer, artifact, fold, charge, or round.

The launch is captured over the reading its subject was bound to rather than
the tick's state (`lands_the_launch`): that state carries what the tick
staged for the round's own write -- a cleared park, a cap grant's round reset
-- which a launch the run circuit refuses discards. A verdict is staged on a
copy, measured whole in its commit against the room its handoff and its
transaction's settlement reserve (`ReturnedVerdict.fits_beside`), and a
comment without that room is answered as one with no room for the verdict
(`lands_the_verdict`). A park is prepared before its notice, with what posting
that notice writes reserved at its widest, and committed behind it
(`parks_the_return`, `parks_over`).
"""
from __future__ import annotations

import logging
from collections.abc import Callable

from github.Issue import Issue

from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    comments as _comments,
    pinned_commit_models as _commit_models,
    prompt_delivery as _prompt_delivery,
    report_commits as _commits,
    review_subjects as _review_subjects,
    verification_records as _evidence_records,
)
from orchestrator.workflow.stages.validating import (
    models as _models,
    review_comment as _review_comment,
    review_records as _review_records,
    review_verdicts as _verdicts,
    state as _state,
)

log = logging.getLogger("orchestrator.workflow")

_AWAITING_HUMAN = "awaiting_human"

# What a returned run leaves on the comment: the usage it folded into the
# issue's totals and their cost tags, the session it ran as, when it
# returned, and the subject it was handed.
_RETURNED = frozenset((
    "issue_agent_runs",
    "issue_total_tokens",
    "issue_total_cost_usd",
    "issue_cost_sources",
    _review_records._LAST_REVIEW_SESSION_ID,
    _review_records._LAST_REVIEW_AT,
    _review_subjects.RETURNED_SUBJECT,
))

# What a park writes: its flags, and the ledger entry and the thread read
# through that posting its notice adds.
_PARKED = frozenset((
    _AWAITING_HUMAN,
    _state._PARK_REASON,
    _prompt_delivery.PINNED_LAST_ACTION_COMMENT_ID,
    _comments._ORCH_COMMENT_IDS,
))

# A park's flags. A park staged over a tick that read the issue parked -- one
# a reply cleared in memory, or a transient park retried -- stages them as that
# reading already spelled them, so the commit carries no change of them a
# conflict could be told by, and a park another road cleared meanwhile would
# survive it. Every write that sets them is decided on them as well.
_PARK_FLAGS = frozenset((_AWAITING_HUMAN, _state._PARK_REASON))

# What a returned verdict stands on: the developer report's records, the pull
# request the issue points at, the verdict itself, and the verification
# evidence its claim is judged over. Another road moving any of them is a
# subject nobody reviewed, or a verdict other than the one held.
VERDICT_STANDS_ON = frozenset((*_review_comment._VERDICT_RECORDS, *_review_comment._EVIDENCE_RECORDS))

# What a returned run's records are decided on beside those it stands on: the
# subject a reviewer returned with, which a repeated return of the same subject
# stages unchanged and which another round's return would otherwise move under it.
_RETURN_DECIDED_ON = frozenset((*_review_comment._VERDICT_RECORDS, _review_subjects.RETURNED_SUBJECT))

# The launch: the reviewer spec and the subject it is handed, decided on both as
# well -- a launch repeated over the same subject stages them unchanged, so
# another road's replacement of either would otherwise survive it and leave a
# reviewer running under a record of another.
_LAUNCH_RECORDS = frozenset((_review_records._REVIEW_AGENT, _review_subjects.REVIEW_SUBJECT))

_LAUNCH = _commits.ReportWrite(
    owned=_LAUNCH_RECORDS,
    decided_on=frozenset(_review_comment._VERDICT_RECORDS) | _LAUNCH_RECORDS,
)

# A returned run's records, where nothing else of the return is written: its
# subject moved, or it left no verdict and parks.
RETURN = _commits.ReportWrite(owned=_RETURNED, decided_on=_RETURN_DECIDED_ON)

_RETURN_PARK = _commits.ReportWrite(owned=_RETURNED | _PARKED, decided_on=_RETURN_DECIDED_ON | _PARK_FLAGS)

# A verdict persisted beside the run that returned it, with the transaction its
# claim was minted as -- recorded into the evidence records, a superseded
# transaction retired into history and the revision floor raised.
_VERDICT = _commits.ReportWrite(
    owned=_RETURNED | {
        _verdicts.RETURNED_VERDICT,
        _evidence_records.PENDING_EVIDENCE,
        _evidence_records.EVIDENCE_HISTORY,
        _evidence_records.REVISION_FLOOR,
    },
    decided_on=VERDICT_STANDS_ON | {_review_subjects.RETURNED_SUBJECT},
)

# The end of a verdict held.
DROP = _commits.ReportWrite(owned=frozenset((_verdicts.RETURNED_VERDICT,)), decided_on=VERDICT_STANDS_ON)

# A verdict's park: its own fields, the verdict it drops, and the records of
# the run it parks where they ride it.
PARK = _commits.ReportWrite(
    owned=_RETURNED | _PARKED | {_verdicts.RETURNED_VERDICT},
    decided_on=VERDICT_STANDS_ON | _PARK_FLAGS | {_review_subjects.RETURNED_SUBJECT},
)

# What a verdict's commit answers where the candidate has no room for the
# verdict at its handoff and its transaction settled beside it.
_NO_ROOM = "no room for the verdict at its handoff"


def lands(gh: GitHubClient, issue: Issue, state: PinnedState, write: _commits.ReportWrite) -> bool:
    """Commit what `state` staged as `write` over the fresh comment; whether it landed.

    Where it landed `state` reads as the comment does, and is synced with it.
    Where it did not -- refused, or sent and never confirmed -- nothing was
    written over the comment, `state` is withheld from every whole-state write
    behind it (`report_commits.ReportCommit.withholds`), and the caller makes
    nothing that depends on the write.
    """
    landed = _commits.ReportCommit(gh, issue, state).lands(state, write)
    if landed.status is _commit_models.CommitStatus.COMMITTED:
        return True
    log.warning(
        "issue=#%d its reviewer round's write did not land (%s); writing and "
        "acting on nothing behind it", issue.number, (landed.refusal or landed.status).value,
    )
    return False


def lands_the_launch(
    gh: GitHubClient,
    issue: Issue,
    state: PinnedState,
    handover: _review_comment._ResolvedSubject,
) -> dict | None:
    """Commit the reviewer spec and the subject `handover` hands over; the comment as it landed, or None.

    Captured over the reading the subject was bound to
    (`handover.resolved_over`), which carries the report records, the pull
    request, and the returned verdict the round was decided on, rather than
    over `state`: what the tick staged there for the round's own write is
    left out of the launch's. None where the commit did not land, and no
    reviewer may be launched: a record that moved refuses it as much as a
    comment that will not read, and an edit never confirmed may not have
    landed.
    """
    bound = PinnedState(comment_id=state.comment_id, state_data=dict(handover.resolved_over))
    commit = _commits.ReportCommit(gh, issue, bound)
    staged = commit.staging()
    _review_records._records_the_launch(staged, handover.subject)
    landed = commit.lands(staged, _LAUNCH)
    if landed.status is _commit_models.CommitStatus.COMMITTED:
        return bound.data
    log.warning(
        "issue=#%d could not record its reviewer's launch (%s); launching no "
        "reviewer this tick", issue.number, (landed.refusal or landed.status).value,
    )
    return None


def stages_the_return(state: PinnedState, run: _models._ReviewerRun) -> None:
    """Stage on `state` what `run`'s reviewer left: its usage, its session, when it returned, and what it read."""
    returned = run.agent_result
    _review_records._records_the_return(state, returned.usage, returned.session_id, run.subject)


def parks_the_return(
    gh: GitHubClient,
    issue: Issue,
    state: PinnedState,
    run: _models._ReviewerRun,
    park: tuple[str | None, Callable[[], None]],
) -> None:
    """Park `run`, which left no verdict, with what it returned, in one guarded commit behind its notice.

    `park` is the reason the park is kept under -- None for one a human
    answers -- and what posts its notice (`guards._park_awaiting_human`),
    staging its flags and the thread read through it on `state`. The record
    is prepared before the notice, with the ledger entry and watermark that
    posting adds reserved at their widest: a comment that will not read, moved
    under the records the return was decided on, or has no room for the park
    beside the run's records posts nothing. A commit refused behind the notice
    leaves the notice on the thread and no park recorded, and the next tick
    spawns a reviewer over the comment as it stands then; the park's event,
    which `posts` emits beside its notice, has gone out either way.
    """
    reason, posts = park
    stages_the_return(state, run)
    prepared = _prepares_the_park(_commits.ReportCommit(gh, issue, state), reason, None, _RETURN_PARK)
    if prepared.status is not _commit_models.CommitStatus.PREPARED:
        return
    posts()
    state.set(_state._PARK_REASON, reason)
    lands(gh, issue, state, _RETURN_PARK)


def lands_the_verdict(
    gh: GitHubClient,
    issue: Issue,
    state: PinnedState,
    returned: _verdicts.ReturnedVerdict,
    pending: _evidence_records.PendingEvidence | None,
) -> bool | None:
    """Persist `returned` with the transaction `pending` it claims, beside what `state` staged; whether it landed.

    Staged on a copy (`review_verdicts.records_the_verdict`), so `state` is
    left as it was wherever the commit does not land; where it lands, `state`
    reads as the comment does. The room the verdict's handoff and the
    transaction's settlement reserve is asked of the very candidate the commit
    sends (`ReturnedVerdict.fits_beside`). None where there is no such room --
    staged or committed -- which the caller parks as unrecorded; False where
    the commit was otherwise refused or never confirmed, and nothing may be
    published or acted on.
    """
    commit = _commits.ReportCommit(gh, issue, state)
    staged = commit.staging()
    if not _verdicts.records_the_verdict(staged, returned, pending):
        return None
    landed = commit.lands(staged, _VERDICT.admitting(
        lambda candidate: None if returned.fits_beside(candidate, pending) else _NO_ROOM,
    ))
    if landed == _NO_ROOM or landed.refusal in _commits._ROOM:
        return None
    if landed.status is _commit_models.CommitStatus.COMMITTED:
        return True
    log.warning(
        "issue=#%d did not persist its reviewer's verdict (%s); publishing and "
        "acting on nothing", issue.number, (landed.refusal or landed.status).value,
    )
    return False


def parks_over(
    gh: GitHubClient,
    issue: Issue,
    state: PinnedState,
    run: _models._ReviewerRun,
    park: tuple,
) -> PinnedState | None:
    """The state the verdict park `park` is taken over, prepared before its notice; None to post and write nothing.

    `park` is as `review_parks.parks_over_the_subject` takes it. `state` where
    the park fits beside what the returned run staged. Where only room refused
    it, the comment as it stands, with the run's records left unrecorded --
    where it still carries what the verdict stands on as `run.resolved_over`
    does, and has room for the park. Anything else posts nothing.
    """
    reason, held = park[0], park[3]
    prepared = _prepares_the_park(_commits.ReportCommit(gh, issue, state), reason, held, PARK)
    if prepared.status is _commit_models.CommitStatus.PREPARED:
        return state
    if prepared.refusal not in _commits._ROOM:
        return None
    fresh = _review_comment._read(gh, issue, state, "park a verdict with no room for what its run staged")
    if fresh is None:
        return None
    if _review_comment._moved(fresh.data, run.resolved_over, VERDICT_STANDS_ON):
        log.warning(
            "issue=#%d its pinned comment moved what its reviewer's verdict stands "
            "on before the %s park was posted; posting and writing nothing", issue.number, reason,
        )
        return None
    taken = _prepares_the_park(_commits.ReportCommit(gh, issue, fresh), reason, held, PARK)
    return fresh if taken.status is _commit_models.CommitStatus.PREPARED else None


def _prepares_the_park(
    commit: _commits.ReportCommit,
    reason: str | None,
    held: _verdicts.ReturnedVerdict | None,
    write: _commits.ReportWrite,
) -> _commit_models.CommitOutcome:
    """The park's record prepared over the fresh comment, its notice reserved; or why it would not land, logged.

    Staged on a copy of `commit.state`: the park's flags under `reason`, and
    `held` dropped -- only where it is still the verdict waiting, so the park
    is measured keeping any other.
    """
    staged = commit.staging()
    _verdicts.drops_the_verdict(staged, only=held)
    staged.set(_AWAITING_HUMAN, True)
    staged.set(_state._PARK_REASON, reason)
    prepared = commit.prepares(staged, write, notice=True)
    if prepared.status is not _commit_models.CommitStatus.PREPARED:
        log.error(
            "issue=#%d could not prepare its park (%s) over the pinned comment (%s); "
            "posting nothing over it", commit.issue.number, reason or "awaiting a human",
            prepared.refusal.value,
        )
    return prepared
