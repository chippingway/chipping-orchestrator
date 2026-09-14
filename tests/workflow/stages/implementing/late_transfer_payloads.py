# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Commit identities, digests, and publication coordinates for rewrite-transfer cases."""
from __future__ import annotations

from pathlib import Path

from orchestrator.config import models as _config_models
from orchestrator.git.verification.status import _WorktreeStatus
from orchestrator.workflow.state import WorkflowLabel

ISSUE_NUMBER = 42
PR_NUMBER = 77
SOURCE_STAGE = WorkflowLabel.VALIDATING

SHA_LENGTH = 40
DIGEST_LENGTH = 64

# The commit a human adjudicated, the base it was measured over, and the
# object the squash replaced it with over that same base.
ACCEPTED_SHA = "a" * SHA_LENGTH
MERGE_BASE_SHA = "b" * SHA_LENGTH
REWRITTEN_SHA = "c" * SHA_LENGTH
STRANGER_SHA = "d" * SHA_LENGTH

# Where the remote says the base branch is now. Deliberately not the merge
# base the rewrite sits over: a base branch moves on its own, so what a permit
# holds the recorded base to is being a commit this tip's history carries.
BASE_TIP_SHA = "2" * SHA_LENGTH

# A whole object id this issue has nothing to do with: another commit that
# types exactly as any of the four above, which is what a hand edit can move a
# recorded end to without the reader refusing it.
FOREIGN_SHA = "7" * SHA_LENGTH

# The head the pull request is standing on, which is what the force-push is
# leased against. Deliberately NOT the commit the squash collapsed: the entry
# admits a tip a durable record says this issue's own push put there, so the
# two are separate facts and a fixture that spelled them alike would let one
# stand in for the other unnoticed.
LEASED_SHA = "9" * SHA_LENGTH

# What the accepted contribution fingerprints to, and what an unequal one does.
ACCEPTED_DIGEST = "e" * DIGEST_LENGTH
OTHER_DIGEST = "f" * DIGEST_LENGTH

WORKTREE = Path("/tmp/orchestrator-test-late-transfer")

SPEC = _config_models.RepoSpec(
    slug="chippingway/orchestrator",
    target_root=Path("/tmp/orchestrator-test-target-root"),
    base_branch="main",
)

# The branch a gated push names, and the seam that stands in for the request.
BRANCH = "orchestrator/chippingway__orchestrator/issue-42"
PUSH_BRANCH = "_push_branch"

# The three seams the ordinary cumulative reading spends, which a case about
# a REFUSED permit has to seed: falling through to that reading is what the
# refusal costs, and what it publishes is what the settlement then sees.
FREEZE_BASE = "_freeze_base_commit"
BASE_PRESENT = "_base_object_present"
COUNT_ADDED_LINES = "_count_added_lines"

# A count the configured ceiling lets through, so the fallback reading ends in
# a push rather than in the adjudication.
UNDER_THE_CEILING = 3

# The seams a permit spends, named on the owners that define them.
PROVE_CANDIDATE = "_prove_candidate_commit"
WORKTREE_STATUS = "_worktree_status"
FINGERPRINT = "_fingerprint_contribution"
COMMIT_CONTAINS = "_commit_contains"

CLEAN = _WorktreeStatus(readable=True)

# The revision a checkout's own head is named by. Every other revision the
# permit asks about is a commit some record names by id.
_HEAD = "HEAD"
