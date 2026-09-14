# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The reads a terminal artifact is judged by, one answer at a time.

Driven against real clones, real checkouts, real refs, and a real bare remote,
because the third answer is the whole point of these probes and it only exists
against a real host: a stubbed `rev-parse` returns whatever the stub was told
to, while a repository that is not there, a ref that is not there, and a ref
that is there are three different exit statuses git assigns on its own.

The remote is real for a second reason. What separates `_published_tip` from
the local ref that resembles it is that one of them can be written by an agent
and the other cannot, and only a fixture holding both can show the two
disagreeing.
"""

from __future__ import annotations

import time
import unittest
from unittest.mock import patch

from orchestrator.git import branch_transport, commands
from orchestrator.git.worktrees import activity_evidence as _activity_evidence, evidence, tip_evidence as _tip_evidence
from orchestrator.git.worktrees.models import BranchTip, ProbeAnswer
from tests.git.worktrees import (
    artifact_git as _artifact_git,
    candidate_refs as _candidate_refs,
    evidence_test_support as _evidence_support,
)
from tests.git.worktrees.artifact_test_support import WIDGET_SLUG, _spec
from tests.git.worktrees.candidate_host_test_support import (
    _foreign_checkout,
)
from tests.git.worktrees.eligibility_test_support import ISSUE_NUMBER
from tests.workflow.stages.question.question_real_git_test_support import (
    _run_git,
)

ANOTHER_BRANCH = "orchestrator/acme__widget/issue-99"
LOOSE_FILE = "left-behind.txt"
LOOSE_CONTENT = "an agent's unfinished work\n"
MISSING_REVISION = "0000000000000000000000000000000000000000"
NOT_A_CLONE = "no-repository-here"
NOTHING_AT_ALL = "never-created"
LOOPING_LINK = "looping"
LOOPING_BACK = "looping-back"
IGNORE_FILE = ".gitignore"
HIDDEN_FILE = "secrets.env"
HIDDEN_CONTENT = "TOKEN=an operator's own\n"
TRACKED_FILE = "tracked.txt"
TRACKED_CONTENT = "committed work\n"


class CheckoutIdentityTest(_evidence_support._HostTestCase):
    """Whether the directory at the issue's path is the issue's checkout."""

    def test_its_own_branch_confirms(self) -> None:
        _candidate_refs._branch_at(self.clone, self.branch, _artifact_git.BASE_BRANCH)
        worktree = self.world.attached_checkout(
            self.spec, ISSUE_NUMBER, self.branch,
        )

        identified = evidence._checkout_identity(
            self.spec, ISSUE_NUMBER, worktree,
        )

        self.assertIs(identified, ProbeAnswer.CONFIRMED)

    def test_a_repository_of_its_own_is_refuted(self) -> None:
        # The path is the one the creators would use and the directory is a
        # git repository, so every reading short of the shared object store
        # says this is the issue's checkout -- and reclaiming it would take a
        # repository this orchestrator never made.
        worktree = _foreign_checkout(self.spec, ISSUE_NUMBER)

        identified = evidence._checkout_identity(
            self.spec, ISSUE_NUMBER, worktree,
        )

        self.assertIs(identified, ProbeAnswer.REFUTED)

    def test_another_branch_and_a_detachment_refute(self) -> None:
        # Both are a checkout of this clone that is not on this issue's work:
        # the first is somebody else's branch parked in our directory, the
        # second is commits sitting on no branch at all.
        _candidate_refs._branch_at(self.clone, ANOTHER_BRANCH, _artifact_git.BASE_BRANCH)
        elsewhere = self.world.attached_checkout(
            self.spec, ISSUE_NUMBER, ANOTHER_BRANCH,
        )
        detached = self.world.checkout(self.spec, ISSUE_NUMBER + 1)

        for worktree, issue_number in (
            (elsewhere, ISSUE_NUMBER), (detached, ISSUE_NUMBER + 1),
        ):
            with self.subTest(worktree=worktree.name):
                self.assertIs(
                    evidence._checkout_identity(
                        self.spec, issue_number, worktree,
                    ),
                    ProbeAnswer.REFUTED,
                )

    def test_no_repository_at_all_is_unreadable(self) -> None:
        # Nothing was established about the directory, which is not the same
        # answer as establishing that it is somebody else's.
        worktree = self.world.path(NOT_A_CLONE)
        worktree.mkdir()

        identified = evidence._checkout_identity(
            self.spec, ISSUE_NUMBER, worktree,
        )

        self.assertIs(identified, ProbeAnswer.UNREADABLE)


class WorktreeCleanlinessTest(_evidence_support._HostTestCase):
    """Whether a checkout PROVED it is carrying nothing an operator wants.

    Two reads rather than one, because git draws the line between them: what
    it calls dirty is what a removal refuses over, and a path the
    repository's own rules hide is neither.
    """

    def setUp(self) -> None:
        super().setUp()
        _candidate_refs._branch_at(self.clone, self.branch, _artifact_git.BASE_BRANCH)
        self.worktree = self.world.attached_checkout(
            self.spec, ISSUE_NUMBER, self.branch,
        )

    def test_a_fresh_checkout_is_confirmed(self) -> None:
        self.assertIs(
            evidence._clean_worktree(self.worktree), ProbeAnswer.CONFIRMED,
        )
        self.assertIs(
            evidence._nothing_ignored(self.worktree), ProbeAnswer.CONFIRMED,
        )

    def test_an_untracked_file_refutes(self) -> None:
        (self.worktree / LOOSE_FILE).write_text(LOOSE_CONTENT)

        self.assertIs(
            evidence._clean_worktree(self.worktree), ProbeAnswer.REFUTED,
        )

    def test_an_ignored_file_refutes_one_read(self) -> None:
        # The gap the two reads exist to cover between them. A path the
        # repository's own rules hide is neither untracked nor modified, so
        # the status read goes on confirming a tree that is carrying it --
        # which is the reading a removal would otherwise be run on.
        (self.worktree / IGNORE_FILE).write_text(f"{HIDDEN_FILE}\n")
        _run_git("add", IGNORE_FILE, cwd=self.worktree)
        _run_git("commit", "-q", "-m", "ignore it", cwd=self.worktree)
        (self.worktree / HIDDEN_FILE).write_text(HIDDEN_CONTENT)

        self.assertIs(
            evidence._clean_worktree(self.worktree), ProbeAnswer.CONFIRMED,
        )
        self.assertIs(
            evidence._nothing_ignored(self.worktree), ProbeAnswer.REFUTED,
        )

    def test_a_tree_that_will_not_report_is_unread(self) -> None:
        # A status that could not be taken names no paths, which is what an
        # empty tree names too -- so the answer has to come from whether the
        # read happened rather than from what it listed. A directory that is
        # no repository and a directory that is not there at all are both
        # that, and the second fails the spawn rather than the command.
        no_repository = self.world.path(NOT_A_CLONE)
        no_repository.mkdir()
        for tree in (no_repository, self.world.path(NOTHING_AT_ALL)):
            with self.subTest(tree=tree.name):
                self.assertIs(
                    evidence._clean_worktree(tree), ProbeAnswer.UNREADABLE,
                )
                self.assertIs(
                    evidence._nothing_ignored(tree), ProbeAnswer.UNREADABLE,
                )

    def test_a_tree_that_will_not_resolve_is_unread(self) -> None:
        # The read names the tree it reports on, and naming it resolves the
        # path -- which on Python 3.12 raises out of `Path.resolve` for a
        # symlink loop rather than answering. A checkout is a tree an agent
        # owns and can rearrange into one, so the probe answers instead of
        # ending the pass that asked.
        looping = self.world.path(LOOPING_LINK)
        back = self.world.path(LOOPING_BACK)
        looping.symlink_to(back)
        back.symlink_to(looping)

        self.assertIs(
            evidence._clean_worktree(looping), ProbeAnswer.UNREADABLE,
        )


class QuietCheckoutTest(_evidence_support._QuietCheckoutCase):
    """When a checkout was last disturbed, and the two ways that does not answer.

    The one read here that is not about what a tree holds. What it costs to get
    wrong is a directory somebody is standing in, so a host that will not say
    answers as one -- never as a tree nobody has been near.
    """

    def test_a_checkout_made_just_now_refutes(self) -> None:
        self.assertIs(
            _activity_evidence._quiet_checkout(self.worktree, time.time() - _evidence_support.HOUR),
            ProbeAnswer.REFUTED,
        )

    def test_a_checkout_left_alone_is_confirmed(self) -> None:
        self.settle()

        self.assertIs(self.quiet(), ProbeAnswer.CONFIRMED)

    def test_an_entry_dropped_in_refutes_again(self) -> None:
        # The tree's own directory answers for a top-level entry created,
        # renamed, or removed: somebody working in it, whatever the status
        # says afterwards.
        self.settle()
        (self.worktree / LOOSE_FILE).write_text(LOOSE_CONTENT)

        self.assertIs(self.quiet(), ProbeAnswer.REFUTED)

    def test_a_tracked_edit_just_committed_refutes(self) -> None:
        # The reading the tree's own directory cannot give: editing a tracked
        # file and committing it leaves that directory exactly where it was,
        # and afterwards the tree is clean and every other probe clears it.
        # What says somebody was here a moment ago is the checkout's own index
        # and reflog, which the commit rewrote.
        _candidate_refs._track_file(self.clone, TRACKED_FILE, TRACKED_CONTENT)
        _run_git("merge", "-q", _artifact_git.BASE_BRANCH, cwd=self.worktree)
        self.settle()
        (self.worktree / TRACKED_FILE).write_text(LOOSE_CONTENT)
        _run_git("commit", "-q", "-am", "an agent's own round", cwd=self.worktree)

        self.assertIs(
            evidence._clean_worktree(self.worktree), ProbeAnswer.CONFIRMED,
        )
        self.assertIs(self.quiet(), ProbeAnswer.REFUTED)

    def test_a_path_that_is_not_there_is_unread(self) -> None:
        self.assertIs(
            _activity_evidence._quiet_checkout(
                self.world.path(NOTHING_AT_ALL), time.time(),
            ),
            ProbeAnswer.UNREADABLE,
        )


class BranchTipTest(_evidence_support._HostTestCase):
    """What a local branch stands on, and the two ways it does not answer."""

    def test_a_branch_resolves_to_its_commit(self) -> None:
        tip = self.commit()

        resolved = _tip_evidence._local_branch_tip(self.spec, self.branch)

        self.assertIs(resolved.answer, ProbeAnswer.CONFIRMED)
        self.assertEqual(resolved.sha, tip)

    def test_an_absent_branch_is_refuted(self) -> None:
        resolved = _tip_evidence._local_branch_tip(self.spec, self.branch)

        self.assertIs(resolved.answer, ProbeAnswer.REFUTED)
        self.assertEqual(resolved.sha, "")

    def test_a_clone_that_will_not_open_is_unread(self) -> None:
        # git's own no is exit 1 and everything else is a reading that never
        # established anything -- a caller that only tested for a non-zero
        # exit would delete a branch on the strength of an unopenable clone.
        elsewhere = self.world.path(NOT_A_CLONE)
        elsewhere.mkdir()

        resolved = _tip_evidence._local_branch_tip(
            _spec(WIDGET_SLUG, elsewhere), self.branch,
        )

        self.assertIs(resolved.answer, ProbeAnswer.UNREADABLE)

    def test_a_git_that_cannot_be_spawned_is_unread(self) -> None:
        with patch.object(
            commands, "_git_hardened", side_effect=OSError("no git here"),
        ):
            resolved = _tip_evidence._local_branch_tip(self.spec, self.branch)

        self.assertIs(resolved.answer, ProbeAnswer.UNREADABLE)


class PublishedTipTest(_evidence_support._HostTestCase):
    """What the remote itself says a branch is at."""

    def test_a_pushed_branch_resolves(self) -> None:
        self.world.serve(self.spec)
        tip = self.commit()
        self.world.publish(self.clone, self.branch, self.branch)

        published = _tip_evidence._published_tip(self.spec, self.branch)

        self.assertIs(published.answer, ProbeAnswer.CONFIRMED)
        self.assertEqual(published.sha, tip)

    def test_a_branch_the_remote_lacks_is_refuted(self) -> None:
        # The ordinary terminal shape rather than a failure: a merged pull
        # request's head branch is deleted there.
        self.world.serve(self.spec)
        self.commit()

        published = _tip_evidence._published_tip(self.spec, self.branch)

        self.assertIs(published.answer, ProbeAnswer.REFUTED)
        self.assertEqual(published.sha, "")

    def test_a_tracking_ref_answers_for_nothing(self) -> None:
        # The tampering this probe exists for. The tracking ref is a local ref
        # in the object store the per-issue worktrees share, so an agent can
        # point it at its own commit -- and the remote goes on saying what it
        # actually holds.
        self.world.serve(self.spec)
        planted = self.commit()
        _candidate_refs._tracking_ref(self.clone, self.branch, planted)

        published = _tip_evidence._published_tip(self.spec, self.branch)

        self.assertIs(published.answer, ProbeAnswer.REFUTED)

    def test_a_transport_that_raised_is_unread(self) -> None:
        # The transport answers `None` for the failures it recognizes and
        # raises for the ones underneath them -- no git to spawn, a clone
        # removed since the scan named it. A probe whose contract is three
        # answers must not have a fourth, so both arrive as the same one.
        self.world.serve(self.spec)
        self.commit()

        with patch.object(
            branch_transport,
            "_remote_branch_tip",
            side_effect=OSError("no git here"),
        ):
            published = _tip_evidence._published_tip(self.spec, self.branch)

        self.assertIs(published.answer, ProbeAnswer.UNREADABLE)

    def test_an_unreachable_remote_is_unread(self) -> None:
        # Neither the branch being there nor its absence was established, and
        # a caller that read this as "the remote does not have it" would go on
        # to decide the branch on evidence nobody produced.
        self.world.unreachable(self.spec)
        self.commit()

        published = _tip_evidence._published_tip(self.spec, self.branch)

        self.assertIs(published.answer, ProbeAnswer.UNREADABLE)


class BaseAncestryTest(_evidence_support._HostTestCase):
    """Whether a base commit the caller established carries a branch tip."""

    def test_a_tip_the_base_holds_is_confirmed(self) -> None:
        # The merged shape: the base has moved onto a commit that descends
        # from what the branch is standing on.
        tip = self.commit()
        merged = self.world.commit_on(
            self.clone, _artifact_git.BASE_BRANCH, start=self.branch,
        )

        self.assertIs(
            _tip_evidence._base_contains(self.spec, _evidence_support._named(merged), tip),
            ProbeAnswer.CONFIRMED,
        )

    def test_a_tip_ahead_of_the_base_is_refuted(self) -> None:
        # Both ends are things the caller established, so what the clone's own
        # `refs/remotes/...` say about either is not consulted at all.
        base = _evidence_support._named(_candidate_refs._revision(self.clone, _artifact_git.BASE_BRANCH))
        tip = self.commit()

        self.assertIs(
            _tip_evidence._base_contains(self.spec, base, tip),
            ProbeAnswer.REFUTED,
        )

    def test_a_commit_this_clone_lacks_is_unread(self) -> None:
        tip = self.commit()

        self.assertIs(
            _tip_evidence._base_contains(self.spec, _evidence_support._named(MISSING_REVISION), tip),
            ProbeAnswer.UNREADABLE,
        )

    def test_a_base_nobody_named_is_unread(self) -> None:
        # The remote would not say what the base is on, so there is nothing to
        # measure against -- which is decided here rather than by each caller,
        # so none of them can reach the comparison holding a base nobody
        # named.
        tip = self.commit()

        for unnamed in (ProbeAnswer.REFUTED, ProbeAnswer.UNREADABLE):
            with self.subTest(base=unnamed):
                self.assertIs(
                    _tip_evidence._base_contains(
                        self.spec, BranchTip(answer=unnamed), tip,
                    ),
                    ProbeAnswer.UNREADABLE,
                )


if __name__ == "__main__":
    unittest.main()
