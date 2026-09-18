# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a discussion park reports beside its reason, and how often it says it.

Every ending of this stage is a park, so the reason alone says what happened
without saying whose turn produced it: the same reason is reached by a tick
opening the conversation and by one answering the humans in it. The road is
what tells those apart, and the session is what ties the record to the
conversation it belongs to.

Each case drives one tick with the audit sink OFF and the analytics sink ON --
the install an operator counting human waits actually runs -- and reads the
analytics line back, because that is the surface the correlation is for. The
artifact identifiers are the other half, and what makes them worth reporting is
that this stage will only ever call its own its own: a pull request number the
issue merely arrived carrying is nobody's plan, a publication that began and did
not finish has its commit written down before it parks, and a commit left
standing by a plan this issue has already been past is not the one a park in
flight is about.
"""

from __future__ import annotations

import contextlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from orchestrator import config
from orchestrator.workflow.engine import guards as _guards
from tests.workflow.fixtures import (
    EVENT_PARK_AWAITING_HUMAN,
    KEY_AWAITING_HUMAN,
    STAGE_DISCUSSION,
    _agent,
    _analytics_records,
)
from tests.workflow.stages.discussion import discussion_test_support as _support
from tests.workflow.stages.discussion.discussion_resume_test_support import (
    DISCUSSION_REPLY,
    UNASKED_ROUND,
    _mark_in_flight,
    _reply,
    _seed_parked_discussion,
)
from tests.workflow.stages.discussion.discussion_test_support import _DiscussionWorkflowMixin

_ANALYTICS_FILE = "analytics.jsonl"
_EVENT_PATH_ATTR = "EVENT_LOG_PATH"
_SINK_PREFIX = "discussion-park-correlation-"
_TREE_PREFIX = "discussion-park-tree-"

_KEY_REASON = "reason"
_KEY_STAGE = "stage"
_KEY_ROUTE = "route"
_KEY_AGENT_ROLE = "agent_role"
_KEY_SESSION_ID = "session_id"
_KEY_PR_NUMBER = "pr_number"
_KEY_SHA = "sha"

# The vocabulary spelled independently of the owner, because these values go
# into two durable sinks: a rename is a change to what an operator's saved
# query matches, not a refactor.
_ROUTE_ROUND = "discussion_round"
_ROUTE_RESUME = "discussion_resume"
_DECOMPOSER_ROLE = "decomposer"

# The envelope every analytics record carries on top of its own extras.
_ENVELOPE = frozenset((
    "ts", "repo", "issue", "event", _KEY_STAGE, _KEY_REASON,
))

_OPENING_ISSUE_NUMBER = 1300
_RESUMED_ISSUE_NUMBER = 1301
_PUBLISHED_ISSUE_NUMBER = 1302
_STRANDED_ISSUE_NUMBER = 1303
_PROSE_ISSUE_NUMBER = 1304
_QUIET_ISSUE_NUMBER = 1305
_INHERITED_PR_ISSUE_NUMBER = 1306
_PUSH_FAILED_ISSUE_NUMBER = 1307
_STALE_ISSUE_NUMBER = 1308
_STALE_PLAN_ISSUE_NUMBER = 1309

_AGENT_STDERR = "Traceback: the backend died halfway through the stream"
_CONFIRMED = "confirmed -- writing it up"
_PLAN_SUBJECT = "docs: write down the sink schema decision"
# The pull request an issue relabeled here from a PR stage arrives carrying:
# its developer's, on a branch this conversation is being held on top of.
_INHERITED_PR_NUMBER = 4242
# What a recovery tick reads twice off a checkout whose round is long over.
_RECOVERED_HEAD = (_support.HEAD_AFTER_COMMIT,) * 2
# The commit a plan this issue has ALREADY been past was published on. The
# implementing handoff retires the plan path and keeps this, so it is still
# pinned when a relabel back here opens another round.
_PREVIOUS_PLAN_SHA = "the-commit-the-last-plan-pr-was-merged-from"


def _flattened(record: dict) -> str:
    """Everything the record actually wrote, as one string to search."""
    return " ".join(str(written) for written in record.values())


class _DiscussionParkRecordCase(unittest.TestCase, _DiscussionWorkflowMixin):
    """Drives discussion ticks against a live analytics sink."""

    @contextlib.contextmanager
    def _analytics_sink(self):
        """A sink the ticks inside write to, with the audit sink switched off.

        The audit sink being off is what shows the fan-out is not riding the
        JSONL trace: an operator who keeps the counts without the transcript
        still gets the park.
        """
        with tempfile.TemporaryDirectory(prefix=_SINK_PREFIX) as sink_dir:
            with patch.object(config, _EVENT_PATH_ATTR, None):
                yield Path(sink_dir, _ANALYTICS_FILE)
            self.assertLessEqual(
                {written.name for written in Path(sink_dir).iterdir()},
                {_ANALYTICS_FILE},
            )

    def _park_records(
        self, gh, issue, *, worktree: Path | None = None, **run_options,
    ) -> list[dict]:
        """The park records one tick wrote, optionally against a real tree.

        A checkout on disk is what the parks taken BEFORE a round need: those
        read the tree to decide, and a path nothing holds reads as a first-ever
        tick with nothing in the way.
        """
        with self._analytics_sink() as log_file:
            run_options["analytics_log_path"] = log_file
            if worktree is None:
                self._run_discussion(gh, issue, **run_options)
            else:
                self._run_discussion_on_worktree(
                    gh, issue, worktree, **run_options,
                )
            records = _analytics_records(
                log_file, event=EVENT_PARK_AWAITING_HUMAN,
            )
        return records

    def _only_park(self, gh, issue, **run_options) -> dict:
        records = self._park_records(gh, issue, **run_options)
        self.assertEqual(len(records), 1)
        return records[0]

    def _analysis_park(self, gh, issue, **agent_fields) -> dict:
        """The record a round that posted its analysis leaves behind."""
        return self._only_park(
            gh,
            issue,
            run_agent=_agent(
                session_id=_support.DISCUSSION_SESSION,
                last_message=_support.DISCUSSION_RESPONSE,
                **agent_fields,
            ),
        )

    def _failed_push_park(
        self, issue_number: int, *, plan_sha: str = "",
    ) -> dict:
        """The record a round whose plan could not be pushed leaves behind.

        `plan_sha` seeds the commit a PREVIOUS plan of this issue was
        published on -- the record the implementing handoff keeps when it
        retires the plan path, and the one state in which both of this
        stage's artifact records are pinned at once.
        """
        gh, issue = _support._seed_discussion(issue_number)
        if plan_sha:
            gh.seed_state(issue.number, **{_support.KEY_PLAN_SHA: plan_sha})
        return self._only_park(
            gh,
            issue,
            run_agent=_agent(
                session_id=_support.DISCUSSION_SESSION,
                last_message=_CONFIRMED,
            ),
            head_shas=_support.MOVED_HEAD,
            committed_paths=(self.plan_path(issue_number),),
            push_branch=False,
        )

    def _opening_round_park(
        self, issue_number: int, *, pr_number: int | None = None, **agent_fields,
    ) -> dict:
        """The record an opening round on a fresh issue leaves behind.

        `pr_number` seeds the pull request an issue relabeled here from a PR
        stage arrives carrying, which is the one artifact-shaped thing an
        opening round can find pinned without this stage having recorded it.
        """
        gh, issue = _support._seed_discussion(issue_number)
        if pr_number is not None:
            gh.seed_state(issue.number, pr_number=pr_number)
        return self._analysis_park(gh, issue, **agent_fields)


class DiscussionParkRoadTest(_DiscussionParkRecordCase):
    """Which of the stage's two roads the park it published came off."""

    def test_an_opening_round_records_its_road(self) -> None:
        record = self._opening_round_park(_OPENING_ISSUE_NUMBER)

        self.assertEqual(record[_KEY_STAGE], STAGE_DISCUSSION)
        self.assertEqual(record[_KEY_REASON], _support.PARK_DISCUSSION_RESPONSE)
        self.assertEqual(record[_KEY_ROUTE], _ROUTE_ROUND)
        self.assertEqual(record[_KEY_AGENT_ROLE], _DECOMPOSER_ROLE)
        self.assertEqual(record[_KEY_SESSION_ID], _support.DISCUSSION_SESSION)
        # Nothing has been published, so the artifact fields are absent rather
        # than written as nulls an aggregation would have to special-case.
        self.assertNotIn(_KEY_PR_NUMBER, record)
        self.assertNotIn(_KEY_SHA, record)

    def test_a_reply_records_the_resume_road(self) -> None:
        # The reason is the one an opening round leaves too, so the road is
        # the only thing in the record that tells a conversation being opened
        # from one being answered.
        gh, issue = _seed_parked_discussion(
            _RESUMED_ISSUE_NUMBER, replies=(_reply(DISCUSSION_REPLY),),
        )

        record = self._analysis_park(gh, issue)

        self.assertEqual(record[_KEY_ROUTE], _ROUTE_RESUME)
        self.assertEqual(record[_KEY_SESSION_ID], _support.DISCUSSION_SESSION)

    def test_a_park_before_a_round_has_no_session(self) -> None:
        # The stranded checkout parks without spawning anything, so there is
        # no conversation to name -- and the road it came off is still the
        # record's own answer to which kind of tick took it.
        gh, issue = _support._seed_discussion(_STRANDED_ISSUE_NUMBER)

        with tempfile.TemporaryDirectory(prefix=_TREE_PREFIX) as tree:
            record = self._only_park(
                gh,
                issue,
                worktree=Path(tree),
                run_agent=_agent(last_message=UNASKED_ROUND),
                dirty_files=_support._dirty_files(),
            )

        self.assertEqual(record[_KEY_REASON], _support.PARK_DISCUSSION_STRANDED)
        self.assertEqual(record[_KEY_ROUTE], _ROUTE_ROUND)
        self.assertNotIn(_KEY_SESSION_ID, record)


class DiscussionArtifactRecordTest(_DiscussionParkRecordCase):
    """Which pull request and commit the stage will call this plan's own."""

    def test_a_published_plan_names_pr_and_commit(
        self,
    ) -> None:
        gh, issue = _support._seed_discussion(_PUBLISHED_ISSUE_NUMBER)

        record = self._only_park(
            gh,
            issue,
            run_agent=_agent(
                session_id=_support.DISCUSSION_SESSION,
                last_message=_CONFIRMED,
            ),
            head_shas=_support.MOVED_HEAD,
            committed_paths=(self.plan_path(issue.number),),
            first_commit_subject=_PLAN_SUBJECT,
        )

        self.assertEqual(
            record[_KEY_REASON], _support.PARK_DISCUSSION_PLAN_PUBLISHED,
        )
        self.assertEqual(record[_KEY_PR_NUMBER], gh.opened_prs[0].number)
        # The commit the pull request carries, not whatever the branch is on
        # by the time anything reads it back.
        self.assertEqual(record[_KEY_SHA], _support.HEAD_AFTER_COMMIT)

    def test_an_inherited_pr_is_not_reported(self) -> None:
        # The issue arrived here from a PR stage carrying its developer's
        # number, which this stage refuses to read as a published plan --
        # correlating a park to it would file this conversation's wait under
        # a pull request it never opened.
        record = self._opening_round_park(
            _INHERITED_PR_ISSUE_NUMBER, pr_number=_INHERITED_PR_NUMBER,
        )

        self.assertEqual(record[_KEY_REASON], _support.PARK_DISCUSSION_RESPONSE)
        self.assertNotIn(_KEY_PR_NUMBER, record)

    def test_a_failed_push_names_the_commit_it_kept(self) -> None:
        # The plan is valid and still on the branch; what failed is the push.
        # The commit was pinned durably before that push, so the record names
        # it even though no pull request exists to carry it yet.
        record = self._failed_push_park(_PUSH_FAILED_ISSUE_NUMBER)

        self.assertEqual(
            record[_KEY_REASON], _support.PARK_DISCUSSION_PUSH_FAILED,
        )
        self.assertEqual(record[_KEY_SHA], _support.HEAD_AFTER_COMMIT)
        self.assertNotIn(_KEY_PR_NUMBER, record)

    def test_a_publication_outranks_an_earlier_plan(self) -> None:
        # Both records are pinned: the issue went round to implementing and
        # back, which keeps the old plan's commit while retiring its path, and
        # the new round has a publication in flight. The park asks for the
        # commit IN FLIGHT to be recovered, so that is the one it may name --
        # the settled record would send an operator to a commit whose plan
        # this conversation is already past.
        record = self._failed_push_park(
            _STALE_PLAN_ISSUE_NUMBER, plan_sha=_PREVIOUS_PLAN_SHA,
        )

        self.assertEqual(record[_KEY_SHA], _support.HEAD_AFTER_COMMIT)
        self.assertNotIn(_PREVIOUS_PLAN_SHA, _flattened(record))

    def test_a_stale_publication_names_its_commit(self) -> None:
        # The tick died mid-publication and the branch has moved off the tip
        # it was pushing. Restoring that tip is the remedy the park asks for,
        # so it is the commit the record has to carry.
        gh, issue = _seed_parked_discussion(
            _STALE_ISSUE_NUMBER, replies=(_reply(DISCUSSION_REPLY),),
        )
        _mark_in_flight(
            gh,
            issue.number,
            **{
                _support.KEY_PUBLISHING_SHA: _support.HEAD_BEFORE_ROUND,
                _support.KEY_ROUND_OPEN: True,
            },
        )

        with tempfile.TemporaryDirectory(prefix=_TREE_PREFIX) as tree:
            record = self._only_park(
                gh,
                issue,
                worktree=Path(tree),
                run_agent=_agent(last_message=UNASKED_ROUND),
                head_shas=_RECOVERED_HEAD,
                committed_paths=(self.plan_path(issue.number),),
            )

        self.assertEqual(
            record[_KEY_REASON], _support.PARK_DISCUSSION_STALE_PUBLISH,
        )
        self.assertEqual(record[_KEY_SHA], _support.HEAD_BEFORE_ROUND)


class DiscussionParkPayloadIsBoundedTest(_DiscussionParkRecordCase):
    """No part of what the round said reaches the record."""

    def test_declared_fields_and_no_prose(self) -> None:
        # Both halves of what a round says are seeded, since both are what an
        # operator would otherwise have to redact before reading a sink.
        record = self._opening_round_park(
            _PROSE_ISSUE_NUMBER, stderr=_AGENT_STDERR,
        )

        written = _flattened(record)
        for prose in (_support.DISCUSSION_RESPONSE, _AGENT_STDERR):
            self.assertNotIn(prose, written)
        self.assertEqual(
            set(record) - _ENVELOPE - _guards.ALLOWED_CORRELATION_FIELDS,
            set(),
        )


class DiscussionWaitIsRecordedOnceTest(_DiscussionParkRecordCase):
    """One record per entry into a wait, not per poll of one that stands."""

    def test_an_unchanged_wait_records_nothing(self) -> None:
        gh, issue = _seed_parked_discussion(_QUIET_ISSUE_NUMBER)

        records = self._park_records(
            gh, issue, run_agent=_agent(last_message=UNASKED_ROUND),
        )

        # The issue is still waiting on the reply its park asked for, and the
        # tick that met that wait wrote nothing at all.
        self.assertTrue(gh.pinned_data(issue.number)[KEY_AWAITING_HUMAN])
        self.assertEqual(records, [])


if __name__ == "__main__":
    unittest.main()
