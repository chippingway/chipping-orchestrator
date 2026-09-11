# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The generation-marked hold on a pull request, and every boundary it crosses."""
from __future__ import annotations

import unittest
from dataclasses import replace
from unittest.mock import MagicMock, patch

from orchestrator.workflow.stages.decomposition import (
    late_hold as _late_hold,
    late_session as _late_session,
)
from tests.support.fakes import FakeGitHubClient, FakePRRef
from tests.workflow.stages.decomposition import late_test_support as _support
from tests.workflow.stages.decomposition.late_run_support import HoldSnapshot

# What a re-measured candidate reports, and therefore what the notice a
# re-marked hold quotes. Any number but the first generation's does.
REVISED_ADDITIONS = 5150

FOREIGN_HOLD = (
    "<!--orchestrator-late-hold:cycle=1:generation=0-->\nan older hold"
)

HUMAN_REPLACEMENT = "a human rewrote the description mid-hold"

# The hold exactly as this binary writes it on a pull request nothing has
# pushed to. Spelled out here rather than built from the owner under test,
# because these are the bytes already standing on live pull requests: a word
# changed under one reads it as a human's own description, and the copy it
# replaced is then never put back.
CURRENT_HOLD = (
    f"<!--orchestrator-late-hold:cycle={_support.CYCLE_ID}-->\n"
    ":hourglass: **Held by the orchestrator.** The committed implementation "
    f"for issue #{_support.LATE_ISSUE_NUMBER} measured past the size ceiling, so it is being "
    "adjudicated before anything is published. Do not merge this pull "
    "request while the hold stands.\n\n"
    "This description is temporary. The original is preserved in the issue's "
    "pinned orchestrator state and is restored when adjudication finishes."
)

# The hold exactly as the binary before this one wrote it: marked by
# generation as well as cycle, and quoting what the candidate measured.
# Spelled out here rather than built from the owner under test, because what
# it pins is the bytes a running orchestrator left on somebody's pull request
# -- an upgrade meets them unchanged, and a spelling this binary cannot
# recognize is a hold it can never take back off.
SUPERSEDED_HOLD = (
    f"<!--orchestrator-late-hold:cycle={_support.CYCLE_ID}:generation={_support.GENERATION_NUMBER}-->\n"
    ":hourglass: **Held by the orchestrator.** The committed implementation "
    f"for issue #{_support.LATE_ISSUE_NUMBER} measures {_support.ADDITIONS} added lines against a ceiling "
    f"of {_support.THRESHOLD}, so it is being adjudicated before anything is "
    "published. Do not merge this pull request while the hold "
    "stands.\n\n"
    "This description is temporary. The original is preserved in the "
    "issue's pinned orchestrator state and is restored when adjudication "
    "finishes."
)

# What a human editing the notice rather than replacing it leaves behind:
# the hidden marker survives, and so do words nothing here wrote.
HUMAN_ADDITION = "\n\nand a note of my own."

CLOSED = "closed"

OPEN = "open"

# A head GitHub could not be made to name: text this domain records as no
# commit at all, which is what the pinned write would then drop.
UNNAMEABLE_HEAD = "HEAD"

GET_PR = "get_pr"

SPEC_FLAGS = 800

HEADROOM_UNDER_THE_CEILING = 4000

# An operator's command line, long enough that the record built from it is
# what decides whether a preserved body still fits.
LONG_SPEC = "claude {}".format("--flag " * SPEC_FLAGS)

WORKFLOW_LOG = "orchestrator.workflow"

ERROR = "ERROR"


class _HoldCase(unittest.TestCase):
    """One late issue whose discussion left an open plan PR standing."""

    def setUp(self) -> None:
        self.github = FakeGitHubClient()
        self.issue = _support.seed_late_issue(
            self.github,
            _support.late_generation(),
            pr_number=_support.PLAN_PR_NUMBER,
            **{_support.KEY_PLAN_PATH: _support.PLAN_PATH},
        )
        self.plan_pr = _support.seed_plan_pr(self.github)

    def _reconcile(self, generation=None):
        return _late_hold._reconcile_hold(
            self.github,
            self.issue,
            self.github.read_pinned_state(self.issue),
            _support.late_generation() if generation is None else generation,
        )

    def _pinned(self) -> dict:
        return self.github.pinned_data(_support.LATE_ISSUE_NUMBER)


class PlanPrHoldTest(_HoldCase):
    """What one reconciliation does to a reusable open plan PR."""

    def test_no_recorded_plan_pr_holds_nothing(self) -> None:
        # An issue that never published a plan PR has nothing to mark, which
        # is not a failure: the caller spawns exactly as it would have.
        self.github = FakeGitHubClient()
        self.issue = _support.seed_late_issue(self.github, _support.late_generation())

        hold = self._reconcile()

        self.assertFalse(hold.held)
        self.assertFalse(hold.failed)
        self.assertEqual(self.github.edited_pr_bodies, [])

    def test_hold_preserves_the_body_it_replaced(self) -> None:
        # The persist-before-mutate order is the whole reason the original
        # body survives a crash: nothing else holds a copy of it.
        recorder = HoldSnapshot(self.github)

        with patch.object(self.github, "edit_pr_body", recorder):
            hold = self._reconcile()

        self.assertTrue(hold.held)
        self.assertEqual(hold.generation.plan_pr_number, _support.PLAN_PR_NUMBER)
        self.assertEqual(hold.generation.plan_pr_body, _support.PLAN_PR_BODY)
        self.assertEqual(
            [held.get(_support.KEYS.plan_pr_body) for held in recorder.snapshots],
            [_support.PLAN_PR_BODY],
        )
        self.assertEqual(
            [held.get(_support.KEYS.plan_pr_head) for held in recorder.snapshots],
            [self.plan_pr.head.sha],
        )

    def test_the_unpublished_notice_is_frozen(self) -> None:
        # The spelling is the compatibility contract, not the marker inside
        # it: holds earlier ticks wrote are standing on live pull requests,
        # and a word changed here reads every one of them as somebody's own
        # description -- refusing to restore what it replaced, for good.
        self.assertEqual(
            _late_hold._hold_body(_support.late_generation()), CURRENT_HOLD,
        )

    def test_hold_body_carries_the_generation(self) -> None:
        generation = _support.late_generation()

        self._reconcile(generation)

        self.assertIn(_late_hold._hold_marker(generation), self.plan_pr.body)
        self.assertNotIn(_support.PLAN_PR_BODY, self.plan_pr.body)

    def test_retry_over_its_own_hold_is_a_no_op(self) -> None:
        # Idempotence is what lets the caller retry a failed reconciliation on
        # every eligible tick without a noisy mutation each poll.
        first = self._reconcile()

        second = self._reconcile(first.generation)

        self.assertTrue(second.held)
        self.assertEqual(len(self.github.edited_pr_bodies), 1)

    def test_a_replaced_body_is_left_alone(self) -> None:
        # A description a human wrote over the hold is theirs, and the
        # preserved copy has stopped being a description of this pull request.
        # Re-marking it would hand the release a body it believed was this
        # generation's, to restore that stale copy over their words.
        first = self._reconcile()
        self.plan_pr.body = HUMAN_REPLACEMENT

        second = self._reconcile(first.generation)

        self.assertFalse(second.held)
        self.assertFalse(second.failed)
        self.assertTrue(second.displaced)
        self.assertEqual(self.plan_pr.body, HUMAN_REPLACEMENT)
        self.assertEqual(len(self.github.edited_pr_bodies), 1)


class ReappliedHoldTest(_HoldCase):
    """The bodies a retry writes over, and the one it never does.

    A hold this orchestrator wrote -- in this spelling or the one before it --
    and the description it recorded beside the identity are all its own to
    replace; anything else is somebody's words.
    """

    def test_an_older_spelling_is_ours_and_migrated(self) -> None:
        # The upgrade case: an orchestrator restarted under a hold its
        # predecessor took. Read as somebody's words it would be a "do not
        # merge" notice nothing could ever take back off, on a pull request
        # nothing could start an agent under -- so it is recognized, and the
        # same edit that would have applied a fresh hold rewrites it in the
        # spelling every later comparison is made against.
        held = _support.late_generation(
            plan_pr_number=_support.PLAN_PR_NUMBER, plan_pr_body=_support.PLAN_PR_BODY,
        )
        self.plan_pr.body = SUPERSEDED_HOLD

        hold = self._reconcile(held)

        self.assertTrue(hold.held)
        self.assertFalse(hold.displaced)
        self.assertFalse(hold.failed)
        self.assertEqual(self.plan_pr.body, _late_hold._hold_body(held))
        self.assertEqual(hold.generation.plan_pr_body, _support.PLAN_PR_BODY)

    def test_an_advanced_generation_needs_no_re_mark(self) -> None:
        # The counter advances on every reconciliation that lands, and the
        # hold is keyed to the CYCLE -- so a re-measured candidate leaves the
        # pull request wearing exactly the body this reconstructs, and there
        # is nothing to re-mark and nothing to mistake for somebody's words.
        first = self._reconcile()
        advanced = replace(
            first.generation,
            generation=first.generation.generation + 1,
            additions=REVISED_ADDITIONS,
        )

        second = self._reconcile(advanced)

        self.assertTrue(second.held)
        self.assertFalse(second.displaced)
        self.assertEqual(self.plan_pr.body, _late_hold._hold_body(advanced))
        self.assertEqual(len(self.github.edited_pr_bodies), 1)

    def test_an_edited_hold_is_left_alone(self) -> None:
        # The marker is hidden, so a human editing one sentence of the notice
        # leaves it in place. Reading its presence as proof the body is
        # unchanged is what would call this held -- and have the release put
        # the preserved copy back over what they wrote.
        first = self._reconcile()
        self.plan_pr.body = self.plan_pr.body + HUMAN_ADDITION

        second = self._reconcile(first.generation)

        self.assertFalse(second.held)
        self.assertTrue(second.displaced)
        self.assertIn(HUMAN_ADDITION.strip(), self.plan_pr.body)
        self.assertEqual(len(self.github.edited_pr_bodies), 1)

    def test_a_lost_edit_is_re_applied(self) -> None:
        # The one body the retry writes over: a crash between the persist and
        # the edit leaves the description recorded beside the identity, and
        # nothing on the pull request says the hold was ever taken.
        first = self._reconcile()
        self.plan_pr.body = _support.PLAN_PR_BODY

        second = self._reconcile(first.generation)

        self.assertTrue(second.held)
        self.assertEqual(second.generation.plan_pr_body, _support.PLAN_PR_BODY)
        self.assertIn(_support.HOLD_MARKER_PREFIX, self.plan_pr.body)


class SettledPlanPrTest(_HoldCase):
    """A pull request a human has decided about is not held."""

    def test_an_older_spelling_is_still_released(self) -> None:
        # The one release the retry cannot have migrated first: a settled
        # pull request is left exactly as it is by the reconciliation above,
        # so the spelling the release meets is whichever binary wrote it.
        # Refusing it would leave a merged plan describing a hold that ended.
        self.plan_pr.state = CLOSED
        self.plan_pr.body = SUPERSEDED_HOLD
        held = _support.late_generation(
            plan_pr_number=_support.PLAN_PR_NUMBER, plan_pr_body=_support.PLAN_PR_BODY,
        )

        release = _late_hold._release_hold(
            self.github, self.issue, held,
        )

        self.assertFalse(release.failed)
        self.assertEqual(self.plan_pr.body, _support.PLAN_PR_BODY)

    def test_a_settled_plan_pr_re_anchors_nothing(self) -> None:
        # A human merging or closing the plan PR has decided something about
        # that pull request and nothing about the commit under adjudication.
        self.plan_pr.state = CLOSED
        held = _support.late_generation(
            plan_pr_number=_support.PLAN_PR_NUMBER, plan_pr_body=_support.PLAN_PR_BODY,
        )

        hold = self._reconcile(held)

        self.assertFalse(hold.held)
        self.assertFalse(hold.failed)
        self.assertEqual(self.github.edited_pr_bodies, [])
        self.assertEqual(hold.generation.candidate_sha, _support.CANDIDATE_SHA)
        self.assertEqual(hold.generation.base_sha, _support.BASE_SHA)
        self.assertEqual(hold.generation.plan_pr_number, _support.PLAN_PR_NUMBER)
        self.assertEqual(hold.generation.plan_pr_body, _support.PLAN_PR_BODY)


class PlanPrProvenanceTest(_HoldCase):
    """Only a plan is held, and only the snapshot that was classified."""

    def test_an_implementation_pr_is_left_alone(self) -> None:
        # `pr_number` names whichever PR the issue records, and that is an
        # implementation as often as a plan. Rewriting one would replace a
        # human's account of a change under review with a notice about
        # another one.
        self.github = FakeGitHubClient()
        self.issue = _support.seed_late_issue(
            self.github, _support.late_generation(), pr_number=_support.PLAN_PR_NUMBER,
        )
        _support.seed_plan_pr(self.github)

        hold = self._reconcile()

        self.assertFalse(hold.held)
        self.assertFalse(hold.failed)
        self.assertEqual(self.github.edited_pr_bodies, [])
        self.assertIsNone(hold.generation.plan_pr_number)

    def test_a_pushed_over_plan_pr_is_left_alone(self) -> None:
        # Past the discussion handoff the plan is told from an implementation
        # by the commit its head is on, so a head that moved off the recorded
        # plan commit is somebody's implementation and not this issue's plan.
        self.github = FakeGitHubClient()
        self.issue = _support.seed_late_issue(
            self.github,
            _support.late_generation(),
            pr_number=_support.PLAN_PR_NUMBER,
            discussion_plan_sha=_support.BASE_SHA,
        )
        self.plan_pr = _support.seed_plan_pr(self.github)
        self.plan_pr.head.sha = _support.CANDIDATE_SHA

        hold = self._reconcile()

        self.assertFalse(hold.held)
        self.assertFalse(hold.failed)
        self.assertEqual(self.github.edited_pr_bodies, [])

    def test_one_snapshot_decides_and_is_acted_on(self) -> None:
        # Two reads would leave a window: a human pushing between them turns
        # the pull request into an implementation whose description this
        # would then preserve and replace.
        self.github = FakeGitHubClient()
        self.issue = _support.seed_late_issue(
            self.github,
            _support.late_generation(),
            pr_number=_support.PLAN_PR_NUMBER,
            discussion_plan_sha=_support.BASE_SHA,
        )
        self.plan_pr = _support.seed_plan_pr(self.github)
        self.plan_pr.head.sha = _support.BASE_SHA
        fetched = MagicMock(side_effect=self.github.get_pr)

        with patch.object(self.github, GET_PR, fetched):
            hold = self._reconcile()

        self.assertTrue(hold.held)
        self.assertEqual(fetched.call_count, 1)

    def test_a_body_leaving_no_room_is_refused(self) -> None:
        # A description that fits the comment EXACTLY is the worst case, not
        # the safe one: the write that starts the run comes next and has no
        # safe failure of its own, since parking is another write of the same
        # oversized comment. Refusing here leaves nothing touched.
        self.plan_pr.body = "p" * _late_session.MAX_RECORDED_BODY

        with self.assertLogs(WORKFLOW_LOG, level=ERROR):
            hold = self._reconcile()

        self.assertTrue(hold.failed)
        self.assertFalse(hold.held)
        self.assertEqual(self.github.edited_pr_bodies, [])
        self.assertNotIn(_support.KEYS.plan_pr_body, self._pinned())

    def test_the_locked_spec_decides_what_fits(self) -> None:
        # An agent spec is an operator's command line and is bounded by
        # nothing here, so the room the run record needs is measured from the
        # real one rather than reserved. The same body is holdable under a
        # short spec and refused under a long one.
        self.plan_pr.body = "p" * (_late_session.MAX_RECORDED_BODY - HEADROOM_UNDER_THE_CEILING)
        self.assertTrue(self._reconcile().held)

        self.github.seed_state(
            _support.LATE_ISSUE_NUMBER, **{**self._pinned(), _support.KEYS.agent: LONG_SPEC},
        )
        self.plan_pr.body = "p" * (_late_session.MAX_RECORDED_BODY - HEADROOM_UNDER_THE_CEILING)

        with self.assertLogs(WORKFLOW_LOG, level=ERROR):
            refused = self._reconcile()

        self.assertTrue(refused.failed)

    def test_an_unpersisted_body_is_never_edited(self) -> None:
        # The preserved body is the only copy of the description the edit is
        # about to replace, so a write that did not land is a hold that may
        # not be taken -- one long enough to overflow the pinned comment
        # refuses exactly this way.
        refused = patch.object(
            self.github, "write_pinned_state", side_effect=RuntimeError,
        )

        with refused, self.assertLogs(WORKFLOW_LOG, level=ERROR):
            hold = self._reconcile()

        self.assertTrue(hold.failed)
        self.assertFalse(hold.held)
        self.assertEqual(self.github.edited_pr_bodies, [])
        self.assertEqual(self.plan_pr.body, _support.PLAN_PR_BODY)


class _UnreadablePr:
    """A pull request whose lazy read of one field is what fails.

    PyGithub asks GitHub nothing when a pull request is fetched: the object
    completes on the first attribute access, so the request that can fail
    lands on the head, the state, or the body rather than on the fetch.
    """

    def __init__(self, failing: str) -> None:
        self.number = _support.PLAN_PR_NUMBER
        self.state = OPEN
        self._failing = failing

    @property
    def body(self) -> str:
        self._refuse("body")
        return _support.PLAN_PR_BODY

    @property
    def head(self) -> FakePRRef:
        self._refuse("head")
        return FakePRRef(sha=_support.CANDIDATE_SHA)

    @property
    def merged(self) -> bool:
        self._refuse("merged")
        return False

    def _refuse(self, name: str) -> None:
        if name == self._failing:
            raise RuntimeError("the pull request could not be read")


class PlanPrHoldFailureTest(_HoldCase):
    """Every way a hold refuses, each of them before any spawn."""

    def test_an_unreadable_plan_pr_fails_closed(self) -> None:
        # Everything downstream is decided from this one read -- the
        # provenance included -- so a fetch nobody could make leaves the
        # question unanswered, and "could not ask" must not be acted on the
        # way "not the plan" safely is.
        with (
            patch.object(self.github, GET_PR, side_effect=RuntimeError),
            self.assertLogs(WORKFLOW_LOG, level=ERROR),
        ):
            hold = self._reconcile()

        self.assertTrue(hold.failed)
        self.assertFalse(hold.held)
        self.assertEqual(self.github.edited_pr_bodies, [])

    def test_a_refused_edit_fails_closed(self) -> None:
        refused = patch.object(
            self.github, "edit_pr_body", side_effect=RuntimeError,
        )

        with refused, self.assertLogs(WORKFLOW_LOG, level=ERROR):
            hold = self._reconcile()

        self.assertTrue(hold.failed)
        # The identity and the original body are already durable, so the
        # retry re-applies the edit rather than re-capturing a body.
        self.assertEqual(self._pinned().get(_support.KEYS.plan_pr_body), _support.PLAN_PR_BODY)
        self.assertEqual(
            self._pinned().get(_support.KEYS.plan_pr_number), _support.PLAN_PR_NUMBER,
        )

    def test_a_lazy_read_that_fails_is_closed(self) -> None:
        # The fetch is not where a lazy pull request fails, so a guard around
        # the fetch alone would let the failure escape as an exception no
        # tick could park on -- halfway through deciding whether to replace a
        # human's description.
        for failing in ("body", "head", "merged"):
            with self.subTest(field=failing):
                self._assert_unreadable(_UnreadablePr(failing))

    def test_a_head_it_cannot_record_is_refused(self) -> None:
        # The identity, the head, and the body are ONE record, and the pinned
        # write drops a head that is not a commit -- so a hold taken over one
        # would replace the description and start an agent under a notice no
        # later tick could show which change it was written over. The plan
        # path is where that bites: provenance is settled by the recorded
        # plan path, so the head is never asked before this.
        self.plan_pr.head.sha = UNNAMEABLE_HEAD

        with self.assertLogs(WORKFLOW_LOG, level=ERROR):
            hold = self._reconcile()

        self.assertTrue(hold.failed)
        self.assertFalse(hold.held)
        self.assertEqual(self.github.edited_pr_bodies, [])
        self.assertEqual(self.plan_pr.body, _support.PLAN_PR_BODY)
        self.assertNotIn(_support.KEYS.plan_pr_head, self._pinned())
        self.assertNotIn(_support.KEYS.plan_pr_body, self._pinned())

    def test_a_foreign_hold_is_refused(self) -> None:
        # Capturing a hold as though it were somebody's description would
        # destroy the only copy of the body it replaced.
        self.plan_pr.body = FOREIGN_HOLD

        with self.assertLogs(WORKFLOW_LOG, level=ERROR):
            hold = self._reconcile()

        self.assertTrue(hold.failed)
        self.assertEqual(self.github.edited_pr_bodies, [])
        self.assertIsNone(hold.generation.plan_pr_body)

    def _assert_unreadable(self, unreadable) -> None:
        """A pull request nobody could read is refused, untouched."""
        fetched = patch.object(
            self.github, GET_PR, return_value=unreadable,
        )

        with fetched, self.assertLogs(WORKFLOW_LOG, level=ERROR):
            hold = self._reconcile()

        self.assertTrue(hold.failed)
        self.assertFalse(hold.held)
        self.assertEqual(self.github.edited_pr_bodies, [])


if __name__ == "__main__":
    unittest.main()
