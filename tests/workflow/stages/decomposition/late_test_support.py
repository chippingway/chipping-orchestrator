# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The one oversized candidate the late-mode tests adjudicate.

One frozen generation described once, so the hold, the prompt, the reply
parser, the pinned run record, and the coordinator over them all read the same
candidate: a field added to the record is exercised by every one of them
without five copies of the fixture drifting apart. The harness those tests run
a coordinator inside is the module beside this one.

The pinned keys are gathered on one record rather than spelled loose, because
they are the compatibility contract the late run round-trips through: a test
naming one of them is naming the durable key a live issue would carry.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, replace

from orchestrator.git.measurement.models import (
    AdditionMeasurement,
    MeasurementFailure,
)
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.late_split import state as _late_state
from orchestrator.workflow.late_split.models import LateGeneration, LatePhase
from tests.support.fakes import (
    FakeGitHubClient,
    FakeIssue,
    FakePR,
    make_issue,
)
from tests.workflow import value_helpers as _value_helpers
from tests.workflow.fixtures import LABEL_DECOMPOSING
from tests.workflow.stages.decomposition import late_reply_support as _reply_support

SHA_LENGTH = 40
# What a whole fingerprint is: a SHA-256 digest, which is the exact length the
# identity field beside an exemption is read at.
DIGEST_LENGTH = 64
CANDIDATE_SHA = "a" * SHA_LENGTH
BASE_SHA = "b" * SHA_LENGTH
OTHER_SHA = "c" * SHA_LENGTH
MERGED_SHA = "f" * SHA_LENGTH

CYCLE_ID = 3
GENERATION_NUMBER = 1
NEXT_GENERATION = 2
ROOT_ISSUE = 41
LATE_ISSUE_NUMBER = 41
LINEAGE_DEPTH = 1
THRESHOLD = 4000
ADDITIONS = 9123
UNDERSIZED_ADDITIONS = 12
SCOPE = "the declared slice this generation owns"

PLAN_PR_NUMBER = 77

# The pull request a post-publication generation was measured against, the
# head it was standing on, and the stage the gate took the issue out of --
# the three a settled verdict has to find unchanged before it publishes.
PUBLISHED_PR_NUMBER = 78
PUBLISHED_HEAD_SHA = "d" * SHA_LENGTH
PUBLISHED_SOURCE_STAGE = "workflow:fixing"
# The branch that pull request is open on, which is the branch this issue's
# own publication pushes. A real record can only name the two together: the
# settlement resolves the branch for itself and pushes THAT, so a pull request
# open anywhere else is one its push would never touch.
PUBLISHED_BRANCH = _value_helpers._issue_branch(LATE_ISSUE_NUMBER)

# A branch this issue never publishes to, for the case where the pinned
# comment's own number and branch disagree.
FOREIGN_BRANCH = f"{PUBLISHED_BRANCH}-elsewhere"

# Somebody else's copy of this repository: where a fork's head lives, which is
# the only fact that tells its pull request from one this issue published.
FORK_REPO = "somebody-else/orchestrator"
PLAN_PR_BODY = "the design this plan PR was opened with"
PLAN_BRANCH = "orchestrator/plan"

# What proves a recorded pull request is this issue's plan rather than an
# implementation. The discussion stage's own record, which the implementing
# stage tells the two apart by and the late hold reads through it.
KEY_PLAN_PATH = "discussion_plan_path"
PLAN_PATH = "plans/issue-41.md"

# What a re-measurement answers when a test did not ask for one. Every path
# that reaches the real counter shells out to git in the scratch worktree, so
# the seam is always held -- and held at a failure, because a test that
# reaches it without saying what it expects has not decided anything.
UNASKED_MEASUREMENT = AdditionMeasurement(
    failure=MeasurementFailure.DIFF_FAILED,
)

# What the contribution between the frozen pair fingerprints to, in the world
# a case says nothing about. Spelled once for the seam that answers the
# reading and the tests that read the identity a settled verdict writes.
CONTRIBUTION_DIGEST = "9" * DIGEST_LENGTH


LATE_SESSION_ID = "late-sess"
LATE_SPEC = "claude --effort high"
LATE_BACKEND = "claude"
LATE_ARGS = ("--effort", "high")
ROLE_DECOMPOSER = "decomposer"

HOLD_MARKER_PREFIX = "<!--orchestrator-late-hold"

EVENT_LATE_VERDICT = "late_verdict"
EVENT_LATE_FAILURE = "late_failure"


@dataclass(frozen=True)
class _StateKeys:
    """The pinned keys the late run and its generation round-trip through."""

    agent: str = "late_agent"
    role: str = "late_agent_role"
    session_id: str = "late_session_id"
    run_cycle_id: str = "late_run_cycle_id"
    source_sha: str = "late_source_sha"
    run_generation: str = "late_run_generation"
    verdict: str = "late_result_verdict"
    category: str = "late_result_category"
    question: str = "late_result_question"
    split_blocker: str = "late_result_split_blocker"
    children: str = "late_result_children"
    plan_pr_number: str = "late_plan_pr_number"
    plan_pr_head: str = "late_plan_pr_head"
    plan_pr_body: str = "late_plan_pr_body"
    candidate_sha: str = "late_candidate_sha"
    base_sha: str = "late_base_sha"
    threshold: str = "late_threshold"
    additions: str = "late_additions"
    phase: str = "late_phase"
    cancelled: str = "late_cancelled"
    cancelled_at: str = "late_cancelled_at"
    cancelled_phase: str = "late_cancelled_phase"
    resources: str = "late_resources"
    owner_check_pending: str = "late_owner_check_pending"
    exempt_sha: str = "late_exempt_sha"
    # What the exempt commit CARRIES: the frozen pair the verdict was taken
    # between, the digest of the contribution between them, and the scheme
    # that digest was taken under. Written with the exemption and outliving
    # the retirement on the same terms.
    exempt_base_sha: str = "late_exempt_base_sha"
    exempt_candidate_sha: str = "late_exempt_candidate_sha"
    exempt_fingerprint: str = "late_exempt_fingerprint"
    exempt_fingerprint_format: str = "late_exempt_fingerprint_format"
    post_publication: str = "late_post_publication"
    source_stage: str = "late_source_stage"
    published_pr_number: str = "late_published_pr_number"
    published_sha: str = "late_published_sha"
    approved_sha: str = "late_approved_sha"
    approved_lease: str = "late_approved_lease"
    approved_basis: str = "late_approved_basis"
    # The publishing stage's own receipt rather than a late field: it is what
    # says a commit REACHED the remote, which is the evidence a settlement
    # resumed past its own push is recognized by.
    receipt_sha: str = "implementing_published_sha"
    # The head that receipt replaced, written with it: what dates it to one
    # publication attempt, since the receipt itself is never cleared.
    receipt_lease: str = "implementing_published_lease"
    # The pull request that receipt went onto, written with it by the push
    # that landed. Neither of the two above says WHICH publication received
    # the commit, so a branch pushed from that head onto a pull request since
    # closed and replaced answers for both.
    receipt_pr: str = "implementing_published_pr"
    retry_count: str = "retry_count"
    retry_window: str = "retry_window_start"
    retry_grant: str = "retry_cap_continued"
    agent_runs: str = "issue_agent_runs"
    awaiting: str = "awaiting_human"
    park_reason: str = "park_reason"
    park_notice: str = "late_park_notice"


KEYS = _StateKeys()

# What the accepted commit CARRIES, as one group: it is written with the
# exemption, refused as a whole where any member of it cannot be vouched for,
# and outlives the retirement on the same terms the exemption does.
IDENTITY_KEYS = (
    KEYS.exempt_base_sha,
    KEYS.exempt_candidate_sha,
    KEYS.exempt_fingerprint,
    KEYS.exempt_fingerprint_format,
)


# What a `single` says stopped a split, as the reply carries it and the
# pinned comment keeps it. One sentence spelled once, so the parser, the
# record, and the recovery over them are all read against the same words.
SPLIT_BLOCKER = "the generated client cannot land without its schema"

SINGLE_REPLY = _reply_support.late_block(
    '{"decision": "single", "rationale": "one coherent change",'
    f' "split_blocker": "{SPLIT_BLOCKER}",'
    ' "category": "generated_artifacts"}'
)

# What each proposed child says it will add across all of its paths. Well
# under the threshold every late-mode test measures against, since a child
# sized at the ceiling is one the reply contract refuses.
FIRST_ESTIMATE = 400
SECOND_ESTIMATE = 600


SPLIT_REPLY = _reply_support.late_block(json.dumps({
    "decision": "split",
    "rationale": "two slices",
    "children": [
        _reply_support.proposed_slice("A", "a", FIRST_ESTIMATE),
        _reply_support.proposed_slice("B", "b", SECOND_ESTIMATE, depends_on=(0,)),
    ],
}))

QUESTION_ASKED = "which half of this is in scope?"

QUESTION_REPLY = _reply_support.late_block(
    '{"decision": "question", "category": "scope_ambiguous",'
    f' "question": "{QUESTION_ASKED}"}}'
)

NO_BLOCK_REPLY = "I looked at the diff and it seems fine to me."


def late_generation(**overrides) -> LateGeneration:
    """The oversized generation every late-mode test starts from."""
    return replace(
        LateGeneration(
            cycle_id=CYCLE_ID,
            generation=GENERATION_NUMBER,
            root_issue=ROOT_ISSUE,
            current_issue=LATE_ISSUE_NUMBER,
            lineage_depth=LINEAGE_DEPTH,
            scope=SCOPE,
            candidate_sha=CANDIDATE_SHA,
            base_sha=BASE_SHA,
            threshold=THRESHOLD,
            additions=ADDITIONS,
            phase=LatePhase.MEASURING,
        ),
        **overrides,
    )


def seed_late_issue(
    github: FakeGitHubClient,
    generation: LateGeneration,
    **extra_state,
) -> FakeIssue:
    """Add the late issue to a fake client with its generation recorded.

    An absent `generation` seeds an issue that never entered the gate, since
    a record with no cycle identity writes no late fields at all.
    """
    issue = make_issue(LATE_ISSUE_NUMBER, label=LABEL_DECOMPOSING)
    github.add_issue(issue)
    recorded = PinnedState(data=dict(extra_state))
    _late_state.write_late_generation(recorded, generation)
    github.seed_state(LATE_ISSUE_NUMBER, **recorded.data)
    return issue


def generation_state(generation: LateGeneration) -> dict:
    """The pinned fields one generation round-trips through."""
    written = PinnedState(data={})
    _late_state.write_late_generation(written, generation)
    return written.data


def seeded_late_issue(**extra_state) -> tuple[FakeGitHubClient, FakeIssue]:
    """A fresh fake client carrying the standard oversized generation."""
    github = FakeGitHubClient()
    return github, seed_late_issue(github, late_generation(), **extra_state)


# Every state the gate can take an issue out of, and so every state a settled
# adjudication can put one back into.
PUBLISHED_SOURCE_STAGES = (
    "workflow:validating",
    "workflow:documenting",
    "in_review",
    "workflow:fixing",
    "workflow:resolving_conflict",
)


def seed_plan_pr(
    github: FakeGitHubClient,
    *,
    body: str = PLAN_PR_BODY,
    pr_state: str = "open",
) -> FakePR:
    """Add an open (or settled) plan PR the late hold can reconcile."""
    plan_pr = FakePR(
        number=PLAN_PR_NUMBER,
        head_branch=PLAN_BRANCH,
        body=body,
        state=pr_state,
    )
    github.add_pr(plan_pr)
    return plan_pr
