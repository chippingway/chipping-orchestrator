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

# The member of a waiting verdict's record naming which verdict it is.
VERDICT = "verdict"

LATER_REPORT = "Covered the empty configuration as well; the suite passes."

# What the approval comment an approval posts says about itself, the notice
# its squash of two commits posts, and the park a failed squash takes.
APPROVAL_NOTICE = "review approved"

SQUASH_NOTICE = "squashed 2 commits"

SQUASH_FAILED_NOTICE = "squash-on-approval failed"

# The client requests a pull-request comment, a pinned-comment write, and an
# issue comment go out through.
PR_COMMENT = "pr_comment"

PINNED_WRITE = "write_pinned_state"

ISSUE_COMMENT = "comment"

# The pinned ledger of the comments the orchestrator posted, which every
# prompt keeps an orchestrator comment by.
LEDGER = "orchestrator_comment_ids"

# A reviewer approving over the evidence revision `digest` names, running
# nothing of its own.
REUSING = "Covered.\n\nVERIFICATION: REUSED sha256:{digest}\n\nVERDICT: APPROVED"

# An evidence digest nothing in the world names.
OTHER_DIGEST = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"

# A reviewer asking for that change beside its declared run, which failed,
# and with nothing declared beside it.
REQUESTING = _world.declared_run(exit_status=1, verdict="CHANGES_REQUESTED")

UNDECLARED_REQUEST = f"{_world.REQUESTED}\n\nVERDICT: CHANGES_REQUESTED"

# An approval with nothing declared beside it.
UNDECLARED_APPROVAL = "LGTM\n\nVERDICT: APPROVED"

REVIEW_ROUND = "review_round"

# The event a park that lands reports, once per human wait it opens.
PARK_EVENT = "park_awaiting_human"

# The verdict an approval's waiting record names.
APPROVED = "approved"


def _settles_a_later_report(case) -> None:
    """Another road's settlement of a later report on the same head, spending the round its handover bought."""
    _published_reports.republishes_the_report(case.github, case.issue, LATER_REPORT)
    state = case.github.read_pinned_state(case.issue)
    state.set(REVIEW_ROUND, (state.get(REVIEW_ROUND) or 0) + 1)
    case.github.write_pinned_state(case.issue, state)


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
            PINNED_WRITE,
            lambda state: state.get(_world.RETURNED_VERDICT) is not None,
            _settles_a_later_report,
        ),
        (0, 2, ()),
    ),
    (
        "a report behind the feedback post",
        (PR_COMMENT, lambda body: _read.FEEDBACK_NOTICE in body, _settles_a_later_report),
        (1, 2, ()),
    ),
    (
        "a push behind the feedback post",
        (PR_COMMENT, lambda body: _read.FEEDBACK_NOTICE in body, _world.pushes),
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

# Every park a verdict of a reviewed subject takes -- the two a returned
# verdict takes and the one its approval's failed verify gate takes -- with
# the reply that earns each, the operator notes that leave no room for the
# verdict, a phrase of the notice, the verdict each leaves waiting where no
# park lands over it, and how the tick runs.
_PARKS = (
    (UNVERIFIED, (UNDECLARED_APPROVAL, 0, UNVERIFIED_NOTICE), APPROVED, {}),
    (
        UNRECORDED,
        (f"{_LONG}\n\nVERDICT: CHANGES_REQUESTED", MAX_PINNED_BODY - len(_LONG), "could not be recorded"),
        None,
        {},
    ),
    (
        "verify_failed",
        (_world.declared_run(), 0, "local verification failed"),
        APPROVED,
        {"verify_result": VerifyResult(status="failed")},
    ),
)

# What another road does to a verdict's subject behind one of its requests,
# the report revision and review round the pinned comment records then, and
# whether the verdict is held for a later tick: a later report settling -- and
# spending its round -- evidence settling, or a push proves what the verdict
# was decided over moved, and a report nobody could read proves nothing either
# way.
# Each verdict another road drops right behind the write that persisted it, as
# the reply that verdict's reviewer returned -- an approval whose evidence is
# published before it is acted on, one reusing settled evidence, and a change
# request relying on none -- and the pull-request comments that tick posts:
# the published approval's artifact alone.
_CLEARED = (
    ("a published approval", lambda _case: _world.declared_run(), 1),
    ("a reused approval", lambda case: REUSING.format(digest=_read.settles_evidence(case).content_revision), 0),
    ("a change request", lambda _case: UNDECLARED_REQUEST, 0),
)

# Where another road puts a verdict of its own -- a later round's change
# request, beside the round it spent -- in place of the one this tick is
# acting on: the reply that earned this tick's verdict, the request behind
# which the other lands with how many of those requests go first, how the
# tick runs, and how many squashes it takes. Behind the squash notice and
# behind the write that settles the squash, the approval is finishing a
# rewrite already made; behind a failed squash's park notice, it is parking
# one that never went.
_REPLACED = (
    (
        "behind the approval comment",
        lambda case: REUSING.format(digest=_read.settles_evidence(case).content_revision),
        (PR_COMMENT, lambda body: APPROVAL_NOTICE in body, 1),
        {},
        0,
    ),
    (
        "behind the feedback post",
        lambda _case: UNDECLARED_REQUEST,
        (PR_COMMENT, lambda body: _read.FEEDBACK_NOTICE in body, 1),
        {},
        0,
    ),
    (
        "behind the park notice",
        lambda _case: UNDECLARED_APPROVAL,
        (ISSUE_COMMENT, lambda body: UNVERIFIED_NOTICE in body, 1),
        {},
        0,
    ),
    (
        # The fourth artifact reread, behind the two the round's handover
        # took and the proof's own, is the approval's last before the comment
        # is read again for it.
        "behind the approval's proof",
        lambda case: REUSING.format(digest=_read.settles_evidence(case).content_revision),
        ("reread_verification_artifact", bool, 4),
        {},
        0,
    ),
    (
        "behind the squash notice",
        lambda case: REUSING.format(digest=_read.settles_evidence(case).content_revision),
        (PR_COMMENT, lambda body: SQUASH_NOTICE in body, 1),
        {"squash_result": (True, _world.HEAD, 2, None)},
        1,
    ),
    (
        "behind the squash failure's notice",
        lambda case: REUSING.format(digest=_read.settles_evidence(case).content_revision),
        (ISSUE_COMMENT, lambda body: SQUASH_FAILED_NOTICE in body, 1),
        {"squash_result": (False, None, 0, "force-push rejected")},
        1,
    ),
    (
        "behind the squash's own write",
        lambda case: REUSING.format(digest=_read.settles_evidence(case).content_revision),
        (PINNED_WRITE, lambda state: state.get("review_approved_subject") is not None, 1),
        {},
        1,
    ),
)

# What every orchestrator post a verdict's tick can make says: the approval
# comment, the squash notice, the feedback, and the two park notices.
_POSTED = (APPROVAL_NOTICE, SQUASH_NOTICE, _read.FEEDBACK_NOTICE, UNVERIFIED_NOTICE, SQUASH_FAILED_NOTICE)

_MOVES = (
    ("a later report", _settles_a_later_report, (2, 1), False),
    ("an evidence settlement", _read.settles_evidence, (1, 0), False),
    ("a push", _world.pushes, (1, 0), False),
    (
        "an unread report",
        lambda case: case.github.report_failures.unreadable.add(_world.PR),
        (1, 0),
        True,
    ),
)

# Each park with each move behind its notice, and what it leaves: whether it
# parked, the verdict waiting, whether the notice was posted, the report
# revision and round, every relabel, and every park reported. No park lands
# over a subject that is not proved to stand, and none is reported.
_BEHIND_THE_NOTICE = tuple(
    (
        park,
        move,
        (*reply, road),
        options,
        ((None, False), waiting if holds else None, True, recorded, ([], [])),
    )
    for park, reply, waiting, options in _PARKS
    for move, road, recorded, holds in _MOVES
)

# An approval whose verify gate fails with each move landing during it, and
# what it leaves: the park it takes, the verdict waiting, the report revision
# and round, and every park reported. Only a subject still standing behind the
# gate parks.
_UNDER_A_FAILED_GATE = (
    ("nothing", None, ("verify_failed", None, (1, 0), ["verify_failed"])),
    *(
        (move, road, (None, APPROVED if holds else None, recorded, []))
        for move, road, recorded, holds in _MOVES
    ),
)


class _RefusesOnce:
    """A post that fails once where it says `phrase`, and goes through every other time.

    Refused outright, or -- where it `lands` -- taken with an answer that
    names no comment, so nothing reads its id back. `posts` is the client's
    own request, a pull-request or an issue comment.
    """

    def __init__(self, posts, phrase: str, *, lands: bool = False) -> None:
        self._posts = posts
        self._phrase = phrase
        self._lands = lands
        self._failed = False

    def __call__(self, thread, body):
        if self._failed or self._phrase not in body:
            return self._posts(thread, body)
        self._failed = True
        if not self._lands:
            raise RuntimeError("comment rejected")
        self._posts(thread, body)
        return None


class DisposedApprovalTest(_world.ReviewVerdictWorld, unittest.TestCase):
    """An approval acts only over settled, passing evidence covering the configuration."""

    def test_the_verdict_is_written_before_publishing(self) -> None:
        # What the pinned comment carries as the artifact is posted, which the
        # post itself leaves untouched.
        seen: list[dict] = []
        posting = _world.AnotherRoadBehind(
            self, "_post_verification_artifact", bool, lambda case: seen.append(case.pinned()),
        )

        posting.returning(_world.declared_run())

        claim = seen[0][_world.RETURNED_VERDICT]["evidence"]
        self.assertEqual(
            (
                claim["use"],
                claim["passed"] and claim["covers"],
                seen[0][_world.PENDING_EVIDENCE]["receipt"],
            ),
            ("published", True, claim["receipt"]),
        )
        self.assertEqual(
            (
                self.github.label_history,
                self.pinned()[_world.RETURNED_VERDICT],
                len(_read.artifacts(self)),
            ),
            ([DOCUMENTING], None, 1),
        )

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
                _read.seeds_a_verdict(self, _read.settles_evidence(self, **settled))

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

    def test_a_superseded_reuse_drops_either_verdict(self) -> None:
        # The evidence a waiting verdict's reuse named is superseded by a later
        # revision before the verdict is finished: the reviewer judged the
        # branch beside evidence the pull request no longer carries as
        # current, so the verdict is dropped for a fresh reviewer handed the
        # later one -- an approval is not parked for a human, and a change
        # request posts no feedback and launches no developer: nothing is
        # spent or posted.
        for verdict in (APPROVED, "changes_requested"):
            with self.subTest(verdict):
                self.setUp()
                _read.seeds_a_verdict(self, _read.settles_evidence(self), verdict, reused=True)
                _read.settles_evidence(self)
                before = (
                    _read.spent(self),
                    len(self.github.posted_pr_comments),
                    len(self.github.posted_comments),
                )

                self.finishes(_world.developer())

                pinned = self.pinned()
                self.assertEqual(
                    (
                        (
                            _read.spent(self),
                            len(self.github.posted_pr_comments),
                            len(self.github.posted_comments),
                        ),
                        pinned.get(_world.RETURNED_VERDICT),
                        pinned.get(_world.PARK_REASON),
                        self.github.label_history,
                    ),
                    (before, None, None, []),
                )

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
                waiting[_world.RETURNED_VERDICT][VERDICT],
                waiting[_world.PENDING_EVIDENCE] is None,
                self.github.label_history,
            ),
            (APPROVED, False, []),
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
            self, PINNED_WRITE, lambda state: state.get(_world.RETURNED_VERDICT) is not None,
            lambda case: case.github.report_failures.unreadable.add(_world.PR),
        )
        posted = list(self.github.posted_pr_comments)

        ran = behind.returning(UNDECLARED_REQUEST)

        waiting = self.pinned()[_world.RETURNED_VERDICT]
        self.assertEqual(
            (
                (waiting[VERDICT], waiting["handed"]),
                ran[_world.RUN_AGENT].call_count,
                self.github.posted_pr_comments,
                self.github.label_history,
            ),
            (("changes_requested", None), 0, posted, []),
        )

    def test_a_feedback_post_with_no_id_holds_it(self) -> None:
        # The post's id is the one durable copy of the feedback a later park's
        # retry replays, so nothing is relabelled or launched without it --
        # whether GitHub refused the post, or took it with an answer naming no
        # comment to read an id from. The verdict, never handed, posts again
        # on the next tick, and reaches one developer: twice over on the pull
        # request where the first post landed, since a feedback post carries
        # no receipt to find it by.
        for name, lands, posts in (("refused", False, 1), ("landed with no id", True, 2)):
            with self.subTest(name):
                self.setUp()
                with patch.object(
                    self.github, PR_COMMENT, _RefusesOnce(self.github.pr_comment, _read.FEEDBACK_NOTICE, lands=lands),
                ):
                    held = self.returns(REQUESTING)
                self.assertEqual(
                    (
                        held[_world.RUN_AGENT].call_count,
                        self.pinned()[_world.RETURNED_VERDICT]["handed"],
                        self.pinned().get(ANCHOR),
                        self.github.label_history,
                    ),
                    (0, None, None, []),
                )

                fixed = self._fixed()

                self.assertEqual(
                    (
                        fixed[_world.RUN_AGENT].call_count,
                        len(_read.feedback_posts(self)),
                        tuple(self.github.label_history),
                        self.pinned()[_world.RETURNED_VERDICT],
                    ),
                    (1, posts, HANDED_BACK, None),
                )

    def _fixed(self) -> dict:
        """The next tick, in which one developer answers the request and pushes."""
        return self.finishes(_world.developer(), dirty_files=(), push_branch=True, head_shas=FIX_HEAD_SHAS)


class ParkedVerdictTest(_world.ReviewVerdictWorld, unittest.TestCase):
    """A verdict that may not be acted on parks for a human, and only over the subject it is about."""

    def test_an_approval_without_valid_evidence_parks(self) -> None:
        for name, message, refusal in _UNVERIFIED_APPROVALS:
            with self.subTest(name):
                self.setUp()

                ran = self.returns(message)

                pinned = self.pinned()
                self.assertEqual(
                    (
                        pinned[_world.PARK_REASON],
                        pinned[_world.RETURNED_VERDICT],
                        ran[VERIFY].call_count,
                        [event.get("reason") for event in self.github.recorded_events if event["event"] == PARK_EVENT],
                    ),
                    (UNVERIFIED, None, 0, [UNVERIFIED]),
                )
                self.assertEqual(self.github.label_history, [])
                self.assertIn(refusal, self.github.posted_comments[-1][1])

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

    def test_a_notice_parks_only_a_standing_subject(self) -> None:
        # The notice is the park's last request: a later report settling, or
        # a push, while it is posted is a subject nobody reviewed, so no park
        # lands to ask a human about it. The verdict is dropped for a fresh
        # reviewer, and a later report is kept rather than written back over.
        # A report nobody could read then is no proof either way: no park
        # lands, and the verdict an approval persisted waits for a later tick.
        for park, move, case, options, expected in _BEHIND_THE_NOTICE:
            with self.subTest(park=park, move=move):
                self.assertEqual(self._moved_behind_the_notice(*case, **options), expected)

    def test_a_park_measures_the_verdict_it_may_keep(self) -> None:
        # A report nobody could read behind the notice lands no park and keeps
        # the verdict waiting beside the notice's ledger entry, the wider of
        # the two writes a park may end in. Measured from that write with
        # nothing filled, a comment with one character too few for it is not
        # posted on, and never written past its ceiling.
        unread = _MOVES[-1][1]
        self._moved_behind_the_notice(UNDECLARED_APPROVAL, 0, UNVERIFIED_NOTICE, unread)
        kept = len(pinned_state_body(self.pinned()))

        filled = MAX_PINNED_BODY - kept + 1

        left = self._moved_behind_the_notice(UNDECLARED_APPROVAL, filled, UNVERIFIED_NOTICE, unread)

        written = len(pinned_state_body(self.pinned()))
        self.assertEqual(
            (left[1], left[2], written <= MAX_PINNED_BODY),
            (APPROVED, False, True),
        )

    def _moved_behind_the_notice(self, message: str, filled: int, notice: str, road, **options) -> tuple:
        """What the park `message` earns over `filled` notes leaves where `road` moves its subject behind `notice`.

        Whether it parked, the verdict it left, whether the notice was posted,
        the current report revision and round, and every relabel beside every
        park reported.
        """
        self.setUp()
        self._fills(filled)
        behind = _world.AnotherRoadBehind(self, ISSUE_COMMENT, lambda body: notice in body, road)
        behind.returning(message, **options)
        pinned = self.pinned()
        return (
            (pinned.get(_world.PARK_REASON), bool(pinned.get("awaiting_human"))),
            (pinned.get(_world.RETURNED_VERDICT) or {}).get(VERDICT),
            any(notice in body for _, body in self.github.posted_comments),
            (_read.current_report_revision(self), pinned.get(REVIEW_ROUND)),
            (
                self.github.label_history,
                [event.get("reason") for event in self.github.recorded_events if event["event"] == PARK_EVENT],
            ),
        )

    def _fills(self, filled: int) -> None:
        """Put `filled` characters of operator notes on the pinned comment."""
        state = self.github.read_pinned_state(self.issue)
        state.set("operator_notes", "x" * filled)
        self.github.write_pinned_state(self.issue, state)


class EvidenceRaceTest(_world.ReviewVerdictWorld, unittest.TestCase):
    """An approval never writes back records a later settlement replaced, nor acts over a subject that moved."""

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
                        verify_result=partial(self._gate, road=_read.settles_evidence if during else None),
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

    def test_a_failed_gate_parks_a_standing_subject(self) -> None:
        # The verify gate is long enough for a push or a later report, and a
        # failure over a subject nobody reviewed is no failure of the
        # approval: it is dropped for a fresh reviewer rather than parked for
        # a human, and a later report's round is kept. A report nobody could
        # read behind the gate proves nothing either way, so nothing parks and
        # the verdict waits. Only the park that lands is reported.
        for move, road, expected in _UNDER_A_FAILED_GATE:
            with self.subTest(move):
                self.setUp()
                digest = _read.settles_evidence(self).content_revision

                self.returns(
                    f"Covered.\n\nVERIFICATION: REUSED sha256:{digest}\n\nVERDICT: APPROVED",
                    verify_result=partial(self._gate, road=road, status="failed"),
                )

                pinned = self.pinned()
                self.assertEqual(
                    (
                        pinned.get(_world.PARK_REASON),
                        (pinned.get(_world.RETURNED_VERDICT) or {}).get(VERDICT),
                        (_read.current_report_revision(self), pinned.get(REVIEW_ROUND)),
                        [event.get("reason") for event in self.github.recorded_events if event["event"] == PARK_EVENT],
                        self.github.label_history,
                    ),
                    (*expected, []),
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
        # so it is not acted on, nor parked for a human -- a fresh reviewer
        # handed the newer evidence answers it -- and the newer records are
        # kept rather than written back over.
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
                pinned[_world.RETURNED_VERDICT],
            ),
            ([], 2, 2, None, None),
        )

    def _gate(self, *_args, road=None, status: str = "ok", **_kw) -> VerifyResult:
        """A verify gate answering `status`, during which `road` does another road's work, or behind which one may."""
        if road is None:
            self._verified = True
        else:
            road(self)
        return VerifyResult(status=status)

    def _after_the_gate(self, _location) -> bool:
        """Whether a reread is one behind a verify gate `_gate` answered with nobody else's work."""
        return self._verified


class RecordRaceTest(_world.ReviewVerdictWorld, unittest.TestCase):
    """A verdict is acted on only while the comment carries it and the records it was proved over.

    And one another road put in its place is never dropped by this one.
    """

    def test_a_settlement_behind_the_approval_comment(self) -> None:
        # Evidence settles while the approval comment is posted, a request long
        # enough for another road: no rewrite goes out over it and nothing the
        # approval holds is written, so the newer records stand -- only the
        # approval comment is recorded as the orchestrator's. The verdict left
        # waiting names evidence the later revision superseded, and the next
        # tick drops it for a fresh reviewer rather than moving the issue on.
        digest = _read.settles_evidence(self).content_revision
        behind = _world.AnotherRoadBehind(
            self, PR_COMMENT, lambda body: APPROVAL_NOTICE in body, _read.settles_evidence,
        )

        ran = behind.returning(REUSING.format(digest=digest))

        approval = next(
            said.id for said in self.pull_request.issue_comments if APPROVAL_NOTICE in said.body
        )
        self.assertEqual(
            (
                ran["_squash_and_force_push"].call_count,
                _read.current_evidence_revision(self),
                self.pinned().get(_world.RETURNED_VERDICT, {}).get(VERDICT),
                self.pinned().get("review_approved_subject"),
                approval in self.pinned()[LEDGER],
                self.github.label_history,
            ),
            (0, 2, APPROVED, None, True, []),
        )

        self.finishes()

        after = self.pinned()
        self.assertEqual(
            (after.get(_world.RETURNED_VERDICT), after.get(_world.PARK_REASON), self.github.label_history),
            (None, None, []),
        )

    def test_a_cleared_verdict_is_not_acted_on(self) -> None:
        # Another road drops the verdict right behind the write that persisted
        # it -- a reply that bought a fresh round, say. Whichever the verdict,
        # and whether or not its evidence is published first, nothing is
        # verified, approved, parked, handed over, or relabelled over a verdict
        # the comment no longer carries.
        for name, reply, posts in _CLEARED:
            with self.subTest(name):
                self.assertEqual(self._cleared_behind_its_write(reply), (0, None, None, posts, []))

    def test_a_replaced_verdict_is_left_standing(self) -> None:
        # Another road puts a verdict of its own in place of the one this tick
        # persisted and is acting on, and spends a round beside it: whichever
        # request it lands behind, this tick squashes no further, relabels,
        # parks -- or reports a park -- and hands over nothing, and drops
        # nothing but its own verdict: the other verdict and its round stand
        # for that road to finish, and no write this tick makes after them
        # lays itself over them. What it posted on the way is still recorded
        # as the orchestrator's.
        for name, reply, behind, options, squashed in _REPLACED:
            with self.subTest(name):
                self.assertEqual(
                    self._replaced_behind(reply, behind, **options),
                    (squashed, (True, 1), (None, []), [], True),
                )

    def _cleared_behind_its_write(self, reply) -> tuple:
        """What returning `reply` leaves where another road clears the verdict behind the write persisting it.

        The verify gate's runs, the verdict and park the comment carries, the
        pull-request comments the tick posted, and every relabel.
        """
        self.setUp()
        message = reply(self)
        posted = len(self.github.posted_pr_comments)
        behind = _world.AnotherRoadBehind(
            self, PINNED_WRITE, lambda state: state.get(_world.RETURNED_VERDICT) is not None, self._clears,
        )
        ran = behind.returning(message)
        left = self.pinned()
        return (
            ran[VERIFY].call_count,
            left.get(_world.RETURNED_VERDICT),
            left.get(_world.PARK_REASON),
            len(self.github.posted_pr_comments) - posted,
            self.github.label_history,
        )

    def _replaced_behind(self, reply, behind: tuple, **options) -> tuple:
        """What returning `reply` leaves where another road puts its own verdict in place behind `behind`'s request.

        The squashes taken, whether that road's verdict stands beside the
        review round, the park beside every park reported, every relabel, and
        whether the pinned ledger records every approval, squash, feedback,
        and park notice the tick posted.
        """
        self.setUp()
        ran = _world.AnotherRoadBehind(
            self, behind[0], behind[1], self._replaces, behind[2],
        ).returning(reply(self), **options)
        standing = self.pinned()
        posted = {
            said.id
            for said in (*self.issue.comments, *self.pull_request.issue_comments)
            if any(phrase in said.body for phrase in _POSTED)
        }
        reported = [event for event in self.github.recorded_events if PARK_EVENT in event.values()]
        return (
            ran["_squash_and_force_push"].call_count,
            (standing.get(_world.RETURNED_VERDICT) == self.replacement, standing.get(REVIEW_ROUND)),
            (standing.get(_world.PARK_REASON), reported),
            self.github.label_history,
            posted <= set(standing[LEDGER]),
        )

    def _replaces(self, _case) -> None:
        """Another road's write putting a later round's change request in place of the verdict, spending a round."""
        state = self.github.read_pinned_state(self.issue)
        self.replacement = {
            "round": 1,
            "verdict": "changes_requested",
            "subject": state.get("review_subject"),
            "feedback": "A later round's feedback.",
            "evidence": None,
            "handed": None,
        }
        state.set(_world.RETURNED_VERDICT, self.replacement)
        state.set(REVIEW_ROUND, 1)
        self.github.write_pinned_state(self.issue, state)

    def _clears(self, _case) -> None:
        """Another road's write dropping the verdict the comment carries."""
        state = self.github.read_pinned_state(self.issue)
        state.set(_world.RETURNED_VERDICT, None)
        self.github.write_pinned_state(self.issue, state)


if __name__ == "__main__":
    unittest.main()
