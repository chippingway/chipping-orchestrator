# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The live fixing roads a report obligation runs through, tick by tick.

What one helper's answer cannot say: the ORDER a fixing tick asks its questions
in. A report an earlier tick recorded is answered ahead of the scan, because the
scan is what the damage runs through -- the readers are held back until the
publication lands, so the batch that report was written over reads as unread and
a second developer is paid to answer it. A park whose retry is that publication
clears on the push rather than on a human. And a relabel is the settlement's to
authorize through the mark it raised, never the settling itself.

The refusals are here for the same reason. A checkout this host cannot publish
from is answered once, with the record RELEASED so restoring it is not enough on
its own to send a report to review; a status nobody could read is not that
refusal and holds everything where it stands.
"""
from __future__ import annotations

import unittest
from types import MappingProxyType

from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    report_delivery as _report_delivery,
    report_records as _records,
    report_settlement_state as _settlement,
)
from orchestrator.workflow.state import WorkflowLabel
from tests.workflow.stages.fixing import (
    fixing_test_support as live,
    report_crash_support as crash,
    report_settlement_support as support,
)
from tests.workflow.stages.fixing.prompt_expectations import (
    only_prompt,
    pr_feedback_prompt,
    spawned_nobody,
)
from tests.workflow.stages.implementing_fixing_test_cases import (
    posted_comment_contains,
)

# A phrase out of the notice a checkout no road can publish from earns.
_UNPUBLISHABLE_PHRASE = "cannot say whether the code it describes got there"

# The pinned field a recorded, unbound report stands on.
_DELIVERED_REPORT = "developer_report_delivery"

# The park reason somebody else's question left standing.
_ASKED_A_QUESTION = "agent_question"

# What a developer says on these roads, and the feedback each round is over.
_REPORTED = live.PUSHED_FIX_MESSAGE
_THE_FEEDBACK = "please rename the helper"
_LATER_FEEDBACK = "one more thing: and its test"

# A reply that lands AFTER the crash, numbered clear of the report the
# recovery publishes: a comment sharing that id reads as one of ours.
_LATER_ID = live.HUMAN_REPLY_ID

# Where the two readers a batch on the issue thread moves stand before the
# round, so "held" and "settled" are concrete numbers rather than an absence.
_SEEDED_READERS = MappingProxyType({
    live.LAST_ACTION_COMMENT_ID: live.HISTORICAL_COMMENT_ID,
    live.PR_LAST_COMMENT_ID: live.INITIAL_PR_COMMENT_WATERMARK,
})

# The route bookkeeping a fix round freezes onto its record: the bookmarks the
# consumed batch clears, the reviewer round it lands on, and the mark that says
# a fixing round is what settled.
_FROZEN_SPENDS = (
    (live.PENDING_FIX_AT, None),
    (live.PENDING_FIX_ISSUE_MAX_ID, None),
    (live.REVIEW_ROUND, 0),
    (support.SETTLED_ROUND, True),
)

# The two run options a case seeds a checkout reading through.
_TREE_STATES = "tree_states"
_HEAD_SHAS = "head_shas"

# The two checkout readings no later poll takes back, and how a case puts this
# host into each: a worktree that is GONE (no real checkout at all) and a tree
# this host PROVED dirty.
_DEFINITE_REFUSALS = MappingProxyType({
    "is no longer on this host": None,
    "is carrying uncommitted changes": {
        _TREE_STATES: (crash.a_tree(paths=("stray.py",)),),
    },
})

# The two readings a report-only round holds on rather than parking under,
# and the one it ends on. A tree carrying something is PROVED, which no later
# poll takes back; a status that established nothing and a head the checkout
# would not name are about the tick alone.
_UNREAD_TREE = "a tree status nobody could take"

_UNREAD_HEAD = "a head the checkout would not name"

_TRANSIENT_READS = MappingProxyType({
    _UNREAD_TREE: {_TREE_STATES: (crash.a_tree(readable=False),)},
    _UNREAD_HEAD: {_HEAD_SHAS: (live.PR_HEAD_SHA, "")},
})

# The same two readings asked of the RECOVERY, which has no run in front of
# it: every probe it takes is the first one, so the head answers unreadable
# from the start rather than after a round moved off a readable one.
_UNREAD_CHECKOUTS = MappingProxyType({
    _UNREAD_TREE: {_TREE_STATES: (crash.a_tree(readable=False),)},
    _UNREAD_HEAD: {_HEAD_SHAS: ("",)},
})

_DIRTY_CHECKOUT = MappingProxyType(
    {_TREE_STATES: (crash.a_tree(paths=("stray.py",)),)},
)

# What every road that cannot move a report parks under.
_UNDELIVERABLE = _report_delivery.UNDELIVERABLE_REPORT


def _reply(comment_id: int, body: str):
    """One human comment on the issue thread, settled past the debounce."""
    return live.FakeComment(
        id=comment_id,
        body=body,
        user=live.FakeUser(live.ALICE),
        created_at=live.now_utc() - live.timedelta(hours=1),
    )


def _records_a_foreign_delivery(seeded) -> None:
    """Re-record this issue's delivery as a route that is NOT this stage's.

    One key claims a delivery whoever wrote it, so the record that settles on
    a fixing tick can be an implementing candidate's or a drift resume's --
    closing bookkeeping of its own and raising no mark this stage could hand a
    round back on.
    """
    state = seeded.github.read_pinned_state(seeded.issue)
    delivered = dict(state.get(_DELIVERED_REPORT))
    delivered["route"] = str(WorkflowLabel.VALIDATING)
    delivered["spends"] = []
    state.set(_DELIVERED_REPORT, delivered)
    seeded.github.write_pinned_state(seeded.issue, state)


def _records_a_handoff(seeded, *, under: WorkflowLabel) -> None:
    """Leave the handoff a settlement under `under` records beside its mark."""
    state = seeded.github.read_pinned_state(seeded.issue)
    _settlement.record_handoff(state, _records.ReportHandoff(
        receipt=f"issue-{live.ISSUE}-report-1",
        pr_number=live.PR_NUMBER,
        report_revision=1,
        source_sha=live.PR_HEAD_SHA,
        settled_under=under,
    ))
    seeded.github.write_pinned_state(seeded.issue, state)


class LiveReportRoundMixin(live._FixingFixtureMixin):
    """One dispatched fixing tick over a round that owes its report."""

    def seed(self, *, crashed: bool = False, landed: str = "", **extra):
        """A `fixing` issue on the in_review route, one reply unread.

        `crashed` seeds what a tick that died past the recording left behind:
        the report, the pairs its run consumed, and the route bookkeeping it
        froze. `landed` is the code-publication receipt a crash AFTER the push
        leaves beside it, and its absence is the crash before one.
        """
        seeded = live.IssueScenario(*self._seed(
            pr=self._open_pr(),
            issue_comments=[_reply(live.TRIGGER_ID, _THE_FEEDBACK)],
            extra_state={**_SEEDED_READERS, **extra},
        ))
        if crashed:
            crash.recorded_delivery(
                seeded, _SEEDED_READERS, live.TRIGGER_ID,
                landed=landed, spends=_FROZEN_SPENDS,
            )
        return seeded

    def tick(self, seeded, *, message: str = "", head: str = "", **options):
        """One whole fixing tick, over a checkout that is really there.

        The checkout is real because that is exactly what every report road
        re-proves, and `head` is what it answers -- the pull request's own
        commit for a push that landed, anything else for one a crash left
        unpublished. `message` is what the developer says where a tick reaches
        one at all, and its absence is a tick that must reach none.
        """
        standing = head or live.PR_HEAD_SHA
        options.setdefault("head_shas", (standing, standing))
        with crash.on_a_real_checkout(), live.patch.object(
            live.config, live.DEBOUNCE_CONFIG, live.DEBOUNCE_SECONDS,
        ):
            return self._run_fixing(
                seeded.github, seeded.issue, run_agent=live._agent(
                    session_id=live.DEV_SESSION, last_message=message,
                ), **options,
            )

    def pinned(self, seeded) -> dict:
        """What this issue's pinned comment says after the tick."""
        return seeded.github.pinned_data(live.ISSUE)

    def handed_back(self, seeded) -> bool:
        """Whether the reviewer was given the head back."""
        return (live.ISSUE, WorkflowLabel.VALIDATING) in (
            seeded.github.label_history
        )


class LiveReportRoundTest(unittest.TestCase, LiveReportRoundMixin):
    """What a dispatched round that finished on a report leaves behind."""

    def test_a_published_round_settles_and_hands_back(self) -> None:
        # The report reaches the pull request on this very tick, so the write
        # that completes the transaction is the one that advances the readers,
        # drops the bookmarks and spends the round -- and only then is the
        # reviewer given the head.
        seeded = self.seed()

        self.tick(seeded, message=_REPORTED, head_shas=(
            live.PR_HEAD_SHA, live.SHA_AFTER,
        ), push_branch=True)

        pinned = self.pinned(seeded)
        self.assertEqual(len(seeded.github.posted_pr_comments), 1)
        self.assertEqual(
            pinned[live.LAST_ACTION_COMMENT_ID], live.TRIGGER_ID,
        )
        self.assertIsNone(pinned[live.PENDING_FIX_AT])
        self.assertEqual(pinned[live.REVIEW_ROUND], 0)
        self.assertTrue(self.handed_back(seeded))

    def test_a_refused_post_holds_everything(self) -> None:
        # The push landed and GitHub refused the comment, so the report is
        # owed: the readers, the bookmarks, the round and the relabel all wait
        # for the write that finally puts it there.
        seeded = self.seed()
        seeded.github.report_failures.refused.add(live.PR_NUMBER)

        self.tick(seeded, message=_REPORTED, head_shas=(
            live.PR_HEAD_SHA, live.SHA_AFTER,
        ), push_branch=True)

        pinned = self.pinned(seeded)
        self.assertEqual(seeded.github.posted_pr_comments, [])
        self.assertLess(
            pinned[live.LAST_ACTION_COMMENT_ID], live.TRIGGER_ID,
        )
        self.assertIsNotNone(pinned[live.PENDING_FIX_AT])
        self.assertEqual(pinned[live.REVIEW_ROUND], 1)
        self.assertFalse(self.handed_back(seeded))

    def test_an_owed_report_spawns_nobody(self) -> None:
        # The readers are held back while the publication is outstanding, so
        # the batch that report was written over reads as unread -- on every
        # poll, for as long as the post keeps failing. What says otherwise is
        # the record's own frozen pairs, which is why no developer runs.
        seeded = self.seed(crashed=True, landed=live.SHA_AFTER)

        mocks = self.tick(seeded, head=live.SHA_AFTER)

        spawned_nobody(mocks)

    def test_a_post_push_crash_publishes_and_closes(self) -> None:
        # The crash landed past the push, so the commit the report describes
        # is on the pull request: the recovery re-proves that against the
        # checkout, publishes, and closes the round the record froze.
        seeded = self.seed(crashed=True, landed=live.SHA_AFTER)
        seeded.github.get_pr(live.PR_NUMBER).head.sha = live.SHA_AFTER

        self.tick(seeded, head=live.SHA_AFTER)

        pinned = self.pinned(seeded)
        self.assertEqual(len(seeded.github.posted_pr_comments), 1)
        self.assertEqual(
            pinned[live.LAST_ACTION_COMMENT_ID], live.TRIGGER_ID,
        )
        self.assertEqual(pinned[live.REVIEW_ROUND], 0)
        self.assertTrue(self.handed_back(seeded))

    def test_a_pre_push_crash_republishes_first(self) -> None:
        # The crash landed before the push, so the branch is carrying a commit
        # the pull request has not got. The recovery will not publish a report
        # over a head it cannot prove, so the round waits for the bounce that
        # republishes the commit -- and nothing is spent meanwhile.
        seeded = self.seed(crashed=True)

        mocks = self.tick(seeded, head=live.SHA_AFTER)

        spawned_nobody(mocks)
        pinned = self.pinned(seeded)
        self.assertEqual(seeded.github.posted_pr_comments, [])
        self.assertEqual(pinned[live.REVIEW_ROUND], 1)
        self.assertFalse(self.handed_back(seeded))

    def test_a_later_reply_runs_an_ordinary_round(self) -> None:
        # A comment ABOVE the pairs the record froze is feedback nobody has
        # answered. The recovery ends the tick that publishes the outstanding
        # report, so the round over that reply is the poll behind it -- and
        # the prompt it earns carries the reply and nothing the report already
        # covers.
        seeded = self.seed(crashed=True, landed=live.SHA_AFTER)
        published = seeded.github.get_pr(live.PR_NUMBER)
        published.head.sha = live.SHA_AFTER
        crash.later_pr_comment(published, _LATER_ID, _LATER_FEEDBACK)
        reply = published.issue_comments[-1]
        self.tick(seeded, head=live.SHA_AFTER)

        mocks = self.tick(seeded, head=live.SHA_AFTER, message=_REPORTED)

        self.assertEqual(only_prompt(mocks), pr_feedback_prompt([reply]))

    def test_an_explicit_retry_replays_the_batch(self) -> None:
        # `/orchestrator continue` is the operator saying so anyway, and it is
        # answered ahead of the reading that holds an owed report's own batch:
        # the park it clears is one only a human clears, so refusing the
        # command over a publication nothing can complete would leave no way
        # out at all.
        #
        # What the developer is handed is that batch and NOT the command line
        # beside it. The prompt renders whatever it is given as feedback to
        # implement, and an owed report is what puts the two in one rescan:
        # the readers are held until the publication lands, so the batch the
        # report answers still reads as unread and the command stops being the
        # only fresh thing on the thread. Asserted whole, because a bare line
        # quoted back to a developer is a substring nothing else would catch.
        seeded = self.seed(
            crashed=True,
            **{live.AWAITING_HUMAN: True, live.PARK_REASON: _ASKED_A_QUESTION},
        )
        answered = seeded.issue.comments[-1]
        crash.later_comment(seeded.issue, _LATER_ID, live.CONTINUE_COMMAND)

        mocks = self.tick(seeded, head=live.SHA_AFTER, message=_REPORTED)

        self.assertEqual(only_prompt(mocks), pr_feedback_prompt([answered]))
        # And the command is still settled by the round that dropped it: this
        # one reported, so what it consumed rides its report's record, and the
        # boundary frozen there is past the command. Left out of that, the
        # retry re-fires on every poll.
        self.assertIn(
            (live.LAST_ACTION_COMMENT_ID, _LATER_ID),
            crash.frozen_record(self.pinned(seeded)).watermarks,
        )


class LiveReportParkTest(unittest.TestCase, LiveReportRoundMixin):
    """The checkouts a recorded report can never be published over.

    Both sides of the fork, because the roads meet here: a record a crash left
    behind, and a round that reported on THIS tick and whose own checkout
    refused the reading it needed. What the two owe is the same, so a refusal
    no later poll takes back ends either road under one notice and a reading
    nobody could take holds either where it stands.
    """

    def test_a_checkout_nothing_can_prove_parks_once(self) -> None:
        # A worktree that is GONE and a tree this host proved DIRTY are the
        # two refusals no later poll takes back, so each announces itself and
        # RELEASES the record -- a human restoring the checkout would
        # otherwise publish the report the notice is asking them about. The
        # debt outlives it, which is what keeps the review held.
        for road, options in _DEFINITE_REFUSALS.items():
            with self.subTest(road=road):
                seeded = self.seed(crashed=True, landed=live.SHA_AFTER)

                mocks = self._parks(seeded, options)

                pinned = self.pinned(seeded)
                spawned_nobody(mocks)
                self.assertTrue(pinned[live.AWAITING_HUMAN])
                self.assertIsNone(pinned[_DELIVERED_REPORT])
                self.assertTrue(_report_delivery.owes_a_report(
                    PinnedState(state_data=pinned),
                ))
                self.assertTrue(posted_comment_contains(
                    seeded.github, _UNPUBLISHABLE_PHRASE,
                ))
                self.assertGreaterEqual(
                    pinned[live.LAST_ACTION_COMMENT_ID], live.TRIGGER_ID,
                )

    def test_an_unread_checkout_holds_the_record(self) -> None:
        # A status nobody could take and a head that would not resolve are not
        # a refusal at all: a later poll may read either, so the record is HELD
        # rather than released and the tick says NOTHING. Let past instead, the
        # scan behind it finds a batch the record's own pairs cover, and the
        # bounce announces a report no road can move -- a claim about a branch
        # this tick could not read a thing about, filed as a park only a human
        # clears.
        for read, options in _UNREAD_CHECKOUTS.items():
            with self.subTest(read=read):
                seeded = self.seed(crashed=True, landed=live.SHA_AFTER)

                mocks = self.tick(seeded, **options)

                pinned = self.pinned(seeded)
                spawned_nobody(mocks)
                self.assertIsNotNone(pinned[_DELIVERED_REPORT])
                self.assertFalse(pinned.get(live.AWAITING_HUMAN))
                self.assertIsNone(pinned.get(live.PARK_REASON))
                self.assertEqual(seeded.github.posted_comments, [])
                self.assertEqual(seeded.github.posted_pr_comments, [])

    def test_the_readable_tick_recovers_what_it_held(self) -> None:
        # The other half of that hold, over the polls it is really made of:
        # the reading heals and the very next tick publishes the record the
        # held one kept, closes the round it froze, and hands the reviewer the
        # head -- with no human ever having been waited for.
        seeded = self.seed(crashed=True, landed=live.SHA_AFTER)
        seeded.github.get_pr(live.PR_NUMBER).head.sha = live.SHA_AFTER
        self.tick(
            seeded, head=live.SHA_AFTER, **_UNREAD_CHECKOUTS[_UNREAD_TREE],
        )

        mocks = self.tick(seeded, head=live.SHA_AFTER)

        pinned = self.pinned(seeded)
        spawned_nobody(mocks)
        self.assertEqual(len(seeded.github.posted_pr_comments), 1)
        self.assertEqual(seeded.github.posted_comments, [])
        self.assertFalse(pinned.get(live.AWAITING_HUMAN))
        self.assertIsNone(pinned[_DELIVERED_REPORT])
        self.assertEqual(
            pinned[live.LAST_ACTION_COMMENT_ID], live.TRIGGER_ID,
        )
        self.assertTrue(self.handed_back(seeded))

    def test_a_transient_read_holds_a_reporting_round(self) -> None:
        # A head the checkout would not name and a status that established
        # nothing are readings about the TICK, not about the round: the report
        # is valid and the branch is wherever it was. So the round is held --
        # nothing published, and no park at all. Parked instead, a human is
        # asked about a question this developer never posed, and the park
        # outlives the tick that finally publishes.
        for read, options in _TRANSIENT_READS.items():
            with self.subTest(read=read):
                seeded = self.seed()

                self.tick(seeded, message=_REPORTED, **options)

                pinned = self.pinned(seeded)
                self.assertFalse(pinned[live.AWAITING_HUMAN])
                self.assertIsNone(pinned.get(live.PARK_REASON))
                self.assertEqual(seeded.github.posted_comments, [])
                self.assertIsNotNone(pinned[_DELIVERED_REPORT])
                self.assertFalse(self.handed_back(seeded))

    def test_the_tick_that_can_read_publishes_it(self) -> None:
        # The other half of that hold, over the polls it is really made of:
        # the reading heals, the recovery ahead of the scan publishes the
        # record the held tick left, and the reviewer is handed the head with
        # no human ever having been waited for.
        seeded = self.seed()
        self.tick(seeded, message=_REPORTED, **_TRANSIENT_READS[_UNREAD_TREE])

        mocks = self.tick(seeded)

        pinned = self.pinned(seeded)
        spawned_nobody(mocks)
        self.assertEqual(len(seeded.github.posted_pr_comments), 1)
        self.assertEqual(seeded.github.posted_comments, [])
        self.assertFalse(pinned[live.AWAITING_HUMAN])
        self.assertEqual(
            pinned[live.LAST_ACTION_COMMENT_ID], live.TRIGGER_ID,
        )
        self.assertTrue(self.handed_back(seeded))

    def test_a_dirty_round_takes_the_report_park(self) -> None:
        # A tree this host PROVED dirty is decisive, so the round ends on the
        # terminal park its REPORT owns rather than on the question road: one
        # notice, the reason a settlement can read, the record released, and
        # the batch it consumed written down in that park's own write. The
        # poll behind it adds no second notice, because nothing has changed
        # that a human has not been asked about.
        seeded = self.seed()

        self.tick(seeded, message=_REPORTED, **_DIRTY_CHECKOUT)
        mocks = self.tick(seeded, message=_REPORTED, **_DIRTY_CHECKOUT)

        pinned = self.pinned(seeded)
        spawned_nobody(mocks)
        self.assertEqual(len(seeded.github.posted_comments), 1)
        self.assertTrue(posted_comment_contains(
            seeded.github, _UNPUBLISHABLE_PHRASE,
        ))
        self.assertEqual(pinned[live.PARK_REASON], _UNDELIVERABLE)
        self.assertIsNone(pinned[_DELIVERED_REPORT])
        self.assertTrue(_report_delivery.owes_a_report(
            PinnedState(state_data=pinned),
        ))
        self.assertGreaterEqual(
            pinned[live.LAST_ACTION_COMMENT_ID], live.TRIGGER_ID,
        )
        self.assertEqual(seeded.github.posted_pr_comments, [])

    def _parks(self, seeded, options):
        """One tick over a checkout this host will never publish from."""
        if options is None:
            standing = live.SHA_AFTER
            return self._run_fixing(
                seeded.github, seeded.issue,
                run_agent=live._agent(),
                head_shas=(standing, standing),
            )
        return self.tick(seeded, head=live.SHA_AFTER, **options)


class LiveStaleCorrelationTest(unittest.TestCase, LiveReportRoundMixin):
    """The rounds a settlement's mark may not be spent on."""

    def test_a_foreign_delivery_hands_no_round_back(self) -> None:
        # A delivery is claimed by ONE key whoever wrote it, so an
        # implementing candidate's or a drift resume's record can be the one
        # that settles here. It closes its own route's bookkeeping and raises
        # no fixing mark, so the reviewer's change request is not handed back
        # with the feedback that earned it unread.
        seeded = self.seed(crashed=True, landed=live.SHA_AFTER)
        _records_a_foreign_delivery(seeded)
        seeded.github.get_pr(live.PR_NUMBER).head.sha = live.SHA_AFTER

        self.tick(seeded, head=live.SHA_AFTER)

        self.assertEqual(len(seeded.github.posted_pr_comments), 1)
        self.assertFalse(self.handed_back(seeded))

    def test_a_mark_from_elsewhere_is_retired_unspent(self) -> None:
        # A settlement that landed under another label says nothing about the
        # round this stage is holding, so the mark comes down -- it is that
        # round's and that round is over -- and the relabel is withheld.
        seeded = self.seed(**{
            support.SETTLED_ROUND: True, live.PENDING_FIX_AT: None,
        })
        _records_a_handoff(seeded, under=WorkflowLabel.VALIDATING)

        self.tick(seeded, head=live.PR_HEAD_SHA, message=_REPORTED)

        self.assertIsNone(self.pinned(seeded)[support.SETTLED_ROUND])
        self.assertFalse(self.handed_back(seeded))


if __name__ == "__main__":
    unittest.main()
