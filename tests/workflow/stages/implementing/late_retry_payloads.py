# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Changed checkout proofs, human replies, and measurement failures for retry cases."""
from __future__ import annotations

from orchestrator.git.measurement.models import FrozenCommit, MeasurementFailure
from orchestrator.workflow.stages.implementing import (
    state as _implementing_state,
)
from tests.workflow.fixtures import (
    LABEL_DECOMPOSING,
    MEASURED_CANDIDATE_SHA,
    SHA_LENGTH,
    _reported,
)
from tests.workflow.stages.implementing import late_gate_test_support as support

_ANSWERS_THE_PARK = "_answers_the_measurement_park"
_PARKED_CONTINUE_DECISION = "_parked_continue_decision"

_MOVED_SHA = "e" * SHA_LENGTH
# What a checkout somebody moved reads as, and the two successive readings of
# one that moves mid-tick: the recorded commit when a reconciliation proves it
# before starting, and something else by the time the gate reads it again.
# Nothing of this tick's put it there.
_MOVED_HEAD = FrozenCommit(sha=_MOVED_SHA)
_HEAD_MOVES = (FrozenCommit(sha=MEASURED_CANDIDATE_SHA), _MOVED_HEAD)
# The same move onto a commit this host names and cannot peel: an object a
# prune took, or work made somewhere else. It carries an id, which is what
# makes it the sharpest of these -- a name is exactly what a park records.
_HEAD_MOVES_TO_ABSENT = (
    FrozenCommit(sha=MEASURED_CANDIDATE_SHA),
    FrozenCommit(
        sha=_MOVED_SHA, failure=MeasurementFailure.CANDIDATE_ABSENT,
    ),
)

# What a checkout a recordless park comes back to can be standing on, none of
# which anything ties to this issue: the commit the developer left, one a
# rebase or reset moved it to, and one a rebuilt worktree cannot name at all.
_RECORDLESS_CHECKOUTS = (
    ("the head it was left on", None),
    ("a head somebody moved", _MOVED_HEAD),
    ("a head nothing can read", FrozenCommit(
        failure=MeasurementFailure.CANDIDATE_UNREADABLE,
    )),
)

# Each of them under both switch settings, since the switch decides what
# ENTERS the gate and decides nothing about a park already waiting on one.
_RECORDLESS_RETRIES = tuple(
    (checkout, head, decomposing)
    for checkout, head in _RECORDLESS_CHECKOUTS
    for decomposing in (True, False)
)
_REAPED_WORKTREE = support.Path("/nonexistent/orchestrator-reaped-worktree")
# The step a checkout that is gone stops the reading at, which is what the
# record names beside `measurement_failed`: the commit is not on this host.
_CHECKOUT_GONE = MeasurementFailure.CANDIDATE_ABSENT
_DECOMPOSING = (support.GATE_ISSUE_NUMBER, LABEL_DECOMPOSING)
_AGENT_TIMEOUT = "agent_timeout"
_PRE_IMPLEMENT_SHA = "pre_implement_sha"
_PRE_TIMEOUT_SHA = "sha-pre"
_POST_TIMEOUT_SHA = "sha-post"
# The sentence the generic parked-continue classifier posts, which a
# measurement park must never reach.
_NEEDS_GUIDANCE = "needs your actual guidance"
_DECOMPOSE = "DECOMPOSE"
# The reply a human writes to make the developer change the work, and
# what a resumed run says when it has.
_GUIDANCE = "drop the generated fixtures from this"
_FINISHED = _reported("done")
# What a resumed run says when it answered instead of building.
_ASKED = "which half of this did you mean?"

# What a scrubbed transport failure hands up for a human to read, and the two
# things the notice built around it has to say for itself: which invocation
# could not be taken, and where the operator reads what it wrote.
_REMOTE_SAID = "fatal: Authentication failed for 'https://github.com/o/r/'"
_LS_REMOTE = "ls-remote"
_GIT_PLUMBING = "orchestrator.git_plumbing"

# The hidden receipt every comment this workflow posts carries, which is what
# the user-content hash reads a bot comment by once its id has been evicted.
_ORCH_COMMENT_MARKER = "<!--orchestrator-comment-->"

# The steps a second reading cannot change: nothing here can pin the diff,
# git refused it, or what came back was unreadable. Each is a park on the
# first miss, since the retry a transport fault is owed would buy the same
# answer over and over.
_UNRETRIED_STEPS = (
    MeasurementFailure.DIFF_UNPINNABLE,
    MeasurementFailure.DIFF_FAILED,
    MeasurementFailure.DIFF_UNREADABLE,
)

# How many readings one frozen pair may lose to the transport before the gate
# stops taking them again by itself. Read off the owner rather than spelled
# again, so a case names the bound rather than a number beside it.
_MISS_BOUND = _implementing_state._MEASUREMENT_MISSES_BEFORE_PARK

# The readings a pair has already lost, and whether the next one is the one
# that hands the issue over: the bound is on consecutive misses, so the tick
# that takes the last of them is quiet and the one past it is not.
_BOUNDED_MISSES = tuple(
    (lost, lost >= _MISS_BOUND) for lost in range(_MISS_BOUND + 1)
)
