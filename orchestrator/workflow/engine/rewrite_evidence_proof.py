# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A landed base rewrite's evidence proved again over the inputs that move under it: the issue, and the base.

The evidence policy proves a binding before a run and proves it again behind
one (`rewrite_evidence`), and a recovery takes up a decision an earlier finish
captured only once it proves again (`rewrite_finish_captured`). Both read the
world afresh rather than off the tick's own reading (`proves_again`): the issue
is fetched again, since the one a finish holds carries the title and body read
when the tick began, and the pinned comment is read again. The whole proof
(`verification_proof.binding_verdict`) then makes requests of its own -- the
pull request, the branch fetch, the settled report re-read at its location --
and every input it read ahead of the last of them could have moved while they
were answered: a checkout committed past the head, a branch pushed elsewhere,
an issue edited, a configuration changed. So each is read again behind the
proof (`_behind_the_proof`): the remote branch and the checkout against the
head (`verification_world.world_verdict`), the issue fetched once more for
its requirements (`verification_subject.requirements_verdict`), and last the
configuration, which no request reads. An issue or a pinned comment nobody
could read again HOLDS.

The base is the other input (`standing_refusal`). The finish counts the landed
head against the base as its tick fetched it, and routes a head the base has
advanced past to another rebase instead of to review (`rewrite_finish`), but
evidence decided for the head rests on the base as much as on the head, so
every evidence decision is held to it once its own requests are behind it -- a
carry, a route that runs nothing, a run, also before its commands start, and a
captured decision once proved again. The reading is the git owner's
(`git/base_sync/rewrite_facts._standing_on_the_remote_base`), over the base tip
the attempt recorded its replay as made onto
(`git/base_sync/attempt_records._recorded_onto`); what each answer means for
the evidence is decided here, in the proof's own verdicts:

- A remote base gone elsewhere since the head was counted -- advanced while
  the commands ran or a proof's requests were answered -- HOLDS, and so does a
  reading nobody could take. Nothing is recorded or routed and the attempt
  stands: the next tick's fetch counts the head again, and a head the base
  advanced past is continued to the next rebase, which replaces it.
- A counted base that is not the recorded tip -- rewound or repointed under
  the head after the rebase -- DEFERS, and so does an attempt that recorded no
  tip at all, since nothing then proves which base the head was replayed
  onto. No later tick changes either answer, so the decision is refused for
  good: nothing is run or recorded for the head, a captured decision is
  abandoned, and the fresh reviewer owes the evidence.
"""
from __future__ import annotations

import logging
from types import MappingProxyType

from github.Issue import Issue

from orchestrator.git.base_sync import attempt_records as _attempt_records, rewrite_facts as _rewrite_facts
from orchestrator.git.base_sync.rewrite_handoffs import _BaseStanding
from orchestrator.git.worktrees import paths as _worktree_paths
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    report_evidence_models as _evidence_models,
    verification_proof as _proof,
    verification_records as _records,
    verification_world as _world,
)
from orchestrator.workflow.engine.rewrite_finish_models import LandedFinish
from orchestrator.workflow.engine.verification_subject import requirements_verdict

log = logging.getLogger("orchestrator.workflow")

_HOLD = _evidence_models.ReportEvidenceVerdict.HOLD

_DEFER = _evidence_models.ReportEvidenceVerdict.DEFER

_UNREAD = _evidence_models.ReportEvidence(
    _HOLD, "the issue or its pinned comment could not be read again to prove the evidence",
)

_RECONFIGURED = _evidence_models.ReportEvidence(
    _DEFER, "the verification configuration moved while the evidence was proved again",
)

_REFUSALS = MappingProxyType({
    _BaseStanding.MOVED: _evidence_models.ReportEvidence(
        _HOLD, "the base moved after the rebased head was counted against it",
    ),
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


def proves_again(finish: LandedFinish, binding: _records.EvidenceBinding) -> _evidence_models.ReportEvidence:
    """The whole proof of `binding` over the issue and pinned comment read afresh, what moves read again behind it."""
    reread = _rereads(finish)
    if reread is None:
        return _UNREAD
    reading = _proof.ProofReading(finish.gh, finish.spec, *reread)
    found = _proof.binding_verdict(reading, binding)
    if not found.proved:
        return found
    return _behind_the_proof(finish, reading.state, binding) or found


def standing_refusal(finish: LandedFinish) -> _evidence_models.ReportEvidence | None:
    """Why `finish`'s landed head no longer stands on the base its replay was made onto, or None where it does."""
    standing = _rewrite_facts._standing_on_the_remote_base(
        finish.spec,
        _worktree_paths._worktree_path(finish.spec, finish.issue.number),
        finish.landed.candidate,
        _attempt_records._recorded_onto(finish.state),
    )
    return _REFUSALS.get(standing)


def _behind_the_proof(
    finish: LandedFinish, state: PinnedState, binding: _records.EvidenceBinding,
) -> _evidence_models.ReportEvidence | None:
    """Why an input the proof read ahead of its own requests moved while they were answered, or None.

    The heads first -- the remote branch and the checkout, whose fetch is a
    request of its own -- then the requirements over the issue fetched once
    more, and last the configuration, which costs no request at all.
    """
    issue = _fetches(finish)
    if issue is None:
        return _UNREAD
    refused = _world.world_verdict(finish.spec, issue, binding)
    if refused is None:
        refused = requirements_verdict(issue, state, binding.target.publication.requirements_revision)
    if refused is None and binding.context_revision != _proof.configured_context_revision():
        return _RECONFIGURED
    return refused


def _rereads(finish: LandedFinish) -> tuple[Issue, PinnedState] | None:
    """The issue fetched again and its pinned comment read again, or None where either would not read."""
    issue = _fetches(finish)
    if issue is None:
        return None
    try:
        state = finish.gh.read_pinned_state(issue)
    except Exception:
        log.exception(
            "issue=#%d could not read its pinned comment again to prove the evidence of %s",
            finish.issue.number, finish.head,
        )
        return None
    return (issue, state) if state.parsed else None


def _fetches(finish: LandedFinish) -> Issue | None:
    """The issue as GitHub carries it now, or None where it would not read."""
    try:
        return finish.gh.get_issue(finish.issue.number)
    except Exception:
        log.exception(
            "issue=#%d could not be read again to prove the evidence of %s", finish.issue.number, finish.head,
        )
        return None
