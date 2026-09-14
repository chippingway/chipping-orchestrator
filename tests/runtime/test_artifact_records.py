# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What one candidate's cleanup record says, and what it may never carry.

One record per candidate the pass decided about -- not one per branch, one per
checkout, or one per deletion step -- so a reader counting them is counting
finished issues considered. The fields are three closed vocabularies and, only
where the reason is about one, a branch this repository itself publishes the
issue under; a checkout path, an issue reference, and a name belonging to some
other spec on a shared clone are all dropped rather than published. Which kind
of artifact a reason is about is what decides that, since the kinds are one
string on a host whose `WORKTREES_DIR` is `orchestrator`: a reason spelled only
on a branch keeps its branch there, one never spelled on a branch publishes
none, and the ones spelled on both drop a subject that is both.

What a sink cannot take is the other half, and it is answered on two levels.
The writer below is silent when it is turned off and reports a filesystem that
refused the line on its own channel; what reaches this owner is a record it
could not build, and that costs one line and leaves every candidate behind it
with its own.
"""
from __future__ import annotations

import logging
import unittest
from pathlib import Path
from types import MappingProxyType
from typing import NamedTuple
from unittest.mock import patch

from orchestrator.config import RepoSpec
from orchestrator.git.worktrees import discovery, maintenance, naming as _naming
from orchestrator.git.worktrees.models import (
    CandidateLayout,
    IssueArtifacts,
    MaintenanceCandidate,
    MaintenanceReason,
    MaintenanceResult,
)
from orchestrator.runtime import artifact_records, artifacts
from tests.runtime import (
    artifact_test_support as _artifacts,
    polling_test_support as _support,
)

_APPEND = "orchestrator.observability.analytics.recording.append_record"
_EVENT = "terminal_artifact_cleanup"
_ENVELOPE = ("event", "issue", "repo", "ts")
_TIMESTAMP_KEY = "ts"
_REPO_KEY = "repo"
_ISSUE_KEY = "issue"
_OUTCOME_KEY = "outcome"
_RETAINED = "retained"
_ISSUE_NUMBER = _artifacts.ALPHA_ISSUE_NUMBER
_SPEC = RepoSpec(
    slug=_support.ALPHA_REPO, target_root=Path("/tmp"), base_branch="main",
)
_OTHER_SPEC = RepoSpec(
    slug=_support.BETA_REPO, target_root=Path("/tmp"), base_branch="main",
)
_BRANCH, _LEGACY_BRANCH = _naming._issue_branch_names(_SPEC, _ISSUE_NUMBER)
# What a subject can be that is not this candidate's branch: the checkout the
# reason is about, the issue itself, and the name another spec sharing this
# clone publishes its own issue 41 under.
_CHECKOUT = "/srv/worktrees/alpha-one/issue-41"
_ISSUE_SUBJECT = f"#{_ISSUE_NUMBER}"
_FOREIGN_BRANCH = _naming._branch_name(_OTHER_SPEC, _ISSUE_NUMBER)
_REFUSED_LOG = "was not written"
_UNSERIALIZABLE = "the record could not be built"
_ANALYTICS_LOGGER = "orchestrator.analytics"
_SINK_KNOB = "orchestrator.observability.analytics.settings.ANALYTICS_LOG_PATH"
# A sink path whose parent is a regular file -- this module -- which is what a
# misconfigured `ANALYTICS_LOG_PATH` looks like from the writer's side: the
# `mkdir` in front of the append raises `NotADirectoryError` and nothing is
# ever created.
_UNWRITABLE_SINK = Path(__file__) / "not-a-directory" / "analytics.jsonl"
# The checkout paths of a host whose `WORKTREES_DIR` is `orchestrator`, where
# each of this issue's checkouts is spelled exactly like one of its branches:
# `orchestrator/<slug>/issue-<n>` is what that configuration derives for both.
_COLLIDING_CHECKOUT = Path(_BRANCH)
_COLLIDING_LEGACY_CHECKOUT = Path(_LEGACY_BRANCH)

# Which branches a candidate published under each layout is holding, so a case
# describes a host the discovery could really have found: an issue in flight
# when namespacing landed carries both names at once.
_LAYOUT_BRANCHES = MappingProxyType({
    CandidateLayout.CURRENT: (_BRANCH,),
    CandidateLayout.LEGACY: (_LEGACY_BRANCH,),
    CandidateLayout.MIXED: (_BRANCH, _LEGACY_BRANCH),
    CandidateLayout.REMOTE_ONLY: (_BRANCH,),
})


class _Case(NamedTuple):
    """One answer the pass gives, and the whole record it earns."""

    answer: MaintenanceResult
    expected: dict


def _case(
    reason: MaintenanceReason,
    *,
    layout: CandidateLayout = CandidateLayout.CURRENT,
    subject: str = "",
    branch: str | None = None,
    worktrees: tuple[Path, ...] = (),
) -> _Case:
    """One candidate's answer beside the record it is expected to produce.

    The branch is stated rather than derived from the subject, so a case
    asserts what may be published instead of re-running the rule that decides
    it.
    """
    answer = MaintenanceResult(
        candidate=MaintenanceCandidate(
            artifacts=IssueArtifacts(
                spec=_SPEC,
                issue_number=_ISSUE_NUMBER,
                worktrees=worktrees,
                branches=_LAYOUT_BRANCHES[layout],
            ),
            layout=layout,
        ),
        outcome=maintenance._OUTCOMES[reason],
        reason=reason,
        subject=subject,
    )
    expected = {
        _REPO_KEY: _support.ALPHA_REPO,
        _ISSUE_KEY: _ISSUE_NUMBER,
        "event": _EVENT,
        _OUTCOME_KEY: str(answer.outcome),
        "reason": str(reason),
        "layout": str(layout),
    }
    if branch is not None:
        expected["branch"] = branch
    return _Case(answer, expected)


# Every shape a pass answers with: the three outcomes, the four layouts an
# artifact can have been published under -- both at once included -- and the
# three subjects that are not a branch this record may name.
_CASES = (
    _case(MaintenanceReason.RECLAIMED),
    _case(
        MaintenanceReason.UNPROVEN,
        layout=CandidateLayout.LEGACY,
        subject=_LEGACY_BRANCH,
        branch=_LEGACY_BRANCH,
    ),
    _case(
        MaintenanceReason.REMOTE_DELETE_FAILED,
        subject=_BRANCH,
        branch=_BRANCH,
    ),
    _case(
        MaintenanceReason.BRANCH_CHECKED_OUT,
        layout=CandidateLayout.MIXED,
        subject=_LEGACY_BRANCH,
        branch=_LEGACY_BRANCH,
    ),
    _case(
        MaintenanceReason.TIP_MOVED,
        layout=CandidateLayout.REMOTE_ONLY,
        subject=_BRANCH,
        branch=_BRANCH,
    ),
    _case(MaintenanceReason.WORKTREE_REMOVAL_FAILED, subject=_CHECKOUT),
    _case(MaintenanceReason.ACTIVE_CLAIM, subject=_ISSUE_SUBJECT),
    _case(MaintenanceReason.UNPROVEN, subject=_FOREIGN_BRANCH),
)

# Every shape on a host whose checkout paths are spelled exactly like its
# branches, and what each may still say. The two reasons that are only ever
# about a tree name no branch; the two that can be about either fail closed on
# a name that is both, since nothing there says which artifact is meant.
_COLLIDING_CASES = (
    _case(
        MaintenanceReason.WORKTREE_REMOVAL_FAILED,
        subject=_BRANCH,
        worktrees=(_COLLIDING_CHECKOUT,),
    ),
    _case(
        MaintenanceReason.RECENT_ACTIVITY,
        layout=CandidateLayout.LEGACY,
        subject=_LEGACY_BRANCH,
        worktrees=(_COLLIDING_LEGACY_CHECKOUT,),
    ),
    _case(
        MaintenanceReason.TIP_MOVED,
        layout=CandidateLayout.MIXED,
        subject=_LEGACY_BRANCH,
        worktrees=(_COLLIDING_CHECKOUT, _COLLIDING_LEGACY_CHECKOUT),
    ),
    _case(
        MaintenanceReason.UNPROVEN,
        subject=_BRANCH,
        worktrees=(_COLLIDING_CHECKOUT,),
    ),
    # The three the pass spells on a branch and nowhere else. Each names the
    # branch it was taking however this host spells its checkouts, so the
    # collision above may not cost an operator the one artifact a refused
    # teardown is about.
    _case(
        MaintenanceReason.REMOTE_DELETE_FAILED,
        subject=_BRANCH,
        branch=_BRANCH,
        worktrees=(_COLLIDING_CHECKOUT,),
    ),
    _case(
        MaintenanceReason.LOCAL_DELETE_FAILED,
        layout=CandidateLayout.MIXED,
        subject=_LEGACY_BRANCH,
        branch=_LEGACY_BRANCH,
        worktrees=(_COLLIDING_CHECKOUT, _COLLIDING_LEGACY_CHECKOUT),
    ),
    _case(
        MaintenanceReason.BRANCH_CHECKED_OUT,
        subject=_BRANCH,
        branch=_BRANCH,
        worktrees=(_COLLIDING_CHECKOUT,),
    ),
    # A candidate holding a checkout that collides with nothing: an ambiguous
    # reason still publishes the branch it names, so the rule above costs the
    # ordinary host nothing.
    _case(
        MaintenanceReason.TIP_UNREADABLE,
        subject=_BRANCH,
        branch=_BRANCH,
        worktrees=(Path(_CHECKOUT),),
    ),
)


def _records(answers) -> list[dict]:
    """Every record a run over these answers handed the sink."""
    with patch(_APPEND) as appended:
        artifact_records.record_cleanup_results(answers)
        return [call.args[0] for call in appended.call_args_list]


def _reported(record: dict) -> tuple:
    """Which candidate a record is about, and what the pass decided."""
    return (record[_REPO_KEY], record[_ISSUE_KEY], record[_OUTCOME_KEY])


class CleanupRecordTest(unittest.TestCase):
    """Each candidate earns one record, in the vocabulary the pass answers in."""

    def test_one_record_per_candidate_shape(self) -> None:
        self._reports(_CASES)

    def test_a_colliding_checkout_is_read_by_reason(self) -> None:
        # Which artifact a reason is about is settled from the reason, not
        # from the text: `WORKTREES_DIR=orchestrator` makes a checkout path
        # and its issue's branch the same string. A removal git refused would
        # otherwise be published as a branch nothing touched -- and a delete
        # the remote refused, which is only ever about a branch, would lose
        # the one artifact its operator has to go and look at.
        self._reports(_COLLIDING_CASES)

    def test_every_branch_reason_is_a_member(self) -> None:
        # The two families are spelled by hand against the pass's own
        # vocabulary, so a reason renamed or dropped there has to be answered
        # here. A reason in neither publishes no branch, which is the safe
        # default; one listed that no longer exists is a rule about nothing.
        # A reason in both would be read as unambiguous and ambiguous at once.
        named = artifact_records._BRANCH_REASONS
        either = artifact_records._EITHER_REASONS
        self.assertEqual(
            ((named | either) - set(MaintenanceReason), named & either),
            (set(), set()),
        )

    def test_a_record_carries_the_declared_fields(self) -> None:
        # The whole of what a sink may be told about a teardown: the envelope,
        # and the four fields this owner declares. What a pass read on the way
        # -- a command, its output, what a tree held -- is not on the list and
        # cannot arrive by being passed along.
        written = _records([_CASES[2].answer])
        self.assertEqual(
            tuple(sorted(written[0])),
            tuple(sorted(
                _ENVELOPE + artifact_records.CLEANUP_PAYLOAD_FIELDS,
            )),
        )

    def _reports(self, cases: tuple[_Case, ...]) -> None:
        """Every case in a table earns exactly the record it declares."""
        written = _records([case.answer for case in cases])

        self.assertEqual(len(written), len(cases))
        for record, case in zip(written, cases, strict=True):
            with self.subTest(reason=case.expected["reason"]):
                record.pop(_TIMESTAMP_KEY)
                self.assertEqual(record, case.expected)


class RefusedRecordTest(unittest.TestCase):
    """A record nobody can write costs that line and nothing else."""

    def test_a_refused_record_keeps_recording(self) -> None:
        # What a record this owner cannot build or serialize does to a pass
        # that has already deleted: nothing. Every candidate is still
        # attempted, so a failure on the first does not take the records of
        # the ones behind it with it.
        answers = [case.answer for case in _CASES[:3]]
        with (
            patch(_APPEND, side_effect=RuntimeError(_UNSERIALIZABLE)) as sink,
            self.assertLogs(
                _artifacts.LIFECYCLE_LOGGER, level=logging.WARNING,
            ) as logs,
        ):
            artifact_records.record_cleanup_results(answers)

            self.assertEqual(sink.call_count, len(answers))
            self.assertEqual(len(logs.output), len(answers))
            # The refusal names the candidate and the failure's type, and
            # repeats neither the exception's own words nor the record it was
            # refused for.
            self.assertNotIn(_UNSERIALIZABLE, "".join(logs.output))
            self.assertTrue(all(
                _REFUSED_LOG in said for said in logs.output
            ))

    def test_a_field_outside_its_vocabulary_is_lost(self) -> None:
        # A lookalike string is not a member, and a record built from one
        # would publish a value nothing in this package names. Refused whole
        # rather than written with the field dropped: the outcome is what a
        # count of what the host did is taken from.
        with (
            patch(_APPEND) as sink,
            self.assertLogs(
                _artifacts.LIFECYCLE_LOGGER, level=logging.WARNING,
            ) as logs,
        ):
            artifact_records.record_cleanup_results([
                MaintenanceResult(
                    candidate=_CASES[0].answer.candidate,
                    outcome=_RETAINED,
                    reason=MaintenanceReason.RECLAIMED,
                ),
            ])

            sink.assert_not_called()
            self.assertIn(_REFUSED_LOG, logs.output[0])
            self.assertIn(_ISSUE_SUBJECT, logs.output[0])

    def test_a_sink_turned_off_says_nothing(self) -> None:
        # The knob set to off is not a failure and not this owner's to report:
        # the shared writer short-circuits before it opens anything, so there
        # is no record, no file, and nothing on this channel.
        with self.assertNoLogs(_artifacts.LIFECYCLE_LOGGER):
            artifact_records.record_cleanup_results(
                [case.answer for case in _CASES[:3]],
            )

    def test_a_refused_write_is_the_sinks_own(self) -> None:
        # A path the filesystem will not take -- a read-only mount, a full
        # disk, a misconfigured knob -- is caught where the line is written
        # and reported once per append on the analytics channel. It never
        # reaches this owner, so the lifecycle channel stays quiet and no
        # record is lost twice over.
        answers = [case.answer for case in _CASES[:2]]
        with (
            patch(_SINK_KNOB, _UNWRITABLE_SINK),
            self.assertLogs(_ANALYTICS_LOGGER, level=logging.WARNING) as logs,
            self.assertNoLogs(_artifacts.LIFECYCLE_LOGGER),
        ):
            artifact_records.record_cleanup_results(answers)

            self.assertEqual(len(logs.output), len(answers))
            self.assertFalse(_UNWRITABLE_SINK.exists())


class PassRecordTest(_artifacts._MaintenanceTestCase):
    """The pass records every candidate it decided about, and only those."""

    def test_each_decided_candidate_is_recorded(self) -> None:
        with (
            patch.object(
                discovery,
                _artifacts.CANDIDATES_ATTR,
                return_value=self._discovered(_ISSUE_NUMBER),
            ),
            patch.object(
                maintenance,
                _artifacts.MAINTAINED_ATTR,
                side_effect=self.recorded,
            ),
            patch(_APPEND) as appended,
        ):
            artifacts.run_maintenance_pass(
                self.state(), self.clients, self.scheduler,
            )

            # One record each, whatever the pass decided: a candidate it kept
            # is exactly the one an operator has to settle by hand, and it is
            # invisible in a count of what was cleaned.
            self.assertEqual(
                [_reported(call.args[0]) for call in appended.call_args_list],
                [
                    (_support.ALPHA_REPO, _ISSUE_NUMBER, _RETAINED),
                    (_support.BETA_REPO, _ISSUE_NUMBER, _RETAINED),
                ],
            )

    def test_an_unreached_candidate_has_no_record(self) -> None:
        state = self.state()
        with (
            patch.object(
                discovery,
                _artifacts.CANDIDATES_ATTR,
                return_value=self._discovered(_ISSUE_NUMBER),
            ),
            patch.object(
                maintenance,
                _artifacts.MAINTAINED_ATTR,
                side_effect=_artifacts.StoppingPass(state),
            ),
            patch(_APPEND) as appended,
        ):
            artifacts.run_maintenance_pass(state, self.clients, self.scheduler)

            # An interrupted pass answers for the prefix it reached, and the
            # records say the same: the rest are found again next interval.
            self.assertEqual(
                [call.args[0][_REPO_KEY] for call in appended.call_args_list],
                [_support.ALPHA_REPO],
            )

    def _discovered(self, issue_number: int):
        """One candidate per configured repository, as the scan reports them."""
        return _artifacts.scan([
            _artifacts.candidate(spec, issue_number) for spec in self.specs
        ])


if __name__ == "__main__":
    unittest.main()
