# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The loops one issue can sit in, and the runs each of them spends.

Every journey here is a shape an issue really gets stuck in, and each is
picked because something about it looks like it ought to buy more runs. A
review answered by a fix answered by a review has no natural end. A base that
moved is rebased onto and a conflict is recovered from, and each of those puts
the review round back to zero itself -- so the two journeys about them stage a
round that has been spent and let the tick reset it, which is the only way a
reset is worth asserting. A session that has been resumed to its limit is
retired and replaced. An issue that goes back to be decomposed and comes out
to be implemented again has changed stage, role, and prompt.

None of those returns a run, and that is the whole of what the table is for:
the counters they DO reset are round counters and session counters, and the
lifetime ledger is neither. A journey added here is a loop somebody found; a
loop nobody added is one nothing holds to the meter.

The late adjudicator is not in the table. It is not a dispatched handler and
runs inside a harness of its own, so its journey lives beside it in
`tests/workflow/stages/decomposition/test_late_lifetime.py`.
"""
from __future__ import annotations

import contextlib
from types import MappingProxyType
from unittest.mock import MagicMock

from orchestrator import config
from tests.workflow import fixtures as _support
from tests.workflow.engine.lifetime_test_support import (
    ALLOWANCE,
    BRANCH,
    DEV_SESSION,
    PR_NUMBER,
    REFUSED_TICKS,
    Journey,
    Leg,
    refreshed_tick,
)
from tests.workflow.git_owners import seam_patch

# The head a round opens on, and the commit the run leaves the checkout at.
_SHA_BEFORE = _support.DEFAULT_PR_HEAD_SHA
_SHA_AFTER = _support.MEASURED_CANDIDATE_SHA

# Pinned keys these legs stage more than once. Wire strings on live issues, so
# they are spelled here rather than retyped per leg.
_KEY_BRANCH = "branch"
_KEY_REVIEW_ROUND = "review_round"

# The watermarks a stage reads its unread feedback against, put back on every
# pass so the road has a batch in front of it rather than one it has read.
_UNREAD_FEEDBACK = MappingProxyType({
    "pr_last_comment_id": 0,
    "pr_last_review_comment_id": 0,
    "pr_last_review_summary_id": 0,
})

# What every delivery leg is entered carrying: the pull request it pushes
# onto, the branch under it, and the developer session it resumes.
_DELIVERING = MappingProxyType({
    "pr_number": PR_NUMBER,
    _KEY_BRANCH: BRANCH,
    "dev_agent": _support.BACKEND_CLAUDE,
    "dev_session_id": DEV_SESSION,
})

# What a human writes on the way into each round that is woken by one. The
# thread is what a round reads its work off, and a round that ran marked what
# it read -- so a loop is a human saying something again rather than a
# watermark somebody put back.
_ASKED_AGAIN = "please carry on"

_CONFLICT_FILE = "a.py"

_CHECKS_PASSED = "success"

# How many reviewer rounds the issue has already spent when a rebase or a
# recovered conflict reaches it. Non-zero on purpose: what the two journeys
# below are about is the tick putting this back to nothing, and a leg that
# staged the reset itself would be asserting on its own fixture.
ROUNDS_SPENT = 2

# What the divergence probe answers while a base that has moved is rebased
# onto: the branch is behind, so there is a rebase to make at all.
_BEHIND_BASE = "2\n"


@contextlib.contextmanager
def _rebase_seams(rebased, behind: str):
    """The three git readings a rebase onto the base is decided by.

    The rebase itself, and the two command seams the fetch and the divergence
    count go through. None of the three is in the hermetic patch set every
    stage runs inside, because no stage handler reads them -- the base refresh
    does, and it is not a stage.
    """
    counted = MagicMock(returncode=0, stdout=behind, stderr="")
    with (
        seam_patch("_rebase_base_into_worktree", MagicMock(
            return_value=rebased,
        )),
        seam_patch("_git", MagicMock(return_value=counted)),
        seam_patch("_git_hardened", MagicMock(return_value=counted)),
    ):
        yield


def _conflict_seams():
    """A rebase that stops on a conflicted file, which is what earns a round."""
    return _rebase_seams((False, [_CONFLICT_FILE]), "0\n")


def _clean_rebase_seams():
    """A rebase onto a base that moved, leaving nothing to resolve."""
    return _rebase_seams((True, []), _BEHIND_BASE)


# The world a round that COMMITS runs in: the two heads its work is measured
# between, and a push that lands.
_PUBLISHING = MappingProxyType({
    "head_shas": (_SHA_BEFORE, _SHA_AFTER),
    "push_branch": True,
})

# What a reviewer round that asks for changes costs: the review itself, and
# the developer resumed inside the same tick to answer it. Two processes and
# two charges -- the ledger counts runs rather than ticks.
_REVIEW_AND_FIX = (
    _support._agent(session_id="rev-sess", last_message=_support.REVIEW_CHANGES_REQUESTED_MESSAGE),
    _support._agent(session_id=DEV_SESSION, last_message="fixed"),
)


FIXING_LEG = Leg(
    role="fixing",
    label=_support.LABEL_FIXING,
    staged={**_DELIVERING, _KEY_REVIEW_ROUND: 1, **_UNREAD_FEEDBACK},
    world=_PUBLISHING,
    agent_result=_support._agent(session_id=DEV_SESSION, last_message="fixed"),
    replies=(_ASKED_AGAIN,),
)

REVIEWING_LEG = Leg(
    role="validating",
    label=_support.LABEL_VALIDATING,
    staged={**_DELIVERING, _KEY_REVIEW_ROUND: 1},
    world=_PUBLISHING,
    agent_result=_REVIEW_AND_FIX,
)

# The reviewer's round as the tick before it left the issue: the round
# counter is not staged at all here, so what this leg runs on is whatever the
# rebase or the conflict recovery ahead of it reset it to.
RESET_REVIEWING_LEG = Leg(
    role="validating-after-reset",
    label=_support.LABEL_VALIDATING,
    staged=_DELIVERING,
    world=_PUBLISHING,
    agent_result=_REVIEW_AND_FIX,
)

CONFLICT_LEG = Leg(
    role="resolving-conflict",
    label=_support.LABEL_RESOLVING_CONFLICT,
    staged={
        **_DELIVERING,
        _KEY_REVIEW_ROUND: ROUNDS_SPENT,
        "conflict_round": 0,
    },
    world={**_PUBLISHING, "fetched_branch_tip": _SHA_BEFORE},
    agent_result=_support._agent(session_id=DEV_SESSION, last_message="resolved"),
    around=_conflict_seams,
)

# The tick that starts no agent at all: the base has moved, the branch is
# rebased onto it and force-pushed, and the round the review cap is counted on
# goes back to nothing. It costs the lifetime ledger nothing, which is exactly
# why a loop built out of it is worth walking.
BASE_SYNC_LEG = Leg(
    role="base-sync",
    label=_support.LABEL_IN_REVIEW,
    staged={**_DELIVERING, _KEY_REVIEW_ROUND: ROUNDS_SPENT},
    world=_PUBLISHING,
    around=_clean_rebase_seams,
    tick=refreshed_tick,
)

ROTATING_LEG = Leg(
    role="implementing-rotation",
    label=_support.LABEL_IMPLEMENTING,
    staged={
        "awaiting_human": True,
        _KEY_BRANCH: BRANCH,
        "dev_agent": _support.BACKEND_CLAUDE,
        "dev_session_id": DEV_SESSION,
        "dev_resume_count": config.DEV_SESSION_MAX_RESUMES,
    },
    world={"has_new_commits": [True], "push_branch": True},
    agent_result=_support._agent(session_id="rotated-sess", last_message="carried on"),
    replies=(_ASKED_AGAIN,),
)

DECOMPOSING_LEG = Leg(
    role="decomposing",
    label=_support.LABEL_DECOMPOSING,
    staged={
        "awaiting_human": False,
        "pr_number": None,
        _KEY_BRANCH: None,
        "decomposer_session_id": None,
    },
    agent_result=_support._agent(
        session_id="dec-sess",
        last_message=_support._manifest(
            '{"decision": "single", "rationale": "one coherent change"}',
        ),
    ),
)

IMPLEMENTING_LEG = Leg(
    role="implementing",
    label=_support.LABEL_IMPLEMENTING,
    staged={
        "awaiting_human": False,
        "dev_session_id": None,
        _KEY_BRANCH: None,
    },
    world={"has_new_commits": [False, True], "push_branch": True},
    agent_result=_support._agent(session_id="dev-fresh", last_message="implemented"),
)


REPEATED_FIXES = Journey(
    name="repeated developer and reviewer rounds",
    legs=(FIXING_LEG, REVIEWING_LEG),
    pull_request=True,
)

RECOVERED_CONFLICTS = Journey(
    name="review rounds reset by a recovered conflict",
    legs=(CONFLICT_LEG, RESET_REVIEWING_LEG),
    pull_request=True,
    # The pull request a conflict round is entered on: one the remote says
    # cannot be merged, whose checks are otherwise green.
    pr_fields={"mergeable": False, "check_state": _CHECKS_PASSED},
)

SYNCED_BASE = Journey(
    name="review rounds reset by a base synchronization",
    legs=(BASE_SYNC_LEG, RESET_REVIEWING_LEG),
    pull_request=True,
    # Half the passes here are refreshes, which start nothing, so the walk
    # takes twice as many ticks to reach the same total.
    ticks=2 * (ALLOWANCE + REFUSED_TICKS),
)

ROTATED_SESSIONS = Journey(
    name="a developer session retired and replaced every round",
    legs=(ROTATING_LEG,),
)

DECOMPOSED_AND_IMPLEMENTED = Journey(
    name="an issue moved back to decomposing and out again",
    legs=(DECOMPOSING_LEG, IMPLEMENTING_LEG),
)

JOURNEYS = (
    REPEATED_FIXES,
    RECOVERED_CONFLICTS,
    SYNCED_BASE,
    ROTATED_SESSIONS,
    DECOMPOSED_AND_IMPLEMENTED,
)

# The two whose first leg is entered on a round the reviewer has spent and
# whose own tick puts it back. What they have in common is the claim: a
# counter that resets is not the counter that ends a lifetime.
RESET_JOURNEYS = (RECOVERED_CONFLICTS, SYNCED_BASE)
