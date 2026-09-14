# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a reading the size gate could not take costs, and how it is retried.

A candidate whose size is unknown is not a small one, so nothing is published
on the strength of one: the pair that was frozen stays on the record, the issue
is handed back with the reason it failed for -- or, where that reason is a base
the transport could not reach, counted quietly against the bound a retry is
held to -- and the retry re-reads exactly that pair. The evidence rules
beside it are the same claim from the other end -- a recorded SHA is what a
later tick acts on, never whatever the branch or the remote has become since.
"""

from __future__ import annotations

import unittest
from pathlib import Path
from types import MappingProxyType
from unittest.mock import patch

from orchestrator import config
from orchestrator.git.measurement.models import FrozenCommit, MeasurementFailure
from tests.workflow.fixtures import (
    LABEL_DECOMPOSING,
    MEASURED_BASE_SHA,
    MEASURED_CANDIDATE_SHA,
    SHA_LENGTH,
)
from tests.workflow.stages.implementing import late_gate_test_support as support

_TEMP_WORKTREE_ROOT = Path("/tmp")
_RETIRED_CYCLE = 4
_RAISED_THRESHOLD = 100000
_DECOMPOSING = (support.GATE_ISSUE_NUMBER, LABEL_DECOMPOSING)
_STAGE_IMPLEMENTING = "implementing"

# One dropped field per case, named as the park reports it.
_DAMAGED_RECORDS = (
    ("late_base_sha", "base_sha", ""),
    ("late_threshold", "threshold", None),
    ("late_phase", "phase", None),
)

# What makes a record an already-taken measurement rather than a frozen pair
# still waiting for one: the count. Each damaged case carries it, so the tick
# reaches the reconciliation rather than measuring afresh.
_COUNTED_ADDITIONS = 12
# The one typed failure every refusal on this page reports under.
_FAILURE = "failure"
_MEASUREMENT_FAILED = "measurement_failed"

# The two of them a reused pair still has to carry. A missing BASE is not one:
# there is no recorded object to protect, so the freeze simply takes a fresh
# one -- while a ceiling and a boundary cannot be re-derived from anything and
# a record short of either is repaired rather than guessed at.
_REUSED_FIELDS = tuple(
    case for case in _DAMAGED_RECORDS if case[1] != "base_sha"
)
# The identities a record is joined by, each dropped from the pinned comment
# in turn. `late_generation` is deliberately not one of them: a counter of 0
# is a cycle that has frozen a candidate without adjudicating it yet, which
# the domain's own record gate allows.
_DROPPED_CYCLE = "late_cycle_id"
_DROPPED_ROOT = "late_root_issue"
_DAMAGED_IDENTITIES = (_DROPPED_CYCLE, _DROPPED_ROOT, "late_current_issue")
# An issue number that is not the one being decided, which is what a record
# carrying somebody else's generation reads back as.
_FOREIGN_ISSUE = 4242

# Every way a record can be one this issue may not mint over -- recorded
# against another issue, carrying no cycle to be joined by, and short of the
# ceiling or the boundary a reading is settled under -- each seeded with no
# base beside it: that is the shape the quiet retry itself leaves, so it is
# the one road into a reuse with no recorded base to be proved by. The base
# is the only field NOT among them, since being without one is what the
# failure being retried means.
_UNMINTABLE_RECORDS = (
    {"current_issue": _FOREIGN_ISSUE},
    {"dropping": _DROPPED_CYCLE},
    {"threshold": None},
    {"phase": None},
)

_AGENT_TIMEOUT = "agent_timeout"
_PRE_IMPLEMENT_SHA = "pre_implement_sha"
_PRE_TIMEOUT_SHA = "sha-pre"
_POST_TIMEOUT_SHA = "sha-post"
_MOVED_SHA = "e" * SHA_LENGTH
_REAPED_WORKTREE = Path("/nonexistent/orchestrator-reaped-worktree")
# The two evidence refusals a record is reported through without ever being
# measured: the checkout is gone, or the object it names is.
_REAPED_CHECKOUT = MappingProxyType({"worktree": _REAPED_WORKTREE})
_ABSENT_OBJECT = MappingProxyType({
    "recorded_commit": FrozenCommit(
        failure=MeasurementFailure.CANDIDATE_ABSENT,
    ),
})
_MISSING_EVIDENCE = (
    ("a reaped worktree", _REAPED_CHECKOUT),
    ("an absent object", _ABSENT_OBJECT),
)
# The sentence the generic parked-continue classifier posts, which a
# measurement park must never reach.
_NEEDS_GUIDANCE = "needs your actual guidance"


class LateGateEvidenceTest(support._GateCase, unittest.TestCase):
    """A recorded SHA is the evidence, and a retry re-reads exactly it."""

    def test_a_frozen_pair_is_not_refrozen(self) -> None:
        # The crash boundary the persist-before-count ordering exists for: the
        # tick that died had already frozen a base, and re-freezing would let a
        # base that advanced since change the size of a candidate nobody
        # touched.
        self._seed(**support.recorded_generation())

        mocks = self._run_gate(added_lines=support.SMALL_ADDITIONS)

        mocks[support.FREEZE_BASE_COMMIT].assert_not_called()
        counted = mocks[support.COUNT_ADDED_LINES].call_args
        self.assertEqual(counted.args[1], MEASURED_BASE_SHA)
        self.assertEqual(counted.args[2], MEASURED_CANDIDATE_SHA)

    def test_a_recorded_count_is_not_retaken(self) -> None:
        # The threshold pinned into the record is the one the generation was
        # frozen under, so a setting retuned between two ticks cannot re-judge
        # a candidate mid-flight.
        self._seed(
            **support.recorded_generation(
                additions=support.OVERSIZED_ADDITIONS,
            ),
        )

        with patch.object(config, "MAX_ADDED_LINES", _RAISED_THRESHOLD):
            mocks = self._run_gate()

        self._assert_unmeasured(mocks)
        self._assert_held(mocks)
        self.assertIn(_DECOMPOSING, self.github.label_history)

    def test_the_cycle_follows_the_retired_one(self) -> None:
        # Monotonic across the clear: a record naming cycle 5 always names the
        # same attempt, even where the attempt before it left no generation
        # behind.
        self._seed(**{support.KEY_RETIRED_CYCLE: _RETIRED_CYCLE})

        self._run_gate(added_lines=support.OVERSIZED_ADDITIONS)

        pinned = self._pinned()
        self.assertEqual(pinned[support.KEY_CYCLE_ID], _RETIRED_CYCLE + 1)
        self.assertNotIn(support.KEY_RETIRED_CYCLE, pinned)

    def test_a_child_inherits_its_lineage(self) -> None:
        # The record a split WROTE about this issue is what its own generation
        # is minted from, so the bound applies at the depth it was really born
        # at and the prompt states the slice it really owns.
        self._seed(**support.recorded_ancestry())

        self._run_gate(added_lines=support.OVERSIZED_ADDITIONS)

        pinned = self._pinned()
        self.assertEqual(
            pinned[support.KEY_ROOT_ISSUE], support.CHILD_ROOT_ISSUE,
        )
        self.assertEqual(
            pinned[support.KEY_LINEAGE_DEPTH], support.CHILD_DEPTH,
        )
        self.assertEqual(pinned[support.KEY_SCOPE], support.CHILD_SCOPE)


class LateGateRecordedCandidateTest(support._GateCase, unittest.TestCase):
    """A recorded candidate is what a tick reconciles, never the current head.

    Every case here is an UNPARKED issue, which is what makes them one
    subject: no developer ran, so nothing in the checkout can be fresh output
    and a head that is not the recorded commit is a checkout somebody moved.
    What a head that moved because a resumed developer really did commit again
    earns is the guidance subject in the retry module beside this one.
    """

    def setUp(self) -> None:
        super().setUp()
        self._seed(**support.recorded_generation())

    def test_a_missing_recorded_object_parks(self) -> None:
        mocks = self._run_gate(**self._moved_past_a_missing_object())

        self._assert_unmeasured(mocks)
        self._assert_held(mocks)
        self._assert_parked()

    def test_it_parks_with_the_switch_off_too(self) -> None:
        # The switch decides whether NEW work is measured. It does not license
        # publishing a head this host cannot prove the recorded work is behind.
        with patch.object(config, "DECOMPOSE", False):
            mocks = self._run_gate(**self._moved_past_a_missing_object())

        self._assert_unmeasured(mocks)
        self._assert_held(mocks)
        self._assert_parked()

    def test_the_record_is_left_for_the_retry(self) -> None:
        self._run_gate(**self._moved_past_a_missing_object())

        self._assert_frozen()

    def _moved_past_a_missing_object(self) -> dict:
        """A head that is not the recorded commit, on a host without it."""
        return {
            "candidate_commit": FrozenCommit(sha=_MOVED_SHA),
            "recorded_commit": FrozenCommit(
                failure=MeasurementFailure.CANDIDATE_ABSENT,
            ),
        }


class LateGateDamagedRecordTest(support._GateCase, unittest.TestCase):
    """A count is not a measurement without the fields that give it meaning."""

    def test_each_missing_field_parks(self) -> None:
        # The threshold is the sharpest: the record's own comparison answers
        # "not oversized" on a missing one, which is a damaged record
        # publishing as a small candidate.
        for field, dropped, blank in _DAMAGED_RECORDS:
            with self.subTest(field=field):
                self.setUp()
                self._seed(
                    **support.recorded_generation(
                        additions=_COUNTED_ADDITIONS, **{dropped: blank},
                    ),
                )

                mocks = self._run_gate()

                self._assert_held(mocks)
                self._assert_parked()
                self.assertIn(field, self.github.posted_comments[-1][1])

    def test_a_damaged_record_is_reported(self) -> None:
        self._seed(
            **support.recorded_generation(
                additions=_COUNTED_ADDITIONS, threshold=None,
            ),
        )

        self._run_gate()

        failures = self._records(support.EVENT_LATE_FAILURE)
        self.assertEqual(len(failures), 1)
        self.assertEqual(failures[0][_FAILURE], _MEASUREMENT_FAILED)

    def test_an_uncounted_record_parks_too(self) -> None:
        # The fields are written by the FREEZE, not by the count, so a record
        # reused for a reading still to be taken is as damaged without them as
        # one whose number is already in -- and this is the ordinary crash
        # retry, where a threshold-less record would otherwise reach the
        # settlement and publish as small because the comparison answers "not
        # oversized" on a missing ceiling.
        for field, dropped, blank in _REUSED_FIELDS:
            with self.subTest(field=field):
                self.setUp()
                self._seed(**support.recorded_generation(**{dropped: blank}))

                mocks = self._run_gate(
                    added_lines=support.OVERSIZED_ADDITIONS,
                )

                self._assert_unmeasured(mocks)
                self._assert_held(mocks)
                self._assert_parked()
                self.assertEqual(self.github.label_history, [])

    def test_an_uncounted_refusal_is_reported(self) -> None:
        self._seed(**support.recorded_generation(threshold=None))

        self._run_gate(added_lines=support.OVERSIZED_ADDITIONS)

        failures = self._records(support.EVENT_LATE_FAILURE)
        self.assertEqual(len(failures), 1)
        self.assertEqual(failures[0][_FAILURE], _MEASUREMENT_FAILED)

    def test_a_counted_record_proves_its_base(self) -> None:
        # The count is done, but the object it was taken against is not here.
        # Acting on the number while its evidence is missing is the
        # substitution this whole contract refuses, so the candidate is held
        # on a reading the fetch lost rather than published on the number
        # beside it.
        self._seed(
            **support.recorded_generation(additions=support.SMALL_ADDITIONS),
        )

        mocks = self._run_gate(base_object_present=False)

        self._assert_held(mocks)
        self._assert_missed()


class LateGateDamagedIdentityTest(support._GateCase, unittest.TestCase):
    """A count nothing can be correlated by is not a measurement either.

    The half of a record nothing downstream reads, which is exactly why
    losing it fails open: the size comparison is happy to publish a count with
    no cycle, no root, or somebody else's issue number beside it, and what an
    operator is left with afterwards is a shipped change and no reading they
    can defend it by.
    """

    def test_a_missing_identity_parks(self) -> None:
        # A count that publishes but cannot be correlated is a reading no
        # operator can defend afterwards: nothing downstream reads the
        # identity, so the record's own comparison ships it as happily as a
        # whole one.
        for field in _DAMAGED_IDENTITIES:
            with self.subTest(field=field):
                self.setUp()
                self._seed(
                    **support.recorded_generation(
                        dropping=field, additions=_COUNTED_ADDITIONS,
                    ),
                )

                mocks = self._run_gate()

                self._assert_held(mocks)
                self._assert_parked()
                self.assertEqual(self.github.label_history, [])

    def test_a_foreign_record_parks(self) -> None:
        # A positive `late_current_issue` is not the same claim as one naming
        # this issue, and a count taken over there is not this one's answer.
        self._seed(
            **support.recorded_generation(
                additions=_COUNTED_ADDITIONS, current_issue=_FOREIGN_ISSUE,
            ),
        )

        mocks = self._run_gate()

        self._assert_held(mocks)
        self._assert_parked()
        said = self.github.posted_comments[-1][1]
        self.assertIn(str(_FOREIGN_ISSUE), said)

    def test_an_uncounted_identity_parks_too(self) -> None:
        # The identity is written by the FREEZE, so the ordinary crash retry
        # carries the same damage into the reading it is about to take.
        self._seed(**support.recorded_generation(dropping=_DROPPED_CYCLE))

        mocks = self._run_gate(added_lines=support.SMALL_ADDITIONS)

        self._assert_unmeasured(mocks)
        self._assert_held(mocks)
        self._assert_parked()

    def test_missing_evidence_is_reported_too(self) -> None:
        # The refusals taken before any measurement reach the sinks through
        # the same identity, and needed the same repair: a record carrying a
        # cycle and no root is one the record gate refuses outright, so both
        # required events would go down with the record they are about.
        for evidence, seeded in _MISSING_EVIDENCE:
            with self.subTest(evidence=evidence):
                self.setUp()
                self._seed(
                    **support.recorded_generation(dropping=_DROPPED_ROOT),
                )

                self._run_gate(**seeded)

                self._assert_reported_here("root_issue")

    def test_a_foreign_record_is_reported_here(self) -> None:
        # A record naming another issue validates on every field the sinks
        # check, so nothing refuses it -- both streams simply file this
        # issue's refusal against that one, where no operator looking at this
        # issue would ever find it.
        self._seed(
            **support.recorded_generation(current_issue=_FOREIGN_ISSUE),
        )

        self._run_gate(**_ABSENT_OBJECT)

        self._assert_reported_here("issue")

    def test_a_damaged_identity_is_still_reported(self) -> None:
        # Filed under the record it is about, the refusal would go down with
        # it: neither sink may carry an identity the domain's gate refuses, so
        # a damaged pinned comment would leave no trace of its own damage.
        self._seed(
            **support.recorded_generation(
                dropping=_DROPPED_CYCLE, additions=_COUNTED_ADDITIONS,
            ),
        )

        self._run_gate()

        self._assert_reported_here("root_issue")

    def _assert_reported_here(self, field: str) -> None:
        """One failure on the audit stream, correlated to this issue."""
        reported = self._records(support.EVENT_LATE_FAILURE)
        self.assertEqual(len(reported), 1)
        self.assertEqual(reported[0][_FAILURE], _MEASUREMENT_FAILED)
        self.assertEqual(reported[0][field], support.GATE_ISSUE_NUMBER)


class LateGateUnusableRetryTest(support._GateCase, unittest.TestCase):
    """A record the gate may not act on is not a pair whose base is retried.

    The two halves of "unusable" meet the one failure this gate retries
    QUIETLY, and quiet is what makes them dangerous together: the retry writes
    the record back, so a record reaching it damaged -- or recorded against
    another issue -- would be repaired under this issue's whole identity and
    left unparked, publishable by the next tick that finds the base readable.
    The proof that stops it is the reused pair's own, so the road with nothing
    in front of it is covered too: the pre-spawn reconciliation runs before
    the gate that would otherwise catch the damage.
    """

    def test_a_damaged_record_is_not_retried(self) -> None:
        # A base this host cannot show is the one failure the gate retries
        # quietly -- and a quiet retry is a WRITE. A record short of the
        # fields that give its count meaning may not reach it: repaired under
        # this issue's identity and left unparked, it would publish on a
        # ceiling nobody set the moment the base came back. So the damage is
        # answered first, and no reading of this pair is spent on it.
        self._seed(**support.recorded_generation(threshold=None))

        mocks = self._run_gate(base_object_present=False)

        self._assert_unmeasured(mocks)
        self._assert_held(mocks)
        self._assert_parked()
        pinned = self._pinned()
        self.assertNotIn(support.KEY_THRESHOLD, pinned)
        self.assertNotIn(support.KEY_MISS_COUNT, pinned)
        self.assertIn("late_threshold", self.github.posted_comments[-1][1])


    def test_a_record_with_no_base_is_proved_too(self) -> None:
        # The road the base proof cannot cover, because there is no base on it
        # to prove: a remote that would not name one records none at all, so
        # the retry over that same candidate freezes AFRESH -- and the mint it
        # freezes under inherits the record beside it, stamping this issue's
        # number over whatever the record said. Unproved, that is the same
        # takeover through the one door left open.
        for damage in _UNMINTABLE_RECORDS:
            with self.subTest(record=damage):
                self.setUp()
                seeded = support.recorded_generation(base_sha="", **damage)
                self._seed(**seeded)

                mocks = self._run_gate(added_lines=support.SMALL_ADDITIONS)

                self._assert_unmeasured(mocks)
                self._assert_held(mocks)
                self._assert_parked()
                self.assertNotIn(support.KEY_MISS_COUNT, self._pinned())
                # Untouched rather than merely unpublished: what the mint
                # would have done is rewrite it under this issue's own name.
                self.assertEqual(
                    {key: self._pinned().get(key) for key in seeded}, seeded,
                )

    def test_a_lost_ceiling_is_not_restamped(self) -> None:
        # The sharpest of them, because the repair looks like a success: the
        # mint the retry goes through stamps the ceiling the process is
        # running with NOW, so a generation that lost the one it was frozen
        # under is re-judged against a setting retuned since -- and an
        # oversized candidate publishes as a small one on a reading nobody
        # took at that ceiling.
        self._seed(**support.recorded_generation(base_sha="", threshold=None))

        with patch.object(config, "MAX_ADDED_LINES", _RAISED_THRESHOLD):
            mocks = self._run_gate(added_lines=support.OVERSIZED_ADDITIONS)

        self._assert_unmeasured(mocks)
        self._assert_held(mocks)
        self._assert_parked()
        self.assertIn("late_threshold", self.github.posted_comments[-1][1])

    def test_a_foreign_record_is_not_adopted(self) -> None:
        # The sharpest shape of the same rule, and the one a single tick
        # cannot show on its own. The quiet retry a missing base earns writes
        # the record back, so a reading taken over THERE would be rewritten
        # under this issue's whole identity, left unparked, and published here
        # by the next tick that finds the base readable. The record is left
        # naming the issue it was taken on, and no base that comes back makes
        # it this one's to publish.
        self._seed(**support.recorded_generation(current_issue=_FOREIGN_ISSUE))
        self._run_gate(base_object_present=False)

        mocks = self._run_gate(added_lines=support.SMALL_ADDITIONS)

        self._assert_held(mocks)
        self._assert_parked()
        pinned = self._pinned()
        self.assertEqual(pinned[support.KEY_CURRENT_ISSUE], _FOREIGN_ISSUE)
        self.assertNotIn(support.KEY_MISS_COUNT, pinned)


class LateGateRefusalTest(support._GateCase, unittest.TestCase):
    """A reading nobody could take is never a small candidate."""

    def test_an_uncounted_diff_parks(self) -> None:
        mocks = self._run_gate(added_lines=MeasurementFailure.DIFF_FAILED)

        self._assert_held(mocks)
        self.assertEqual(self.github.label_history, [])
        self._assert_parked()
        self._assert_frozen()

    def test_an_unfrozen_base_is_counted_and_retried(self) -> None:
        # The failure is reportable because the identity went down with it: a
        # record no sink could correlate would leave the operator with a
        # refusal and nothing to join it to. What the remote would not name is
        # the transport, so the candidate is recorded with no base beside it
        # and the reading is taken again rather than handed to a human.
        mocks = self._run_gate(
            frozen_base=FrozenCommit(
                failure=MeasurementFailure.BASE_UNREADABLE,
            ),
        )

        self._assert_unmeasured(mocks)
        self._assert_missed()
        pinned = self._pinned()
        self.assertEqual(
            pinned[support.KEY_CANDIDATE_SHA], MEASURED_CANDIDATE_SHA,
        )
        self.assertNotIn(support.KEY_BASE_SHA, pinned)

    def test_a_typed_failure_is_reported(self) -> None:
        self._run_gate(added_lines=MeasurementFailure.DIFF_UNPINNABLE)

        failures = self._records(support.EVENT_LATE_FAILURE)
        self.assertEqual(len(failures), 1)
        self.assertEqual(failures[0][_FAILURE], _MEASUREMENT_FAILED)
        self.assertEqual(failures[0]["stage"], _STAGE_IMPLEMENTING)

    def test_an_unnameable_candidate_parks(self) -> None:
        # A reading that did not happen is reported whether or not a pair was
        # ever frozen, so the identity is minted for the record rather than
        # the failure going unsaid. It is not PERSISTED: a pinned cycle with
        # no candidate under it freezes nothing, reconciles nothing, and the
        # guard that ends a live cycle when the issue closes would read it as
        # one.
        mocks = self._run_gate(
            candidate_commit=FrozenCommit(
                failure=MeasurementFailure.CANDIDATE_ABSENT,
            ),
        )

        self._assert_held(mocks)
        self._assert_parked()
        self.assertNotIn(support.KEY_CYCLE_ID, self._pinned())
        failures = self._records(support.EVENT_LATE_FAILURE)
        self.assertEqual(len(failures), 1)
        self.assertEqual(failures[0][_FAILURE], _MEASUREMENT_FAILED)
        self.assertEqual(failures[0]["cycle_id"], 1)
        self.assertEqual(failures[0]["root_issue"], support.GATE_ISSUE_NUMBER)

    def test_a_named_absent_candidate_is_recorded(self) -> None:
        # A revision that RESOLVED and would not peel carries the id it
        # resolved to, and that id is the only record of which commit the
        # attempt was about. Reported and dropped, the retry has nothing to
        # ask for, the base refresh has nothing to hold the branch by, and the
        # reconciliation ahead of the next spawn has nothing to prove -- so
        # whatever the checkout points at by then is measured in its place.
        mocks = self._run_gate(
            candidate_commit=FrozenCommit(
                sha=MEASURED_CANDIDATE_SHA,
                failure=MeasurementFailure.CANDIDATE_ABSENT,
            ),
        )

        self._assert_held(mocks)
        self._assert_parked()
        self.assertEqual(
            self._pinned()[support.KEY_CANDIDATE_SHA], MEASURED_CANDIDATE_SHA,
        )

    def test_the_recorded_id_binds_the_retry(self) -> None:
        # Which is the whole point of recording it: the next tick asks for
        # that exact object, and a checkout standing anywhere else is refused
        # rather than measured in its place.
        self._run_gate(
            candidate_commit=FrozenCommit(
                sha=MEASURED_CANDIDATE_SHA,
                failure=MeasurementFailure.CANDIDATE_ABSENT,
            ),
        )
        self._reply(support.BARE_CONTINUE)

        mocks = self._run_gate(
            candidate_commit=FrozenCommit(sha=_MOVED_SHA),
            added_lines=support.SMALL_ADDITIONS,
        )

        self._assert_no_agent(mocks)
        self._assert_unmeasured(mocks)
        self._assert_held(mocks)
        self.assertIn(MEASURED_CANDIDATE_SHA, self.github.posted_comments[-1][1])

    def test_a_repeated_refusal_reports_one_attempt(self) -> None:
        # Minting is derived from what the record already says, so a reading
        # that keeps failing correlates to the same attempt instead of
        # inventing a cycle per tick.
        absent = FrozenCommit(failure=MeasurementFailure.CANDIDATE_ABSENT)

        self._run_gate(candidate_commit=absent)
        self._run_gate(candidate_commit=absent)

        cycles = {
            record["cycle_id"]
            for record in self._records(support.EVENT_LATE_FAILURE)
        }
        self.assertEqual(cycles, {1})


class LateGateBaseIdentityTest(support._GateCase, unittest.TestCase):
    """A base the remote named is retried by id, never re-read."""

    def test_an_unfrozen_base_keeps_its_identity(self) -> None:
        # The remote NAMED the commit and this host cannot read it. Recording
        # the failure without the id would leave the retry nothing to ask for,
        # so the next pass would read the remote again and freeze whatever the
        # base branch had moved to since.
        self._run_gate(
            frozen_base=FrozenCommit(
                sha=MEASURED_BASE_SHA,
                failure=MeasurementFailure.BASE_ABSENT,
            ),
        )

        self._assert_missed()
        self.assertEqual(self._pinned()[support.KEY_BASE_SHA], MEASURED_BASE_SHA)

    def test_a_moved_base_is_not_read_again(self) -> None:
        # The regression the recorded identity exists for: the retry asks for
        # the exact object it froze, and a host that still does not hold it
        # takes the reading again -- rather than re-reading a remote whose base
        # has moved on and measuring a different pair under the same
        # generation.
        self._seed(**support.recorded_generation())

        mocks = self._run_gate(base_object_present=False)

        mocks[support.FREEZE_BASE_COMMIT].assert_not_called()
        self._assert_unmeasured(mocks)
        self._assert_held(mocks)
        self._assert_missed()
        self.assertEqual(self._pinned()[support.KEY_BASE_SHA], MEASURED_BASE_SHA)

    def test_a_restored_base_object_measures(self) -> None:
        # And once the object is back, the same recorded pair measures without
        # the remote being asked at all.
        self._seed(**support.recorded_generation())

        mocks = self._run_gate(added_lines=support.SMALL_ADDITIONS)

        # Proved twice on this path and against the same id both times: once
        # where the record is reconciled ahead of the spawn, once where the
        # gate reuses the pair. What matters is which object is asked for.
        self.assertEqual(
            {
                call.args[2]
                for call in mocks[support.BASE_OBJECT_PRESENT].call_args_list
            },
            {MEASURED_BASE_SHA},
        )
        mocks[support.FREEZE_BASE_COMMIT].assert_not_called()
        self._assert_published(mocks)


if __name__ == "__main__":
    unittest.main()
