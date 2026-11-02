# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""An initial decomposition whose decomposer answers each launch in turn, and what every launch met.

Driven through whole `decomposing` ticks over the in-memory client, so the
rejection, the arming, the circuit's charge, the accounting, and every write a
correction makes are the production ones; only the decomposer process is
scripted. Each launch records the pinned record and the children the client
had created when it was invoked, which is how a test proves nothing was made
before the correction ran. A strict edit can be lost by its place in the tick,
or the world moved right behind it once it lands (`CountedEdit`): the rejected
run's accounting, the arming, the correction's accounting, and its exhaustion
are the parent's first four. The issue can be
moved right before one of the tick's fresh fetches of it (`OnFetch`), which a
tick correcting its rejected run on the spot makes in this order: the
live-pause check behind the rejected run; the controls the circuit asks on the
reading the correction is charged on; behind the charge, the controls asked
before and behind the thread's read; the controls asked on the reading its
start is written over; the live-pause check behind its return; and before its
answer is acted on, the controls asked before and behind the thread's read,
again behind the exhaustion, and last behind the saved context's read.
"""
from __future__ import annotations

import copy
import dataclasses
import json
from collections.abc import Callable
from functools import partial
from unittest.mock import patch

from orchestrator.agents.models import AgentResult, AgentRunOptions
from orchestrator.workflow.engine import issue_processing as _issue_processing
from tests.support.fakes import FakeComment, FakeGitHubClient, FakeLabel, FakeUser, make_issue
from tests.workflow.fixtures import _TEST_SPEC, LABEL_DECOMPOSING, _agent, _manifest
from tests.workflow.stages.decomposition.decomposing_test_support import _DecomposingWorkflowMixin

ISSUE_NUMBER = 77

SESSION = "dec-corrected"

TRUSTED_AUTHOR = "alice"

FIELD = "decomposer_correction"

SLICES = 10

PENDING = "pending"
EXHAUSTED = "exhausted"
RETIRED = "retired"

# The fetch right behind the correction's charge, the controls asked behind its
# thread's read and on the reading its start is written over; the first fetch
# before its answer is used, and the controls asked behind the saved context's read.
BEHIND_THE_CHARGE = 3
BEHIND_THE_THREAD = 4
ON_THE_START = 5
BEFORE_ACTING = 7
BEHIND_THE_CONTEXT = 11

# The parent's strict edit that spends a correction its answer returned.
EXHAUSTION = 4

# The refusal ten children with every list left out earn: the first one's.
UNLISTED_ERROR = "child 0 missing depends_on"

# What a correction's own malformed manifest adds to the park it takes.
CORRECTED_PARK = "after its one automatic correction"

# What a split writes on its parent before it creates the first child.
SPLIT_MARKERS = ("expected_children_count", "children", "dep_graph", "split_attempt")

SINGLE = _manifest('{"decision": "single", "rationale": "fits one context"}')

QUESTION = "Should the parser and the renderer ship apart?"

# A malformed answer whose error is not the first one's: a child's list names itself.
SELF_EDGE = _manifest(
    '{"decision": "split", "children": [{"title": "A", "body": "a", "depends_on": [0]}]}',
)
SELF_EDGE_ERROR = "child 0 has invalid dependency 0"

# What a shutdown kill exits with.
SHUTDOWN_EXIT = -15


def slices(*, listed: bool) -> str:
    """A split into ten slices, each needing the one before it: every list stated, or every one left out."""
    children = []
    for index in range(SLICES):
        before = index - 1
        child = {"title": f"Slice {index}", "body": f"Deliver slice {index} on slice {before}."}
        if listed:
            child["depends_on"] = [before] if index else []
        children.append(child)
    return _manifest(json.dumps({"decision": "split", "rationale": "ten slices in a chain", "children": children}))


UNLISTED = slices(listed=False)
LISTED = slices(listed=True)


@dataclasses.dataclass(frozen=True)
class Launch:
    """One process the decomposer double was invoked as, and what the issue carried as it was."""

    backend: str
    prompt: str
    options: AgentRunOptions
    record: dict
    children: int

    @property
    def resumed(self) -> str | None:
        """The session id the launch resumed, or None for a fresh conversation."""
        return self.options.resume_session_id

    def command(self) -> tuple:
        """The backend and arguments the launch ran under."""
        return self.backend, self.options.extra_args


@dataclasses.dataclass
class Decomposer:
    """The runner seam: each launch answered with the next of `answers`, the last repeated, on `session`.

    An answer is a final message, or an `AgentResult` field mapping; `during`
    maps a launch's place to what happens to the world while it is out.
    """

    world: CorrectionTickCase
    answers: tuple
    during: dict = dataclasses.field(default_factory=dict)
    session: str | None = SESSION
    launches: list[Launch] = dataclasses.field(default_factory=list)

    def __call__(self, backend: str, prompt: str, _cwd, *, options: AgentRunOptions) -> AgentResult:
        place = len(self.launches)
        world = self.world
        self.launches.append(Launch(
            backend,
            prompt,
            options,
            world.pinned(),
            world.children(),
        ))
        meanwhile = self.during.get(place)
        if meanwhile is not None:
            meanwhile(world)
        return _agent(session_id=self.session, **self._answer(place))

    def _answer(self, place: int) -> dict:
        """The result fields the launch at `place` comes back with: its answer, or the last one."""
        answer = self.answers[min(place, len(self.answers) - 1)]
        return {"last_message": answer} if isinstance(answer, str) else dict(answer)


@dataclasses.dataclass
class OnFetch:
    """The issue fetch, letting `action` befall the world right before its `nth` call and every one after."""

    world: CorrectionTickCase
    nth: int
    action: Callable
    fetch: Callable
    seen: int = 0

    def __call__(self, number: int):
        self.seen += 1
        if self.seen >= self.nth:
            self.action(self.world)
        return self.fetch(number)

    @classmethod
    def patch(cls, world: CorrectionTickCase, nth: int, action: Callable):
        """The world's issue fetch, so patched for the block."""
        fetches = cls(world, nth, action, world.github.get_issue)
        return patch.object(world.github, "get_issue", side_effect=fetches)


@dataclasses.dataclass
class CountedEdit:
    """The strict editor, at the issue's edits counted at the places named: response lost, or the world moved behind.

    A lost edit lands as sent and answers as though it had not; one with
    `behind` lands and is answered, and `behind` befalls the world right after.
    """

    github: FakeGitHubClient
    at: frozenset
    edit: Callable
    behind: Callable[[], None] | None = None
    seen: int = 0

    def __call__(self, issue, *args, **kwargs):
        if issue.number != ISSUE_NUMBER:
            return self.edit(issue, *args, **kwargs)
        self.seen += 1
        counted = self.seen in self.at
        lost = self.github.pinned_failures.lost
        if counted and self.behind is None:
            lost.add(issue.number)
        try:
            answered = self.edit(issue, *args, **kwargs)
        except RuntimeError:
            lost.discard(issue.number)
            raise
        lost.discard(issue.number)
        if counted and self.behind is not None:
            self.behind()
        return answered

    @classmethod
    def losing(cls, github: FakeGitHubClient, *nth: int):
        """The client's strict editor, losing the response of its `nth` edits, for the block."""
        edits = cls(github, frozenset(nth), github.edit_pinned_state)
        return patch.object(github, "edit_pinned_state", side_effect=edits)

    @classmethod
    def landing(cls, world: CorrectionTickCase, nth: int, action: Callable):
        """The world's strict editor, letting `action` befall the world right behind its `nth` edit, for the block."""
        github = world.github
        moved = partial(action, world)
        edits = cls(github, frozenset((nth,)), github.edit_pinned_state, moved)
        return patch.object(github, "edit_pinned_state", side_effect=edits)


class _CorrectionReadings:
    """What the issue reads as now, off the client."""

    def pinned(self) -> dict:
        return copy.deepcopy(self.github.pinned_data(ISSUE_NUMBER))

    def stage(self) -> str | None:
        """The stage the issue's correction attempt stands at, or None where it carries none."""
        attempt = self.pinned().get(FIELD)
        return None if attempt is None else attempt["stage"]

    def said(self) -> list[str]:
        posted = self.github.posted_comments
        return [body for number, body in posted if number == ISSUE_NUMBER]

    def label(self) -> str | None:
        return self.github.workflow_label(self.issue)

    def children(self) -> int:
        return len(self.github.created_child_issues)

    def runs(self) -> int:
        """The lifetime charges the issue's run ledger counts."""
        return self.pinned()["agent_runs_used"]


class CorrectionTickCase(_CorrectionReadings, _DecomposingWorkflowMixin):
    """An issue on `workflow:decomposing` that has never been decomposed, and the ticks that meet it."""

    def opened(self, **record) -> None:
        self.github = FakeGitHubClient()
        self.issue = make_issue(ISSUE_NUMBER, label=LABEL_DECOMPOSING, title="Ten slices", body="Ship ten slices.")
        self.github.add_issue(self.issue)
        if record:
            self.github.seed_state(ISSUE_NUMBER, **record)

    def decomposer(self, *answers, **options) -> Decomposer:
        return Decomposer(self, answers, **options)

    def tick(self, runner: Decomposer, **run_options):
        """One `decomposing` handler tick, as a process holding nothing from an earlier one."""
        return self._run_decomposing(self.github, self.issue, run_agent=runner, **run_options)

    def dispatch(self, runner: Decomposer) -> None:
        """One dispatched tick, the dispatcher's holds and grants ahead of the handler included."""
        self._run(
            lambda: _issue_processing._process_issue(self.github, _TEST_SPEC, self.issue),
            run_agent=runner,
        )

    def reply(self, body: str) -> FakeComment:
        """A trusted human's comment appended to the thread now."""
        comment = FakeComment(
            id=self.github.next_reply_id(self.issue),
            body=body,
            user=FakeUser(TRUSTED_AUTHOR),
        )
        self.issue.comments.append(comment)
        return comment

    def hold(self, name: str = "paused") -> None:
        self.issue.labels.append(FakeLabel(name))

    def lift(self, name: str = "paused") -> None:
        self.issue.labels = [label for label in self.issue.labels if label.name != name]
