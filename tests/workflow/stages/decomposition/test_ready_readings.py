# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What the `ready` decision reads off GitHub decides and licenses it, not what the tick was dispatched with.

The decision compares the issue fetched afresh, and again every issue it
fetches ahead of a pickup or a relabel, consumes exactly the thread reading it
last compared -- with the title and body fetched behind it -- and reads the
pinned record back behind its checkpoint before it hands the issue on. A
receipt it reads off the thread is one this orchestrator generated, not any
comment the token account wrote. Each case lands something on GitHub
apart from the dispatched object, or between two of the decision's requests,
and reads back what the tick did.
"""
from __future__ import annotations

import copy
import unittest
from functools import partial

from orchestrator.workflow.engine import drift as _drift
from orchestrator.workflow.stages.decomposition.ready_handoff import PICKUP_NOTICE
from tests.support.fakes import DEFAULT_BOT_LOGIN, FakeComment, FakeGitHubClient, FakeUser
from tests.workflow.fixtures import _PatchedWorkflowMixin
from tests.workflow.stages.decomposition import child_baseline_support as _baseline, ready_test_support as _support

# What a thread told one changed reroute's notice and one pickup holds.
_SAID_PICKUP_AND_CHANGED = (1, 0, 1)

# What a human edits on GitHub apart from the dispatched issue.
_EDITED_FIELDS = ("title", "body")

# Where a rerouted tick leaves the child -- its reroute's relabel -- and what
# the thread was told: the reroute's notice alone where the edit was read ahead
# of the pickup, and behind the pickup said where it was read only behind the
# handoff's checkpoint.
_UNANNOUNCED = (_support.REROUTED, _support.SAID_CHANGED)

_OVER_THE_HANDOFF = (_support.REROUTED, _SAID_PICKUP_AND_CHANGED)


class ReadyFreshReadingTest(unittest.TestCase, _PatchedWorkflowMixin, _support.ReadyTicks):
    """What GitHub holds now, not what the tick was dispatched with, decides and licenses the handoff."""

    def test_a_stale_dispatch_reroutes_unannounced(self) -> None:
        # The title or the body edited on GitHub before the tick, the issue
        # object it was dispatched with still reading as it did: the decision
        # reads the issue fetched afresh, so the edit reroutes before any
        # pickup is announced.
        for field in _EDITED_FIELDS:
            with self.subTest(field=field):
                gh = FakeGitHubClient()
                dispatched = _support.ready_child(gh)
                _edited_on_github(field, gh, dispatched)

                ran = self.ready_tick(gh, dispatched)

                self.assertEqual(ran, 0)
                self.assertEqual(_support.seen(gh)[0], _support.REROUTED)
                self.assertEqual(_support.notices(gh), _support.SAID_CHANGED)

    def test_a_record_edited_behind_the_checkpoint(self) -> None:
        # A human takes the child's baseline off its record right after the
        # handoff's checkpoint lands: the record read back no longer carries it,
        # so nothing is relabelled or launched, and the next tick reroutes the
        # child it now reads as unbaselined.
        gh = FakeGitHubClient()
        child = _support.ready_child(gh)
        unbaselined = _support.InPlace(user_content_hash=None)
        lands = _support.LandsAfter(gh, "edit_pinned_state", 1, unbaselined)

        held = self.interleaved_tick(gh, child, lands)

        self.assertEqual(held[0], 0)
        self.assertEqual(held[1][0], ())
        self.assertEqual(self.ready_tick(gh, child), 0)
        self.assertEqual(self.reroute(gh), _support.UNBASELINED_REROUTE)
        self.assertEqual(gh.workflow_label(child), _support.LABEL_DECOMPOSING)

    def test_a_requirement_at_the_pickup_reroutes(self) -> None:
        # A trusted requirements comment lands while the pickup is posted,
        # ahead of the reading the checkpoint consumes: it is compared on that
        # reading and rerouted, and nothing is consumed or implemented.
        gh = FakeGitHubClient()
        child = _support.ready_child(gh)
        lands = _support.LandsAfter(gh, "comment", 1, _baseline.Commented(_support.TRUSTED))

        ran, seen = self.interleaved_tick(gh, child, lands)

        self.assertEqual(
            (ran, seen[:2]),
            (0, (_support.REROUTED, _SAID_PICKUP_AND_CHANGED)),
        )
        self.assertEqual(self.reroute(gh), _support.CHANGED_REROUTE)
        self.assertEqual(self.recorded(gh, _support.KEY_BASELINE), _support.reading(child))
        self.assertIsNone(self.recorded(gh, _support.KEY_LAST_ACTION))

    def test_an_edit_at_the_pickup_reroutes(self) -> None:
        # The title or the body edited on GitHub while the pickup is posted,
        # the issue object the tick was dispatched with still reading as it
        # did: the last comparison reads the issue GitHub answers for behind
        # the consumed reading, so the edit reroutes, and nothing is consumed
        # or implemented.
        for field in _EDITED_FIELDS:
            with self.subTest(field=field):
                gh = FakeGitHubClient()
                dispatched = _support.ready_child(gh)
                lands = _support.LandsAfter(gh, "comment", 1, partial(_edited_on_github, field))

                held = self.interleaved_tick(gh, dispatched, lands)

                self.assertEqual(held[0], 0)
                self.assertEqual(held[1][0], _support.REROUTED)
                self.assertEqual(
                    self.recorded(gh, _support.KEY_BASELINE),
                    _support.reading(gh.get_issue(_support.CHILD)),
                )
                self.assertIsNone(self.recorded(gh, _support.KEY_LAST_ACTION))

    def test_an_edit_at_the_decision_reroutes(self) -> None:
        # The title or the body edited on GitHub while the decision reads the
        # thread, behind the issue it fetched first: the fetch ahead of the
        # pickup shows the edit, so the issue is rerouted with no pickup
        # announced, nothing consumed, and nothing implemented.
        for field in _EDITED_FIELDS:
            with self.subTest(field=field):
                gh = FakeGitHubClient()
                child = _support.ready_child(gh)
                held = self.interleaved_tick(gh, child, _edit_behind(gh, "comments_after", field))

                self.assertEqual(held[0], 0)
                self.assertEqual(held[1][:2], _UNANNOUNCED)
                self.assertEqual(self.reroute(gh), _support.CHANGED_REROUTE)
                self.assertEqual(
                    self.recorded(gh, _support.KEY_BASELINE),
                    _support.reading(gh.get_issue(_support.CHILD)),
                )
                self.assertIsNone(self.recorded(gh, _support.KEY_PICKUP))
                self.assertIsNone(self.recorded(gh, _support.KEY_LAST_ACTION))

    def test_an_edit_at_the_checkpoint_reroutes(self) -> None:
        # The title or the body edited on GitHub while the handoff's checkpoint
        # lands: the fetch ahead of the relabel shows the edit, so the issue is
        # rerouted over the handoff that landed -- its pickup and consumed
        # reading kept -- never relabelled to implementing, and its decomposer
        # is what runs next.
        for field in _EDITED_FIELDS:
            with self.subTest(field=field):
                gh = FakeGitHubClient()
                child = _support.ready_child(gh)
                held = self.interleaved_tick(gh, child, _edit_behind(gh, "edit_pinned_state", field))

                self.assertEqual(held[0], 0)
                self.assertEqual(held[1][:2], _OVER_THE_HANDOFF)
                self.assertEqual(self.reroute(gh), _support.CHANGED_REROUTE)
                current = gh.get_issue(_support.CHILD)
                self.assertEqual(self.recorded(gh, _support.KEY_BASELINE), _support.reading(current))
                self.assertIsNotNone(self.recorded(gh, _support.KEY_PICKUP))
                self.assertIsNotNone(self.recorded(gh, _support.KEY_LAST_ACTION))
                self.assertEqual(self.decomposing_tick(gh, current), 1)

    def test_a_quoted_pickup_stays_a_human_comment(self) -> None:
        # A trusted human sharing the token account quotes the pickup sentence,
        # with no hidden marker of ours and no entry in our ledger: it is no
        # pickup of ours, so ours is posted, the quotation never enters the
        # ledger, and an edit of it later is a requirements change.
        gh = FakeGitHubClient()
        child = _support.ready_child(gh)
        quote = FakeComment(gh.next_reply_id(child), f"Check the wording: {PICKUP_NOTICE}", FakeUser(DEFAULT_BOT_LOGIN))
        child.comments.append(quote)
        gh.seed_state(_support.CHILD, parent_number=_support.PARENT, user_content_hash=_support.reading(child))

        self.assertEqual(self.ready_tick(gh, child), 1)
        quote.body = f"{quote.body}\n\nAlso require a regression test."

        self.assertNotIn(quote.id, self.recorded(gh, "orchestrator_comment_ids"))
        self.assertEqual(_support.notices(gh), _support.SAID_PICKUP)
        self.assertIsNotNone(_drift._detect_user_content_change(gh, child, gh.read_pinned_state(child)))


def _edited_on_github(field: str, gh: FakeGitHubClient, issue) -> None:
    """Add to the issue's title or body as GitHub holds it, as a snapshot of its own.

    Every later fetch answers the edited snapshot, the way each fetch from the
    real client is an object of its own, while every object fetched before it
    -- the dispatched one, and any a tick fetched since -- still reads as it
    did. The thread is the same one either way.
    """
    remote = copy.copy(gh.get_issue(issue.number))
    if field == "title":
        remote.title = f"{remote.title}, and the docs"
    else:
        remote.body = f"{remote.body}\n\nAlso cover the docs."
    gh.add_issue(remote)


def _edit_behind(gh: FakeGitHubClient, request: str, field: str) -> _support.LandsAfter:
    """The issue's `field` edited on GitHub (`_edited_on_github`) behind the answer to the tick's first `request`."""
    return _support.LandsAfter(gh, request, 1, partial(_edited_on_github, field))


if __name__ == "__main__":
    unittest.main()
