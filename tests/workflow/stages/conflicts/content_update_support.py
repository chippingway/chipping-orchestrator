# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The record a conflict tick's own size reading leaves half-finished.

The freeze is durable and the count that follows it is not, so the crash this
fixture stands for lands between them: a generation naming both commits, the
publication it was entered on, and no number at all. Every case about a retry,
or about a publication that moved while the pair was outstanding, starts from
exactly that comment.

It is the one door those cases reach this stage's fixtures through, so the
scenario mixin and the heads a publication can be standing on come back out of
it beside the record.

Written through the domain's own writer rather than spelled as a dict, so what
a test seeds is what the freeze would really have left -- the marker included,
which is what tells an entry taken past publication from one taken before it.
"""
from __future__ import annotations

from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.late_split import state as _late_state
from orchestrator.workflow.late_split.models import LateGeneration
from orchestrator.workflow.late_split.phases import LatePhase
from tests.workflow.other_labels import LABEL_RESOLVING_CONFLICT
from tests.workflow.repo_values import (
    MEASURED_BASE_SHA,
    MEASURED_CANDIDATE_SHA,
)
from tests.workflow.stages.conflicts.conflicts_test_support import (
    CONFLICT_PR_HEAD_SHA,
    MOVED_PR_HEAD_SHA as MOVED_PR_HEAD_SHA,
    RESOLVED_HEAD_SHA as RESOLVED_HEAD_SHA,
    _ResolvingConflictMixin as _ResolvingConflictMixin,
)

CONFLICT_ISSUE = 200
CONFLICT_PR = 800

# The ceiling the generation was frozen under. It rides the record rather than
# the setting, so a threshold retuned between the freeze and the reading that
# answers it cannot re-judge a candidate mid-flight.
GATE_CEILING = 5


def recorded_generation(**overrides) -> dict:
    """The pinned fields a conflict tick's frozen pair is retried from."""
    recorded = PinnedState(data={})
    _late_state.write_late_generation(
        recorded,
        LateGeneration(**{
            "cycle_id": 1,
            "generation": 1,
            "root_issue": CONFLICT_ISSUE,
            "current_issue": CONFLICT_ISSUE,
            "lineage_depth": 0,
            "candidate_sha": MEASURED_CANDIDATE_SHA,
            "base_sha": MEASURED_BASE_SHA,
            "threshold": GATE_CEILING,
            "phase": LatePhase.MEASURING,
            **overrides,
        }).with_publication(
            stage=LABEL_RESOLVING_CONFLICT,
            pr_number=CONFLICT_PR,
            published_sha=CONFLICT_PR_HEAD_SHA,
        ),
    )
    return recorded.data
