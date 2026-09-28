# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A returned reviewer's verdict, persisted and its evidence reconciled before anything acts on it.

The verdict and the transaction its declared commands are minted as go down in
one write before the evidence is published, and the verdict is ready to be
acted on only once that evidence has settled, or where it relies on none. A
comment with no room for either, or a write GitHub refuses, publishes nothing.
Evidence still owed holds the verdict while its subject stands, for a later
tick to finish with no second reviewer, no second fold of its usage, and no
round spent; a subject that moved, or evidence that can never be relied on,
drops it -- over the comment as it stands, and never in place of a verdict
another road put there.
"""
from __future__ import annotations

import itertools
import operator
import unittest
from functools import partial
from unittest.mock import patch

from orchestrator import config as _config
from orchestrator.github.pinned_state import MAX_PINNED_BODY
from orchestrator.workflow.stages.validating import (
    review_claims as _claims,
    review_disposition as _disposition,
    review_verdicts as _verdicts,
)
from tests.workflow.stages.validating import review_verdict_readings as _read, review_verdict_test_support as _world

REREAD = "reread_report_location"

PINNED_WRITE = "write_pinned_state"

POST = "_post_verification_artifact"

REVIEW_ROUND = "review_round"

TREE_READ = "_tree_sha"

# What a human edits a landed artifact's quoted output to.
_EDITED_OUTPUT = "13 passed"

# The thread mark another road's answer to a reply advances, and the issue
# comment it has read through.
LAST_ACTION = "last_action_comment_id"

ANSWERED_THROUGH = 1_999_001

# The issue's usage totals, and the tokens the developer run answering that
# reply folds into them.
AGENT_RUNS = "issue_agent_runs"

TOKENS = "issue_total_tokens"

ANSWER_TOKENS = 10

# The member of a waiting verdict's record naming which verdict it is, and the
# verdict an approval's record names.
VERDICT = "verdict"

APPROVED = "approved"

# A reviewer approving over the evidence revision `digest` names, running
# nothing of its own.
REUSING = "Covered.\n\nVERIFICATION: REUSED sha256:{digest}\n\nVERDICT: APPROVED"

UNDECLARED_REQUEST = f"{_world.REQUESTED}\n\nVERDICT: CHANGES_REQUESTED"

# Whether a pinned-comment write carries a returned verdict, or settled
# verification evidence.
_CARRIES_THE_VERDICT = operator.methodcaller("get", _world.RETURNED_VERDICT)

_SETTLED = operator.methodcaller("get", "verification_evidence_current")

# What preparing a verdict answers where the tick has nothing to act on.
NOTHING = _disposition.Prepared()

# A change request's feedback longer than most of what the pinned comment
# holds, and a failed run's output the transaction quotes again: the filler
# leaves room for the round's own records and not for the verdict, or for the
# verdict and not its transaction.
_LONG = "12 passed, 1 failed " * 1000

# Each verdict that cannot be persisted, the operator notes filling the comment
# ahead of it, and why it went unrecorded: no room for the verdict, no room for
# its transaction beside it, or feedback in words UTF-8 cannot carry -- which a
# reviewer's JSON decodes a lone surrogate into -- however much room there is.
_UNRECORDED = (
    (
        "no room for the verdict",
        f"{_LONG}\n\nVERDICT: CHANGES_REQUESTED",
        MAX_PINNED_BODY - len(_LONG),
        _disposition.NO_ROOM,
    ),
    (
        "no room for its evidence",
        _world.declared_run(exit_status=1, verdict="CHANGES_REQUESTED", output=_LONG),
        MAX_PINNED_BODY - len(_LONG) * 3 // 2,
        _disposition.NO_ROOM,
    ),
    ("feedback UTF-8 cannot carry", "1. Handle \ud800 too.\n\nVERDICT: CHANGES_REQUESTED", 0, _disposition.UNREADABLE),
)


def _answers_a_reply(case, moves=()) -> None:
    """Another road's write answering a reply -- the round it buys, the thread read through -- then `moves`.

    The answer is a developer's run, whose usage is folded into the issue's
    totals in the same write. None of those fields is a record a verdict
    stands on, so only a write composed over the comment as it stands keeps
    them. Each of `moves` is more of another road's work, done behind that
    write.
    """
    state = case.github.read_pinned_state(case.issue)
    state.set(REVIEW_ROUND, (state.get(REVIEW_ROUND) or 0) + 1)
    state.set(LAST_ACTION, ANSWERED_THROUGH)
    state.set(AGENT_RUNS, (state.get(AGENT_RUNS) or 0) + 1)
    state.set(TOKENS, (state.get(TOKENS) or 0) + ANSWER_TOKENS)
    case.github.write_pinned_state(case.issue, state)
    for move in moves:
        move(case)


# The reply each verdict ready without publishing anything was returned with,
# and the evidence it is ready over: how it relies on it, the refusal a
# declaration of none says, and the artifacts the pull request shows -- only
# the one an earlier round settled, where a reuse names it.
_READY = (
    (
        "a reuse of settled evidence",
        lambda case: REUSING.format(digest=_read.settles_evidence(case).content_revision),
        ("reused", "", 1),
    ),
    ("a change request declaring nothing", lambda _case: UNDECLARED_REQUEST, (None, _claims.NO_DECLARATION, 0)),
)

# Another road's work behind a request ahead of the verdict's write, and the
# report revision, round, and current evidence revision the pinned comment
# carries then: a later report or evidence settling while the reviewed tree is
# read for the transaction, a later report behind the subject check -- the
# second reread of the settled report, behind the one the round resolved its
# subject with -- and a push while the tree is read. The comment is read after
# the subject, so what settled is carried and never written back over.
_BEFORE_THE_WRITE = (
    ("a report during minting", (TREE_READ, bool, _read.settles_a_later_report), (2, 1, None)),
    ("evidence during minting", (TREE_READ, bool, _read.settles_evidence), (1, 0, 1)),
    ("a report behind the subject check", (REREAD, bool, _read.settles_a_later_report, 2), (2, 1, None)),
    ("a push during minting", (TREE_READ, bool, _world.pushes), (1, 0, None)),
)


# The reply a verdict was returned with, another road's work behind a request
# once the verdict is written, and what the tick leaves: the verdict waiting,
# whether the transaction is still owed, the report revision, the current
# evidence revision, and the round. A later report or a push behind the
# artifact's post, or behind the write that settled the evidence or persisted
# a verdict nothing published, proves the verdict is of a subject that moved;
# a later revision recorded and settled behind the verdict's own write
# supersedes the one it claims or reuses; a thread nobody could read proves
# nothing, and holds it. A round another road spent beside a move is kept.
_ONCE_WRITTEN = (
    (
        "a later report behind the post",
        lambda _case: _world.declared_run(),
        (POST, bool, _read.settles_a_later_report),
        (None, True, 2, None, 1),
    ),
    (
        "a push behind the post",
        lambda _case: _world.declared_run(),
        (POST, bool, _world.pushes),
        (None, True, 1, None, 0),
    ),
    (
        "a push behind the settlement",
        lambda _case: _world.declared_run(),
        (PINNED_WRITE, _SETTLED, _world.pushes),
        (None, False, 1, 1, 0),
    ),
    (
        "later evidence behind the verdict's write",
        lambda _case: _world.declared_run(),
        (PINNED_WRITE, _CARRIES_THE_VERDICT, _read.settles_evidence),
        (None, False, 1, 2, 0),
    ),
    (
        "a push beside a reply behind a reuse's write",
        lambda case: REUSING.format(digest=_read.settles_evidence(case).content_revision),
        (PINNED_WRITE, _CARRIES_THE_VERDICT, partial(_answers_a_reply, moves=(_world.pushes,))),
        (None, False, 1, 1, 1),
    ),
    (
        "later evidence behind a reuse's write",
        lambda case: REUSING.format(digest=_read.settles_evidence(case).content_revision),
        (PINNED_WRITE, _CARRIES_THE_VERDICT, _read.settles_evidence),
        (None, False, 1, 2, 0),
    ),
    (
        "a push behind a change request's write",
        lambda _case: UNDECLARED_REQUEST,
        (PINNED_WRITE, _CARRIES_THE_VERDICT, _world.pushes),
        (None, False, 1, None, 0),
    ),
    (
        "an unread thread behind the post",
        lambda _case: _world.declared_run(),
        (POST, bool, _world.stops_answering),
        (APPROVED, True, 1, None, 0),
    ),
)

# Another road's work once a later tick has read the comment, beside a reply
# it answers: whether the waiting verdict's claim is a reuse or its own
# published run, the moves, and what that tick leaves -- whether the verdict
# is ready, the verdict waiting, and the current evidence revision. A push, or
# a later revision superseding the evidence its claim names, drops it.
_WHILE_IT_WAITED = (
    ("nothing else", True, (), (True, APPROVED, 1)),
    ("a push, its claim reused", True, (_world.pushes,), (False, None, 1)),
    ("a push, its claim published", False, (_world.pushes,), (False, None, 1)),
    ("later evidence", True, (_read.settles_evidence,), (False, None, 2)),
)

# The writes behind which another road clears the verdict or puts its own in
# its place: the one persisting it, and the one settling its evidence.
_REPLACED_BEHIND = (("the verdict's write", _CARRIES_THE_VERDICT), ("the settlement", _SETTLED))


class _RefusesTheVerdict:
    """A pinned-comment write GitHub refuses wherever it carries a returned verdict, and takes otherwise."""

    def __init__(self, writes) -> None:
        self._writes = writes

    def __call__(self, issue, state):
        if _CARRIES_THE_VERDICT(state):
            raise RuntimeError("GitHub refused the edit")
        return self._writes(issue, state)


def _leaves(case, *, replaces: bool) -> None:
    """Another road's write clearing `case`'s returned verdict, or leaving a later round's change request there.

    What it left is kept as `case.left`.
    """
    state = case.github.read_pinned_state(case.issue)
    case.left = None
    if replaces:
        case.left = {
            "round": 1,
            VERDICT: "changes_requested",
            "subject": state.get("review_subject"),
            "feedback": "A later round's feedback.",
            "evidence": None,
            "handed": None,
            "anchor": None,
        }
    state.set(_world.RETURNED_VERDICT, case.left)
    case.github.write_pinned_state(case.issue, state)


def _restores_and_settles(case) -> None:
    """Another tick's reconciliation settling `case`'s owed transaction, over its edited artifact restored."""
    artifact = case.pull_request.issue_comments[-1]
    artifact.body = artifact.body.replace(_EDITED_OUTPUT, _world.SUITE_OUTPUT)
    _world.reconciles(case)


# Another road's work once a tick has read the comment its verdict waits on an
# owed transaction in -- its artifact edited, so that tick's own
# reconciliation stood down -- and what the tick leaves: whether the verdict
# is ready, the verdict waiting, whether the transaction is still owed, and the
# current evidence revision. Nothing else holds it; another tick settling that
# very transaction, its artifact restored, readies it rather than moving it;
# a push drops it, leaving the transaction to the reconciliation.
_OWED = (
    ("nothing else", None, (False, APPROVED, True, None)),
    ("settled by another tick", _restores_and_settles, (True, APPROVED, False, 1)),
    ("a push", _world.pushes, (False, None, True, None)),
)


class PersistedVerdictTest(_world.ReviewVerdictWorld, unittest.TestCase):
    """The verdict goes down with its transaction before anything is published, or nothing does."""

    def test_the_verdict_is_written_before_publishing(self) -> None:
        # What the pinned comment carries as the artifact is posted, which the
        # post itself leaves untouched.
        seen: list[dict] = []
        posting = _world.AnotherRoadBehind(
            self, POST, bool, lambda case: seen.append(case.pinned()),
        )
        posting.returning(_world.declared_run())

        written = seen[0]
        claim = written[_world.RETURNED_VERDICT]["evidence"]
        self.assertEqual(
            (
                claim["use"],
                claim["passed"] and claim["covers"],
                written[_world.PENDING_EVIDENCE]["receipt"],
            ),
            ("published", True, claim["receipt"]),
        )
        # Settled, and ready as persisted: nothing acts on it here.
        pinned = self.pinned()
        self.assertEqual(
            _verdicts.ReturnedVerdict.read(pinned[_world.RETURNED_VERDICT]), self.prepared.ready.returned(),
        )
        self.assertEqual(
            (
                self.prepared.ready.claim.receipt,
                pinned[_world.RETURNED_VERDICT]["evidence"],
                pinned[_world.PENDING_EVIDENCE],
                _read.current_evidence_revision(self),
                len(_read.artifacts(self)),
                _read.spent(self),
                self.github.label_history,
            ),
            (
                claim["receipt"],
                claim,
                None,
                1,
                1,
                (1, 1, _world.REVIEWER_TOKENS, 0),
                [],
            ),
        )

    def test_an_unrecorded_verdict_publishes_nothing(self) -> None:
        # The park that answers it is the caller's; the preparation says why
        # and leaves the comment exactly as it found it.
        for name, message, filled, why in _UNRECORDED:
            with self.subTest(name):
                self.setUp()
                self._fills(filled)
                before = self.pinned()

                self.returns(message)

                self.assertEqual(
                    (self.prepared, self.pinned(), _read.artifacts(self)),
                    (_disposition.Prepared(unrecorded=why), before, []),
                )

    def test_a_refused_write_publishes_nothing(self) -> None:
        refusing = _RefusesTheVerdict(self.github.write_pinned_state)
        with patch.object(self.github, PINNED_WRITE, refusing), self.assertRaises(RuntimeError):
            self.returns(_world.declared_run())

        pinned = self.pinned()
        self.assertEqual(
            (
                pinned.get(_world.RETURNED_VERDICT),
                pinned.get(_world.PENDING_EVIDENCE),
                _read.artifacts(self),
            ),
            (None, None, []),
        )

    def _fills(self, filled: int) -> None:
        """Put `filled` characters of operator notes on the pinned comment."""
        state = self.github.read_pinned_state(self.issue)
        state.set("operator_notes", "x" * filled)
        self.github.write_pinned_state(self.issue, state)


class EvidenceStandingTest(_world.ReviewVerdictWorld, unittest.TestCase):
    """A verdict is ready over settled evidence or none, held while it is owed, and dropped once it is lost."""

    def test_settled_evidence_or_none_is_ready(self) -> None:
        # Ready as persisted: what the comment carries reads back as the
        # verdict in hand.
        for name, reply, expected in _READY:
            with self.subTest(name):
                self.setUp()

                self.returns(reply(self))

                ready = self.prepared.ready
                persisted = _verdicts.ReturnedVerdict.read(self.pinned()[_world.RETURNED_VERDICT])
                self.assertEqual(
                    (
                        None if ready.claim is None else ready.claim.use.value,
                        ready.refusal,
                        len(_read.artifacts(self)),
                    ),
                    expected,
                )
                self.assertEqual(persisted, ready.returned())

    def test_owed_evidence_needs_no_reviewer(self) -> None:
        # The post lands and its response is lost: the tick holds with the
        # verdict and its transaction owed. The next tick's reconciliation
        # finds the artifact by its receipt, and the verdict is ready from the
        # record the first tick wrote, read off the comment alone.
        self._held()
        waiting = self.pinned()
        spent = _read.spent(self)
        self.assertEqual(
            (
                self.prepared,
                waiting[_world.RETURNED_VERDICT][VERDICT],
                waiting[_world.PENDING_EVIDENCE] is None,
            ),
            (NOTHING, APPROVED, False),
        )

        finished = self.finishes()

        self.assertEqual(
            (
                self.ready,
                finished[_world.RUN_AGENT].call_count,
                _read.spent(self),
                len(_read.artifacts(self)),
                _read.current_evidence_revision(self),
            ),
            (
                _verdicts.ReturnedVerdict.read(waiting[_world.RETURNED_VERDICT]),
                0,
                spent,
                1,
                1,
            ),
        )

    def test_owed_evidence_holds_it_while_it_stands(self) -> None:
        for name, meanwhile, expected in _OWED:
            with self.subTest(name):
                self.setUp()
                self._held()
                artifact = self.pull_request.issue_comments[-1]
                artifact.body = artifact.body.replace(_world.SUITE_OUTPUT, _EDITED_OUTPUT)

                self.finishes(meanwhile=meanwhile)

                pinned = self.pinned()
                self.assertEqual(
                    (
                        self.ready is not None,
                        (pinned[_world.RETURNED_VERDICT] or {}).get(VERDICT),
                        pinned[_world.PENDING_EVIDENCE] is not None,
                        _read.current_evidence_revision(self),
                    ),
                    expected,
                )

    def test_evidence_that_can_never_settle_drops_it(self) -> None:
        # The verification context the owed transaction was bound under moves,
        # so that evidence can never settle: the verdict is dropped for a
        # fresh reviewer rather than waiting on it forever. A later report, or
        # a reply answered, by another road once the tick has read the comment
        # is kept rather than written back over by that drop.
        for name, meanwhile, recorded in (
            ("alone", None, (1, 0)),
            ("beside a later report", _read.settles_a_later_report, (2, 1)),
            ("beside a reply answered", _answers_a_reply, (1, 1)),
        ):
            with self.subTest(name):
                self.setUp()
                self._held()

                with patch.object(_config, "VERIFY_TIMEOUT", _config.VERIFY_TIMEOUT + 1):
                    self.finishes(meanwhile=meanwhile)

                self.assertEqual(
                    (
                        self.ready is not None,
                        self.pinned()[_world.RETURNED_VERDICT],
                        (_read.current_report_revision(self), self.pinned()[REVIEW_ROUND]),
                    ),
                    (False, None, recorded),
                )

    def test_a_waiting_verdict_is_held_to_what_stands(self) -> None:
        # Settled evidence is not the end of it: the subject and the records
        # it was proved over are read again behind the tick's own reads, so a
        # push, or a later revision settled once the tick read the comment,
        # drops the verdict for a fresh reviewer. A reply another road
        # answered beside them is no move, and every drop keeps it.
        for name, reused, moves, expected in _WHILE_IT_WAITED:
            with self.subTest(name):
                self.setUp()
                _read.seeds_a_verdict(self, _read.settles_evidence(self), reused=reused)

                self.finishes(meanwhile=partial(_answers_a_reply, moves=moves))

                pinned = self.pinned()
                self.assertEqual(
                    (
                        self.ready is not None,
                        (pinned[_world.RETURNED_VERDICT] or {}).get(VERDICT),
                        _read.current_evidence_revision(self),
                    ),
                    expected,
                )
                self.assertEqual(
                    (pinned[REVIEW_ROUND], pinned[LAST_ACTION]),
                    (1, ANSWERED_THROUGH),
                )

    def test_a_superseded_claim_drops_either_verdict(self) -> None:
        # The evidence a waiting verdict's reuse named is superseded by a later
        # revision before the verdict is finished: the reviewer judged the
        # branch beside evidence the pull request no longer carries as
        # current, so the verdict is dropped for a fresh reviewer handed the
        # later one, and nothing is spent or posted.
        for verdict in (APPROVED, "changes_requested"):
            with self.subTest(verdict):
                self.setUp()
                _read.seeds_a_verdict(self, _read.settles_evidence(self), verdict, reused=True)
                _read.settles_evidence(self)
                before = (_read.spent(self), len(self.github.posted_pr_comments))

                self.finishes()

                self.assertEqual(
                    (
                        self.ready is not None,
                        self.pinned()[_world.RETURNED_VERDICT],
                        (_read.spent(self), len(self.github.posted_pr_comments)),
                    ),
                    (False, None, before),
                )

    def _held(self) -> None:
        """Return an approval over its own run, on a pull request that lands the artifact and loses the response."""
        self.github.report_failures.lost.add(_world.PR)
        self.returns(_world.declared_run())
        self.github.report_failures.lost.discard(_world.PR)


class RecordRaceTest(_world.ReviewVerdictWorld, unittest.TestCase):
    """A verdict is persisted and kept only over the subject and records it was proved over."""

    def test_a_move_before_the_write_persists_nothing(self) -> None:
        # The run is recorded over what moved -- its usage folded once -- and
        # neither the verdict nor its transaction is persisted or published.
        for name, behind, recorded in _BEFORE_THE_WRITE:
            with self.subTest(name):
                self.setUp()

                _world.AnotherRoadBehind(self, *behind).returning(_world.declared_run())

                pinned = self.pinned()
                self.assertEqual(
                    (
                        self.prepared,
                        pinned.get(_world.RETURNED_VERDICT),
                        pinned.get(_world.PENDING_EVIDENCE),
                        _read.spent(self)[:3],
                    ),
                    (NOTHING, None, None, (1, 1, _world.REVIEWER_TOKENS)),
                )
                # Only an artifact another road settled is on the pull request.
                self.assertEqual(
                    (
                        _read.current_report_revision(self),
                        pinned[REVIEW_ROUND],
                        _read.current_evidence_revision(self),
                        len(_read.artifacts(self)),
                    ),
                    (*recorded, int(recorded[-1] is not None)),
                )

    def test_a_reply_answered_while_minting_is_kept(self) -> None:
        # Another road answers a reply while the reviewed tree is read, which
        # moves no record the verdict stands on: the verdict's write, or the
        # run's own where a push beside it moved the subject, is composed over
        # the comment as it stands and keeps the round and the thread's mark
        # -- and so does the run's own where a later report beside it moved
        # the records. Either way the reviewer's usage is folded over the
        # answer's, never in place of it.
        for name, moves, expected in (
            ("alone", (), (APPROVED, 1)),
            ("beside a push", (_world.pushes,), (None, 1)),
            ("beside a later report", (_read.settles_a_later_report,), (None, 2)),
        ):
            with self.subTest(name):
                self.setUp()
                answering = partial(_answers_a_reply, moves=moves)

                _world.AnotherRoadBehind(self, TREE_READ, bool, answering).returning(_world.declared_run())

                pinned = self.pinned()
                self.assertEqual(
                    (
                        (pinned.get(_world.RETURNED_VERDICT) or {}).get(VERDICT),
                        pinned[REVIEW_ROUND],
                        pinned[LAST_ACTION],
                        (pinned[AGENT_RUNS], pinned[TOKENS]),
                    ),
                    (*expected, ANSWERED_THROUGH, (2, ANSWER_TOKENS + _world.REVIEWER_TOKENS)),
                )

    def test_an_unread_subject_writes_nothing(self) -> None:
        # The thread stops answering once the round has resolved its subject:
        # no verdict is persisted over a reading nobody took.
        before = self.pinned()

        unread = _world.AnotherRoadBehind(self, REREAD, bool, _world.stops_answering)
        unread.returning(_world.declared_run())

        self.assertEqual(
            (self.prepared, self.pinned(), _read.artifacts(self)),
            (NOTHING, before, []),
        )

    def test_a_move_once_the_verdict_is_written(self) -> None:
        for name, reply, behind, expected in _ONCE_WRITTEN:
            with self.subTest(name):
                self.setUp()

                _world.AnotherRoadBehind(self, *behind).returning(reply(self))

                pinned = self.pinned()
                self.assertEqual(
                    (
                        self.prepared,
                        (pinned.get(_world.RETURNED_VERDICT) or {}).get(VERDICT),
                        pinned.get(_world.PENDING_EVIDENCE) is not None,
                        _read.current_report_revision(self),
                        _read.current_evidence_revision(self),
                        pinned[REVIEW_ROUND],
                    ),
                    (NOTHING, *expected),
                )

    def test_another_roads_verdict_is_left_standing(self) -> None:
        # Another road clears the verdict, or puts a later round's change
        # request in its place, right behind a write this tick made: nothing
        # is ready, and whatever that road left is still what the comment
        # carries -- this tick drops only its own verdict.
        for (name, when), replaces in itertools.product(_REPLACED_BEHIND, (False, True)):
            with self.subTest(name, replaces=replaces):
                self.setUp()

                _world.AnotherRoadBehind(
                    self, PINNED_WRITE, when, partial(_leaves, replaces=replaces),
                ).returning(_world.declared_run())

                self.assertEqual(
                    (self.prepared, self.pinned()[_world.RETURNED_VERDICT]), (NOTHING, self.left),
                )

if __name__ == "__main__":
    unittest.main()
