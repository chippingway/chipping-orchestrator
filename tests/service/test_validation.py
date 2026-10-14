# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The setup field validators: what each accepts, and the words it refuses with."""

import contextlib
import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from orchestrator.service.validation import (
    AGENTS,
    validate_agent,
    validate_branch,
    validate_clone,
    validate_logins,
    validate_repository,
)
from tests.service.service_test_support import refusal
from tests.support.checkouts import committed_checkout
from tests.support.git import _run_git

_CLONE_ADVICE = "give the top of a local clone or linked worktree"
_NOT_TOP = "has no .git of its own, so it is not the top of a git checkout"
_LINKED = "linked"
_UP = ".."
_BRANCH_ADVICE = "name the branch pull requests target, such as main"

# Branch names git takes, and ones it refuses, rule by rule; git itself is
# asked about each too, so the validator cannot drift from what it mirrors.
_BRANCHES = ("main", "release/2.x", "release;2.x", "a|b", "foo@bar", "x/HEAD", "foo.lock.x", "\u00fcn\u00efcode")
_NOT_BRANCHES = (
    "feature branch", "-foo", "foo.", "foo/", "/foo", "foo//bar", ".foo", "foo/.bar", "foo.lock",
    "foo.lock/bar", "foo..bar", "foo@{bar", "@{-1}", "foo~1", "foo^", "foo:bar", "foo?", "foo*",
    "foo[", r"foo\bar", "foo\tbar", "foo\x7f",
)


# A path to refuse, and each error the refusal may carry for it.
_Unwalkable = tuple[str, tuple[str, ...]]


def _unwalkable_paths(clone: Path) -> tuple[_Unwalkable, ...]:
    """Paths whose `..` steps out of no directory, and the errors that may name each.

    A path failing at its first component is named by that component. Past it,
    Python 3.12's strict `realpath` names the whole path it was handed, and
    later versions the component the lookup failed on, so either is accepted.
    """
    missing = clone / "missing"
    manifest = clone / "pyproject.toml"
    inner = manifest / "inner"
    file_named = f"Not a directory: '{manifest}'"
    return (
        (str(missing / _UP), (f"No such file or directory: '{missing}'",)),
        (str(manifest / _UP), (file_named,)),
        (str(inner / _UP), (file_named, f"Not a directory: '{inner}'")),
    )


class _ClonesCase(unittest.TestCase):
    """A committed clone and a worktree linked to it, in a scratch directory."""

    def setUp(self) -> None:
        self._scratch = Path(self.enterContext(tempfile.TemporaryDirectory())).resolve()
        self._clone = committed_checkout(self._scratch / "clone")
        self._linked = self._scratch / _LINKED
        _run_git("worktree", "add", "-q", str(self._linked), cwd=self._clone)


class CloneValidatorTest(_ClonesCase):
    """A clone is the top of a checkout git opens, named by its absolute path.

    An ordinary clone and a linked worktree pass, spelled absolutely, under
    `~`, or relative to the current directory. Anything else is refused with
    the configuration's own reason for the path and what to give instead.
    """

    def test_checkouts_pass_however_spelled(self) -> None:
        home = {"HOME": str(self._scratch)}
        self.enterContext(patch.dict(os.environ, home))
        self.enterContext(contextlib.chdir(self._scratch))
        padded = f"  {self._linked}\n"
        for raw, expected in (
            (str(self._clone), self._clone),
            (padded, self._linked),
            ("~/clone", self._clone),
            (_LINKED, self._linked),
        ):
            with self.subTest(raw=raw):
                self.assertEqual(validate_clone(raw), expected)

    def test_dotdot_steps_out_of_a_symlink(self) -> None:
        # `link/..` is the parent of where the link leads, so the checkout
        # beside its target is the one named, never the one beside the link;
        # a symlink no `..` steps out of keeps its spelling.
        target = self._scratch / "physical" / "dir"
        target.mkdir(parents=True)
        beside_target = committed_checkout(self._scratch / "physical" / "clone")
        (self._scratch / "link").symlink_to(target, target_is_directory=True)
        alias = self._scratch / "alias"
        alias.symlink_to(self._clone, target_is_directory=True)
        for raw, expected in (
            (str(self._scratch / "link" / _UP / "clone"), beside_target),
            (str(alias), alias),
            (str(alias / _UP / _LINKED), self._linked),
        ):
            with self.subTest(raw=raw):
                self.assertEqual(validate_clone(raw), expected)

    def test_other_paths_are_refused(self) -> None:
        (self._scratch / "file").write_text("not a checkout\n")
        (self._scratch / "plain").mkdir()
        (self._clone / "nested").mkdir()
        bare = self._scratch / "bare.git"
        _run_git("init", "-q", "--bare", str(bare), cwd=self._scratch)
        for path, reason in (
            (self._scratch / "missing", "does not exist"),
            (self._scratch / "file", "is not a directory"),
            (self._scratch / "plain", _NOT_TOP),
            (self._clone / "nested", _NOT_TOP),
            (bare, "is a bare repository"),
        ):
            with self.subTest(path=path.name):
                refused = refusal(validate_clone, str(path))
                self.assertTrue(refused.startswith(f"{path} {reason}"), refused)
                self.assertTrue(refused.endswith(f"; {_CLONE_ADVICE} of the repository"), refused)

    def test_a_blank_answer_names_no_clone(self) -> None:
        self.assertEqual(
            refusal(validate_clone, "  "), f"no clone was given; {_CLONE_ADVICE}",
        )


class UnreadableClonePathTest(_ClonesCase):
    """A path the filesystem cannot walk is refused before any checkout check.

    The refusal quotes the answer and the error the walk met, so a clone that
    is left once a bad component is dropped never stands in for it. Only what
    the walk really reads can fail it: an absolute path never consults the
    current directory.
    """

    def test_an_unknown_home_is_refused(self) -> None:
        # `~user` naming no account cannot be expanded at all.
        raw = "~orchestrator-test-no-such-user/clone"
        refused = refusal(validate_clone, f" {raw} ")
        self.assertTrue(refused.startswith(f"{raw!r} cannot be read as a path ("), refused)
        self.assertTrue(refused.endswith(f"); {_CLONE_ADVICE}"), refused)

    def test_a_removed_launch_directory(self) -> None:
        # An absolute clone never asks for the current directory, so it still
        # passes once that directory is gone; only a relative one is refused.
        gone = self._scratch / "gone"
        gone.mkdir()
        self.enterContext(contextlib.chdir(gone))
        gone.rmdir()

        self.assertEqual(validate_clone(str(self._clone)), self._clone)
        refused = refusal(validate_clone, _LINKED)
        self.assertTrue(refused.startswith(f"{_LINKED!r} cannot be read as a path ("), refused)

    def test_no_dotdot_out_of_what_is_not_a_directory(self) -> None:
        # The kernel looks each name up before `..` steps back out of it, so a
        # missing name or a file there fails the path, even though the clone
        # that is left once it is dropped is a checkout. The refusal carries
        # the lookup's own error and the path it names.
        for raw, named in _unwalkable_paths(self._clone):
            with self.subTest(raw=raw):
                refused = refusal(validate_clone, raw)
                self.assertTrue(refused.startswith(f"{raw!r} cannot be read as a path ("), refused)
                self.assertTrue(any(error in refused for error in named), refused)
                self.assertTrue(refused.endswith(f"); {_CLONE_ADVICE}"), refused)


class EntryFieldValidatorTest(unittest.TestCase):
    """A repository is one GitHub owner and one name, joined by one slash;
    a base branch is a name git allows for one, without the blanks around it.
    """

    def test_owner_and_name_pass(self) -> None:
        for raw, expected in (
            ("acme/api", "acme/api"),
            ("  Acme-Labs/api.v2_x \n", "Acme-Labs/api.v2_x"),
        ):
            with self.subTest(raw=raw):
                self.assertEqual(validate_repository(raw), expected)

    def test_other_spellings_are_refused(self) -> None:
        for raw in (
            "", "acme", "acme/", "/api", "acme/api/extra", "acme api/x", "acme/a|b", "acme/.", "acme/..",
        ):
            with self.subTest(raw=raw):
                self.assertEqual(
                    refusal(validate_repository, raw),
                    f"repository {raw!r} is not written owner/name; give a GitHub owner "
                    "and repository name joined by one '/', such as acme/api",
                )

    def test_names_git_allows_pass(self) -> None:
        for branch in _BRANCHES:
            with self.subTest(branch=branch):
                self.assertTrue(self._git_allows(branch))
                self.assertEqual(validate_branch(f" {branch} \n"), branch)

    def test_names_git_refuses_are_refused(self) -> None:
        for branch in _NOT_BRANCHES:
            with self.subTest(branch=branch):
                self.assertFalse(self._git_allows(branch))
                self.assertEqual(
                    refusal(validate_branch, branch),
                    f"{branch!r} is not a name git allows for a branch; {_BRANCH_ADVICE}",
                )

    def test_names_for_head_are_refused(self) -> None:
        # Not asked of git: `--branch` reads `@` as `HEAD`, and only newer
        # versions refuse `HEAD` itself as a branch name.
        for branch in ("HEAD", "@"):
            with self.subTest(branch=branch):
                self.assertEqual(
                    refusal(validate_branch, branch),
                    f"{branch!r} is not a name git allows for a branch; {_BRANCH_ADVICE}",
                )

    def test_a_blank_branch_is_refused(self) -> None:
        for raw in ("", " \t\n"):
            with self.subTest(raw=raw):
                self.assertEqual(refusal(validate_branch, raw), f"no branch was given; {_BRANCH_ADVICE}")

    def _git_allows(self, branch: str) -> bool:
        """Whether git takes ``branch`` for a branch, asked outside every repository."""
        outside = self.enterContext(tempfile.TemporaryDirectory())
        checked = subprocess.run(
            ("git", "check-ref-format", "--branch", branch),
            cwd=outside,
            env={**os.environ, "GIT_CEILING_DIRECTORIES": str(Path(outside).parent)},
            capture_output=True,
            check=False,
        )
        return checked.returncode == 0


class LoginValidatorTest(unittest.TestCase):
    """A login list names at least one GitHub login, read the way config reads it."""

    def test_lists_are_read_in_order_once(self) -> None:
        for raw, expected in (
            ("alice", ("alice",)),
            (" @alice, bob ,alice,, @ bob ", ("alice", "bob")),
            ("renovate[bot],Carol-9", ("renovate[bot]", "Carol-9")),
        ):
            with self.subTest(raw=raw):
                self.assertEqual(validate_logins(raw), expected)

    def test_an_empty_list_is_refused(self) -> None:
        for raw in ("", " , @ ,"):
            with self.subTest(raw=raw):
                self.assertEqual(
                    refusal(validate_logins, raw),
                    f"{raw!r} names no GitHub login; give at least one, separated by commas",
                )

    def test_a_name_that_is_no_login_is_refused(self) -> None:
        for raw, login in (("alice bob", "alice bob"), ("alice;bob", "alice;bob"), ("alice, b/c", "b/c")):
            with self.subTest(raw=raw):
                self.assertEqual(
                    refusal(validate_logins, raw),
                    f"{login!r} is not a GitHub login; separate logins with commas",
                )


class AgentValidatorTest(unittest.TestCase):
    """An agent is a backend the configuration runs, executable on the given PATH."""

    def setUp(self) -> None:
        scratch = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self._bin = scratch / "bin"
        self._bin.mkdir()
        for agent in AGENTS:
            (self._bin / agent).write_text("#!/bin/sh\n")
            (self._bin / agent).chmod(stat.S_IRWXU)
        self._empty = scratch / "empty"
        self._empty.mkdir()

    def test_each_backend_on_the_path_passes(self) -> None:
        directories = (str(self._empty), str(self._bin))
        search_path = os.pathsep.join(directories)
        for agent in AGENTS:
            with self.subTest(agent=agent):
                self.assertEqual(validate_agent(f" {agent} ", search_path), agent)

    def test_another_name_is_refused(self) -> None:
        for raw in ("gpt", "Claude", "codex -m gpt-5.5", ""):
            with self.subTest(raw=raw):
                self.assertEqual(
                    refusal(validate_agent, raw, str(self._bin)),
                    f"agent {raw!r} is not one the orchestrator runs; expected one of "
                    "claude, codex, agy",
                )

    def test_a_backend_off_the_path_is_refused(self) -> None:
        # A file of that name that is not executable is no executable either.
        (self._empty / "codex").write_text("not executable\n")
        for search_path in (str(self._empty), ""):
            with self.subTest(search_path=search_path):
                self.assertEqual(
                    refusal(validate_agent, "codex", search_path),
                    "agent 'codex' has no executable on PATH; install its CLI or add the "
                    "directory holding it to PATH",
                )


if __name__ == "__main__":
    unittest.main()
