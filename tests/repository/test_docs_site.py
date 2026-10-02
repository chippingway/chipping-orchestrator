# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Published pages retain usable links, and the workflow publishing them keeps its boundaries.

Every pull request reports `build`, whatever files it changes: a path filter
skips the whole workflow, and branch protection would wait forever on a
required check that never reports. Only `main` outside a pull request uploads
the site or deploys it, and the deploy job alone holds a Pages token, so a
pull request's run stays read-only. A push to `main` publishes when it changes
a source the site is built from, the template directory among them.

A run builds the full site once. The check step names that output in
`DOCS_SITE_DIR`, so `test_docs_output.py` validates the pages the upload step
publishes, and does so before they are uploaded. Source links in the Markdown
are the CI matrix's to check, through `test_doc_links.py`.

Pages serves one site, so main runs share a group: GitHub replaces a pending
run with the newest one while an active deployment finishes. Pull requests
use their own refs and cancel superseded builds without displacing a deploy.
The workflow runs on GitHub, so each policy is checked as the text GitHub
receives.
"""
from __future__ import annotations

import re
import unittest
from importlib.util import find_spec
from pathlib import Path
from tempfile import TemporaryDirectory

from tests.repository import docs_site_test_support as _site_support
from tests.repository.doc_link_test_support import HEADING_ANCHOR_CASES

_ENCODING = "utf-8"
_WORKFLOW = _site_support.REPO_ROOT / ".github" / "workflows" / "docs.yml"
_SOURCE_URL = "https://github.com/chippingway/chipping-orchestrator/blob/main/README.md#quick-start"
_CONCURRENCY_BLOCK = """concurrency:
  group: >-
    ${{ github.workflow }}-${{ github.ref == 'refs/heads/main' && github.event_name != 'pull_request' &&
    'pages' || github.ref }}
  cancel-in-progress: ${{ github.event_name == 'pull_request' }}
"""
_TRIGGERS = "on"
_JOBS = "jobs"
_PULL_REQUEST = "pull_request"
_BARE_PULL_REQUEST = "  pull_request:\n"
_MAIN_ONLY = "github.ref == 'refs/heads/main' && github.event_name != 'pull_request'"
_MAIN_BRANCH = "    branches: [main]"
_DEPLOY_GATE = f"    if: {_MAIN_ONLY}"
_ARTIFACT_STEP = f"""      - name: Upload Pages artifact
        if: {_MAIN_ONLY}
        uses: actions/upload-pages-artifact@"""
_BUILD_STEP = """      - name: Build documentation
        run: uv run --no-sync mkdocs build --strict
"""
_CHECK_STEP = f"""      - name: Check the built documentation
        env:
          {_site_support.SITE_VARIABLE}: {_site_support.SITE_DIRECTORY}
        run: uv run --no-sync pytest tests/repository/test_docs_site.py tests/repository/test_docs_output.py
"""
_PUBLISHING_STEPS = (_BUILD_STEP, _CHECK_STEP, _ARTIFACT_STEP)
_UPLOADED_SITE = f"        with:\n          path: {_site_support.SITE_DIRECTORY}\n"
_READ_ONLY_GRANT = "\npermissions:\n  contents: read\n\n"
_THEME_PATH = '      - ".github/docs-theme/**"\n'
# YAML lets a comment sit at any indent, so one left in place would end the
# block above it early and hide the configuration nested below it.
_COMMENT_LINE = re.compile(r"^[ \t]*#.*\n", re.MULTILINE)
# A key that opens a block, and every line after it indented past the key's
# own indent -- the backreference is what makes "past" relative to the key.
_BLOCK = re.compile(
    r"^(?P<indent> *)(?P<name>[\w-]+):[ \t]*(?:#.*)?\n(?P<body>(?:[ \t]*\n|(?P=indent) .*\n)*)",
    re.MULTILINE,
)
_SAMPLE = """# Sample

[source](../README.md#quick-start) and [reference][source].
[local](next.md#local-page).

`[example](../README.md)`

```markdown
[example](../README.md)
```

[source]: ../README.md#quick-start
"""
_HEADING_SAMPLE = "\n\n".join(f"## {heading}" for heading, _ in HEADING_ANCHOR_CASES)


def _blocks(text: str, indent: int) -> dict[str, str]:
    """Each key at one indent that opens a block, against the lines nested deeper than it."""
    return {
        match["name"]: match["body"]
        for match in _BLOCK.finditer(_COMMENT_LINE.sub("", text))
        if len(match["indent"]) == indent
    }


def _section(workflow: str, key: str) -> dict[str, str]:
    """Each trigger under `on:`, or each job under `jobs:`, against its own lines."""
    return _blocks(_blocks(workflow, 0)[key], 2)


def _published_paths(workflow: str) -> str:
    """What a push to `main` publishes on -- empty when the push filter lists no `paths`."""
    return _blocks(_section(workflow, _TRIGGERS)["push"], 4).get("paths", "")


def _workflow() -> str:
    return _WORKFLOW.read_text(encoding=_ENCODING)


class DocumentationConcurrencyTest(unittest.TestCase):
    def test_only_deploys_share_pages_concurrency(self) -> None:
        self.assertIn(_CONCURRENCY_BLOCK, _workflow())


class DocumentationWorkflowTest(unittest.TestCase):
    def test_every_pull_request_reports_the_build(self) -> None:
        self.assertEqual(
            _section(_workflow(), _TRIGGERS)[_PULL_REQUEST].strip(),
            "",
            "a filtered pull_request trigger skips the workflow, leaving a required `build` check unreported",
        )

    def test_main_pushes_publish_template_edits(self) -> None:
        workflow = _workflow()
        self.assertIn(_MAIN_BRANCH, _section(workflow, _TRIGGERS)["push"].splitlines())
        self.assertIn(_THEME_PATH, _published_paths(workflow))

    def test_only_main_runs_upload_and_deploy(self) -> None:
        jobs = _section(_workflow(), _JOBS)
        self.assertIn(_ARTIFACT_STEP, jobs["build"])
        self.assertIn(_DEPLOY_GATE, jobs["deploy"].splitlines())

    def test_the_checked_build_is_the_uploaded_one(self) -> None:
        jobs = _section(_workflow(), _JOBS)
        builds = "".join(jobs.values()).count("mkdocs build")
        self.assertEqual(builds, 1, "one build supplies both the checked and the uploaded site")
        build = jobs["build"]
        order = [build.find(step) for step in _PUBLISHING_STEPS]
        self.assertNotIn(-1, order)
        self.assertEqual(order, sorted(order), "the check must read the build before it is uploaded")
        self.assertIn(_UPLOADED_SITE, build[order[-1]:])

    def test_pull_request_runs_hold_a_read_only_token(self) -> None:
        workflow = _workflow()
        self.assertIn(_READ_ONLY_GRANT, workflow)
        self.assertNotIn("permissions:", _section(workflow, _JOBS)["build"])

    def test_every_pull_request_filter_is_seen(self) -> None:
        """Every spelling of a filter GitHub honours is one the check above sees."""
        workflow = _workflow()
        filters = {
            "a path filter": "  pull_request:\n    paths:\n      - docs/**\n",
            "an ignore list": "  pull_request:\n    paths-ignore:\n      - orchestrator/**\n",
            "an indented comment": "  pull_request:\n  # documentation only\n    paths:\n      - docs/**\n",
            "a column-zero comment": "  pull_request:\n# documentation only\n    paths:\n      - docs/**\n",
            "a trailing comment": "  pull_request: # documentation only\n    paths:\n      - docs/**\n",
            "a narrower indent": "  pull_request:\n   paths:\n   - docs/**\n",
        }
        for description, trigger in filters.items():
            edited = workflow.replace(_BARE_PULL_REQUEST, trigger)
            with self.subTest(trigger=description):
                self.assertNotEqual(edited, workflow)
                self.assertTrue(_section(edited, _TRIGGERS)[_PULL_REQUEST].strip())

    def test_an_ignored_template_does_not_publish(self) -> None:
        """Listing the template under `paths-ignore` suppresses a template-only push."""
        workflow = _workflow()
        edited = workflow.replace("    paths:\n", "    paths-ignore:\n")
        self.assertNotEqual(edited, workflow)
        self.assertIn(_THEME_PATH, _section(edited, _TRIGGERS)["push"])
        self.assertNotIn(_THEME_PATH, _published_paths(edited))


@unittest.skipUnless(find_spec("mkdocs"), _site_support.INSTALL_HINT)
class DocumentationWebsiteTest(unittest.TestCase):
    def test_unique_heading_anchors_match_github(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            built = _site_support.build_site(
                _site_support.write_sample_repository(root, _HEADING_SAMPLE), root / _site_support.SITE_DIRECTORY,
            )
            self.assertEqual(built.returncode, 0, built.stderr)
            anchors = _site_support.SitePage(root / _site_support.SITE_DIRECTORY / "index.html").anchors
            self.assertLessEqual({expected for _, expected in HEADING_ANCHOR_CASES}, anchors)

    def test_source_links_preserve_code(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            built = _site_support.build_site(
                _site_support.write_sample_repository(root, _SAMPLE), root / _site_support.SITE_DIRECTORY,
            )
            self.assertEqual(built.returncode, 0, built.stderr)
            homepage = root / _site_support.SITE_DIRECTORY / "index.html"
            links = _site_support.SitePage(homepage).links
            self.assertEqual(links.count(_SOURCE_URL), 2)
            self.assertIn("next/#local-page", links)
            self.assertEqual(homepage.read_text(encoding=_ENCODING).count("[example](../README.md)"), 2)
            links = _site_support.SitePage(
                root / _site_support.SITE_DIRECTORY / "nested" / "page" / "index.html",
            ).links
            self.assertIn(_SOURCE_URL, links)
            self.assertIn("../../next/#local-page", links)

    def test_broken_repository_link_fails_build(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            built = _site_support.build_site(
                _site_support.write_sample_repository(root, "# Sample\n\n[missing](../missing.py)\n"),
                root / _site_support.SITE_DIRECTORY,
            )
            self.assertNotEqual(built.returncode, 0, built.stderr)
            self.assertIn("Repository link does not resolve", built.stderr)


if __name__ == "__main__":
    unittest.main()
