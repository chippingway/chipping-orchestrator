# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The issue of `review_verdict_test_support`, whose persisted approval is handed to its proof and the approval arc.

A case hands a waiting approval to `unverified_approvals` directly, the way
the disposition service does (`disposed_verdict_test_support` goes through
that service instead): an approval of the standing subject waits on the
pinned comment (`waits`), relying on the claim a case names, and one tick
builds the gate over the round's checkout and hands the run that returned it
to `unverified_approvals.approves`, which proves the claim the waiting record
names, and whose answer the case keeps (`answered`). The run is rebuilt ahead
of the tick, off a reading nothing writes, so the requests that rebuild takes
are none of the tick's own.

Beside that world: the claim a settled transaction is named by, a verify gate
during which another road does its work (`DuringTheGate`), the two things the
pull request can do to the evidence's artifact that no pinned record shows --
delete it, or stop answering for the thread it is on -- and what the comment
reads back as -- the park and the verdict waiting.
"""
from __future__ import annotations

from unittest.mock import patch

from orchestrator.git.verification.models import VerifyResult
from orchestrator.workflow.engine import verification_settlement_state as _settlement
from orchestrator.workflow.stages.implementing import late_records as _late_records
from orchestrator.workflow.stages.validating import (
    models as _models,
    review_verdicts as _verdicts,
    unverified_approvals as _unverified,
)
from tests.workflow.repo_values import _FAKE_WT, _TEST_SPEC
from tests.workflow.stages.validating import (
    review_verdict_readings as _read,
    review_verdict_test_support as _world,
)

APPROVAL = "LGTM\n\nVERDICT: APPROVED"

PARK_EVENT = "park_awaiting_human"

# What the approval comment and the two park notices an approval's arc can
# post say about themselves.
APPROVAL_NOTICE = "review approved"

VERIFY_NOTICE = "local verification failed"

SQUASH_FAILED_NOTICE = "squash-on-approval failed"

# The pinned ledger of the comments the orchestrator posted.
LEDGER = "orchestrator_comment_ids"


def claim_on(settled, **flags) -> _verdicts.EvidenceClaim:
    """A published claim naming exactly the transaction `settled`, passing and covering unless `flags` say not."""
    return _verdicts.EvidenceClaim(
        use=_verdicts.EvidenceUse.PUBLISHED,
        receipt=settled.receipt,
        revision=settled.revision,
        digest=settled.content_revision,
        passed=flags.get("passed", True),
        covers=flags.get("covers", True),
    )


def behind_the_proof(case, road) -> _world.AnotherRoadBehind:
    """The approval's last read of its artifact, behind the proof's own, with `road` done by another road behind it."""
    return _world.AnotherRoadBehind(case, "reread_verification_artifact", bool, road, 2)


def deletes_the_artifact(case) -> None:
    """A human deleting the current evidence's artifact from `case`'s pull request."""
    current = _settlement.read_current_evidence(case.github.read_pinned_state(case.issue))
    thread = case.pull_request.issue_comments
    artifact = next(said for said in thread if said.id == current.comment_id)
    thread.remove(artifact)


def stops_reading_the_artifact(case) -> None:
    """The thread `case`'s evidence artifact is on stops answering its readers for the rest of the case."""
    case.enterContext(patch.object(case.github, "_verification_thread", side_effect=OSError))


def saying(phrase: str):
    """Whether a post's body says `phrase`, for a request another road lands behind."""
    return lambda body: phrase in body


# A verify gate's run of the suite that failed.
FAILED_GATE = VerifyResult(status="failed", command=_world.SUITE, exit_code=1, output="1 failed")

PASSED_GATE = VerifyResult(status="ok")


class DuringTheGate:
    """A verify gate answering `verified`, while `road` does another road's work on the case -- or nobody's."""

    def __init__(self, case, road, verified: VerifyResult) -> None:
        self._case = case
        self._road = road
        self._verified = verified

    def __call__(self, *_ran) -> VerifyResult:
        if self._road is not None:
            self._road(self._case)
        return self._verified


class ApprovedVerdictWorld(_world.ReviewVerdictWorld):
    """The same issue, with an approval of its standing subject waiting to be proved and acted on."""

    def setUp(self) -> None:
        super().setUp()
        # The run the waiting approval was returned from, and what the last
        # tick's proof answered.
        self.run: _models._ReviewerRun | None = None
        self.answered: str | None = None

    def waits(self, claim: _verdicts.EvidenceClaim | None) -> None:
        """Leave an approval of the standing subject waiting, relying on `claim`, as the tick that persisted it."""
        self.run = _world.returned_run(self, self.github.read_pinned_state(self.issue), APPROVAL)
        state = self.github.read_pinned_state(self.issue)
        subject = self.run.subject.recorded()
        returned = _verdicts.ReturnedVerdict(self.run.round_n, _verdicts.APPROVED, subject, "", claim)
        state.set(_verdicts.RETURNED_VERDICT, returned.recorded())
        self.github.write_pinned_state(self.issue, state)

    def waits_on_settled_evidence(self) -> None:
        """Leave an approval waiting that relies on one passing run of the suite, settled as the current evidence."""
        self.waits(claim_on(_read.settles_evidence(self)))

    def approves(self, **run_options) -> dict:
        """One tick handing the waiting approval to its proof, and the arc where that proves it.

        The round's checkout stands on the head the reviewer was handed,
        unless `run_options` seed it elsewhere.
        """
        run_options.setdefault("head_shas", (_world.HEAD,))
        return self._run(self._approves, run_agent=[], **run_options)

    def waiting(self) -> str | None:
        """Which verdict the pinned comment has waiting, or None."""
        return (self.pinned().get(_world.RETURNED_VERDICT) or {}).get("verdict")

    def parked(self) -> tuple:
        """The park the pinned comment records and whether it waits, the verdict waiting, and every park reported."""
        pinned = self.pinned()
        flags = (pinned.get("park_reason"), bool(pinned.get("awaiting_human")))
        events = self.github.recorded_events
        reasons = [event.get("reason") for event in events if event["event"] == PARK_EVENT]
        return (flags, self.waiting(), reasons)

    def _approves(self) -> None:
        state = self.github.read_pinned_state(self.issue)
        gate = _late_records._gate(self.github, _TEST_SPEC, self.issue, state, _FAKE_WT)
        self.answered = _unverified.approves(gate, self.run)
