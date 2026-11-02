# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A decomposition parked by a real first run, over the baseline that run's tick recorded.

Nothing about the park is seeded. The first tick's own drift check records the
baseline over the title, the body, and the guidance already on the thread, its
run's invalid manifest earns the one correction it may, and that correction's
own invalid manifest parks: the park posts its notice and stands the reply
boundary on it, so every later tick meets exactly what a live issue would: a
reply past that boundary is the park's answer, and a change to anything at or
below it is an edit.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from orchestrator import config
from orchestrator.workflow.engine import (
    comments as _comments,
    content_hash as _content_hash,
    issue_processing as _issue_processing,
    run_ledger_values as _run_ledger_values,
)
from tests.support.fakes import FakeComment, FakeGitHubClient, FakeLabel, FakeUser, make_issue
from tests.workflow.fixtures import _TEST_SPEC, LABEL_DECOMPOSING, _agent, _manifest
from tests.workflow.stages.decomposition.decomposing_test_support import _DecomposingWorkflowMixin
from tests.workflow.stages.decomposition.decomposition_test_support import _comments_for_issue

# Below the first number the client mints for an issue it opens, so every
# child a split of this issue creates is numbered above it, as on GitHub.
PARKED_ISSUE_NUMBER = 81

PARKED_SESSION = "dec-parked"

TRUSTED_AUTHOR = "alice"

OUTSIDER = "mallory"

ISSUE_TITLE = "Split the report pipeline"

ISSUE_BODY = "Parse the reports, then render them."

# Guidance a human gave before the decomposer first ran: the baseline that
# run's tick recorded counts it, and the park has already read it.
EARLIER_COMMENT_ID = 700

EARLIER_GUIDANCE = "the renderer has to keep streaming"

REPLY = "split it into the parser and the renderer"

LATER_REPLY = "and keep the output byte-identical"

DRIFT_NOTICE = "issue content changed"

# A split whose child leaves `depends_on` unstated, which parks the issue on
# `decomposer_invalid_manifest` before any child is created.
INVALID_MANIFEST = _manifest('{"decision": "split", "children": [{"title": "A", "body": "a"}]}')

SINGLE_MANIFEST = _manifest('{"decision": "single", "rationale": "fits"}')

# A reply carrying no manifest at all, which parks the issue as a question.
QUESTION = "Should the renderer keep streaming while it splits?"

SPLIT_MANIFEST = _manifest('{"decision": "split", "children": [{"title": "A", "body": "a", "depends_on": []}]}')

EDITED_TITLE = "Split the report pipeline in three"

EDITED_BODY = "Parse the reports, validate them, then render them."

EDITED_GUIDANCE = "the renderer may buffer whole pages"

# The one run the park's first tick charged: an allowance of exactly that
# leaves the issue's lifetime ledger spent.
FIRST_TICK_RUNS = 1

SHUTDOWN_EXIT_CODE = -15

# How often one clause repeats in a reply longer than the excerpt a decompose
# prompt quotes its thread under.
LONG_REPLY_CLAUSES = 200

LONG_REPLY = "".join(("split it by stage: ", "parse each report in turn; " * LONG_REPLY_CLAUSES))

# Each change to what the park had already read, by the text it leaves for a
# fresh decomposer to read.
_EDITS = (
    (EDITED_TITLE, lambda case: setattr(case.issue, "title", EDITED_TITLE)),
    (EDITED_BODY, lambda case: setattr(case.issue, "body", EDITED_BODY)),
    (EDITED_GUIDANCE, lambda case: setattr(case.earlier, "body", EDITED_GUIDANCE)),
)

# Each of those edits alone, and beside a reply.
PARKED_EDITS = tuple(
    (edited, edits, replied) for edited, edits in _EDITS for replied in (False, True)
)


def decomposer_run(last_message: str = SINGLE_MANIFEST, **fields) -> MagicMock:
    """A runner whose one exit comes back on the parked session, recording the launch it was handed."""
    return MagicMock(return_value=_agent(session_id=PARKED_SESSION, last_message=last_message, **fields))


def launched(runner: MagicMock) -> tuple[str, str | None]:
    """The prompt and the resumed session id the runner's last launch was handed."""
    launch = runner.call_args
    return launch.args[1], launch.kwargs["options"].resume_session_id


def read_through(pinned: dict) -> tuple:
    """The reply boundary and the requirements baseline one pinned record carries."""
    return pinned["last_action_comment_id"], pinned["user_content_hash"]


def allowing(*authors: str):
    """`ALLOWED_ISSUE_AUTHORS` naming only these logins, for the block."""
    return patch.object(config, "ALLOWED_ISSUE_AUTHORS", authors)


class PausedWhileOut:
    """A runner whose run an operator pauses before it returns."""

    def __init__(self, issue) -> None:
        self._issue = issue

    def __call__(self, *_args, **_kwargs):
        self._issue.labels.append(FakeLabel("paused"))
        return _agent(session_id=PARKED_SESSION, last_message=SINGLE_MANIFEST)


# Each run launched on replies it never read: the record edit that sets it up,
# the runner it meets, and what the worktree reads.
HELD_RUNS = (
    (
        "a refused launch",
        (_run_ledger_values.AGENT_RUN_ALLOWANCE, FIRST_TICK_RUNS),
        lambda issue: decomposer_run(),
        {},
    ),
    (
        "an unresolved accounting",
        ("issue_total_tokens", "a counter no accounting adds to"),
        lambda issue: decomposer_run(),
        {},
    ),
    ("a live hold", None, PausedWhileOut, {}),
    (
        "an ignored interruption",
        None,
        lambda issue: decomposer_run(interrupted=True, exit_code=SHUTDOWN_EXIT_CODE),
        {},
    ),
    (
        "an interrupted run's dirty park",
        None,
        lambda issue: decomposer_run(interrupted=True, exit_code=SHUTDOWN_EXIT_CODE),
        {"has_new_commits": True},
    ),
)


class AnsweredWhileOut:
    """A runner a human writes a further reply under while it is out.

    It keeps that reply and the prompt and resumed session id it was handed,
    and comes back with `last_message` on `session`: by default a question on
    the parked session, which parks the issue again with no correction owed.
    """

    def __init__(self, reply, last_message: str = QUESTION, session: str = PARKED_SESSION) -> None:
        self._reply = reply
        self._returned = _agent(session_id=session, last_message=last_message)
        self.written: list[FakeComment] = []
        self.handed: tuple[str, str | None] = ("", None)

    def __call__(self, _backend, prompt, *_args, options=None, **_kwargs):
        self.handed = (prompt, options.resume_session_id)
        self.written.append(self._reply(LATER_REPLY))
        return self._returned


class _ParkedDecompositionCase(_DecomposingWorkflowMixin):
    """An issue parked on its first decomposer run's invalid manifest, and the ticks that meet it.

    `baseline` and `floor` are what that park recorded: the requirements and
    the reply boundary every later reading is measured against.
    """

    def _park(self) -> None:
        self.github = FakeGitHubClient()
        self.issue = make_issue(
            PARKED_ISSUE_NUMBER, label=LABEL_DECOMPOSING, title=ISSUE_TITLE, body=ISSUE_BODY,
        )
        self.earlier = FakeComment(
            id=EARLIER_COMMENT_ID,
            body=EARLIER_GUIDANCE,
            user=FakeUser(TRUSTED_AUTHOR),
        )
        self.issue.comments.append(self.earlier)
        self.github.add_issue(self.issue)
        self._tick(decomposer_run(INVALID_MANIFEST))
        parked = self._pinned()
        self.floor = parked["last_action_comment_id"]
        self.baseline = parked["user_content_hash"]

    def _reply(self, body: str = REPLY, author: str = TRUSTED_AUTHOR) -> FakeComment:
        """A comment appended to the thread now, under the next id the client mints."""
        reply = FakeComment(
            id=self.github.next_reply_id(self.issue),
            body=body,
            user=FakeUser(author),
        )
        self.issue.comments.append(reply)
        return reply

    def _tick(self, run_agent, **run_options):
        """One `decomposing` handler tick."""
        return self._run_decomposing(self.github, self.issue, run_agent=run_agent, **run_options)

    def _dispatch(self, run_agent) -> None:
        """One dispatched tick, the guards ahead of the handler included."""
        self._run(
            lambda: _issue_processing._process_issue(self.github, _TEST_SPEC, self.issue),
            run_agent=run_agent,
        )

    def _pinned(self) -> dict:
        return self.github.pinned_data(PARKED_ISSUE_NUMBER)

    def _said(self) -> list[str]:
        return _comments_for_issue(self.github, PARKED_ISSUE_NUMBER)

    def _requirements(self, through: int | None = None) -> str:
        """The fingerprint a drift check reads off the thread as it stands, up to `through` where named."""
        thread = [
            seen for seen in self.issue.comments
            if through is None or seen.id <= through
        ]
        ours = _comments._orchestrator_ids(self.github.read_pinned_state(self.issue))
        return _content_hash._compute_user_content_hash(self.issue, ours, comments=thread)
