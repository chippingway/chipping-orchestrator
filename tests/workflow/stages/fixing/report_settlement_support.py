# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The world one fixing round's report is recorded, published and settled in.

A fix round that finishes on a report owes a publication the tick cannot
guarantee, so what it consumed and what its route spent ride the RECORD and are
applied by the write that completes the transaction. Proving that takes the
whole road in one world: an open pull request standing where the round left it,
a checkout still on that commit, an issue whose requirements have not moved, and
a comment carrying the bookmarks and the round a settlement is supposed to
close.

Each case then moves exactly one of those, so what a refusal is about is the
thing the case changed. The requirements revision is computed from the issue
rather than written down, because that is what the evidence compares against: a
fixture spelling a digest of its own would pass or fail on the fixture.

What a settlement LEAVES is here too, and it is a different fixture: a handoff
and the mark beside it outlive every transaction after them, so a case about a
stale correlation seeds them directly rather than by running a round.
"""

from __future__ import annotations

import contextlib
from pathlib import Path

from orchestrator.git.verification.status import _WorktreeStatus
from orchestrator.github import (
    developer_reports as _dev_reports,
    pinned_state as _pinned_state,
)
from orchestrator.workflow.engine import (
    content_hash as _content_hash,
    prompt_delivery as _prompt_delivery,
    report_records as _records,
    report_settlement_state as _settlement,
)
from orchestrator.workflow.stages.fixing import models as _models
from orchestrator.workflow.stages.implementing import (
    late_gate_models as _late_gate_models,
)
from orchestrator.workflow.state import WorkflowLabel
from tests.support.fakes import FakeGitHubClient, FakePR, FakePRRef, make_issue
from tests.workflow.fixtures import (
    _TEST_SPEC,
    LABEL_FIXING,
    SHA_LENGTH,
    TEST_REPO_SLUG,
    _agent,
)
from tests.workflow.git_owners import seam_patch

ISSUE_NUMBER = 880

PR_NUMBER = 880

BRANCH = "orchestrator/chippingway__orchestrator/issue-880"

# The head the round opened on, which the pull request is standing on because
# the reviewer had just read it, and the head a round that committed nothing
# leaves the checkout at. Whole object ids: a recorded commit is read back at
# its exact length, so an abbreviation is no commit at all.
HEAD_SHA = "a" * SHA_LENGTH

MOVED_SHA = "b" * SHA_LENGTH

REPORT_TEXT = "Answered the review: renamed the temp var and added the test."

READY_MESSAGE = f"REPORT: READY\n{REPORT_TEXT}\nREPORT: END"

ACK_MESSAGE = "ACK: nothing to change here."

# A reply that reaches for the contract and misses: an `ACK:` line beside a
# report, which the two readings contradict each other on.
MISREAD_MESSAGE = f"ACK: nothing to change here.\n\n{READY_MESSAGE}"

# The comment a round asserts its report is already published as, and the
# message asserting it -- the exact place and the digest read there, which is
# the whole of what a verification claims.
VERIFIED_COMMENT_ID = 4242

VERIFIED_MESSAGE = (
    "done\n\nREPORT: VERIFIED "
    f"https://github.com/{TEST_REPO_SLUG}/pull/{PR_NUMBER}"
    f"#issuecomment-{VERIFIED_COMMENT_ID} "
    f"sha256:{_dev_reports.content_digest(REPORT_TEXT)}"
)

# The highest id on the pull request conversation this round's prompt quoted,
# and the boundary the comment carries until the report answering it lands.
CONSUMED_ID = 2100

UNREAD_ID = 1999

PR_WATERMARK = "pr_last_comment_id"

# What the in_review route writes when it hands a pull request to `fixing`: the
# discriminator saying whose round this is, and the bookmark a replay rebuilds
# the triggering batch from. Both are cleared by the write that settles the
# report the round hands back.
PENDING_FIX_AT = "pending_fix_at"

PENDING_FIX_ISSUE_MAX_ID = "pending_fix_issue_max_id"

# The validating route's own anchor, which a settlement clears too.
REVIEWER_ANCHOR = "pending_fix_reviewer_comment_id"

OPENED_AT = "2026-05-24T00:00:00+00:00"

REVIEW_ROUND = "review_round"

SPENT_ROUND = 2

# The mark a fixing report transaction's own settlement raises, spelled as the
# comment carries it: a case seeding one by hand seeds what a settlement left.
SETTLED_ROUND = "fixing_round_settled"

AWAITING_HUMAN = "awaiting_human"

PARK_REASON = "park_reason"

PR_NUMBER_FIELD = "pr_number"

BRANCH_FIELD = "branch"


def agent(message: str, **overrides):
    """One finished run's result, with its last message spelled by a case."""
    return _agent(last_message=message, **overrides)


def owed_round() -> _late_gate_models._Spends:
    """The route bookkeeping a reviewer-requested fix round hands over."""
    return _late_gate_models._Spends(fields=(
        (REVIEW_ROUND, SPENT_ROUND),
        (PENDING_FIX_AT, None),
        (PENDING_FIX_ISSUE_MAX_ID, None),
    ))


def consumed_batch() -> tuple:
    """The readers a round's prompt delivered, frozen for its report."""
    return ((PR_WATERMARK, CONSUMED_ID),)


@contextlib.contextmanager
def a_checkout(*, readable: bool = True):
    """A worktree probe answering a tree with nothing loose in it.

    The report-only reading asks the tree through `is_clean`, so a case about
    it has to answer the probe rather than leave it to whatever a host holds.
    `readable=False` is the status nobody could take, which is the one shape an
    empty path list reads identically to and which no report may go out over.
    """
    with seam_patch(
        "_worktree_status",
        lambda *_args: _WorktreeStatus(readable=readable),
    ):
        yield


class FixingReportCase:
    """One issue on `workflow:fixing` whose round is about to report."""

    def setUp(self) -> None:
        self.issue = make_issue(ISSUE_NUMBER, label=LABEL_FIXING)
        self.pull_request = FakePR(
            number=PR_NUMBER,
            head_branch=BRANCH,
            head=FakePRRef(sha=HEAD_SHA),
            commit_shas=(HEAD_SHA,),
        )
        self.gh = FakeGitHubClient([self.issue])
        self.gh.add_pr(self.pull_request)
        self.spec = _TEST_SPEC
        self.state = _pinned_state.PinnedState(comment_id=1, state_data={
            PR_NUMBER_FIELD: PR_NUMBER,
            BRANCH_FIELD: BRANCH,
            _prompt_delivery.PINNED_USER_CONTENT_HASH: self.requirements(),
            PR_WATERMARK: UNREAD_ID,
            REVIEW_ROUND: 1,
            PENDING_FIX_AT: OPENED_AT,
            PENDING_FIX_ISSUE_MAX_ID: CONSUMED_ID,
        })

    def requirements(self) -> str:
        """The revision the issue's content currently hashes to."""
        return _content_hash._compute_user_content_hash(self.issue, set())

    def ctx(self) -> _models._FixingContext:
        """The per-tick handles every disposition helper is handed."""
        return _models._FixingContext(
            gh=self.gh,
            spec=self.spec,
            issue=self.issue,
            state=self.state,
            pr=self.pull_request,
        )

    def resume_run(self, **overrides) -> _models._FixingResumeRun:
        """One finished dev resume, with any member replaced.

        The default is the round this owner is about: a completed run that
        committed nothing, wrote its report, and left the checkout standing on
        the head its pull request already carries.
        """
        fields = {
            "worktree": Path("/tmp/orchestrator-fixing-report-worktree"),
            "dev_result": agent(READY_MESSAGE),
            "paused": False,
            "before_sha": HEAD_SHA,
            "after_sha": HEAD_SHA,
            "reported": True,
        }
        return _models._FixingResumeRun(**(fields | overrides))

    def pinned(self) -> dict:
        """What the pinned comment carries now, as GitHub holds it."""
        return self.gh.read_pinned_state(self.issue).data

    def records_a_settlement(self, *, under: WorkflowLabel | None) -> None:
        """Leave the comment a settlement under `under` would have left.

        Written through the engine's own writer, so a correlation case is
        asked about a record this build really produces -- and with both route
        anchors gone, because a settlement closes them: a comment still
        carrying one is a LATER round having opened, which is one of the
        readings the correlation is about.
        """
        _settlement.record_handoff(self.state, _records.ReportHandoff(
            receipt=f"issue-{ISSUE_NUMBER}-report-1",
            pr_number=PR_NUMBER,
            report_revision=1,
            source_sha=HEAD_SHA,
            settled_under=under,
        ))
        for anchor in (PENDING_FIX_AT, PENDING_FIX_ISSUE_MAX_ID):
            self.state.set(anchor, None)
        self.state.set(SETTLED_ROUND, True)


class RelabelRecorder:
    """The relabel seam, recording what the comment carried when it fired.

    The ORDER is the contract a hand-back rests on: the mark has to be down
    and durable before the label moves, so a tick that dies between the two
    leaves a round nothing can mistake for one that has just settled.
    """

    def __init__(self, case: FixingReportCase) -> None:
        self.case = case
        self.relabel = case.gh.set_workflow_label
        self.durable: list = []

    def __call__(self, issue, label) -> None:
        """Take the relabel, noting the mark the comment still carries."""
        self.durable.append(self.case.pinned().get(SETTLED_ROUND))
        self.relabel(issue, label)
