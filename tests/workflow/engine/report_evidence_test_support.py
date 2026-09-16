# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""One outstanding developer report, and the world its evidence is read in.

The default world is the one a transaction is recorded in: a clean checkout
standing on the commit the report is about, an open pull request on the recorded
branch standing on that commit, a code-publication receipt naming both, and an
issue whose requirements are still the ones the run was handed. Each case then
moves exactly one of those, so what a refusal is about is the thing the case
changed.

Nothing here writes the transaction onto the pinned comment. The evidence owners
are handed a `PendingReport` and answer about the WORLD, so a fixture recording
one would tie these cases to the record round trip that is proved next door and
make every verdict here readable two ways.

The requirements revision is computed from the issue rather than written down,
because that is what the evidence compares against: a fixture spelling a digest
of its own would pass or fail on the fixture rather than on the record.

Every git reading the evidence takes travels on one `checkout` record, owned by
`report_checkout_fixture` beside this, so a case that moves the head or the
remote does not have to know which owner answers it.
"""
from __future__ import annotations

import contextlib
import tempfile

from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    content_hash as _content_hash,
    report_evidence as _evidence,
    report_evidence_models as _evidence_models,
    report_records as _records,
)
from orchestrator.workflow.stages.implementing import (
    late_publication_state as _publication_state,
    state as _implementing_state,
)
from orchestrator.workflow.state import WorkflowLabel
from tests.support.fakes import FakeGitHubClient, FakePR, FakePRRef, make_issue
from tests.workflow.engine.report_checkout_fixture import Fetched, fresh_checkout
from tests.workflow.fixtures import _TEST_SPEC, LABEL_VALIDATING, SHA_LENGTH
from tests.workflow.git_owners import seam_patch

ISSUE_NUMBER = 7

PR_NUMBER = 12

OTHER_PR_NUMBER = 13

BRANCH = "orchestrator/chippingway__orchestrator/issue-7"

SOURCE_SHA = "3f786850e387550fdab836ed7e6dc881de23001b"

MOVED_SHA = "ab" * (SHA_LENGTH // 2)

RECEIPT = "issue-7-report-1"

REPORT_TEXT = "Implemented the change.\n\nChecks: `uv run pytest tests` passed."

# What `_authed_fetch` answers with where the ref could not be refreshed.
FETCH_REFUSED = 128

# What a read GitHub would not answer raises.
REFUSED = "GitHub did not answer the read"

# The four verdicts, named here so a case asserts the answer rather than the
# enum path to it.
PROVED = _evidence_models.ReportEvidenceVerdict.PROVED

HOLD = _evidence_models.ReportEvidenceVerdict.HOLD

DEFER = _evidence_models.ReportEvidenceVerdict.DEFER

ENDED = _evidence_models.ReportEvidenceVerdict.ENDED

# The code-publication receipt group, read off the owner that writes it rather
# than respelled, so a case damaging a member damages the field production uses.
PUBLISHED_SHA = _implementing_state._PUBLISHED_SHA

PUBLISHED_PR = _implementing_state._PUBLISHED_PR

PUBLISHED_LEASE = _implementing_state._PUBLISHED_LEASE


class ReportEvidenceCase:
    """An issue owing one report, and every reading the evidence takes of it."""

    def setUp(self) -> None:
        worktrees = contextlib.ExitStack()
        self.addCleanup(worktrees.close)
        self.checkout = fresh_checkout(
            worktrees.enter_context(tempfile.TemporaryDirectory()), SOURCE_SHA,
        )
        self.issue = make_issue(ISSUE_NUMBER, label=LABEL_VALIDATING)
        # Standing ON the recorded commit, not merely carrying it: a head
        # that has moved past the report's commit is a pull request whose work
        # is no longer what the report describes.
        self.pull_request = FakePR(
            number=PR_NUMBER,
            head_branch=BRANCH,
            head=FakePRRef(sha=SOURCE_SHA),
            commit_shas=(SOURCE_SHA,),
        )
        self.gh = FakeGitHubClient([self.issue])
        self.gh.add_pr(self.pull_request)
        self.state = PinnedState(comment_id=1)
        # Written through the gate's own owner, which puts all three members
        # down: a fixture spelling two of them would seed a PARTIAL group, and
        # the receipt's damage reader is right to call that damage.
        _publication_state._record_publication(
            self.state, SOURCE_SHA, "", PR_NUMBER,
        )

    def requirements(self) -> str:
        """The revision the issue's content currently hashes to."""
        return _content_hash._compute_user_content_hash(self.issue, set())

    def subject(self, **overrides) -> _records.ReportSubject:
        """What the report is about, with any member replaced."""
        about = {
            "repo_slug": self.gh.repo_slug,
            "pr_number": PR_NUMBER,
            "branch": BRANCH,
            "source_sha": SOURCE_SHA,
            "requirements_revision": self.requirements(),
        }
        return _records.ReportSubject(**(about | overrides))

    def pending(self, **overrides) -> _records.PendingReport:
        """The transaction this issue owes, with any member replaced."""
        owed = {
            "receipt": RECEIPT,
            "subject": self.subject(),
            "report_revision": 1,
            "mode": _records.ReportMode.PUBLISH,
            "route": WorkflowLabel.VALIDATING,
            "report": REPORT_TEXT,
        }
        return _records.PendingReport(**(owed | overrides))

    def publication(
        self, owed: _records.PendingReport | None = None,
    ) -> _evidence_models.ReportEvidence:
        """The pull-request reading alone, which every other one stands behind."""
        return _evidence.publication_for(self.gh, owed or self.pending())

    def evidence(
        self, owed: _records.PendingReport | None = None,
    ) -> _evidence_models.ReportEvidence:
        """Every reading one transaction needs, taken in the order it runs in.

        `owed` is composed by the caller for any case about the REQUIREMENTS,
        because the revision a record freezes is computed by the very reader
        such a case moves. Built here it would be computed after the move: a
        case editing the issue would record the edit it means to be refused
        over, and a case refusing the read would raise out of the fixture
        instead of being answered by the evidence.
        """
        pending = owed or self.pending()
        with self._seams():
            return _evidence.evidence_for(
                _TEST_SPEC, self.issue, self.state, pending,
                _evidence.publication_for(self.gh, pending),
            )

    @contextlib.contextmanager
    def _seams(self):
        """The git readings the evidence takes, answered from the case."""
        with contextlib.ExitStack() as seams:
            seams.enter_context(
                seam_patch("_worktree_path", lambda *_args: self.checkout.path),
            )
            seams.enter_context(
                seam_patch("_worktree_status", lambda *_args: self.checkout.status),
            )
            seams.enter_context(
                seam_patch("_head_sha", lambda *_args: self.checkout.head),
            )
            seams.enter_context(seam_patch(
                "_authed_fetch",
                lambda *_args, **_kw: Fetched(self.checkout.fetched),
            ))
            seams.enter_context(
                seam_patch("_branch_divergence", lambda *_args: self.checkout.remote),
            )
            yield
