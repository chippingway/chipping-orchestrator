# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Commands, measurements, receipts, and pinned payloads for oversized-candidate consent."""
from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from types import MappingProxyType

from orchestrator.git.measurement.models import (
    AdditionMeasurement,
    ContributionFingerprint,
    FingerprintFailure,
    MeasurementFailure,
)
from orchestrator.github.pinned_state import (
    MAX_PINNED_BODY,
    PINNED_STATE_MARKER,
    PinnedState,
)
from orchestrator.workflow.late_split import state as _late_state
from orchestrator.workflow.late_split.models import LateGeneration, LatePhase
from orchestrator.workflow.stages.implementing import (
    late_consent as _consent,
    late_records as _records,
)
from tests.workflow.fixtures import (
    LABEL_IMPLEMENTING,
    MEASURED_BASE_SHA,
    MEASURED_CANDIDATE_SHA,
    SHA_LENGTH,
)
from tests.workflow.repo_values import CONTRIBUTION_DIGEST

FINGERPRINT_CONTRIBUTION = "_fingerprint_contribution"
FROZEN_PAIR = "_frozen_pair"
COUNT_ADDED_LINES = "_count_added_lines"
SETTLED = "_settled"
# The two the verdict owner reaches past that one: the publication a count at
# or below the ceiling earns, and the hold an oversized candidate nobody has
# ruled on is routed by.
ACCEPTED = "_accepted"
ROUTED = "_routed"
RECONCILED_MEASUREMENT = "_reconciled_measurement"
FRESHLY_MEASURED = "_freshly_measured"
PARK_AWAITING_HUMAN = "_park_awaiting_human"
WRITE_PINNED_STATE = "write_pinned_state"
POST_ISSUE_COMMENT = "_post_issue_comment"
ORCHESTRATOR_IDS = "orchestrator_comment_ids"

ISSUE_NUMBER = 612
THRESHOLD = 4000
OVERSIZED_ADDITIONS = 9123

# A reading the ceiling lets through, which is a candidate no operator has to
# authorize: measured afresh, it is not the change anybody was asked about.
SMALL_ADDITIONS = 12
PR_NUMBER = 41
WORKTREE = Path("/tmp/orchestrator-test-late-consent")

# A directory the recovery's existence probe finds, standing in for the
# checkout the committed candidate lives in.
TEMP_WORKTREE_ROOT = Path("/tmp")

# The two seams a case asks whether a whole tick spent: a developer run, and
# the push that would have published the candidate.
RUN_AGENT = "run_agent"
PUSH_BRANCH = "_push_branch"
WORKTREE_PATH = "_worktree_path"

# A commit that types as one and that no record on this issue names: the id an
# operator copies out of a notice about work a resumed developer moved past.
STRANGER_SHA = "d" * SHA_LENGTH

# How much of a whole object id a `git log` line shows, which is what somebody
# types when they abbreviate. Nothing in this domain writes one, so it is the
# mismatch it is rather than a prefix to compare.
ABBREVIATED = 7

TRUSTED_AUTHOR = "alice"
OUTSIDER = "mallory"
ALLOWLIST_CONFIG = "ALLOWED_ISSUE_AUTHORS"

# Where the thread had been read to when the park went up, so every reply a
# case seeds is one the reading is entitled to find.
PRIOR_ACTION_COMMENT_ID = 900

_COMMAND = "/orchestrator authorize-oversized {commit}"

AUTHORIZE = _COMMAND.format(commit=MEASURED_CANDIDATE_SHA)
AUTHORIZE_ANOTHER = _COMMAND.format(commit=STRANGER_SHA)
AUTHORIZE_ABBREVIATED = _COMMAND.format(
    commit=MEASURED_CANDIDATE_SHA[:ABBREVIATED],
)
GUIDANCE = "make it smaller, please"

# The one reply the measurement park is ended by: take the reading you could
# not take again. It carries no words for a developer, which is what makes it
# the retry rather than guidance -- and what has every road but that park's
# own read it as a command carrying no answer.
CONTINUE = "/orchestrator continue"

# The receipt the park's own notice is stamped with, which is what a tick that
# died before saying it leaves on the record and what the sentence itself
# carries once it lands.
PARK_RECEIPT = _consent._RECEIPTS["parked"].format(
    issue=ISSUE_NUMBER, scope=MEASURED_CANDIDATE_SHA,
)

# A record too big for its own escaping, which is the rendering that puts
# every receipt it holds into the pinned comment's body VERBATIM: the escape
# that hides a comment terminator is dropped wherever keeping it would push
# the write past GitHub's ceiling, and losing the write is the worse trade.
# Sized through a park's own message, which is free text a stage really does
# put there.
AT_THE_LIMIT = MappingProxyType({
    "late_park_notice": {
        "reason": "late_question", "message": "x" * MAX_PINNED_BODY,
    },
})


def refusal_receipt(comment_id: int) -> str:
    """The receipt the answer to one reply is stamped with."""
    return _consent._RECEIPTS["refused"].format(
        issue=ISSUE_NUMBER, scope=comment_id,
    )

# A reply that merely QUOTES the pinned comment's marker -- an operator
# pasting a payload back to ask about it, or writing under one they copied.
# The record is named by its id, so this is somebody's word like any other.
QUOTES_THE_RECORD = f"hold off -- this issue says {PINNED_STATE_MARKER} ... -->"

KEY_OVERRIDE_CANDIDATE_SHA = "late_override_candidate_sha"
KEY_OVERRIDE_BASE_SHA = "late_override_base_sha"
KEY_OVERRIDE_ADDITIONS = "late_override_additions"
KEY_OVERRIDE_THRESHOLD = "late_override_threshold"
KEY_OVERRIDE_COMMENT_ID = "late_override_comment_id"

KEY_EXEMPT_SHA = "late_exempt_sha"


def measured() -> LateGeneration:
    """The reading the tick that acts took, which the terms are written from."""
    return LateGeneration(
        cycle_id=1,
        generation=1,
        root_issue=ISSUE_NUMBER,
        current_issue=ISSUE_NUMBER,
        lineage_depth=0,
        candidate_sha=MEASURED_CANDIDATE_SHA,
        base_sha=MEASURED_BASE_SHA,
        threshold=THRESHOLD,
        additions=OVERSIZED_ADDITIONS,
        phase=LatePhase.MEASURING,
    )


# A gate call entered PAST a publication: the stage it takes the issue out
# of, the pull request the work already has, and the head that pull request
# stands on. What it changes here is the notice, since guidance reaches a
# developer only where the ordinary resume is still in front of the issue.
PUBLISHED_ENTRY = _records._PublicationEntry(
    stage=LABEL_IMPLEMENTING,
    pr_number=PR_NUMBER,
    published_sha=MEASURED_BASE_SHA,
)


def measured_pair(**overrides) -> dict:
    """The pair the freeze wrote, which is all a standing park carries.

    Deliberately without the count, which is what the freeze itself persists:
    a generation answering "oversized" is what this workflow means by an
    adjudication in flight, so a park that recorded one would be relabelled
    out from under itself before anything could answer it -- and a recorded
    number is what the gate acts on instead of taking the reading again. What
    the announce-once guard compares is the COMMIT.
    """
    recorded = PinnedState(data={})
    _late_state.write_late_generation(
        recorded, replace(measured(), additions=None, **overrides),
    )
    return recorded.data


@dataclass(frozen=True)
class GateDecision:
    """What one gate call answered, and whether it needed a reading to.

    Both facts, because the roads past the gate reach the same two verdicts:
    a commit two records vouch for publishes without a count, and one an
    exemption alone names publishes only once the count says the ceiling lets
    it through, so a case asking only what came back could not tell them
    apart.
    """

    verdict: object
    measured: bool


# What the hermetic world's reading of the frozen pair answers with, and the
# refusal a host that never held the content between them gives instead.
CONTRIBUTED = ContributionFingerprint(
    base_sha=MEASURED_BASE_SHA,
    candidate_sha=MEASURED_CANDIDATE_SHA,
    digest=CONTRIBUTION_DIGEST,
)
UNREADABLE = ContributionFingerprint(failure=FingerprintFailure.CONTENT_ABSENT)

# What a fresh count answers with on each side of the ceiling, and what a host
# that could not read the diff between the frozen pair answers instead.
OVERSIZED = AdditionMeasurement(additions=OVERSIZED_ADDITIONS)
FITS = AdditionMeasurement(additions=SMALL_ADDITIONS)
UNCOUNTABLE = AdditionMeasurement(failure=MeasurementFailure.DIFF_FAILED)
