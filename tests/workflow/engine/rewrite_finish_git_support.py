# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A pull request in review over a real checkout and bare remote, its evidence settled, and the base about to move.

The base-sync real-git fixture (`tests/git/base_sync/real_git_test_support.py`)
-- a bare remote, a clone, and the issue's worktree one feature commit past the
base -- with the branch named as the evidence fixtures bind it, pushed, and
the pull request standing on it. A developer report about that head is settled
and reviewed, and evidence of the configured command's run on it is recorded
and settled through the dispatcher's own reconciliation, so every reading the
proof takes -- the fetch, the divergence, the trees -- is git's own.

The configured command is a real one, and every run of it appends a line to a
file outside the checkout (`RealGitFinishCase.runs`). A rewrite either goes through the whole
per-tick base refresh -- its real rebase and its lease-pinned push -- or is
made here (`rebases_by_hand`) and handed to the finish as the git owner reads
its candidate, which is how a case stands a review of the rewritten head on the
comment before the finish reads it.
"""
from __future__ import annotations

from unittest.mock import patch

from orchestrator import config
from orchestrator.git.base_sync import rewrite_facts as _rewrite_facts
from orchestrator.git.base_sync.rewrite_handoffs import _LandedRewrite, _PushOutcome, _RewriteAttempt
from orchestrator.github.pinned_state import PinnedState
from orchestrator.github.verification_evidence import EvidenceSource, VerifiedCommand
from orchestrator.workflow.engine import (
    report_records as _report_records,
    rewrite_finish as _finish,
    verification_proof as _proof,
    verification_record_state as _record_state,
    verification_records as _records,
    verification_transaction as _transaction,
)
from orchestrator.workflow.engine.rewrite_finish_models import FinishOutcome, FinishRoad, LandedFinish
from tests.git.base_sync.real_git_test_support import _RefreshBaseRealGitFixture
from tests.support.fakes import FakeGitHubClient, FakePR, FakePRRef, make_issue
from tests.workflow.engine import (
    rewrite_finish_evidence_test_support as finish_support,
    rewrite_finish_readings as _readings,
    verification_report_fixture as _report,
    verification_world_fixture as _world,
)

ISSUE = 7

PR_NUMBER = 42

BRANCH = _world.BRANCH

REVIEWING = finish_support.REVIEWING

# What the configured command prints where a case configures nothing else.
CHECKED = "feature.py is in place"

_QUIET = "--quiet"

_ORIGIN = "origin"


def tree(case, revision: str) -> str:
    """The full tree `revision` carries in `case`'s checkout."""
    return case._git("rev-parse", f"{revision}^{{tree}}", cwd=case._wt).strip()


def remote_head(case) -> str:
    """Where `case`'s bare remote has the pull request's branch."""
    return case._git("rev-parse", f"refs/heads/{BRANCH}", cwd=case._remote).strip()


def invalidated(case) -> tuple:
    """The history that indexes `case`'s settled evidence alone, invalidated."""
    return ((case.source.receipt, _readings.INVALIDATED),)


def nothing_recorded(case) -> tuple:
    """What a finish that recorded nothing for the rewritten head leaves: the settled evidence invalidated."""
    return None, None, invalidated(case)


def advances_the_base(case, *, net: bool = True) -> None:
    """Move the base under the pull request: by a file the branch lacks, or -- `net` False -- by none at all.

    A file added and then removed moves the base without changing what a
    rebase onto it leaves the branch carrying: the replayed commit is new, and
    its tree is the one tested.
    """
    case._advance_base(conflicting=False)
    if net:
        return
    work = case._work
    case._git("rm", _QUIET, "extra.txt", cwd=work)
    case._git("commit", _QUIET, "-m", "base retreat", cwd=work, env_extra=case._author_env)
    case._git("push", _QUIET, _ORIGIN, "main", cwd=work)


class RealGitFinishCase(_RefreshBaseRealGitFixture):
    """Issue #7 in review over PR #42, its head's evidence settled, on a real checkout and remote."""

    def setUp(self) -> None:
        _RefreshBaseRealGitFixture.setUp(self)
        self._ran = self._tmpdir / "ran"
        worktrees = self._tmpdir / "worktrees"
        self.enterContext(patch.object(config, "WORKTREES_DIR", worktrees))
        self.configures(f"test -f feature.py && echo '{CHECKED}'")
        self._git("branch", "-m", BRANCH, cwd=self._wt)
        self._git("push", _QUIET, _ORIGIN, BRANCH, cwd=self._wt)
        self.anchor = self._wt_head()
        self.issue = make_issue(ISSUE, label=REVIEWING)
        self.gh = FakeGitHubClient([self.issue])
        self._gh = self.gh
        self.pull_request = FakePR(
            number=PR_NUMBER, head_branch=BRANCH, head=FakePRRef(sha=self.anchor),
        )
        self.gh.add_pr(self.pull_request)
        self.state = PinnedState(comment_id=1, state_data={"pr_number": PR_NUMBER, "branch": BRANCH})
        self.source = self._settles(_report.settles_report(self, 1, head=self.anchor))

    def configures(self, command: str) -> None:
        """Configure `command` as the one verification command, counted on every run."""
        counted = f"echo run >> '{self._ran}' && {command}"
        self.enterContext(patch.object(config, "VERIFY_COMMANDS", (counted,)))

    def runs(self) -> int:
        """How many times the configured command has run."""
        if not self._ran.exists():
            return 0
        return len(self._ran.read_text().splitlines())

    def rebases_by_hand(self) -> str:
        """Rebase the checkout onto the moved base and push it over the anchor, as a refresh would; the new head."""
        self._git("fetch", _QUIET, _ORIGIN, cwd=self._wt)
        self._git("rebase", _QUIET, f"{_ORIGIN}/main", cwd=self._wt, env_extra=self._author_env)
        head = self._wt_head()
        lease = f"--force-with-lease=refs/heads/{BRANCH}:{self.anchor}"
        self._git("push", _QUIET, lease, _ORIGIN, f"HEAD:refs/heads/{BRANCH}", cwd=self._wt)
        self.pull_request.head.sha = head
        return head

    def reviews(self, head: str) -> None:
        """Settle the refreshed report of `head` and hand a reviewer it, over the comment as it stands."""
        self.state = self.gh.read_pinned_state(self.issue)
        _report.settles_report(self, 2, _report.LATER_REPORT_TEXT, head=head)
        self.gh.write_pinned_state(self.issue, self.state)

    def finishes(self, head: str, road: FinishRoad = FinishRoad.PUBLICATION) -> FinishOutcome:
        """Finish the landing onto `head` that `road` reached, its candidate read out of the checkout by git.

        The publication pins the attempt it made first, and saw its push
        accepted; a recovery finds that attempt pinned and observes the push
        standing. Either way the remote is the reading the candidate carries.
        """
        if road is FinishRoad.PUBLICATION:
            self.state = self.gh.read_pinned_state(self.issue)
            for key, attempted in finish_support.attempt_record(self.anchor, head, PR_NUMBER, REVIEWING).items():
                self.state.set(key, attempted)
            self.gh.write_pinned_state(self.issue, self.state)
        attempt = _RewriteAttempt(anchor=self.anchor, pr_number=PR_NUMBER, stage=REVIEWING)
        candidate = _rewrite_facts._prepares_the_candidate(self._spec, self._wt, attempt, BRANCH)
        outcome = _PushOutcome.ACCEPTED if road is FinishRoad.PUBLICATION else _PushOutcome.OBSERVED
        return _finish.finalizes(LandedFinish(
            gh=self.gh,
            spec=self._spec,
            issue=self.issue,
            state=self.gh.read_pinned_state(self.issue),
            landed=_LandedRewrite(candidate=candidate, outcome=outcome, remote=candidate.remote),
            label=self.gh.workflow_label(self.issue),
            road=road,
        ))

    def _settles(self, subject) -> _records.PendingEvidence:
        """Record the configured command's run on the anchor and settle it through the dispatcher's reconciliation."""
        publication = _report_records.ReportSubject(
            repo_slug=self.gh.repo_slug,
            pr_number=PR_NUMBER,
            branch=BRANCH,
            source_sha=self.anchor,
            requirements_revision=subject.requirements_revision,
        )
        binding = _records.EvidenceBinding(
            target=_records.EvidenceTarget(publication=publication, subject=subject.recorded()),
            source=EvidenceSource.ORCHESTRATOR_EXECUTED,
            tested_sha=self.anchor,
            tested_tree=tree(self, self.anchor),
            context_revision=_proof.configured_context_revision(),
        )
        ran = (VerifiedCommand(command=config.VERIFY_COMMANDS[0], exit_status=0, output=CHECKED),)
        pending = _record_state.mint_pending_evidence(self.state, ISSUE, binding, ran)
        self.assertTrue(_record_state.record_pending_evidence(self.state, pending))
        self.gh.write_pinned_state(self.issue, self.state)
        settling = self.gh.read_pinned_state(self.issue)
        self.assertFalse(_transaction._reconciles_pending_evidence(
            self.gh, self._spec, self.issue, REVIEWING, settling,
        ))
        return pending
