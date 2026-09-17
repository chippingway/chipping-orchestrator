# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Subject shape, the subject reads, and PR-title selection on `titles`."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from orchestrator.git import commands
from orchestrator.git.publication import titles
from tests.git.publication.publication_helpers import (
    DEFAULT_REVISION_RANGE,
    FEATURE_PREFIX,
    GIT_HELPER,
    WORKTREE,
    _GitRecorder,
    _spec,
)
from tests.support.fakes import FakeLabel, make_issue

PREFIX_HELPER_ISSUE = 50
GIT_ERROR_ISSUE = 51
REMOTE_ROUTING_ISSUE = 52
TITLE_ISSUE = 53
ISSUE_TITLE = "add a sparkly thing"


class ConventionalSubjectHelperTest(unittest.TestCase):
    """Direct coverage for the regex helper, since the convention list grew
    beyond what the prompts spell out."""

    def test_accepts_basic_types(self) -> None:
        for subject in (
            "feat: add thing",
            "fix: bug",
            "chore: bump dep",
            "docs: tweak",
            "refactor: rename foo",
            "test: cover edge case",
            "perf: speed it up",
            "ci: fix workflow",
        ):
            self.assertTrue(
                titles._is_conventional_subject(subject),
                f"expected conventional: {subject!r}",
            )

    def test_accepts_scope_and_breaking(self) -> None:
        self.assertTrue(titles._is_conventional_subject("feat(api): foo"))
        self.assertTrue(titles._is_conventional_subject("fix!: bar"))
        self.assertTrue(titles._is_conventional_subject("feat(api)!: baz"))

    def test_rejects_non_conventional(self) -> None:
        for subject in (
            "",
            "Add a thing",
            "wip: thing",
            "feat:",  # no subject after colon
            "feat:   ",  # whitespace-only subject
            "Feat: cap type",  # types must be lowercase
            "  feat: leading",  # leading whitespace not accepted
        ):
            self.assertFalse(
                titles._is_conventional_subject(subject),
                f"expected non-conventional: {subject!r}",
            )


class PrefixedSubjectHelperTest(unittest.TestCase):
    """`_is_prefixed_subject` is broader than `_is_conventional_subject`: it
    accepts any lowercase `<token>: <subject>` prefix, so repo-local styles
    survive, while still rejecting prose and bare prefixes."""

    def test_accepts_conventional_and_local_prefixes(self) -> None:
        for subject in (
            "feat: add thing",
            "fix(api)!: drop endpoint",
            "event: add the gala",  # not a Conventional type
            "career: open a role",
            "ui: tweak the spacing",
        ):
            self.assertTrue(
                titles._is_prefixed_subject(subject),
                f"expected prefixed: {subject!r}",
            )

    def test_rejects_prose_and_bare_prefixes(self) -> None:
        for subject in (
            "",
            "updated stuff",  # no colon
            "fixed it",  # no colon
            "Add a thing",  # not prefixed
            "Note: capitalized token",  # token must start lowercase
            "event:",  # no subject after colon
            "event:   ",  # whitespace-only subject
            "  event: leading",  # leading whitespace not accepted
        ):
            self.assertFalse(
                titles._is_prefixed_subject(subject),
                f"expected non-prefixed: {subject!r}",
            )


class FirstCommitSubjectBaseBranchTest(unittest.TestCase):
    """`_first_commit_subject` must compare against `spec.base_branch`, not
    the global `config.BASE_BRANCH`. With `REPOS=...|...|master` and the
    legacy `BASE_BRANCH=main`, the global default would point at the wrong
    remote and either fail or include unrelated commits."""

    def test_uses_per_spec_base_branch(self) -> None:
        git = _GitRecorder("feat: hello\n")
        subject = self._read_subject(git, _spec(base_branch="master"))
        self.assertEqual(subject, "feat: hello")
        self.assertEqual(len(git.calls), 1)
        args, _cwd = git.calls[0]
        # The third positional arg to `_git` is the rev range; it must
        # reference master (the spec's base_branch), not the cached `main`.
        self.assertIn("origin/master..HEAD", args)
        self.assertNotIn(DEFAULT_REVISION_RANGE, args)

    def test_default_spec_still_uses_main(self) -> None:
        # Sanity check: legacy single-repo deployments keep using `main`
        # because the default spec's `base_branch` is `main`.
        git = _GitRecorder()
        self._read_subject(git, _spec())
        args, _cwd = git.calls[0]
        self.assertIn(DEFAULT_REVISION_RANGE, args)

    def test_uses_per_spec_remote_name(self) -> None:
        # Multi-remote target clones (e.g. public `origin` + private fork
        # `private`) need the rev range to reference the configured remote.
        git = _GitRecorder("feat: hi\n")
        self._read_subject(git, _spec(remote_name="private"))
        args, _cwd = git.calls[0]
        self.assertIn("private/main..HEAD", args)
        self.assertNotIn(DEFAULT_REVISION_RANGE, args)

    def _read_subject(self, git: _GitRecorder, spec) -> str:
        with patch.object(commands, GIT_HELPER, git):
            return titles._first_commit_subject(spec, WORKTREE)


class _InferFixtureMixin:
    def _infer(
        self,
        git: _GitRecorder,
        *,
        bug: bool = False,
        spec=None,
        number: int = PREFIX_HELPER_ISSUE,
    ) -> str:
        issue = make_issue(number, title="do a thing")
        if bug:
            issue.labels.append(FakeLabel("bug"))
        with patch.object(commands, GIT_HELPER, git):
            return titles._infer_subject_prefix(
                spec or _spec(),
                WORKTREE,
                issue,
            )


class InferSubjectPrefixTest(unittest.TestCase, _InferFixtureMixin):
    """`_infer_subject_prefix` reads recent base-branch history and reuses a
    dominant repo-local prefix; otherwise it falls back to `fix` for
    bug-labelled issues and `feat` everywhere else."""

    def test_dominant_repo_local_prefix_is_reused(self) -> None:
        # Events repo: `event:` dominates, so the fallback honors it.
        self.assertEqual(
            self._infer(_GitRecorder("event: gala\nevent: meetup\nfeat: tooling\n")),
            "event",
        )

    def test_repo_local_prefix_overrides_bug_label(self) -> None:
        # The repo's own style wins even for a bug-labelled issue -- a repo
        # that doesn't use `fix:` shouldn't suddenly get one.
        self.assertEqual(
            self._infer(_GitRecorder("event: gala\nevent: meetup\n"), bug=True),
            "event",
        )

    def test_conventional_history_keeps_feat_default(self) -> None:
        # When the dominant prefix is itself a Conventional type, defer to
        # the bug/feat heuristic rather than echoing the history prefix.
        self.assertEqual(
            self._infer(_GitRecorder("feat: a\nfix: b\nfeat: c\n")),
            FEATURE_PREFIX,
        )

    def test_conventional_history_bug_label_uses_fix(self) -> None:
        self.assertEqual(
            self._infer(_GitRecorder("feat: a\nfeat: b\n"), bug=True),
            "fix",
        )

    def test_empty_history_falls_back_to_feat(self) -> None:
        self.assertEqual(self._infer(_GitRecorder()), FEATURE_PREFIX)

    def test_unprefixed_history_falls_back_to_feat(self) -> None:
        # History with no `<prefix>:` subjects yields no dominant prefix.
        self.assertEqual(
            self._infer(_GitRecorder("initial commit\nmore work\n")),
            FEATURE_PREFIX,
        )

    def test_prefixes_survive_a_pr_reference_suffix(self) -> None:
        # Landed subjects end in ` (#N)`. Were the scoped, breaking one not
        # counted, `event` and `career` would tie and the newer `event` win.
        history = (
            "event: add the gala (#7)\n"
            "career(jobs)!: open a role (#6)\n"
            "career: close a role (#5)\n"
        )
        self.assertEqual(self._infer(_GitRecorder(history)), "career")


class InferSubjectPrefixGitRoutingTest(unittest.TestCase, _InferFixtureMixin):
    def test_git_error_falls_back_without_crashing(self) -> None:
        git = _GitRecorder(returncode=1, stderr="fatal: bad revision")
        self.assertEqual(
            self._infer(git, number=GIT_ERROR_ISSUE),
            FEATURE_PREFIX,
        )

    def test_reads_per_spec_base_and_remote(self) -> None:
        git = _GitRecorder("event: x\n")
        self._infer(
            git,
            spec=_spec(base_branch="master", remote_name="private"),
            number=REMOTE_ROUTING_ISSUE,
        )
        args, _cwd = git.calls[0]
        # The history log targets `<remote>/<base>`, honoring the spec.
        self.assertIn("private/master", args)
        self.assertNotIn("origin/main", args)


class PrTitleSelectionTest(unittest.TestCase):
    """`_pr_title_from_commit_or_issue` prefers the agent's own commit
    subject, then the issue title when either already carries a reusable
    `<prefix>:` form, and only otherwise synthesizes one from the fallback
    prefix. The title stays free of the issue reference -- the `Resolves #<n>`
    line in the PR body carries traceability."""

    def test_reusable_commit_subject_is_reused(self) -> None:
        # The subject comes back as the agent wrote it, less the tracked
        # issue's own trailing reference. A subject written under the
        # commit-subject contract carries none, so the cases that exercise the
        # removal are the ones that contract does not reach -- a commit made
        # before it, or one written by hand. Any other number is somebody
        # else's link, and a number written into the line rather than after it
        # is prose.
        for case, subject, expected in (
            ("plain", "feat: add a sparkly thing", "feat: add a sparkly thing"),
            # Scope and breaking marker.
            (
                "scoped and breaking",
                "fix(api)!: drop legacy endpoint",
                "fix(api)!: drop legacy endpoint",
            ),
            # Repo-local prefix, not a Conventional type: the removal must
            # leave the prefix the repository actually uses in place.
            (
                "repo-local prefix, issue reference",
                f"event: add the winter gala (#{TITLE_ISSUE})",
                "event: add the winter gala",
            ),
            (
                "issue reference",
                f"feat: add a sparkly thing (#{TITLE_ISSUE})",
                "feat: add a sparkly thing",
            ),
            (
                "issue ahead of another link",
                f"feat: port the upstream fix (#{TITLE_ISSUE}) (#99)",
                "feat: port the upstream fix (#99)",
            ),
            (
                "another request's link alone",
                "feat: port the upstream fix (#99)",
                "feat: port the upstream fix (#99)",
            ),
            (
                "the number inside the text",
                f"feat: drop the #{TITLE_ISSUE} shim",
                f"feat: drop the #{TITLE_ISSUE} shim",
            ),
            (
                "a mid-line reference",
                f"feat: rework (#{TITLE_ISSUE}) handling",
                f"feat: rework (#{TITLE_ISSUE}) handling",
            ),
        ):
            with self.subTest(case=case):
                self.assertEqual(self._title(subject), expected)

    def test_prefixed_issue_title_is_reused(self) -> None:
        # An already-prefixed issue title must not gain a second prefix, and
        # a number typed onto the end of one is the same link read from the
        # wrong side as one left on a commit subject. No contract governs what
        # a human writes into an issue title, so this road is the removal's on
        # its own.
        for title in (
            "docs: clarify the README",
            f"docs: clarify the README (#{TITLE_ISSUE})",
        ):
            with self.subTest(title=title):
                self.assertEqual(
                    self._title("some unconventional commit", title=title),
                    "docs: clarify the README",
                )

    def test_unprefixed_pair_synthesizes_from_default(self) -> None:
        for case, first_subject, title in (
            ("neither is prefixed", "updated stuff", ISSUE_TITLE),
            # Stripping ahead of the prefix test is what makes this one fall
            # through: reused as written, the title would be a bare `feat:`
            # with nothing after the colon.
            (
                "the subject was only the reference",
                f"feat: (#{TITLE_ISSUE})",
                ISSUE_TITLE,
            ),
            (
                "the issue title carries the reference",
                "updated stuff",
                f"{ISSUE_TITLE} (#{TITLE_ISSUE})",
            ),
        ):
            with self.subTest(case=case):
                self.assertEqual(
                    self._title(first_subject, title=title),
                    f"{FEATURE_PREFIX}: {ISSUE_TITLE}",
                )

    def test_synthesized_title_honors_fallback_prefix(self) -> None:
        # The repo-local prefix `_infer_subject_prefix` read from base
        # history reaches the synthesized subject.
        self.assertEqual(
            self._title("updated the listings", prefix="career"),
            f"career: {ISSUE_TITLE}",
        )

    def test_titleless_issue_falls_back_to_its_number(self) -> None:
        self.assertEqual(
            self._title("", title=""),
            f"{FEATURE_PREFIX}: address issue #{TITLE_ISSUE}",
        )

    def _title(
        self,
        first_subject: str,
        *,
        title: str = ISSUE_TITLE,
        prefix: str = "",
    ) -> str:
        issue = make_issue(TITLE_ISSUE, title=title)
        if not prefix:
            # Exercise the `feat` default the callers rely on.
            return titles._pr_title_from_commit_or_issue(issue, first_subject)
        return titles._pr_title_from_commit_or_issue(
            issue, first_subject, prefix,
        )


if __name__ == "__main__":
    unittest.main()
