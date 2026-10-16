# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A landed base rewrite's evidence proved again, and the last word on its route over everything that moves.

The readings a landed head's evidence route is held to, before it records or
routes anything over a decision: its binding proved again (`proves_again`),
the head held to the base tip its replay was made onto (`standing_refusal`),
and the last word over everything that moves (`last_word`). The evidence
policy (`rewrite_evidence`) proves a run again behind it and holds the head
to the base before a run starts or a carry is made, and a recovery takes up a
decision an earlier finish captured only once it proves again
(`rewrite_finish_captured`). Every route the finish's evidence step takes that
carries or follows a recorded decision ends in the last word -- a captured
transaction's behind whatever stopped it -- and only a fresh decision held
before its write, whose write did not land, or whose failure notice nobody
could confirm ends without it, leaving no transaction behind it to abandon.
The readiness proof (`rewrite_finish_readiness`) asks the last word over
evidence already settled for the head as well, on every road that finishes
the landing and every recovery answer that proves that evidence.

`proves_again` reads the world afresh rather than off the tick's own reading:
the issue is fetched again, since the one a finish holds carries the title and
body read when the tick began, and the pinned comment is read again, and the
whole proof (`verification_proof.binding_verdict`) is taken over them. An
issue or a pinned comment nobody could read again HOLDS. The proof reads the
pull request first and stops at a reading nobody could take, so a proof that
holds is answered beside the review and report records the comment it read
carries (`verification_proof.recorded_verdict`): a subject or settled report
that moved is movement, whatever went unanswered.

That proof makes requests of its own -- the pull request, the branch fetch,
the settled report re-read -- and so would the finish behind it: the evidence
write, a failure notice's conversation read and post. Anything read before one
of them can have moved while it was answered. So `last_word` is asked once
nothing else is left to request, and reads everything that moves again in one
fixed order: the network first -- the remote branch the head landed on, the
base, and, over the issue and pinned comment fetched once more, the issue's
requirements and the review and report records the transaction is bound to,
and any verdict the caller asks of that comment (`records`) --
and then the readings no request answers, behind every one that did: the
checkout's own head, the local base ref it counts against, and the
configuration. The remote branch and the checkout are two readings, the
checkout read whatever the remote's came to, and the records are compared on
their own, whatever the proof before them could read. Every reading is taken,
and the last word answers with the first that establishes movement and the
first that holds the route, side by side, so a reading nobody could take never
hides movement another reading took. Movement that only the reading nobody
could take would have shown is established by nothing: it holds, and is
proved again. A remote branch or a checkout read off the landed head
(`LEFT_THE_LANDING`) both holds the route and establishes movement; a remote
branch nobody could read, a checkout whose head would not prove, or a local
base nobody could count it against only HOLDS. Requirements, review or report records, or a configuration that moved
DEFER, establishing movement under the transaction the route would carry. The
remote branch and the checkout are read only where the caller asks for the
landing (`landing`): a route that ran nothing and recorded nothing has nothing
the landing could have moved under.

`standing_refusal` reads the base through the git owner
(`git/base_sync/rewrite_facts._standing_on_the_remote_base`), over the base
tip the attempt recorded its replay as made onto
(`git/base_sync/attempt_records._recorded_onto`), or over one a caller that
counted the head itself hands in:

- A remote base gone elsewhere since the head was counted, or a local count
  the head is behind -- the base advanced past it -- is movement established
  (`BASE_MOVED`), and HOLDS: a later tick's fetch counts the head again, and
  a head the base advanced past is the next rebase's to replace. A base
  nobody could read HOLDS without establishing movement. A local count
  nobody could take still has the remote's base read, so a remote base gone
  elsewhere is movement whatever the local count came to.
- A counted base that is not the recorded tip and that the head is not behind
  -- rewound or repointed under the head after the rebase -- DEFERS, and so
  does an attempt that recorded no tip at all, a legacy one included, since
  nothing then proves which base the head was replayed onto. No later tick
  changes either answer, so the decision is refused for good: nothing is run
  or carried for the head, a captured decision is abandoned, and the fresh
  reviewer owes the evidence.

Two remote readings cannot be taken at one instant, so the network part of the
last word is ordered rather than atomic, and the writes the route itself makes
behind it are not read past. What moves there is no evidence anyone settles:
the finish proves a recorded transaction whole again, held to the base too,
before it publishes it and again before it settles it
(`rewrite_finish_settlement`), and the retirement behind the route is decided
on every record the evidence is bound through (`rewrite_finish_writes.FINISH`).
`standing_refusal` is that settlement's anchored proof
(`verification_proof.ProofReading.anchored`).
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from types import MappingProxyType

from github.Issue import Issue

from orchestrator.git import branch_transport
from orchestrator.git.base_sync import attempt_records as _attempt_records, rewrite_facts as _rewrite_facts
from orchestrator.git.base_sync.rewrite_handoffs import _BaseStanding
from orchestrator.git.worktrees import paths as _worktree_paths
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    report_evidence_models as _evidence_models,
    verification_proof as _proof,
    verification_records as _records,
    verification_subject as _subject,
)
from orchestrator.workflow.engine.rewrite_finish_models import LandedFinish

log = logging.getLogger("orchestrator.workflow")

_HOLD = _evidence_models.ReportEvidenceVerdict.HOLD

_DEFER = _evidence_models.ReportEvidenceVerdict.DEFER

_UNREAD = _evidence_models.ReportEvidence(
    _HOLD, "the issue or its pinned comment could not be read again to prove the evidence",
)

_UNREADABLE = "issue=#%d could not read %s again to prove the evidence of %s"

_RECONFIGURED = _evidence_models.ReportEvidence(
    _DEFER, "the verification configuration moved while the evidence was proved again",
)

_UNREAD_REMOTE = _evidence_models.ReportEvidence(
    _HOLD, "the remote branch the rebased head landed on could not be read again",
)

_UNREAD_CHECKOUT = _evidence_models.ReportEvidence(
    _HOLD, "the checkout's head could not be proved again",
)

_UNREAD_BASE_REF = _evidence_models.ReportEvidence(
    _HOLD, "the local base the checkout's head is counted against could not be read again",
)

# A checkout or remote branch off the head that landed: the landing the route
# would finish is no longer the one in front of it.
LEFT_THE_LANDING = _evidence_models.ReportEvidence(
    _HOLD, "the checkout or the remote branch is no longer on the rebased head",
)

# What one reading refuses, None for each check it passed.
Refusals = tuple[_evidence_models.ReportEvidence | None, ...]

# What the last word's requests heard: the remote branch's head, then the
# base's refusal and what the issue and its pinned comment, read again, refuse.
_Heard = tuple[str | None, Refusals]

# A base gone elsewhere since the head was counted -- the remote's read on
# another commit, or a local base advanced past the head: movement
# established, as a landing off its head is, rather than a reading nobody
# could take.
BASE_MOVED = _evidence_models.ReportEvidence(
    _HOLD, "the base moved after the rebased head was counted against it",
)

# The holds that read movement rather than a reading that did not happen; a
# caller sorting refusals it collected itself sorts them by this too
# (`rewrite_finish_settlement`).
MOVEMENT = (LEFT_THE_LANDING, BASE_MOVED)

# What the last word comes to: the first reading of movement, and the first
# reading that holds the route.
Word = tuple[_evidence_models.ReportEvidence | None, _evidence_models.ReportEvidence | None]

_REFUSALS = MappingProxyType({
    _BaseStanding.MOVED: BASE_MOVED,
    _BaseStanding.UNREAD: _evidence_models.ReportEvidence(
        _HOLD, "the base the rebased head was counted against could not be read again",
    ),
    _BaseStanding.DROPPED: _evidence_models.ReportEvidence(
        _DEFER, "the base is no longer the tip the rebased head was replayed onto",
    ),
    _BaseStanding.UNPROVEN: _evidence_models.ReportEvidence(
        _DEFER, "the attempt recorded no base tip its replay was made onto",
    ),
})

# The base readings a continuation is made over -- the base gone past the
# landed head since its replay -- which move nothing under settled evidence
# the continuation keeps for the rebase behind it to decide over
# (`last_word`); a tip blanked to record movement is no such reading.
ADVANCED = (BASE_MOVED, _REFUSALS[_BaseStanding.DROPPED])


def proves_again(finish: LandedFinish, binding: _records.EvidenceBinding) -> _evidence_models.ReportEvidence:
    """The whole proof of `binding` over the issue and pinned comment read afresh, or the HOLD nobody could read.

    A proof that holds on a reading nobody could take stopped there, so the
    records the pinned comment carries are asked beside it
    (`verification_proof.recorded_verdict`), and a refusal of theirs -- a
    review subject or settled report that moved -- is the answer instead:
    movement those records establish is never hidden behind a request that
    went unanswered.
    """
    read = _reads_again(finish)
    if read is None:
        return _UNREAD
    issue, state = read
    reading = _proof.ProofReading(finish.gh, finish.spec, issue, state)
    found = _proof.binding_verdict(reading, binding)
    if not found.holds:
        return found
    return _proof.recorded_verdict(state, binding) or found


def standing_refusal(finish: LandedFinish, onto: str | None = None) -> _evidence_models.ReportEvidence | None:
    """Why `finish`'s landed head no longer stands on the base its replay was made onto, or None where it does.

    `onto` is the base tip to hold the head to, where the caller has one of
    its own: by default the one the attempt recorded its replay as made onto.
    """
    standing = _rewrite_facts._standing_on_the_remote_base(
        finish.spec,
        _worktree_paths._worktree_path(finish.spec, finish.issue.number),
        finish.landed.candidate,
        _attempt_records._recorded_onto(finish.state) if onto is None else onto,
    )
    return _REFUSALS.get(standing)


def last_word(
    finish: LandedFinish,
    binding: _records.EvidenceBinding | None = None,
    *,
    landing: bool = True,
    earlier: _evidence_models.ReportEvidence | None = None,
    records: Callable[[PinnedState], Refusals] | None = None,
) -> Word:
    """What everything that moves under `finish`'s route reads as now, behind every request: `(moved, held)`.

    `binding` is the evidence the route would carry -- a transaction recorded
    for the head, or evidence already settled for it, proved ready again
    (`rewrite_finish_readiness`) -- None where it carries none, and `landing`
    whether the remote branch and the checkout are read again too -- for a
    route that carries or follows a recorded decision.
    `earlier` is a verdict the caller already read the transaction with -- a
    proof of it again -- which is sorted first, beside the rest. `records` is
    a caller's own reading of the pinned comment the last word reads afresh,
    asked beside the requirements and the review and report records, and
    answering with refusals of its own that are sorted beside every other --
    the evidence records settled evidence is held to
    (`rewrite_finish_readiness`). The network is read first and the local
    readings last (`_answers_locally`), so nothing read before a request is
    taken on trust behind it. Settled evidence for a head the base advanced
    past again -- `records` asked of a landing whose candidate counted the base
    ahead of it, which a continuation keeps that evidence over for the rebase
    behind it -- does not count the base readings that made the continuation
    (`ADVANCED`): they are dropped before the first movement and the first
    hold are taken, so none of them hides a reading behind it. Only the
    readiness proof asks `records` (`rewrite_finish_readiness.settled_word`).

    Every reading is taken, and none nobody could take hides one that read
    movement. `moved` is the first that establishes that something the route
    rests on moved -- every refusal that defers, and the two holds that read
    movement, a landing off its head and a base gone elsewhere (`MOVEMENT`)
    -- and a transaction the route would carry can never be taken again after
    it. `held` is the first that holds the route: a reading nobody could take,
    or one of those two. Either is None where no reading says so.
    """
    answered = _answers_locally(finish, binding, _hears(finish, binding, landing, records), landing)
    excused = ADVANCED if finish.behind and records is not None else ()
    found = [refused for refused in (earlier, *answered) if refused and not refused.proved]
    found = [refused for refused in found if refused not in excused]
    movements = (refused for refused in found if not refused.holds or refused in MOVEMENT)
    holds = (refused for refused in found if refused.holds)
    return next(movements, None), next(holds, None)


def _hears(
    finish: LandedFinish,
    binding: _records.EvidenceBinding | None,
    landing: bool,
    records: Callable[[PinnedState], Refusals] | None,
) -> _Heard:
    """Every request the last word makes, in its order: the remote branch, the base, and the issue and its comment.

    The issue and its pinned comment are read again for a transaction the
    route would carry, and both are asked of it: the requirements over the
    issue, and the review and report records over the comment
    (`verification_proof.recorded_verdict`), whatever any other reading came to
    -- and whatever the caller's `records` refuses on that same comment, where
    it asks any.
    """
    remote = None
    if landing:
        remote = branch_transport._remote_branch_read(
            finish.spec,
            _worktree_paths._worktree_path(finish.spec, finish.issue.number),
            finish.landed.candidate.branch,
        ).sha
    base = standing_refusal(finish)
    if binding is None:
        return remote, (base,)
    read = _reads_again(finish)
    if read is None:
        return remote, (base, _UNREAD)
    issue, state = read
    return remote, (
        base,
        _subject.requirements_verdict(issue, state, binding.target.publication.requirements_revision),
        _proof.recorded_verdict(state, binding),
        *(() if records is None else records(state)),
    )


def _answers_locally(
    finish: LandedFinish, binding: _records.EvidenceBinding | None, heard: _Heard, landing: bool,
) -> tuple[_evidence_models.ReportEvidence | None, ...]:
    """The readings no request answers, behind every one that did -- the checkout's own head, the configuration.

    Then every verdict in its order, None for each reading that refused
    nothing: the remote branch, the checkout and the local base it counts
    against, the base, the requirements and the records, the configuration.
    """
    remote, asked = heard
    landed = _landing_refusals(finish, remote) if landing else (None, None, None)
    reconfigured = binding is not None and binding.context_revision != _proof.configured_context_revision()
    return *landed, *asked, _RECONFIGURED if reconfigured else None


def _landing_refusals(
    finish: LandedFinish, remote: str | None,
) -> tuple[_evidence_models.ReportEvidence | None, ...]:
    """The remote branch, as heard, and the checkout, read now, each against the landed head; and the local base.

    Two readings, each refused on its own: a remote branch nobody could read
    says nothing about the checkout, which is read whatever the branch's
    reading came to, so a checkout that moved is never hidden behind it. A
    reading that did not happen -- the branch unread, or a checkout head the
    proof could not name, which reads as "" -- holds without establishing
    movement, as the evidence policy holds a reading nobody took; only a head
    read somewhere else is the landing left. The checkout's reading counts
    against the local base ref as it reads now too, behind every request, and
    a base that reads as another tip than the one the attempt recorded its
    replay made onto has moved: advanced past the head (`BASE_MOVED`), or
    rewound or repointed under it (`_BaseStanding.DROPPED`). A local base
    nobody could count against holds, as a remote base nobody could read does,
    since the base reading before the requests says nothing about it now.
    """
    reading = _rewrite_facts._reads_the_checkout(
        finish.spec, _worktree_paths._worktree_path(finish.spec, finish.issue.number),
    )
    onto = _attempt_records._recorded_onto(finish.state)
    base = None
    if onto and not reading.base.readable:
        base = _UNREAD_BASE_REF
    elif onto and reading.base.tip != onto:
        base = BASE_MOVED if reading.base.behind else _REFUSALS[_BaseStanding.DROPPED]
    # Each head against the landed one: on it refuses nothing, a reading that
    # did not happen holds, and any other head is the landing left.
    branch = {None: _UNREAD_REMOTE, finish.head: None}.get(remote, LEFT_THE_LANDING)
    checkout = {"": _UNREAD_CHECKOUT, finish.head: None}.get(reading.head, LEFT_THE_LANDING)
    return branch, checkout, base


def _reads_again(finish: LandedFinish) -> tuple[Issue, PinnedState] | None:
    """The issue as GitHub carries it now and its pinned comment read over it, or None where either would not read."""
    try:
        issue = finish.gh.get_issue(finish.issue.number)
    except Exception:
        log.exception(_UNREADABLE, finish.issue.number, "the issue", finish.head)
        return None
    try:
        state = finish.gh.read_pinned_state(issue)
    except Exception:
        log.exception(_UNREADABLE, finish.issue.number, "its pinned comment", finish.head)
        return None
    return (issue, state) if state.parsed else None
