# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Checkouts on a real repository whose issues' pinned records admission refuses.

Three issues stand where a refresh route would act on each, read as current:
a pull request one commit behind the base, a pre-PR branch nobody has pushed,
and an auto rebase interrupted between its rebase and its push -- its
checkout on a replay the remote has never seen, the pull request still on
the head the push would be leased against. The base has advanced on the
remote since, by a commit pushed from another clone, so the tick's own base
fetch is the one thing that can move this clone's base ref.

Each record is the pinned comment itself, posted on the issue's thread by the
account the token belongs to and spelled as the writer spells one, and the
client reads and writes it through the production pinned-state reader and
writers rather than the double's own store: admission refuses or takes it from
the comment's bytes, as a deployed poller's would.

Everything an issue owns can be read back whole: its checkout's files and
HEAD, every local and remote ref, the worktrees git has registered, and the
issue's thread byte for byte, its labels, and its pull request on GitHub.
"""
from __future__ import annotations

import contextlib
from pathlib import Path
from unittest.mock import patch

from orchestrator.git import branch_transport as _branch_transport
from orchestrator.git.worktrees import naming as _worktree_naming, paths as _worktree_paths
from orchestrator.github.pinned_state import SUPPORTED_SCHEMA_VERSION, GitHubStateMixin, pinned_state_body
from tests.git.base_sync.gate_reads_support import _gate_base_reads, _remote_on_disk
from tests.git.base_sync.recovery_git_support import _local_fetch, _LocalLeasePush
from tests.git.worktrees import real_git_test_support as _real_git
from tests.support.fakes import FakeGitHubClient, FakePR, FakePRRef, make_issue
from tests.workflow.observation_support import left_on_github

# The pull request, the pre-PR branch, and the interrupted rebase.
PUBLISHED = 41
PRE_PR = 42
INTERRUPTED = 43
REFUSED = (PUBLISHED, PRE_PR, INTERRUPTED)

# The version a record is pinned under to be admitted.
SUPPORTED_VERSION = SUPPORTED_SCHEMA_VERSION

# What the refresh and the dispatch each say they do with a refused record.
LEFT_STANDING = "running no base refresh route over it"
NOT_DISPATCHED = "refusing to dispatch it"
_OUTCOMES = (LEFT_STANDING, NOT_DISPATCHED)

# The anchor the interrupted rebase pinned and the replay it left, by key.
KEY_ANCHOR = "pending_auto_base_rebase_push_sha"
KEY_REPLAY = "pending_auto_base_rebase_rewrite_sha"
KEY_BRANCH = "branch"

_LABEL_IN_REVIEW = "in_review"
_LABEL_IMPLEMENTING = "workflow:implementing"
_LABEL_VALIDATING = "workflow:validating"

# Fields the issues' own work recorded, which read as current would say runs
# were spent and a review is under way.
_RUNS_USED = 2
_REVIEW_ROUND = 3

_PR_OFFSET = 100

_QUIET = "--quiet"
_ORIGIN = _real_git.ORIGIN_REMOTE
_BASE_BRANCH = _real_git.BASE_BRANCH
_BASE_REF = f"refs/remotes/{_ORIGIN}/{_BASE_BRANCH}"

# Where the advanced base is borrowed into the clone to replay onto, and
# dropped from again so this clone's base ref never sees it.
_BORROWED_BASE = "refs/borrowed/base"

# The client's pinned-state roads taken from the production client: the
# reader, the whole-state writer, and the two requests the strict edit makes.
_PRODUCTION_PINNED_ROADS = ("read_pinned_state", "write_pinned_state", "_pinned_comment", "_send_pinned_edit")


class _Disk:
    """The bare remote, this clone of it, and another clone the base advances from.

    The transport is pointed at the bare remote: the token-bearing fetches and
    the leased push run against it for real, and the size gate's base reads
    are answered.
    """

    def __init__(self, case) -> None:
        repository = _real_git._RealGitWorktreeRepo()
        repository.prepare(case)
        self.spec = repository.spec
        self.remote = self.spec.target_root.parent / "remote.git"
        self._upstream = self.spec.target_root.parent / "upstream"
        cloned = ("clone", _QUIET, str(self.remote), str(self._upstream))
        _real_git._run_git(*cloned, cwd=self.remote.parent)
        self.push = _LocalLeasePush()
        case.enterContext(patch.object(_branch_transport, "_push_branch", self.push))
        case.enterContext(patch.object(_branch_transport, "_authed_fetch", _local_fetch))
        _gate_base_reads(case)
        _remote_on_disk(case, self.spec.slug, self.remote)

    def branch(self, number: int, *, push: bool) -> tuple[str, str]:
        """Check issue `number`'s branch out off the base, commit to it, and push it where asked."""
        branch = _worktree_naming._branch_name(self.spec, number)
        checkout = _worktree_paths._worktree_path(self.spec, number)
        checkout.parent.mkdir(parents=True, exist_ok=True)
        added = ("worktree", "add", _QUIET, "-b", branch, str(checkout), _BASE_REF)
        _real_git._run_git(*added, cwd=self.spec.target_root)
        _committed(checkout, f"issue_{number}.py")
        if push:
            _real_git._run_git("push", _QUIET, _ORIGIN, branch, cwd=checkout)
        return branch, _tip(checkout)

    def advance_base(self) -> str:
        """Commit to the base from the other clone and push it, leaving this clone's base ref where it was."""
        _committed(self._upstream, "advance.txt")
        _real_git._run_git("push", _QUIET, _ORIGIN, _BASE_BRANCH, cwd=self._upstream)
        return _tip(self._upstream)

    def replay(self, number: int) -> str:
        """Rebase issue `number`'s checkout onto the advanced base without moving this clone's base ref."""
        checkout = _worktree_paths._worktree_path(self.spec, number)
        # Fetched by path rather than by remote name: a fetch from `origin`
        # updates its remote-tracking base ref whatever the refspec says.
        borrowed = (str(self.remote), f"{_BASE_BRANCH}:{_BORROWED_BASE}")
        _real_git._run_git("fetch", _QUIET, *borrowed, cwd=checkout)
        _real_git._run_git("rebase", _QUIET, _BORROWED_BASE, cwd=checkout, env_extra=_real_git._author_env())
        _real_git._run_git("update-ref", "-d", _BORROWED_BASE, cwd=checkout)
        return _tip(checkout)

    def standing(self) -> dict:
        """Each checkout's files and HEAD, every ref, and the registered worktrees -- this clone's base ref aside.

        Moving that ref is the shared base fetch's one effect, which `base`
        reads on its own.
        """
        target = self.spec.target_root
        checkouts = {number: _worktree_paths._worktree_path(self.spec, number) for number in REFUSED}
        return {
            "checkouts": {number: _files(checkout) for number, checkout in checkouts.items()},
            "heads": {number: _tip(checkout) for number, checkout in checkouts.items()},
            "local refs": [ref for ref in _refs(target) if not ref.startswith(f"{_BASE_REF} ")],
            "remote refs": _refs(self.remote),
            "worktrees": _real_git._run_git("worktree", "list", "--porcelain", cwd=target),
        }

    def base(self) -> str:
        """What this clone's remote-tracking base ref names now."""
        return _tip(self.spec.target_root, _BASE_REF)

    def remote_head(self, branch: str) -> str:
        """What `branch` names on the remote now."""
        return _tip(self.remote, f"refs/heads/{branch}")


class RefusedCheckouts:
    """The three issues, their checkouts, and the records their own work left.

    No record is pinned until a case pins one, under the version it chooses.
    """

    def __init__(self, case, github: FakeGitHubClient) -> None:
        self.disk = _Disk(case)
        self._github = github
        for road in _PRODUCTION_PINNED_ROADS:
            production = getattr(GitHubStateMixin, road)
            case.enterContext(patch.object(type(github), road, production))
        self._pinned_under: dict[int, int | None] = {}
        self._pins: dict[int, object] = {}
        self.base_before = self.disk.base()
        self.records = {
            PUBLISHED: self._work(PUBLISHED, _LABEL_IN_REVIEW, pushed=True),
            PRE_PR: self._work(PRE_PR, _LABEL_IMPLEMENTING, pushed=False),
            INTERRUPTED: self._work(INTERRUPTED, _LABEL_VALIDATING, pushed=True),
        }
        self.base_after = self.disk.advance_base()
        self._replayed(INTERRUPTED)

    def pin(self, number: int, version: int | None) -> None:
        """Pin issue `number`'s record, with the runs it spent, under `version` -- or under none where it is None.

        The first pin posts the comment on the thread as the token's own
        account, and a later one edits that same comment in place.
        """
        self._pinned_under[number] = version
        stamped = {} if version is None else {"schema_version": version}
        body = pinned_state_body({**self.records[number], "agent_runs_used": _RUNS_USED, **stamped})
        pinned = self._pins.get(number)
        if pinned is None:
            self._pins[number] = self._github.get_issue(number).create_comment(body)
        else:
            pinned.edit(body)

    def refreshed(self) -> contextlib.AbstractContextManager:
        """The block a tick's real refresh runs in: nothing beyond this world's own transport stands in for it."""
        return contextlib.nullcontext()

    def on_github(self) -> dict:
        """Each issue's thread byte for byte, what admission makes of its pinned comment, and everything else a pass
        could change about it.
        """
        return {
            number: (
                [(comment.id, comment.body) for comment in self._github.get_issue(number).comments],
                self._github.read_pinned_state(self._github.get_issue(number)).admission_status.value,
                left_on_github(self._github, number),
            )
            for number in REFUSED
        }

    def said(self, output: list[str]) -> dict[int, set[str]]:
        """What the warnings say is done with each pinned record, among those naming it and the version it carries."""
        return {
            number: _outcomes(output, self._github.repo_slug, number, version)
            for number, version in self._pinned_under.items()
        }

    def _work(self, number: int, label: str, *, pushed: bool) -> dict:
        """Open issue `number` under `label` on a branch of its own, and answer the record that work leaves.

        A pushed branch is published on a pull request standing on its head.
        """
        branch, head = self.disk.branch(number, push=pushed)
        self._github.add_issue(make_issue(number, label=label))
        if not pushed:
            return {KEY_BRANCH: branch}
        pr_number = _PR_OFFSET + number
        standing_on = FakePRRef(sha=head)
        self._github.add_pr(FakePR(number=pr_number, head_branch=branch, head=standing_on))
        return {KEY_BRANCH: branch, "pr_number": pr_number, "review_round": _REVIEW_ROUND}

    def _replayed(self, number: int) -> None:
        """Rebase issue `number` onto the advance, and record the attempt as a crash before its push leaves it."""
        record = self.records[number]
        anchor = self.disk.remote_head(record[KEY_BRANCH])
        record.update({
            KEY_ANCHOR: anchor,
            KEY_REPLAY: self.disk.replay(number),
            "pending_auto_base_rebase_rewrite_pr": record["pr_number"],
            "pending_auto_base_rebase_rewrite_stage": _LABEL_VALIDATING,
        })


def _outcomes(
    output: list[str],
    repo_slug: str,
    issue_number: int,
    version: int | None,
) -> set[str]:
    """Which of the two outcomes the warnings naming this issue's refused record, and its version, say."""
    named = f"repo={repo_slug} issue=#{issue_number} pinned comment"
    versions = f"found schema_version {version!r}, supported {SUPPORTED_SCHEMA_VERSION}"
    lines = [line for line in output if named in line and versions in line]
    return {outcome for outcome in _OUTCOMES for line in lines if outcome in line}


def _committed(checkout: Path, filename: str) -> None:
    """Add one new file where asked and commit it."""
    (checkout / filename).write_text(f"{filename}\n")
    _real_git._run_git("add", filename, cwd=checkout)
    _real_git._run_git("commit", _QUIET, "-m", filename, cwd=checkout, env_extra=_real_git._author_env())


def _tip(repository: Path, revision: str = "HEAD") -> str:
    """The commit `revision` names in `repository`."""
    return _real_git._run_git("rev-parse", revision, cwd=repository).strip()


def _refs(repository: Path) -> list[str]:
    """Every ref the repository holds, with the commit it names."""
    return _real_git._run_git("for-each-ref", "--format=%(refname) %(objectname)", cwd=repository).splitlines()


def _files(checkout: Path) -> dict[str, bytes]:
    """Every file in the checkout, git's own pointer file aside, by path."""
    return {
        str(path.relative_to(checkout)): path.read_bytes()
        for path in sorted(checkout.rglob("*"))
        if path.is_file() and path.name != ".git"
    }
