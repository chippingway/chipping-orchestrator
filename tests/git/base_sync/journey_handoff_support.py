# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""An authorized oversized change whose base advance changes what it contributes, walked for real.

The adjudicated journey's fixture with one difference in what the base does:
the branch edits the tail of a file the base also carries, and the advance
edits that file's head. The replay is clean and its contribution is a
different one -- the pre-image a reviewer would be handed is another blob --
so the transfer permit refuses and the cumulative gate measures the replay
past the ceiling. What a journey drives over it are the production ticks: the
refresh, then the dispatcher over the issue as the refresh left it, with only
the adjudicator's reply and the authenticated push stood in for.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from orchestrator.agents import runner as _agent_runner
from orchestrator.git import branch_transport as _branch_transport
from orchestrator.workflow.engine import (
    comments as _comments,
    content_hash as _content_hash,
    issue_processing as _issue_processing,
)
from tests.git.base_sync.exemption_git_support import BASE_EDIT, SHARED_FILE, _shared_body, events_of
from tests.git.base_sync.journey_adjudication_support import SINGLE_MANIFEST, adjudicates_once, replies
from tests.git.base_sync.journey_assertions import ADJUDICATOR, KEY_REWRITE_DEBT, JourneyAssertions
from tests.git.base_sync.journey_git_support import OversizedJourneyRealGitFixture
from tests.git.base_sync.journey_push_support import PUSH_BRANCH, PublishesToThePullRequest
from tests.git.base_sync.real_git_test_support import ADD_COMMAND, ORIGIN_REMOTE, PR_BRANCH, PR_NUMBER
from tests.workflow.fixtures import LABEL_DECOMPOSING, LABEL_VALIDATING, _agent

# Who holds the replay: the attempt's anchor and its record of the replay, and
# the candidate the live generation froze beside the replay it took over.
_HOLDERS = (
    "pending_auto_base_rebase_push_sha",
    "pending_auto_base_rebase_rewrite_sha",
    "late_candidate_sha",
    "late_auto_rebase_replay_sha",
)

# The park a `single` verdict leaves for the human who authorizes it.
PARK_SINGLE_DECISION = "late_single_decision"

# Two adjudicator runs: the one the authorized change earned, and the replay's.
ADJUDICATED_TWICE = (ADJUDICATOR, ADJUDICATOR)

# The operator's content-free nudge, which the legacy requirements baseline counted.
BARE_CONTINUE = "/orchestrator continue"

# The file somebody else's push to the pull request's branch adds.
FOREIGN_FILE = "foreign.txt"
_FOREIGN_BRANCH = "foreign"


def records_a_legacy_baseline(fixture) -> None:
    """Have a stage read a bare continue, and record the requirements baseline as the legacy algorithm spelled it.

    That algorithm counted the continue, which the current one leaves out, so
    the baseline covers the thread in the one spelling and not the other.
    """
    nudged = replies(fixture, BARE_CONTINUE)
    durable = fixture._durable()
    durable.set("last_action_comment_id", nudged)
    ours = _comments._orchestrator_ids(durable)
    durable.set("user_content_hash", _content_hash._compute_user_content_hash(
        fixture._issue(), ours, include_bare_continue=True,
    ))
    fixture._gh.write_pinned_state(fixture._issue(), durable)


def spawned_roles(fixture) -> tuple:
    """Every agent role the journey spawned, in order."""
    return tuple(spawned["agent_role"] for spawned in events_of(fixture, "agent_spawn"))


class ChangedContributionJourney(JourneyAssertions, OversizedJourneyRealGitFixture):
    """An adjudicated, authorized change whose base advanced under the file it edits."""

    def setUp(self) -> None:
        super().setUp()
        self._commits_on_the_shared_file()
        self.accepted = self._commits_an_oversized_candidate()
        adjudicates_once(self, self.accepted)
        self.adjudication = self._issue_comments()
        self._commit_to_base(SHARED_FILE, _shared_body(first=BASE_EDIT))

    def _ticks(self, reply: str = SINGLE_MANIFEST) -> PublishesToThePullRequest:
        """One production tick: the refresh, then the dispatcher; the dispatcher's push.

        The dispatcher's road is the whole of it -- every guard ahead of the
        handler, the handler, and any agent the handler spawns, whose reply is
        `reply`: by default the adjudicator's `single` -- over the issue as the
        refresh left it.
        """
        self._refreshes()
        pusher = PublishesToThePullRequest(self._gh)
        spawn = MagicMock(return_value=_agent(last_message=reply))
        with patch.object(_agent_runner, "run_agent", spawn), patch.object(_branch_transport, PUSH_BRANCH, pusher):
            _issue_processing._route_issue_to_handler(
                self._gh, self._spec, self._issue(), self._gh.workflow_label(self._issue()),
            )
        return pusher

    def _pushes_over_the_pull_request(self) -> str:
        """Somebody else's commit pushed onto the pull request's branch; its id."""
        self._git("checkout", "-B", _FOREIGN_BRANCH, self.accepted, cwd=self._work)
        (self._work / FOREIGN_FILE).write_text("foreign\n")
        self._git(ADD_COMMAND, ".", cwd=self._work)
        self._git("commit", "-m", "somebody else's work", cwd=self._work, env_extra=self._author_env)
        self._git("push", ORIGIN_REMOTE, f"{_FOREIGN_BRANCH}:refs/heads/{PR_BRANCH}", cwd=self._work)
        foreign = self._git("rev-parse", "HEAD", cwd=self._work).strip()
        pull_request = self._gh.pulls[PR_NUMBER]
        pull_request.head.sha = foreign
        return foreign

    def _assert_adjudicated_afresh(self, replay: str) -> None:
        """The replay was handed over and adjudicated once, unreset and unpublished.

        The checkout still stands on it and the pull request on the commit the
        human authorized; the attempt is gone and the generation owns the
        replay; the second reading and the second adjudicator run are the
        replay's own, with no developer run beside them; the human is asked
        about the replay; and no report is owed yet, since nothing new is on
        the pull request.
        """
        durable = self._durable()
        parked = (durable.get("awaiting_human"), durable.get("park_reason"))
        self.assertEqual(self._standing(), (replay, self.accepted, LABEL_DECOMPOSING))
        self.assertEqual(self._holders(), (None, None, replay, replay))
        self.assertEqual(parked, (True, PARK_SINGLE_DECISION))
        self.assertIsNone(durable.get(KEY_REWRITE_DEBT))
        self.assertEqual(spawned_roles(self), ADJUDICATED_TWICE)
        self.assertEqual(len(events_of(self, "late_measurement")), 2)
        self.assertIn(replay, self._issue_comments()[-1])

    def _assert_published(self, replay: str, pushed: PublishesToThePullRequest) -> None:
        """The settlement pushed the replay over the head the generation froze, and handed it back.

        Leased to the commit the human authorized before, owing a report of
        the head it rewrote, the reviewer's spent rounds put back as for every
        rebase this orchestrator publishes, the exemption moved onto it, the
        generation and its takeover retired, and no agent run for any of it.
        """
        durable = self._durable()
        lease = (pushed.revision, pushed.force_with_lease, durable.get("review_round"))
        self.assertEqual(lease, (replay, self.accepted, 0))
        self.assertEqual(self._standing(), (replay, replay, LABEL_VALIDATING))
        self.assertEqual(self._holders(), (None, None, None, None))
        self.assertEqual(durable.get("late_exempt_sha"), replay)
        self.assertEqual(durable.get(KEY_REWRITE_DEBT), {
            "pr": PR_NUMBER, "branch": PR_BRANCH, "previous_head": self.accepted, "rewritten_head": replay,
        })
        self.assertEqual(spawned_roles(self), ADJUDICATED_TWICE)

    def _standing(self) -> tuple:
        """The commit the checkout stands on, the one the pull request stands on, and the issue's label."""
        pull_request = self._gh.pulls[PR_NUMBER]
        label = self._gh.workflow_label(self._issue())
        return self._wt_head(), pull_request.head.sha, label

    def _holders(self) -> tuple:
        """The attempt's anchor and record of the replay, and the generation's candidate and takeover."""
        durable = self._durable()
        return tuple(durable.get(key) for key in _HOLDERS)
