# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A captured run something moves under while the recovery publishes and settles it, abandoned rather than settled.

A finish recorded its run for the landed head and died posting its artifact,
so the recovery proves that run again, takes the last word behind every
request it made, and publishes and settles it with the attempt still standing.
Another road moves what the run is bound to on the way: the review subject just
behind the evidence step's last word, which the settlement's room -- prepared
over the comment before the post -- refuses with nothing posted; or the review
subject, the configured command, or the issue's requirements as the artifact
is posted, which the settlement's own proof, taken again over the issue and
comment read afresh, refuses -- the configuration read once more behind the
settlement's own requests, so a command configured as it re-reads the artifact
refuses it too. Either way the run is abandoned into history
rather than settled, and the head goes on to the fresh reviewer; put back
afterwards, the move revives nothing -- neither a later recovery nor the
dispatcher's reconciliation settles the run. A base that advances as the
artifact is posted refuses the settlement under the anchor's own proof: the run
is abandoned and the head held, for the next recovery to rebase it once more.
An attempt another road pins in place of the recovered one meanwhile refuses
every write the publication and settlement would make, and survives with the
run neither settled nor abandoned over it and nothing announced. Nothing runs,
pushes, or announces again, and no developer is launched.
"""
from __future__ import annotations

import hashlib
import unittest
from copy import copy
from dataclasses import replace
from functools import partial
from unittest.mock import patch

from orchestrator.git.base_sync import rewrite_facts
from orchestrator.workflow.engine import verification_record_state as _record_state
from orchestrator.workflow.engine.review_subjects import REVIEW_SUBJECT
from tests.workflow.engine import (
    rewrite_finish_git_support as git_support,
    rewrite_finish_readings as readings,
    rewrite_verification_recovery_support as support,
)
from tests.workflow.interleaving import _RacesPastTheCall

# A requirements revision no reviewer was handed, for a review subject another road records.
_ELSEWHERE = hashlib.sha256(b"requirements recorded behind the last word").hexdigest()

_EDITED_BODY = "Also cover a moved base."

_BODY = "body"


def _moves_the_subject(case: support.VerificationRecoveryCase, before: tuple, *, until_read: bool = False) -> None:
    """Record a review subject no reviewer was handed in place of the one `before` names.

    Where `until_read`, the subject `before` names is put back the moment the
    next read of the comment has answered -- the move read once, by whatever
    guard read it, and gone by the time anything reads the comment again.
    """
    _records_the_subject(case, {**before[0], "requirements": _ELSEWHERE})
    if until_read:
        _after(*_COMMENT_READ, _records_the_subject, case, before[0])


def _records_the_subject(case: support.VerificationRecoveryCase, recorded: dict) -> None:
    """Record `recorded` as the review subject on `case`'s pinned comment, as another road's write would."""
    moved = case.gh.read_pinned_state(case.issue)
    moved.set(REVIEW_SUBJECT, recorded)
    case.gh.write_pinned_state(case.issue, moved)


def _after(where, nth: int, moves, case: support.VerificationRecoveryCase, before) -> None:
    """Have `moves(case, before)` made just after call number `nth` of the step `where` names for `case` answers."""
    owner, step = where(case)
    answers = getattr(owner, step)
    raced = partial(moves, case, before)
    case.enterContext(patch.object(owner, step, _RacesPastTheCall(answers, nth, raced)))


def _records_a_successor(case: support.VerificationRecoveryCase, before: tuple) -> None:
    """Record a newer transaction in place of the captured one, bound to a review subject another road recorded."""
    state = case.gh.read_pinned_state(case.issue)
    pending = _record_state.read_pending_evidence(state)
    subject = {**before[0], "report_revision": before[0]["report_revision"] + 1}
    rebound = replace(pending.binding, target=replace(pending.binding.target, subject=subject))
    state.set(REVIEW_SUBJECT, subject)
    case.assertTrue(_record_state.record_pending_evidence(
        state, _record_state.mint_pending_evidence(state, git_support.ISSUE, rebound, pending.commands),
    ))
    case.gh.write_pinned_state(case.issue, state)


def _replacement(case: support.VerificationRecoveryCase) -> dict:
    """An attempt another road pinned in place of `case`'s: anchored on the landed head, nothing yet recorded for it."""
    return {
        readings.KEY_PENDING_PUSH: git_support.remote_head(case),
        readings.KEY_REWRITE_PR: git_support.PR_NUMBER,
        readings.KEY_REWRITE_STAGE: str(git_support.REVIEWING),
        readings.KEY_REWRITE_SHA: None,
        readings.KEY_REWRITE_BASE: None,
        readings.KEY_ANNOUNCED: None,
        readings.KEY_EVIDENCE_RECEIPT: None,
        readings.KEY_ANNOUNCED_EVENT: None,
        readings.KEY_RELABELLED: None,
    }


def _replaces_the_attempt(case: support.VerificationRecoveryCase, _before: tuple) -> None:
    """Pin another attempt in place of `case`'s, as another road's write would."""
    replaced = case.gh.read_pinned_state(case.issue)
    for key, recorded in _replacement(case).items():
        replaced.set(key, recorded)
    case.gh.write_pinned_state(case.issue, replaced)


# The steps a move is hung on, each beside the call it follows: the checkout's
# reading -- the recovery's second of which is the evidence step's last word,
# behind the captured run's proof -- the post of the artifact, and the
# settlement's re-read of it behind its proof.
_LAST_WORD = (lambda _case: (rewrite_facts, "_reads_the_checkout"), 2)
_POST = (lambda case: (case.gh, "publish_verification_artifact"), 1)
_REREAD = (lambda case: (case.gh, "reread_verification_artifact"), 1)
_COMMENT_READ = (lambda case: (case.gh, "read_pinned_state"), 1)

# What moves while the run is published and settled, beside what puts it back
# -- each handed the review subject and the issue body the comment and issue
# carried before -- and how many artifacts the run's receipt was posted under.
_MOVES = (
    (
        "the review subject, behind the evidence step's last word",
        partial(_after, *_LAST_WORD, _moves_the_subject),
        lambda case, before: _records_the_subject(case, before[0]),
        0,
    ),
    (
        "the review subject, as the artifact is posted",
        partial(_after, *_POST, _moves_the_subject),
        lambda case, before: _records_the_subject(case, before[0]),
        1,
    ),
    (
        "the review subject, as the artifact is posted, put back once the settlement's guard read it",
        partial(_after, *_POST, partial(_moves_the_subject, until_read=True)),
        lambda case, before: _records_the_subject(case, before[0]),
        1,
    ),
    (
        "the configured command, as the artifact is posted",
        partial(_after, *_POST, lambda case, _before: case.configures("echo another")),
        lambda case, _before: case.configures(support.CONFIGURED),
        1,
    ),
    (
        "the requirements, as the artifact is posted",
        partial(_after, *_POST, lambda case, _before: setattr(case.issue, _BODY, _EDITED_BODY)),
        lambda case, before: setattr(case.issue, _BODY, before[1]),
        1,
    ),
    (
        "the configured command, as the settlement re-reads the artifact",
        partial(_after, *_REREAD, lambda case, _before: case.configures("echo another")),
        lambda case, _before: case.configures(support.CONFIGURED),
        1,
    ),
    (
        "the requirements, as the settlement re-reads the artifact",
        partial(_after, *_REREAD, lambda case, _before: setattr(case.issue, _BODY, _EDITED_BODY)),
        lambda case, before: setattr(case.issue, _BODY, before[1]),
        1,
    ),
)

# Where the base advances while the run is published: as the artifact is
# posted, and as the settlement re-reads it behind its proof.
_ADVANCED = (
    ("as the artifact is posted", partial(_after, *_POST, lambda case, _before: support.advances_the_base_again(case))),
    (
        "as the settlement re-reads it",
        partial(_after, *_REREAD, lambda case, _before: support.advances_the_base_again(case)),
    ),
)

# Where another road puts a new attempt in place of the recovered one: ahead of
# the post, behind the evidence step's last word, and as the artifact is posted.
_REPLACED = (
    ("behind the evidence step's last word", partial(_after, *_LAST_WORD, _replaces_the_attempt), 0),
    ("as the artifact is posted", partial(_after, *_POST, _replaces_the_attempt), 1),
)


class SettlementMoveRecoveryTest(support.CapturedRunCase, unittest.TestCase):
    """A run something moved under while it was published or settled is abandoned, and no restoration revives it."""

    def test_a_move_while_settling_abandons(self) -> None:
        # The run is abandoned rather than settled, its artifact posted at
        # most once, and the head routed to the fresh reviewer by the same
        # recovery. Put back, the move revives nothing in a later recovery or
        # in the reconciliation.
        for move in _MOVES:
            with self.subTest(moved=move[0]):
                head, captured, before = self._recovers_beside(move[1])

                self._assert_routed_abandoned(head, captured, move[3])
                move[2](self, before)
                self.recovers()
                self.reconciles()
                self._assert_routed_abandoned(head, captured, move[3])

    def test_a_base_advanced_while_settling_abandons(self) -> None:
        # The base advances as the artifact is posted or re-read: the
        # settlement's proof, behind both, holds the head to the base its
        # replay was made onto, so the run is abandoned rather than settled
        # and the head held, nothing announced. The next recovery continues
        # it to the tick's rebase, which routes the next head with nothing
        # run, since no reviewer was handed it.
        for advanced in _ADVANCED:
            with self.subTest(advanced=advanced[0]):
                head, captured = self._recovers_beside(advanced[1])[:2]

                self.assert_abandoned(captured)
                self.assertEqual(self.posted(captured), [captured.commands])
                self.assertEqual(readings.pinned(self)[readings.KEY_PENDING_PUSH], self.anchor)
                self.assert_unannounced()
                self.recovers()
                rebased = git_support.remote_head(self)
                self.assert_abandoned(captured)
                self.assertEqual(
                    (support.announced(self), self.pushes.call_count, self.developer.call_count),
                    ([head, rebased], 1, 0),
                )
                self.assertEqual(
                    (readings.relabels(self), readings.attempt(readings.pinned(self))),
                    (readings.ROUTED, readings.RETIRED),
                )

    def test_a_successor_recorded_meanwhile_stands(self) -> None:
        # Another road records a newer transaction for the head -- bound to a
        # review subject it recorded -- in place of the run while the
        # settlement re-reads the artifact. The recovery holds rather than
        # prove the run's refusal over that successor or route past it: the
        # successor stands as recorded, the run in history as that road
        # retired it and the revision floor at the successor's revision, and
        # nothing is announced, relabelled, or cleared.
        captured = self._recovers_beside(partial(_after, *_REREAD, _records_a_successor))[1]

        pending, current, retired = readings.pinned_records(self)
        abandoned = (captured.receipt, readings.ABANDONED)
        self.assertEqual((pending.revision, current), (captured.revision + 1, None))
        self.assertEqual(readings.pinned(self)[readings.KEY_REVISION_FLOOR], pending.revision)
        self.assertEqual(retired, (*git_support.invalidated(self), abandoned))
        self.assertEqual(readings.pinned(self)[readings.KEY_PENDING_PUSH], self.anchor)
        self.assert_unannounced()

    def test_a_replacement_attempt_survives(self) -> None:
        # Another road pins a new attempt while the recovery publishes the
        # run: the post, the settlement, and the retirement are all decided on
        # the attempt the recovery read, so the run is neither settled nor
        # abandoned over the new one, and nothing is announced, relabelled, or
        # cleared -- the replacement stands as that road wrote it.
        for replaced in _REPLACED:
            with self.subTest(replaced=replaced[0]):
                captured = self._recovers_beside(replaced[1])[1]

                pinned = readings.pinned(self)
                self.assertEqual(readings.attempt(pinned), _replacement(self))
                self.assertEqual(readings.records(pinned)[:2], (captured, None))
                self.assertEqual(len(self.posted(captured)), replaced[2])
                self.assert_unannounced()

    def _recovers_beside(self, arms) -> tuple:
        """A fresh case's captured run, recovered with the move `arms` hangs on one of its steps.

        The head, the run, and the review subject and issue body recorded
        before the move. Every read of the issue through the client is a
        snapshot of it as it then stands, as GitHub hands one back, so an edit
        made after a reading is seen only by a reading taken after it.
        """
        self.setUp()
        head, captured = self.captures()
        before = (readings.pinned(self)[REVIEW_SUBJECT], self.issue.body)
        snapshots = patch.object(self.gh, "get_issue", lambda _number: copy(self.issue))
        self.enterContext(snapshots)
        arms(self, before)
        self.recovers()
        return head, captured, before

    def _assert_routed_abandoned(self, head: str, captured, posted: int) -> None:
        """`captured` abandoned with `posted` artifacts under its receipt, and `head` routed once to the reviewer."""
        self.assert_abandoned(captured)
        self.assert_recovered(head)
        self.assertEqual(len(self.posted(captured)), posted)


if __name__ == "__main__":
    unittest.main()
