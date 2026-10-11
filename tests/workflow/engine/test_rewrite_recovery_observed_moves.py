# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A movement the settlement of a captured run read, put back before anything reads it again, still abandons the run.

A finish recorded its run for the landed head and died posting its artifact,
so the recovery publishes and settles it with the attempt still standing. As
the artifact is posted, another hand moves something the run is bound to, and
puts it back the moment the settlement has read it: the base advanced past the
head, restored right behind the anchored proof that read it gone elsewhere;
the issue's requirements edited, restored right behind the proof's hash of
them; or the artifact edited, restored right behind the settlement's re-read
of it -- each of the last two with the pinned comment going unanswered once on
the read behind them. The settlement keeps every refusal as it reads it, so
none is lost behind a reading that came after, and the recovery abandons the
run over that movement however the world reads by its last word: the run goes
into history whole, the revision floor stays at its revision, and it is never
settled -- by this recovery or the next. A base read gone elsewhere also holds
that recovery; the head goes to the fresh reviewer once it is routed. Nothing
runs again, nothing is pushed, and no developer is launched.
"""
from __future__ import annotations

import unittest
from functools import partial
from unittest.mock import patch

from orchestrator.git.base_sync import rewrite_facts
from orchestrator.workflow.engine import verification_subject
from tests.workflow.engine import (
    rewrite_finish_readings as readings,
    rewrite_verification_recovery_support as support,
)
from tests.workflow.interleaving import _RacesPastTheCall

_EDITED_BODY = "Also cover a moved base."

_BASE = "refs/heads/main"


def _hangs(case: support.CapturedRunCase, owner, step: str, raced) -> None:
    """Have `raced` made once, just after the next call of `owner`'s `step` answers."""
    races = _RacesPastTheCall(getattr(owner, step), 1, raced)
    case.enterContext(patch.object(owner, step, races))


def _puts_back_unread(case: support.CapturedRunCase, puts_back) -> None:
    """Make `puts_back`, then have the next read of `case`'s pinned comment go unanswered once."""
    puts_back()
    case.gh.pinned_failures.unanswered_once.add(case.issue.number)


def _advances_until_proved(case: support.CapturedRunCase, tip: str) -> None:
    """Advance the base past the head, and put it back on `tip` once the next reading of where it stands answers.

    Put back by the push that moved it, forced, so the remote's base and the
    checkout's own reading of it both stand on `tip` again.
    """
    support.advances_the_base_again(case)
    pushed = f"{tip}:{_BASE}"
    restores = partial(case._git, "push", "--quiet", "--force", "origin", pushed, cwd=case._work)
    _hangs(case, rewrite_facts, "_standing_on_the_remote_base", restores)


def _edits_the_requirements(case: support.CapturedRunCase) -> None:
    """Edit the issue body, and put it back once the next hash of its requirements answers."""
    restores = partial(setattr, case.issue, "body", case.issue.body)
    case.issue.body = _EDITED_BODY
    _hangs(case, verification_subject, "requirements_verdict", partial(_puts_back_unread, case, restores))


def _edits_the_artifact(case: support.CapturedRunCase) -> None:
    """Edit the artifact just posted out of its format, and put it back once the next re-read of it answers."""
    posted = case.pull_request.issue_comments[-1]
    restores = partial(setattr, posted, "body", posted.body)
    posted.body = f"{posted.body}\nEdited by hand."
    _hangs(case, case.gh, "reread_verification_artifact", partial(_puts_back_unread, case, restores))


# What moves as the artifact is posted, put back once the settlement read it,
# with the comment unanswered once behind it.
_REFUSED = (("the requirements", _edits_the_requirements), ("the artifact", _edits_the_artifact))


class ObservedMoveRecoveryTest(support.CapturedRunCase, unittest.TestCase):
    """A refusal the settlement read abandons the run, put back before the recovery's last word or not."""

    def test_a_base_put_back_still_abandons(self) -> None:
        # The anchored proof reads the base gone elsewhere, and the base is
        # back before anything reads it again: the run is abandoned over that
        # reading and the route held, nothing announced. The next recovery
        # routes the head to the fresh reviewer, settling nothing.
        head, captured = self.captures()
        tip = self._git("rev-parse", _BASE, cwd=self._remote).strip()
        _hangs(self, self.gh, support.POST, partial(_advances_until_proved, self, tip))

        self.recovers()

        self.assert_abandoned(captured)
        self.assertEqual(readings.pinned(self)[readings.KEY_PENDING_PUSH], self.anchor)
        self.assert_unannounced()
        self.recovers()
        self.assert_abandoned(captured)
        self.assert_recovered(head)

    def test_a_refusal_survives_an_unread_comment(self) -> None:
        # The settlement's proof refuses the run, the move is put back, and
        # the comment read behind the proof goes unanswered: the refusal was
        # kept as it was read, so the run is abandoned over it -- its
        # revision and binding in history, the floor unchanged -- and the head
        # routed to the fresh reviewer, never settled.
        for refused, arms in _REFUSED:
            with self.subTest(refused=refused):
                self.setUp()
                head, captured = self.captures()
                _hangs(self, self.gh, support.POST, partial(arms, self))

                self.recovers()

                self.assert_abandoned(captured)
                self.assertEqual(readings.pinned(self)[readings.KEY_REVISION_FLOOR], captured.revision)
                self.assert_recovered(head)


if __name__ == "__main__":
    unittest.main()
