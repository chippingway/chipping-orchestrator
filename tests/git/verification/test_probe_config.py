# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What the probes read when the worktree answers for itself.

Every probe below runs against a real repository rather than a mocked `git`,
because what is being pinned is git's own behaviour: the worktree's
`.git/config` is inside the tree an agent writes to, and the knobs planted here
change what a command reports without failing it. A mock could only assert the
flags were passed; only real git can show that passing them is what makes the
answer true.

Each test proves the trap first. It plants the knob, runs the command the way a
caller reading defaults would, and asserts the planted setting really did hide
the evidence -- otherwise a probe that quietly stopped passing its flags would
still pass here, on a repository where there was nothing to hide.

The base-commit test is the same shape without any config: the local
`refs/remotes/<remote>/<base>` ref is agent-writable too, since a linked
worktree shares the object store, so a diff that names that ref can be pointed
at whatever the agent likes.

The replacement tests go one further. Naming a commit by object id is only
worth something if the object id still means that commit: `refs/replace/<oid>`
and the graft file both tell git to serve something else under the same name,
and neither is config, so nothing the hardened envelope overrides with `-c`
reaches them. What answers them is the pair of environment variables the
envelope also sets, and these are what prove it.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from orchestrator.git.verification import probes, status as _worktree_status
from tests.workflow.fixtures import TEST_BASE_BRANCH

GIT_COMMAND = "git"
QUIET_FLAG = "-q"
GIT_CONFIG = "config"
GIT_DIFF = "diff"
NAMES_ONLY = "--name-only"
MESSAGE_FLAG = "-m"
SEED_FILE = "seed"
LEFTOVER_FILE = "leftover.txt"
IGNORE_FILE = ".gitignore"
HIDDEN_FILE = "secrets.env"
HIDDEN_TEXT = "TOKEN=an operator's own\n"
IGNORED_DIR = "build"
# More individually hidden files than the probe carries back, so what it
# answers with says the cap ran rather than that the tree was small.
HIDDEN_SPREAD = 14
CODE_PATH = "code.py"
PLAN_PATH = "plans/issue-42.md"
PLAN_TEXT = "# the plan\n"
# A committed path whose bytes are not valid UTF-8, spelled the way the
# filesystem hands one back: git prints it verbatim under `-z`.
UNDECODABLE_PATH = os.fsdecode(b"docs/od\xffd.txt")
GITLINK_PATH = "vendor/dep"
GITLINK_MODE = "160000"
REMOTE_BASE_REF = f"refs/remotes/origin/{TEST_BASE_BRANCH}"
GRAFT_FILE = ".git/info/grafts"
GIT_STATUS = "status"
WORK_TREE_FLAG = "--work-tree"
PORCELAIN = "--porcelain"
UPDATE_INDEX = "update-index"
AT_PATH = "-C"
WORKTREE_SCOPE = "--worktree"
LINKED_DIR = "linked"
SHADOW_DIR = "shadow"
FEATURE_BRANCH = "feature"
SEED_TEXT = "x\n"
# An untracked file named exactly as the default line format spells a rename,
# and what that format makes of it.
ARROW_FILE = " -> "
QUOTED_ARROW = '?? " -> "'
RENAMED_FILE = "renamed"
AGENT_EDIT = "edited by the agent\n"
# The two index bits that stop git comparing an entry against the working
# tree, and neither is config -- so nothing the hardened envelope overrides
# reaches either one.
SUPPRESSING_INDEX_FLAGS = ("--assume-unchanged", "--skip-worktree")
# A well-formed object id no repository in this module ever created.
UNKNOWN_SHA = "0123456789abcdef0123456789abcdef01234567"
TREE_OF = "^{tree}"


class _RealRepoMixin:
    """A real repository with one commit, ready to be written into."""

    def setUp(self) -> None:
        tmpdir = Path(tempfile.mkdtemp(prefix="orch-probe-config-"))
        self.addCleanup(shutil.rmtree, str(tmpdir), ignore_errors=True)
        self.work = tmpdir / "work"
        self.work.mkdir()
        self.git("init", QUIET_FLAG, "-b", TEST_BASE_BRANCH, ".")
        self.git(GIT_CONFIG, "user.email", "t@t")
        self.git(GIT_CONFIG, "user.name", "t")
        self.write(SEED_FILE, "x\n")
        self.base_sha = self.commit(SEED_FILE)

    def git(self, *args: str) -> str:
        """Run one git command in the repository and return its stdout."""
        completed = subprocess.run(
            [GIT_COMMAND, *args],
            cwd=str(self.work),
            check=True,
            capture_output=True,
            text=True,
            env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
        )
        return completed.stdout

    def write(self, path: str, text: str) -> None:
        """Write a file in the repository, creating its parents."""
        target = self.work / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)

    def commit(self, message: str) -> str:
        """Commit everything staged or written, and return the new SHA."""
        self.git("add", "-A")
        self.git("commit", QUIET_FLAG, MESSAGE_FLAG, message)
        return self.git("rev-parse", "HEAD").strip()

    def ignore(self, *paths: str) -> None:
        """Commit a rule file that hides every one of `paths`."""
        self.write(IGNORE_FILE, "".join(f"{path}\n" for path in paths))
        self.commit(IGNORE_FILE)

    def _linked_worktree(self) -> Path:
        """A second checkout of this repository, as the orchestrator makes one."""
        linked = self.work.parent / LINKED_DIR
        self.git("worktree", "add", QUIET_FLAG, "-b", FEATURE_BRANCH, str(linked))
        return linked


class StatusFlagOverrideTest(_RealRepoMixin, unittest.TestCase):
    """`_worktree_status` reports what the worktree would have hidden.

    Three ways a clean answer is arranged without touching the file it is about
    -- a config knob that narrows what is reported, one that changes which tree
    is reported ON, and an index bit that stops the comparison happening at all
    -- and each of them leaves a publication reading a branch as the plan file
    alone while the checkout carries the agent's own work beside it.

    Naming the tree is not free, and one read here answers for that rather
    than for a planted knob: the path a caller holds is relative whenever
    `WORKTREES_DIR` is, so the flag has to name the tree in terms the command
    running inside it agrees with.
    """

    def test_untracked_and_ignored_survive_the_knob(self) -> None:
        # `status.showUntrackedFiles=no` is one line an agent can add to the
        # config inside its own worktree, and it turns every untracked file
        # into a clean tree for anything reading defaults -- including a
        # publication that must prove the tree is clean before it pushes.
        #
        # It empties the ignored half of the report with it, since that half
        # is what the untracked walk turned up and then classified: asked for
        # defaults, a tree holding a secret its own rules hide answers that it
        # holds nothing, which is the answer that gets the tree deleted.
        self.ignore(HIDDEN_FILE)
        self.git(GIT_CONFIG, "status.showUntrackedFiles", "no")
        self.write(LEFTOVER_FILE, "left behind\n")
        self.write(HIDDEN_FILE, HIDDEN_TEXT)

        self.assertEqual(self.git("status", "--porcelain"), "")
        self.assertEqual(self.git("status", "--porcelain", "--ignored"), "")

        status = _worktree_status._worktree_status(self.work)

        self.assertTrue(status.readable)
        self.assertIn(LEFTOVER_FILE, status.paths)
        self.assertEqual(_worktree_status._ignored_paths(self.work), (HIDDEN_FILE,))

    def test_the_ignored_report_is_kept_small(self) -> None:
        # `--untracked-files=all` is what the other half of this read needs and
        # what this half must not have: under it an ignored directory is
        # reported as every file beneath it, so a dependency root or a build
        # tree answers with a walk nobody reads. Collapsed, the root is one
        # entry -- and what is left is capped, since the answer is spent on a
        # yes-or-no and a line naming what to go and look at.
        self.ignore(IGNORED_DIR, f"{HIDDEN_FILE}*")
        for buried in range(HIDDEN_SPREAD):
            self.write(f"{IGNORED_DIR}/deep/{buried}", HIDDEN_TEXT)
            self.write(f"{HIDDEN_FILE}{buried}", HIDDEN_TEXT)

        hidden = _worktree_status._ignored_paths(self.work)

        self.assertIn(f"{IGNORED_DIR}/", hidden)
        self.assertEqual(len(hidden), _worktree_status._IGNORED_LIMIT)

    def test_a_redirected_worktree_is_not_read(self) -> None:
        # The knob no `-c` override wins against. With `extensions.
        # worktreeConfig` written into the repository a linked worktree shares,
        # `core.worktree` in that worktree's own config points every read at
        # another directory -- so a probe that lets git discover its tree
        # reports on a clean shadow checkout while the real one carries the
        # agent's edits, and the publication pushes over them.
        linked = self._linked_worktree()
        (linked / SEED_FILE).write_text(AGENT_EDIT)
        # Every tracked path present with the content the index has, so the
        # read the redirect captures reports a clean tree.
        shadow = self.work.parent / SHADOW_DIR
        shadow.mkdir()
        (shadow / SEED_FILE).write_text(SEED_TEXT)
        self.git(GIT_CONFIG, "extensions.worktreeConfig", "true")
        self.git(
            AT_PATH, str(linked), GIT_CONFIG, WORKTREE_SCOPE,
            "core.worktree", str(shadow),
        )

        self.assertEqual(self.git(AT_PATH, str(linked), GIT_STATUS, PORCELAIN), "")

        status = _worktree_status._worktree_status(linked)

        self.assertTrue(status.readable)
        self.assertIn(SEED_FILE, status.paths)

    def test_a_relative_worktree_is_read(self) -> None:
        # The path the caller holds is relative whenever `WORKTREES_DIR` is
        # configured that way, and the command runs with its cwd set to the
        # worktree -- so a flag naming the tree relatively names a directory
        # BENEATH it, git refuses to run at all, and the exit code reads as a
        # checkout nothing can be read from. That verdict is about the tree, so
        # the caller parks the issue and promises a later tick will resume it
        # once the tree reads again -- which a failure this deterministic never
        # lets happen.
        self.write(LEFTOVER_FILE, "left behind\n")
        self.addCleanup(os.chdir, os.getcwd())
        os.chdir(str(self.work.parent))
        relative = Path(self.work.name)

        with self.assertRaises(subprocess.CalledProcessError):
            self.git(f"{WORK_TREE_FLAG}={relative}", GIT_STATUS, PORCELAIN)

        status = _worktree_status._worktree_status(relative)

        self.assertTrue(status.readable)
        self.assertIn(LEFTOVER_FILE, status.paths)

    def test_an_unwatched_entry_is_not_clean(self) -> None:
        # The last way out, and the one no envelope reaches: the bit lives on
        # the index entry rather than in config, and git honours it by not
        # looking -- so a tracked file the agent rewrote after setting it comes
        # back clean from every reader of defaults.
        for index_flag in SUPPRESSING_INDEX_FLAGS:
            with self.subTest(index_flag=index_flag):
                self._assert_suppressed_entry_refuses(index_flag)

    def test_nul_delimited_paths_survive(self) -> None:
        # What the default line format loses, in the two ways it loses it. An
        # untracked file named ` -> ` comes back as `?? " -> "`, which is also
        # how that format spells a rename -- read as one, what follows the
        # arrow is a lone quote, which is nothing once the quoting is undone,
        # so the tree reports clean and a plan beside it is published as though
        # the round had left nothing loose. And a real rename puts the path a
        # file came FROM on the same line, where `-z` gives it its own record
        # with no status columns in front of it: taken for a status line it
        # would lose its first three bytes and name a path nothing answers to.
        self.write(ARROW_FILE, "left where the round died\n")
        self.assertIn(QUOTED_ARROW, self.git(GIT_STATUS, PORCELAIN))

        self.assertEqual(_worktree_status._worktree_status(self.work).paths, (ARROW_FILE,))

        (self.work / ARROW_FILE).unlink()
        self.git("mv", SEED_FILE, RENAMED_FILE)

        self.assertEqual(
            sorted(_worktree_status._worktree_status(self.work).paths),
            sorted((RENAMED_FILE, SEED_FILE)),
        )

    def _assert_suppressed_entry_refuses(self, index_flag: str) -> None:
        """One suppressed entry: named as a path, and not a proof of clean."""
        self.write(SEED_FILE, AGENT_EDIT)
        self.git(UPDATE_INDEX, index_flag, SEED_FILE)
        cleared = index_flag.replace("--", "--no-", 1)
        self.addCleanup(self.git, UPDATE_INDEX, cleared, SEED_FILE)

        self.assertEqual(self.git(GIT_STATUS, PORCELAIN), "")

        status = _worktree_status._worktree_status(self.work)

        # Named, so a refusal can tell an operator which entry to clear -- and
        # so the callers that refuse on what git listed refuse on it too.
        self.assertIn(SEED_FILE, status.paths)
        self.assertIn(SEED_FILE, _worktree_status._worktree_dirty_files(self.work))
        # Withheld, since nothing here established what the rest of the tree is.
        self.assertFalse(status.readable)


class CommittedPathFlagOverrideTest(_RealRepoMixin, unittest.TestCase):
    """`_committed_paths_since` reports what a caller reading defaults misses.

    Two ways it would: a local knob that hides a whole class of change, and a
    path whose bytes a strict decode will not take at all -- and the second
    does not answer wrongly, it raises out of `subprocess` before the probe
    returns anything.
    """

    def test_a_moved_gitlink_survives_the_local_knob(self) -> None:
        # A gitlink is a committed path like any other, and pointing one at a
        # different commit is a change to what the branch builds. With
        # `diff.ignoreSubmodules=all` planted, a caller permitting exactly one
        # path is told about that path alone and publishes the rest unseen.
        self.write(PLAN_PATH, PLAN_TEXT)
        self.commit(PLAN_PATH)
        # Staged straight into the index and committed from there: an `add -A`
        # over a gitlink whose directory is not checked out stages its removal.
        self.git(
            "update-index", "--add",
            "--cacheinfo", f"{GITLINK_MODE},{self.base_sha},{GITLINK_PATH}",
        )
        self.git("commit", QUIET_FLAG, MESSAGE_FLAG, GITLINK_PATH)
        head_sha = self.git("rev-parse", "HEAD").strip()
        self.git(GIT_CONFIG, "diff.ignoreSubmodules", "all")

        hidden = self.git(
            GIT_DIFF, NAMES_ONLY, f"{self.base_sha}...{head_sha}",
        )
        self.assertNotIn(GITLINK_PATH, hidden)

        changed = probes._committed_paths_since(
            self.work, self.base_sha, head_sha,
        )

        self.assertEqual(sorted(changed), [PLAN_PATH, GITLINK_PATH])

    def test_an_undecodable_path_is_reported(self) -> None:
        # A repository path is bytes, and nothing makes it UTF-8. Decoded
        # strictly, it raises inside `subprocess` before the probe can hand
        # anything back -- so the tick dies where it should have parked the
        # artifact this extra path makes invalid, and an agent that wants a
        # publication check never to answer only has to commit one.
        self.write(PLAN_PATH, PLAN_TEXT)
        self.write(UNDECODABLE_PATH, "bytes git hands back as they are\n")
        head_sha = self.commit(PLAN_PATH)

        changed = probes._committed_paths_since(
            self.work, self.base_sha, head_sha,
        )

        # Both paths come back, so the caller permitting exactly one refuses.
        self.assertIn(PLAN_PATH, changed)
        self.assertEqual(len(changed), 2)


class CommittedPathBaseTest(_RealRepoMixin, unittest.TestCase):
    """`_committed_paths_since` measures from the caller's own base commit."""

    def test_a_repointed_remote_ref_hides_nothing(self) -> None:
        # The attack the object id exists for: a linked worktree shares the
        # refs of the clone it was made from, so the agent commits its code,
        # repoints `<remote>/<base>` at that commit, and commits the one path
        # it was permitted. Measured against the ref, the branch carries only
        # the plan -- and the push would carry both commits.
        self.write(CODE_PATH, "print('shipped without review')\n")
        code_sha = self.commit(CODE_PATH)
        self.write(PLAN_PATH, PLAN_TEXT)
        head_sha = self.commit(PLAN_PATH)
        self.git("update-ref", REMOTE_BASE_REF, code_sha)

        hidden = self.git(
            GIT_DIFF, NAMES_ONLY, f"{REMOTE_BASE_REF}...{head_sha}",
        )
        self.assertNotIn(CODE_PATH, hidden)

        changed = probes._committed_paths_since(
            self.work, self.base_sha, head_sha,
        )

        self.assertEqual(sorted(changed), [CODE_PATH, PLAN_PATH])


class PlanEntryKindTest(_RealRepoMixin, unittest.TestCase):
    """`_revision_contains_path` answers for the kind of entry, not just the path.

    Git can hold four different things at `plans/issue-N.md`, and three of
    them resolve as objects the caller never asked for. Each case proves the
    trap first the way this module always does: `cat-file -e` succeeds on
    them, so "the object is there" would publish a branch carrying no plan.
    """

    def test_a_symlink_at_the_path_is_not_the_plan(self) -> None:
        # A symlink is a blob at exactly the permitted path, so the object
        # resolves and the diff names one file -- while what a reviewer opens
        # there is whatever it points at, anywhere on the host.
        self.write(CODE_PATH, "print('shipped without review')\n")
        (self.work / PLAN_PATH).parent.mkdir(parents=True, exist_ok=True)
        (self.work / PLAN_PATH).symlink_to(f"../{CODE_PATH}")
        linked_sha = self.commit(PLAN_PATH)

        self.assertEqual(
            self.git("cat-file", "-e", f"{linked_sha}:{PLAN_PATH}"), "",
        )

        self.assertFalse(
            probes._revision_contains_path(self.work, linked_sha, PLAN_PATH),
        )

    def test_a_gitlink_at_the_path_is_not_the_plan(self) -> None:
        # The other entry that resolves at the path: a submodule pointer. Its
        # object is a commit nothing here ever fetches, so the plan a reviewer
        # was promised is not in this branch at all.
        self.git(
            "update-index", "--add",
            "--cacheinfo", f"{GITLINK_MODE},{self.base_sha},{PLAN_PATH}",
        )
        self.git("commit", QUIET_FLAG, MESSAGE_FLAG, PLAN_PATH)
        gitlink_sha = self.git("rev-parse", "HEAD").strip()

        self.assertEqual(
            self.git("cat-file", "-e", f"{gitlink_sha}:{PLAN_PATH}"), "",
        )

        self.assertFalse(
            probes._revision_contains_path(self.work, gitlink_sha, PLAN_PATH),
        )

    def test_a_committed_plan_is_the_plan(self) -> None:
        # The reading the refusals above are only meaningful against.
        self.write(PLAN_PATH, PLAN_TEXT)
        plan_sha = self.commit(PLAN_PATH)

        self.assertTrue(
            probes._revision_contains_path(self.work, plan_sha, PLAN_PATH),
        )


class PublishedTipAncestryTest(_RealRepoMixin, unittest.TestCase):
    """`_commit_contains` answers what a lease cannot: what a push takes away.

    A lease proves only that a ref has not moved since it was read. Whether the
    commit replacing it KEEPS what is there is a different question, and the
    inherited PR branch is where it bites: a round opens on the dev's tip and a
    plan committed on top of it contains that tip, but a plan committed after a
    reset to base passes every other check -- clean tree, one path against base,
    the plan in HEAD -- while publishing it deletes the commits the PR carries.
    """

    def test_a_plan_on_the_inherited_tip_contains_it(self) -> None:
        inherited = self._inherited_pr_tip()
        self.write(PLAN_PATH, PLAN_TEXT)
        plan_sha = self.commit(PLAN_PATH)

        self.assertTrue(
            probes._commit_contains(self.work, inherited, plan_sha),
        )

    def test_a_plan_over_a_reset_branch_does_not(self) -> None:
        inherited = self._inherited_pr_tip()
        self.git("reset", "--hard", self.base_sha)
        self.write(PLAN_PATH, PLAN_TEXT)
        plan_sha = self.commit(PLAN_PATH)

        # Every other reading still passes, which is the whole problem: the
        # branch against base is exactly the one permitted path.
        self.assertEqual(
            probes._committed_paths_since(self.work, self.base_sha, plan_sha),
            [PLAN_PATH],
        )

        self.assertFalse(
            probes._commit_contains(self.work, inherited, plan_sha),
        )

    def test_a_tip_this_host_never_had_does_not(self) -> None:
        # The reviewer's own push, seen from a clone that has not fetched it:
        # unresolvable here, and not contained by anything here either.
        self.write(PLAN_PATH, PLAN_TEXT)
        plan_sha = self.commit(PLAN_PATH)

        self.assertFalse(
            probes._commit_contains(self.work, UNKNOWN_SHA, plan_sha),
        )

    def _inherited_pr_tip(self) -> str:
        """The dev commit an issue arrives at discussion carrying on its branch."""
        self.write(CODE_PATH, "print('the PR this issue arrived with')\n")
        return self.commit(CODE_PATH)


class ReplacedObjectTest(_RealRepoMixin, unittest.TestCase):
    """The probes read the commits that exist, not their stand-ins."""

    def test_a_replaced_base_hides_nothing(self) -> None:
        # `git replace` is a ref, not config: written into the clone the
        # worktree shares, it makes every reader serve a synthetic commit
        # under the base's object id. Give that stand-in the code commit's
        # tree and the honest diff of the honest SHAs reports only the plan --
        # while the push, which names the real HEAD, carries both commits.
        code_sha, head_sha = self._code_then_plan()
        synthetic = self.git(
            "commit-tree", f"{code_sha}{TREE_OF}", MESSAGE_FLAG, "synthetic base",
        ).strip()
        self.git("replace", self.base_sha, synthetic)

        hidden = self.git(
            GIT_DIFF, NAMES_ONLY, f"{self.base_sha}...{head_sha}",
        )
        self.assertNotIn(CODE_PATH, hidden)

        changed = probes._committed_paths_since(
            self.work, self.base_sha, head_sha,
        )

        self.assertEqual(sorted(changed), [CODE_PATH, PLAN_PATH])

    def test_a_grafted_base_hides_nothing(self) -> None:
        # The older mechanism, and the one `GIT_NO_REPLACE_OBJECTS` does not
        # cover: lines in `info/grafts` rewrite a commit's parents, which
        # moves the merge base of the three-dot diff onto the code commit and
        # leaves the same lie behind. The second line makes the code commit a
        # grafted root, which keeps the rewritten history acyclic: base and
        # code each claiming the other as a parent is a graph git can traverse
        # to no merge base at all, depending on how their timestamps fall.
        code_sha, head_sha = self._code_then_plan()
        self._plant_graft(f"{self.base_sha} {code_sha}", code_sha)

        hidden = self.git(
            GIT_DIFF, NAMES_ONLY, f"{self.base_sha}...{head_sha}",
        )
        self.assertNotIn(CODE_PATH, hidden)

        changed = probes._committed_paths_since(
            self.work, self.base_sha, head_sha,
        )

        self.assertEqual(sorted(changed), [CODE_PATH, PLAN_PATH])

    def test_a_replaced_head_cannot_fake_the_plan(self) -> None:
        # The same trick pointed at the other probe: a commit that DELETED the
        # plan, replaced by one whose tree still carries it. The tree read is
        # what tells a written plan from a deleted one, so believing the
        # stand-in would publish a deletion as the agreed design.
        self._code_then_plan()
        self.git("rm", "-q", PLAN_PATH)
        deleted_sha = self.commit("delete the plan")
        synthetic = self.git(
            "commit-tree", f"{deleted_sha}~1{TREE_OF}", MESSAGE_FLAG, "synthetic head",
        ).strip()
        self.git("replace", deleted_sha, synthetic)

        self.assertIn(
            PLAN_PATH,
            self.git("ls-tree", NAMES_ONLY, deleted_sha, "--", PLAN_PATH),
        )

        self.assertFalse(
            probes._revision_contains_path(self.work, deleted_sha, PLAN_PATH),
        )

    def _code_then_plan(self) -> tuple[str, str]:
        """Commit the code the round may not publish, then the plan it may."""
        self.write(CODE_PATH, "print('shipped without review')\n")
        code_sha = self.commit(CODE_PATH)
        self.write(PLAN_PATH, PLAN_TEXT)
        return code_sha, self.commit(PLAN_PATH)

    def _plant_graft(self, *lines: str) -> None:
        """Write the graft file an agent with the git dir can write."""
        graft_file = self.work / GRAFT_FILE
        graft_file.parent.mkdir(parents=True, exist_ok=True)
        graft_file.write_text("".join(f"{line}\n" for line in lines))


if __name__ == "__main__":
    unittest.main()
