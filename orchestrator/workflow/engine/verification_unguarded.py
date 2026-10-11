# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The readings of a verification transaction no guarded commit holds, taken behind every other request.

A post and a settlement are each decided on a long run of requests -- the pull
request, the branch and its objects, the settled report at its location, the
artifact re-read, the pinned comment read again -- and a guarded commit holds
only what that comment carries. Three things a transaction is bound to live
elsewhere: the issue (whether it is still live work, and the requirements its
body and comments hash to), the landing and base a standing auto-rebase anchor
holds the head to (`verification_proof.ProofReading.anchored`), and the
configuration the commands are held to. Read once, early, any of them can move
while a later request is answered, and the post or the settlement would go out
over a reading taken before it.

So they are read again here, last, in the one order that leaves none of them
in front of a request: the anchor's own proof first, whose landing and base
are git requests; then the issue fetched afresh (`live_issue`), which has to
be live work still, its requirements hashed over that very reading -- the
comment walk among them; and the configuration last of all, which costs no
request. The publication asks it right before the post
(`verification_publishing`) and the settlement right before its commit
(`verification_settling`), so an issue edited, a base advanced, or a command
configured otherwise while any earlier request was answered refuses the post
or the settlement rather than riding it. Every refusal of the binding is kept
the moment it is read (`ProofReading.observes`) -- the anchor's, whatever the
readings behind it come to -- so a caller collecting them still has a movement
read once and put back since.
"""
from __future__ import annotations

import logging

from github.Issue import Issue

from orchestrator.github import labels as _labels
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    verification_live_work as _live_work,
    verification_proof as _proof,
    verification_records as _records,
    verification_subject as _subject,
)
from orchestrator.workflow.engine.report_evidence_models import ReportEvidence, ReportEvidenceVerdict

log = logging.getLogger("orchestrator.workflow")


def live_issue(reading: _proof.ProofReading) -> Issue | ReportEvidence:
    """The issue read afresh, or the refusal that leaves nothing written.

    A refusal comes back with no comment read at all, so nothing -- not even
    an artifact's ledger entry -- is written onto an issue somebody has
    closed, paused, or ended meanwhile, or one that could not be read again.
    The labels and the state are lazy reads on the issue fetched afresh, so
    they are taken under a boundary of their own.
    """
    try:
        fresh = reading.gh.get_issue(reading.issue.number)
    except Exception:
        log.exception(
            "issue=#%d could not be re-read before publishing or settling its verification "
            "evidence", reading.issue.number,
        )
        return ReportEvidence(
            ReportEvidenceVerdict.HOLD, "the issue could not be re-read before the settlement",
        )
    try:
        aside = _live_work.stands_aside(fresh, _labels.workflow_label(fresh))
    except Exception:
        log.exception(
            "issue=#%d could not be read again for its labels and state before "
            "publishing or settling its verification evidence", fresh.number,
        )
        return ReportEvidence(
            ReportEvidenceVerdict.HOLD,
            "the issue's labels and state could not be re-read before the settlement",
        )
    if aside:
        return ReportEvidence(
            ReportEvidenceVerdict.DEFER,
            "the issue stopped being live work while the artifact was posted",
        )
    return fresh


def unguarded_refusal(
    reading: _proof.ProofReading, state: PinnedState, pending: _records.PendingEvidence,
) -> tuple[Issue | None, ReportEvidence | None]:
    """The issue the readings no guarded commit holds were taken over, and the first of them that refuses `pending`.

    `state` is the pinned comment the caller is about to write over, whose
    orchestrator comments the requirements hash leaves out. The issue is None
    where it would not read again or stopped being live work, with that as
    the refusal, for the caller to write nothing; otherwise the refusal is the
    anchor's, the requirements', or the configuration's, in that order, or
    None where all three prove.
    """
    anchored = reading.anchor_verdict()
    reading.observes(anchored)
    behind = live_issue(reading)
    if isinstance(behind, ReportEvidence):
        return None, behind
    revision = pending.binding.target.publication.requirements_revision
    refused = _subject.requirements_verdict(behind, state, revision) or _proof._context_verdict(pending.binding)
    reading.observes(refused)
    return behind, anchored or refused
