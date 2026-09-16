# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Whether the pull request a report names is the one it may be published onto.

The repository is asked first, because a slug that disagrees means every reading
below would be taken against somebody else's pull request -- a fork carries this
repository's ref names over its commits and would otherwise agree on everything.
It is asked through the client's own `is_own_repository`, which compares
case-INSENSITIVELY as GitHub does: spelled as an equality here, a record naming
`Octo/Repo` for the repository configured as `octo/repo` would defer forever over
a difference GitHub does not have.

Then the pull request is found by the COMMIT rather than by the number the record
names, which is what makes the answer worth having. The lookup is scoped to the
branch the record froze and searched over every state, so what comes back is the
pull request this exact publication landed on: a number read back on its own says
nothing about whether the work ever got there.

Carrying the commit is what that lookup answers, and it is not what licenses a
report. A human pushing to the branch, a rebase, or a squash moves the head while
the commit stays in the pull request's history -- and the work under review is
then no longer the work the report describes, so a moved head DEFERS. Carrying is
how the pull request is found; standing on the commit is what it has to be doing.

The number is then held against what came back rather than used to fetch it. A
lookup that answers with some other pull request is a publication this
transaction is not about, which is exactly the case a fetch by number would have
hidden.

The code-publication receipt is asked beside all of it, because carrying the
commit says the work is THERE and nothing about how it got there. A report is a
claim about work this orchestrator published, so the receipt has to vouch for it
in both halves: the commit it names and the pull request it names, since a
receipt left by some other publication -- an earlier one of this issue's, or one
written before this transaction -- vouches for nothing here.
"""
from __future__ import annotations

import importlib
import logging
from typing import Any

from orchestrator.github import pull_request_reads as _pr_reads
from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    report_evidence_models as _evidence_models,
    report_records as _records,
    stage_targets as _stage_targets,
)

log = logging.getLogger("orchestrator.workflow")

_PR_OPEN = "open"


def publication_verdict(
    gh: GitHubClient, pending: _records.PendingReport,
) -> _evidence_models.ReportEvidence:
    """Prove the pull request this report may be published onto, or refuse.

    An enumeration nobody could complete holds rather than defers: "no pull
    request carries this" and "nobody could say" are different answers, and
    only the first of them means the commit still needs publishing. Read the
    other way round, a transient failure would send a finished report back to
    the publication gate on every tick.

    The repository is asked through the client rather than compared here, so
    this reading inherits the case-insensitive rule GitHub itself applies.

    A lookup that does not answer with the RECORDED pull request sends the
    question to that pull request by number before it refuses. The search is by
    commit, so a recorded thread whose head was force-pushed off it drops out of
    the answer entirely -- and if it was then closed, the transaction would
    stand down for the rest of the issue's life over work that is finished. The
    number is the one thing a moved head cannot take away, so the ending is
    asked of it directly.
    """
    subject = pending.subject
    if not gh.is_own_repository(subject.repo_slug):
        return _evidence_models.ReportEvidence(
            _evidence_models.ReportEvidenceVerdict.DEFER,
            "the transaction was recorded against another repository",
        )
    found = gh.find_pr_for_commit(
        branch=subject.branch, head_sha=subject.source_sha,
    )
    if found is _pr_reads.PR_LOOKUP_UNREADABLE:
        return _evidence_models.ReportEvidence(
            _evidence_models.ReportEvidenceVerdict.HOLD,
            "the pull requests on the recorded branch could not be read",
        )
    if found is None:
        return _unfound_verdict(
            gh, subject,
            "no pull request on the recorded branch carries the commit yet",
        )
    if found.number != subject.pr_number:
        return _unfound_verdict(
            gh, subject,
            "another pull request carries the commit the report is about",
        )
    return _identified_verdict(found, subject)


def _unfound_verdict(
    gh: GitHubClient, subject: _records.ReportSubject, refusal: str,
) -> _evidence_models.ReportEvidence:
    """Retire a recorded pull request that has ended, or stand down.

    Reached whenever the commit search did not answer with the recorded pull
    request, which is the one case the search cannot decide an ending in: it
    finds a pull request BY the commit, so a thread somebody force-pushed off
    that commit is invisible to it whether it is open or closed. Closed, and
    left to the refusal above, the transaction would be proved impossible on
    every tick forever and the record never dropped -- a report owed to a
    thread nobody will read, held against the issue for good.

    The recorded NUMBER is what survives a moved head, so the ending is asked
    of it. A reading that failed stands down with the refusal it was called
    with rather than holding: what was being added here is a retirement, and a
    tick held on a failed extra reading would sit in front of the publication
    gate that the ordinary refusal is waiting for.
    """
    try:
        recorded = gh.get_pr(subject.pr_number)
    except Exception:
        log.exception(
            "could not read PR #%d to say whether the developer report it is "
            "owed is owed to work that has ended; standing down",
            subject.pr_number,
        )
        return _evidence_models.ReportEvidence(
            _evidence_models.ReportEvidenceVerdict.DEFER, refusal,
        )
    if _pr_reads.pr_state(recorded) != _PR_OPEN:
        return _evidence_models.ReportEvidence(
            _evidence_models.ReportEvidenceVerdict.ENDED,
            "the recorded pull request is no longer open",
        )
    return _evidence_models.ReportEvidence(
        _evidence_models.ReportEvidenceVerdict.DEFER, refusal,
    )


def receipt_verdict(
    state: PinnedState, pending: _records.PendingReport,
) -> _evidence_models.ReportEvidence | None:
    """Refuse until the code-publication receipt vouches for this commit.

    The group is asked whole before either member is believed. `_record_
    publication` writes all three keys on every receipt and clears all three on
    none, so a partial group is not a record with a gap in it but one nothing
    here produced -- and every reader in that domain is fail-closed, so read
    member by member a damaged group answers "no receipt" and this evidence
    would defer forever instead of saying what a human has to repair.

    Then both halves, because neither answers alone: the commit says what
    reached a remote and the pull request says which publication now
    carries it. Deferred rather than held, because what WRITES that receipt is
    the publication gate the stage behind this evidence reaches -- so a
    transaction recorded ahead of a push waits here for exactly one tick's
    worth of ordinary progress.

    The receipt's owner is imported when this is called rather than above, for
    the reason every stage owner the engine reaches is: the stage tree imports
    the engine back, so binding it here would make importing the engine pull
    the handlers it drives.
    """
    subject = pending.subject
    damaged = importlib.import_module(
        _stage_targets._LATE_RECEIPT_DAMAGE_OWNER,
    )._damaged_receipt(state)
    if damaged:
        return _evidence_models.ReportEvidence(
            _evidence_models.ReportEvidenceVerdict.HOLD,
            f"the code-publication receipt cannot be read ({damaged})",
        )
    publication_state = importlib.import_module(
        _stage_targets._LATE_PUBLICATION_STATE_OWNER,
    )
    if publication_state._published_commit(state) != subject.source_sha:
        return _evidence_models.ReportEvidence(
            _evidence_models.ReportEvidenceVerdict.DEFER,
            "no code-publication receipt names the commit the report is about",
        )
    if publication_state._published_pull_request(state) != subject.pr_number:
        return _evidence_models.ReportEvidence(
            _evidence_models.ReportEvidenceVerdict.DEFER,
            "the code-publication receipt names another pull request",
        )
    return None


def _identified_verdict(
    pull_request: Any, subject: _records.ReportSubject,
) -> _evidence_models.ReportEvidence:
    """Prove the recorded pull request is one this report may be published onto.

    Reached only for the pull request the record NAMES -- a lookup answering
    with any other is a publication this transaction is not about, and is
    refused above through the reader that can also retire it.

    One that is no longer open ends the transaction: a report posted to a
    merged or closed pull request is a comment nobody is going to read.

    Carrying the commit is what FOUND this pull request, and it is not enough
    to settle on. A head that has moved past the recorded commit -- a human
    pushing to the branch, a rebase, a squash -- leaves the commit in the
    pull request's history while the work under review is no longer the work
    the report describes. The report names one commit, so the pull request has
    to be standing on it.
    """
    if _pr_reads.pr_state(pull_request) != _PR_OPEN:
        return _evidence_models.ReportEvidence(
            _evidence_models.ReportEvidenceVerdict.ENDED,
            "the pull request is no longer open",
        )
    if getattr(pull_request.head, "sha", None) != subject.source_sha:
        return _evidence_models.ReportEvidence(
            _evidence_models.ReportEvidenceVerdict.DEFER,
            "the pull request has moved off the commit the report is about",
        )
    return _evidence_models.ReportEvidence(
        _evidence_models.ReportEvidenceVerdict.PROVED,
        pull_request=pull_request,
    )
