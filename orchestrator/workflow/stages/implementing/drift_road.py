# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a requirements-drift resume freezes before its launch, for the capture of the report it returns.

A requirements edit resumes the locked developer session on whichever stage
reads it -- `implementing`, `validating`, `in_review`, and `resolving_conflict`
-- and so do the replies that remain that resume's continuation: the reply
`validating` reads as the rest of a drift park or of a report it owes, and the
reply a conflict park owing a report is answered with. Each of those runs is
handed one frozen reading of the thread (`drift_delivery`), whose record the
run's report is stamped with and whose settlement is the only thing that moves
the requirements baseline. A live hold, a lost write, or a restart that
discards the return would otherwise leave the edit to be resumed again, the
paid report lost with it. So each launch carries this road (`road`), and the
shared coordinator captures a return that finished on its report
(`completion_roads.CompletionRoad.captures`) for the dispatcher's recovery to
finish with no developer run (`captured_drift`, and each stage's owner beside
it).

What the road freezes is that one reading, as the run's own tick settles it
(`DriftReading`): the requirements revision the run's report is stamped with
-- the one its prompt fingerprints, which the coordinator's own prompt digest
was built over, the re-grounding preamble a rotated, retired, or poisoned
session's fresh spawn is given included, since every caller hands that spawn
the same frozen text -- and the watermarks the road advances once the run is
back: the reading's own settlement, the commands a retry consumed ahead of the
run, or both, as that road writes them. Those pairs are the road's own to
settle, as its tick settles them, so the delivered report the capture becomes
carries none of them, as the recording its own tick makes carries none
(`completion_routes.RouteContract.settles_input`): a pair riding that report
would be carried onto every later report superseding it, and a requirements
baseline settled late would move the issue back onto requirements it has since
left. No round settlement is frozen either: each road's own disposition
counts, resets, or hands on its round from the records below, as it always
has, and a round frozen onto the report would be spent by a report with no
code in it, which spends none.

The handoff is frozen over the records each road's accounting is read off and
the reason it was allowed to resume (`FROZEN`), as the comment spells them at
the launch: the pull request, the code-publication receipt -- whose head a
resume over a commit an earlier run left unpushed is still admitted on
(`completion_frozen.published_over`) -- the settled report pair a pending
transaction's reconciliation would move, the review and conflict rounds, the
report debt, the fresh budget an `in_review` hand-back reset, and the drift
`validating` holds open across a park. A body edit read on `validating`
freezes the round that stage stood down for beside them (`STOOD_DOWN`), and a
reply answering its drift park does not, which is what tells the two apart:
each lands on its own round (`validating/captured_drift`). None of those
records moves while a capture holds the stage, so one moved since is another
road's or a human's, and the run no longer the answer the issue is owed. The
park the resume answers is not frozen, as on the fix rounds: a spent run
ledger's park recorded while the capture waits is waited through, never a
proof it is stale.

The checkout is the one the run ran in, at the head it began on
(`launched_in`) -- save on `resolving_conflict`, whose publication is leased
against a head its caller proved, which that road freezes as the head it began
on: the head a body edit's resume started from in sync with its remote, or the
pull request's own head a reply's run was admitted over, so the capture is
admitted only while the pull request still stands there or on the commit
reported on, and is published against that exact lease.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from orchestrator.config import models as _config_models
from orchestrator.git.verification import probes as _probes
from orchestrator.git.worktrees import naming as _naming
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    completion_frozen as _frozen,
    completion_records as _records,
    completion_routes as _routes,
    report_delivery as _report_delivery,
    report_records as _report_records,
)
from orchestrator.workflow.engine.prompt_delivery import PromptDeliverySnapshot
from orchestrator.workflow.stages.implementing.completion_roads import CompletionRoad, RoadCheckout
from orchestrator.workflow.state import WorkflowLabel

# The records every drift road is decided on, frozen as the comment spells
# them at the launch: the pull request and the code-publication receipt
# whole, the settled report pair, the review and conflict rounds, and the
# claims its outcome settles beside its report.
FROZEN = (
    "pr_number",
    _frozen.PUBLISHED_COMMIT,
    _frozen.PUBLISHED_LEASE,
    _frozen.PUBLISHED_PULL_REQUEST,
    _report_records.CURRENT_REPORT,
    _report_records.REPORT_HANDOFF,
    "review_round",
    "conflict_round",
    _report_delivery.OWED_REPORT,
    _report_delivery.UNREPORTED_WORK,
    _report_delivery.OWED_ROUND_RESET,
    "requirements_drift_open",
)

# The round `validating` stood down for, as that stage spells it, and what a
# body edit read there freezes: every drift road's records and that one.
STOOD_DOWN_FOR = "validating_reviewer_owes_a_round"

STOOD_DOWN = (*FROZEN, STOOD_DOWN_FOR)


@dataclass(frozen=True)
class DriftReading:
    """What one drift resume was handed: its report's requirements revision, and the watermarks its road advances."""

    revision: str
    watermarks: tuple = ()

    @classmethod
    def settled_by(cls, delivery: PromptDeliverySnapshot, state: PinnedState) -> DriftReading:
        """The frozen reading `delivery` is the record of, settled as its own pairs advance the comment `state` is."""
        return cls(delivery.requirements_revision or "", delivery.consumed_pairs(state))


def launched_in(spec: _config_models.RepoSpec, number: int, state: PinnedState, worktree: Path) -> RoadCheckout:
    """The checkout a resume is launched in: `worktree` on the branch the record pins, at its head as it is launched."""
    return RoadCheckout(worktree, _naming._resolve_branch_name(state, spec, number), _probes._head_sha(worktree))


def road(
    label: WorkflowLabel,
    state: PinnedState,
    reading: DriftReading,
    checkout: RoadCheckout,
    fields: tuple = FROZEN,
) -> CompletionRoad:
    """The drift road a resume on `label`, handed `reading`, is launched on in `checkout`, frozen over `fields`."""
    return CompletionRoad(_records.CompletionHandoff(
        route=_routes.CompletionRoute.REQUIREMENTS_DRIFT,
        origin=label,
        requirements_revision=reading.revision,
        watermarks=reading.watermarks,
        frozen=_frozen.frozen_over_the_comment(state, fields),
    ), checkout)
