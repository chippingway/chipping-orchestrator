# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The repository, remote, and base branch a clone's GitHub remote implies."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from orchestrator.service.clone_defaults import clone_entry
from orchestrator.service.repos_entry import RepositoryEntry
from orchestrator.service.validation import validate_clone
from tests.service.service_test_support import refusal
from tests.support.checkouts import committed_checkout
from tests.support.git import _run_git

_ACME = "acme/api"
_ACME_URL = "https://github.com/acme/api.git"
_FORK_URL = "git@github.com:alice/api.git"
_ALIAS_URL = "git@github-work:acme/api.git"
# GitHub's SSH endpoint over the HTTPS port, for networks that block port 22.
_HTTPS_PORT_SSH_URL = "ssh://git@ssh.github.com:443/acme/api.git"
_ORIGIN = "origin"
_UPSTREAM = "upstream"
_TRUNK = "trunk"
_REMOTE = "remote"
_CHECKOUT = "checkout"
_QUIET = "-q"
_ADVICE = "add one, or say which repository and remote to use"


class _CloneCase(unittest.TestCase):
    """A committed clone on `main`, with no remote until a test adds one.

    Git runs detached from the host's global and system config, so no
    `insteadOf` or default the operator carries can rewrite what a remote
    says.
    """

    def setUp(self) -> None:
        self.enterContext(patch.dict(os.environ, {
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_SYSTEM": os.devnull,
        }))
        self._scratch = Path(self.enterContext(tempfile.TemporaryDirectory())).resolve()
        self._clone = committed_checkout(self._scratch / "clone")

    def _add_remote(self, name: str, url: str, default_branch: str | None = None) -> None:
        """Add a remote, recording `default_branch` as its HEAD the way a clone does."""
        _run_git(_REMOTE, "add", name, url, cwd=self._clone)
        if default_branch is not None:
            branch = f"refs/remotes/{name}/{default_branch}"
            _run_git("update-ref", branch, "HEAD", cwd=self._clone)
            _run_git("symbolic-ref", f"refs/remotes/{name}/HEAD", branch, cwd=self._clone)


class DerivedEntryTest(_CloneCase):
    """A clone alone answers for its whole entry.

    The repository comes from its GitHub remote, the base branch from that
    remote's recorded default branch, else the branch checked out, and a
    remote other than `origin` is recorded under its own name, which the
    rendered entry then carries.
    """

    def test_origin_with_its_default_branch(self) -> None:
        self._add_remote(_ORIGIN, _ACME_URL, _TRUNK)

        entry = clone_entry(self._clone)

        self.assertEqual(entry, RepositoryEntry(_ACME, self._clone, _TRUNK))
        self.assertEqual(entry.render(), f"{_ACME}|{self._clone}|{_TRUNK}")

    def test_a_non_origin_remote_is_recorded(self) -> None:
        self._add_remote(_ORIGIN, "https://gitlab.com/acme/api.git")
        self._add_remote(_UPSTREAM, _HTTPS_PORT_SSH_URL, _TRUNK)

        entry = clone_entry(self._clone)

        written = f"{_ACME}|{self._clone}|{_TRUNK}|{_UPSTREAM}"
        self.assertEqual(entry, RepositoryEntry(_ACME, self._clone, _TRUNK, _UPSTREAM))
        self.assertEqual(entry.render(), written)

    def test_the_named_checkout_supplies_the_entry(self) -> None:
        # `link/../clone` names the checkout beside the link's target, which
        # points at another repository than the one beside the link.
        self._add_remote(_ORIGIN, _ACME_URL)
        target = self._scratch / "physical" / "dir"
        target.mkdir(parents=True)
        beside_target = committed_checkout(self._scratch / "physical" / "clone")
        _run_git(_REMOTE, "add", _ORIGIN, "git@github.com:acme/other.git", cwd=beside_target)
        (self._scratch / "link").symlink_to(target, target_is_directory=True)

        clone = validate_clone(str(self._scratch / "link" / ".." / "clone"))

        self.assertEqual(clone_entry(clone), RepositoryEntry("acme/other", beside_target, "main"))

    def test_the_checked_out_branch_answers(self) -> None:
        # With no default branch recorded for the remote.
        self._add_remote(_ORIGIN, _ACME_URL)
        _run_git(_CHECKOUT, _QUIET, "-b", "release/2.x", cwd=self._clone)

        self.assertEqual(clone_entry(self._clone).base_branch, "release/2.x")

    def test_a_linked_worktree_answers_like_its_clone(self) -> None:
        # Remotes and remote-tracking refs are shared; the checked-out branch
        # is the worktree's own.
        self._add_remote(_ORIGIN, _ACME_URL)
        linked = self._scratch / "linked"
        _run_git("worktree", "add", _QUIET, "-b", "wt-branch", str(linked), cwd=self._clone)

        self.assertEqual(clone_entry(linked), RepositoryEntry(_ACME, linked, "wt-branch"))
        self._add_remote(_UPSTREAM, "git@github.com:acme/other.git", _TRUNK)
        _run_git(_REMOTE, "remove", _ORIGIN, cwd=self._clone)
        self.assertEqual(
            clone_entry(linked), RepositoryEntry("acme/other", linked, _TRUNK, _UPSTREAM),
        )

    def test_an_insteadof_rewrite_applies(self) -> None:
        _run_git("config", "url.https://github.com/.insteadOf", "gh:", cwd=self._clone)
        self._add_remote(_ORIGIN, "gh:acme/api")

        self.assertEqual(clone_entry(self._clone).repository, _ACME)

    def test_a_detached_head_needs_a_base_branch(self) -> None:
        # With no default branch recorded either, nothing names one.
        self._add_remote(_ORIGIN, _ACME_URL)
        _run_git(_CHECKOUT, _QUIET, "--detach", cwd=self._clone)

        self.assertEqual(
            refusal(clone_entry, self._clone),
            f"{self._clone} records no default branch for origin and has no branch "
            "checked out; give the branch pull requests target",
        )
        # A base branch the caller chose is not derived at all.
        self.assertEqual(clone_entry(self._clone, base_branch="main").base_branch, "main")


class RemoteChoiceTest(_CloneCase):
    """Which remote an entry records, and when the clone cannot say.

    `origin` wins whenever it points at GitHub, then the only remote that
    does. A repository the caller chose narrows that to the remotes naming it,
    and an `origin` whose URL names no GitHub repository stands for it when
    none does. Several candidates, or none, are refused rather than guessed.
    """

    def test_origin_wins_among_github_remotes(self) -> None:
        self._add_remote("fork", _FORK_URL)
        self._add_remote(_ORIGIN, _ACME_URL)

        self.assertEqual(clone_entry(self._clone).remote, _ORIGIN)

    def test_no_github_remote_is_refused(self) -> None:
        nothing = f"no remote of {self._clone} points at a repository on GitHub; {_ADVICE}"
        self.assertEqual(refusal(clone_entry, self._clone), nothing)
        self._add_remote(_ORIGIN, _ALIAS_URL)
        self.assertEqual(refusal(clone_entry, self._clone), nothing)

    def test_several_non_origin_remotes_are_refused(self) -> None:
        self._add_remote("fork", _FORK_URL)
        self._add_remote(_UPSTREAM, _ACME_URL)

        self.assertEqual(
            refusal(clone_entry, self._clone),
            f"remotes fork, {_UPSTREAM} of {self._clone} all point at GitHub and none "
            "is origin; say which repository or remote to use",
        )
        # Naming the repository picks the remote that points at it.
        chosen = clone_entry(self._clone, repository="ACME/api")
        self.assertEqual((chosen.repository, chosen.remote), ("ACME/api", _UPSTREAM))

    def test_a_chosen_repository_skips_a_fork(self) -> None:
        # An origin naming another repository does not stand for this one.
        self._add_remote(_ORIGIN, _FORK_URL)
        self._add_remote(_UPSTREAM, _ACME_URL)

        self.assertEqual(clone_entry(self._clone, repository=_ACME).remote, _UPSTREAM)
        self.assertEqual(
            refusal(clone_entry, self._clone, repository="acme/web"),
            f"no remote of {self._clone} points at acme/web on GitHub; {_ADVICE}",
        )

    def test_an_unread_origin_takes_the_repository(self) -> None:
        self._add_remote(_ORIGIN, _ALIAS_URL, _TRUNK)

        self.assertEqual(
            clone_entry(self._clone, repository=_ACME),
            RepositoryEntry(_ACME, self._clone, _TRUNK),
        )


class NamedRemoteTest(_CloneCase):
    """A remote the caller named is used as named, and has to agree."""

    def test_a_named_remote_supplies_its_repository(self) -> None:
        self._add_remote(_ORIGIN, _FORK_URL)
        self._add_remote(_UPSTREAM, _ACME_URL, _TRUNK)

        self.assertEqual(
            clone_entry(self._clone, remote=_UPSTREAM),
            RepositoryEntry(_ACME, self._clone, _TRUNK, _UPSTREAM),
        )

    def test_an_unread_remote_needs_the_repository(self) -> None:
        self._add_remote("work", _ALIAS_URL)

        self.assertEqual(
            refusal(clone_entry, self._clone, remote="work"),
            f"remote 'work' of {self._clone} does not point at a GitHub repository; "
            "give the repository as owner/name",
        )
        self.assertEqual(clone_entry(self._clone, remote="work", repository=_ACME).repository, _ACME)

    def test_a_missing_or_other_remote_is_refused(self) -> None:
        self._add_remote(_ORIGIN, _FORK_URL)

        self.assertEqual(
            refusal(clone_entry, self._clone, remote=_UPSTREAM),
            f"{self._clone} has no remote named 'upstream'",
        )
        self.assertEqual(
            refusal(clone_entry, self._clone, remote=_ORIGIN, repository=_ACME),
            f"remote 'origin' of {self._clone} points at alice/api on GitHub, not {_ACME}",
        )


if __name__ == "__main__":
    unittest.main()
