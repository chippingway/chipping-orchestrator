# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a workflow-label write leaves on the PyGithub issue it went through.

`Issue.set_labels` sends the PUT and keeps nothing of the answer, while the
in-memory double rewrites its own labels whatever it is asked -- so only a
real issue shows whether a read after the write, the transition guard of the
next one included, sees what the write put on GitHub.
"""
from __future__ import annotations

import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import urlsplit

from github import Github, GithubException
from github.Issue import Issue

from orchestrator import config
from orchestrator.github.client import GitHubClient
from orchestrator.workflow.state import ControlLabel, WorkflowLabel
from orchestrator.workflow.transition_guard import IllegalTransition

_REPO_SLUG = "chippingway/chipping-orchestrator"
_ISSUE_NUMBER = 1641
_ISSUE_PATH = f"/repos/{_REPO_SLUG}/issues/{_ISSUE_NUMBER}"
_LABELS_PATH = f"{_ISSUE_PATH}/labels"
_PUT = "PUT"
_HTTP_OK = 200
_HTTP_UNPROCESSABLE = 422
_UNRELATED_LABEL = "bug"
_OBSOLETE_IMPLEMENTING = "implementing"
_OBSOLETE_FIXING = "fixing"
_GUARD_SETTING = "WORKFLOW_TRANSITION_GUARD"
_STATE_MACHINE_LOG = "orchestrator.state_machine"


# One relabel per case: the labels it starts from, the label it writes, every
# name its PUT carries, and the stage tag its `stage_enter` event records. An
# obsolete bare name is repository metadata like `bug`, so a write carries it
# over alone or beside the canonical label of the state it resembles. The
# unprefixed canonical labels are no such name: `in_review` comes off as the
# current state, and `paused` stays as the control it is.
_KEPT_LABEL_CASES = (
    SimpleNamespace(
        carried=(_OBSOLETE_IMPLEMENTING,),
        written=WorkflowLabel.IMPLEMENTING,
        sent=[_OBSOLETE_IMPLEMENTING, WorkflowLabel.IMPLEMENTING],
        stage="implementing",
    ),
    SimpleNamespace(
        carried=(_OBSOLETE_FIXING, WorkflowLabel.FIXING, _UNRELATED_LABEL),
        written=WorkflowLabel.VALIDATING,
        sent=[_OBSOLETE_FIXING, _UNRELATED_LABEL, WorkflowLabel.VALIDATING],
        stage="validating",
    ),
    SimpleNamespace(
        carried=("ready", WorkflowLabel.IN_REVIEW, ControlLabel.PAUSED),
        written=WorkflowLabel.DONE,
        sent=["ready", ControlLabel.PAUSED, WorkflowLabel.DONE],
        stage="done",
    ),
)


class _GitHubApi:
    """GitHub's REST API, as far as a real PyGithub issue reaches it.

    Stubbed at `requests.Session.request`, beneath PyGithub's own requester
    and connection, so `sent` is every HTTP request the client really made
    and the issue it writes through is PyGithub's rather than a double that
    already knows what a write should leave behind.
    """

    def __init__(self, status: int = _HTTP_OK) -> None:
        self.status = status
        self.sent: list[tuple[str, str, object]] = []

    def __call__(self, method: str, url: str, **options: object) -> SimpleNamespace:
        """Answer one request the way GitHub answers a label replacement."""
        sent_body = options.get("data")
        label_names = json.loads(sent_body) if sent_body else None
        self.sent.append((method, urlsplit(url).path, label_names))
        answer: object = {"message": "Validation Failed"}
        if self.status == _HTTP_OK:
            answer = [{"name": name} for name in label_names or ()]
        return SimpleNamespace(
            status_code=self.status,
            headers={"content-type": "application/json"},
            text=json.dumps(answer),
        )

    def issue(self, *label_names: str) -> Issue:
        """A PyGithub issue carrying these labels, as a listing serves it."""
        requester = Github(
            seconds_between_requests=None,
            seconds_between_writes=None,
        ).requester
        return Issue(requester, {}, {
            "number": _ISSUE_NUMBER,
            "url": f"https://api.github.com{_ISSUE_PATH}",
            "labels": [{"name": name} for name in label_names],
        })

    def write(
        self,
        client: GitHubClient,
        issue: Issue,
        new_label: object,
    ) -> None:
        """Relabel through the client, with this stub answering the wire."""
        with patch("requests.Session.request", self):
            client.set_workflow_label(issue, new_label)


def _client() -> GitHubClient:
    """The composed client, without the network its constructor opens."""
    client = GitHubClient.__new__(GitHubClient)
    client._repo_slug = _REPO_SLUG
    client.recorded_events = []
    return client


class SetWorkflowLabelTest(unittest.TestCase):
    """One request per write, and the object it went through reads it back."""

    def setUp(self) -> None:
        patchers = (
            patch.object(config, "EVENT_LOG_PATH", None),
            patch.object(config, _GUARD_SETTING, "enforce"),
        )
        for patcher in patchers:
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_pickup_and_outcome_relabel_one_object(self) -> None:
        # Pickup hands the object it relabelled to the decomposition handler,
        # whose outcome relabels it again in the same tick. Neither mode that
        # can object to an edge may see the second one start from no label.
        for mode in ("warn", "enforce"):
            with self.subTest(mode=mode):
                self._assert_decomposed_in_one_tick(mode)

    def test_clearing_keeps_what_the_write_kept(self) -> None:
        api = _GitHubApi()
        issue = api.issue(_UNRELATED_LABEL, WorkflowLabel.READY)
        client = _client()

        api.write(client, issue, None)

        self.assertEqual(api.sent, [(_PUT, _LABELS_PATH, [_UNRELATED_LABEL])])
        self.assertEqual(
            [issue_label.name for issue_label in issue.labels],
            [_UNRELATED_LABEL],
        )

    def test_a_write_keeps_every_repository_label(self) -> None:
        for case in _KEPT_LABEL_CASES:
            with self.subTest(carried=case.carried):
                api = _GitHubApi()
                issue = api.issue(*case.carried)
                client = _client()

                api.write(client, issue, case.written)

                self.assertEqual(api.sent, [(_PUT, _LABELS_PATH, case.sent)])
                self.assertEqual(
                    [issue_label.name for issue_label in issue.labels],
                    case.sent,
                )
                self.assertEqual(
                    [event["stage"] for event in client.recorded_events],
                    [case.stage],
                )

    def test_an_obsolete_label_guards_as_unlabeled(self) -> None:
        # A bare `implementing` is not the state it resembles, so the guard
        # checks the edge out of no label at all and refuses this one before
        # any request leaves.
        api = _GitHubApi()
        issue = api.issue(_OBSOLETE_IMPLEMENTING)
        client = _client()

        with self.assertRaises(IllegalTransition):
            api.write(client, issue, WorkflowLabel.VALIDATING)

        self.assertEqual(api.sent, [])
        self.assertIsNone(client.workflow_label(issue))

    def test_a_refused_write_moves_nothing(self) -> None:
        api = _GitHubApi(status=_HTTP_UNPROCESSABLE)
        issue = api.issue(_UNRELATED_LABEL, WorkflowLabel.DECOMPOSING)
        client = _client()

        with self.assertRaises(GithubException):
            api.write(client, issue, WorkflowLabel.READY)

        self.assertEqual(len(api.sent), 1)
        self.assertEqual(client.workflow_label(issue), WorkflowLabel.DECOMPOSING)
        self.assertEqual(client.recorded_events, [])

    def _assert_decomposed_in_one_tick(self, mode: str) -> None:
        api = _GitHubApi()
        issue = api.issue(_UNRELATED_LABEL)
        client = _client()

        with patch.object(config, _GUARD_SETTING, mode), self.assertNoLogs(_STATE_MACHINE_LOG):
            api.write(client, issue, WorkflowLabel.DECOMPOSING)
            api.write(client, issue, WorkflowLabel.READY)

        self.assertEqual(api.sent, [
            (_PUT, _LABELS_PATH, [_UNRELATED_LABEL, WorkflowLabel.DECOMPOSING]),
            (_PUT, _LABELS_PATH, [_UNRELATED_LABEL, WorkflowLabel.READY]),
        ])
        self.assertEqual(
            [issue_label.name for issue_label in issue.labels],
            [_UNRELATED_LABEL, WorkflowLabel.READY],
        )
        self.assertEqual(
            [event["stage"] for event in client.recorded_events],
            ["decomposing", "ready"],
        )


class InvalidLabelWriteTest(unittest.TestCase):
    """A label that is not canonical is refused before any request leaves."""

    def test_only_none_clears(self) -> None:
        # A falsy value is no clear: `0` or an empty string read as one would
        # strip the issue's state past an enforcing guard. Each is refused as
        # a typo and an obsolete bare name are, and the issue keeps its state.
        for label in ("vaildating", _OBSOLETE_FIXING, "", 0, False):
            with self.subTest(label=label):
                api = _GitHubApi()
                issue = api.issue(_UNRELATED_LABEL, WorkflowLabel.IMPLEMENTING)
                client = _client()

                with patch.object(config, _GUARD_SETTING, "enforce"), self.assertRaises(ValueError):
                    api.write(client, issue, label)

                self.assertEqual(api.sent, [])
                self.assertEqual(client.workflow_label(issue), WorkflowLabel.IMPLEMENTING)
                self.assertEqual(client.recorded_events, [])


if __name__ == "__main__":
    unittest.main()
