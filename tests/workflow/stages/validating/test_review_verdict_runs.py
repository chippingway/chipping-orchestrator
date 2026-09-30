# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A verdict is acted on only through a run of its own round and subject, on the pull request that subject names.

Through `review_disposition`: a returned run naming another pull request than
the one its subject is on, or none, is refused before anything is minted,
persisted, or published, and a later tick finishes a waiting verdict only
through the run its caller rebuilt of the round, subject, and pull request the
record names. Anything else would post, push, or squash where nobody reviewed.
"""
from __future__ import annotations

import itertools
import unittest
from dataclasses import replace
from functools import partial
from unittest.mock import patch

from orchestrator.workflow.stages.validating import review_verdicts as _verdicts
from tests.workflow.stages.validating import (
    disposed_verdict_test_support as _disposed,
    review_verdict_readings as _read,
    review_verdict_test_support as _world,
)

UNDECLARED_REQUEST = f"{_world.REQUESTED}\n\nVERDICT: CHANGES_REQUESTED"

# The pull request another road could name, and the verdicts a run returns.
_OTHER_PR = _world.PR + 1

_VERDICTS = (_verdicts.CHANGES_REQUESTED, _verdicts.APPROVED)

# A reviewer's change request declaring nothing, and its approval over its own
# passing run.
_REPLIES = (UNDECLARED_REQUEST, _world.declared_run())

# What a returned run names in place of its subject's pull request: another,
# none, or that very one spelled as a float, which no record spells.
_NAMED_ELSEWHERE = (_OTHER_PR, None, float(_world.PR))


def _off_its_pull_request(pr_number, returned_run, *read):
    """The run `returned_run` builds from `read`, naming `pr_number` rather than its subject's pull request."""
    return replace(returned_run(*read), pr_number=pr_number)


def _over_another_subject(run):
    """`run`, rebuilt over a subject standing on a head nobody reviewed."""
    return replace(run, subject=replace(run.subject, commit=_world.OTHER_HEAD))


def _over_a_true_report_revision(run):
    """`run`, rebuilt over its own subject with the report's revision `1` spelled `True`."""
    report = replace(run.subject.report, report_revision=True)
    return replace(run, subject=replace(run.subject, report=report))


# How a later tick's caller can rebuild the run a waiting verdict was returned
# in, none of which is that run: of another round, over another subject, or
# naming another pull request or none -- or its own round, report revision, or
# pull request spelled as a value Python calls equal to it and no record
# spells that way, a boolean or a float.
_REBUILT_ELSEWHERE = (
    ("of another round", lambda run: replace(run, round_n=run.round_n + 1)),
    ("over another subject", _over_another_subject),
    ("on another pull request", lambda run: replace(run, pr_number=_OTHER_PR)),
    ("on no pull request", lambda run: replace(run, pr_number=None)),
    ("of round False", lambda run: replace(run, round_n=False)),
    ("of round 0.0", lambda run: replace(run, round_n=float(run.round_n))),
    ("over a report revision spelled True", _over_a_true_report_revision),
    ("on its pull request spelled as a float", lambda run: replace(run, pr_number=float(run.pr_number))),
)


class ForeignRunTest(_disposed.DisposedVerdictWorld, unittest.TestCase):
    """A verdict is acted on only through its own run."""

    def test_a_returned_run_elsewhere_is_refused(self) -> None:
        # A change request's feedback and fix, or an approval and its squash,
        # would go to another pull request than the one reviewed -- or to one
        # named by no whole number, as no record spells it: nothing is
        # written, posted, relabelled, or launched.
        for pr_number, message in itertools.product(_NAMED_ELSEWHERE, _REPLIES):
            with self.subTest(pr_number=pr_number, verdict=message.splitlines()[-1]):
                self.setUp()
                before = self.pinned()
                elsewhere = partial(_off_its_pull_request, pr_number, _world.returned_run)

                with patch.object(_world, "returned_run", elsewhere):
                    ran = self.returns(message, **_disposed.fixing())

                self.assertEqual(
                    (
                        self.pinned(),
                        self.github.posted_pr_comments,
                        ran[_world.RUN_AGENT].call_count,
                        self.github.label_history,
                    ),
                    (before, [], 0, []),
                )

    def test_a_waiting_verdict_needs_its_own_run(self) -> None:
        # Through its own run, a change request is handed to its developer
        # and an approval reaches `documenting`. Through any other, nothing is
        # posted, relabelled, launched, or written, and the verdict waits.
        for verdict in _VERDICTS:
            with self.subTest(verdict=verdict):
                self._finishes_through(verdict, None)
                self.assertEqual(
                    (bool(self.github.label_history), self.waiting()),
                    (True, None),
                )
        for (name, rebuilt), verdict in itertools.product(_REBUILT_ELSEWHERE, _VERDICTS):
            with self.subTest(name, verdict=verdict):
                before = self._finishes_through(verdict, rebuilt)

                self.assertEqual(
                    (
                        (self.pinned(), len(self.github.posted_pr_comments)),
                        self.github.posted_comments,
                        self.github.label_history,
                    ),
                    (before, [], []),
                )

    def _finishes_through(self, verdict: str, rebuilt) -> tuple:
        """Leave `verdict` waiting, and finish it through its run -- as `rebuilt`, where given; what stood before.

        What stood before is the pinned comment and the count of comments on
        the pull request, as the finishing tick found them.
        """
        self.setUp()
        run = _read.seeds_a_verdict(self, _read.settles_evidence(self), verdict)
        self.run = run if rebuilt is None else rebuilt(run)
        before = (self.pinned(), len(self.github.posted_pr_comments))
        requested = verdict == _verdicts.CHANGES_REQUESTED
        self.finishes(**(_disposed.fixing() if requested else _disposed.ON_THE_HEAD))
        return before


if __name__ == "__main__":
    unittest.main()
