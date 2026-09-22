# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The live fixing route a round that reports takes, driven as whole ticks.

One world for all of it: an in_review-route round that wrote its report and
whose push MISSED. What that leaves is the shape every road here answers -- a
delivered record carrying the pairs the run consumed and the round its route
owes, a `push_failed` park, and readers that still say the triggering comment
is unread, because a reporting round's readers ride the report rather than the
tick.

The point of driving whole ticks is what the owner-level cases beside this
cannot show: that nothing between the scan and the resume pays a SECOND
developer to answer the batch the outstanding report already answers, and that
the roads which can end that wait -- the silent retry of the push, a reply
above the record's own pairs -- still run.
"""

from __future__ import annotations

import unittest

from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import report_record_state as _record_state
from tests.workflow.stages.fixing import (
    fixing_test_support as support,
    report_crash_support as crash,
)
from tests.workflow.stages.fixing.prompt_expectations import (
    only_prompt,
    pr_feedback_prompt,
    spawned_nobody,
)

ALICE = support.ALICE
AWAITING_HUMAN = support.AWAITING_HUMAN
ISSUE = support.ISSUE
LAST_ACTION_COMMENT_ID = support.LAST_ACTION_COMMENT_ID
PARK_PUSH_FAILED = support.PARK_PUSH_FAILED
PARK_REASON = support.PARK_REASON
PENDING_FIX_AT = support.PENDING_FIX_AT
PR_LAST_COMMENT_ID = support.PR_LAST_COMMENT_ID
PUSH_BRANCH = support.PUSH_BRANCH
REVIEW_ROUND = support.REVIEW_ROUND
SHA_AFTER = support.SHA_AFTER
SHA_BEFORE = support.SHA_BEFORE
TEMP_ROOT = support.TEMP_ROOT
TRIGGER_ID = support.TRIGGER_ID
VALIDATING = support.VALIDATING
WORKTREE_PATH = support.WORKTREE_PATH

# What a later human writes, above everything the owed record accounts for.
_LATER_FEEDBACK = "and rename the helper while you are in there"

# The reply that acknowledges without changing anything. It is refused here
# for one reason only: the issue OWES a report, and handing the pull request
# back as needing nothing would present it while the report it owes is still
# on the pinned comment and nothing has gone out.
_ACK_REPLY = "ACK: the comments name no actionable change."

# What the reviewer of a LATER round is owed, which no publication of the
# earlier round's report is an answer to.
_PARK_AGENT_TIMEOUT = support.PARK_AGENT_TIMEOUT

# The commit a round resumed over a standing record leaves on the branch. The
# report already owed was written before it existed, so nothing may publish
# that report against this head.
_UNDESCRIBED_SHA = "9d" * (support.SHA_LENGTH // 2)

# The reviewer feedback the validating route anchors its replay to, which is
# also the route whose transient parks the silent recovery may answer.
_REVIEWER_ANCHOR_ID = 1_500


def _pinned(scenario) -> dict:
    """What the pinned comment carries after the tick this case just ran."""
    return scenario.github.pinned_data(ISSUE)


def _parked_under(scenario):
    """The reason the issue is waiting on a human under, or None."""
    return scenario.github.pinned_data(ISSUE).get(PARK_REASON)


def _reply(comment_id: int, body: str):
    """One trusted human comment, old enough to clear the quiet window."""
    return support.FakeComment(
        id=comment_id,
        body=body,
        user=support.FakeUser(ALICE),
        created_at=support.now_utc() - support.timedelta(hours=1),
    )



def _lands_a_later_reply(scenario, *, on_the_pull_request: bool = False):
    """One reply above every id the owed record accounts for.

    Minted through the client rather than hand-numbered: the round before it
    posted its own park notice out of the same ascending space, so a fixed id
    would repeat one a reader here hides.

    `on_the_pull_request` puts it on the thread the requirements a report is
    stamped with do NOT cover: a reply on the issue moves them, and the
    settlement then declines to publish a report answering content the run
    never saw -- a different refusal from the ones these cases are about.
    """
    later = _reply(
        scenario.github.next_reply_id(scenario.issue), _LATER_FEEDBACK,
    )
    if on_the_pull_request:
        scenario.github.get_pr(support.PR_NUMBER).issue_comments.append(later)
    else:
        scenario.issue.comments.append(later)
    return later


def _validating_round_whose_push_missed(case):
    """A validating-route round that reported and could not publish.

    The route matters: its transient parks are the ones the silent
    recovery answers with nobody commenting, so it is the route on which a
    later round's timeout is retried -- and pushed -- without a reply.
    """
    pr = case._open_pr()
    pr.issue_comments.append(
        _reply(support.TRIGGER_ID, support.FIX_FEEDBACK),
    )
    scenario = support.IssueScenario(*case._seed(
        pr=pr,
        extra_state={
            PENDING_FIX_AT: None,
            support.PENDING_FIX_ISSUE_MAX_ID: None,
            support.PENDING_FIX_REVIEWER_COMMENT_ID: _REVIEWER_ANCHOR_ID,
        },
    ))
    case._tick(scenario, push_branch=False)
    case.assertEqual(_parked_under(scenario), PARK_PUSH_FAILED)
    case.assertIsNotNone(
        crash.frozen_record(PinnedState(state_data=_pinned(scenario))),
    )
    return scenario


def _round_whose_push_missed(case):
    """One in_review-route round that reported and could not publish."""
    scenario = support.IssueScenario(*case._seed(
        pr=case._open_pr(),
        issue_comments=[_reply(TRIGGER_ID, support.FIX_FEEDBACK)],
    ))
    case._tick(scenario, push_branch=False)
    pinned = _pinned(scenario)
    case.assertEqual(pinned[PARK_REASON], PARK_PUSH_FAILED)
    case.assertEqual(
        crash.frozen_record(PinnedState(state_data=pinned)).watermarks,
        (
            (LAST_ACTION_COMMENT_ID, TRIGGER_ID),
            (PR_LAST_COMMENT_ID, TRIGGER_ID),
        ),
    )
    return scenario


class OwedReportRouteTest(unittest.TestCase, support._FixingFixtureMixin):
    """What the tick after a report whose push missed does, and does not do."""

    def test_a_retried_push_publishes_the_report(self) -> None:
        # The park says a push failed and this tick is that push landing. The
        # readers, the round and the bookmarks are all frozen on the record,
        # so the retry is handed nothing to count -- and the write that
        # completes the publication applies every one of them. The commit it
        # binds to is the one THIS attempt's receipt names, never the standing
        # value, which on a tick that pushed nothing is an older round's.
        #
        # The park comes down with the hand-back rather than being relabelled
        # over: the receipt is durable a step ahead of the publication, so a
        # tick dying in between leaves the issue on `fixing` still saying a
        # human is owed an answer.
        scenario = _round_whose_push_missed(self)

        mocks = self._tick(scenario, push_branch=True, head_shas=(SHA_AFTER,))

        spawned_nobody(mocks)
        mocks[PUSH_BRANCH].assert_called_once()
        pinned = _pinned(scenario)
        self.assertEqual(
            (pinned[AWAITING_HUMAN], pinned[PARK_REASON]), (False, None),
        )
        self.assertEqual(
            scenario.github.label_history[-1], (ISSUE, VALIDATING),
        )
        # Everything the record was carrying, applied by that one write: the
        # in_review route's reset, its bookmarks, and the batch the round
        # answered.
        self.assertEqual(
            (pinned[REVIEW_ROUND], pinned[PENDING_FIX_AT],
             pinned[PR_LAST_COMMENT_ID], pinned[LAST_ACTION_COMMENT_ID]),
            (0, None, TRIGGER_ID, TRIGGER_ID),
        )
        self.assertIsNone(
            crash.frozen_record(PinnedState(state_data=pinned)),
        )

    def test_a_later_reply_still_resumes_a_developer(self) -> None:
        # The other side of the same reading. What holds a park closed is the
        # record's own frozen pairs, and a comment ABOVE them is genuinely
        # unanswered feedback: the park clears and a developer runs.
        #
        # What it is handed is the whole batch the readers still call unread,
        # because those readers are held until the publication lands. The
        # record gates the SCAN rather than trimming the prompt: a round asked
        # to answer the later comment on its own would be answering it over a
        # pull request whose report of the earlier one nothing has published.
        scenario = _round_whose_push_missed(self)
        later = _lands_a_later_reply(scenario)
        triggering = scenario.issue.comments[0]

        mocks = self._tick(
            scenario, push_branch=False, head_shas=(SHA_AFTER,),
        )

        self.assertEqual(
            only_prompt(mocks), pr_feedback_prompt([triggering, later]),
        )

    def test_an_ack_does_not_discharge_the_debt(self) -> None:
        # An `ACK:` says the feedback needs no change, and a round standing on
        # a report an earlier tick could not deliver may not be read that way:
        # returning the pull request to `in_review` would present it as needing
        # nothing while the report it owes is still on the pinned comment. The
        # debt is read off the RECORD rather than off this run, so a reply that
        # wrote no report of its own is refused too.
        scenario = _round_whose_push_missed(self)
        _lands_a_later_reply(scenario)

        self._tick(
            scenario,
            push_branch=False,
            run_agent=support._agent(
                session_id=support.DEV_SESSION, last_message=_ACK_REPLY,
            ),
            head_shas=(SHA_AFTER, SHA_AFTER),
        )

        pinned = _pinned(scenario)
        self.assertNotIn(
            (ISSUE, support.IN_REVIEW_LABEL), scenario.github.label_history,
        )
        self.assertIsNotNone(
            crash.frozen_record(PinnedState(state_data=pinned)),
        )

    def test_a_newer_park_outlives_an_older_report(self) -> None:
        # The park a publication ANSWERS is the one its own push filed, and
        # nothing wider. Here a second round runs over feedback that arrived
        # after the report was written -- on the pull request, so the
        # requirements the report answers have not moved -- and that round
        # times out, leaving an `agent_timeout` park and the later feedback
        # already recorded as delivered. When the commit the FIRST report
        # describes then turns up on the pull request, the recovery binds and
        # publishes it and hands the round back.
        #
        # What it may not do is take the second round's park down on the way.
        # That notice is about a session nobody has heard from, which this
        # publication says nothing about, and the feedback behind it is
        # consumed -- so a tick that cleared it would leave the issue with no
        # road back to a developer at all.
        scenario = _round_whose_push_missed(self)
        _lands_a_later_reply(scenario, on_the_pull_request=True)
        self._tick(
            scenario,
            push_branch=False,
            run_agent=support._agent(timed_out=True),
            head_shas=(SHA_AFTER,),
        )
        self.assertEqual(
            _parked_under(scenario), _PARK_AGENT_TIMEOUT,
        )

        # Somebody else's push puts the reported commit on the pull request.
        scenario.github.get_pr(support.PR_NUMBER).head.sha = SHA_AFTER
        mocks = self._tick(scenario, push_branch=False, head_shas=(SHA_AFTER,))

        spawned_nobody(mocks)
        pinned = _pinned(scenario)
        self.assertIsNone(
            crash.frozen_record(PinnedState(state_data=pinned)),
        )
        self.assertEqual(
            (pinned[AWAITING_HUMAN], pinned[PARK_REASON]),
            (True, _PARK_AGENT_TIMEOUT),
        )

    def test_a_timed_out_commit_is_no_subject_here(self) -> None:
        # The round that reported could not push, so its report is still owed
        # and describes the branch as THAT run left it. A later round commits
        # on top and then times out -- and the park a timeout earns has a
        # recovery that PUSHES what the run left, on the route where that
        # recovery runs without a human.
        #
        # So the work is recorded as undescribed the moment it appears: a
        # timeout is a way to commit like any other, and the head is read for
        # exactly this reason. Left unread, the commit reaches the pull request
        # and the road that publishes reads only the debt -- which the earlier
        # report still satisfies -- so a reviewer is handed a head under a
        # report written before the code existed.
        scenario = _validating_round_whose_push_missed(self)
        _lands_a_later_reply(scenario, on_the_pull_request=True)

        self._tick(
            scenario,
            push_branch=False,
            run_agent=support._agent(timed_out=True),
            # Three readings: the recovery ahead of the scan re-proves the
            # checkout for the record it is holding, and the run reads the
            # head on either side of itself.
            head_shas=(SHA_AFTER, SHA_AFTER, _UNDESCRIBED_SHA),
        )

        parked = _pinned(scenario)
        self.assertTrue(parked[crash.UNREPORTED_WORK])
        self.assertIsNotNone(
            crash.frozen_record(PinnedState(state_data=parked)),
        )

        # And the tick behind it, on the road that would otherwise publish:
        # the report stays a DELIVERY -- unbound, still owed, and never made
        # to describe a commit it was written before. What refuses there is
        # the flag above, which every publishing road reads before it binds
        # anything (`test_report_settlement` pins that refusal itself).
        self._tick(
            scenario,
            push_branch=True,
            head_shas=(_UNDESCRIBED_SHA,),
            branch_ahead_behind=(1, 0),
            fetched_branch_tip=support.PR_HEAD_SHA,
        )

        pinned = _pinned(scenario)
        self.assertIsNotNone(
            crash.frozen_record(PinnedState(state_data=pinned)),
        )
        self.assertIsNone(
            _record_state.read_pending_report(PinnedState(state_data=pinned)),
        )
        self.assertEqual(scenario.github.posted_pr_comments, [])

    def _tick(self, scenario, **run_options):
        """One whole fixing tick over a checkout this host really holds."""
        run_options.setdefault(
            "run_agent",
            support._agent(
                session_id=support.DEV_SESSION,
                last_message=support.PUSHED_FIX_MESSAGE,
            ),
        )
        run_options.setdefault("head_shas", (SHA_BEFORE, SHA_AFTER))
        with support.patch.object(
            support.config, support.DEBOUNCE_CONFIG, support.DEBOUNCE_SECONDS,
        ), support.patch.object(
            support.worktree_paths, WORKTREE_PATH, return_value=TEMP_ROOT,
        ):
            return self._run_fixing(
                scenario.github, scenario.issue, **run_options,
            )


if __name__ == "__main__":
    unittest.main()
