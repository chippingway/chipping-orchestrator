# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What an operator wrote while a developer was running, and who consumes it.

Every other window on this park is between two of one tick's own steps, and
each is closed by asking its question once. This one is not: an agent takes
minutes, nothing reads the thread again while it does, and the park that ends
the run is the next thing to write down how far the thread has been read.

Stamped to whatever the thread ENDS on, that write is the notice the park just
posted -- above anything a human wrote during the run, which is then skipped
for good. On this stage the comment skipped can be the
`/orchestrator authorize-oversized` an adjudicated candidate is still waiting
for, and the road that could act on it never sees it.
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from orchestrator import config
from orchestrator.workflow.engine import (
    comments as _comments,
    park_watermarks as _park_watermarks,
    pickup as _pickup,
)
from orchestrator.workflow.stages.implementing import state as _state
from tests.support.fakes import FakeComment, FakeGitHubClient, FakeUser, make_issue
from tests.workflow.fixtures import (
    _TEST_SPEC,
    LABEL_IMPLEMENTING,
    _agent,
    _PatchedWorkflowMixin,
)
from tests.workflow.stages.implementing import (
    late_consent_case as _consent_case,
    late_consent_payloads as _consent_payloads,
)

# What the agent comes back with: words, and no commit unless a case seeds
# one. Both parks under test are ends a run reaches without publishing.
_ASKS = "which of the two did you mean?"

# One issue of this stage's own, for the two answers a whole tick cannot
# reach: a post nothing named, and a thread nobody has read yet.
_ISSUE_NUMBER = 614
_AUTHOR = "alice"
_SAID = "one comment on the thread"

# The issue nobody has picked up yet, for the one run that has no watermark
# under it until the pickup writes one.
_FRESH_ISSUE_NUMBER = 615

# The client read a park re-takes after posting its notice, and what a
# transient failure of it says.
_COMMENTS_AFTER = "comments_after"
_BAD_GATEWAY = "502 Bad Gateway"
_POST = "comment"
_RUN_AGENT = "run_agent"
_DECOMPOSE = "DECOMPOSE"
_PICKUP_COMMENT_ID = "pickup_comment_id"


class _RunsWhileOneLands:
    """A developer run one comment lands during, ending in a question.

    The run is where the window is -- minutes on a real host -- and what a
    case here needs is one comment written inside them. A class rather than a
    closure because the runner this repository patches is a value with a name.

    An empty `said` lands nothing, which is the ordinary tick every bound here
    has to leave alone.
    """

    def __init__(
        self,
        case,
        said: str = _consent_payloads.AUTHORIZE,
        *,
        timed_out: bool = False,
    ) -> None:
        self._case = case
        self._said = said
        self._timed_out = timed_out
        self.landed = 0

    def __call__(self, *called, **options):
        if self._said:
            self.landed = self._case._reply(self._said)
        if self._timed_out:
            return _agent(timed_out=True)
        return _agent(last_message=_ASKS)


class _ReadFailsOnceAfterAPost:
    """The client read that fails once, the first time it follows a post.

    A class rather than a closure because two client methods share its state:
    the post that arms it and the read it fails. What it stands for is the
    request a park re-takes after its notice is on the thread, failing the one
    time that matters.
    """

    def __init__(self, github) -> None:
        self._post = github.comment
        self._read = github.comments_after
        self._armed = False
        self.failed = 0

    def comment(self, *called, **options):
        self._armed = True
        return self._post(*called, **options)

    def comments_after(self, *called, **options):
        if self._armed and not self.failed:
            self.failed += 1
            raise RuntimeError(_BAD_GATEWAY)
        return self._read(*called, **options)


class RunWindowWatermarkTest(_consent_case._ParkedCase, unittest.TestCase):
    """How far a park ending a run may record this thread as read.

    Past its own notice, so the next tick does not answer our own sentence as
    somebody's guidance, and past nothing else: what landed behind this tick's
    back was never read by it, and the watermark is the only record of that.
    """

    def test_a_command_landing_mid_run_is_kept(self) -> None:
        # The question park, which is where a run with no commit and words to
        # say ends up. Guidance hands the tick to the ordinary resume, the
        # resume consumes it and spawns a developer, and the corrected command
        # is written while that developer runs.
        guided, landing = self._runs_over_guidance()

        self._assert_read_only_to(guided)
        self.assertLess(guided, landing.landed)

    def test_a_timed_out_run_keeps_what_landed(self) -> None:
        # The other end a run with no commit reaches. A timeout is a run that
        # ENDED after minutes of somebody's compute, so its park owes the same
        # bound the question park does -- and the recovery that retries it
        # fires only on a thread with nothing new, so a watermark carried over
        # the reply would answer that reply with a rerun that never saw it.
        guided, landing = self._runs_over_guidance(timed_out=True)

        self._assert_read_only_to(guided)
        self.assertEqual(self._pinned()[_state._PARK_REASON], _state._AGENT_TIMEOUT)
        self.assertLess(guided, landing.landed)

    def test_a_quiet_run_reads_past_its_own_notice(self) -> None:
        # What the bound may not cost, on the ordinary tick nobody wrote
        # anything during: the park's own notice still has to carry the
        # watermark over itself, or every poll after this one answers our own
        # sentence as somebody's fresh guidance and pays a developer to do it.
        guided, _ = self._runs_over_guidance(said="")

        self.assertGreater(
            self._pinned()[_state._LAST_ACTION_COMMENT_ID], guided,
        )

    def test_a_failed_reread_still_records_the_park(self) -> None:
        # The question park posts its notice and then re-reads the thread for
        # how far it may record it read. Failing there costs that advance and
        # nothing else: the park is written, so the poll after this one finds
        # the question standing -- no second agent, no second notice.
        self._seed(**_consent_payloads.measured_pair())
        self._reply(_consent_payloads.GUIDANCE)
        flaky = _ReadFailsOnceAfterAPost(self.github)

        with (
            patch.object(self.github, _POST, flaky.comment),
            patch.object(self.github, _COMMENTS_AFTER, flaky.comments_after),
        ):
            self._run_tick(run_agent=_agent(last_message=_ASKS), has_new_commits=False)
        said = len(self.github.posted_comments)
        polled = self._run_tick(
            run_agent=_agent(last_message=_ASKS), has_new_commits=False,
        )

        self.assertEqual(flaky.failed, 1)
        self.assertTrue(self._pinned()[_state._AWAITING_HUMAN])
        polled[_RUN_AGENT].assert_not_called()
        self.assertEqual(len(self.github.posted_comments), said)

    def _assert_read_only_to(self, guided: int) -> None:
        """The tick read the guidance it was resumed on, and nothing past it."""
        self.assertEqual(
            self._pinned()[_state._LAST_ACTION_COMMENT_ID], guided,
        )
        self.assertTrue(self._pinned()[_state._AWAITING_HUMAN])

    def _runs_over_guidance(
        self,
        said: str = _consent_payloads.AUTHORIZE,
        *,
        timed_out: bool = False,
    ):
        """One whole tick: guidance resumes a developer, and a reply lands."""
        self._seed(**_consent_payloads.measured_pair())
        guided = self._reply(_consent_payloads.GUIDANCE)
        landing = _RunsWhileOneLands(self, said, timed_out=timed_out)
        self._run_tick(
            run_agent=MagicMock(side_effect=landing), has_new_commits=False,
        )
        return guided, landing


class ReadThisFarFallbackTest(unittest.TestCase):
    """The two answers no walk can reach, and why neither of them is the tip.

    A notice nothing identified advances the mark nowhere: what may be
    advanced through is a comment actually posted and identified, and taking
    the tip for one that was not would spend the comment a human wrote while
    the agent ran. A thread with no watermark is the same answer for the same
    reason -- it is tempting to read the tip there, since the spawn behind
    such a tick quoted the whole thread, but the tip is also exactly where the
    comment written DURING that run is, and no id tells the two apart.
    """

    def setUp(self) -> None:
        self.github = FakeGitHubClient()
        self.issue = make_issue(_ISSUE_NUMBER, label=LABEL_IMPLEMENTING)
        self.github.add_issue(self.issue)
        self.github.seed_state(_ISSUE_NUMBER)
        self.state = self.github.read_pinned_state(self.issue)

    def test_a_post_nothing_named_moves_nothing(self) -> None:
        # The ledger gained nothing, so no id came back from the post. The
        # mark stays on the reply the resume settled to, and our own
        # unrecorded sentence above it is refused by the frozen reply batch --
        # which drops a body carrying our marker that no id vouches for --
        # rather than by a watermark that skipped it along with everyone else.
        settled = self._reply()
        self.state.set(_state._LAST_ACTION_COMMENT_ID, settled)
        self._reply()

        said_before = _comments._orchestrator_ids(self.state)

        self.assertIsNone(self._read_this_far(said_before))
        self.assertEqual(
            self.state.get(_state._LAST_ACTION_COMMENT_ID), settled,
        )

    def test_a_thread_never_read_moves_nothing(self) -> None:
        # The post itself landed here, which is what separates this from the
        # answer above -- and it still buys no advance, because the walk has
        # nothing under it to start from. Reading the tip instead would cross
        # the reply a human wrote while the agent was out; leaving the mark
        # unset costs one redundant resume over conversation that agent has
        # already been handed, which the settlement then records for good.
        said_before = _comments._orchestrator_ids(self.state)
        _comments._track_orchestrator_comment(self.state, self._reply())
        self._reply()

        self.assertIsNone(self._read_this_far(said_before))

    def test_a_thread_it_cannot_reread_moves_nothing(self) -> None:
        # Asked after the notice is posted and before the park is written, so
        # a raise here would strand the park with its notice already said.
        settled = self._reply()
        self.state.set(_state._LAST_ACTION_COMMENT_ID, settled)
        said_before = _comments._orchestrator_ids(self.state)
        _comments._track_orchestrator_comment(self.state, self._reply())

        with patch.object(
            self.github, _COMMENTS_AFTER, side_effect=RuntimeError(_BAD_GATEWAY),
        ):
            self.assertIsNone(self._read_this_far(said_before))

    def _read_this_far(self, said_before) -> int | None:
        return _park_watermarks._read_this_far(
            self.github, self.issue, self.state, said_before,
        )

    def _reply(self) -> int:
        identified = self.github.next_reply_id(self.issue)
        self.issue.comments.append(
            FakeComment(identified, _SAID, user=FakeUser(_AUTHOR)),
        )
        return identified


class _WritesWhileTheFirstRunIsOut:
    """The first agent an issue ever pays for, with one reply written into it.

    A class rather than a closure because the runner this repository patches
    is a value with a name, and this window is the one a fresh issue has no
    watermark under: what the pickup wrote is the only floor the park that
    ends this run can walk from.
    """

    def __init__(self, github, issue) -> None:
        self._github = github
        self._issue = issue
        self.landed = 0

    def __call__(self, *called, **options):
        self.landed = self._github.next_reply_id(self._issue)
        self._issue.comments.append(
            FakeComment(self.landed, _SAID, user=FakeUser(_AUTHOR)),
        )
        return _agent(last_message=_ASKS)


class FirstRunWindowTest(_PatchedWorkflowMixin, unittest.TestCase):
    """The window under the very first agent run, which has no prior mark.

    Every other bound on this road walks from a watermark some earlier tick
    settled. This one has none until the pickup writes it, and what the pickup
    posts is the last word of the reading its own spawn prompt carried -- so
    the park that ends that first run can stop below whatever a human wrote
    while the agent was out, rather than crossing it with the thread's tip.
    """

    def test_a_reply_during_the_first_run_is_kept(self) -> None:
        github = FakeGitHubClient()
        issue = make_issue(_FRESH_ISSUE_NUMBER)
        github.add_issue(issue)
        landing = _WritesWhileTheFirstRunIsOut(github, issue)

        with patch.object(config, _DECOMPOSE, False):
            self._run(
                lambda: _pickup._handle_pickup(github, _TEST_SPEC, issue),
                run_agent=MagicMock(side_effect=landing),
                has_new_commits=False,
            )

        pinned = github.pinned_data(_FRESH_ISSUE_NUMBER)
        self.assertEqual(
            pinned[_state._LAST_ACTION_COMMENT_ID], pinned[_PICKUP_COMMENT_ID],
        )
        self.assertLess(
            pinned[_state._LAST_ACTION_COMMENT_ID], landing.landed,
        )
        self.assertTrue(pinned[_state._AWAITING_HUMAN])


if __name__ == "__main__":
    unittest.main()
