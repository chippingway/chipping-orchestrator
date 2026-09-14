# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Repository and backend values shared by workflow tests."""
from pathlib import Path

from orchestrator.config import models as _config_models

TEST_REPO_SLUG = "chippingway/orchestrator"
TEST_BASE_BRANCH = "main"
# What the remote says the base branch is at when a round opens. Pinned
# before the spawn, so a test seeding a round that already ran has to seed
# this too or its plan is measured against nothing.
BASE_TIP_SHA = "base-branch-tip"

# The two commits the size gate freezes a candidate between. Whole object
# ids, unlike the readable tip above, because these two round-trip through
# the pinned comment -- which reads a frozen commit at its exact length and
# drops anything else, so a readable stand-in would come back absent.
SHA_LENGTH = 40
# How many times an eight-character group repeats to fill one whole id.
SHA_LENGTH_EIGHTHS = SHA_LENGTH // 8
MEASURED_BASE_SHA = "b" * SHA_LENGTH
MEASURED_CANDIDATE_SHA = "c" * SHA_LENGTH

# What the checkout's own head reads as before and after a run, in the world
# a test says nothing about. Two values rather than one because the ordinary
# world is a run that COMMITTED: the dispositions decide by comparing the two
# ends, so a single value says "the head never moved" and no value at all says
# "the probe failed" -- both of which are refusals a test should have to ask
# for. A test about either seeds the readings it is about.
#
# The post-run head IS the commit the size gate proves the checkout to, because
# in production the two are one read of one worktree: a route names the commit
# it means to publish and the gate refuses a checkout standing anywhere else.
# Both are whole object ids for the same reason the pair above is -- a commit
# field is read at its exact length.
HEAD_BEFORE_RUN = "be40e5ba" * SHA_LENGTH_EIGHTHS
HEAD_AFTER_RUN = MEASURED_CANDIDATE_SHA

# The commit a contribution is read over: the fork point where its branch left
# the base. Two values, because telling them apart is the whole of what a
# rebase does -- the head it replays forks from one commit and the head it
# produces from another -- so a world with one answer for both is a branch
# nothing rebased. Whole object ids for the reason the pair above is: a rewrite
# record reads every end at its exact length.
FORK_POINT_SHA = "e" * SHA_LENGTH
REPLAYED_FORK_POINT_SHA = "f" * SHA_LENGTH

# What the contribution between the two frozen commits fingerprints to in the
# world a test says nothing about. A whole SHA-256 digest, because that is
# what a fingerprint field is read at: a shorter stand-in would come back
# absent and no identity written from it would round-trip.
DIGEST_LENGTH = 64
CONTRIBUTION_DIGEST = "d" * DIGEST_LENGTH

STATE_CLOSED = "closed"
STATE_OPEN = "open"

BACKEND_CLAUDE = "claude"
BACKEND_CODEX = "codex"

_FAKE_WT = Path("/tmp/orchestrator-test-wt-doesnt-matter")
_TEST_SPEC = _config_models.RepoSpec(
    slug=TEST_REPO_SLUG,
    target_root=Path("/tmp/orchestrator-test-target-root"),
    base_branch=TEST_BASE_BRANCH,
)
