# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import json
import unittest
from types import MappingProxyType
from unittest.mock import patch

from orchestrator.github.pinned_state import MAX_PINNED_BODY
from tests.support.fakes import (
    FakeComment,
    FakeGitHubClient,
    FakeUser,
    make_issue,
)
from tests.workflow.fixtures import (
    KEY_AWAITING_HUMAN,
    LABEL_DECOMPOSING,
    LABEL_READY,
    _agent,
    _manifest,
)
from tests.workflow.stages.decomposition import correction_tick_support as _corrected
from tests.workflow.stages.decomposition.decomposing_test_support import (
    _DecomposingWorkflowMixin,
)
from tests.workflow.stages.decomposition.decomposition_test_support import _run_with_logs

KEY_DECOMPOSER_AGENT = "decomposer_agent"
KEY_DECOMPOSER_SESSION_ID = "decomposer_session_id"
KEY_CHILDREN = "children"
KEY_UMBRELLA = "umbrella"
CLEANUP_DECOMPOSE_WORKTREE = "_cleanup_decompose_worktree"
RUN_AGENT = "run_agent"
CONFIG_DECOMPOSE = "DECOMPOSE"
DECOMPOSER_SESSION = "dec-sess"
DEV_SESSION = "dev-sess"
TRUSTED_AUTHOR = "alice"
CREATED_AT = "2026-05-03T00:00:00+00:00"
PICKUP_ISSUE_NUMBER = 10
SINGLE_DECISION_ISSUE_NUMBER = 11
CONTEXT_HANDOFF_ISSUE_NUMBER = 73
SPLIT_DECISION_ISSUE_NUMBER = 12
UMBRELLA_SPLIT_ISSUE_NUMBER = 50
NON_UMBRELLA_SPLIT_ISSUE_NUMBER = 51
DEPENDENCY_SPLIT_ISSUE_NUMBER = 13
COMMITS_PARK_ISSUE_NUMBER = 40
DIRTY_PARK_ISSUE_NUMBER = 41
MALFORMED_MANIFEST_ISSUE_NUMBER = 14
QUESTION_PARK_ISSUE_NUMBER = 15
SILENT_FAILURE_ISSUE_NUMBER = 115
TIMEOUT_ISSUE_NUMBER = 116
RESUME_ISSUE_NUMBER = 16
FILTERED_RESUME_ISSUE_NUMBER = 17
RETRY_CAP_ISSUE_NUMBER = 18
HUMAN_REPLY_COMMENT_ID = 1100
OUTSIDER_REPLY_COMMENT_ID = 1101
PRIOR_ACTION_COMMENT_ID = 900
DISABLED_PICKUP_ISSUE_NUMBER = 19
DISABLED_LABELED_ISSUE_NUMBER = 20
DISABLED_RATCHET_ISSUE_NUMBER = 21
RATCHET_FIRST_COMMENT_ID = 950
RATCHET_LATEST_COMMENT_ID = 960
DISABLED_MONOTONIC_ISSUE_NUMBER = 22
OLDER_COMMENT_ID = 500
PRESERVED_HIGH_WATERMARK = 10000
HALF_COMPLETE_DISABLED_PARENT_NUMBER = 50
RECOVERY_CHILD_NUMBERS = (101, 102)
PERSISTENCE_ISSUE_NUMBER = 80
COMPLETE_RECOVERY_PARENT_NUMBER = 50
AWAITING_RECOVERY_PARENT_NUMBER = 51
AWAITING_RECOVERY_CHILD_NUMBER = 201
PARTIAL_RECOVERY_PARENT_NUMBER = 52
ORPHAN_RECOVERY_PARENT_NUMBER = 53
ORPHAN_REPAIR_PARENT_NUMBER = 60
HEALTHY_CHILD_NUMBER = 601
ORPHAN_CHILD_NUMBER = 602
STALE_PARK_COMMENT_ID = 999
EXPECTED_COUNT_ORDER_ISSUE_NUMBER = 82
CHILD_STATE_ORDER_ISSUE_NUMBER = 83
WORKTREE_ISSUE_NUMBER = 70
DIRTY_WORKTREE_ISSUE_NUMBER = 71
AWAITING_WORKTREE_ISSUE_NUMBER = 73
NON_STRING_RATIONALE_ISSUE_NUMBER = 72
FRESH_USAGE_ISSUE_NUMBER = 620
RESUMED_USAGE_ISSUE_NUMBER = 621
NO_COMMENT_USAGE_ISSUE_NUMBER = 622
INTERRUPTED_USAGE_ISSUE_NUMBER = 623
DIRTY_INTERRUPTED_USAGE_ISSUE_NUMBER = 624

SINGLE_MANIFEST_PAYLOAD = '{"decision": "single", "rationale": "fits"}'
SPLIT_MANIFEST = _manifest(
    '{"decision": "split", "children": ['
    '{"title": "A", "body": "a", "depends_on": []},{"title": "B", "body": "b", "depends_on": []}]}'
)
READ_ONLY_FRAGMENT = "read-only"
IMPLEMENTED_MESSAGE = "implemented"
_PARK_REASON_DIRTY = "decomposer_dirty"
_PARK_REASON_TIMEOUT = "decomposer_timeout"
_PARK_REASON_INVALID = "decomposer_invalid_manifest"
_PARK_REASON_QUESTION = "decomposer_question"
_PARK_REASON_SILENT = "decomposer_silent"
_ROLE_DECOMPOSER = "decomposer"
_EVENT_PARK = "park_awaiting_human"
# Malformed manifest payloads, each beside the reason its park names: one that
# is not JSON, and a split whose second child leaves the prerequisite its body
# names unstated, missing or null.
_MALFORMED_PAYLOADS = MappingProxyType({
    "{not really json": "invalid JSON",
    (
        '{"decision": "split", "umbrella": true, "children": ['
        '{"title": "A", "body": "a", "depends_on": []}, {"title": "B", "body": "needs A"}]}'
    ): "child 1 missing depends_on",
    (
        '{"decision": "split", "umbrella": true, "children": ['
        '{"title": "A", "body": "a", "depends_on": []}, {"title": "B", "body": "needs A", "depends_on": null}]}'
    ): "child 1 depends_on is null",
})
# What a split writes on its parent before it creates the first child.
_SPLIT_TRACKING = ("expected_children_count", "children", "dep_graph", "split_attempt", "umbrella")

# Second invalid answers longer than the pinned comment can hold beside the
# rest of the record, each beside the stretches its held notice keeps: a split
# whose one child depends on itself, behind a rationale this long -- the error
# quoted whole -- and one whose child depends on a value this long, which the
# error spells out -- the error quoted only so far, marked where it runs on.
_LONG = 64000
_LONG_TEXT = "x" * _LONG
_OVERSIZED_ANSWERS = (
    (
        "a long rationale",
        _manifest(json.dumps({
            "decision": "split",
            "rationale": _LONG_TEXT,
            KEY_CHILDREN: [{"title": "A", "body": "a", "depends_on": [0]}],
        })),
        (f"manifest invalid ({_corrected.SELF_EDGE_ERROR}) {_corrected.CORRECTED_PARK}",),
    ),
    (
        "a long dependency",
        _manifest(json.dumps({
            "decision": "split",
            KEY_CHILDREN: [{"title": "A", "body": "a", "depends_on": [f"latest-invalid-dependency-{_LONG_TEXT}"]}],
        })),
        ("manifest invalid (child 0 has invalid dependency 'latest-invalid-", f"...) {_corrected.CORRECTED_PARK}"),
    ),
)

# The client's send of a pinned comment's body, which GitHub refuses past its limit.
_PINNED_SEND = "_send_pinned_edit"


def _too_long(body: str) -> bool:
    """Whether GitHub refuses `body` as longer than one comment."""
    return len(body) > MAX_PINNED_BODY


def _corrected_park(body: str) -> bool:
    """Whether `body` is the park a correction's own invalid answer takes."""
    return _corrected.CORRECTED_PARK in body


class _Refusing:
    """One of the client's requests, refusing each body `refuses` picks -- only the first, where `once` -- as GitHub.

    `refused` keeps the size of every body refused.
    """

    def __init__(self, send, refuses, *, once: bool = False) -> None:
        self._send = send
        self._refuses = refuses
        self._once = once
        self.refused: list[int] = []

    def __call__(self, issue, body: str):
        if self._refuses(body) and not (self._once and self.refused):
            self.refused.append(len(body))
            raise RuntimeError("GitHub refused the request")
        return self._send(issue, body)

    @classmethod
    def patching(cls, github, name: str, refuses, *, once: bool = False):
        """The client's `name` request, so refusing, for the block; and the double counting what it refused."""
        refusing = cls(getattr(github, name), refuses, once=once)
        return patch.object(github, name, side_effect=refusing), refusing


def _assert_resumed_timeout_park_fail_open(
    test_case: HandleDecomposingParkTest,
    retry_count: object,
) -> None:
    gh = FakeGitHubClient()
    issue = make_issue(RESUME_ISSUE_NUMBER, label=LABEL_DECOMPOSING)
    issue.comments.append(
        FakeComment(
            id=HUMAN_REPLY_COMMENT_ID,
            body="please proceed",
            user=FakeUser(TRUSTED_AUTHOR),
        )
    )
    gh.add_issue(issue)
    gh.seed_state(
        RESUME_ISSUE_NUMBER,
        awaiting_human=True,
        last_action_comment_id=PRIOR_ACTION_COMMENT_ID,
        decomposer_agent="claude",
        decomposer_session_id=DECOMPOSER_SESSION,
        retry_count=retry_count,
    )
    test_case._run_decomposing(
        gh,
        issue,
        run_agent=_agent(session_id=DECOMPOSER_SESSION, timed_out=True),
    )
    test_case.assertTrue(gh.pinned_data(RESUME_ISSUE_NUMBER).get(KEY_AWAITING_HUMAN))
    test_case._assert_decomposer_park_event(
        gh, _PARK_REASON_TIMEOUT, expected_retry_count=None,
    )


class HandleDecomposingParkTest(
    unittest.TestCase,
    _DecomposingWorkflowMixin,
):
    def test_commits_left_by_decomposer_park(self) -> None:
        # The decomposer is supposed to be read-only. If it commits in the
        # parent's worktree, the implementer recovery path in
        # `_handle_implementing` would later see `_has_new_commits` -> True
        # and push decomposer-authored work as if it were implementation.
        # Defensive park is the surface that catches this.
        gh = FakeGitHubClient()
        issue = make_issue(COMMITS_PARK_ISSUE_NUMBER, label=LABEL_DECOMPOSING)
        gh.add_issue(issue)
        manifest = _manifest(SINGLE_MANIFEST_PAYLOAD)

        self._run_decomposing(
            gh,
            issue,
            run_agent=_agent(session_id=DECOMPOSER_SESSION, last_message=manifest),
            has_new_commits=True,
        )

        state = gh.pinned_data(COMMITS_PARK_ISSUE_NUMBER)
        self.assertTrue(state.get(KEY_AWAITING_HUMAN))
        # Did NOT advance to ready -- the operator must clean up first.
        self.assertNotIn(
            (COMMITS_PARK_ISSUE_NUMBER, LABEL_READY),
            gh.label_history,
        )
        last_comment = gh.posted_comments[-1][1]
        self.assertIn(READ_ONLY_FRAGMENT, last_comment)
        self._assert_decomposer_park_event(gh, _PARK_REASON_DIRTY)

    def test_dirty_files_left_by_decomposer_park(self) -> None:
        gh = FakeGitHubClient()
        issue = make_issue(DIRTY_PARK_ISSUE_NUMBER, label=LABEL_DECOMPOSING)
        gh.add_issue(issue)
        manifest = _manifest(SINGLE_MANIFEST_PAYLOAD)

        self._run_decomposing(
            gh,
            issue,
            run_agent=_agent(session_id=DECOMPOSER_SESSION, last_message=manifest),
            dirty_files=("foo.py",),
        )

        state = gh.pinned_data(DIRTY_PARK_ISSUE_NUMBER)
        self.assertTrue(state.get(KEY_AWAITING_HUMAN))
        self.assertNotIn(
            (DIRTY_PARK_ISSUE_NUMBER, LABEL_READY),
            gh.label_history,
        )
        last_comment = gh.posted_comments[-1][1]
        self.assertIn(READ_ONLY_FRAGMENT, last_comment)
        self._assert_decomposer_park_event(gh, _PARK_REASON_DIRTY)

    def test_decompose_timeout_parks(self) -> None:
        gh = FakeGitHubClient()
        issue = make_issue(TIMEOUT_ISSUE_NUMBER, label=LABEL_DECOMPOSING)
        gh.add_issue(issue)

        self._run_decomposing(
            gh,
            issue,
            run_agent=_agent(session_id=DECOMPOSER_SESSION, timed_out=True),
        )

        state = gh.pinned_data(TIMEOUT_ISSUE_NUMBER)
        self.assertTrue(state.get(KEY_AWAITING_HUMAN))
        last_comment = gh.posted_comments[-1][1]
        self.assertIn("decomposer timed out", last_comment)
        self._assert_decomposer_park_event(
            gh, _PARK_REASON_TIMEOUT, expected_retry_count=1,
        )
        _assert_resumed_timeout_park_fail_open(self, "not-an-int")

    def test_decompose_malformed_manifest_parks(self) -> None:
        # A malformed reply earns one correction, and a correction answering
        # malformed again parks before the split writes anything: no child is
        # created and no split tracking is written, so the human's reply
        # resumes the decomposer rather than a recovery. The correction is a
        # retry the budget counts, so the park reads the second.
        for payload, refusal in _MALFORMED_PAYLOADS.items():
            with self.subTest(refusal=refusal):
                gh = FakeGitHubClient()
                issue = make_issue(MALFORMED_MANIFEST_ISSUE_NUMBER, label=LABEL_DECOMPOSING)
                gh.add_issue(issue)

                self._run_decomposing(
                    gh,
                    issue,
                    run_agent=_agent(session_id=DECOMPOSER_SESSION, last_message=_manifest(payload)),
                )

                state = gh.pinned_data(MALFORMED_MANIFEST_ISSUE_NUMBER)
                self.assertTrue(state.get(KEY_AWAITING_HUMAN))
                self.assertIn(f"manifest invalid ({refusal}", gh.posted_comments[-1][1])
                # Last decomposer message quoted into the HITL ping so the human
                # can see what the agent actually emitted.
                self.assertIn(payload, gh.posted_comments[-1][1])
                # Decomposer session recorded so the resume on human reply uses
                # the right backend even if DECOMPOSE_AGENT flips between ticks.
                self.assertEqual(state.get(KEY_DECOMPOSER_SESSION_ID), DECOMPOSER_SESSION)
                self.assertEqual((gh.created_child_issues, gh.label_history), ([], []))
                self.assertFalse(set(_SPLIT_TRACKING) & set(state), "no split tracking is written")
                self._assert_decomposer_park_event(gh, _PARK_REASON_INVALID, expected_retry_count=2)

    def test_decompose_no_manifest_question_parks(self) -> None:
        gh = FakeGitHubClient()
        issue = make_issue(QUESTION_PARK_ISSUE_NUMBER, label=LABEL_DECOMPOSING)
        gh.add_issue(issue)

        self._run_decomposing(
            gh,
            issue,
            run_agent=_agent(
                session_id=DECOMPOSER_SESSION,
                last_message="Should the new commands accept a --json flag?",
                stderr="benign warning",
            ),
        )

        state = gh.pinned_data(QUESTION_PARK_ISSUE_NUMBER)
        self.assertTrue(state.get(KEY_AWAITING_HUMAN))
        last_comment = gh.posted_comments[-1][1]
        self.assertIn("needs your input", last_comment)
        self.assertIn("--json flag", last_comment)
        # Real decomposer text -> no stderr block (would be noise).
        self.assertNotIn("Decomposer stderr", last_comment)
        self._assert_decomposer_park_event(gh, _PARK_REASON_QUESTION)

    def test_decompose_silent_failure_surfaces_stderr(self) -> None:
        # No manifest AND no final message: the decomposer subprocess
        # produced literally nothing. Surface its stderr/exit_code in
        # the park so the operator can tell a CF / quota / auth failure
        # apart from a model that just had no opinion.
        gh = FakeGitHubClient()
        issue = make_issue(SILENT_FAILURE_ISSUE_NUMBER, label=LABEL_DECOMPOSING)
        gh.add_issue(issue)

        log_lines = _run_with_logs(
            self,
            "orchestrator.workflow",
            "WARNING",
            lambda: self._run_decomposing(
                gh,
                issue,
                run_agent=_agent(
                    session_id=DECOMPOSER_SESSION,
                    last_message="",
                    stderr="rate limit exceeded; retry after 60s",
                    exit_code=3,
                ),
            ),
        )

        state = gh.pinned_data(SILENT_FAILURE_ISSUE_NUMBER)
        self.assertTrue(state.get(KEY_AWAITING_HUMAN))
        last_comment = gh.posted_comments[-1][1]
        self.assertIn("(decomposer produced no final message)", last_comment)
        self.assertIn("_Decomposer stderr (last 1KB):_", last_comment)
        self.assertIn("rate limit exceeded", last_comment)
        self.assertIn("_Decomposer exit code:_ 3", last_comment)
        self.assertTrue(
            any(
                "decomposer produced no final message" in log_line and "exit_code=3" in log_line
                for log_line in log_lines
            )
        )
        self._assert_decomposer_park_event(gh, _PARK_REASON_SILENT)

    def _assert_decomposer_park_event(
        self,
        gh: FakeGitHubClient,
        expected_reason: str,
        expected_session: str = DECOMPOSER_SESSION,
        expected_retry_count: int | None = 1,
    ) -> None:
        events = [
            recorded_event for recorded_event in gh.recorded_events
            if recorded_event.get("event") == _EVENT_PARK
        ]
        self.assertEqual(len(events), 1)
        park_record = events[0]
        self.assertEqual(park_record.get("reason"), expected_reason)
        self.assertEqual(park_record.get("agent_role"), _ROLE_DECOMPOSER)
        self.assertEqual(park_record.get("session_id"), expected_session)
        self.assertEqual(park_record.get("retry_count"), expected_retry_count)


class FailedCorrectionParkTest(unittest.TestCase, _corrected.CorrectionTickCase):
    """A correction's own malformed answer parks once, quoting its own error and manifest, and stays parked.

    The session is left pinned for the reply that resumes it, and the spent
    attempt arms nothing: quiet polls, each a process holding nothing of the
    one before, launch, say, write, and announce nothing more.
    """

    def test_a_failed_correction_parks_once(self) -> None:
        parked = self._parked_by_its_correction()
        quiet = self.decomposer(_corrected.LISTED)

        self.tick(quiet)
        self.tick(quiet)

        said = self.said()
        self.assertEqual(quiet.launches, [])
        self.assertEqual(said, [said[0]], "the first rejection is never announced, the second once")
        self.assertIn(f"manifest invalid ({_corrected.SELF_EDGE_ERROR}) after its one automatic correction", said[0])
        self.assertNotIn(_corrected.UNLISTED_ERROR, said[0])
        self.assertEqual(self.pinned(), parked, "nothing is written again")
        self.assertEqual(self.stage(), _corrected.EXHAUSTED)
        self.assertEqual(len(self._park_events()), 1)

    def test_an_oversized_answer_is_held_cut_to_fit(self) -> None:
        # The second invalid answer, or the error it is refused with, is
        # longer than the record can hold beside everything it carries: its
        # notice is held cut to fit -- the latest error and the opening of the
        # rejected answer kept -- and no pinned write is refused for its size,
        # so the post that never landed is said once on the next tick in those
        # words, never in the first error's.
        for name, answer, kept in _OVERSIZED_ANSWERS:
            with self.subTest(name):
                said = self._said_from_the_record(answer)

                self.assertEqual(len(said), 1, "the park is said once")
                self.assertIn("> ```orchestrator-manifest", said[0], "the rejected answer's opening is quoted")
                self.assertIn("left out to fit the pinned comment", said[0])
                self.assertEqual([stretch for stretch in kept if stretch not in said[0]], [])
                self.assertEqual(self.stage(), _corrected.EXHAUSTED)

    def _said_from_the_record(self, answer: str) -> list[str]:
        """What a rejected run's correction answering `answer` has said once its first post was refused.

        Every pinned write is held to the size GitHub takes, and none is
        refused for it.
        """
        self.opened()
        limited, sized = _Refusing.patching(self.github, _PINNED_SEND, _too_long)
        posting, _ = _Refusing.patching(self.github, "comment", _corrected_park, once=True)
        with limited:
            with posting, self.assertRaises(RuntimeError):
                self.tick(self.decomposer(_corrected.UNLISTED, answer))
            self.tick(self.decomposer(_corrected.LISTED))
        self.assertEqual(sized.refused, [], "no pinned write is refused for its size")
        return self.said()

    def _parked_by_its_correction(self) -> dict:
        """The record a tick leaves whose rejected run's correction answered malformed again."""
        self.opened()
        self.tick(self.decomposer(_corrected.UNLISTED, _corrected.SELF_EDGE))
        parked = self.pinned()
        self.assertTrue(parked[KEY_AWAITING_HUMAN])
        self.assertEqual(parked[KEY_DECOMPOSER_SESSION_ID], _corrected.SESSION)
        return parked

    def _park_events(self) -> list:
        return [
            recorded for recorded in self.github.recorded_events
            if recorded.get("event") == _EVENT_PARK and recorded.get("reason") == _PARK_REASON_INVALID
        ]
