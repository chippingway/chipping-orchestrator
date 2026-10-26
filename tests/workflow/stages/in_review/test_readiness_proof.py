# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The ready ping is taken only over current passing evidence, proved whole at the ping on either route.

A head qualified for the ping -- by the final-docs pass stamped on it, or by a
GitHub approval of it -- is announced only once the issue's current
verification evidence proves current there: the configured repository, the
pull request on its branch and standing on the head, the remote branch level
with it, the tested tree, the configured verification context, the applicable
review subject, the latest revision with its handoff describing it, and its
artifact still the one that settled. And it has to pass: every command
exiting 0, at least one of them, with the configured suite among them.

Anything of that moved -- before the tick, or while the gate asks GitHub about
the pull request -- pings nobody and writes nothing, and so does evidence that
is missing, failed, leaves the configured suite out, or records that nothing
ran, under any configuration. A reading the proof needs that stops answering
holds the ping the same way, and the ping follows once it answers. A ping an
earlier tick armed and never posted takes the same proof before it goes out.
And the proof is taken once more behind the ping's checkpoints, with the
pinned comment and then the pull request read afresh behind it, the pull
request's state and head the last thing asked before any post: a push, a
report edit, the artifact deleted, or a hand edit of the record the ping rests
on behind the ping's arming or behind the reading its settlement is prepared
over, and a push behind the comment's last reading -- on a first attempt or a
recovered one -- still pings nobody, with the arming left standing and nothing
else written; so does the pull request merged or closed while that last proof
re-reads the artifact, which leaves its head where it was and is seen by its
state read last, and a verification configuration moved behind the last
proof's own context check, which its last word sees on every route.

A final docs pass's completion is a route of its own: it qualifies exactly the
head it completed on, and the ping over it waits on that completion's whole
proof instead -- every binding above held over the approval's own evidence
retained on the unchanged head, a run of the docs commit, or, under an empty
configuration, nothing but the tree no run tested. Each pings once with the
approval, its claim, and its report left as they were. A plain docs stamp on
a docs commit no completion names, a damaged completion, a run that failed or
is still owed, the approval's claim gone, the suite configured since a pass
that ran under none, a push past the final head, and a docs commit that does
not descend from the head the pass was entered on each ping nobody, and so
does everything above that lands while the gate decides, behind the
checkpoints, on a recovered attempt, or behind the proof's last reading. A
reply beside a completion is still feedback, and a standing veto still holds
the ping until it is answered.
"""
from __future__ import annotations

import unittest
from functools import partial
from itertools import product
from types import MappingProxyType
from unittest.mock import MagicMock, patch

from orchestrator import config
from orchestrator.github.verification_evidence import VerifiedCommand
from orchestrator.workflow.state import WorkflowLabel
from tests.workflow.git_owners import seam_patch
from tests.workflow.stages.in_review import (
    completion_test_support as completion,
    readiness_test_support as support,
    ready_ping_test_support as ping,
)

# A repository other than the one the evidence was recorded against: the one the
# client is configured for, or the one a fork's head is built from.
ELSEWHERE = "octo/elsewhere"

# The client request the gate asks right before it decides the head is
# approved, which a late change lands behind.
_VETO = "pr_has_changes_requested"

# A command the configuration does not list.
_UNCONFIGURED = "uv run ruff check"

# Every route that qualifies a head for the ping: a docs stamp, a GitHub
# approval, and a final docs pass completed each way it can.
_ROUTES = (*support.ROUTES, *completion.KINDS)

# What several windows below land: a push, the issue edited, and the
# approval's own artifact deleted from behind a run of the docs commit, where
# it is no longer the current evidence's.
_PUSHED = ("a push", support.EvidenceMoves.pushes)

_ISSUE_EDIT = ("an issue edit", support.EvidenceMoves.edits_the_issue)

_APPROVALS_ARTIFACT = ("the approval's artifact deleted", completion.WorldMoves.deletes_the_approvals_artifact)

# A tree the checkout reads as that no evidence was gathered on.
_ANOTHER_TREE = ("another tree", None, {"checkout_tree": support.OTHER_TREE})

# Each thing the evidence is bound to, moved before the tick, beside the tick's
# own readings where those are what moved: the configured repository, a fork's
# head, another branch, a push, a remote branch standing past the head, another
# tree, the verification context, the review subject the evidence answers for,
# a later run recorded, a handoff that no longer describes the record, and the
# artifact edited or deleted.
_BINDINGS = (
    ("another repository", lambda case: setattr(case.github, "_repo_slug", ELSEWHERE), {}),
    ("a fork's head", lambda case: setattr(case.pull_request.head.repo, "full_name", ELSEWHERE), {}),
    ("another branch", lambda case: setattr(case.pull_request.head, "ref", "another-branch"), {}),
    (*_PUSHED, {}),
    ("the branch past the head", None, {"fetched_branch_tip": support.PUSHED}),
    _ANOTHER_TREE,
    ("a moved context", support.RecordEdits.moves_the_context, {}),
    ("no review subject", partial(support.RecordEdits.restates, review_returned_subject=None), {}),
    ("a later run recorded", support.RecordEdits.records_a_later_run, {}),
    ("no handoff", partial(support.RecordEdits.restates, verification_evidence_handoff=None), {}),
    ("an edited artifact", support.EvidenceMoves.edits_the_artifact, {}),
    ("a deleted artifact", support.EvidenceMoves.deletes_the_artifact, {}),
)

# Each of those on every route -- save the tested tree under no configuration,
# where the pass tested nothing for a tree to answer to.
_MOVED_BINDINGS = (
    *product((*support.ROUTES, completion.RETAINED, completion.EXECUTED), _BINDINGS),
    *((completion.UNCONFIGURED, moved) for moved in _BINDINGS if moved is not _ANOTHER_TREE),
)

# What refuses a completion before the tick, beside how its pass completed
# and anything that seeds differently: a plain docs stamp on a docs commit no
# completion names, on either changed head; a completion damaged beside a docs
# stamp on a head the approval's own evidence answers for, which the ordinary
# proof would ping; a run of the docs commit that failed, or is still owed;
# the approval's claim gone; the suite configured since a pass that ran under
# none; a push past the final head that GitHub approves; and a docs commit
# that does not descend from the head the pass was entered on.
_A_PLAIN_STAMP = (completion.CompletionEdits.drops_the_completion, completion.CompletionEdits.stamps_the_docs)

_COMPLETION_REFUSALS = (
    ("a plain docs stamp", completion.EXECUTED, {}, _A_PLAIN_STAMP),
    ("a plain docs stamp", completion.UNCONFIGURED, {}, _A_PLAIN_STAMP),
    (
        "a damaged completion", completion.RETAINED, {},
        (completion.CompletionEdits.stamps_the_docs, completion.CompletionEdits.damages_the_completion),
    ),
    ("a failed run", completion.EXECUTED, {"run": completion.FAILED_RUN}, ()),
    ("a run still owed", completion.EXECUTED, {"settled": False}, ()),
    (
        "the approval's claim gone", completion.EXECUTED, {},
        (partial(support.RecordEdits.restates, **{completion.APPROVED_EVIDENCE: None}),),
    ),
    ("the suite configured since", completion.UNCONFIGURED, {}, (completion.WorldMoves.configures_the_suite,)),
    ("a push approved on GitHub", completion.EXECUTED, {}, (completion.WorldMoves.pushes_approved_on_github,)),
    ("no descent", completion.UNCONFIGURED, {}, (completion.WorldMoves.descends_nowhere,)),
)

# Evidence nothing may be announced over, by what it carries: nothing recorded
# at all, a failed command, a passing run leaving the configured suite out, and
# a record that nothing ran.
_UNPASSING = (
    ("no evidence", None),
    ("a failed command", (VerifiedCommand(support.SUITE, 1, support.FAILED_OUTPUT),)),
    ("the suite left out", (VerifiedCommand(_UNCONFIGURED, 0, "ok"),)),
    ("nothing run", ()),
)

# Each of those on either route, with the approval's claim naming the evidence
# and with no claim recorded at all.
_UNPASSING_CASES = tuple(product(support.ROUTES, _UNPASSING, (True, False)))

# What lands while the gate asks GitHub about the pull request: a push, the
# issue edited, the report edited, the artifact edited or deleted, and the
# verification configuration changed.
_LATE = (
    _PUSHED,
    _ISSUE_EDIT,
    ("a report edit", support.EvidenceMoves.edits_the_report),
    ("an artifact edit", support.EvidenceMoves.edits_the_artifact),
    ("an artifact deletion", support.EvidenceMoves.deletes_the_artifact),
    ("a moved context", support.RecordEdits.moves_the_context),
)

# Each of those on every route, and the approval's artifact deleted from behind
# a run of the docs commit.
_LATE_CHANGES = (*product(_ROUTES, _LATE), (completion.EXECUTED, _APPROVALS_ARTIFACT))

# What lands behind the lineage, the last reading of a completion's proof, so
# that only the last word behind it sees it: the run's artifact or the
# approval's deleted, the issue edited, or a push.
_BEHIND_THE_LINEAGE = (
    (completion.EXECUTED, ("the run's artifact deleted", support.EvidenceMoves.deletes_the_artifact)),
    (completion.EXECUTED, _APPROVALS_ARTIFACT),
    (completion.EXECUTED, _ISSUE_EDIT),
    (completion.UNCONFIGURED, _APPROVALS_ARTIFACT),
    (completion.UNCONFIGURED, _PUSHED),
)

# A reply a human writes beside a completed pass.
_REPLY = "one more thing before this merges"

# A reading that stops answering while the gate asks GitHub about the pull
# request, by the client request that then raises -- None for the pull
# request's thread, which a re-read of the artifact reports as unconfirmed --
# or by the tick's own git readings: a branch that would not compare, a tree
# read answering nothing, and git not started at all.
_UNREAD_REQUESTS = (None, "get_issue", "get_pr", "reread_verification_artifact")

_UNREAD_READINGS = (
    ("an uncompared branch", {"branch_divergence_readable": False}),
    ("an unread tree", {"checkout_tree": ""}),
    ("an unstarted git", {"checkout_tree": None}),
)

# What lands behind one of the ping's checkpoints, on every route: a push, a
# report edit, the artifact deleted, a maintainer's hand edit of the record
# the ping rests on -- a completion, or else the approval -- or a report debt
# recorded by hand, as owed or as an undeliverable report's park, behind the
# arming or behind the reading the settlement is prepared over -- the first
# patching the client's edit, the second its read of the pinned comment. The
# proof behind that reading reads the records in hand, so only the comment
# read afresh behind it sees a hand edit.
_CHECKPOINT_MOVES = (
    _PUSHED,
    ("a report edit", support.EvidenceMoves.edits_the_report),
    ("an artifact deletion", support.EvidenceMoves.deletes_the_artifact),
    ("a hand edit", completion.CompletionEdits.edits_by_hand),
    ("a report owed", partial(support.RecordEdits.restates, developer_report_owed=True)),
    ("an undeliverable park", partial(support.RecordEdits.restates, park_reason="report_undeliverable")),
)

_CHECKPOINTS = (
    ("arming", "edit_pinned_state", support.BehindTheArming),
    ("preparation", "read_pinned_state", support.BehindThePreparation),
)

# A first attempt -- seeded and armed on the tick -- and a recovered one,
# armed by an earlier tick.
_ATTEMPTS = (("first", completion._CompletionFixture.seeded_on), ("recovered", completion._CompletionFixture.armed))

# A merge or a close landing behind the last proof's first artifact re-read, on
# every route and either attempt; and the terminal label each leaves.
_LATE_ENDS = tuple(product(_ROUTES, (True, False), _ATTEMPTS))

_ENDED = MappingProxyType({True: WorkflowLabel.DONE, False: WorkflowLabel.REJECTED})

_ENDS = MappingProxyType({
    merged: partial(support.EvidenceMoves.ends_behind_the_next_artifact_read, merged=merged)
    for merged in (True, False)
})

# The window behind the reading the settlement is prepared over, and the one
# behind the comment read afresh behind the last proof.
_PREPARATION = ("read_pinned_state", support.BehindThePreparation)

_REREADING = ("read_pinned_state", partial(support.BehindThePreparation, nth=2))

_BEHIND_THE_CHECKPOINTS = tuple(
    (route, f"{moved} behind the {checkpoint[0]}", checkpoint[1:], move)
    for route, checkpoint, (moved, move) in product(_ROUTES, _CHECKPOINTS, _CHECKPOINT_MOVES)
)


class _DuringTheVeto:
    """The gate's veto request answered with no veto, `move` made on the case while GitHub answered it."""

    def __init__(self, case, move) -> None:
        self._case = case
        self._move = move

    def __call__(self, *_asked, **_options) -> bool:
        self._move(self._case)
        return False


class _Unanswered:
    """The client request `request` raising once stopped, until the case `answers` it -- the PR's thread, for None."""

    def __init__(self, request: str | None) -> None:
        self._request = request
        self._refused = None

    def __call__(self, case) -> None:
        if self._request is None:
            case.github.report_failures.unreadable.add(ping.PR)
            return
        unanswered = MagicMock(side_effect=RuntimeError("no answer"))
        self._refused = patch.object(case.github, self._request, unanswered)
        self._refused.start()

    def answers(self, case) -> None:
        """Answer the request again, as GitHub does once it recovers."""
        case.github.report_failures.unreadable.discard(ping.PR)
        if self._refused is not None:
            self._refused.stop()


def _unpassing(commands: tuple | None, *, claimed: bool):
    """The move leaving the current evidence carrying `commands` -- or none at all, for None -- `claimed` or not."""
    if commands is None:
        return partial(support.RecordEdits.drops_the_evidence, claimed=claimed)
    return partial(support.RecordEdits.rewrites_the_evidence, commands=commands, claimed=claimed)


class ReadinessProofTest(completion._CompletionFixture, unittest.TestCase):
    """What the ping needs of the evidence on every route, and that it pings nobody where that is not there."""

    def test_passing_evidence_pings_on_every_route(self) -> None:
        # Current, passing, and covering the configured suite -- or, for a
        # completion, every link it names proved: the head is pinged once,
        # armed and recorded, with no relabel and the approval, its claim, and
        # its report exactly as they were -- on a docs commit, still the
        # implementation's report about the approved commit -- and a quiet
        # tick after says nothing.
        for route in _ROUTES:
            with self.subTest(route):
                self.seeded_on(route)
                kept = self.approval_records()

                self.tick()

                self.assert_settled()
                self.assertEqual(self.approval_records(), kept)
                self.assertEqual(self.github.label_history, [])
                self.doCleanups()
                self.setUp()

    def test_a_moved_binding_withholds(self) -> None:
        for route, (name, moves, readings) in _MOVED_BINDINGS:
            with self.subTest(route=route, moved=name):
                self.withheld_over(route, moves, **readings)

    def test_a_refused_completion_withholds(self) -> None:
        for name, kind, options, moves in _COMPLETION_REFUSALS:
            with self.subTest(name, kind=kind):
                self.withheld_after(kind, moves, **options)

    def test_a_veto_holds_a_completion(self) -> None:
        # A standing change request on the final head pings nobody and writes
        # nothing; once it is withdrawn the head is pinged once.
        self.completed(completion.UNCONFIGURED)
        self.pull_request.changes_requested = True
        before = self.standing()
        self.tick()
        self.assert_withheld(before)
        self.pull_request.changes_requested = False

        self.tick()

        self.assert_settled()

    def test_a_reply_beside_a_completion_is_feedback(self) -> None:
        # A human's reply on the thread goes to `fixing`, pinging nobody.
        self.completed(completion.EXECUTED)
        reply_id = self.replies(_REPLY)

        self.tick()

        self.assertEqual(self.github.label_history, [(ping.ISSUE, "workflow:fixing")])
        self.assertEqual(self.pinned()["pending_fix_issue_ids"], [reply_id])
        self.assertEqual(self.pings(), [])

    def test_unpassing_evidence_withholds(self) -> None:
        # The record and its artifact each describe the other, so the evidence
        # proves current, and what its commands say is what refuses it --
        # whether the approval's claim names it, or the approval was never
        # held to any evidence at all.
        for route, (name, commands), claimed in _UNPASSING_CASES:
            with self.subTest(route=route, evidence=name, claimed=claimed):
                self.withheld_over(route, _unpassing(commands, claimed=claimed))

    def test_nothing_run_never_passes_unconfigured(self) -> None:
        # With no `VERIFY_COMMANDS` configured, a record that nothing ran
        # still covers the configuration -- and is still no evidence that
        # anything passed.
        for route, claimed in product(support.ROUTES, (True, False)):
            with self.subTest(route=route, claimed=claimed):
                self.enterContext(patch.object(config, "VERIFY_COMMANDS", ()))
                self.withheld_over(route, _unpassing((), claimed=claimed))


class LateReadinessTest(completion._CompletionFixture, unittest.TestCase):
    """What lands, or stops answering, while the gate decides, and a ping an earlier tick armed."""

    def test_a_late_change_withholds(self) -> None:
        # Each lands while GitHub answers the veto request, behind the head
        # the gate read and the drift and hand-back checks before it.
        for route, (name, move) in _LATE_CHANGES:
            with self.subTest(route=route, moved=name):
                self.seeded_on(route)
                before = self.standing()
                with patch.object(self.github, _VETO, _DuringTheVeto(self, move)):
                    self.tick()
                self.assert_withheld(before)
                self.doCleanups()
                self.setUp()

    def test_an_unread_request_holds(self) -> None:
        # Nothing is pinged or written while the request does not answer, and
        # the ping follows once it does.
        for route, request in product(_ROUTES, _UNREAD_REQUESTS):
            with self.subTest(route=route, unread=request or "the thread"):
                unanswered = _Unanswered(request)
                self._held_over(route, _DuringTheVeto(self, unanswered))
                unanswered.answers(self)
                self._pinged_once_answered()

    def test_an_unread_git_reading_holds(self) -> None:
        # A branch that would not compare, a tree read answering nothing, or
        # git not started at all: held, and pinged once git answers.
        unstarted = MagicMock(side_effect=OSError("git was not started"))
        for route, (name, readings) in product(support.ROUTES, _UNREAD_READINGS):
            with self.subTest(route=route, unread=name), seam_patch("_tree_sha", unstarted):
                self._held_over(route, MagicMock(return_value=False), **readings)
            self._pinged_once_answered()

    def test_a_move_behind_the_lineage_withholds(self) -> None:
        # A completion's whole proof has proved by the time it reads the
        # lineage, so only the last word behind it -- the evidence the
        # completion rests on, the report, the requirements, and the head --
        # sees what lands there.
        for kind, (name, move) in _BEHIND_THE_LINEAGE:
            with self.subTest(kind=kind, moved=name):
                behind = partial(completion.WorldMoves.behind_the_lineage, move=move)
                self.withheld_after(kind, (behind,))

    def test_a_late_context_withholds(self) -> None:
        # The verification configuration moves behind the last proof's report
        # re-read, past that proof's own context check: only its last word --
        # the evidence the approval, or the completion, rests on -- sees it,
        # so on every route nothing is posted and the arming stands.
        for route in _ROUTES:
            with self.subTest(route):
                self.seeded_on(route)
                head = self.pull_request.head.sha
                self.behind_the_armed_report_read(support.RecordEdits.moves_the_context)

                self.tick()

                standing = self.standing()
                self.assertEqual(standing[:2], (0, None))
                self.assertEqual(standing[2]["sha"], head)
                self.doCleanups()
                self.setUp()

    def _held_over(self, route: str, veto, **readings) -> None:
        """Seed `route` and tick with `veto` answering the veto request, over `readings`: nothing pinged or written."""
        self.seeded_on(route)
        before = self.standing()
        with patch.object(self.github, _VETO, veto):
            self.tick(**readings)
        self.assert_withheld(before)

    def _pinged_once_answered(self) -> None:
        """With every reading answering again, the next tick pings once; the case is then set up afresh."""
        self.tick()
        self.assert_settled()
        self.doCleanups()
        self.setUp()


class CheckpointReadinessTest(completion._CompletionFixture, unittest.TestCase):
    """The proof taken once more behind the ping's checkpoints, the last thing asked before the post."""

    def test_a_move_behind_a_checkpoint_withholds(self) -> None:
        # A first attempt: the arming lands -- the one write the tick makes,
        # with no relabel -- and the move behind it, or behind the
        # settlement's reading, is seen by the proof taken behind that
        # reading, or, for a hand edit, by the settlement's preparation or
        # the comment read afresh behind the proof. Nothing is posted or
        # recorded as pinged, and the tick after, reading the thread without
        # the ping, answers the move rather than pinging: a report edit, a
        # respelled approval, or a report owed goes back for review, and a
        # push, a deleted artifact, or a damaged completion is announced over
        # by nobody.
        for route, name, window, move in _BEHIND_THE_CHECKPOINTS:
            with self.subTest(route=route, moved=name):
                self.seeded_on(route)
                armed = self._armed_behind(window, move)
                self.tick()

                self.assertEqual(armed, (0, None, True, 1, ()))
                self.assertEqual(self.standing()[:2], (0, None))
                self.doCleanups()
                self.setUp()

    def test_a_recovered_preparation_withholds(self) -> None:
        # A recovered attempt: the arming an earlier tick landed stands, the
        # thread reads without the ping, and the move lands behind the reading
        # the settlement is prepared over. Nothing is posted or written.
        for route, (name, move) in product(_ROUTES, _CHECKPOINT_MOVES):
            with self.subTest(route=route, moved=name):
                self.armed(route)
                armed = self.standing()

                self._ticks_behind(_PREPARATION, move)

                self.assertEqual(self.standing(), armed)
                self.doCleanups()
                self.setUp()

    def test_an_unread_last_proof_holds(self) -> None:
        # The pull request's thread stops answering behind the arming: the
        # last proof cannot re-read the artifact, so nothing is posted, and
        # once it answers the next tick posts the ping under the receipt that
        # arming recorded.
        for route in _ROUTES:
            with self.subTest(route):
                self.seeded_on(route)
                unanswered = _Unanswered(None)
                self._ticks_behind(("edit_pinned_state", support.BehindTheArming), unanswered)
                receipt = self.pinned()[ping.PENDING]["receipt"]
                self.assertEqual(self.pings(), [])
                unanswered.answers(self)

                self.tick()

                self.assert_settled(receipt)
                self.doCleanups()
                self.setUp()

    def test_a_late_end_holds_the_ping(self) -> None:
        # The pull request is merged or closed behind an artifact re-read of
        # the last proof, after that proof read it open: its head stays where
        # it was, so only the pull request's state read last sees the end.
        # Nothing is posted or recorded as pinged, and the next tick's
        # terminals finish the issue, pinging nobody.
        for route, merged, (attempt, seeds) in _LATE_ENDS:
            with self.subTest(route=route, merged=merged, attempt=attempt):
                seeds(self, route)
                held = self._armed_behind(_PREPARATION, _ENDS[merged])[:3]
                self.tick()

                self.assertEqual(held, (0, None, True))
                self.assertEqual(self.pings(), [])
                self.assertEqual(self.github.label_history, [(ping.ISSUE, _ENDED[merged])])
                self.doCleanups()
                self.setUp()

    def test_a_push_behind_the_reread_withholds(self) -> None:
        # The comment read afresh behind the last proof is a request of its
        # own: a push landing while it is read is seen by the pull request
        # read behind it, the last thing asked before the post, on a first
        # attempt and a recovered one alike. Nothing is posted or recorded as
        # pinged, and the arming stands over the head the gate read.
        for route, (attempt, seeds) in product(_ROUTES, _ATTEMPTS):
            with self.subTest(route=route, attempt=attempt):
                seeds(self, route)

                held = self._armed_behind(_REREADING, support.EvidenceMoves.pushes)[:3]

                self.assertEqual(held, (0, None, True))
                self.doCleanups()
                self.setUp()

    def _ticks_behind(self, window: tuple, move) -> None:
        """One tick with `move` made behind the checkpoint `window` names: the client request, and its double."""
        request, behind = window
        with patch.object(self.github, request, behind(self, move)):
            self.tick()

    def _armed_behind(self, window: tuple, move) -> tuple:
        """Tick with `move` behind `window`: pings, head pinged, head armed, writes made, and relabels.

        The pending record is told by whether it names the head the pull
        request stood on as the tick began, and the writes by how many this
        tick made.
        """
        writes = self.github.write_state_calls
        head = self.pull_request.head.sha
        self._ticks_behind(window, move)
        standing = list(self.standing())
        standing[2] = standing[2]["sha"] == head
        standing[3] -= writes
        return tuple(standing)


class RecoveredReadinessTest(completion._CompletionFixture, unittest.TestCase):
    """A ping an earlier tick armed and never posted takes the whole proof before it goes out."""

    def test_a_recovered_ping_refuses_moved_evidence(self) -> None:
        # The ping is armed and its answer lost, so nothing is posted. Behind
        # it the artifact is deleted: the next tick reads the thread without
        # the ping, and the post it then owes is refused with the arming left
        # standing.
        for route in _ROUTES:
            with self.subTest(route):
                self.armed(route)
                armed = self.standing()
                self.deletes_the_artifact()

                self.tick()

                self.assertEqual(self.standing(), armed)
                self.doCleanups()
                self.setUp()

    def test_an_unread_thread_holds_a_recovered_ping(self) -> None:
        # The same ping, and a pull-request thread nobody could read for the
        # artifact behind it: nothing is posted or written, and once it
        # answers the ping is posted under the receipt it was armed with.
        for route in _ROUTES:
            with self.subTest(route):
                receipt = self.armed(route)
                armed = self.standing()
                unanswered = _Unanswered(None)
                unanswered(self)
                self.tick()
                self.assertEqual(self.standing(), armed)
                unanswered.answers(self)

                self.tick()

                self.assert_settled(receipt)
                self.doCleanups()
                self.setUp()


if __name__ == "__main__":
    unittest.main()
