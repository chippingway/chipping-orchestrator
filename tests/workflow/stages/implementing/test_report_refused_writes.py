# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A record or binding that did not land leaves the comment as another road wrote it, for the whole tick.

The report's record and its binding are guarded commits decided on the comment
the tick read. Another road writing a newer report record and verification
evidence while the developer runs, or while the push is out, refuses them --
and every whole-state write the implementing handler takes behind the refusal
writes nothing, so neither record is put back the way the tick read it. A
record GitHub took and never confirmed is no different for that tick, and the
next one publishes it at the run's own revision with no developer run. Nor is a
binding that did not land over an older transaction the delivery supersedes:
the handoff stops behind it, so no park is announced over a debt it replaces.
"""

from __future__ import annotations

import unittest
from types import MappingProxyType
from unittest.mock import MagicMock, patch

from orchestrator.github.developer_reports import content_digest
from orchestrator.github.pull_request_reports import ReportLocation
from orchestrator.workflow.engine import report_record_state as _record_state, report_records as _records
from orchestrator.workflow.state import WorkflowLabel
from tests.support.fakes import FakePRRef
from tests.workflow.engine import report_commit_test_support as commit_support
from tests.workflow.fixtures import LABEL_VALIDATING, _agent, _named_description, _open_pr_for
from tests.workflow.stages.implementing import report_test_support as support

PUSH_BRANCH = "_push_branch"

AWAITING_HUMAN = "awaiting_human"

RUN_AGENT = "run_agent"

# The pull request the next tick opens: this client numbers them from 1.
OPENED_PR = 1

READ_PINNED_STATE = "read_pinned_state"

# What another road writes meanwhile: verification evidence, and a report
# record the tick's decision rests on -- a newer delivery while the run is out,
# and a settled report while the push is.
_EVIDENCE = MappingProxyType({"verification_evidence_current": {"revision": 3}})

_NEWER_DELIVERY = MappingProxyType({
    _records.DELIVERED_REPORT: {"receipt": "issue-1-report-9", "revision": 9},
})

_SETTLED_SINCE = MappingProxyType({_records.CURRENT_REPORT: {"revision": 9}})

# The pull request already open on the branch, and the comment on it an older
# verification of this issue named, which nobody can find there any more.
_REUSED_PR = 4400

_VANISHED_REPORT_ID = 9400

_VANISHED_REPORT = "An earlier report a human verified, since deleted."

# The revision a report the run writes over that older transaction goes out at.
_SUPERSEDING_REVISION = 2


class RefusedWritesTest(unittest.TestCase, support._ReportDeliveryMixin):
    """What the handler leaves behind a record or a binding its comment refused."""

    def test_a_refused_record_writes_nothing(self) -> None:
        # The other road writes while the developer is out, so the record
        # minted past the comment the tick read is refused: nothing is pushed,
        # and the comment ends the tick exactly as that road left it.
        github, issue = self.seeded()
        written = {**_NEWER_DELIVERY, **_EVIDENCE}
        finished = _agent(session_id=support.DEV_SESSION, last_message=support.ready_message())

        mocks = self._run_implementing(
            github, issue,
            run_agent=MagicMock(side_effect=_Beside(github, issue, written, finished)),
            has_new_commits=[False, True], dirty_files=(), push_branch=True,
        )

        mocks[PUSH_BRANCH].assert_not_called()
        _assert_left_as(self, github, written)

    def test_a_refused_binding_writes_nothing(self) -> None:
        # The other road writes while the push is out, so the binding decided
        # on the comment the tick read is refused: no report is posted, and the
        # comment ends the tick exactly as that road left it.
        github, issue = self.seeded()
        written = {**_SETTLED_SINCE, **_EVIDENCE}
        reads = _ReadsBehindThePush(github, issue, written)
        pushes = MagicMock(side_effect=reads.arms)

        with patch.object(github, READ_PINNED_STATE, reads):
            self.deliver(github, issue, support.ready_message(), push_branch=pushes)

        self.assertEqual(support.published_reports(github, 1), [])
        _assert_left_as(self, github, written)

    def test_a_lost_answer_is_published_next_tick(self) -> None:
        # GitHub took the record and its answer never came back, and another
        # road settles evidence right behind the edit. The tick pushes nothing
        # and writes nothing behind it, so the evidence stays; the next tick
        # finds the record, spawns nothing, and publishes the commit under it
        # -- one pull request, one report, at the run's own revision.
        github, issue = self.seeded()
        github.seed_state(
            support.REPORT_ISSUE, **github.pinned_data(support.REPORT_ISSUE),
            dev_agent="claude", dev_session_id=support.DEV_SESSION,
        )
        github.pinned_failures.lost.add(support.REPORT_ISSUE)
        with commit_support.behind(github, issue, commit_support.EDIT, **_EVIDENCE):
            first = self.deliver(github, issue, support.ready_message())
        github.pinned_failures.lost.discard(support.REPORT_ISSUE)
        first[PUSH_BRANCH].assert_not_called()
        _assert_left_as(self, github, dict(_EVIDENCE))

        mocks = self.republish(github, issue)

        mocks[RUN_AGENT].assert_not_called()
        _assert_left_as(self, github, dict(_EVIDENCE))
        self.assertEqual(
            (len(github.opened_prs), len(support.published_reports(github, OPENED_PR))),
            (1, 1),
        )
        self.assertIn((support.REPORT_ISSUE, LABEL_VALIDATING), github.label_history)


class SupersededTransactionTest(unittest.TestCase, support._ReportDeliveryMixin):
    """A binding that did not land, over an older transaction its delivery supersedes."""

    def test_an_unlanded_binding_parks_nothing(self) -> None:
        # The issue still owes an older verification on the pull request this
        # tick pushes to, at a location nobody can find any more: a debt no
        # retry pays, which the handoff parks once it reads the report. The
        # run's binding would have superseded it, but it did not land --
        # refused over a comment another road moved behind the push, or sent
        # and never confirmed. The handoff stops right behind it: no notice
        # about the older transaction, no park, no handoff, and the other
        # road's fields stand. Where the binding did land, the next tick
        # publishes it once, at the run's own revision, with no developer run.
        for written in ({**_SETTLED_SINCE, **_EVIDENCE}, {}):
            with self.subTest(refused=bool(written)):
                github, issue = self._owing_an_older_verification()
                said = len(github.posted_comments)

                self._delivers_unbound(github, issue, written)

                self.assertEqual(
                    (
                        len(github.posted_comments),
                        github.pinned_data(support.REPORT_ISSUE).get(AWAITING_HUMAN),
                        support.published_reports(github, _REUSED_PR, _SUPERSEDING_REVISION),
                        github.label_history,
                    ),
                    (said, None, [], []),
                )
                _assert_left_as(self, github, written)
                if not written:
                    self._assert_published_next_tick(github, issue)

    def _owing_an_older_verification(self):
        """An issue owing a verification on the pull request open on its branch, whose comment is gone."""
        github, issue = self.seeded()
        github.existing_open_pr[support.BRANCH] = _open_pr_for(
            github, issue_number=support.REPORT_ISSUE, pr_number=_REUSED_PR,
            body=_named_description(support.REPORT_ISSUE, support.DEV_SESSION),
        )
        reading = github.read_pinned_state(issue)
        _record_state.record_pending_report(reading, _records.PendingReport(
            receipt=f"issue-{support.REPORT_ISSUE}-report-1",
            subject=_records.ReportSubject(
                repo_slug=github.repo_slug,
                pr_number=_REUSED_PR,
                branch=support.BRANCH,
                source_sha=support.PUBLISHED_SHA,
                requirements_revision=support.REQUIREMENTS_REVISION,
            ),
            report_revision=1,
            mode=_records.ReportMode.VERIFY,
            route=WorkflowLabel.IMPLEMENTING,
            location=ReportLocation(pr_number=_REUSED_PR, comment_id=_VANISHED_REPORT_ID),
            content_revision=content_digest(_VANISHED_REPORT),
        ))
        github.write_pinned_state(issue, reading)
        return github, issue

    def _delivers_unbound(self, github, issue, written: dict) -> None:
        """One tick whose binding another road's `written` refuses -- or, with nothing written, goes unconfirmed."""
        reads = _ReadsBehindThePush(github, issue, written)
        pushes = MagicMock(side_effect=reads.arms if written else _Loses(github))
        with patch.object(github, READ_PINNED_STATE, reads):
            self.deliver(github, issue, support.ready_message(), push_branch=pushes)
        github.pinned_failures.lost.discard(support.REPORT_ISSUE)

    def _assert_published_next_tick(self, github, issue) -> None:
        """The next tick publishes the bound report once, at its own revision, and hands it on.

        The pull request stands on the pushed commit by then, which the double
        cannot derive from a push it never made: the next tick reads that head
        to tell a publication that landed from a receipt naming a moved branch.
        """
        reused = github.existing_open_pr[support.BRANCH]
        reused.head = FakePRRef(sha=support.PUBLISHED_SHA, ref=support.BRANCH)
        github.add_pr(reused)
        mocks = self.republish(github, issue)

        mocks[RUN_AGENT].assert_not_called()
        self.assertEqual(
            len(support.published_reports(github, _REUSED_PR, _SUPERSEDING_REVISION)), 1,
        )
        self.assertIn((support.REPORT_ISSUE, LABEL_VALIDATING), github.label_history)


def _assert_left_as(case: unittest.TestCase, github, written: dict) -> None:
    """The comment carries what the other road wrote, field for field."""
    pinned = github.pinned_data(support.REPORT_ISSUE)
    case.assertEqual({field: pinned.get(field) for field in written}, written)


class _ReadsBehindThePush:
    """The pinned reads a tick makes, the first one after its push taken behind another road's write."""

    def __init__(self, github, issue, written: dict) -> None:
        self._read = github.read_pinned_state
        self._beside = _Beside(github, issue, written, None)
        self._armed = False

    def __call__(self, issue):
        """Read the comment, behind the other road's write where armed."""
        if self._armed:
            self._armed = False
            self._beside()
        return self._read(issue)

    def arms(self, *_args, **_kwargs) -> bool:
        """Land the push, and arm the next read."""
        self._armed = True
        return True


class _Loses:
    """A push that lands and leaves every pinned-comment edit behind it unanswered."""

    def __init__(self, github) -> None:
        self._github = github

    def __call__(self, *_args, **_kwargs) -> bool:
        """Land the push, and lose the answer to every edit after it."""
        self._github.pinned_failures.lost.add(support.REPORT_ISSUE)
        return True


class _Beside:
    """A request during which another road writes `written` over the pinned comment, once."""

    def __init__(self, github, issue, written: dict, answer) -> None:
        self._github = github
        self._issue = issue
        self._written = written
        self._answer = answer

    def __call__(self, *_args, **_kwargs):
        """Write the other road's fields, then answer as the request would."""
        reading = self._github.read_pinned_state(self._issue)
        reading.data.update(self._written)
        self._github.write_pinned_state(self._issue, reading)
        return self._answer


if __name__ == "__main__":
    unittest.main()
