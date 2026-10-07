# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The order the workflow routes an interrupted rebase in, and what its decision leaves the tick.

Every road the recovery can take ends on a git owner -- a clear, or a park --
or on one of the workflow's own: the retry, or the finish of a push already
landed. Each is watched on the owner that defines it, and the cases pin which
one a reading selects, and which readings are never taken on the way there.
"""
from __future__ import annotations

import contextlib
import dataclasses
import unittest
from types import MappingProxyType
from unittest.mock import MagicMock, patch

from orchestrator.git.base_sync import (
    outcomes,
    replay_publication_parks as _replay_publication_parks,
    snapshot,
)
from orchestrator.git.verification import probes as _probes
from orchestrator.workflow.engine import (
    rewrite_landed as _rewrite_landed,
    rewrite_recovery as _rewrite_recovery,
    rewrite_retry as _rewrite_retry,
)
from tests.git.base_sync import base_sync_helpers as fixtures
from tests.git.base_sync.refresh_test_support import MOVED_CHECKOUT_SHA

FETCH_SNAPSHOT = "_fetch_recovery_snapshot"
COMPLETE_SNAPSHOT = "_complete_recovery_snapshot"
CLEAR_INELIGIBLE = "_clear_ineligible_recovery"
CLEAR_UNCHANGED = "_clear_unchanged_recovery"
STRANDED = "_park_stranded_recovery"
LANDED = "recovers"
UNKNOWN_COMPARISON = "_reject_unknown_recovery_comparison"
DIVERGED = "_park_diverged_recovery"
RETRY = "retries"
RECOVERS = "recovers"

RETRY_COMMENT_ID = 200

# Every answer a completed comparison can resolve into, and the owner it is
# selected on.
ANSWERS = (
    (_rewrite_landed, LANDED),
    (outcomes, UNKNOWN_COMPARISON),
    (outcomes, DIVERGED),
    (_rewrite_retry, RETRY),
)

# Each completed comparison over a comment with no record of a replay, and the
# single answer it selects. The ahead-only row is the only one that reaches a
# push, which is what keeps a force-push off every head the tick could not
# prove is ahead of the remote it read.
ROUTE_CASES = (
    (fixtures._snapshot(remote_head=fixtures.RECOVERED_SHA), LANDED),
    (fixtures._snapshot(), UNKNOWN_COMPARISON),
    (fixtures._snapshot(ahead=1, behind=2), DIVERGED),
    (fixtures._snapshot(ahead=1), RETRY),
)

_OWNERS = MappingProxyType({
    CLEAR_INELIGIBLE: snapshot,
    CLEAR_UNCHANGED: snapshot,
    COMPLETE_SNAPSHOT: snapshot,
    FETCH_SNAPSHOT: snapshot,
})


def _handled(recovered: bool = True) -> MagicMock:
    """A collaborator stub reporting whether it owns the tick."""
    return MagicMock(return_value=recovered)


@contextlib.contextmanager
def _routed(**collaborators):
    """Patch the named recovery collaborators on the owner they live on."""
    with contextlib.ExitStack() as stack:
        for name, replacement in collaborators.items():
            stack.enter_context(patch.object(_OWNERS[name], name, replacement))
        yield


@contextlib.contextmanager
def _every_answer(selected: dict):
    """Patch every answer the route can select, recording them by name."""
    with contextlib.ExitStack() as stack:
        for owner, name in ANSWERS:
            selected[name] = _handled()
            stack.enter_context(patch.object(owner, name, selected[name]))
        yield


class RecoveryRouteTest(unittest.TestCase):
    """Every question is asked before the one it would make unsafe."""

    def test_ineligible_label_clears_before_any_fetch(self) -> None:
        cleared = _handled()
        fetch = MagicMock()

        with _routed(**{CLEAR_INELIGIBLE: cleared, FETCH_SNAPSHOT: fetch}), self._standing_on(
            fixtures.PRE_REBASE_SHA,
        ):
            recovered = _rewrite_recovery.recovers(self._relabelled(fixtures._recovery_context()))

        self.assertTrue(recovered)
        cleared.assert_called_once()
        # An issue nobody is refreshing any more is not worth a network hop.
        fetch.assert_not_called()

    def test_an_ineligible_label_keeps_a_replay(self) -> None:
        # The checkout has moved off the anchor and no road under this label
        # will ever classify it, so the record a clear would strand is kept
        # and a human is asked instead.
        cleared = _handled()
        parked = _handled()

        with _routed(**{CLEAR_INELIGIBLE: cleared}), self._standing_on(
            MOVED_CHECKOUT_SHA,
        ), patch.object(_replay_publication_parks, STRANDED, parked):
            _rewrite_recovery.recovers(self._relabelled(fixtures._recovery_context()))

        parked.assert_called_once()
        cleared.assert_not_called()

    def test_unreadable_snapshot_owns_the_tick(self) -> None:
        # The fetch already reset and parked, so owning the tick is what stops
        # the caller from rebasing against a head it could not verify.
        complete = MagicMock()

        with _routed(**{FETCH_SNAPSHOT: MagicMock(return_value=None), COMPLETE_SNAPSHOT: complete}):
            recovered = _rewrite_recovery.recovers(fixtures._recovery_context())

        self.assertTrue(recovered)
        complete.assert_not_called()

    def test_unmoved_head_falls_back(self) -> None:
        unchanged = fixtures._snapshot(local_head=fixtures.PRE_REBASE_SHA)
        cleared = _handled(recovered=False)
        complete = MagicMock()

        with _routed(**{
            FETCH_SNAPSHOT: MagicMock(return_value=unchanged),
            CLEAR_UNCHANGED: cleared,
            COMPLETE_SNAPSHOT: complete,
        }):
            recovered = _rewrite_recovery.recovers(fixtures._recovery_context())

        # Nothing was rewritten, so there is nothing to compare and the same
        # tick continues into the normal rebase flow.
        self.assertFalse(recovered)
        cleared.assert_called_once()
        complete.assert_not_called()

    @contextlib.contextmanager
    def _standing_on(self, head_sha: str):
        """Answer the local head read the ineligible road takes for itself."""
        with patch.object(_probes, "_head_sha", MagicMock(return_value=head_sha)):
            yield

    def _relabelled(self, context):
        return dataclasses.replace(context, label="workflow:implementing")


class RecoveryComparisonTest(unittest.TestCase):
    """One completed comparison resolves into exactly one answer."""

    def test_each_comparison_selects_its_answer(self) -> None:
        for completed, answer in ROUTE_CASES:
            with self.subTest(answer=answer):
                selected = {}

                with _every_answer(selected), _routed(**{
                    FETCH_SNAPSHOT: MagicMock(return_value=fixtures._snapshot()),
                    COMPLETE_SNAPSHOT: MagicMock(return_value=completed),
                }):
                    self.assertTrue(_rewrite_recovery.recovers(fixtures._recovery_context()))

                self.assertIs(selected.pop(answer).call_args.args[1], completed)
                for unselected in selected.values():
                    unselected.assert_not_called()

    def test_unverified_comparison_owns_the_tick(self) -> None:
        # `_complete_recovery_snapshot` already parked; no answer applies.
        selected = {}

        with _every_answer(selected), _routed(**{
            FETCH_SNAPSHOT: MagicMock(return_value=fixtures._snapshot()),
            COMPLETE_SNAPSHOT: MagicMock(return_value=None),
        }):
            self.assertTrue(_rewrite_recovery.recovers(fixtures._recovery_context()))

        for unselected in selected.values():
            unselected.assert_not_called()


class RecoveryDecisionTest(unittest.TestCase):
    """Crash recovery runs first, and only an unspent retry survives it."""

    def test_no_anchor_keeps_the_reported_retry(self) -> None:
        recover = _handled()

        with patch.object(_rewrite_recovery, RECOVERS, recover):
            decision = _rewrite_recovery.decides(fixtures._sync_context(), RETRY_COMMENT_ID)

        recover.assert_not_called()
        self.assertTrue(decision.should_continue)
        self.assertEqual(decision.consumed_comment_id, RETRY_COMMENT_ID)

    def test_finished_recovery_owns_the_tick(self) -> None:
        recover = _handled()

        with patch.object(_rewrite_recovery, RECOVERS, recover):
            decision = _rewrite_recovery.decides(self._anchored_context(), RETRY_COMMENT_ID)

        self.assertFalse(decision.should_continue)
        # Recovery is the side that can publish the rewrite, so the retry it
        # was handed is what it unparks with, over the lag the refresh read.
        resumed = recover.call_args.args[0]
        self.assertEqual(resumed.unparking_consumed_max, RETRY_COMMENT_ID)
        self.assertEqual(resumed.behind, fixtures.BEHIND_BY)
        self.assertEqual(resumed.pending_pre_rebase_sha, fixtures.PRE_REBASE_SHA)

    def test_released_park_drops_a_spent_retry(self) -> None:
        # Recovery cleared the park itself, so the reply it consumed must not
        # be re-consumed by the rebase this tick continues into.
        with patch.object(_rewrite_recovery, RECOVERS, _handled(recovered=False)):
            decision = _rewrite_recovery.decides(self._anchored_context(), RETRY_COMMENT_ID)

        self.assertTrue(decision.should_continue)
        self.assertIsNone(decision.consumed_comment_id)

    def test_surviving_park_keeps_its_retry(self) -> None:
        with patch.object(_rewrite_recovery, RECOVERS, _handled(recovered=False)):
            decision = _rewrite_recovery.decides(
                self._anchored_context(awaiting_human=True), RETRY_COMMENT_ID,
            )

        self.assertTrue(decision.should_continue)
        self.assertEqual(decision.consumed_comment_id, RETRY_COMMENT_ID)

    def _anchored_context(self, **state_fields):
        return fixtures._sync_context(pending_pre_rebase_sha=fixtures.PRE_REBASE_SHA, **state_fields)


if __name__ == "__main__":
    unittest.main()
