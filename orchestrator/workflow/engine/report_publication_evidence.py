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

Then ONE pull request is read, by the number the record froze. A number is
unique in a repository and a search is not: several pull requests can stand on
one branch carrying one commit -- a replacement opened beside the original, a
second thread raised against another base -- and a search answering with
whichever it reaches first would refuse this transaction on every tick for the
rest of the issue's life while the pull request it names sits open on the very
commit the report is about. It would also hide an ENDING, since a thread
force-pushed off the commit drops out of a search by commit whether it is open
or closed.

Everything that search would have proved is then asked of the object that came
back, and more. The branch and the head repository say this is the publication
the record is about rather than one wearing its number; and the head has to BE
the recorded commit, which is strictly more than carrying it. A human pushing to
the branch, a rebase, or a squash moves the head while the commit stays in the
pull request's history -- and the work under review is then no longer the work
the report describes, so a moved head DEFERS.

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

    The pull request is read by the NUMBER the record froze, and everything
    that makes it the right one is then asked of the object that comes back. A
    number is unique in a repository and a search is not: several pull requests
    can stand on one branch carrying one commit -- a replacement opened beside
    the original, a second thread somebody raised against another base -- and a
    search answering with whichever it reaches first would refuse this
    transaction forever while the pull request it names sits open on the very
    commit the report is about.

    What the search did prove, and a bare number does not, is that the work
    actually got there. That is not lost: the head read off this object has to
    BE the recorded commit, which is strictly more than carrying it. So the
    reading is one request, about one thread, and it answers every question the
    enumeration did.

    A read that did not happen HOLDS. "The pull request is not what the record
    says" and "nobody could say" are different answers and only the first may
    be acted on -- read the other way round, a transient failure would send a
    finished report back to the publication gate on every tick, or retire a
    transaction over a pull request nobody managed to look at.

    EVERY read of this reading is inside that boundary, not just the fetch.
    The client resolves its repository lazily, so asking whether a slug is our
    own can complete the repository; and the members read off the pull request
    are lazy too, so the state, the head ref, the head repository and the head
    sha are each a request that can fail on a worker that has not completed the
    object yet. Left outside, any one of them leaves this guard by an exception
    rather than by a verdict -- through the dispatcher and out of the tick --
    which is the one answer a reading here may never give.

    The repository is asked through the client rather than compared here, so
    this reading inherits the case-insensitive rule GitHub itself applies.
    """
    return subject_verdict(gh, pending.subject)


def subject_verdict(
    gh: GitHubClient, subject: _records.ReportSubject,
) -> _evidence_models.ReportEvidence:
    """The reading above, for any record bound to a report subject.

    Public for the verification-evidence transaction, whose target is a
    report subject about the head the evidence is written for: one reading,
    under one boundary, proves both kinds of record against a pull request.
    """
    try:
        return _read_verdict(gh, subject)
    except Exception:
        log.exception(
            "the pull request a record is bound to (#%d) could not be read; "
            "holding the tick", subject.pr_number,
        )
        return _evidence_models.ReportEvidence(
            _evidence_models.ReportEvidenceVerdict.HOLD,
            "the recorded pull request could not be read",
        )


def _read_verdict(
    gh: GitHubClient, subject: _records.ReportSubject,
) -> _evidence_models.ReportEvidence:
    """Take the whole pull-request reading, raising where one read fails.

    Spelled apart from the verdict above so that every read it makes is under
    one boundary rather than each one being wrapped where it stands. What the
    caller is owed on any of them failing is the same answer, and a reading
    assembled from parts that each fell back to a verdict of their own would
    be a publication proved against a world nobody saw whole.
    """
    if not gh.is_own_repository(subject.repo_slug):
        return _evidence_models.ReportEvidence(
            _evidence_models.ReportEvidenceVerdict.DEFER,
            "the transaction was recorded against another repository",
        )
    return _identified_verdict(gh, gh.get_pr(subject.pr_number), subject)


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
    gh: GitHubClient, pull_request: Any, subject: _records.ReportSubject,
) -> _evidence_models.ReportEvidence:
    """Prove the recorded pull request is one this report may be published onto.

    The number brought this object back and proves nothing else about it, so
    every other member of the subject is asked of it here.

    ENDED is asked first, ahead of the three that could disagree. A pull
    request that has merged or closed needs no report, whatever its head or its
    branch now says -- and a refusal taken before the ending would strand a
    transaction on work that is over, which is the one outcome this whole
    reading cannot recover from.

    The branch and the head repository are what say this is the publication the
    record is about rather than one that happens to wear its number. A pull
    request's head ref cannot move on GitHub, so a disagreement is a record
    naming two things that never went together; and a head in ANOTHER
    repository is a fork's branch, which carries this repository's ref names
    over somebody else's commits.

    The head commit is last and is the one that says the work got there. A head
    that has moved past the recorded commit -- a human pushing to the branch, a
    rebase, a squash -- leaves the commit in the pull request's history while
    the work under review is no longer the work the report describes. The
    report names one commit, so the pull request has to be STANDING on it.
    """
    if _pr_reads.pr_state(pull_request) != _PR_OPEN:
        return _evidence_models.ReportEvidence(
            _evidence_models.ReportEvidenceVerdict.ENDED,
            "the recorded pull request is no longer open",
        )
    head = getattr(pull_request, "head", None)
    if getattr(head, "ref", None) != subject.branch:
        return _evidence_models.ReportEvidence(
            _evidence_models.ReportEvidenceVerdict.DEFER,
            "the recorded pull request is not on the recorded branch",
        )
    if not gh.is_own_repository(getattr(getattr(head, "repo", None), "full_name", None)):
        return _evidence_models.ReportEvidence(
            _evidence_models.ReportEvidenceVerdict.DEFER,
            "the recorded pull request is built from another repository",
        )
    if getattr(head, "sha", None) != subject.source_sha:
        return _evidence_models.ReportEvidence(
            _evidence_models.ReportEvidenceVerdict.DEFER,
            "the pull request has moved off the recorded commit",
        )
    return _evidence_models.ReportEvidence(
        _evidence_models.ReportEvidenceVerdict.PROVED,
        pull_request=pull_request,
    )
