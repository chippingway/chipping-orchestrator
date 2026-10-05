# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What counts as a git checkout for a target: a working tree git opens."""

import os
import tempfile
import unittest
from pathlib import Path
from types import MappingProxyType
from typing import NamedTuple

from tests.config import (
    config_reload_helpers as _reload,
    config_test_support as _support,
    config_test_values as _config_cases,
)
from tests.support.git import (
    _append_git_config,
    _claim_work_tree,
    _foreign_owner_settings,
    _run_git,
)

_TARGET_ROOT_ENV = "TARGET_REPO_ROOT"
_CLONE = "clone"
_LINKED = "linked"
_DOT_GIT = ".git"
_ADD_WORKTREE = ("worktree", "add")
_BARE_REPOSITORY = "is a bare repository"
_UNOPENABLE = "has git metadata git cannot open"
_NO_METADATA = "has no .git of its own"
_UNSURE_BARE = "[core]\n\tbare = maybe\n"
# Configs git refuses to open a checkout under, appended to a fresh clone's
# own: bare, a core.bare that is not a boolean, a line git cannot parse, a
# repository format this git predates, and an extension it does not know.
_UNOPENABLE_CONFIGS = MappingProxyType({
    "configured-bare": "[core]\n\tbare = true\n",
    "unsure-bare": _UNSURE_BARE,
    "malformed-config": "[core\n",
    "future-format": "[core]\n\trepositoryformatversion = 2\n",
    "unknown-extension": (
        "[core]\n\trepositoryformatversion = 1\n[extensions]\n\tnoSuchExtension = true\n"
    ),
})
# A value git continues onto the next line, which it reads as `false`: `\x5c`
# is the backslash that ends a continued line.
_LINE_CONTINUATION = "\x5c\n"
_CONTINUED_FALSE = f"[core]\n\tbare = fal{_LINE_CONTINUATION}se\n"


class _Unusable(NamedTuple):
    """One path that is not a checkout, and the refusal that names it."""

    case: str
    target: Path
    problem: str

    @property
    def slug(self) -> str:
        name = self.case.replace(" ", "-")
        return f"unusable/{name}"

    @property
    def refusal(self) -> str:
        return f"orchestrator: REPOS target {self.target} for {self.slug!r} {self.problem}"


def _committed_checkout(root: Path) -> Path:
    """A clone at `root` with one commit, so worktrees can be added to it."""
    _support.make_checkout(root)
    _run_git("add", "pyproject.toml", cwd=root)
    _run_git("commit", "-m", "init", cwd=root)
    return root


def _usable_targets(scratch: Path) -> list[Path]:
    """Every layout a target may have, the ordinary clone first.

    Beside the clone: a worktree linked to it, whose `.git` is a file; one
    whose detached HEAD holds a commit id rather than a ref; one added to a
    bare clone, whose shared config sets `core.bare` while the worktree still
    has a working tree; and a clone whose config continues a value onto the
    next line.
    """
    clone = _committed_checkout(scratch / _CLONE)
    bare_clone = scratch / "origin.git"
    _run_git(*_ADD_WORKTREE, str(scratch / _LINKED), cwd=clone)
    _run_git(*_ADD_WORKTREE, "--detach", str(scratch / "detached"), cwd=clone)
    _run_git("clone", "--bare", str(clone), str(bare_clone), cwd=scratch)
    _run_git(*_ADD_WORKTREE, str(scratch / "bare-linked"), cwd=bare_clone)
    continued = _append_git_config(_support.make_checkout(scratch / "continued"), _CONTINUED_FALSE)
    return [clone, scratch / _LINKED, scratch / "detached", scratch / "bare-linked", continued]


def _lay_out_broken_metadata(scratch: Path) -> None:
    """Directories with a `.git` git refuses to open as a checkout."""
    (scratch / "gutted" / _DOT_GIT).mkdir(parents=True)
    (scratch / "dangling").mkdir()
    (scratch / "dangling" / _DOT_GIT).write_text("gitdir: ../missing\n")
    (scratch / "tight-pointer").mkdir()
    linked_git_dir = scratch / _CLONE / _DOT_GIT / "worktrees" / _LINKED
    (scratch / "tight-pointer" / _DOT_GIT).write_text(f"gitdir:{linked_git_dir}\n")
    corrupt = _support.make_checkout(scratch / "corrupt-head")
    (corrupt / _DOT_GIT / "HEAD").write_text("not a ref\n")
    for name, config_text in _UNOPENABLE_CONFIGS.items():
        _append_git_config(_support.make_checkout(scratch / name), config_text)


def _unusable_targets(scratch: Path) -> list[_Unusable]:
    """Each kind of path that is not a checkout, beside the targets in `scratch`."""
    (scratch / "file").write_text("not a checkout\n")
    (scratch / "plain").mkdir()
    (scratch / _CLONE / "nested").mkdir()
    _run_git("init", "--bare", str(scratch / "bare.git"), cwd=scratch)
    _lay_out_broken_metadata(scratch)
    # Git reads the shared config for a linked worktree too, so a core.bare
    # that is not a boolean there stops it as surely as in the clone.
    unsure_origin = _committed_checkout(scratch / "unsure-origin")
    _run_git(*_ADD_WORKTREE, str(scratch / "unsure-linked"), cwd=unsure_origin)
    _append_git_config(unsure_origin, _UNSURE_BARE)
    return [
        _Unusable("missing path", scratch / "missing", "does not exist"),
        _Unusable("file", scratch / "file", "is not a directory"),
        _Unusable("plain directory", scratch / "plain", _NO_METADATA),
        _Unusable("directory inside a clone", scratch / _CLONE / "nested", _NO_METADATA),
        _Unusable("bare repository", scratch / "bare.git", _BARE_REPOSITORY),
        _Unusable("clone configured bare", scratch / "configured-bare", _BARE_REPOSITORY),
        _Unusable("core.bare not a boolean", scratch / "unsure-bare", _UNOPENABLE),
        _Unusable("linked worktree of an unsure core.bare", scratch / "unsure-linked", _UNOPENABLE),
        _Unusable("malformed config", scratch / "malformed-config", _UNOPENABLE),
        _Unusable("unsupported repository format", scratch / "future-format", _UNOPENABLE),
        _Unusable("unknown repository extension", scratch / "unknown-extension", _UNOPENABLE),
        _Unusable("git directory without HEAD", scratch / "gutted", _UNOPENABLE),
        _Unusable("corrupted HEAD", scratch / "corrupt-head", _UNOPENABLE),
        _Unusable("dangling worktree pointer", scratch / "dangling", _UNOPENABLE),
        _Unusable("gitdir pointer without its space", scratch / "tight-pointer", _UNOPENABLE),
    ]


def _claimed_targets(scratch: Path) -> list[_Unusable]:
    """Targets a repository around them names as its work tree.

    Each sits in a repository whose core.worktree names it, under a path
    holding the `:` git splits a discovery ceiling list on, so git finds that
    repository whenever it is left to discover one: only a check asking the
    target's own `.git` refuses them. One has no `.git`, the other a corrupted
    one.
    """
    plain = _claim_work_tree(scratch / "claims:plain", "target")
    plain.mkdir()
    corrupt = _support.make_checkout(_claim_work_tree(scratch / "claims:corrupt", "target"))
    (corrupt / _DOT_GIT / "HEAD").write_text("not a ref\n")
    return [
        _Unusable("claimed plain directory", plain, _NO_METADATA),
        _Unusable("claimed corrupted HEAD", corrupt, _UNOPENABLE),
    ]


class TargetCheckoutTest(unittest.TestCase):
    """A target is a directory git opens as the top of a working tree.

    That is an ordinary clone or a linked worktree whatever valid spelling its
    metadata takes, and the `.git` git opens has to be the target's own: a
    repository around it never answers for it, even one naming it as its work
    tree. Git also has to open it from inside, where it declines a checkout
    another user owns unless `safe.directory` trusts it, as it will decline
    every later command there. Every other path aborts the import -- before
    anything can connect -- naming the setting, the path, and the repository
    it was meant to be, and one abort names every unusable target rather than
    the first.
    """

    def setUp(self) -> None:
        self._scratch = Path(self.enterContext(tempfile.TemporaryDirectory()))

    def test_clones_and_linked_worktrees_are_targets(self) -> None:
        targets = _usable_targets(self._scratch)
        config = _reload.load_config({_config_cases._REPOS_ENV: ";".join(
            f"usable/{index}|{target}|main" for index, target in enumerate(targets)
        )})

        self.assertEqual(
            [spec.target_root for spec in config.default_repo_specs()], targets,
        )

    def test_every_unusable_target_is_named(self) -> None:
        clone = _usable_targets(self._scratch)[0]
        unusable = _unusable_targets(self._scratch)
        lines = _reload.config_error_message({_config_cases._REPOS_ENV: ";".join([
            f"{_config_cases._ALPHA_REPO}|{clone}|main",
            *(f"{target.slug}|{target.target}|main" for target in unusable),
        ])}).splitlines()

        # One line per unusable target, so the clone beside them is not named.
        self.assertEqual(len(lines), len(unusable), lines)
        for line, target in zip(lines, unusable, strict=True):
            with self.subTest(case=target.case):
                self.assertTrue(line.startswith(target.refusal), line)

    def test_enclosing_repository_never_answers(self) -> None:
        claimed = _claimed_targets(self._scratch)
        lines = _reload.config_error_message({_config_cases._REPOS_ENV: ";".join(
            f"{target.slug}|{target.target}|main" for target in claimed
        )}).splitlines()

        self.assertEqual(len(lines), len(claimed), lines)
        for line, target in zip(lines, claimed, strict=True):
            with self.subTest(case=target.case):
                self.assertTrue(line.startswith(target.refusal), line)

    def test_another_users_checkout_is_refused(self) -> None:
        foreign = _foreign_owner_settings(self._scratch)
        if foreign is None:
            self.skipTest("this git cannot be made to read a checkout as another user's")
        trusted = _support.make_checkout(self._scratch / "trusted")
        untrusted = _support.make_checkout(self._scratch / "untrusted")
        message = _reload.config_error_message({
            **foreign,
            "GIT_CONFIG_COUNT": "1",
            "GIT_CONFIG_KEY_0": "safe.directory",
            "GIT_CONFIG_VALUE_0": os.path.realpath(trusted),
            _config_cases._REPOS_ENV: f"owners/trusted|{trusted}|main;owners/untrusted|{untrusted}|main",
        })

        # Only the checkout no `safe.directory` entry trusts is named.
        self.assertTrue(message.startswith(
            f"orchestrator: REPOS target {untrusted} for 'owners/untrusted' "
            "is a checkout git refuses to open from inside it (",
        ), message)
        self.assertEqual(len(message.splitlines()), 1, message)

    def test_line_breaks_stay_in_a_target_path(self) -> None:
        # Git writes the work tree's path raw, so a line break inside it is a
        # character of the developer target rather than the end of git's
        # answer.
        for name in _config_cases._LINE_BREAKING_NAMES:
            with self.subTest(name=name):
                target = _support.make_checkout(self._scratch / name)
                config = _reload.load_config({
                    "REPO": _config_cases._LEGACY_REPO,
                    _TARGET_ROOT_ENV: str(target),
                })

                self.assertEqual(
                    _support.only_repo_spec(config.default_repo_specs()).target_root,
                    target,
                )

    def test_developer_target_is_held_to_a_checkout(self) -> None:
        message = _reload.config_error_message({
            "REPO": _config_cases._LEGACY_REPO,
            _TARGET_ROOT_ENV: str(self._scratch),
        })

        self.assertEqual(
            message,
            f"orchestrator: TARGET_REPO_ROOT target {self._scratch} for "
            f"'{_config_cases._LEGACY_REPO}' {_NO_METADATA}, so it is not the "
            "top of a git checkout; point it at a local clone or linked "
            f"worktree of {_config_cases._LEGACY_REPO}",
        )
