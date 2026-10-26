# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""User-content hash and drift detection tests."""
from __future__ import annotations

import itertools
import unittest
from unittest.mock import Mock, patch

from orchestrator.workflow.engine import content_hash as _content_hash, drift
from tests.workflow.engine import drift_test_support as support

OBSERVED = "observed_user_content_hash"

# An operator's bare continue, and a trusted comment carrying a requirement.
_BARE_CONTINUE = support.FakeComment(
    id=100,
    body=support.CONTINUE_COMMAND,
    user=support.FakeUser("dave"),
)
_GUIDANCE_ID = 101
_GUIDANCE = support.FakeComment(id=_GUIDANCE_ID, body="and also handle empty input")

_RECORDED_BODY = "the body as its reading was taken"

# Where a waiting issue's record keeps its reading, and whether the check's
# caller holds a reading of the thread: every pairing of no reading, a
# baseline, and an observed one.
_WAITING = tuple(itertools.product(
    (None, support.KEY_USER_CONTENT_HASH, OBSERVED),
    (False, True),
))

# Where a record keeps a reading an earlier producer spelled, and whether the
# check is asked on a parked tick, measured by what the park had read.
_SPELLED_OTHERWISE = tuple(itertools.product(
    (support.KEY_USER_CONTENT_HASH, OBSERVED),
    (False, True),
))

# What the check answers every one of them: no drift, no fingerprint taken,
# its claimed reading still the record as pinned, and no write.
_ASKED_NOTHING = (None, 0, True, 0)


class ComputeUserContentHashTest(unittest.TestCase):
    """The hash must include user-visible content (title, body, human
    comments) and exclude orchestrator-authored content (pinned-state
    marker comments, anything in `orchestrator_comment_ids`). Author-login
    matching is intentionally avoided because the orchestrator PAT is
    often shared with a human reviewer's GitHub account."""

    def test_hash_changes_when_body_changes(self) -> None:
        issue_a = support.make_issue(1, body="old body")
        issue_b = support.make_issue(1, body=support.NEW_BODY)
        self.assertNotEqual(
            _content_hash._compute_user_content_hash(issue_a, set()),
            _content_hash._compute_user_content_hash(issue_b, set()),
        )

    def test_hash_changes_when_title_changes(self) -> None:
        issue_a = support.make_issue(1, title="old", body="b")
        issue_b = support.make_issue(1, title="new", body="b")
        self.assertNotEqual(
            _content_hash._compute_user_content_hash(issue_a, set()),
            _content_hash._compute_user_content_hash(issue_b, set()),
        )

    def test_orchestrator_comments_filtered_by_id(self) -> None:
        # A human comment with the same body as a bot comment must still
        # affect the hash; only the recorded bot id is filtered.
        human = support.FakeComment(
            id=100,
            body="please retry",
            user=support.FakeUser(support.TRUSTED_AUTHOR),
        )
        bot = support.FakeComment(
            id=support._BOT_COMMENT_ID,
            body="picking this up",
            user=support.FakeUser(support.TRUSTED_AUTHOR),
        )
        issue_with_human = support.make_issue(1, comments=[human])
        issue_with_both = support.make_issue(1, comments=[human, bot])
        self.assertEqual(
            _content_hash._compute_user_content_hash(
                issue_with_human,
                {support._BOT_COMMENT_ID},
            ),
            _content_hash._compute_user_content_hash(
                issue_with_both,
                {support._BOT_COMMENT_ID},
            ),
        )
        # Without filtering the bot comment, the hash differs.
        self.assertNotEqual(
            _content_hash._compute_user_content_hash(issue_with_human, set()),
            _content_hash._compute_user_content_hash(issue_with_both, set()),
        )

    def test_state_marker_filtered_by_marker(self) -> None:
        pinned = support.FakeComment(
            id=support._PINNED_COMMENT_ID,
            body="<!--orchestrator-state {\"k\": 1}-->",
        )
        issue = support.make_issue(1)
        issue_with_pinned = support.make_issue(1, comments=[pinned])
        # Pinned-state comment id is NOT in orchestrator_ids but its marker
        # body causes it to be filtered.
        self.assertEqual(
            _content_hash._compute_user_content_hash(issue, set()),
            _content_hash._compute_user_content_hash(issue_with_pinned, set()),
        )

    def test_bare_continue_ignored_guidance_counts(
        self,
    ) -> None:
        # A bare `/orchestrator continue` is an operator command, not
        # requirements content: it must not shift the hash (else it routes
        # through generic drift handling instead of the intentional
        # session-limit retry). The same command carrying real guidance is
        # NOT bare, so it still shifts the hash.
        issue = support.make_issue(1)
        bare = support.FakeComment(
            id=100, body=support.CONTINUE_COMMAND, user=support.FakeUser(support.TRUSTED_AUTHOR),
        )
        guided = support.FakeComment(
            id=support._GUIDED_CONTINUE_COMMENT_ID,
            body="/orchestrator continue\nalso rename the flag",
            user=support.FakeUser(support.TRUSTED_AUTHOR),
        )
        self.assertEqual(
            _content_hash._compute_user_content_hash(issue, set()),
            _content_hash._compute_user_content_hash(
                support.make_issue(1, comments=[bare]), set()
            ),
        )
        self.assertNotEqual(
            _content_hash._compute_user_content_hash(issue, set()),
            _content_hash._compute_user_content_hash(
                support.make_issue(1, comments=[guided]), set()
            ),
        )


def _observed_issue(*, edited: bool):
    """An issue whose one recorded reading is an observed one, edited since or not."""
    gh = support.FakeGitHubClient()
    issue = support.make_issue(1)
    gh.add_issue(issue)
    gh.seed_state(1, **{
        OBSERVED: _content_hash._compute_user_content_hash(issue, set()),
    })
    if edited:
        issue.body = support.NEW_BODY
    return gh, issue


def _asked_while_waiting(recorded_as: str | None, *, held: bool) -> tuple:
    """Ask the drift check of an issue on `workflow:blocked`, edited since the reading its record carries.

    The body moved and a trusted comment was written under it since the
    reading recorded under `recorded_as` -- none at all for None -- and the
    check's caller holds a reading of the thread where `held`. Answers what
    the check returned, how many fingerprints it took, whether the claimed
    reading still matches the record as pinned, and how many writes were sent.
    """
    context = support._content_change_case(_RECORDED_BODY, support.NEW_BODY)
    context.issue.comments.append(_GUIDANCE)
    context.issue.labels = [support.FakeLabel(support.LABEL_BLOCKED)]
    record = {} if recorded_as is None else {recorded_as: context.prior_hash}
    context.github.seed_state(1, **record)
    state = context.github.read_pinned_state(context.issue)
    fingerprint = Mock(wraps=_content_hash._compute_user_content_hash)
    with patch.object(_content_hash, "_compute_user_content_hash", fingerprint):
        changed = drift._detect_user_content_change(
            context.github, context.issue, state, reading=list(context.issue.comments) if held else None,
        )
    return (
        changed,
        fingerprint.call_count,
        state.data == context.github.pinned_data(1),
        context.github.write_state_calls,
    )


class DetectUserContentChangeTest(unittest.TestCase):
    def test_a_waiting_issue_is_asked_nothing(self) -> None:
        # Whatever its record carries -- no reading, a baseline, or an
        # observed reading in its place -- and whether or not its caller
        # holds a reading of the thread, an issue on `workflow:blocked` is
        # answered with no fingerprint taken, nothing staged, and nothing
        # written: its requirements wait for `ready`.
        for recorded_as, held in _WAITING:
            with self.subTest(recorded_as=recorded_as, held=held):
                asked = _asked_while_waiting(recorded_as, held=held)

                self.assertEqual(asked, _ASKED_NOTHING)


    def test_first_call_persists_and_returns_none(self) -> None:
        # The first encounter has no baseline; we record the current value
        # AND write pinned state immediately so a parked/idle tick can't
        # silently absorb a later edit as the new baseline.
        gh = support.FakeGitHubClient()
        issue = support.make_issue(1)
        gh.add_issue(issue)
        state = gh.read_pinned_state(issue)
        before = gh.write_state_calls
        detected_hash = drift._detect_user_content_change(gh, issue, state)
        self.assertIsNone(detected_hash)
        self.assertEqual(
            state.get(support.KEY_USER_CONTENT_HASH),
            _content_hash._compute_user_content_hash(issue, set()),
        )
        # Durably written so a later edit after an early-return tick is
        # correctly classified as drift, not absorbed as the new baseline.
        self.assertEqual(gh.write_state_calls, before + 1)
        self.assertEqual(
            gh.pinned_data(1).get(support.KEY_USER_CONTENT_HASH),
            state.get(support.KEY_USER_CONTENT_HASH),
        )

    def test_an_observed_reading_stands_in(self) -> None:
        # A stage that acted on a reading without consuming it recorded it as
        # observed. With no baseline recorded, the first call compares against
        # that: an unchanged thread is persisted as the baseline, and an edit
        # made since is the drift it is rather than the baseline.
        for edited in (False, True):
            with self.subTest(edited=edited):
                gh, issue = _observed_issue(edited=edited)

                detected_hash = drift._detect_user_content_change(
                    gh, issue, gh.read_pinned_state(issue),
                )

                current = _content_hash._compute_user_content_hash(issue, set())
                self.assertEqual(detected_hash, current if edited else None)
                self.assertEqual(
                    gh.pinned_data(1).get(support.KEY_USER_CONTENT_HASH),
                    None if edited else current,
                )

    def test_unchanged_returns_none(self) -> None:
        gh = support.FakeGitHubClient()
        issue = support.make_issue(1)
        gh.add_issue(issue)
        prior_hash = _content_hash._compute_user_content_hash(issue, set())
        gh.seed_state(1, user_content_hash=prior_hash)
        state = gh.read_pinned_state(issue)
        before = gh.write_state_calls
        self.assertIsNone(
            drift._detect_user_content_change(gh, issue, state)
        )
        # No extra write when the baseline already matches.
        self.assertEqual(gh.write_state_calls, before)

    def test_body_change_returns_hash_without_persist(
        self,
    ) -> None:
        context = support._content_change_case("old", support.NEW_BODY)
        detected_hash = drift._detect_user_content_change(
            context.github,
            context.issue,
            context.state,
        )
        self.assertEqual(detected_hash, context.current_hash)
        self.assertNotEqual(detected_hash, context.prior_hash)
        # The helper does NOT auto-persist on a real change; the caller
        # decides whether to act and persist (so the routing branches can
        # use the comparison without committing to a state write).
        self.assertEqual(
            context.github.write_state_calls,
            context.before_writes,
        )
        self.assertEqual(
            context.state.get(support.KEY_USER_CONTENT_HASH),
            context.prior_hash,
        )


class BareContinueBaselineTest(unittest.TestCase):
    """The drift check over a thread carrying an operator's bare continue."""

    def test_a_bare_continue_reads_unchanged(self) -> None:
        # An operator wrote a bare `/orchestrator continue` under the recorded
        # baseline. It is a control the stage answers, not a requirement, so
        # the thread reads unchanged: no drift, and nothing written.
        context = support._content_change_case("body", "body")
        context.issue.comments.append(_BARE_CONTINUE)

        detected_hash = drift._detect_user_content_change(
            context.github, context.issue, context.state,
        )

        self.assertIsNone(detected_hash)
        self.assertEqual(context.github.write_state_calls, context.before_writes)
        self.assertEqual(
            context.github.pinned_data(1).get(support.KEY_USER_CONTENT_HASH),
            context.prior_hash,
        )

    def test_real_edit_with_bare_continue_drifts(self) -> None:
        # The continue leaves the hash alone, and only the continue: a body
        # edited beside it is the drift it is.
        context = support._content_change_case(
            "old", support.NEW_BODY, comments=(_BARE_CONTINUE,),
        )

        detected_hash = drift._detect_user_content_change(
            context.github, context.issue, context.state,
        )

        self.assertEqual(detected_hash, context.current_hash)
        self.assertNotEqual(detected_hash, context.prior_hash)

    def test_a_reading_spelled_otherwise_is_drift(self) -> None:
        # The record's reading counted the bare continue the thread carries,
        # as an earlier producer spelled it, and the current fingerprint
        # leaves that out. It is no reading of this thread, as a baseline or
        # as the observed reading standing in for one, on a parked tick or
        # any other: the check reports the drift for a route to answer, and
        # neither recognizes nor rewrites the value.
        for recorded_as, parked in _SPELLED_OTHERWISE:
            with self.subTest(recorded_as=recorded_as, parked=parked):
                changed, current, *kept = _asked_over_an_earlier_spelling(recorded_as, parked=parked)

                self.assertEqual(changed, current)
                self.assertEqual(kept, [True, True], "the reading was recognized or rewritten")


def _asked_over_an_earlier_spelling(recorded_as: str, *, parked: bool) -> tuple:
    """Ask the drift check of an unedited thread whose record keeps a reading that counted its bare continue.

    The reading is recorded under `recorded_as`, and the check is asked on a
    parked tick -- the park having read the whole thread -- where `parked`.
    Answers what the check returned, the thread's current fingerprint, and
    whether the claimed reading and the pinned record each still read as
    seeded.
    """
    context = support._content_change_case("", "", comments=(_BARE_CONTINUE,))
    context.github.seed_state(1, **{recorded_as: support.continue_counting_hash(context.issue)})
    seeded = context.github.pinned_data(1)
    state = context.github.read_pinned_state(context.issue)
    changed = drift._detect_user_content_change(
        context.github, context.issue, state,
        answered=list(context.issue.comments) if parked else None,
    )
    kept = (state.data == seeded, context.github.pinned_data(1) == seeded)
    return (changed, context.current_hash, *kept)


if __name__ == "__main__":
    unittest.main()
