# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Fresh transfer and recorded-authorization recovery setup and assertions."""
from __future__ import annotations

from types import MappingProxyType

from orchestrator.git.measurement.models import (
    FingerprintFailure,
    FrozenCommit,
    MeasurementFailure,
)
from orchestrator.git.verification.status import _WorktreeStatus
from orchestrator.workflow.late_split import (
    exemption_reading as _exemption_reading,
    rewrite_fields as _rewrite_fields,
    rewrite_reading as _rewrite_reading,
    rewrite_values as _rewrite_values,
    rewrites as _rewrites,
)
from orchestrator.workflow.stages.implementing import (
    late_gate_permission as _late_gate_permission,
    late_transfer as _transfer,
)
from orchestrator.workflow.state import WorkflowLabel
from tests.workflow.observation_support import ObservedCloseCase
from tests.workflow.stages.implementing import (
    late_transfer_adjudication as _transfer_adjudication,
    late_transfer_payloads as _transfer_payloads,
    late_transfer_readings as _transfer_readings,
    late_transfer_test_support as _support,
)

# Every way a group already on the comment claims the commit this issue
# exempts and cannot show what it claims. A value of None is the field being
# absent -- a crash between two halves of one write -- and anything else is a
# value nothing here would have written.
_STANDING_CLAIMS = MappingProxyType({
    "a partial one": {_rewrite_fields.LATE_REWRITE_FROM_BASE_SHA: None},
    "one that names no rewritten commit": {
        _rewrite_fields.LATE_REWRITE_TO_SHA: None,
    },
    "one at a phase this build does not write": {
        _rewrite_fields.LATE_REWRITE_PHASE: "reverted",
    },
    "one for a kind this build does not authorize": {
        _rewrite_fields.LATE_REWRITE_KIND: "amend",
    },
    "one for a kind the recorded stage does not make": {
        _rewrite_fields.LATE_REWRITE_KIND: str(_rewrite_values.LateRewriteKind.CONFLICT_REBASE),
    },
    "one with a hand-edited accepted commit": {
        _rewrite_fields.LATE_REWRITE_FROM_SHA: _transfer_payloads.ACCEPTED_SHA[:7],
    },
})

_DIRTY_PATH = "orchestrator/x.py"

# Every way the issue this transfer would be granted on is not the one the
# rewrite was entered on, offered through the labels a fresh fetch reads back.
_MOVED_ISSUES = MappingProxyType({
    "one an operator paused": (str(_transfer_payloads.SOURCE_STAGE), "paused"),
    "one an operator sent back to the backlog": (
        str(_transfer_payloads.SOURCE_STAGE), "backlog",
    ),
    "one a relabel moved to another stage": (str(WorkflowLabel.FIXING),),
    "one carrying no workflow label at all": (),
})

# A commit the checkout resolved and this host cannot peel, which is what work
# made on another host reads back as.
_UNPEELABLE_HEAD = FrozenCommit(
    sha=_transfer_payloads.REWRITTEN_SHA, failure=MeasurementFailure.CANDIDATE_ABSENT,
)

# Every way the evidence itself fails to describe a rewrite this build may
# authorize, offered through the record the squash hands in.
_UNUSABLE_EVIDENCE = MappingProxyType({
    "an unknown rewrite kind": {"kind": "amend"},
    "no rewrite kind at all": {"kind": None},
    "a kind the recorded stage does not make": {
        "kind": _rewrite_values.LateRewriteKind.CONFLICT_REBASE,
    },
    "an abbreviated accepted commit": {"from_sha": _transfer_payloads.ACCEPTED_SHA[:7]},
    "an accepted base that is prose": {"from_base_sha": "the merge base"},
    "a rewritten base that is not a commit": {"to_base_sha": 7},
    "a pull request that is not an identity": {"pr_number": 0},
    "a stage no publication is entered from": {
        "source_stage": WorkflowLabel.READY,
    },
    "a lease that is no object id": {"lease": _transfer_payloads.ACCEPTED_SHA[:8]},
})

# Every way the publication the rewrite claims is not the one this call froze.
_DISAGREEING_PUBLICATIONS = MappingProxyType({
    "an entry that refused": _support.entry(refusal="the tree is dirty"),
    "another pull request": _support.entry(pr_number=_transfer_payloads.PR_NUMBER + 1),
    "another stage": _support.entry(stage=WorkflowLabel.IN_REVIEW),
    "a remote that moved off the lease": _support.entry(
        published_sha=_transfer_payloads.STRANGER_SHA,
    ),
})

# A reading that established nothing names no paths -- which is what a clean
# tree names too, and why the probe answers on `readable` as well.
_UNPUBLISHABLE_TREES = MappingProxyType({
    "one carrying something loose": _WorktreeStatus(
        readable=True, paths=(_DIRTY_PATH,),
    ),
    "one nothing could read": _WorktreeStatus(readable=False),
})

_MOVED_CHECKOUTS = MappingProxyType({
    "a head that moved": _transfer_payloads.STRANGER_SHA,
    "a head this host cannot peel": _UNPEELABLE_HEAD,
})

# Every rewrite this build authorizes, with a stage that really makes it. The
# base a rewritten contribution is read over is proved the same way for each,
# so the rule is exercised over every road an exemption can travel rather than
# over the one the fixture happens to describe.
_SUPPORTED_REWRITES = MappingProxyType({
    _rewrite_values.LateRewriteKind.SQUASH: WorkflowLabel.VALIDATING,
    _rewrite_values.LateRewriteKind.CONFLICT_REBASE: WorkflowLabel.RESOLVING_CONFLICT,
    _rewrite_values.LateRewriteKind.AUTO_CLEAN_REBASE: WorkflowLabel.IN_REVIEW,
})

# Every way the two contributions are not one contribution.
_UNEQUAL_CONTRIBUTIONS = MappingProxyType({
    "an accepted pair whose content is gone": {
        _transfer_payloads.ACCEPTED_SHA: FingerprintFailure.CONTENT_ABSENT,
    },
    "a rewritten pair whose base is gone": {
        _transfer_payloads.REWRITTEN_SHA: FingerprintFailure.BASE_ABSENT,
    },
    "an accepted pair the record does not describe": {
        _transfer_payloads.ACCEPTED_SHA: _transfer_payloads.OTHER_DIGEST,
    },
    "a rewrite that picked something up": {_transfer_payloads.REWRITTEN_SHA: _transfer_payloads.OTHER_DIGEST},
})


class _TransferCase(ObservedCloseCase):
    """One squash of an accepted commit, asked for a permit."""

    def setUp(self) -> None:
        super().setUp()
        self._fresh_process()
        self.reading = _transfer_readings.readings(self)
        self._adjudicated()

    def _adjudicated(self, **overrides) -> None:
        """Seed the pinned comment a settled `single` verdict leaves."""
        seeded = _transfer_adjudication.adjudicated(**overrides)
        self.github = seeded.github
        self.issue = seeded.issue
        self.state = seeded.state

    def _carried(self, **gate_overrides) -> str:
        """What the gate is told about this rewrite once the permit is asked."""
        gate = _support.gate(
            self.github, self.issue, self.state, **gate_overrides,
        )
        return _transfer._carried_over(gate, _transfer_payloads.REWRITTEN_SHA)

    def _claimed(self, damage: dict) -> None:
        """Leave an authorization already standing on the comment.

        Written the way a real one is and then damaged the way a real one gets
        damaged: a group that never round-tripped would be a shape this domain
        cannot produce, and the reader would refuse it for the wrong reason.
        """
        _rewrites.record_rewrite_authorization(
            self.state, _support.rewrite(), _transfer_payloads.ACCEPTED_DIGEST,
        )
        for key, written in damage.items():
            if written is None:
                self.state.data.pop(key, None)
            else:
                self.state.data[key] = written
        self.github.write_pinned_state(self.issue, self.state)

    def _assert_untouched(self) -> None:
        """The exemption is where the adjudication left it, and alone."""
        self.assertTrue(_exemption_reading.is_exempt(self.state, _transfer_payloads.ACCEPTED_SHA))
        pinned = self.github.pinned_data(self.issue.number)
        self.assertEqual(pinned[_exemption_reading.LATE_EXEMPT_SHA], _transfer_payloads.ACCEPTED_SHA)
        self.assertFalse(_rewrite_reading.carries_rewrite_authorization(self.state))


class _RecoveryCase(_TransferCase):
    """The comment a crash between the grant and its push leaves behind."""

    def setUp(self) -> None:
        super().setUp()
        self._carried()
        self.recovery = _support.gate(
            self.github, self.issue, self.state, rewrite=None,
        )

    def _re_asked(self) -> str:
        """What the permit answers when the recovery asks it again."""
        return _transfer._carried_over(self.recovery, _transfer_payloads.REWRITTEN_SHA)

    def _bypasses(self, candidate: str = _transfer_payloads.REWRITTEN_SHA) -> bool:
        """Whether the approval alone would carry this commit past the gate."""
        return _late_gate_permission._approved_on_a_reading(self.recovery, candidate)

    def _recovered(self, damage: dict) -> None:
        """That comment, with one field of the permission moved or gone."""
        for key, written in damage.items():
            if written is None:
                self.state.data.pop(key, None)
            else:
                self.state.data[key] = written
        self.github.write_pinned_state(self.issue, self.state)
