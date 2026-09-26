# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""One oversized candidate on a real repository, for a journey to walk.

The adjudicated fixture beside this one WRITES the verdict a rebase then
carries; this one is where a journey earns it. The branch carries a change the
real counter reads past a small ceiling, and the ticks a journey drives over it
are the production ones: the size gate, the adjudicator and the operator's
command, the base refresh, and the reviewer.

What is stood in for decides nothing: the agents' replies, the report the
delivery would have published, the authenticated push and branch fetch, and the
remote-side base freeze these fixtures have no token to take.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from orchestrator import config
from orchestrator.agents import runner as _agent_runner
from orchestrator.git import branch_transport as _branch_transport
from orchestrator.git.measurement import additions as _additions
from orchestrator.workflow.stages.validating import handler as _validating
from tests.git.base_sync.exemption_git_support import ISSUE, AdjudicatedRebaseRealGitFixture
from tests.git.base_sync.journey_push_support import PUSH_BRANCH, PublishesToThePullRequest, crash_at
from tests.git.base_sync.real_git_test_support import (
    ADD_COMMAND,
    ORIGIN_REMOTE,
    PR_BRANCH,
    PUSH_COMMAND,
    WORKTREES_DIR_NAME,
)
from tests.git.base_sync.recovery_git_support import _local_fetch
from tests.workflow.fixtures import LABEL_VALIDATING, REVIEW_APPROVED_MESSAGE, _agent, publishes_the_report

# The ceiling the candidate is oversized against and the file that puts it
# there: small enough to keep the real diff cheap, large enough that the real
# counter crosses the ceiling on the real objects.
JOURNEY_CEILING = 20
JOURNEY_FILE = "oversized.py"
JOURNEY_LINES = 200

# The one account trusted to answer the adjudication's park.
OPERATOR = "operator"

# The line counter before the shared base-sync doubles replace it, put back
# because a journey about an OVERSIZED candidate has to really cross the ceiling.
_REAL_ADDITION_COUNT = _additions._count_added_lines


class OversizedJourneyRealGitFixture(AdjudicatedRebaseRealGitFixture):
    """A branch whose head adds past the ceiling, and the ticks that act on it."""

    def setUp(self) -> None:
        super().setUp()
        # The recovery fetches the pull request's own branch before it compares
        # anything, answered against the bare repository that IS the remote;
        # the adjudicator fingerprints the pair in the checkout the configured
        # root names, and this journey's is the real one.
        for owner, name, replacement in (
            (_branch_transport, "_authed_fetch", _local_fetch),
            (_additions, "_count_added_lines", _REAL_ADDITION_COUNT),
            (config, "MAX_ADDED_LINES", JOURNEY_CEILING),
            (config, "ALLOWED_ISSUE_AUTHORS", (OPERATOR,)),
            (config, "WORKTREES_DIR", self._tmpdir / WORKTREES_DIR_NAME),
        ):
            self.enterContext(patch.object(owner, name, replacement))

    def _commits_an_oversized_candidate(self) -> str:
        """Put a change past the ceiling on the branch and open its review."""
        (self._wt / JOURNEY_FILE).write_text(
            "".join(f"value_{line} = {line}\n" for line in range(JOURNEY_LINES)),
        )
        self._git(ADD_COMMAND, ".", cwd=self._wt)
        self._git(
            "commit", "-m", "feat: add the oversized change",
            cwd=self._wt, env_extra=self._author_env,
        )
        self._git(PUSH_COMMAND, ORIGIN_REMOTE, PR_BRANCH, cwd=self._wt)
        self._open_pull_request(label=LABEL_VALIDATING)
        return self._wt_head()

    def _refreshes(self, window: str = "") -> PublishesToThePullRequest:
        """Run one refresh, lost at `window` if one is named, and report its push.

        Nothing is asserted about the raise. The refresh treats one worktree's
        failure as that worktree's -- it logs and moves on -- so what the tick
        leaves behind is the durable state a process death would. The push
        double goes on first and the seam second, so a window about the
        transport replaces it.
        """
        pusher = PublishesToThePullRequest(self._gh)
        with patch.object(_branch_transport, PUSH_BRANCH, pusher), crash_at(self._gh, window):
            self._refresh()
        return pusher

    def _reviews(self) -> MagicMock:
        """Run one real `workflow:validating` tick and report its spawn.

        The handler itself, with only the reviewer agent stood in for: the
        drift read, the round cap, the prompt, the verdict parse, and what an
        approval earns are the production ones, over the rewritten checkout.
        The pull request carries a report of the head it stands on, since a
        reviewer is refused one that carries none.
        """
        publishes_the_report(self._gh, self._issue())
        spawn = MagicMock(return_value=_agent(last_message=REVIEW_APPROVED_MESSAGE))
        with patch.object(_agent_runner, "run_agent", spawn), patch.object(
            _branch_transport, PUSH_BRANCH, PublishesToThePullRequest(self._gh),
        ):
            _validating._handle_validating(self._gh, self._spec, self._issue())
        return spawn

    def _issue(self):
        """The journey's issue as the client holds it."""
        return self._gh._issues[ISSUE]

    def _durable(self):
        """The pinned comment as a process starting now would read it."""
        return self._gh.read_pinned_state(self._issue())

    def _issue_comments(self) -> list[str]:
        """Every comment the workflow posted on the issue thread."""
        return [
            body for number, body in self._gh.posted_comments
            if number == ISSUE
        ]
