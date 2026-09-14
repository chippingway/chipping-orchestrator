# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""When the round's records reach GitHub, and what happens when they never do.

The spec and the session id are staged on the `PinnedState` the tick read at
the top and are made durable by one write, the same contract every spawning
stage keeps, plus the anchor and the spec that are written before it. Four
things follow and are pinned here: a round costs one write on each side of the
spawn -- beside the pair its own spawn charge takes between them -- the park's
write lands after the comment it records, the spec is the
full configured command string and is already there when the agent is invoked
rather than after it succeeds, and a round that dies before its disposition
leaves that provenance behind -- which is what lets the next tick classify the
commit it may have made instead of adopting it.

The spec case is the one with two ways to be wrong that a default-config test
cannot see. A bare `claude` reads the same whether the stage stored the spec or
just the backend, and a run that hands back a session id reaches the same
pinned state whether the spec was staged before the spawn or after it -- so the
case here configures args and takes a session id away.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from orchestrator import config
from tests.workflow.fixtures import (
    AGENT_RUN_CHARGE_WRITES,
    KEY_PARK_REASON,
    _agent,
)
from tests.workflow.stages.discussion import discussion_test_support as _support
from tests.workflow.stages.discussion.discussion_test_support import _DiscussionWorkflowMixin

_ONE_WRITE_ISSUE_NUMBER = 960
_ORDERING_ISSUE_NUMBER = 961
_SPAWN_FAILURE_ISSUE_NUMBER = 962
_LOCKED_SPEC_ISSUE_NUMBER = 963
_CRASH_RECOVERY_ISSUE_NUMBER = 964
_WRITE_PINNED_STATE = "write_pinned_state"
_READ_PINNED_STATE = "read_pinned_state"
_SPAWN_FAILURE = "the CLI is not installed"
_NO_SESSION_ID = ""


class _WriteRecorder:
    """Record what each `write_pinned_state` carried, and when."""

    def __init__(self, gh) -> None:
        self._gh = gh
        self._write = gh.write_pinned_state
        self.writes: list[tuple[dict, int]] = []

    def __call__(self, issue, state):
        posted_so_far = len(self._gh.posted_comments)
        self.writes.append((dict(state.data), posted_so_far))
        return self._write(issue, state)


class _SpawnObserver:
    """Snapshot the live pinned state at the moment the agent is invoked.

    The handler mutates the one `PinnedState` it read at the top of the tick,
    so holding on to that object and reading it from inside the spawn is what
    tells "staged before the CLI ran" apart from "recorded once it returned".
    """

    def __init__(self, gh, agent_result) -> None:
        self._read = gh.read_pinned_state
        self._agent_result = agent_result
        self._live_state = None
        self.staged_at_spawn: dict = {}

    def read_pinned_state(self, issue):
        self._live_state = self._read(issue)
        return self._live_state

    def run_agent(self, *spawn_args, **spawn_kwargs):
        self.staged_at_spawn = dict(self._live_state.data)
        return self._agent_result


class DiscussionPersistenceTest(unittest.TestCase, _DiscussionWorkflowMixin):

    def test_a_round_costs_one_write_each_side(self) -> None:
        # One write on each side and no more: the provenance a round that
        # never comes back is judged by, then the disposition. The session id
        # belongs to the second, so it never outlives the analysis it points
        # at. Between them sit only the writes the spawn's own charge takes,
        # which carry the provenance forward and nothing of the round.
        gh, issue = _support._seed_discussion(_ONE_WRITE_ISSUE_NUMBER)
        recorder = _WriteRecorder(gh)

        with patch.object(gh, _WRITE_PINNED_STATE, recorder):
            self._run_discussion(
                gh,
                issue,
                run_agent=_agent(
                    session_id=_support.DISCUSSION_SESSION,
                    last_message=_support.DISCUSSION_RESPONSE,
                ),
            )

        # Opened: the provenance, and nothing a park would carry -- which is
        # also what each of the charge's own writes carries forward.
        opened = (config.DECOMPOSE_AGENT_SPEC, _support.HEAD_BEFORE_ROUND, None, None)

        self.assertEqual(len(recorder.writes), 2 + AGENT_RUN_CHARGE_WRITES)
        self.assertEqual(
            [self._written_round(written) for written, _ in recorder.writes],
            [
                opened,
                *(opened for _ in range(AGENT_RUN_CHARGE_WRITES)),
                # Parked: the session it opened and the outcome, over an
                # anchor that stands because the round did not move the branch.
                (
                    config.DECOMPOSE_AGENT_SPEC,
                    _support.HEAD_BEFORE_ROUND,
                    _support.DISCUSSION_SESSION,
                    _support.PARK_DISCUSSION_RESPONSE,
                ),
            ],
        )

    def test_the_write_follows_the_comment_it_records(self) -> None:
        # The park's comment is posted first, so a failure to publish the
        # analysis leaves the issue un-parked and the next tick re-opens the
        # round rather than waiting on a human for a comment nobody can see.
        # The provenance write ahead of it predates the round entirely.
        gh, issue = _support._seed_discussion(_ORDERING_ISSUE_NUMBER)
        recorder = _WriteRecorder(gh)

        with patch.object(gh, _WRITE_PINNED_STATE, recorder):
            self._run_discussion(
                gh,
                issue,
                run_agent=_agent(
                    session_id=_support.DISCUSSION_SESSION,
                    last_message=_support.DISCUSSION_RESPONSE,
                ),
            )

        self.assertEqual(
            [comments_at_write for _, comments_at_write in recorder.writes],
            # The provenance write and the spawn's charge all predate the
            # comment; only the park's write follows it.
            [0 for _ in range(1 + AGENT_RUN_CHARGE_WRITES)] + [1],
        )

    def test_the_full_spec_is_staged_before_the_spawn(self) -> None:
        gh, issue = _support._seed_discussion(_LOCKED_SPEC_ISSUE_NUMBER)
        # An empty session id is the CLI hiccup the pre-spawn pin exists for:
        # the round still lands a park, and the spec has to be in it.
        observer = _SpawnObserver(
            gh,
            _agent(
                session_id=_NO_SESSION_ID, last_message=_support.DISCUSSION_RESPONSE,
            ),
        )

        with _support._configured_spec(
            _support.SPEC_WITH_ARGS, _support.SPEC_BACKEND, _support.SPEC_ARGS,
        ), patch.object(
            gh, _READ_PINNED_STATE, observer.read_pinned_state,
        ):
            self._run_discussion(gh, issue, run_agent=observer.run_agent)

        # Already staged when the CLI was invoked, and the whole command
        # string -- a stage that stored `claude` alone would drop the args
        # every later round of this conversation has to run under.
        self.assertEqual(
            observer.staged_at_spawn.get(_support.KEY_DISCUSSION_AGENT), _support.SPEC_WITH_ARGS,
        )
        pinned_data = gh.pinned_data(issue.number)
        self.assertEqual(pinned_data[_support.KEY_DISCUSSION_AGENT], _support.SPEC_WITH_ARGS)
        # No session id came back, so the round records that it has none --
        # written rather than left out, since a fresh round is a new
        # conversation and any pin it found belongs to a finished one. The
        # spec is pinned anyway, which is the whole point of staging it first.
        self.assertIsNone(pinned_data[_support.KEY_DISCUSSION_SESSION_ID])

    def test_a_crashed_round_leaves_its_provenance(self) -> None:
        # The spawn raising is the exit that reaches no disposition at all, so
        # it is the one the provenance write exists for: the tick dies, and
        # what survives is the record of what the checkout looked like when
        # the round opened. No park, no session, no comment.
        gh, issue = _support._seed_discussion(_SPAWN_FAILURE_ISSUE_NUMBER)

        with self.assertRaises(RuntimeError):
            self._run_discussion(
                gh,
                issue,
                run_agent=self._raise_on_spawn,
            )

        pinned_data = gh.pinned_data(issue.number)
        self.assertEqual(pinned_data[_support.KEY_ROUND_SHA], _support.HEAD_BEFORE_ROUND)
        self.assertEqual(
            pinned_data[_support.KEY_DISCUSSION_AGENT], config.DECOMPOSE_AGENT_SPEC,
        )
        self.assertNotIn(KEY_PARK_REASON, pinned_data)
        self.assertNotIn(_support.KEY_DISCUSSION_SESSION_ID, pinned_data)
        self.assertEqual(gh.posted_comments, [])

    def test_a_crashed_round_s_commit_is_recovered(self) -> None:
        # Two ticks: the round commits and the process dies before it can be
        # assessed, then the next tick reads the anchor back and names the
        # commit instead of opening a round that would inherit it.
        gh, issue = _support._seed_discussion(_CRASH_RECOVERY_ISSUE_NUMBER)

        with tempfile.TemporaryDirectory() as tree:
            with self.assertRaises(RuntimeError):
                self._run_discussion_on_worktree(
                    gh,
                    issue,
                    Path(tree),
                    run_agent=self._raise_on_spawn,
                    head_shas=(_support.HEAD_BEFORE_ROUND,),
                )

            recovery_mocks = self._run_discussion_on_worktree(
                gh,
                issue,
                Path(tree),
                run_agent=_agent(last_message="a round that would inherit it"),
                # Read twice: the tip has moved off the anchor, and the
                # publication check reads what that tip would publish.
                head_shas=(_support.HEAD_AFTER_COMMIT,) * 2,
            )

        recovery_mocks[_support.RUN_AGENT].assert_not_called()
        pinned_data = gh.pinned_data(issue.number)
        self.assertEqual(
            pinned_data[KEY_PARK_REASON], _support.PARK_DISCUSSION_PLAN_INVALID,
        )
        # Reporting the commit does not spend the anchor: it is the tip an
        # operator has to reset back to, and what clears the relabel after.
        self.assertEqual(pinned_data[_support.KEY_ROUND_SHA], _support.HEAD_BEFORE_ROUND)
        self.assertEqual(len(gh.posted_comments), 1)

    def _raise_on_spawn(self, *spawn_args, **spawn_kwargs):
        raise RuntimeError(_SPAWN_FAILURE)

    def _written_round(self, written_state: dict) -> tuple:
        """The four fields that say which side of the spawn a write is on."""
        return (
            written_state.get(_support.KEY_DISCUSSION_AGENT),
            written_state.get(_support.KEY_ROUND_SHA),
            written_state.get(_support.KEY_DISCUSSION_SESSION_ID),
            written_state.get(KEY_PARK_REASON),
        )


if __name__ == "__main__":
    unittest.main()
