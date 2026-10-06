# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A returned reviewer's verdict, persisted and its evidence reconciled before anything acts on it.

The verdict and the transaction its declared commands are minted as go down in
one write before the evidence is published, and the verdict is ready to be
acted on only once that evidence has settled, or where it relies on none. A
comment with no room for either, or a write GitHub refuses, publishes nothing.
A verdict's feedback is the reviewer's findings without their declaration,
which still earns exactly what it would unformatted, every command, status,
and output kept in the transaction.
Evidence still owed, or settled by a commit nobody confirmed, holds the
verdict while its subject stands, for a later tick to finish with no second
reviewer, no second fold of its usage, and no round spent; a subject that
moved, or evidence that can never be relied on, drops it -- over the comment
as it stands, and never in place of a verdict another road put there.

What a ready verdict is disposed of through -- the approval arc, the
change-request handoff, the parks -- is in `test_review_verdict_approvals.py`,
`test_review_verdict_handoffs.py`, and `test_review_verdict_parks.py`, and the
run a verdict is acted through in `test_review_verdict_runs.py`.
"""
from __future__ import annotations

import itertools
import operator
import unittest
from functools import partial
from unittest.mock import patch

from orchestrator import config as _config
from orchestrator.workflow.stages.validating import (
    review_claims as _claims,
    review_disposition as _disposition,
    review_parks as _parks,
    review_verdicts as _verdicts,
)
from tests.workflow.reviewed_reports import restate
from tests.workflow.stages.validating import (
    disposed_verdict_test_support as _disposed,
    review_park_test_support as _parked,
    review_verdict_readings as _read,
    review_verdict_test_support as _world,
    review_write_test_support as _roads,
)

REREAD = "reread_report_location"

# The strict edit the evidence settlement's guarded commit lands through.
PINNED_EDIT = "edit_pinned_state"

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

# A passing command the configuration does not require.
UNRELATED = "true"

# How a claim relies on its evidence, as the record spells it.
PUBLISHED = "published"

REUSED = "reused"

# Whether a pinned-comment write carries a returned verdict, or settled
# verification evidence.
_CARRIES_THE_VERDICT = operator.methodcaller("get", _world.RETURNED_VERDICT)

_SETTLED = operator.methodcaller("get", "verification_evidence_current")

_HISTORY = "verification_evidence_history"

# What preparing a verdict answers where the tick has nothing to act on.
NOTHING = _disposition.Prepared()


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

# What the artifact of the world's failed run of the suite carries.
FAILED_RUN = ((_world.SUITE, 1, _world.FAILURE_OUTPUT),)

# The reply each change request was returned with, and what the tick leaves:
# the feedback it is persisted with; the use, pass, and coverage of the claim
# its declaration earned, or the refusal it earned none with; and every
# command, exit status, and output the pull request's artifacts carry.
_CONCISE = (
    (
        "a failed run",
        lambda _case: _world.FAILED_REQUEST,
        (
            _world.CONCISE_FAILURE,
            ((PUBLISHED, False, False), ""),
            FAILED_RUN,
        ),
    ),
    (
        "the configured command left out",
        lambda _case: _world.declared_run(verdict="CHANGES_REQUESTED", command=UNRELATED),
        (
            _world.REQUESTED,
            ((PUBLISHED, True, False), ""),
            ((UNRELATED, 0, _world.SUITE_OUTPUT),),
        ),
    ),
    (
        "a reuse",
        lambda case: _world.REQUEST_REUSING.format(digest=_read.settles_evidence(case).content_revision),
        (
            _world.REQUESTED,
            ((REUSED, True, True), ""),
            ((_world.SUITE, 0, _world.SUITE_OUTPUT),),
        ),
    ),
    (
        "nothing declared",
        lambda _case: UNDECLARED_REQUEST,
        (_world.REQUESTED, (None, _claims.NO_DECLARATION), ()),
    ),
    (
        "a run declared alone",
        lambda _case: _world.DECLARED_ALONE,
        (
            _world.NO_FINDINGS,
            ((PUBLISHED, True, True), ""),
            ((_world.SUITE, 0, _world.SUITE_OUTPUT),),
        ),
    ),
)

# Another road pointing the issue at another pull request, leaving the one
# reviewed standing as it was handed.
_OTHER_PR = _world.PR + 1

_REPOINTS = partial(restate, pr_number=_OTHER_PR)

# Another road's work behind a request ahead of the verdict's write, and the
# report revision, round, and current evidence revision the pinned comment
# carries then: a later report or evidence settling while the reviewed tree is
# read for the transaction, a later report behind the subject check -- the
# second reread of the settled report, behind the one the round resolved its
# subject with -- and a push, or the issue pointed at another pull request,
# while the tree is read. The comment is read after the subject, so what
# settled is carried and never written back over.
_BEFORE_THE_WRITE = (
    ("a report during minting", (TREE_READ, bool, _read.settles_a_later_report), (2, 1, None)),
    ("evidence during minting", (TREE_READ, bool, _read.settles_evidence), (1, 0, 1)),
    ("a report behind the subject check", (REREAD, bool, _read.settles_a_later_report, 2), (2, 1, None)),
    ("a push during minting", (TREE_READ, bool, _world.pushes), (1, 0, None)),
    ("a repoint during minting", (TREE_READ, bool, _REPOINTS), (1, 0, None)),
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
        (PINNED_EDIT, _SETTLED, _world.pushes),
        (None, False, 1, 1, 0),
    ),
    (
        "later evidence behind the verdict's write",
        lambda _case: _world.declared_run(),
        (PINNED_EDIT, _CARRIES_THE_VERDICT, _read.settles_evidence),
        (None, False, 1, 2, 0),
    ),
    (
        "a push beside a reply behind a reuse's write",
        lambda case: REUSING.format(digest=_read.settles_evidence(case).content_revision),
        (PINNED_EDIT, _CARRIES_THE_VERDICT, partial(_answers_a_reply, moves=(_world.pushes,))),
        (None, False, 1, 1, 1),
    ),
    (
        "later evidence behind a reuse's write",
        lambda case: REUSING.format(digest=_read.settles_evidence(case).content_revision),
        (PINNED_EDIT, _CARRIES_THE_VERDICT, _read.settles_evidence),
        (None, False, 1, 2, 0),
    ),
    (
        "a push behind a change request's write",
        lambda _case: UNDECLARED_REQUEST,
        (PINNED_EDIT, _CARRIES_THE_VERDICT, _world.pushes),
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
# its place: the one persisting it, and the commit settling its evidence.
_REPLACED_BEHIND = (
    ("the verdict's write", PINNED_EDIT, _CARRIES_THE_VERDICT),
    ("the settlement", PINNED_EDIT, _SETTLED),
)


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
        }
    state.set(_world.RETURNED_VERDICT, case.left)
    case.github.write_pinned_state(case.issue, state)


def _restores_and_settles(case) -> None:
    """Another tick's reconciliation settling `case`'s owed transaction, over its edited artifact restored."""
    artifact = case.pull_request.issue_comments[-1]
    artifact.body = artifact.body.replace(_EDITED_OUTPUT, _world.SUITE_OUTPUT)
    _world.reconciles(case)


# The ledger of the orchestrator's own comments, and a notice another road
# posts and records there.
LEDGER = "orchestrator_comment_ids"

ANOTHER_NOTICE = 1_999_002

# Another road's write right ahead of the commit persisting a verdict, behind
# the last reading the verdict was decided on, and what preparing it answers:
# a later report or evidence settled, a verdict of that road's own or one
# written `null` where there was none, a repoint, or the comment unparsed or
# replaced refuses the commit; a comment filled to its limit has no room for
# the verdict, which its caller parks as unrecorded.
_AHEAD_OF_THE_COMMIT = (
    ("a later report", _read.settles_a_later_report, NOTHING),
    ("evidence settled", _read.settles_evidence, NOTHING),
    ("another round's verdict", partial(_leaves, replaces=True), NOTHING),
    ("a verdict written null", partial(_leaves, replaces=False), NOTHING),
    ("a repoint", _REPOINTS, NOTHING),
    ("an unparsed comment", _roads.unparses, NOTHING),
    ("a replaced comment", _roads.repins, NOTHING),
    ("a full comment", partial(_parked.fills_to, spare=0), _disposition.Prepared(unrecorded=_parks.NO_ROOM)),
)

# Another road's write right ahead of the commit dropping a waiting verdict a
# push moved the subject of, and whether the drop lands beside it: a verdict
# of that road's own in place of the one held, or a later evidence revision
# recorded, refuses it; a reply answered does not.
_AHEAD_OF_THE_DROP = (
    ("another round's verdict", partial(_leaves, replaces=True), False),
    ("a later evidence revision", _roads.Writes({"verification_evidence_revision": 2}), False),
    ("a reply answered", _answers_a_reply, True),
)

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


# Each response a returned approval's tick can lose -- the failures it is lost
# through, the issue or pull request named there, and the write behind which it
# starts losing, None for from the first -- and whether the transaction the
# verdict persisted is settled once that tick holds: the artifact's post, the
# commit settling it, and the commit persisting the verdict itself, which
# leaves the artifact unposted.
_POST_LOST = ("report_failures", _world.PR, None)

_LOST = (
    ("the artifact's post", _POST_LOST, False),
    ("the settlement", ("pinned_failures", _world.ISSUE, _CARRIES_THE_VERDICT), True),
    ("the verdict's own commit", ("pinned_failures", _world.ISSUE, None), False),
)


class PersistedVerdictTest(_world.ReviewVerdictWorld, unittest.TestCase):
    """The verdict goes down with its transaction before anything is published, or nothing does.

    Its feedback is the reviewer's findings, concise, beside exactly the evidence its declaration earned.
    """

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
        for name, message, filled, why in _disposed.UNRECORDED:
            with self.subTest(name):
                self.setUp()
                _disposed.fills(self, filled)
                before = self.pinned()

                self.returns(message)

                self.assertEqual(
                    (self.prepared, self.pinned(), _read.artifacts(self)),
                    (_disposition.Prepared(unrecorded=why), before, []),
                )

    def test_a_refused_write_publishes_nothing(self) -> None:
        # GitHub refuses the commit persisting the verdict: nothing is
        # recorded, and nothing that depends on the record is made.
        self.github.pinned_failures.refused.add(_world.ISSUE)
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

    def test_concise_findings_beside_exact_evidence(self) -> None:
        # The declaration is read off the message as the reviewer wrote it,
        # so a run, a reuse, a failed check, a configured command left out,
        # and nothing declared each earn what they would unformatted, and the
        # artifact keeps every command, status, and output. The feedback sets
        # the declaration aside, save a failed check kept as its diagnostic,
        # and a run declared alone reads as no findings rather than as the
        # raw message it sits in.
        for name, reply, expected in _CONCISE:
            with self.subTest(name):
                self.setUp()

                self.returns(reply(self))

                self.assertEqual(self._persisted(), expected)

    def test_a_lost_post_keeps_the_concise_findings(self) -> None:
        # The artifact lands and its response is lost: the request waits with
        # its findings concise and its transaction owed, and the later tick
        # that finds the artifact by its receipt readies it exactly as
        # persisted, the output the findings left out kept whole there.
        self.github.report_failures.lost.add(_world.PR)
        self.returns(_world.FAILED_REQUEST)
        self.github.report_failures.lost.discard(_world.PR)
        waiting = self._persisted()[0]
        owed = self.pinned()[_world.PENDING_EVIDENCE] is not None

        self.finishes()

        self.assertEqual((self.prepared, waiting, owed), (NOTHING, _world.CONCISE_FAILURE, True))
        self.assertEqual(self.ready.feedback, _world.CONCISE_FAILURE)
        self.assertEqual(_disposed.carried(self), FAILED_RUN)

    def _persisted(self) -> tuple:
        """The waiting verdict's feedback, what its declaration earned, and what the artifacts carry, as `_CONCISE`."""
        verdict = _verdicts.read_returned_verdict(self.github.read_pinned_state(self.issue))
        claim = verdict.evidence
        earned = None
        if claim is not None:
            earned = (claim.use.value, claim.passed, claim.covers)
        refusal = "" if self.prepared.ready is None else self.prepared.ready.refusal
        return (verdict.feedback, (earned, refusal), _disposed.carried(self))


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
        # The commit persisting the verdict lands and its response is lost,
        # or the artifact's post does, or the commit settling it: the tick
        # publishes or acts on nothing past the response it lost, with the
        # verdict persisted beside its transaction, owed or settled with
        # nobody told. The next tick's reconciliation posts the artifact, finds
        # it by its receipt and settles it, or finds nothing owed, and the
        # verdict is ready from the record the first tick wrote, read off the
        # comment alone -- with no second reviewer, charge, fold, round,
        # artifact, or settlement.
        for lost in _LOST:
            with self.subTest(lost[0]):
                self.setUp()
                self._held(lost[1])
                waiting = self.pinned()
                spent = _read.spent(self)
                self.assertEqual(
                    (
                        self.prepared,
                        waiting[_world.RETURNED_VERDICT][VERDICT],
                        waiting[_world.PENDING_EVIDENCE] is None,
                    ),
                    (NOTHING, APPROVED, lost[2]),
                )

                finished = self.finishes()

                self.assertEqual(
                    (
                        self.ready,
                        finished[_world.RUN_AGENT].call_count,
                        _read.spent(self),
                        len(_read.artifacts(self)),
                        _read.current_evidence_revision(self),
                        self.pinned().get(_HISTORY),
                    ),
                    (
                        _verdicts.ReturnedVerdict.read(waiting[_world.RETURNED_VERDICT]),
                        0,
                        spent,
                        1,
                        1,
                        None,
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

    def _held(self, lost: tuple = _POST_LOST) -> None:
        """Return an approval over its own run, losing the response `lost` names, as `_LOST` spells one."""
        failures, number, behind = lost
        losing = getattr(self.github, failures).lost
        if behind is None:
            losing.add(number)
            self.returns(_world.declared_run())
        else:
            _world.AnotherRoadBehind(
                self, PINNED_EDIT, behind, lambda _case: losing.add(number),
            ).returning(_world.declared_run())
        losing.discard(number)


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

    def test_a_repointed_issue_drops_the_verdict(self) -> None:
        # The issue is pointed at another pull request between ticks, or once
        # a later tick has read the comment: the one reviewed still stands as
        # it was handed, but every road acting on the verdict reads the pull
        # request off the comment, so the verdict is dropped for a fresh
        # reviewer rather than answered on a pull request nobody reviewed --
        # and the pointer is kept as the other road left it.
        for name, between_ticks in (("between ticks", True), ("while it waited", False)):
            with self.subTest(name):
                self.setUp()
                _read.seeds_a_verdict(self, _read.settles_evidence(self), reused=True)
                if between_ticks:
                    _REPOINTS(self)

                self.finishes(meanwhile=None if between_ticks else _REPOINTS)

                pinned = self.pinned()
                self.assertEqual(
                    (self.ready, pinned[_world.RETURNED_VERDICT], pinned["pr_number"]),
                    (None, None, _OTHER_PR),
                )

    def test_another_roads_verdict_is_left_standing(self) -> None:
        # Another road clears the verdict, or puts a later round's change
        # request in its place, right behind a write this tick made: nothing
        # is ready, and whatever that road left is still what the comment
        # carries -- this tick drops only its own verdict.
        for (name, *behind), replaces in itertools.product(_REPLACED_BEHIND, (False, True)):
            with self.subTest(name, replaces=replaces):
                self.setUp()

                _world.AnotherRoadBehind(
                    self, *behind, partial(_leaves, replaces=replaces),
                ).returning(_world.declared_run())

                self.assertEqual(
                    (self.prepared, self.pinned()[_world.RETURNED_VERDICT]), (NOTHING, self.left),
                )



class CommitRaceTest(_world.ReviewVerdictWorld, unittest.TestCase):
    """A verdict's commit, and a drop's, land over another road's write right ahead of them, or not at all."""

    def test_a_move_ahead_of_the_commit_writes_none(self) -> None:
        # Another road writes right ahead of the commit persisting the
        # verdict, behind the last reading it was decided on: nothing is
        # persisted, published, or folded, and the comment stays exactly as
        # that road left it.
        for name, road, prepared in _AHEAD_OF_THE_COMMIT:
            with self.subTest(name):
                self.setUp()

                self._raced_ahead(_CARRIES_THE_VERDICT, road, self.returns, _world.declared_run())

                self.assertEqual(
                    (self.prepared, *self._left()), (prepared, *self.left_behind),
                )

    def test_a_reply_ahead_of_the_commit_is_kept(self) -> None:
        # Another road answers a reply, and records a notice it posted as the
        # orchestrator's, right ahead of the commit persisting the verdict:
        # the commit lands over it -- the reviewer's usage folded beside the
        # answer's, the thread read as far as that road read it, its round and
        # notice kept -- and the verdict's evidence is published and settled
        # behind it, its artifact recorded beside that notice.
        ledger = [*self.pinned().get(LEDGER, []), ANOTHER_NOTICE]
        answering = partial(_answers_a_reply, moves=(_roads.Writes({LEDGER: ledger}),))

        self._raced_ahead(_CARRIES_THE_VERDICT, answering, self.returns, _world.declared_run())

        pinned = self.pinned()
        recorded = {ANOTHER_NOTICE, self.pull_request.issue_comments[-1].id}
        self.assertEqual(
            (
                self.prepared.ready.returned(),
                pinned[REVIEW_ROUND],
                pinned[LAST_ACTION],
                (pinned[AGENT_RUNS], pinned[TOKENS]),
                _read.current_evidence_revision(self),
                recorded <= set(pinned[LEDGER]),
            ),
            (
                _verdicts.ReturnedVerdict.read(pinned[_world.RETURNED_VERDICT]),
                1,
                ANSWERED_THROUGH,
                (2, ANSWER_TOKENS + _world.REVIEWER_TOKENS),
                1,
                True,
            ),
        )

    def test_a_move_ahead_of_a_drop(self) -> None:
        # A push moves the subject of a waiting verdict, and another road
        # writes right ahead of the commit dropping it: one that put its own
        # verdict in place of the one held, or recorded a later evidence
        # revision, refuses the drop -- the comment stays as it left it, and
        # the verdict held waits for a later tick -- while a reply answered is
        # kept beside the drop.
        for name, road, dropped in _AHEAD_OF_THE_DROP:
            with self.subTest(name):
                self.setUp()
                settled = _read.settles_evidence(self)
                _read.seeds_a_verdict(self, settled, reused=True)

                self._raced_ahead(bool, road, self.finishes, meanwhile=_world.pushes)

                left = self.left_behind[0]
                if dropped:
                    left = {**left, _world.RETURNED_VERDICT: None}
                self.assertIsNone(self.ready)
                self.assertEqual(self.pinned(), left)

    def _raced_ahead(self, when, road, tick, *asked, **options) -> None:
        """`tick` asked with `road` landing right ahead of the first guarded commit `when` names.

        What the road left -- the pinned comment and the comments on the pull
        request -- is kept as `left_behind`.
        """
        with _roads.AnotherRoadAhead(self, when, partial(self._leaves_behind, road)).patched():
            tick(*asked, **options)

    def _leaves_behind(self, road, case) -> None:
        """`road`'s work on `case`, and what it left kept as `left_behind` (`_left`)."""
        road(case)
        self.left_behind = self._left()

    def _left(self) -> tuple:
        """The pinned comment, and every comment on the pull request."""
        return self.pinned(), len(self.pull_request.issue_comments)


if __name__ == "__main__":
    unittest.main()
