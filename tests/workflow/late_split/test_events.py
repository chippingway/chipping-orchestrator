# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What each family may say, and the closed vocabulary a verdict says it in."""
from __future__ import annotations

import unittest

from orchestrator.workflow.late_split import events as _events, formats as _formats
from orchestrator.workflow.late_split.models import (
    LateFailure,
    LateResource,
    LateResourceKind,
    LateResourceState,
    LateVerdict,
)
from orchestrator.workflow.late_split.rewrite_values import LateRewriteProof
from tests.workflow.late_split import event_test_support as _event_support, generation_test_support as _support

_FAMILY_KEY = "family"
_CATEGORY = _events.LateVerdictCategory
_REFUSED = _formats.InvalidLateValue
# A category that arrives as something other than text at all, which the
# mapper has to answer for rather than raise on.
_NOT_TEXT = ("generated_artifacts",)
# What an agent's own words look like when they reach a field: prose, a path,
# and a quoted secret, none of which may become a record.
_PROSE = "rationale: inspect /srv/private/key before splitting"
_MULTILINE = f"{_PROSE}\n"
_PROOF = LateRewriteProof
_STEP = _support.MEASUREMENT_STEP
_SAID = _support.FAILURE_DETAIL
_LIMIT = _events.MAX_FAILURE_DETAIL
# What git actually writes when a step fails: the sentence naming the fault,
# and then the advice, the hints, and the remote's banner under it.
_TRANSCRIPT = f"\n  {_SAID}  \nhint: check your credentials\nhint: or ask"
# The same transcript written by a step whose output uses bare carriage
# returns, which display as two lines everywhere one of these is read.
_RETURNED = f"{_SAID}\rhint: check your credentials"
# A failure that answers for a step no reading was taken at: nothing here has
# a measurement to name or a line to carry.
_UNMEASURED_FAILURE = LateFailure.SNAPSHOT_FAILED


class FamilySchemaTest(unittest.TestCase):
    """A family carries what it owns, all of it, and nothing else."""

    def test_every_family_builds_with_its_own_fields(self) -> None:
        for event in _event_support.every_family():
            with self.subTest(family=str(event.family)):
                self.assertIsInstance(event, _events.LateEvent)

    def test_the_vocabulary_is_covered(self) -> None:
        # The walk above is only worth what it covers, so a family the schema
        # gains without a case is a family nothing here checks.
        self.assertEqual(
            {event.family for event in _event_support.every_family()},
            set(_event_support._FAMILY),
        )

    def test_a_field_the_family_lacks_is_refused(self) -> None:
        # A measurement claiming a verdict, a failure claiming a resource, a
        # cancellation claiming a restart step: each would be a record whose
        # fields describe a step that did not happen.
        unowned = (
            {_FAMILY_KEY: _event_support._FAMILY.MEASUREMENT, "verdict": LateVerdict.SINGLE},
            {
                _FAMILY_KEY: _event_support._FAMILY.FAILURE,
                "failure": LateFailure.SNAPSHOT_FAILED,
                "resource": _support.SNAPSHOT,
            },
            {
                _FAMILY_KEY: _event_support._FAMILY.CANCELLATION,
                "restart_step": _events.LateRestartStep.PENDING,
            },
            {_FAMILY_KEY: _event_support._FAMILY.MEASUREMENT, "measurement_failure": _STEP},
            {_FAMILY_KEY: _event_support._FAMILY.CANCELLATION, "detail": _SAID},
            {
                _FAMILY_KEY: _event_support._FAMILY.CANCELLATION,
                "transfer_proof": _PROOF.PUSHED,
            },
        )
        for fields in unowned:
            with self.subTest(family=str(fields[_FAMILY_KEY])), self.assertRaises(_REFUSED):
                _events.LateEvent(**fields)

    def test_a_failure_may_name_its_step(self) -> None:
        # A `measurement_failed` record reaches both sinks for a remote that
        # would not answer, a checkout that is gone, and a diff nothing can
        # pin, and the member is what tells those apart afterwards. Optional
        # in both directions: most of the vocabulary answers for a step that
        # took no reading at all, and a failure naming none is still a record.
        described = _event_support._failure(measurement_failure=_STEP, detail=_SAID)
        bare = _event_support._failure()

        self.assertIs(described.measurement_failure, _STEP)
        self.assertEqual(described.detail, _SAID)
        self.assertIsNone(bare.measurement_failure)
        self.assertIsNone(bare.detail)

    def test_a_missing_required_field_is_refused(self) -> None:
        for family in (
            _event_support._FAMILY.VERDICT, _event_support._FAMILY.FAILURE, _event_support._FAMILY.SNAPSHOT,
            _event_support._FAMILY.CLEANUP, _event_support._FAMILY.RESTART, _event_support._FAMILY.TRANSFER,
        ):
            with self.subTest(family=str(family)), self.assertRaises(_REFUSED):
                _events.LateEvent(family=family)

    def test_a_family_that_is_not_a_member_is_refused(self) -> None:
        with self.assertRaises(_REFUSED):
            _events.LateEvent(family="late_measurement")

    def test_the_refusal_names_the_family_and_field(self) -> None:
        with self.assertRaisesRegex(_REFUSED, "late_measurement.*failure"):
            _events.LateEvent(
                family=_event_support._FAMILY.MEASUREMENT, failure=LateFailure.RESTART_FAILED,
            )


class VerdictCompanionTest(unittest.TestCase):
    """A category explains a verdict; a child count belongs to one verdict."""

    def test_a_single_verdict_may_explain_itself(self) -> None:
        # The artifact-dominated `single` is the signal the telemetry exists
        # to count, so the verdict that produces it has to be recordable.
        explained = _event_support.verdict_event(
            verdict=LateVerdict.SINGLE,
            category=_CATEGORY.GENERATED_ARTIFACTS,
        )
        self.assertIs(explained.category, _CATEGORY.GENERATED_ARTIFACTS)

    def test_a_verdict_needs_no_category(self) -> None:
        self.assertIsNone(
            _event_support.verdict_event(verdict=LateVerdict.SINGLE).category,
        )

    def test_a_question_must_say_what_it_asks_about(self) -> None:
        # The one verdict a category is required of: a question nobody can
        # group is a question nobody can act on.
        with self.assertRaises(_REFUSED):
            _event_support.verdict_event(verdict=LateVerdict.QUESTION)

    def test_a_child_count_pairs_only_with_a_split(self) -> None:
        with self.assertRaises(_REFUSED):
            _event_support.verdict_event(
                verdict=LateVerdict.QUESTION,
                category=_CATEGORY.UNSAFE_SPLIT,
                child_count=_support.CHILD_COUNT,
            )
        with self.assertRaises(_REFUSED):
            _event_support.verdict_event(verdict=LateVerdict.SPLIT)


class FailureCompanionTest(unittest.TestCase):
    """Which failure the measurement companions describe, and in what order."""

    def test_the_companions_belong_to_one_failure(self) -> None:
        # A field allowed beside every member describes none of them: a
        # snapshot the remote refused and a restart GitHub declined took no
        # reading, so neither has a step to name or a line to carry.
        unpaired = (
            {"measurement_failure": _STEP},
            {"detail": _SAID},
            {"measurement_failure": _STEP, "detail": _SAID},
        )
        for fields in unpaired:
            with self.subTest(fields=sorted(fields)), self.assertRaises(_REFUSED):
                _events.LateEvent(
                    family=_event_support._FAMILY.FAILURE,
                    failure=_UNMEASURED_FAILURE,
                    **fields,
                )

    def test_a_line_needs_the_step_it_came_from(self) -> None:
        # The roads that refuse a RECORD rather than a reading hold the
        # sentence they were about to tell a human, and that sentence is
        # prose. A line with no step over it is the field it would travel in.
        with self.assertRaises(_REFUSED):
            _event_support._failure(detail=_SAID)


class DetailTypeTest(unittest.TestCase):
    """A member is required where a member is declared, not a lookalike."""

    def test_a_lookalike_string_is_not_a_member(self) -> None:
        # `StrEnum` members compare equal to their own spelling, so a raw
        # string satisfies every comparison the schema makes -- and would be
        # written verbatim. Only the member itself is accepted.
        lookalikes = (
            {"verdict": "single"},
            {"verdict": LateVerdict.QUESTION, "category": "generated_artifacts"},
        )
        for fields in lookalikes:
            with self.subTest(fields=sorted(fields)), self.assertRaises(_REFUSED):
                _event_support.verdict_event(**fields)

    def test_prose_cannot_enter_through_a_typed_field(self) -> None:
        # The adversarial case the closed vocabulary exists for: an
        # adjudication's rationale, naming a path, offered as a category.
        with self.assertRaises(_REFUSED):
            _event_support.verdict_event(
                verdict=LateVerdict.QUESTION, category=_PROSE,
            )

    def test_a_measurement_step_must_be_a_member(self) -> None:
        # The vocabulary is the git layer's, and a `StrEnum` member compares
        # equal to its own spelling -- so the raw string would satisfy every
        # comparison and be written verbatim under the field named for it.
        for asked in (str(_STEP), _PROSE):
            with self.subTest(asked=asked), self.assertRaises(_REFUSED):
                _event_support._failure(measurement_failure=asked)

    def test_a_detail_must_be_one_bounded_line(self) -> None:
        # The one field no vocabulary closes, so the bound is what stands in
        # for membership: a transcript, an untrimmed line, an unbounded one,
        # and a value that is not text at all are each refused rather than
        # written into two append-only sinks.
        unbounded = (
            _MULTILINE, _RETURNED, f" {_SAID}", "x" * (_LIMIT + 1), _NOT_TEXT,
        )
        for said in unbounded:
            with self.subTest(said=said), self.assertRaises(_REFUSED):
                _event_support._failure(measurement_failure=_STEP, detail=said)

    def test_a_count_must_be_a_real_count(self) -> None:
        for counted in (True, 2.5, "4", -1):
            with self.subTest(counted=counted), self.assertRaises(_REFUSED):
                _event_support.verdict_event(
                    verdict=LateVerdict.SPLIT, child_count=counted,
                )

    def test_a_resource_is_checked_through(self) -> None:
        # The kind is what a record reports, so a resource built with a string
        # for it would put that string in the payload under the field named
        # for the vocabulary.
        untyped = (
            LateResource(kind=_PROSE, target="x"),
            LateResource(
                kind=LateResourceKind.BRANCH, target="x", resource_state="gone",
            ),
            LateResource(kind=LateResourceKind.BRANCH, target=""),
            LateResource(kind=LateResourceKind.BRANCH, target=_MULTILINE),
        )
        for resource in untyped:
            with self.subTest(kind=str(resource.kind)), self.assertRaises(_REFUSED):
                _event_support.cleanup_event(resource)

    def test_a_typed_resource_is_accepted(self) -> None:
        recorded = _event_support.cleanup_event(
            LateResource(
                kind=LateResourceKind.BRANCH,
                target="orchestrator/issue-7",
                resource_state=LateResourceState.FAILED,
            ),
        )
        self.assertIs(recorded.resource.kind, LateResourceKind.BRANCH)


class TransferDetailTest(unittest.TestCase):
    """A transfer names both ends it moved a verdict off, and what proved it."""

    def test_all_four_are_required(self) -> None:
        # A record short of any of them describes a move nobody could check:
        # which change was carried, which rewrite carried it, and what proved
        # the push behind it landed are the whole of what it says.
        for name in (
            "rewrite_kind",
            "transfer_proof",
            "transferred_from_sha",
            "transferred_from_base_sha",
        ):
            with self.subTest(missing=name), self.assertRaises(_REFUSED):
                _event_support.transfer_event(**{name: None})

    def test_an_end_must_be_a_whole_commit(self) -> None:
        # Bounded as a commit rather than as text: an abbreviation names no
        # object a reader could re-derive the equality from, and prose offered
        # through a field named for a SHA is exactly what the bound is for.
        for given in (_support.CANDIDATE_SHA[:7], _PROSE, ""):
            with self.subTest(given=given), self.assertRaises(_REFUSED):
                _event_support.transfer_event(transferred_from_sha=given)

    def test_its_vocabularies_are_closed(self) -> None:
        for name in ("rewrite_kind", "transfer_proof"):
            with self.subTest(field=name), self.assertRaises(_REFUSED):
                _event_support.transfer_event(**{name: _PROSE})


class MeasurementFailureEventTest(unittest.TestCase):
    """What one refused size reading is reduced to before it is recorded."""

    def test_the_family_and_failure_are_unchanged(self) -> None:
        # The two companions widen what a record SAYS and nothing about what
        # it is: every consumer filtering on `late_failure` carrying
        # `measurement_failed` goes on matching every one of these.
        recorded = _events.measurement_failure_event(_STEP, _SAID)

        self.assertIs(recorded.family, _event_support._FAMILY.FAILURE)
        self.assertIs(recorded.failure, LateFailure.MEASUREMENT_FAILED)
        self.assertIs(recorded.measurement_failure, _STEP)

    def test_a_transcript_is_cut_to_its_first_line(self) -> None:
        # git names the fault first and spends the lines after it on advice
        # and a banner. Handed over whole the event would be refused, and a
        # refused record is the only account of a reading that never happened.
        # Which character ended that first line does not change where it ends:
        # a bare carriage return displays as a break wherever one of these is
        # read, so it is one here too.
        for whole in (_TRANSCRIPT, _RETURNED):
            with self.subTest(said=whole):
                self.assertEqual(
                    _events.measurement_failure_event(_STEP, whole).detail,
                    _SAID,
                )

    def test_a_line_past_the_bound_is_cut(self) -> None:
        # The head of the sentence locates the fault; nothing at all locates
        # nothing.
        cut = _events.measurement_failure_event(_STEP, "y" * (_LIMIT * 2))

        self.assertEqual(cut.detail, "y" * _LIMIT)

    def test_a_step_that_said_nothing_carries_no_line(self) -> None:
        for said in ("", "   \n\n", None):
            with self.subTest(said=said):
                self.assertIsNone(
                    _events.measurement_failure_event(_STEP, said).detail,
                )

    def test_a_refusal_naming_no_step_names_none(self) -> None:
        # The size gate parks on refusals that reached no reading at all -- a
        # pinned record too damaged to act on, a debt no push can pay -- and
        # those say so in their own words. The record keeps the family and
        # reports no step rather than reporting the sentence as one.
        # The line goes with the step: what those roads hold instead is the
        # sentence they were about to tell a human, and prose has no field on
        # a late record.
        refused = _events.measurement_failure_event(_PROSE, _SAID)

        self.assertIsNone(refused.measurement_failure)
        self.assertIsNone(refused.detail)
        self.assertIs(refused.failure, LateFailure.MEASUREMENT_FAILED)


class VerdictCategoryTest(unittest.TestCase):
    """A category is chosen from the vocabulary, never written into it."""

    def test_a_known_category_maps_to_its_member(self) -> None:
        known = {
            "generated_artifacts": _CATEGORY.GENERATED_ARTIFACTS,
            "Generated Artifacts": _CATEGORY.GENERATED_ARTIFACTS,
            " UNSAFE_SPLIT ": _CATEGORY.UNSAFE_SPLIT,
        }
        for asked, member in known.items():
            with self.subTest(asked=asked):
                self.assertIs(_events.verdict_category(asked), member)

    def test_agent_prose_never_becomes_a_category(self) -> None:
        # The reason the vocabulary is closed: an adjudication's rationale
        # names files and quotes its own reasoning, and none of that may reach
        # a sink. Everything unrecognized groups under one member instead.
        prose = (
            (
                "Generated Artifacts?! docs/architecture.md and "
                "orchestrator/cli.py look wrong to commit"
            ),
            _PROSE,
            "",
            None,
            _NOT_TEXT,
        )
        for asked in prose:
            with self.subTest(asked=asked):
                self.assertIs(_events.verdict_category(asked), _CATEGORY.UNKNOWN)

    def test_the_mapper_always_answers(self) -> None:
        # A `question` verdict requires a category, so the mapper answering
        # None would leave the emitter with a record it cannot legally build.
        self.assertIsNotNone(_events.verdict_category(None))


if __name__ == "__main__":
    unittest.main()
