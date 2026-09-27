# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A returned reviewer's verdict, persisted before anything is done with it.

The verdict and the transaction its declared commands are minted as go down in
one write before the evidence is published, and neither verdict is acted on
until that evidence settles: an approval reaches the approval arc only over
settled, passing evidence that covers the configured verification, and parks
otherwise. A verdict the comment has no room for parks with nothing acted on,
one whose subject moves is dropped, and one whose evidence can never settle is
dropped too. A tick that stops short leaves the verdict for the service's own
entry behind the persisted write to finish, with no second reviewer, no second
fold of its usage, and no round spent -- and a change request reaches exactly
one developer, only once its feedback is posted.
"""
from __future__ import annotations

import operator
import unittest
from functools import partial
from unittest.mock import patch

from orchestrator import config as _config
from orchestrator.git.verification.models import VerifyResult
from orchestrator.github.pinned_state import MAX_PINNED_BODY, pinned_state_body
from tests.workflow import published_reports as _published_reports
from tests.workflow.fixtures import LABEL_DOCUMENTING, LABEL_FIXING, LABEL_VALIDATING
from tests.workflow.stages.validating import review_verdict_readings as _read, review_verdict_test_support as _world
from tests.workflow.stages.validating.validating_review_test_support import FIX_HEAD_SHAS

VERIFY = "_run_verify_commands"

REREAD = "reread_report_location"

UNVERIFIED = "reviewer_unverified"

UNRECORDED = "reviewer_unrecorded"

UNVERIFIED_NOTICE = "approved without the verification evidence"

DOCUMENTING = (_world.ISSUE, LABEL_DOCUMENTING)

FIXING = (_world.ISSUE, LABEL_FIXING)

HANDED_BACK = (FIXING, (_world.ISSUE, LABEL_VALIDATING))

ANCHOR = "pending_fix_reviewer_comment_id"

LATER_REPORT = "Covered the empty configuration as well; the suite passes."

# An evidence digest nothing in the world names.
OTHER_DIGEST = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"

# A reviewer asking for that change beside its declared run, which failed,
# and with nothing declared beside it.
REQUESTING = _world.declared_run(exit_status=1, verdict="CHANGES_REQUESTED")

UNDECLARED_REQUEST = f"{_world.REQUESTED}\n\nVERDICT: CHANGES_REQUESTED"

# An approval with nothing declared beside it.
UNDECLARED_APPROVAL = "LGTM\n\nVERDICT: APPROVED"



def _settles_a_later_report(case) -> None:
    """Another road's settlement of a later report on the same head."""
    _published_reports.republishes_the_report(case.github, case.issue, LATER_REPORT)


# The requests between a change request's verdict and its handoff behind which
# another road moves its subject, how many feedback posts that leaves, and the
# report revision the pinned comment records then.
_BEFORE_THE_HANDOFF = (
    (
        # The second reread of the settled report is the disposition's own
        # subject check, behind the one the round resolved its subject with.
        "a report behind the subject check",
        (REREAD, lambda _location: True, _settles_a_later_report, 2),
        (0, 2, ()),
    ),
    (
        "a report behind the verdict's write",
        (
            "write_pinned_state",
            lambda state: state.get(_world.RETURNED_VERDICT) is not None,
            _settles_a_later_report,
        ),
        (0, 2, ()),
    ),
    (
        "a report behind the feedback post",
        ("pr_comment", lambda body: _read.FEEDBACK_NOTICE in body, _settles_a_later_report),
        (1, 2, ()),
    ),
    (
        "a push behind the feedback post",
        ("pr_comment", lambda body: _read.FEEDBACK_NOTICE in body, _world.pushes),
        (1, 1, ()),
    ),
    (
        "a report behind the relabel",
        ("set_workflow_label", lambda label: label == LABEL_FIXING, _settles_a_later_report),
        (1, 2, (FIXING,)),
    ),
)

# Approvals that rely on no evidence an approval may rest on, and the words
# the park names each for.
_UNVERIFIED_APPROVALS = (
    ("nothing declared", UNDECLARED_APPROVAL, "declared no verification"),
    ("a failed run", _world.declared_run(exit_status=1), "did not exit 0"),
    ("another command", _world.declared_run(command="uv run ruff check"), "every command `VERIFY_COMMANDS`"),
    ("another head", _world.declared_run().replace(_world.HEAD, _world.OTHER_HEAD), "names another commit"),
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

# What one developer answering a change request adds to what the issue spent:
# its run charged and folded, and the one round its pushed fix spends -- the
# reviewer's tokens are not folded again.
_ONE_DEVELOPER = (1, 1, 0, 1)

# A change request's feedback longer than most of what the pinned comment
# holds, and a failed run's output the transaction quotes again: the filler
# leaves room for the round's own records and not for the verdict, or for the
# verdict and not its transaction.
_LONG = "12 passed, 1 failed " * 1000

# What a comment a park cannot fit on has left: a few characters, fewer than
# the park's own flags take.
_SPARE = 8

_NO_ROOM = (
    ("for the verdict", f"{_LONG}\n\nVERDICT: CHANGES_REQUESTED", MAX_PINNED_BODY - len(_LONG)),
    (
        "for its evidence",
        _world.declared_run(exit_status=1, verdict="CHANGES_REQUESTED", output=_LONG),
        MAX_PINNED_BODY - len(_LONG) * 3 // 2,
    ),
)

# The two parks a returned verdict takes -- the reply that earns each, the
# operator notes that leave no room for the verdict, and a phrase of the
# notice -- and what moves the subject behind that notice, with the report
# revision the pinned comment records then.
_PARKS = (
    (UNVERIFIED, (UNDECLARED_APPROVAL, 0, UNVERIFIED_NOTICE)),
    (UNRECORDED, (f"{_LONG}\n\nVERDICT: CHANGES_REQUESTED", MAX_PINNED_BODY - len(_LONG), "could not be recorded")),
)

_MOVES = (
    ("a later report", _settles_a_later_report, 2),
    ("a push", _world.pushes, 1),
)


class _ReadsTheCommentAtThePost:
    """Artifact posts that record what the pinned comment carried as each was made."""

    def __init__(self, case) -> None:
        self._case = case
        self._post = case.github._post_verification_artifact
        self.seen: list[dict] = []

    def __call__(self, pull_request, body):
        self.seen.append(self._case.pinned())
        return self._post(pull_request, body)


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

                ran = self.finishes()

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

        finished = self.finishes()

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

    def test_an_unsettleable_transaction_drops_it(self) -> None:
        # The approval waits on its publication, and the verification context
        # its transaction was bound under moves: that evidence can never settle,
        # so the verdict is dropped for a fresh reviewer rather than waiting on
        # it forever, and is neither acted on nor parked for a human. A later
        # report another road settles once the tick has read the comment is
        # kept rather than written back over by that drop.
        for name, meanwhile, revision in (("alone", None, 1), ("beside a later report", _settles_a_later_report, 2)):
            with self.subTest(name):
                self.setUp()
                self._held(_world.declared_run())

                with patch.object(_config, "VERIFY_TIMEOUT", _config.VERIFY_TIMEOUT + 1):
                    ran = self.finishes(meanwhile=meanwhile)

                pinned = self.pinned()
                self.assertEqual(
                    (
                        ran[_world.RUN_AGENT].call_count,
                        ran[VERIFY].call_count,
                        pinned[_world.RETURNED_VERDICT],
                        pinned.get(_world.PARK_REASON),
                        _read.current_report_revision(self),
                        self.github.label_history,
                    ),
                    (0, 0, None, None, revision, []),
                )

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
        charged = tuple(map(operator.add, _read.spent(self), _ONE_DEVELOPER))
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
        posting = _world.AnotherRoadBehind(
            self, "_post_verification_artifact", lambda _body: True, _settles_a_later_report,
        )
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

    def test_a_move_before_the_handoff_drops_it(self) -> None:
        # Nothing declared, so nothing is published: the request is held to
        # what the comment carries before its own write, to the subject after
        # it, behind its feedback post, and behind the relabel ahead of the
        # launch. No developer is launched, a later report is kept rather than
        # written back over, and no anchor is left for a retry to replay.
        for name, behind, expected in _BEFORE_THE_HANDOFF:
            with self.subTest(name):
                self.setUp()

                ran = _world.AnotherRoadBehind(self, *behind).returning(UNDECLARED_REQUEST)

                pinned = self.pinned()
                self.assertEqual(
                    (
                        ran[_world.RUN_AGENT].call_count,
                        pinned.get(_world.RETURNED_VERDICT),
                        pinned.get(ANCHOR),
                    ),
                    (0, None, None),
                )
                self.assertEqual(
                    (
                        len(_read.feedback_posts(self)),
                        _read.current_report_revision(self),
                        tuple(self.github.label_history),
                    ),
                    expected,
                )

    def test_an_unread_subject_holds_it(self) -> None:
        # The pull request stops answering behind the verdict's write: that is
        # no proof the subject moved, so the verdict waits, unhanded, for a
        # later tick to resolve again rather than being dropped as stale.
        behind = _world.AnotherRoadBehind(
            self, "write_pinned_state", lambda state: state.get(_world.RETURNED_VERDICT) is not None,
            lambda case: case.github.report_failures.unreadable.add(_world.PR),
        )
        posted = list(self.github.posted_pr_comments)

        ran = behind.returning(UNDECLARED_REQUEST)

        waiting = self.pinned()[_world.RETURNED_VERDICT]
        self.assertEqual(
            (
                (waiting["verdict"], waiting["handed"]),
                ran[_world.RUN_AGENT].call_count,
                self.github.posted_pr_comments,
                self.github.label_history,
            ),
            (("changes_requested", None), 0, posted, []),
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

    def _fixed(self) -> dict:
        """The next tick, in which one developer answers the request and pushes."""
        return self.finishes(_world.developer(), dirty_files=(), push_branch=True, head_shas=FIX_HEAD_SHAS)


class ParkedVerdictTest(_world.ReviewVerdictWorld, unittest.TestCase):
    """A verdict that may not be acted on parks for a human, and only over the subject it is about."""

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

    def test_no_room_even_for_the_park_writes_nothing(self) -> None:
        # A comment GitHub accepts, a few characters short of its ceiling, has
        # room for no park either: a notice posted over a write GitHub then
        # refuses would leave neither a verdict nor a park durable, so nothing
        # is posted or written at all.
        self._fills(0)
        spare = MAX_PINNED_BODY - len(pinned_state_body(self.pinned()))
        self._fills(spare - _SPARE)
        before = (self.pinned(), len(self.github.posted_comments))
        self.assertEqual(len(pinned_state_body(before[0])), MAX_PINNED_BODY - _SPARE)

        ran = self.returns(UNDECLARED_REQUEST)

        self.assertEqual(
            (
                (self.pinned(), len(self.github.posted_comments)),
                ran[_world.RUN_AGENT].call_count,
                _read.feedback_posts(self),
                self.github.label_history,
            ),
            (before, 0, [], []),
        )

    def test_a_move_behind_the_park_notice_drops_it(self) -> None:
        # The notice is the park's last request: a later report settling, or
        # a push, while it is posted is a subject nobody reviewed, so no park
        # lands to ask a human about it. The verdict is dropped for a fresh
        # reviewer, and a later report is kept rather than written back over.
        for park, reply in _PARKS:
            for move, road, revision in _MOVES:
                with self.subTest(park=park, move=move):
                    self.assertEqual(
                        self._moved_behind_the_notice(*reply, road),
                        ((None, False), None, True, revision, []),
                    )

    def _moved_behind_the_notice(self, message: str, filled: int, notice: str, road) -> tuple:
        """What the park `message` earns over `filled` notes leaves where `road` moves its subject behind `notice`.

        Whether it parked, the verdict it left, whether the notice was posted,
        the current report revision, and every relabel.
        """
        self.setUp()
        self._fills(filled)
        behind = _world.AnotherRoadBehind(self, "comment", lambda body: notice in body, road)
        behind.returning(message)
        pinned = self.pinned()
        return (
            (pinned.get(_world.PARK_REASON), bool(pinned.get("awaiting_human"))),
            pinned.get(_world.RETURNED_VERDICT),
            any(notice in body for _, body in self.github.posted_comments),
            _read.current_report_revision(self),
            self.github.label_history,
        )

    def _fills(self, filled: int) -> None:
        """Put `filled` characters of operator notes on the pinned comment."""
        state = self.github.read_pinned_state(self.issue)
        state.set("operator_notes", "x" * filled)
        self.github.write_pinned_state(self.issue, state)


class EvidenceRaceTest(_world.ReviewVerdictWorld, unittest.TestCase):
    """An approval never writes back evidence records a later settlement replaced."""

    def test_a_settlement_behind_the_verify_gate(self) -> None:
        # A second transaction settles while the approval's verify gate runs,
        # or behind the subject it resolves once the gate passes -- its
        # report's reread, the last read before the approval writes: the
        # approval is of evidence no longer current, so the issue does not
        # move on, and the newer records are kept rather than written back.
        for name, during in (("during the gate", True), ("behind its subject", False)):
            with self.subTest(name):
                self.setUp()
                self._verified = False
                digest = _read.settles_evidence(self).content_revision
                behind = _world.AnotherRoadBehind(
                    self, REREAD, self._after_the_gate, _read.settles_evidence,
                )

                with patch.object(self.github, REREAD, behind):
                    self.returns(
                        f"Covered.\n\nVERIFICATION: REUSED sha256:{digest}\n\nVERDICT: APPROVED",
                        verify_result=partial(self._passes, settles=during),
                    )

                pinned = self.pinned()
                self.assertEqual(
                    (
                        self.github.label_history,
                        _read.current_evidence_revision(self),
                        pinned["verification_evidence_revision"],
                        pinned[_world.RETURNED_VERDICT],
                    ),
                    ([], 2, 2, None),
                )

    def test_a_report_settling_during_minting(self) -> None:
        # Reading the reviewed tree its declared commands are minted over is a
        # request of its own: a later report settling during it is a subject
        # nobody reviewed, so nothing is persisted, published, or acted on,
        # whichever the verdict, and the later report is kept rather than
        # written back over.
        for message in (_world.declared_run(), REQUESTING):
            with self.subTest(message=message.splitlines()[-1]):
                self.setUp()

                _world.AnotherRoadBehind(self, "_tree_sha", bool, _settles_a_later_report).returning(message)

                pinned = self.pinned()
                self.assertEqual(
                    (
                        pinned.get(_world.RETURNED_VERDICT),
                        pinned.get(_world.PENDING_EVIDENCE),
                        _read.artifacts(self),
                        _read.current_report_revision(self),
                        self.github.label_history,
                    ),
                    (None, None, [], 2, []),
                )

    def test_a_settlement_behind_a_park_notice(self) -> None:
        # Evidence settles while the refused approval's park notice is posted,
        # the park's last request: the park lands and keeps the settlement.
        behind = _world.AnotherRoadBehind(
            self, "comment", lambda body: UNVERIFIED_NOTICE in body, _read.settles_evidence,
        )

        behind.returning(UNDECLARED_APPROVAL)

        pinned = self.pinned()
        self.assertEqual(
            (
                pinned[_world.PARK_REASON],
                _read.current_evidence_revision(self),
                pinned[_world.RETURNED_VERDICT],
            ),
            (UNVERIFIED, 1, None),
        )

    def test_a_settlement_behind_a_refusals_recheck(self) -> None:
        # An approval declaring nothing is refused, and evidence settles while
        # its subject is resolved once more before the park -- the third
        # reread of the report, behind the round's and the verdict's write's:
        # the settlement is carried rather than written away.
        behind = _world.AnotherRoadBehind(
            self, REREAD, lambda _location: True, _read.settles_evidence, 3,
        )

        behind.returning(UNDECLARED_APPROVAL)

        pinned = self.pinned()
        self.assertEqual(
            (
                self.github.label_history,
                _read.current_evidence_revision(self),
                pinned[_world.RETURNED_VERDICT],
                pinned.get(_world.PARK_REASON),
            ),
            ([], 1, None, None),
        )

    def test_a_later_settlement_stops_the_approval(self) -> None:
        # A second transaction settles behind the approval's last read of its
        # artifact -- the fourth, behind the two the round's handover took and
        # the proof's own: the approval rests on evidence no longer current,
        # so it is not acted on, and the newer records are kept rather than
        # written back over.
        digest = _read.settles_evidence(self).content_revision
        behind = _world.AnotherRoadBehind(
            self, "reread_verification_artifact", lambda _comment: True, _read.settles_evidence, 4,
        )

        behind.returning(f"Covered.\n\nVERIFICATION: REUSED sha256:{digest}\n\nVERDICT: APPROVED")

        pinned = self.pinned()
        self.assertEqual(
            (
                self.github.label_history,
                _read.current_evidence_revision(self),
                pinned["verification_evidence_revision"],
                pinned.get(_world.PARK_REASON),
            ),
            ([], 2, 2, UNVERIFIED),
        )

    def _passes(self, *_args, settles: bool = False, **_kw) -> VerifyResult:
        """A verify gate that passes, during which another road settles newer evidence, or behind which it may."""
        if settles:
            _read.settles_evidence(self)
        else:
            self._verified = True
        return VerifyResult(status="ok")

    def _after_the_gate(self, _location) -> bool:
        """Whether a reread is one behind a verify gate `_passes` answered without settling anything."""
        return self._verified


if __name__ == "__main__":
    unittest.main()
