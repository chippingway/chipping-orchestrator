# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What the `ready` decision cases plant on an issue, and the ticks they drive it through.

An issue reaches `ready` carrying the baseline its record preserves -- a
split's child the one its create answered, any other issue the one the drift
check recorded -- and the cases plant that baseline as the drift check itself
would read the thread, through the same entry point. The ticks are the stage's
own: the `ready` handler, with the implementer it hands an unchanged issue to
stood in, and the `decomposing` handler a reroute hands the issue to.
"""
from __future__ import annotations

from types import MappingProxyType
from unittest.mock import patch

from orchestrator.workflow.engine import comments as _comments, content_hash as _content_hash
from orchestrator.workflow.stages.decomposition import blocked as _blocked, run as _decomposing
from tests.support.fakes import FakeGitHubClient, FakeIssue, make_issue
from tests.workflow.fixtures import _TEST_SPEC, LABEL_READY, _agent, _manifest, _reported

PARENT = 119

CHILD = 120

# What the child was created saying: its slice, as its split cut it.
CREATED_TITLE = "Cover the drift baseline"

CREATED_BODY = "The slice its split cut for it.\n\nParent: #119"

KEY_BASELINE = "user_content_hash"

# What the drift check reads off a child nobody has edited since its create.
CREATED_READING = _content_hash._compute_user_content_hash(
    make_issue(CHILD, title=CREATED_TITLE, body=CREATED_BODY), set(),
)

KEY_OBSERVED = "observed_user_content_hash"

KEY_REROUTE = "ready_reroute"

KEY_PICKUP = "pickup_comment_id"

KEY_LAST_ACTION = "last_action_comment_id"

RUN_AGENT = "run_agent"

LABEL_DECOMPOSING = "workflow:decomposing"

LABEL_IMPLEMENTING = "workflow:implementing"

PICKUP = "picking this up; starting implementation"

CHANGED_NOTICE = "issue content changed; re-running decomposer"

UNBASELINED_NOTICE = "carries no baseline of the requirements it was created with"

TRUSTED = "alice"

SINGLE_MANIFEST = _manifest('{"decision": "single", "rationale": "fits one"}')

# A comment this orchestrator posted, its hidden marker and all.
GENERATED = _comments._with_orch_marker(":robot: an orchestrator notice")

# The reroute a `ready` tick records with its reset, as `ReadyTicks.reroute`
# reads it back with its notice's receipt set aside: for requirements that
# changed, and for a child carrying no baseline at all.
CHANGED_REROUTE = MappingProxyType({"orphans": [], "unbaselined": False})

UNBASELINED_REROUTE = MappingProxyType({"orphans": [], "unbaselined": True})

# The notices a thread was told, as `notices` counts them: one changed
# reroute, one unbaselined reroute, one pickup, and none at all.
SAID_CHANGED = (1, 0, 0)

SAID_UNBASELINED = (0, 1, 0)

SAID_PICKUP = (0, 0, 1)

SAID_NOTHING = (0, 0, 0)

# Where the child stands: once its reroute's relabel has landed, once its
# handoff's has, and before anything was relabelled, said, or written.
REROUTED = ((CHILD, LABEL_DECOMPOSING),)

STARTED = (CHILD, LABEL_IMPLEMENTING)

UNMOVED = ((), SAID_NOTHING, 0)

# How a reroute's notice receipt is spelled.
RECEIPT_SPELLING = "^[0-9a-f]{16}$"


def reading(issue: FakeIssue) -> str:
    """What the drift check reads off the thread as it stands, with no comment of ours on it."""
    return _content_hash._compute_user_content_hash(issue, set())


def ready_child(gh: FakeGitHubClient, *, edited: bool = False, **pinned) -> FakeIssue:
    """A child its parent released onto `ready`, its record linking it and carrying `pinned`.

    Baselined at what it was created saying unless `pinned` names the
    baseline itself -- None for a record carrying none at all. `edited` is a
    child whose body a human has added to since.
    """
    issue = make_issue(CHILD, label=LABEL_READY, title=CREATED_TITLE, body=CREATED_BODY)
    gh.add_issue(issue)
    record = {"parent_number": PARENT, KEY_BASELINE: reading(issue), **pinned}
    kept = {key: field for key, field in record.items() if field is not None}
    gh.seed_state(CHILD, **kept)
    if edited:
        issue.body = f"{issue.body}\n\nAlso cover the docs."
    return issue


def seen(gh: FakeGitHubClient) -> tuple:
    """What the child's ticks so far left visible: its relabels, the notices told, and the pinned writes sent."""
    return tuple(gh.label_history), notices(gh), gh.write_state_calls


def notices(gh: FakeGitHubClient, number: int = CHILD) -> tuple:
    """How many changed and unbaselined reroute notices, and pickups, the issue's thread was told."""
    bodies = [body for posted, body in gh.posted_comments if posted == number]
    return tuple(
        sum(fragment in body for body in bodies)
        for fragment in (CHANGED_NOTICE, UNBASELINED_NOTICE, PICKUP)
    )


class ReadyTicks:
    """The two ticks a `ready` issue is driven through, for a case on the patched workflow."""

    def ready_tick(self, gh: FakeGitHubClient, issue: FakeIssue) -> int:
        """The `ready` handler's tick, its implementer answering with a report over a commit; the agents it ran."""
        mocks = self._run(
            lambda: _blocked._handle_ready(gh, _TEST_SPEC, issue),
            run_agent=_agent(session_id="dev-sess", last_message=_reported()),
            has_new_commits=[False, True],
            push_branch=True,
        )
        return mocks[RUN_AGENT].call_count

    def decomposing_tick(self, gh: FakeGitHubClient, issue: FakeIssue) -> int:
        """The `decomposing` handler's tick, its decomposer voting `single`; the agents it ran."""
        mocks = self._run(
            lambda: _decomposing._handle_decomposing(gh, _TEST_SPEC, issue),
            run_agent=_agent(session_id="decomposer-sess", last_message=SINGLE_MANIFEST),
        )
        return mocks[RUN_AGENT].call_count

    def edited_tick(self, gh: FakeGitHubClient, issue: FakeIssue, readings: int, **edits) -> tuple:
        """The `ready` tick, a human's edit landing on the record once `readings` reads are taken; what it left."""
        lands = LandsAfter(gh, "read_pinned_state", readings, InPlace(**edits))
        return self.interleaved_tick(gh, issue, lands)

    def interleaved_tick(self, gh: FakeGitHubClient, issue: FakeIssue, lands: LandsAfter) -> tuple:
        """The `ready` tick with `lands` landing between two of its requests; what it left.

        The agents it ran, and what it left visible (`seen`).
        """
        with patch.object(gh, lands.request, lands):
            ran = self.ready_tick(gh, issue)
        return ran, seen(gh)

    def reroute(self, gh: FakeGitHubClient):
        """The reroute the child's record carries, its notice's receipt held to its shape and set aside; or None."""
        recorded = self.recorded(gh, KEY_REROUTE)
        if recorded is None:
            return None
        owed = dict(recorded)
        self.assertRegex(owed.pop("receipt"), RECEIPT_SPELLING)
        return owed

    def recorded(self, gh: FakeGitHubClient, key: str):
        """What the child's pinned record carries under `key`, or None."""
        return gh.pinned_data(CHILD).get(key)


class LandsAfter:
    """One of the client's requests, with something landing on the issue once `calls` of them are answered.

    `landing` is called with the client and the issue behind the answer to
    the last of those calls -- a human's edit, a comment, a label -- the way
    GitHub would show it to the next request.
    """

    def __init__(self, gh: FakeGitHubClient, request: str, calls: int, landing) -> None:
        self.request = request
        self._gh = gh
        self._answer = getattr(gh, request)
        self._left = calls
        self._landing = landing

    def __call__(self, issue, *args, **kwargs):
        """Answer the request, and land what lands behind the last answer before it."""
        answered = self._answer(issue, *args, **kwargs)
        self._left -= 1
        if not self._left:
            self._landing(self._gh, issue)
        return answered


class InPlace:
    """A human's hand edit of the issue's pinned record: the same comment, rewritten with `edits` laid over it."""

    def __init__(self, **edits) -> None:
        self._edits = edits

    def __call__(self, gh: FakeGitHubClient, issue: FakeIssue) -> None:
        """Lay the edits over the record as pinned."""
        pinned = gh._pinned[issue.number]
        pinned.state_data.update(self._edits)
