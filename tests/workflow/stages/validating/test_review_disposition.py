# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A returned reviewer's verdict, persisted before anything is done with it.

The verdict and the transaction its declared commands are minted as go down in
one write before the evidence is published, and neither verdict is acted on
until that evidence settles: an approval reaches the approval arc only over
settled, passing evidence that covers the configured verification, and parks
otherwise. A verdict the comment has no room for parks with nothing acted on,
and one whose subject moves is dropped. A tick that stops short leaves the
verdict for the next one to finish with no second reviewer, no second fold of
its usage, and no round spent -- and a change request reaches exactly one
developer, only once its feedback is posted.
"""
from __future__ import annotations

import unittest
from unittest.mock import patch

from orchestrator.github.pinned_state import MAX_PINNED_BODY
from tests.workflow import published_reports as _published_reports
from tests.workflow.fixtures import LABEL_DOCUMENTING, LABEL_FIXING, LABEL_VALIDATING, _agent, _reported
from tests.workflow.stages.validating import review_verdict_readings as _read, review_verdict_test_support as _world
from tests.workflow.stages.validating.validating_review_test_support import FIX_HEAD_SHAS

VERIFY = "_run_verify_commands"

UNVERIFIED = "reviewer_unverified"

UNRECORDED = "reviewer_unrecorded"

DOCUMENTING = (_world.ISSUE, LABEL_DOCUMENTING)

HANDED_BACK = ((_world.ISSUE, LABEL_FIXING), (_world.ISSUE, LABEL_VALIDATING))

LATER_REPORT = "Covered the empty configuration as well; the suite passes."

# A commit and an evidence digest nothing in the world names.
OTHER_HEAD = "0123456789abcdef0123456789abcdef01234567"

OTHER_DIGEST = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"

# A reviewer asking for that change beside its declared run, which failed,
# and with nothing declared beside it.
REQUESTING = _world.declared_run(exit_status=1, verdict="CHANGES_REQUESTED")

UNDECLARED_REQUEST = f"{_world.REQUESTED}\n\nVERDICT: CHANGES_REQUESTED"

# The requests between a change request's verdict and its handoff behind
# which a later report settles, and how many feedback posts that leaves.
_BEFORE_THE_HANDOFF = (
    (
        "the verdict's write",
        ("write_pinned_state", lambda state: state.get(_world.RETURNED_VERDICT) is not None),
        0,
    ),
    ("the feedback post", ("pr_comment", lambda body: _read.FEEDBACK_NOTICE in body), 1),
)

# Approvals that rely on no evidence an approval may rest on, and the words
# the park names each for.
_UNVERIFIED_APPROVALS = (
    ("nothing declared", "LGTM\n\nVERDICT: APPROVED", "declared no verification"),
    ("a failed run", _world.declared_run(exit_status=1), "did not exit 0"),
    ("another command", _world.declared_run(command="uv run ruff check"), "every command `VERIFY_COMMANDS`"),
    ("another head", _world.declared_run().replace(_world.HEAD, OTHER_HEAD), "names another commit"),
)

# Settled evidence a waiting approval's claim says passed and covers the
# configuration, and the words the park names what it really shows for.
_MISDESCRIBED = (
    ("a failed run", {"exit_status": 1}, "did not exit 0"),
    ("another command", {"command": "uv run ruff check"}, "every command `VERIFY_COMMANDS`"),
)

# A reuse naming the evidence it was handed, or other evidence, and where the
# approval ends up: the approval arc, or the park.
_REUSES = (
    ("the settled evidence", lambda digest: digest, ([DOCUMENTING], None)),
    ("other evidence", lambda _digest: OTHER_DIGEST, ([], UNVERIFIED)),
)

# A change request's feedback longer than most of what the pinned comment
# holds, and a failed run's output the transaction quotes again: the filler
# leaves room for the round's own records and not for the verdict, or for the
# verdict and not its transaction.
_LONG = "12 passed, 1 failed " * 1000

_NO_ROOM = (
    ("for the verdict", f"{_LONG}\n\nVERDICT: CHANGES_REQUESTED", MAX_PINNED_BODY - len(_LONG)),
    (
        "for its evidence",
        _world.declared_run(exit_status=1, verdict="CHANGES_REQUESTED", output=_LONG),
        MAX_PINNED_BODY - len(_LONG) * 3 // 2,
    ),
)


def _developer():
    """The developer run a handed change request is answered by."""
    return _agent(session_id=_world.DEV_SESSION, last_message=_reported("fixed"))


def _one_developer_later(spent: tuple) -> tuple:
    """What `spent` becomes once one developer answered and its pushed fix spent the one round.

    Only that developer is charged and folded: the reviewer's tokens are not
    folded again.
    """
    runs, folded, tokens, _ = spent
    return (runs + 1, folded + 1, tokens, 1)


class _ReadsTheCommentAtThePost:
    """Artifact posts that record what the pinned comment carried as each was made."""

    def __init__(self, case) -> None:
        self._case = case
        self._post = case.github._post_verification_artifact
        self.seen: list[dict] = []

    def __call__(self, pull_request, body):
        self.seen.append(self._case.pinned())
        return self._post(pull_request, body)


class _SettlesALaterReportBehind:
    """A client request behind which, the first time `when` says, a later report settles on the same head."""

    def __init__(self, case, request: str, when) -> None:
        self._case = case
        self._name = request
        self._request = getattr(case.github, request)
        self._when = when
        self._settled = False

    def __call__(self, target, asked):
        answered = self._request(target, asked)
        if not self._settled and self._when(asked):
            self._settled = True
            _published_reports.republishes_the_report(self._case.github, self._case.issue, LATER_REPORT)
        return answered

    def returning(self, message: str) -> dict:
        """The tick in which a reviewer returned `message`, over a client carrying this request."""
        with patch.object(self._case.github, self._name, self):
            return self._case.returns(message)


class _RefusesTheFeedback:
    """A pull request that refuses the reviewer's feedback post once, and takes every other comment."""

    def __init__(self, github) -> None:
        self._posts = github.pr_comment
        self._refused = False

    def __call__(self, pr_number, body):
        if not self._refused and _read.FEEDBACK_NOTICE in body:
            self._refused = True
            raise RuntimeError("pull request comment rejected")
        return self._posts(pr_number, body)


class DisposedApprovalTest(_world.ReviewVerdictWorld, unittest.TestCase):
    """An approval acts only over settled, passing evidence covering the configuration."""

    def test_the_verdict_is_written_before_publishing(self) -> None:
        posting = _ReadsTheCommentAtThePost(self)
        with patch.object(self.github, "_post_verification_artifact", posting):
            self.returns(_world.declared_run())

        seen = posting.seen[-1]
        claim = seen[_world.RETURNED_VERDICT]["evidence"]
        self.assertEqual(
            (
                len(posting.seen),
                claim["use"],
                claim["passed"] and claim["covers"],
                seen[_world.PENDING_EVIDENCE]["receipt"],
            ),
            (1, "published", True, claim["receipt"]),
        )
        self.assertEqual(
            (
                self.github.label_history,
                self.pinned()[_world.RETURNED_VERDICT],
                len(_read.artifacts(self)),
            ),
            ([DOCUMENTING], None, 1),
        )

    def test_an_approval_without_valid_evidence_parks(self) -> None:
        for name, message, refusal in _UNVERIFIED_APPROVALS:
            with self.subTest(name):
                self.setUp()

                ran = self.returns(message)

                pinned = self.pinned()
                self.assertEqual(
                    (pinned[_world.PARK_REASON], pinned[_world.RETURNED_VERDICT], ran[VERIFY].call_count),
                    (UNVERIFIED, None, 0),
                )
                self.assertEqual(self.github.label_history, [])
                self.assertIn(refusal, self.github.posted_comments[-1][1])

    def test_a_reuse_counts_only_for_handed_evidence(self) -> None:
        for name, named, outcome in _REUSES:
            with self.subTest(name):
                self.setUp()
                digest = _read.settles_evidence(self).content_revision

                self.returns(f"Covered.\n\nVERIFICATION: REUSED sha256:{named(digest)}\n\nVERDICT: APPROVED")

                self.assertEqual(
                    (self.github.label_history, self.pinned().get(_world.PARK_REASON)), outcome,
                )
                self.assertEqual(len(_read.artifacts(self)), 1, "a reuse publishes nothing of its own")

    def test_a_claim_is_held_to_the_evidence_it_names(self) -> None:
        # The claim's flags are the verdict's copy of what the evidence said;
        # the approval rests on the evidence, which shows otherwise.
        for name, settled, refusal in _MISDESCRIBED:
            with self.subTest(name):
                self.setUp()
                _read.seeds_an_approval(self, _read.settles_evidence(self, **settled))

                ran = self.dispatched()

                pinned = self.pinned()
                self.assertEqual(
                    (
                        pinned[_world.PARK_REASON],
                        pinned[_world.RETURNED_VERDICT],
                        ran[VERIFY].call_count,
                        ran[_world.RUN_AGENT].call_count,
                    ),
                    (UNVERIFIED, None, 0, 0),
                )
                self.assertEqual(self.github.label_history, [])
                self.assertIn(refusal, self.github.posted_comments[-1][1])

    def test_a_held_publication_needs_no_reviewer(self) -> None:
        # The post lands and its response is lost: the tick holds with the
        # verdict and its transaction owed. The next tick's reconciliation
        # finds the artifact by its receipt, and the approval goes on from the
        # verdict the first tick wrote.
        self._held(_world.declared_run())
        waiting = self.pinned()
        spent = _read.spent(self)
        self.assertEqual(
            (
                waiting[_world.RETURNED_VERDICT]["verdict"],
                waiting[_world.PENDING_EVIDENCE] is None,
                self.github.label_history,
            ),
            ("approved", False, []),
        )

        finished = self.dispatched()

        self.assertEqual(
            (
                finished[_world.RUN_AGENT].call_count,
                _read.spent(self),
                len(_read.artifacts(self)),
            ),
            (0, spent, 1),
        )
        self.assertEqual(
            (self.github.label_history, self.pinned()[_world.RETURNED_VERDICT]),
            ([DOCUMENTING], None),
        )

    def test_a_moved_subject_drops_the_verdict(self) -> None:
        # A later report settles while the approval waits on its publication:
        # the next tick drops it and hands a fresh reviewer the later report.
        self._held(_world.declared_run())
        _published_reports.republishes_the_report(self.github, self.issue, LATER_REPORT)

        ran = self.dispatched(_agent(session_id="rev-2", last_message="Reading.\n\nVERDICT: UNKNOWN"))

        self.assertEqual(
            (ran[_world.RUN_AGENT].call_count, self.pinned()[_world.RETURNED_VERDICT]),
            (1, None),
        )
        self.assertIn(f"> {LATER_REPORT}", ran[_world.RUN_AGENT].call_args.args[1])

    def _held(self, message: str) -> None:
        """Return `message` over a pull request that lands the artifact and loses the response."""
        self.github.report_failures.lost.add(_world.PR)
        self.returns(message)
        self.github.report_failures.lost.discard(_world.PR)


class DisposedChangeRequestTest(_world.ReviewVerdictWorld, unittest.TestCase):
    """A change request reaches one developer, and only over what stands."""

    def test_a_held_request_reaches_one_developer(self) -> None:
        self.github.report_failures.lost.add(_world.PR)
        self.returns(REQUESTING)
        self.github.report_failures.lost.discard(_world.PR)
        charged = _one_developer_later(_read.spent(self))
        self.assertEqual(
            (_read.feedback_posts(self), self.github.label_history), ([], []),
        )

        fixed = self._fixed()

        run = fixed[_world.RUN_AGENT].call_args
        self.assertEqual(
            (
                fixed[_world.RUN_AGENT].call_count,
                run.kwargs.get("resume_session_id"),
                _world.REQUESTED in run.args[1],
            ),
            (1, _world.DEV_SESSION, True),
        )
        self.assertEqual(
            (
                len(_read.feedback_posts(self)),
                _read.artifacts(self)[0].commands[0].exit_status,
                tuple(self.github.label_history),
            ),
            (1, 1, HANDED_BACK),
        )
        self.assertEqual(_read.spent(self), charged)

    def test_a_report_settling_mid_post_drops_it(self) -> None:
        posting = _SettlesALaterReportBehind(self, "_post_verification_artifact", lambda _body: True)
        ran = posting.returning(REQUESTING)

        self.assertEqual(
            (
                ran[_world.RUN_AGENT].call_count,
                _read.feedback_posts(self),
                self.pinned()[_world.RETURNED_VERDICT],
                self.github.label_history,
            ),
            (0, [], None, []),
        )

    def test_a_report_before_the_handoff_drops_it(self) -> None:
        # Nothing declared, so nothing is published: the request is held to
        # the subject after its own write and again behind its feedback post,
        # and the later report is kept rather than written back over.
        for name, settles_behind, posts in _BEFORE_THE_HANDOFF:
            with self.subTest(name):
                self.setUp()

                ran = _SettlesALaterReportBehind(self, *settles_behind).returning(UNDECLARED_REQUEST)

                self.assertEqual(
                    (
                        ran[_world.RUN_AGENT].call_count,
                        len(_read.feedback_posts(self)),
                        self.pinned()[_world.RETURNED_VERDICT],
                        self.github.label_history,
                        _read.current_report_revision(self),
                    ),
                    (0, posts, None, [], 2),
                )

    def test_a_refused_feedback_post_holds_it(self) -> None:
        # The post is the one durable copy of the feedback a later park's
        # retry replays, so nothing is relabelled or launched without it; the
        # verdict, never handed, posts again on the next tick.
        with patch.object(self.github, "pr_comment", _RefusesTheFeedback(self.github)):
            held = self.returns(REQUESTING)
        self.assertEqual(
            (self.pinned()[_world.RETURNED_VERDICT]["handed"], self.github.label_history),
            (None, []),
        )

        fixed = self._fixed()

        self.assertEqual(
            (held[_world.RUN_AGENT].call_count, fixed[_world.RUN_AGENT].call_count),
            (0, 1),
        )
        self.assertEqual(
            (
                len(_read.feedback_posts(self)),
                tuple(self.github.label_history),
                self.pinned()[_world.RETURNED_VERDICT],
            ),
            (1, HANDED_BACK, None),
        )

    def test_no_room_parks_the_verdict_unacted(self) -> None:
        for name, message, filled in _NO_ROOM:
            with self.subTest(name):
                self.setUp()
                self._fills(filled)

                ran = self.returns(message)

                pinned = self.pinned()
                self.assertEqual(
                    (
                        pinned[_world.PARK_REASON],
                        pinned.get(_world.RETURNED_VERDICT),
                        pinned.get(_world.PENDING_EVIDENCE),
                        _read.artifacts(self),
                        ran[_world.RUN_AGENT].call_count,
                        _read.feedback_posts(self),
                        self.github.label_history,
                    ),
                    (UNRECORDED, None, None, [], 0, [], []),
                )

    def _fixed(self) -> dict:
        """The next tick, in which one developer answers the request and pushes."""
        return self.dispatched(_developer(), dirty_files=(), push_branch=True, head_shas=FIX_HEAD_SHAS)

    def _fills(self, filled: int) -> None:
        """Put `filled` characters of operator notes on the pinned comment."""
        state = self.github.read_pinned_state(self.issue)
        state.set("operator_notes", "x" * filled)
        self.github.write_pinned_state(self.issue, state)


if __name__ == "__main__":
    unittest.main()
