# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a workflow-label write leaves on the PyGithub issue it went through, and what it sends.

`Issue.set_labels` sends the PUT and keeps nothing of the answer, while the
in-memory double rewrites its own labels whatever it is asked -- so only a
real issue shows whether a read after the write, the transition guard of the
next one included, sees what the write put on GitHub. A move sends no set at
all: it adds its label and takes off the workflow labels it replaces by name,
so only the requests on the wire show that nothing else the issue carries --
applied before the reading or after it -- was ever named.
"""
from __future__ import annotations

import json
import unittest
from types import MappingProxyType, SimpleNamespace
from unittest.mock import patch
from urllib.parse import quote, unquote, urlsplit

from github import Github, GithubException
from github.Issue import Issue

from orchestrator import config
from orchestrator.github.client import GitHubClient
from orchestrator.workflow.state import ControlLabel, WorkflowLabel, stage_name
from orchestrator.workflow.transition_guard import IllegalTransition

_REPO_SLUG = "chippingway/chipping-orchestrator"
_ISSUE_NUMBER = 1641
_ISSUE_PATH = f"/repos/{_REPO_SLUG}/issues/{_ISSUE_NUMBER}"
_LABELS_PATH = f"{_ISSUE_PATH}/labels"
_PUT = "PUT"
_POST = "POST"
_DELETE = "DELETE"
_HTTP_OK = 200
_HTTP_NOT_FOUND = 404

# What GitHub says beside a refusal, by status: a removal of a label the issue
# does not carry answers in words of its own rather than "Not Found".
_REFUSALS = MappingProxyType({_HTTP_NOT_FOUND: "Label does not exist"})
_HTTP_UNPROCESSABLE = 422
_UNRELATED_LABEL = "bug"
_OBSOLETE_IMPLEMENTING = "implementing"
_OBSOLETE_FIXING = "fixing"
_GUARD_SETTING = "WORKFLOW_TRANSITION_GUARD"
_ENFORCE = "enforce"
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

    def __init__(self, status: int = _HTTP_OK, missing: tuple[str, ...] = ()) -> None:
        self.status = status
        self.missing = missing
        self.sent: list[tuple[str, str, object]] = []

    def __call__(self, method: str, url: str, **options: object) -> SimpleNamespace:
        """Answer one request the way GitHub answers a label write; a removal of a `missing` label is not found."""
        sent_body = options.get("data")
        label_names = json.loads(sent_body) if sent_body else None
        path = urlsplit(url).path
        self.sent.append((method, path, label_names))
        status = self._status(method, path)
        answer: object = {"message": _REFUSALS.get(status, "Validation Failed")}
        if status == _HTTP_OK:
            answer = [{"name": name} for name in label_names or ()]
        return SimpleNamespace(
            status_code=status,
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

    def move(self, client: GitHubClient, issue: Issue, new_label: object) -> None:
        """Move through the client, with this stub answering the wire."""
        with patch("requests.Session.request", self):
            client.move_workflow_label(issue, new_label)

    def _status(self, method: str, path: str) -> int:
        """The status one request is answered with: not found for the removal of a `missing` label."""
        removed = unquote(path.rsplit("/", 1)[-1])
        if method == _DELETE and removed in self.missing:
            return _HTTP_NOT_FOUND
        return self.status


def _stages(client: GitHubClient) -> list:
    """The stage tag every `stage_enter` event the client recorded names, in order."""
    return [event["stage"] for event in client.recorded_events]


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
            patch.object(config, _GUARD_SETTING, _ENFORCE),
        )
        for patcher in patchers:
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_pickup_and_outcome_relabel_one_object(self) -> None:
        # Pickup hands the object it relabelled to the decomposition handler,
        # whose outcome relabels it again in the same tick. Neither mode that
        # can object to an edge may see the second one start from no label.
        for mode in ("warn", _ENFORCE):
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
                    _stages(client),
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
            _stages(client),
            ["decomposing", "ready"],
        )


class MoveWorkflowLabelTest(unittest.TestCase):
    """A move adds its label and takes off the workflow labels it replaces, and names nothing else."""

    def setUp(self) -> None:
        patchers = (
            patch.object(config, "EVENT_LOG_PATH", None),
            patch.object(config, _GUARD_SETTING, _ENFORCE),
        )
        for patcher in patchers:
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_a_move_names_only_what_it_moves(self) -> None:
        # The reading carries a repository label, an operator's hold, and the
        # workflow label the move replaces. The requests name the label added
        # and the one taken off and no request carries a whole set, so a label
        # applied on GitHub after that reading -- which nothing sends -- stays
        # as surely as the ones it read. The object reads what moved.
        api = _GitHubApi()
        issue = api.issue(_UNRELATED_LABEL, WorkflowLabel.BLOCKED, ControlLabel.PAUSED)
        client = _client()

        api.move(client, issue, WorkflowLabel.READY)

        self.assertEqual(api.sent, [
            (_POST, _LABELS_PATH, [WorkflowLabel.READY]),
            (_DELETE, f"{_LABELS_PATH}/{quote(WorkflowLabel.BLOCKED)}", None),
        ])
        self.assertEqual(
            [issue_label.name for issue_label in issue.labels],
            [_UNRELATED_LABEL, ControlLabel.PAUSED, WorkflowLabel.READY],
        )
        self.assertEqual(_stages(client), [stage_name(WorkflowLabel.READY)])

    def test_a_label_already_gone_is_gone(self) -> None:
        # A human took the replaced label off before the move did: GitHub
        # answers that removal as not found, and the move stands.
        api = _GitHubApi(missing=(WorkflowLabel.BLOCKED,))
        issue = api.issue(WorkflowLabel.BLOCKED)
        client = _client()

        with self.assertLogs("orchestrator.github", level="INFO"):
            api.move(client, issue, WorkflowLabel.READY)

        methods = [sent[0] for sent in api.sent]
        self.assertEqual(methods, [_POST, _DELETE])
        self.assertEqual(client.workflow_label(issue), WorkflowLabel.READY)
        self.assertEqual(_stages(client), [stage_name(WorkflowLabel.READY)])

    def test_a_refused_edge_sends_nothing(self) -> None:
        # The guard judges the edge before any request leaves: `blocked` is
        # left only for `ready`, so an enforcing guard refuses the move to
        # `decomposing` with nothing sent, moved, or recorded.
        api = _GitHubApi()
        issue = api.issue(WorkflowLabel.BLOCKED)
        client = _client()

        with self.assertRaises(IllegalTransition):
            api.move(client, issue, WorkflowLabel.DECOMPOSING)

        self.assertEqual(api.sent, [])
        self.assertEqual(client.recorded_events, [])
        self.assertEqual(client.workflow_label(issue), WorkflowLabel.BLOCKED)


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

                with patch.object(config, _GUARD_SETTING, _ENFORCE), self.assertRaises(ValueError):
                    api.write(client, issue, label)

                self.assertEqual(api.sent, [])
                self.assertEqual(client.workflow_label(issue), WorkflowLabel.IMPLEMENTING)
                self.assertEqual(client.recorded_events, [])


if __name__ == "__main__":
    unittest.main()
