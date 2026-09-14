# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The late generation the domain's tests read state and events off.

One frozen candidate described once: the state round trip writes it, the
record builder correlates against it, and the dual emission carries it to both
sinks, so a field added to the record is exercised by all three without three
copies of the same fixture drifting apart. `family_cases` is the same idea for
the event families whose record reads over that generation -- one valid event
per family, built where the family schema is spelled. The transfer sits beside
them in `transfer_event` rather than among them, because its record is only
ever written past a publication and a generation entered before one could not
carry it; `every_family` is the two together, so a walk over the vocabulary
cannot fall behind a family the schema gained.
"""
from __future__ import annotations

from types import MappingProxyType

from orchestrator.git.measurement.models import MeasurementFailure
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.late_split import events as _events, state as _late_state
from orchestrator.workflow.late_split.identity import RESOURCE_FINGERPRINT_LENGTH
from orchestrator.workflow.late_split.models import (
    LateGeneration,
    LatePhase,
    LateResource,
    LateResourceKind,
    LateResourceState,
)
from orchestrator.workflow.state import WorkflowLabel

REPO = "chippingway/orchestrator"
# Where the analytics half of a dual emission lands, patched by every test
# that has to see what a sink was handed.
ANALYTICS_APPEND = (
    "orchestrator.observability.analytics.recording.events.append_record"
)
CYCLE_ID = 2
GENERATION_NUMBER = 1
ROOT_ISSUE = 7
CURRENT_ISSUE = 9
LINEAGE_DEPTH = 1
THRESHOLD = 4000
ADDITIONS = 9123
# What a reading that did not happen leaves on the record: the misses this
# frozen pair has lost, and the step the last one stopped at.
MEASUREMENT_MISS_COUNT = 2
MEASUREMENT_FAILURE = MeasurementFailure.DIFF_UNREADABLE
# What one refused reading hands the record beside the family: the step the
# git layer stopped at, and the line that step wrote once the transport had
# scrubbed its own stderr.
MEASUREMENT_STEP = MeasurementFailure.BASE_ABSENT
FAILURE_DETAIL = "fatal: could not read Username for 'https://github.com'"
SHA_LENGTH = 40
DIGEST_LENGTH = 64
CANDIDATE_SHA = "a" * SHA_LENGTH
BASE_SHA = "b" * SHA_LENGTH
TITLE_BODY_HASH = "c" * DIGEST_LENGTH
COMMENT_HASH = "d" * DIGEST_LENGTH
COMMENT_WATERMARK_ID = 555
PLAN_PR_NUMBER = 12
PLAN_PR_HEAD = "f" * SHA_LENGTH
PLAN_PR_BODY = "the plan PR body held while adjudication runs"
# What a post-publication entry froze: the stage the gate took the issue out
# of, the pull request the work already had, and the head it was left on.
SOURCE_STAGE = WorkflowLabel.IN_REVIEW
PUBLISHED_PR_NUMBER = 34
PUBLISHED_SHA = "e" * SHA_LENGTH
# The whole of what a generation entered on an existing pull request carries,
# described once: the round trip writes it, the record projects it onto the
# closed pair, and the key tells it apart from an initial publication.
ENTERED_ON_PUBLICATION = MappingProxyType({
    "post_publication": True,
    "source_stage": SOURCE_STAGE,
    "published_pr_number": PUBLISHED_PR_NUMBER,
    "published_sha": PUBLISHED_SHA,
})
# The pair a transfer moved a verdict OFF. The pair it moved onto is the
# generation's own frozen pair, which is why only these two travel on the
# event.
TRANSFERRED_FROM_SHA = "1" * SHA_LENGTH
TRANSFERRED_FROM_BASE_SHA = "2" * SHA_LENGTH

SCOPE = "the declared slice this generation owns"
SNAPSHOT_REF = "refs/orchestrator/snapshot/9"
CANCELLED_AT = "2026-08-21T10:00:00+00:00"
DECOMPOSING = "workflow:decomposing"

CATEGORY = _events.LateVerdictCategory
CHILD_COUNT = 4
OTHER_CHILD_COUNT = 7
RESOURCE_PRINT_LENGTH = RESOURCE_FINGERPRINT_LENGTH

SNAPSHOT = LateResource(
    kind=LateResourceKind.SNAPSHOT_REF,
    target=SNAPSHOT_REF,
    resource_state=LateResourceState.RETAINED,
)

# The same snapshot once its consumers let it go: one resource, a second
# outcome.
RECLAIMED_SNAPSHOT = LateResource(
    kind=LateResourceKind.SNAPSHOT_REF,
    target=SNAPSHOT_REF,
    resource_state=LateResourceState.RECONCILED,
)

# Two obligations of one kind, reconciled the same way: what tells them apart
# in a record is the resource fingerprint and nothing else.
FIRST_CHILD = LateResource(
    kind=LateResourceKind.CHILD,
    target="21",
    resource_state=LateResourceState.RECONCILED,
)

SECOND_CHILD = LateResource(
    kind=LateResourceKind.CHILD,
    target="22",
    resource_state=LateResourceState.RECONCILED,
)


def read_state(state: PinnedState) -> LateGeneration:
    """The late generation one pinned comment records."""
    return _late_state.read_late_generation(state)


def rewritten_state(state: PinnedState) -> PinnedState:
    """One read-and-write-back pass, the shape a handler's tick takes."""
    _late_state.write_late_generation(state, read_state(state))
    return state


def transferred_generation(**fields) -> LateGeneration:
    """The generation one transfer record is correlated by.

    Entered on a publication by construction: a verdict moves only onto a
    commit a pull request the remote already carries has been pushed to, so
    the same record over a pre-publication generation would describe a move
    nothing could be attributed to.
    """
    return measured_generation(**{**ENTERED_ON_PUBLICATION, **fields})


def measured_generation(**fields) -> LateGeneration:
    """A frozen, measured generation partway through adjudication."""
    measured = {
        "cycle_id": CYCLE_ID,
        "generation": GENERATION_NUMBER,
        "root_issue": ROOT_ISSUE,
        "current_issue": CURRENT_ISSUE,
        "lineage_depth": LINEAGE_DEPTH,
        "candidate_sha": CANDIDATE_SHA,
        "base_sha": BASE_SHA,
        "threshold": THRESHOLD,
        "additions": ADDITIONS,
        "phase": LatePhase.ADJUDICATING,
    }
    return LateGeneration(**{**measured, **fields})


def full_generation() -> LateGeneration:
    """The same generation with every remaining field set as well.

    Every late field carries a value here, so a round trip over this record
    covers the whole pinned contract rather than the fields a happy path
    happens to write.
    """
    return measured_generation(
        phase=LatePhase.SNAPSHOTTING,
        scope=SCOPE,
        title_body_hash=TITLE_BODY_HASH,
        comment_hash=COMMENT_HASH,
        comment_watermark_id=COMMENT_WATERMARK_ID,
        plan_pr_number=PLAN_PR_NUMBER,
        plan_pr_head=PLAN_PR_HEAD,
        plan_pr_body=PLAN_PR_BODY,
        measurement_miss_count=MEASUREMENT_MISS_COUNT,
        measurement_failure=MEASUREMENT_FAILURE,
        **ENTERED_ON_PUBLICATION,
        resources=(SNAPSHOT,),
        consumers=(21, 22),
        owner_check_pending=True,
        cancelled=True,
        cancelled_at=CANCELLED_AT,
        cancelled_phase=LatePhase.SPLITTING,
        restart_pending=True,
        restart_target=DECOMPOSING,
        restart_cycle_id=CYCLE_ID + 1,
        restart_predecessor=CYCLE_ID,
    )
