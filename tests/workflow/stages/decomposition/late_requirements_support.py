# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The issue-wide requirements baseline a late reading is consumed into.

`user_content_hash` is the baseline every stage's drift check compares the
thread against, and a late path that acts on a reply records it off the very
reading it acted on. What it is held to here is the drift check's own
reading of the thread, computed through the same entry point that check
calls, so a recorded value that agreed only with the late owner's copy of the
filter would still fail.

The journey that value exists for is described here too, because more than
one module drives it: guidance a developer revision answers, a revised
candidate that comes back still oversized, the adjudication that splits it,
and the dispatches that follow -- the umbrella's first poll, and the
decomposing tick a genuine edit reroutes it to. Each step writes the pinned
comment the next one reads, so the case drives them in order rather than
seeding the state one of them would have left.
"""
from __future__ import annotations

from unittest.mock import MagicMock

from orchestrator.workflow.engine import content_hash as _content_hash, issue_processing as _issue_processing
from tests.support.fakes import FakeComment, FakeGitHubClient, FakeIssue
from tests.workflow.fixtures import _TEST_SPEC, _agent
from tests.workflow.patch_context import _patch_and_run
from tests.workflow.patch_models import _WorkflowRunContext
from tests.workflow.stages.decomposition.late_content_replies import human_comment, reply
from tests.workflow.stages.decomposition.late_content_support import REVISED_SHA
from tests.workflow.stages.decomposition.late_revision_support import DEV_PIN, REMEASURED_OVERSIZED, RevisionCase
from tests.workflow.stages.decomposition.late_run_support import WorktreeSeed, agent_reply, late_run_context
from tests.workflow.stages.decomposition.late_test_support import LATE_ISSUE_NUMBER, SPLIT_REPLY

KEY_USER_CONTENT_HASH = "user_content_hash"

KEY_OBSERVED_USER_CONTENT_HASH = "observed_user_content_hash"

KEY_CHILDREN = "children"

# The phrase the drift reroute's notice is recognized by, on every label it
# reroutes from.
DRIFT_NOTICE = "issue content changed"

# What a re-derived decomposition answers with. A question parks the tick that
# spawned it, so a case about what the decomposer was SHOWN has no second set
# of children to account for.
DECOMPOSER_QUESTION = "which of these still applies?"

DECOMPOSER_SESSION = "decomposer-sess"


def requirements(issue: FakeIssue) -> str:
    """The baseline the drift check would compute for the thread as it stands."""
    return _content_hash._compute_user_content_hash(issue, set())


def recorded_baselines(pinned: dict) -> tuple:
    """The recorded requirements baseline and the observed reading, as pinned."""
    return pinned.get(KEY_USER_CONTENT_HASH), pinned.get(KEY_OBSERVED_USER_CONTENT_HASH)


def poll(github: FakeGitHubClient, issue: FakeIssue) -> None:
    """One tick through the dispatcher, under whatever label the issue wears."""
    _issue_processing._route_issue_to_handler(
        github, _TEST_SPEC, issue, github.workflow_label(issue),
    )


def posted(issue: FakeIssue, body: str, **author) -> FakeComment:
    """Append one comment after everything on the thread, by whoever is named."""
    comment = human_comment(
        1 + max(issue_comment.id for issue_comment in issue.comments),
        body,
        **author,
    )
    issue.comments.append(comment)
    return comment


class _Adjudicator:
    """A late adjudicator that splits, with the issue changing while it runs."""

    def __init__(self, issue: FakeIssue, arriving) -> None:
        self._issue = issue
        self._arriving = arriving

    def __call__(self, *_asked, **_answering):
        if self._arriving is not None:
            self._arriving(self._issue)
        return agent_reply(SPLIT_REPLY)


class GuidedSplitCase(RevisionCase):
    """One late issue whose guidance buys a revision the adjudicator splits.

    `head` is the commit the split is made from: the one the revision
    re-froze, unless a case starts from a candidate no revision touched.
    """

    def _start(self) -> None:
        """Seed the issue as its pickup left it, then post the guidance.

        The baseline is the one the pickup recorded, before anybody replied,
        which is what makes the guidance an edit to every reader that never
        consumed it.
        """
        self._seed(**DEV_PIN)
        self.github.seed_state(LATE_ISSUE_NUMBER, **{
            **self._pinned(),
            KEY_USER_CONTENT_HASH: requirements(self.issue),
        })
        self.guidance = reply(self.issue)
        self.head = REVISED_SHA

    def _revise_oversized(self):
        """The tick the guidance buys: a developer run, re-measured oversized.

        Reports the outcome and the resume it went through.
        """
        return self._revise(measurement=REMEASURED_OVERSIZED)

    def _split(self, arriving=None):
        """The tick after it: the revised candidate adjudicated and split.

        `arriving` is what the human does to the issue while the adjudicator
        runs -- past the reading the revision consumed, and before the
        handoff the split makes.
        """
        outcome, _adjudicated = self._run(
            _Adjudicator(self.issue, arriving),
            worktree=WorktreeSeed(head=self.head),
            transact=True,
        )
        return outcome

    def _dispatch(self) -> None:
        """One tick through the dispatcher, under whatever label it wears.

        The late seams are held for the tick that re-enters a split
        transaction; an umbrella poll reaches none of them.
        """
        spawn = MagicMock(return_value=agent_reply(SPLIT_REPLY))
        with late_run_context(
            spawn, worktree=WorktreeSeed(head=self.head), transact=True,
        ):
            self._route()

    def _redecompose(self) -> MagicMock:
        """The decomposing tick a reroute leaves, and the spawn it made."""
        mocks = _patch_and_run(self._route, _WorkflowRunContext(
            run_agent=_agent(
                session_id=DECOMPOSER_SESSION,
                last_message=DECOMPOSER_QUESTION,
            ),
        ))
        return mocks["run_agent"]

    def _route(self) -> None:
        poll(self.github, self.issue)

    def _created(self) -> list[int]:
        """Every child issue any split on this client has created."""
        return [child.number for child in self.github.created_child_issues]
