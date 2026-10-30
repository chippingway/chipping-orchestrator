# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What one captured developer completion is, before and after the report transaction takes it over.

A developer run that finished on a report hands the orchestrator work nothing
durable describes yet: the report, the session it returned, and the inputs the
run was handed live in the memory of a call a live hold or a lost tick can end.
A capture is that return recorded whole, on the issue's pinned comment
(`developer_completion`), so a later tick can hand it to the existing report
delivery instead of asking an agent to write it again.

It is immutable and bounded. A PENDING capture (`CompletionCapture`) holds the
invocation it came from -- repository, issue, the pinned comment and workflow
cycle its charge was taken on, and the charge itself -- the road the run came
down and the handoff the caller froze before the launch, what actually ran,
where it ran, the report outcome with its complete READY text or VERIFIED
reference, and whether the run's usage was settled as it returned. It holds no
raw output, no prompt, and nothing else a stage staged: the prompt is its
digest, the delivered input the bounded watermark pairs a settlement applies,
and the frozen handoff a digest per pinned record it was decided on.

A resolved one (`ResolvedCapture`) keeps no report. HANDED_OFF is a capture
whose report the delivery transaction now owns, written in the very commit
that records it: it keeps the delivery's receipt and revision and the branch
and source commit the report is about, so a binding of that delivery is held
to the commit the run reported on. RETIRED is one a guarded decision ended --
handed off and finished with, or found no longer to apply -- and keeps only
which invocation it was and why. Both keep the invocation, so a later capture
of it, or of an earlier one, is refused rather than taken for fresh work.

Nothing here is read or written; `completion_spelling` is the wire shape and
`completion_state` the reader of a state.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from orchestrator.agents.models import AgentInvocation
from orchestrator.workflow.engine import completion_routes as _routes
from orchestrator.workflow.state import WorkflowLabel

# The one pinned field a capture lives in, whichever stage it is at.
DEVELOPER_COMPLETION = "developer_completion"


class CaptureStage(StrEnum):
    """Where one capture is in its bounded lifecycle."""

    # Captured, and its report owned by nothing else yet.
    PENDING = "pending"
    # Its report recorded as the issue's delivered report, in the same commit.
    HANDED_OFF = "handed_off"
    # Ended by a guarded decision, its report kept nowhere by this record.
    RETIRED = "retired"


class CaptureAccounting(StrEnum):
    """Whether the captured run's usage was settled as it returned (`usage_checkpoint`)."""

    # Accounted, or already covered by the issue's receipts.
    SETTLED = "settled"
    # No usage was parsed, so the run owed nothing.
    NOTHING_OWED = "nothing_owed"
    # The checkpoint was refused or never confirmed: only its receipt says.
    UNRESOLVED = "unresolved"


class RetirementReason(StrEnum):
    """Why a capture was retired."""

    # A guarded decision found it no longer applies.
    INVALIDATED = "invalidated"
    # The transaction it was handed off to is done with it.
    SETTLED = "settled"


@dataclass(frozen=True)
class CompletionHandoff:
    """What the road froze before the launch: its route, the label it reports under, and what it handed the run.

    `requirements_revision` is the issue content the run was given.
    `watermarks` are the input the run's prompt delivered and `spends` the
    round and bookmarks the road closes, each `((field, value), ...)` bounded
    by the vocabulary the report records hold them to, applied only by the
    settlement of the report they ride. `frozen` is `((field, digest), ...)`:
    each pinned record the road's handoff was decided on, as the digest of its
    spelling at the launch, so a handoff another road moved since is told
    apart from the one the run answered.
    """

    route: _routes.CompletionRoute
    origin: WorkflowLabel
    requirements_revision: str
    watermarks: tuple = ()
    spends: tuple = ()
    frozen: tuple = ()


@dataclass(frozen=True)
class CompletionRun:
    """What actually ran, and where.

    `command` is the full command the attempt ran under -- its backend and
    arguments, as the pinned command spells them -- and `prompt_revision` the
    SHA-256 of the prompt it was handed. `worktree` and `branch` are the
    checkout, `before_sha` its head when the run started and `source_sha` the
    head the report is about.
    """

    command: str
    prompt_revision: str
    worktree: str
    branch: str
    before_sha: str
    source_sha: str


@dataclass(frozen=True)
class CompletionCapture:
    """One PENDING capture: an eligible return recorded whole.

    `outcome` is the report outcome as the outcome owner read it, a READY
    report's complete text or a VERIFIED reference. `session_id` is the
    session the run returned, None where its CLI named none.
    """

    invocation: AgentInvocation
    handoff: CompletionHandoff
    run: CompletionRun
    outcome: _routes.CapturedOutcome
    accounting: CaptureAccounting
    session_id: str | None = None

    @property
    def stage(self) -> CaptureStage:
        """A capture holding its report is PENDING; only a resolved one is anything else."""
        return CaptureStage.PENDING


@dataclass(frozen=True)
class ResolvedCapture:
    """A capture past PENDING, holding no report.

    HANDED_OFF carries the delivery that owns the report -- its `receipt` and
    `report_revision` -- and the `branch` and `source_sha` the report is
    about; RETIRED carries its `reason` alone.
    """

    invocation: AgentInvocation
    stage: CaptureStage
    receipt: str = ""
    report_revision: int = 0
    branch: str = ""
    source_sha: str = ""
    reason: RetirementReason | None = None
