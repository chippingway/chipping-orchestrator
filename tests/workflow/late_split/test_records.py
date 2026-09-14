# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a late record may carry, and what each family has to say in it."""
from __future__ import annotations

import unittest
from dataclasses import replace

from orchestrator.workflow.late_split import events as _events, formats as _formats, records as _records
from orchestrator.workflow.late_split.models import LateGeneration, LateVerdict
from orchestrator.workflow.state import WorkflowLabel
from tests.workflow.late_split import event_test_support as _event_support, generation_test_support as _support

_PREDECESSOR = 1
_REFUSED = _formats.InvalidLateValue
_MEASUREMENT, _VERDICT = _event_support.family_cases()[:2]
_FAILURE = _event_support.family_cases()[2]
_CLEANUP = _event_support.family_cases()[4]
_MEASUREMENT_FAILURE = "measurement_failure"
_DETAIL = "detail"
# The pair every size-bearing record names, spelled once because three of the
# assertions below read the same two fields off a payload.
_SOURCE_SHA = "source_sha"
_BASE_SHA = "base_sha"
_CATEGORY = _support.CATEGORY
# What a generation must never carry into a record: prose, a path, a quoted
# secret -- offered through the fields that are typed only by annotation.
_PROSE = "rationale: inspect /srv/private/key before splitting"
# What a measurement and the verdict answering it are read for, one field at a
# time, and a generation that has let all of it go.
_MEASURED_CASES = tuple(
    (event, name)
    for event in _event_support.family_cases()[:2]
    for name in ("candidate_sha", _BASE_SHA, "threshold", "additions", "phase")
)
_STRIPPED = _support.measured_generation(
    candidate_sha="", base_sha="", threshold=None, additions=None, phase=None,
)
_PUBLICATION = "publication"
_PRE = "pre_publication"
_POST = "post_publication"
_SOURCE_STAGE = "source_stage"
_PUBLISHED_SHA = "published_sha"
_PUBLISHED_PR = "published_pr_number"
_CONTEXT_FIELDS = (_SOURCE_STAGE, _PUBLISHED_PR, _PUBLISHED_SHA)
# What a marked entry may not reach a sink saying: a context it can no longer
# name, and one offered as text nothing looked up.
_UNNAMEABLE = (
    (_SOURCE_STAGE, None),
    (_SOURCE_STAGE, str(WorkflowLabel.FIXING)),
    (_SOURCE_STAGE, _PROSE),
    (_PUBLISHED_PR, None),
    (_PUBLISHED_PR, 0),
    (_PUBLISHED_PR, "34"),
    (_PUBLISHED_SHA, ""),
    (_PUBLISHED_SHA, _PROSE),
)


def _payload(event, **generation_fields) -> dict:
    return _records.build_late_payload(
        event, _support.measured_generation(**generation_fields),
    )


def _refusal(**generation_fields) -> str:
    """What the boundary said when it refused a generation."""
    try:
        _payload(_MEASUREMENT, **generation_fields)
    except _REFUSED as refused:
        return str(refused)
    raise AssertionError("the record was not refused")


class BoundedRecordTest(unittest.TestCase):
    """A record carries correlation and nothing a reader could not publish."""

    def test_no_family_writes_an_unlisted_field(self) -> None:
        for event in _event_support.family_cases():
            with self.subTest(family=str(event.family)):
                self.assertLessEqual(
                    set(_payload(event)),
                    set(_records.LATE_PAYLOAD_FIELDS),
                )

    def test_every_correlation_field_is_carried(self) -> None:
        # Every field a join needs is on the record itself, so an analysis
        # never has to read the pinned comment back to interpret one.
        self.assertEqual(
            _payload(_MEASUREMENT),
            {
                "cycle_id": _support.CYCLE_ID,
                "generation": _support.GENERATION_NUMBER,
                "root_issue": _support.ROOT_ISSUE,
                "lineage_depth": _support.LINEAGE_DEPTH,
                "source_sha": _support.CANDIDATE_SHA,
                "base_sha": _support.BASE_SHA,
                "threshold": _support.THRESHOLD,
                "additions": _support.ADDITIONS,
                "phase": "adjudicating",
                _PUBLICATION: _PRE,
            },
        )

    def test_an_unknown_depth_is_absent_not_a_root(self) -> None:
        # A record may not report a lineage depth the pinned state could not
        # say, least of all the root's 0.
        self.assertNotIn(
            "lineage_depth", _payload(_MEASUREMENT, lineage_depth=None),
        )

    def test_a_family_carries_only_its_extras(self) -> None:
        recorded = _payload(_VERDICT)
        self.assertEqual(recorded["verdict"], str(LateVerdict.SPLIT))
        self.assertEqual(recorded["child_count"], _support.CHILD_COUNT)
        self.assertNotIn("failure", recorded)
        self.assertNotIn("verdict", _payload(_CLEANUP))

    def test_a_resource_is_kind_and_print_only(self) -> None:
        # The ledger's own target -- a ref, a branch, an issue number -- is
        # not something a record may carry, so what identifies it is a
        # bounded digest and the kind beside it.
        recorded = _payload(_CLEANUP)
        self.assertEqual(recorded["resource"], "child")
        self.assertEqual(recorded["outcome"], "reconciled")
        self.assertNotIn(
            _support.FIRST_CHILD.target, str(tuple(recorded.values())),
        )
        self.assertEqual(
            len(recorded["resource_id"]),
            _support.RESOURCE_PRINT_LENGTH,
        )

    def test_a_refused_reading_names_its_step(self) -> None:
        # `measurement_failed` is what every refused reading reaches a sink
        # as, so the member beside it is the whole of what tells a remote
        # that would not answer from a diff nothing here can pin -- and the
        # line is the whole of what says which of the three the remote was.
        # The members that reached no reading at all name neither, and an
        # absent field is dropped by both envelope builders.
        recorded = _payload(_events.measurement_failure_event(
            _support.MEASUREMENT_STEP, _support.FAILURE_DETAIL,
        ))
        unnamed = _payload(_FAILURE)

        self.assertEqual(recorded["failure"], unnamed["failure"])
        self.assertEqual(
            recorded[_MEASUREMENT_FAILURE], str(_support.MEASUREMENT_STEP),
        )
        self.assertEqual(recorded[_DETAIL], _support.FAILURE_DETAIL)
        self.assertFalse(set(unnamed) & {_MEASUREMENT_FAILURE, _DETAIL})

    def test_a_restart_names_its_step_and_predecessor(self) -> None:
        restarting = {
            "restart_pending": True,
            "restart_target": _support.DECOMPOSING,
            "restart_predecessor": _PREDECESSOR,
        }
        payload = _payload(_event_support.family_cases()[-1], **restarting)
        self.assertEqual(payload["restart_step"], "pending")
        self.assertEqual(payload["restart_target"], _support.DECOMPOSING)
        self.assertEqual(payload["predecessor_cycle_id"], _PREDECESSOR)


class PublicationRecordTest(unittest.TestCase):
    """Which side of publication a record was entered on, and on what."""

    def test_every_family_says_where_it_was_entered(self) -> None:
        # The answer is correlation rather than one family's own detail: a
        # cleanup reconciling a snapshot of an initial publication and one
        # reconciling a pull request the remote already carries are the same
        # family describing two different steps.
        for event in _event_support.family_cases():
            with self.subTest(family=str(event.family)):
                self.assertEqual(_payload(event)[_PUBLICATION], _PRE)

    def test_an_overflow_names_what_it_was_entered_on(self) -> None:
        recorded = _payload(_MEASUREMENT, **_support.ENTERED_ON_PUBLICATION)
        self.assertEqual(recorded[_PUBLICATION], _POST)
        self.assertEqual(recorded[_SOURCE_STAGE], "in_review")
        self.assertEqual(recorded[_PUBLISHED_PR], _support.PUBLISHED_PR_NUMBER)
        self.assertEqual(recorded[_PUBLISHED_SHA], _support.PUBLISHED_SHA)

    def test_the_source_stage_is_the_envelopes_tag(self) -> None:
        # A filter compares it against the envelope's own `stage`, which every
        # emitter on these sinks records as the bare tag under the label.
        entered = {
            _PUBLICATION: replace(
                _support.PUBLICATION_CONTEXT, source_stage=WorkflowLabel.FIXING,
            ),
        }
        self.assertEqual(
            _payload(_MEASUREMENT, **entered)[_SOURCE_STAGE], "fixing",
        )

    def test_context_travels_only_under_the_marker(self) -> None:
        # A record that reports an initial publication may not also carry a
        # publication's context, however a hand-edited comment got it there.
        unmarked = {
            _PUBLICATION: replace(_support.PUBLICATION_CONTEXT, post_publication=False),
        }
        for named, fields in (("nothing", {}), ("context", unmarked)):
            with self.subTest(carrying=named):
                recorded = _payload(_MEASUREMENT, **fields)

                self.assertEqual(recorded[_PUBLICATION], _PRE)
                self.assertFalse(set(recorded) & set(_CONTEXT_FIELDS))

    def test_an_unnameable_publication_is_refused(self) -> None:
        # None of the three can be recovered from anywhere else, so a marker
        # standing over a missing one -- or over a stage nobody looked up, a
        # pull request nobody can ask about, or a head that is not a commit --
        # would reach both sinks as a publication with no publication in it.
        for field, damaged in _UNNAMEABLE:
            with self.subTest(field=field, damaged=damaged):
                entered = {
                    _PUBLICATION: replace(_support.PUBLICATION_CONTEXT, **{field: damaged}),
                }
                with self.assertRaises(_REFUSED):
                    _payload(_MEASUREMENT, **entered)

    def test_a_pull_requests_own_text_is_not_recorded(self) -> None:
        # A record says WHICH pull request a candidate overflowed, never what
        # that pull request says: the body held through an adjudication is
        # free-form text a human and an agent both write into.
        recorded = _payload(
            _MEASUREMENT,
            **_support.ENTERED_ON_PUBLICATION,
            plan_pr_body=_PROSE,
            scope=_PROSE,
        )

        self.assertLessEqual(set(recorded), set(_records.LATE_PAYLOAD_FIELDS))
        self.assertNotIn(_PROSE, str(tuple(recorded.values())))


class RefusedRecordTest(unittest.TestCase):
    """A generation that cannot satisfy the contract produces no record."""

    def test_a_generation_with_no_identity_is_refused(self) -> None:
        # Nothing could join it to a pinned generation, a lineage, or its own
        # retry, which is the only reason the record exists.
        with self.assertRaises(_REFUSED):
            _records.build_late_payload(_MEASUREMENT, LateGeneration())

    def test_prose_in_a_commit_field_is_refused(self) -> None:
        # Both directions of the same adversary: the fields are typed `str`,
        # so only the format check keeps a sentence -- and the path inside it
        # -- out of a field an analysis reads as a commit.
        for sha_field in ("candidate_sha", "base_sha"):
            with self.subTest(field=sha_field), self.assertRaises(_REFUSED):
                _payload(_MEASUREMENT, **{sha_field: _PROSE})

    def test_a_phase_that_is_not_a_member_is_refused(self) -> None:
        with self.assertRaises(_REFUSED):
            _payload(_MEASUREMENT, phase=_PROSE)

    def test_a_restart_target_outside_the_pair(self) -> None:
        with self.assertRaises(_REFUSED):
            _payload(_MEASUREMENT, restart_target="workflow:done")

    def test_a_count_that_is_not_a_count_is_refused(self) -> None:
        for counted in (True, 2.5, "4000", -1):
            with self.subTest(counted=counted), self.assertRaises(_REFUSED):
                _payload(_MEASUREMENT, threshold=counted)

    def test_a_depth_past_the_bound_is_refused(self) -> None:
        with self.assertRaises(_REFUSED):
            _payload(_MEASUREMENT, lineage_depth=9)

    def test_the_refusal_never_quotes_the_value(self) -> None:
        # A field refused for carrying prose must not put that prose in the
        # log line reporting it -- that is the same leak one level over.
        self.assertNotIn(_PROSE, _refusal(candidate_sha=_PROSE))


class FamilyContextTest(unittest.TestCase):
    """A record is readable without the pinned comment its family answers for."""

    def test_a_sized_family_must_say_what_it_measured(self) -> None:
        # A measurement or the verdict answering it, reporting only an
        # identity, is a row no threshold study can use: which commits were
        # frozen, what they were measured against, and what the measurement
        # was are the record.
        for event, name in _MEASURED_CASES:
            with self.subTest(family=str(event.family), field=name):
                self._assert_refused(event, **{name: None})

    def test_a_reconciling_family_is_not_held_to_it(self) -> None:
        # The other five describe reconciliation rather than size, and a
        # restart's fresh cycle has deliberately let its commits go.
        for event in _event_support.family_cases()[2:]:
            with self.subTest(family=str(event.family)):
                self.assertNotIn(
                    _SOURCE_SHA,
                    _records.build_late_payload(event, _STRIPPED),
                )

    def _assert_refused(self, event, **generation_fields) -> None:
        with self.assertRaises(_REFUSED):
            _records.build_late_payload(
                event, _support.measured_generation(**generation_fields),
            )


class TransferRecordTest(unittest.TestCase):
    """What one settled transfer says, and what it may not be written over."""

    def test_it_names_both_pairs_and_the_proof(self) -> None:
        # The pair the verdict moved ONTO is the generation's own, since that
        # is what a later measurement of the same work joins on; the pair it
        # moved OFF is the family's, because nothing else on a record could
        # name a commit the branch no longer carries.
        recorded = _records.build_late_payload(
            _event_support.transfer_event(), _support.transferred_generation(),
        )

        self.assertEqual(recorded[_SOURCE_SHA], _support.CANDIDATE_SHA)
        self.assertEqual(recorded[_BASE_SHA], _support.BASE_SHA)
        self.assertEqual(
            recorded["transferred_from_sha"], _support.TRANSFERRED_FROM_SHA,
        )
        self.assertEqual(
            recorded["transferred_from_base_sha"],
            _support.TRANSFERRED_FROM_BASE_SHA,
        )
        self.assertEqual(recorded["rewrite_kind"], "squash")
        self.assertEqual(recorded["transfer_proof"], "pushed")

    def test_it_names_the_publication_it_happened_on(self) -> None:
        recorded = _records.build_late_payload(
            _event_support.transfer_event(), _support.transferred_generation(),
        )

        self.assertEqual(recorded[_PUBLICATION], _POST)
        self.assertEqual(recorded[_SOURCE_STAGE], "in_review")
        self.assertEqual(recorded[_PUBLISHED_PR], _support.PUBLISHED_PR_NUMBER)

    def test_an_unattributable_move_is_refused(self) -> None:
        # A verdict moves only onto a commit a pull request the remote already
        # carries has been pushed to, so a transfer that cannot name that pull
        # request is a move nothing could be attributed to.
        unattributable = (
            {"post_publication": False},
            {_PUBLISHED_PR: None},
            {_PUBLISHED_SHA: ""},
        )
        for fields in unattributable:
            with self.subTest(**fields), self.assertRaises(_REFUSED):
                _records.build_late_payload(
                    _event_support.transfer_event(),
                    _support.transferred_generation(
                        publication=replace(_support.PUBLICATION_CONTEXT, **fields),
                    ),
                )

    def test_it_is_still_held_to_the_commits(self) -> None:
        for name in ("candidate_sha", _BASE_SHA):
            with self.subTest(field=name), self.assertRaises(_REFUSED):
                _records.build_late_payload(
                    _event_support.transfer_event(),
                    _support.transferred_generation(**{name: ""}),
                )


if __name__ == "__main__":
    unittest.main()
