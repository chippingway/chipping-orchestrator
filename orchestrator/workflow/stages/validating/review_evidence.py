# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The workflow verification evidence a reviewer is handed beside its subject.

A reviewer is handed the evidence this issue records as CURRENT, and only
where that evidence answers for the very subject the reviewer is about to be
handed -- the pull request, head, requirements, and developer report, compared
whole as `review_subjects` records them. Evidence bound to an earlier report on
the same head, or to requirements the issue has moved past, is evidence about
a review nobody is asking for now; handed over, a reviewer could reuse it for
a subject it never covered.

The record alone is not enough either, since a head, a context, a report, or
the artifact itself can move after a settlement and the record sees none of
it. So the evidence is proved current again first
(`verification_proof.current_evidence_verdict`) -- still the latest revision
this issue spent, its handoff describing it, its artifact on the pull request
exactly as it settled, and the whole binding proved against the world -- and
the artifact is then re-read at the comment it settled as, which is what the
prompt quotes -- held again to the record exactly as the proof held its own
reading, since an edit landing between the two reads could otherwise put words
the evidence never carried under the revision the reviewer is told to reuse.
Asked after the launch has recorded this round's subject, so evidence this
orchestrator executed is held to the subject this reviewer is handed, and a
reviewer's evidence to the subject the last returned reviewer read, which is
this one's only where nothing moved since.

Anything short of that hands no evidence, and the reviewer is told to run the
verification itself. A reading nobody could take is no reason to hold the
round: a reviewer handed nothing to reuse still produces fresh evidence.
"""
from __future__ import annotations

import logging

from github.Issue import Issue

from orchestrator.config import models as _config_models
from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.github.pull_request_reports import ReportPresence
from orchestrator.workflow.engine import (
    review_evidence_prompts as _evidence_prompts,
    review_subjects as _review_subjects,
    verification_current as _current,
    verification_proof as _proof,
    verification_settlement_state as _settlement,
)

log = logging.getLogger("orchestrator.workflow")


def handed_evidence(
    gh: GitHubClient,
    spec: _config_models.RepoSpec,
    issue: Issue,
    state: PinnedState,
    subject: _review_subjects.ReviewSubject,
) -> _evidence_prompts.HandedEvidence | None:
    """The current evidence a reviewer of `subject` is handed, or None for none."""
    current = _settlement.read_current_evidence(state)
    if current is None or current.binding.target.subject != subject.recorded():
        return None
    proved = _proof.current_evidence_verdict(_proof.ProofReading(gh, spec, issue, state))
    if not proved.proved:
        log.info(
            "issue=#%d hands its reviewer no verification evidence: %s",
            issue.number, proved.refusal,
        )
        return None
    presence, found = gh.reread_verification_artifact(proved.pull_request, current.comment_id)
    if presence is not ReportPresence.PRESENT or not _current._is_the_settled_artifact(found, current):
        log.info(
            "issue=#%d hands its reviewer no verification evidence: the "
            "artifact read for the prompt is not the one that settled", issue.number,
        )
        return None
    return _evidence_prompts.HandedEvidence(current, found)
