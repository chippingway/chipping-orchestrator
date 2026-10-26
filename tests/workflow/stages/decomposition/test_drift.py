# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import unittest

from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import content_hash as _content_hash
from orchestrator.workflow.late_split.obligations import LateResourceState
from orchestrator.workflow.stages.decomposition import (
    blocked as _blocked,
    drift as _drift_reset,
    run as _decomposing,
    split_receipts as _split_receipts,
    umbrella as _umbrella,
)
from tests.support.fakes import (
    FakeComment,
    FakeGitHubClient,
    FakeUser,
    make_issue,
)
from tests.workflow.fixtures import (
    _TEST_SPEC,
    LABEL_BLOCKED,
    LABEL_READY,
    _agent,
    _manifest,
    _PatchedWorkflowMixin,
)
from tests.workflow.stages.decomposition import (
    late_cleanup_support as _late_support,
    ready_test_support as _ready_support,
    replacement_lineage_support as _lineage_support,
)
from tests.workflow.stages.decomposition.decomposition_test_support import (
    _comment_with_marker,
    _comments_for_issue,
)

LABEL_DECOMPOSING = "workflow:decomposing"
LABEL_DONE = "done"
KEY_USER_CONTENT_HASH = "user_content_hash"
STALE_USER_CONTENT_HASH = "stale-hash"
PRIOR_TICK_USER_CONTENT_HASH = "stale-hash-from-prior-tick"
PICKUP_COMMENT_ID = 900
READY_DRIFT_ISSUE_NUMBER = 50
STABLE_READY_ISSUE_NUMBER = 51
DECOMPOSING_DRIFT_ISSUE_NUMBER = 90
DECOMPOSING_ORPHAN_ISSUE_NUMBER = 91
ORPHANED_CHILD_NUMBERS = (411, 412)
HUMAN_COMMENT_ID = 2000
LAST_ACTION_COMMENT_ID = 1500
BLOCKED_PARENT_NUMBER = 300
BLOCKED_PARENT_CHILD_NUMBERS = (301, 302)
UMBRELLA_NUMBER = 400
UMBRELLA_CHILD_NUMBERS = (401, 402)
LOCKED_BACKEND = "claude"
RETIRED_SESSION_ID = "old-sess"
KEY_DECOMPOSER_SESSION_ID = "decomposer_session_id"
KEY_CHILDREN = "children"
RESPAWN_NOTICE_MARKER = "re-running decomposer"
ORPHAN_NOTICE_WORD = "ORPHANED"
LATE_KEY_PREFIX = "late_"
KEY_LATE_CONSUMERS = "late_consumers"
KEY_LATE_DEPTH = "late_lineage_depth"
SPLIT_ATTEMPT = "0123456789abcdef"
RECEIPT = "fedcba9876543210"
REPLACEMENT_SLICE = "a replacement slice"
REPLACEMENT_MANIFEST = _manifest(
    '{"decision": "split", "umbrella": true, "rationale": "re-planned", '
    '"children": [{"title": "A", "body": "a", "depends_on": []}, {"title": "B", "body": "b", "depends_on": []}]}'
)


def _decomposing_drift_fixture():
    github = FakeGitHubClient()
    issue = make_issue(
        DECOMPOSING_DRIFT_ISSUE_NUMBER,
        label=LABEL_DECOMPOSING,
        body="updated decomposition input",
    )
    issue.comments.append(
        FakeComment(
            id=HUMAN_COMMENT_ID,
            body="please reconsider",
            user=FakeUser("alice"),
        )
    )
    github.add_issue(issue)
    github.seed_state(
        DECOMPOSING_DRIFT_ISSUE_NUMBER,
        user_content_hash=STALE_USER_CONTENT_HASH,
        decomposer_agent=LOCKED_BACKEND,
        decomposer_session_id=RETIRED_SESSION_ID,
        awaiting_human=True,
        park_reason=None,
        last_action_comment_id=LAST_ACTION_COMMENT_ID,
        pickup_comment_id=PICKUP_COMMENT_ID,
    )
    return github, issue


def _blocked_parent_drift_fixture(second_label: str):
    """A `blocked` parent whose body was edited since its baseline, over a `done` child and a second on `second_label`.

    The second depends on the first, and both are linked the way a split
    seeds them.
    """
    github = FakeGitHubClient()
    parent = make_issue(
        BLOCKED_PARENT_NUMBER,
        label="workflow:blocked",
        body="updated parent body",
    )
    github.add_issue(parent)
    for child_number, child_label in zip(BLOCKED_PARENT_CHILD_NUMBERS, (LABEL_DONE, second_label), strict=True):
        github.add_issue(make_issue(child_number, label=child_label))
        github.seed_state(child_number, parent_number=BLOCKED_PARENT_NUMBER)
    github.seed_state(
        BLOCKED_PARENT_NUMBER,
        children=list(BLOCKED_PARENT_CHILD_NUMBERS),
        dep_graph={"1": [0]},
        decomposer_agent=LOCKED_BACKEND,
        decomposer_session_id=RETIRED_SESSION_ID,
        split_rationale="the parent keeps the docs for its own pass",
        user_content_hash=STALE_USER_CONTENT_HASH,
    )
    return github, parent


def _umbrella_drift_fixture():
    github = FakeGitHubClient()
    umbrella = make_issue(
        UMBRELLA_NUMBER,
        label="workflow:umbrella",
        body="updated umbrella body",
    )
    github.add_issue(umbrella)
    for child_number in UMBRELLA_CHILD_NUMBERS:
        github.add_issue(make_issue(child_number, label=LABEL_DONE))
    github.seed_state(
        UMBRELLA_NUMBER,
        children=list(UMBRELLA_CHILD_NUMBERS),
        umbrella=True,
        user_content_hash=STALE_USER_CONTENT_HASH,
    )
    return github, umbrella


class HandleReadyRoutesBackOnHashChangeTest(
    unittest.TestCase,
    _PatchedWorkflowMixin,
    _ready_support.ReadyTicks,
):
    def test_body_drift_routes_ready_back(self) -> None:
        # `ready` is reached only after a `single` decomposition decision
        # (no children created), so re-decomposing is safe. The handler
        # must clear the locked decomposer session so the next tick spawns
        # a fresh manifest derived against the new body.
        gh = FakeGitHubClient()
        issue = make_issue(
            READY_DRIFT_ISSUE_NUMBER,
            label="workflow:ready",
            body="updated body",
        )
        gh.add_issue(issue)
        gh.seed_state(
            READY_DRIFT_ISSUE_NUMBER,
            user_content_hash=PRIOR_TICK_USER_CONTENT_HASH,
            decomposer_agent=LOCKED_BACKEND,
            decomposer_session_id=RETIRED_SESSION_ID,
            pickup_comment_id=PICKUP_COMMENT_ID,
        )

        self._run(
            lambda: _blocked._handle_ready(gh, _TEST_SPEC, issue),
            run_agent=_agent(),
        )

        # Routed back to decomposing; the implementer must NOT have run
        # this tick.
        self.assertIn(
            (READY_DRIFT_ISSUE_NUMBER, LABEL_DECOMPOSING),
            gh.label_history,
        )
        state = gh.pinned_data(READY_DRIFT_ISSUE_NUMBER)
        # Session id dropped so the next tick spawns fresh, but the
        # recorded `decomposer_agent` spec is PRESERVED -- the
        # lock-on-first-spawn rule (see FullSpecPersistenceTest) means
        # a mid-flight config flip must not retarget the issue's
        # recorded role identity. The fresh spawn uses the recorded
        # spec via `_read_decomposer_session`.
        self.assertIsNone(state.get(KEY_DECOMPOSER_SESSION_ID))
        self.assertEqual(state.get("decomposer_agent"), LOCKED_BACKEND)
        # New hash now persisted so the next decomposing tick sees a
        # stable baseline.
        self.assertNotEqual(
            state.get(KEY_USER_CONTENT_HASH),
            PRIOR_TICK_USER_CONTENT_HASH,
        )
        # A human-visible notice is posted.
        self.assertTrue(
            any(
                "issue content changed" in body
                for body in _comments_for_issue(
                    gh,
                    READY_DRIFT_ISSUE_NUMBER,
                )
            )
        )

    def test_unchanged_ready_does_not_route_back(self) -> None:
        gh = FakeGitHubClient()
        issue = make_issue(
            STABLE_READY_ISSUE_NUMBER,
            label="workflow:ready",
            body="stable body",
        )
        gh.add_issue(issue)
        current = _content_hash._compute_user_content_hash(issue, set())
        gh.seed_state(
            STABLE_READY_ISSUE_NUMBER,
            user_content_hash=current,
            pickup_comment_id=PICKUP_COMMENT_ID,
        )

        self._run(
            lambda: _blocked._handle_ready(gh, _TEST_SPEC, issue),
            run_agent=_agent(session_id="dev-sess", last_message="done"),
            has_new_commits=[False, True],
            push_branch=True,
        )

        # Falls through to the normal `ready` -> `implementing` flow.
        self.assertIn(
            (STABLE_READY_ISSUE_NUMBER, "workflow:implementing"),
            gh.label_history,
        )
        self.assertNotIn(
            (STABLE_READY_ISSUE_NUMBER, LABEL_DECOMPOSING),
            gh.label_history,
        )

    def test_a_late_parent_accounts_replacements(self) -> None:
        # A parent a late split made, put back on `ready` by hand over a
        # replacement split of its own: one replacement recorded, the next
        # created and never recorded. A body edit reroutes it, and before the
        # reset drops the register both replacements join the snapshot's
        # consumer ledger beside the original -- the notice and the marker
        # naming both -- while every other late field stands as it was.
        gh, replacements = self._late_parent_over_replacements()
        before = self._late_fields(gh)

        self.assertEqual(self.ready_tick(gh, gh.get_issue(_lineage_support.PARENT)), 0)

        pinned = gh.pinned_data(_lineage_support.PARENT)
        notice = _comment_with_marker(gh, _lineage_support.PARENT, RESPAWN_NOTICE_MARKER)
        self.assertEqual(pinned[KEY_LATE_CONSUMERS], sorted([_lineage_support.ORIGINAL, *replacements]))
        self.assertEqual(
            (pinned[KEY_CHILDREN], pinned.get("split_attempt"), pinned[_ready_support.KEY_REROUTE]["orphans"]),
            ([], None, replacements),
        )
        self.assertEqual(self._late_fields(gh), before)
        self.assertEqual(gh.label_history, [(_lineage_support.PARENT, LABEL_DECOMPOSING)])
        self.assertTrue(all(f"#{number}" in notice for number in replacements))

    def test_an_unlanded_retirement_holds_the_tick(self) -> None:
        # The decomposing tick a reroute handed the issue to drops the marker
        # before anything else. A retirement that does not land holds that
        # tick -- no decomposer runs -- and the marker waits for the next one,
        # which drops it and runs the decomposer.
        gh = FakeGitHubClient()
        child = _ready_support.ready_child(gh, ready_reroute=dict(_ready_support.CHANGED_REROUTE, receipt=RECEIPT))
        gh.set_workflow_label(child, LABEL_DECOMPOSING, guarded=False)
        gh.pinned_failures.refused.add(_ready_support.CHILD)

        held = self.decomposing_tick(gh, child)
        gh.pinned_failures.refused.clear()
        kept = gh.pinned_data(_ready_support.CHILD).get(_ready_support.KEY_REROUTE)
        ran = self.decomposing_tick(gh, child)

        self.assertEqual((held, ran), (0, 1))
        self.assertEqual(kept, dict(_ready_support.CHANGED_REROUTE, receipt=RECEIPT))
        self.assertNotIn(_ready_support.KEY_REROUTE, gh.pinned_data(_ready_support.CHILD))

    def _late_parent_over_replacements(self) -> tuple:
        """The root of a late lineage on `ready`, its replacement split cut short; the client and both replacements."""
        gh = FakeGitHubClient([make_issue(_lineage_support.PARENT, label="workflow:ready", body="the root, edited")])
        receipts = [
            _split_receipts.receipt(_lineage_support.PARENT, SPLIT_ATTEMPT, index, None)
            for index in range(2)
        ]
        replacements = [
            gh.create_child_issue(
                title=REPLACEMENT_SLICE,
                body=f"{REPLACEMENT_SLICE}\n\n{stamp}",
                parent_number=_lineage_support.PARENT,
                labels=["workflow:blocked"],
            ).number
            for stamp in receipts
        ]
        parent = _lineage_support.record(
            _lineage_support.own_split(),
            children=replacements[:1],
            split_attempt=SPLIT_ATTEMPT,
            expected_children_count=len(replacements),
            user_content_hash=STALE_USER_CONTENT_HASH,
        )
        gh.seed_state(_lineage_support.PARENT, **parent.data)
        return gh, replacements

    def _late_fields(self, gh: FakeGitHubClient) -> dict:
        """Every late field the parent's pinned comment carries but the consumer ledger, which a reroute extends."""
        return {
            key: recorded
            for key, recorded in gh.pinned_data(_lineage_support.PARENT).items()
            if key.startswith(LATE_KEY_PREFIX) and key != KEY_LATE_CONSUMERS
        }


class DecomposingHashChangeResetsSessionTest(
    unittest.TestCase,
    _PatchedWorkflowMixin,
):
    """The reset an issue already wearing `decomposing` takes on a body edit.

    The tick sees only what the fresh spawn reads back, so the wipe and the
    orphan notice are asked of the owner that performs them: nothing about the
    manifest a re-derivation throws away survives into the run below it.
    """

    def test_notice_names_every_child_it_orphans(self) -> None:
        for orphans in ([], list(ORPHANED_CHILD_NUMBERS)):
            with self.subTest(orphans=orphans):
                notice = _drift_reset._decomposition_drift_notice(orphans)

                self.assertIn("issue content changed", notice)
                self.assertEqual(ORPHAN_NOTICE_WORD in notice, bool(orphans))
                for child_number in orphans:
                    self.assertIn(f"#{child_number}", notice)

    def test_manifest_wipe_keeps_the_locked_spec(self) -> None:
        state = PinnedState(data={
            "decomposer_agent": LOCKED_BACKEND,
            KEY_DECOMPOSER_SESSION_ID: RETIRED_SESSION_ID,
            KEY_CHILDREN: list(ORPHANED_CHILD_NUMBERS),
            "dep_graph": {"411": []},
            "expected_children_count": len(ORPHANED_CHILD_NUMBERS),
            "split_ledger_sealed": 7,
            "umbrella": True,
            "awaiting_human": True,
            "park_reason": "decomposer_question",
        })

        _drift_reset._clear_decomposition_manifest(state)

        cleared = {
            KEY_DECOMPOSER_SESSION_ID: None,
            KEY_CHILDREN: [],
            "dep_graph": {},
            "expected_children_count": None,
            "split_ledger_sealed": None,
            "umbrella": None,
            "awaiting_human": False,
            "park_reason": None,
        }
        self.assertEqual({key: state.get(key) for key in cleared}, cleared)
        # The backend the pinned session id was written by outlives the
        # transcript it names: the fresh spawn has to land on the same CLI.
        self.assertEqual(state.get("decomposer_agent"), LOCKED_BACKEND)

    def test_reset_names_the_children_it_drops(self) -> None:
        gh = FakeGitHubClient()
        issue = make_issue(
            DECOMPOSING_ORPHAN_ISSUE_NUMBER,
            label=LABEL_DECOMPOSING,
            body="updated decomposition input",
        )
        gh.add_issue(issue)
        gh.seed_state(
            DECOMPOSING_ORPHAN_ISSUE_NUMBER,
            user_content_hash=STALE_USER_CONTENT_HASH,
            decomposer_agent=LOCKED_BACKEND,
            decomposer_session_id=RETIRED_SESSION_ID,
            children=list(ORPHANED_CHILD_NUMBERS),
        )
        state = gh.read_pinned_state(issue)

        _drift_reset._reset_decomposing_on_drift(gh, issue, state)

        notice = _comment_with_marker(
            gh,
            DECOMPOSING_ORPHAN_ISSUE_NUMBER,
            RESPAWN_NOTICE_MARKER,
        )
        self.assertIn(ORPHAN_NOTICE_WORD, notice)
        for child_number in ORPHANED_CHILD_NUMBERS:
            self.assertIn(f"#{child_number}", notice)
        # The notice quotes the children off the manifest, so it has to be
        # said before the wipe that stops tracking them.
        self.assertEqual(state.get(KEY_CHILDREN), [])
        self.assertNotEqual(
            state.get(KEY_USER_CONTENT_HASH),
            STALE_USER_CONTENT_HASH,
        )

    def test_drops_session_and_spawns_fresh(
        self,
    ) -> None:
        # An issue parked at `decomposing awaiting_human` whose body the
        # human edited mid-thread should NOT resume the decomposer's
        # prior session (which would only see the human's reply, not the
        # new body). Drop the session id, clear the park flags, force a
        # fresh spawn against the new body.
        gh, issue = _decomposing_drift_fixture()

        mocks = self._run(
            lambda: _decomposing._handle_decomposing(gh, _TEST_SPEC, issue),
            run_agent=_agent(
                session_id="new-sess",
                last_message=(
                    'fits one\n\n```orchestrator-manifest\n{"decision": "single", "rationale": "small"}\n```'
                ),
            ),
            has_new_commits=False,
        )

        # The decomposer ran fresh (no resume of the stale session).
        mocks["run_agent"].assert_called_once()
        launch = mocks["run_agent"].call_args
        self.assertIsNone(launch.kwargs["options"].resume_session_id)
        state = gh.pinned_data(DECOMPOSING_DRIFT_ISSUE_NUMBER)
        # The new session id from the fresh spawn was persisted, not the
        # stale one.
        self.assertEqual(state.get(KEY_DECOMPOSER_SESSION_ID), "new-sess")
        # Notice posted.
        self.assertIn(
            "issue content changed",
            "\n".join(_comments_for_issue(gh, DECOMPOSING_DRIFT_ISSUE_NUMBER)),
        )


class HandleBlockedEditTest(
    unittest.TestCase,
    _PatchedWorkflowMixin,
    _ready_support.ReadyTicks,
):
    """An edit to a `blocked` parent waits for its release: the poll goes on over it, and `ready` compares it.

    Nothing is hashed, told, reset, or rerouted on `blocked` -- the baseline,
    the manifest, the graph, and the rationale stand as they were -- while the
    walk releases what the graph permits and the parent finishes waiting once
    its children are done. The entry to `ready` that finish makes is where the
    edit is compared, before anything implements the parent.
    """

    def test_an_edited_parent_releases_its_children(self) -> None:
        gh, parent = _blocked_parent_drift_fixture(LABEL_BLOCKED)
        recorded = gh.pinned_data(BLOCKED_PARENT_NUMBER)

        self._run(lambda: _blocked._handle_blocked(gh, _TEST_SPEC, parent), run_agent=_agent())

        self.assertEqual(gh.label_history, [(BLOCKED_PARENT_CHILD_NUMBERS[1], LABEL_READY)])
        self.assertEqual(gh.pinned_data(BLOCKED_PARENT_NUMBER), recorded)
        self.assertEqual(_comments_for_issue(gh, BLOCKED_PARENT_NUMBER), [])

    def test_an_edited_parent_finishes_waiting(self) -> None:
        gh, parent = _blocked_parent_drift_fixture(LABEL_DONE)

        self._run(lambda: _blocked._handle_blocked(gh, _TEST_SPEC, parent), run_agent=_agent())
        finished = (
            list(gh.label_history),
            gh.pinned_data(BLOCKED_PARENT_NUMBER)[KEY_USER_CONTENT_HASH],
        )
        ran = self.ready_tick(gh, parent)

        self.assertEqual(finished, ([(BLOCKED_PARENT_NUMBER, LABEL_READY)], STALE_USER_CONTENT_HASH))
        self.assertEqual(
            (ran, gh.label_history[1:]),
            (0, [(BLOCKED_PARENT_NUMBER, LABEL_DECOMPOSING)]),
        )
        notice = _comment_with_marker(gh, BLOCKED_PARENT_NUMBER, RESPAWN_NOTICE_MARKER)
        self.assertIn(ORPHAN_NOTICE_WORD, notice)
        self.assertEqual([f"#{number}" in notice for number in BLOCKED_PARENT_CHILD_NUMBERS], [True, True])


class HandleUmbrellaHashDriftTest(
    unittest.TestCase,
    _PatchedWorkflowMixin,
):
    """Reviewer point 2: `umbrella` parents never enter implementation,
    so a body edit cannot be picked up by any later stage's drift check.
    Route back to `decomposing` per spec so the new manifest is derived
    against the updated body; the previously-tracked children become
    orphans and are listed in the notice."""

    def test_edited_umbrella_routes_back_before_close(
        self,
    ) -> None:
        gh, umbrella = _umbrella_drift_fixture()

        self._run(
            lambda: _umbrella._handle_umbrella(gh, _TEST_SPEC, umbrella),
            run_agent=_agent(),
        )

        state = gh.pinned_data(UMBRELLA_NUMBER)
        # Routed back to decomposing per spec.
        self.assertIn(
            (UMBRELLA_NUMBER, LABEL_DECOMPOSING),
            gh.label_history,
        )
        # Crucially: did NOT close the umbrella to `done`.
        self.assertNotIn((UMBRELLA_NUMBER, LABEL_DONE), gh.label_history)
        self.assertFalse(umbrella.closed)
        # Manifest state cleared so half-finished-recovery does not fire
        # against the stale children list / umbrella flag.
        self.assertEqual(
            (state.get(KEY_CHILDREN), state.get("umbrella")),
            ([], None),
        )
        self.assertNotEqual(
            state.get(KEY_USER_CONTENT_HASH),
            STALE_USER_CONTENT_HASH,
        )
        # Orphans listed in the notice.
        notice = _comment_with_marker(
            gh,
            UMBRELLA_NUMBER,
            RESPAWN_NOTICE_MARKER,
        )
        self.assertIn("#401", notice)
        self.assertIn("#402", notice)
        self.assertIn(ORPHAN_NOTICE_WORD, notice)

    def test_a_late_split_keeps_what_it_owes(self) -> None:
        # Two genuine edits, one taken on `umbrella` and one on `decomposing`,
        # so both resets run before the replacement manifest is split. The
        # generation is not manifest tracking: its register, snapshot, and
        # consumer ledger still say who the ref was preserved for, and the
        # children the edit orphaned are left exactly where they stood. The
        # one thing the replacement split adds is itself -- each child it
        # points at the ref, recorded as that ref's consumer beside them.
        seeded = self._late_split_umbrella()
        split = self._owed_fields(seeded.github)

        _late_support.walk_owner(self, seeded)
        seeded.parent.body = "edited again before the decomposer ran"
        self._run(
            lambda: _decomposing._handle_decomposing(seeded.github, _TEST_SPEC, seeded.parent),
            run_agent=_agent(session_id="replanned", last_message=REPLACEMENT_MANIFEST),
        )

        created = [child.number for child in seeded.github.created_child_issues]
        pinned = seeded.github.pinned_data(_late_support.PARENT_NUMBER)
        self.assertEqual(self._owed_fields(seeded.github), split)
        self.assertEqual(len(created), 2)
        self.assertEqual(pinned[KEY_LATE_CONSUMERS], sorted([_late_support.CHILD_NUMBER, *created]))
        self.assertEqual(pinned.get(KEY_CHILDREN), created)
        self.assertEqual(
            sum(
                RESPAWN_NOTICE_MARKER in body
                for body in _comments_for_issue(seeded.github, _late_support.PARENT_NUMBER)
            ),
            2,
        )
        self.assertNotIn(_late_support.CHILD_NUMBER, dict(seeded.github.label_history))
        self.assertFalse(seeded.github.get_issue(_late_support.CHILD_NUMBER).closed)

    def _late_split_umbrella(self) -> _late_support.SeededUmbrella:
        """An umbrella a late split made, its child still running, then edited.

        It still owes the branch and still holds the ref, which is what a
        reset that took the generation with the manifest would lose. It is the
        root of its lineage, at depth 0, which is what its replacements are
        seeded one level below.
        """
        seeded = _late_support.split_umbrella(
            LateResourceState.PENDING,
            snapshot=LateResourceState.RETAINED,
            child_label=_late_support.LABEL_READY,
            owner=_late_support.OwnerSeed(child_closed=False),
        )
        seeded.github.seed_state(_late_support.PARENT_NUMBER, **{
            **seeded.github.pinned_data(_late_support.PARENT_NUMBER),
            KEY_USER_CONTENT_HASH: STALE_USER_CONTENT_HASH,
            KEY_LATE_DEPTH: 0,
        })
        return seeded

    def _owed_fields(self, github: FakeGitHubClient) -> dict:
        """Every late field the parent's pinned comment carries right now.

        All but the consumer ledger, which a replacement split adds to.
        """
        return {
            key: recorded
            for key, recorded in github.pinned_data(_late_support.PARENT_NUMBER).items()
            if key.startswith(LATE_KEY_PREFIX) and key != KEY_LATE_CONSUMERS
        }
