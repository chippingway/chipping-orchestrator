# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A later tick's handoff takes the feedback post an earlier one made for the very request it hands over, and only it.

A post closes on a receipt naming the request it was posted for -- its round,
subject, and evidence claim -- so the same findings returned again over
another subject, the round reset, never take the earlier request's post,
which stands above the report and the evidence the later request was
reviewed over. A tick before receipts posted a request with none -- in its
findings concise, or, one persisted before findings were formatted, raw: such
a post, whose response was lost, is found in those words all the same and
anchored rather than posted twice, but only where it stands in the thread
behind everything the request was reviewed over, and is no post another
request's landed handoff already accounts for.

Of the line a post opens on, only the round is held to the request's: the
reviewer it names and the round cap it counts to are configuration, so a post
whose response was lost, or one left unanchored, is found across a restart
that configured either otherwise, and never posted twice.

What a found post is held to beyond its words -- its author, the thread read
whole -- is in `test_review_handoff_commits.py` and `test_review_handoffs.py`.
"""
from __future__ import annotations

import contextlib
import operator
import unittest
from functools import partial
from itertools import product
from unittest.mock import patch

from orchestrator import config
from orchestrator.workflow.engine import comments as _comments, verification_settlement_state as _settlement_state
from orchestrator.workflow.stages.validating import feedback_posts as _feedback_posts
from tests.workflow.fixtures import LABEL_FIXING
from tests.workflow.stages.validating import (
    disposed_verdict_test_support as _disposed,
    raw_feedback_test_support as _raw,
    resumed_verdict_test_support as _resumed,
    review_handoff_test_support as _support,
    review_verdict_readings as _read,
    review_verdict_test_support as _world,
    review_write_test_support as _roads,
)

PR_COMMENT = "pr_comment"

SET_LABEL = "set_workflow_label"


def _loses_the_post(case, reply: str) -> None:
    """The tick whose reviewer returned `reply`, its feedback post taken with its response lost."""
    lost = RuntimeError("response lost")
    loses = _support.RefusesOnce(case.github.pr_comment, _support.FEEDBACK_NOTICE, lands=True, answers=lost)
    with patch.object(case.github, PR_COMMENT, loses):
        case.returns(reply, **_disposed.fixing())


def _posts_unreceipted(case, findings: str) -> None:
    """A feedback post of `findings` in the review's first round, as a tick before posts carried a receipt made it."""
    words = _feedback_posts.posted(0, findings)
    case.github.pr_comment(_world.PR, _comments._with_orch_marker(words))


def _anchors_it(case) -> None:
    """The comment ledger of `case`'s issue accounting for every feedback post, as another request's handoff left it."""
    posted = [said.id for said in case.feedback_posts()]
    _roads.Writes({"orchestrator_comment_ids": posted})(case)


def _returns_again_raw(case) -> None:
    """`_returns_again`, the request it leaves waiting rewritten as a tick before formatting persisted it: raw."""
    _returns_again(case)
    waiting = case.github.read_pinned_state(case.issue).get(_world.RETURNED_VERDICT)
    _roads.Writes({_world.RETURNED_VERDICT: {**waiting, "feedback": _raw.RAW_FAILURE}})(case)


def _returns_again(case) -> int:
    """The same findings returned over another subject, the round reset, their post refused; the evidence's comment.

    A later report is settled, the round reset, and the change request
    returned again in the very words over the subject that report makes,
    claiming evidence settled for it; its tick's feedback post is refused, so
    nothing is handed over. The answer is the comment that evidence's
    artifact stands at on the pull request.
    """
    _read.settles_a_later_report(case)
    _roads.Writes({"review_round": 0})(case)
    decision = case.seeds(evidence=True)
    refuses = _support.RefusesOnce(case.github.pr_comment, _support.FEEDBACK_NOTICE, lands=False)
    with patch.object(case.github, PR_COMMENT, refuses):
        case.hands_over(decision)
    return _settlement_state.read_current_evidence(case.github.read_pinned_state(case.issue)).comment_id


# The pinned comment remembered right behind the relabel to `workflow:fixing`.
_REMEMBERS_BEHIND_THE_RELABEL = partial(
    _world.AnotherRoadBehind,
    request=SET_LABEL,
    when=partial(operator.eq, LABEL_FIXING),
    road=_support.HandoffWorld.remembers,
)

# A request a tick persisted -- with its findings raw, or concise -- and how a
# tick before this one left its feedback post: taken, its response lost, and
# receipted -- raw, or concise; or posted before posts carried a receipt --
# raw, or concise as a recovery or the live round formatted it -- and left
# unanchored, its own tick's post refused. Then the findings that post quotes.
_UNANCHORED = (
    (
        "persisted raw, posted raw and receipted, its response lost",
        partial(_raw.leaves_raw, leaves=_loses_the_post),
        None,
        _raw.RAW_FAILURE,
    ),
    (
        "persisted concise, posted receipted, its response lost",
        partial(_loses_the_post, reply=_world.FAILED_REQUEST),
        None,
        _world.CONCISE_FAILURE,
    ),
    (
        "persisted raw, posted raw with no receipt",
        partial(_raw.leaves_raw, leaves=_resumed.refuses_the_post),
        _raw.RAW_FAILURE,
        _raw.RAW_FAILURE,
    ),
    (
        "persisted raw, posted concise with no receipt",
        partial(_raw.leaves_raw, leaves=_resumed.refuses_the_post),
        _world.CONCISE_FAILURE,
        _world.CONCISE_FAILURE,
    ),
    (
        "persisted concise, posted with no receipt",
        partial(_resumed.refuses_the_post, message=_world.FAILED_REQUEST),
        _world.CONCISE_FAILURE,
        _world.CONCISE_FAILURE,
    ),
)

# What a restart between a feedback post and the tick finishing its request
# configures: nothing new, a higher round cap, or another reviewer -- each but
# the first rewording the line the post opens on.
_RESTARTS = (
    ("as posted", contextlib.nullcontext),
    ("the round cap raised", partial(patch.object, config, "MAX_REVIEW_ROUNDS", config.MAX_REVIEW_ROUNDS + 1)),
    ("another reviewer named", partial(patch.object, config, "REVIEW_AGENT", "another-reviewer")),
)

# A post with no receipt in the request's words -- concise, or raw for a
# request persisted raw -- that is another request's: one made before a later
# report, fresh evidence, and the round reset; or one made over the very
# subject the request stands on that another request's landed handoff
# accounts for in the comment ledger.
_ANOTHER_REQUESTS = (
    ("concise, above a later report and fresh evidence", _world.REQUESTED, _returns_again),
    ("raw, above a later report and fresh evidence", _raw.RAW_FAILURE, _returns_again_raw),
    ("concise, accounted for by another request's handoff", _world.REQUESTED, _anchors_it),
)


class AnotherRequestTest(_support.HandoffWorld, unittest.TestCase):
    """A post made for one request is never taken for another returned in the same words."""

    def test_another_requests_post_is_never_taken(self) -> None:
        # A request handed over beside its post; then a later report, the
        # round reset, and the same findings returned over that subject with
        # fresh evidence, their post refused. A later tick does not take the
        # first request's post, which stands above that evidence: it posts
        # this request's own and hands it over beside that post.
        self.hands_over_unlaunched()
        evidence = _returns_again(self)
        relabel = _world.AnotherRoadBehind(
            self, SET_LABEL, partial(operator.eq, LABEL_FIXING), _support.HandoffWorld.remembers,
        )

        with relabel.patched():
            ran = self.hands_over()

        posted = [said.id for said in self.feedback_posts()]
        anchor = self.remembered[_support.ANCHOR]
        self.assertEqual(
            (ran.call_count, len(posted), anchor, anchor > evidence),
            (1, 2, posted[-1], True),
        )

    def test_an_unreceipted_post_is_bound_too(self) -> None:
        # A post with no receipt, in the very words the request posts, as a
        # tick before receipts made it for another request: standing above a
        # later report and fresh evidence the request was reviewed over, or
        # accounted for in the comment ledger by that request's landed
        # handoff. A later tick does not take it: it posts this request's own
        # and hands the request over beside that post.
        for name, findings, meanwhile in _ANOTHER_REQUESTS:
            with self.subTest(name):
                self.setUp()
                self.seeds()
                _posts_unreceipted(self, findings)
                meanwhile(self)

                with _REMEMBERS_BEHIND_THE_RELABEL(self).patched():
                    ran = self.hands_over()

                posted = [said.id for said in self.feedback_posts()]
                self.assertEqual(
                    (ran.call_count, len(posted), self.remembered[_support.ANCHOR]),
                    (1, 2, posted[-1]),
                )


class LegacyPostTest(_disposed.DisposedVerdictWorld, unittest.TestCase):
    """A request is found in the words a tick before this one posted it in, and never posted twice."""

    def test_a_legacy_post_is_found(self) -> None:
        # The request was persisted with its findings raw or concise, and its
        # feedback post is on the pull request with no id anchored: receipted,
        # its response lost, or raw or concise with no receipt at all, behind
        # the report and the evidence it was reviewed over -- and a restart
        # may since have configured another reviewer or round cap than the
        # line the post opens on names. The tick finishing it posts nothing
        # again: it hands the request over beside that post, and resumes the
        # one developer on the concise findings.
        for (name, *left), (restart, reconfigures) in product(_UNANCHORED, _RESTARTS):
            with self.subTest(name, restart=restart):
                self.setUp()
                self._finds_it(reconfigures, left)

    def _finds_it(self, reconfigures, left) -> None:
        """Leave the post `left` describes, and finish its request under what `reconfigures` sets; it is found."""
        leaves, unreceipted, quoted = left
        leaves(self)
        if unreceipted is not None:
            _posts_unreceipted(self, unreceipted)

        with reconfigures():
            ran = self.finishes(**_disposed.fixing())[_world.RUN_AGENT]

        self.assertEqual(
            (
                ran.call_count,
                _raw.handed(self, ran.call_args.args[1], _world.CONCISE_FAILURE),
                self.waiting(),
            ),
            (1, ((quoted,), True), None),
        )


if __name__ == "__main__":
    unittest.main()
