# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A child a real split created, taken to the gate its own slice is measured by.

Two stages, because the claim spans them. An oversized candidate its operator
authorized to publish unsplit is one road; a split of that same candidate into
children is the other, and what a child then owes at publication is the whole
question. Nothing but the split's own transaction can answer what a child is
born carrying, so the child here is CREATED by it -- the manifest, the
snapshot, the child issue and the seed that attributes it -- rather than by a
fixture writing an ancestry onto an ordinary issue. A regression that copied
the parent's exemption or its authorization onto the child would be a change
to that seeding, and it is that seeding these run.

The parent is authorized on purpose. Its pinned comment carries both halves of
the bypass over the very commit the slice below is committed at, so a child
that inherited either would publish unmeasured -- and every case here is the
same tick either way, which is what makes the absence worth asserting.

Past the split the child is an ordinary implementing issue with a real
checkout under it, and the reading its gate takes is git's own: the seed the
tick runs under is the production count pointed at that worktree, so what
decides the publication is what `git diff base...candidate` reports rather
than a number a case chose.
"""

from __future__ import annotations

from unittest.mock import patch

from orchestrator import config
from orchestrator.git.measurement import additions as _additions
from orchestrator.git.measurement.models import FrozenCommit
from orchestrator.workflow.stages.decomposition import (
    late_models as _late_models,
    late_transaction as _late_transaction,
)
from tests.support import fakes as _fakes
from tests.workflow import fixtures as _fixtures
from tests.workflow.stages import slice_checkout as _slice
from tests.workflow.stages.decomposition import (
    late_seam_support as _seams,
    late_test_support as _late,
)
from tests.workflow.stages.implementing import late_gate_test_support as _gate

MAX_ADDED_LINES = "MAX_ADDED_LINES"

# The one slice the split below proposes. A single child, because what these
# cases ask is what ANY child carries rather than how a manifest is walked --
# which the split transaction's own tests own.
_SLICE = _late.proposed_slice(
    "the slice this child owns", "implement it end to end", _late.FIRST_ESTIMATE,
)


def _split_off_a_child(github, parent):
    """Run the real split over `parent`, and hand back the child it created.

    Entered the way the coordinator enters it -- a `split` a fresh owner read
    cleared -- rather than by paying for an adjudicator run to reach the same
    place. Everything past that point is production: the snapshot the slice is
    cut from, the child issue, and the one write that attributes it.
    """
    generation = _late.late_generation()
    decided = _late_models._LateAdjudicationRun(
        disposition=_late_models._LateDisposition.DECIDED,
        generation=generation,
        run=_late_models._LateRun(),
        guarded_split=_late_models._GuardedSplit(
            generation=generation, children=(_SLICE,),
        ),
    )
    context = _late_models._LateContext(
        gh=github,
        spec=_fixtures._TEST_SPEC,
        issue=parent,
        state=github.read_pinned_state(parent),
        generation=generation,
    )
    with _seams.snapshot_seams(_seams.SnapshotSeed()):
        _late_transaction._run_late_split(context, decided)
    return github.created_child_issues[0]


class _SliceGateCase(_gate._GateCase):
    """One implementing tick over the slice a split's child committed.

    `setUp` is the whole arrangement: an authorized parent, the split that
    turns it into a child, the pickup relabel that hands that child to the
    implementer, and a real checkout carrying the slice it committed.
    """

    def setUp(self) -> None:
        self.checkout = _slice.SliceCheckout()
        self.checkout.prepare(self)
        self.github = _fakes.FakeGitHubClient()
        self.parent = _late.seed_late_issue(
            self.github,
            _late.late_generation(),
            **_fixtures._authorized_exemption(
                self.checkout.candidate, self.checkout.base,
            ),
        )
        self.issue = _split_off_a_child(self.github, self.parent)
        # What the split wrote to the child and nothing else, kept before any
        # tick runs: the cases about what a child inherits assert against this
        # rather than against a literal, so they are about the seeding.
        self.seeded = dict(self.github.pinned_data(self.issue.number))
        self.github.set_workflow_label(self.issue, _fixtures.LABEL_IMPLEMENTING)
        self._labelled_before = len(self.github.label_history)

    def _seed_child(self, **state) -> None:
        """Add to the pinned comment the split wrote, never over it."""
        self.github.seed_state(
            self.issue.number, **{**self._pinned(), **state},
        )

    def _authorize(self, candidate_sha: str) -> None:
        """Post the operator's whole-comment authorization of one commit.

        Numbered off the client's own allocator rather than picked, since the
        tick that parked this issue has already written to the thread and a
        reply at or below its notice is one the staleness rule never reads.
        """
        self.issue.comments.append(_fakes.FakeComment(
            self.github.next_reply_id(self.issue),
            _fixtures._authorize_command(candidate_sha),
            user=_fakes.FakeUser(_gate.TRUSTED_AUTHOR),
        ))

    def _run_slice(
        self,
        ceiling: int = _slice.WHOLE_SLICE,
        candidate: str = "",
        **run_options,
    ):
        """Run one tick over this slice, with git taking the reading.

        The pair the gate freezes is this repository's own -- the base commit
        the slice was cut from, and the commit it is being published at -- so
        the count the seam takes is the prospective pull request's whole diff.

        A case naming `added_lines` itself is asking the counterfactual: what
        this same candidate would have earned had the gate taken one of the
        narrower readings of it instead.
        """
        run_options.setdefault("added_lines", _additions._count_added_lines)
        with patch.object(config, MAX_ADDED_LINES, ceiling):
            return self._run_gate(
                worktree=self.checkout.worktree,
                issue_worktree=self.checkout.worktree,
                frozen_base=FrozenCommit(sha=self.checkout.base),
                candidate_commit=FrozenCommit(
                    sha=candidate or self.checkout.candidate,
                ),
                **run_options,
            )

    def _labelled(self) -> list:
        """Where this case's own ticks have taken the child, and nowhere else.

        Past the writes the split and the pickup made, since those are the
        arrangement rather than the answer.
        """
        return self.github.label_history[self._labelled_before:]

    def _measured(self) -> int | None:
        """What this tick counted, off the record both sides of the gate emit.

        Read from the stream rather than from the pinned comment because only
        one side of the ceiling leaves a number there: a candidate that
        publishes has its generation dropped in the same breath, and the
        emitted measurement is the one place the count survives either way.
        """
        measurements = self._records(_gate.EVENT_LATE_MEASUREMENT)
        self.assertEqual(len(measurements), 1)
        return measurements[0].get("additions")
