# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What the ClusterFuzzLite workflows declare around the fuzzing they run.

Each declaration changes what a green fuzz run means or what it can reach.

The triggers decide which revision is fuzzed and by whom. A pull request, a
fork's included, runs on `pull_request` and never `pull_request_target`, so it
gets no write grant and no secret; batch fuzzing and pruning run on a schedule,
which GitHub runs on the default branch, and on demand.

The token decides what a run can read back. ClusterFuzzLite's own corpus and
build downloads take the newest artifact of a name from any run, a fork's
included, so no ClusterFuzzLite step is handed one. Only the corpus restore,
the source checkout before it -- `actions/checkout` fetches with `github.token`
unless handed another, and keeps it out of the checkout here -- and the log
copy hold `github.token`, and only their jobs are granted `actions: read`; no
workflow names a repository secret.

The budgets and switches decide whether a failure can pass green. Every run
states its mode and fuzzing seconds, sits inside a step ceiling that covers
them and a job ceiling that covers its steps, and reports timeouts and
out-of-memory failures, which the pinned action leaves off unless told. The
crashing inputs and the job's log are kept, on a stated retention, whatever
the run did. The log is copied with the GitHub CLI a hosted runner carries,
which refuses to print a log's terminal escapes unless told, so each copy is
run through that CLI against a local server serving a colored log.

The commit decides what a green run vouches for. The build action checks a
pull request's merge ref out when it builds, and that ref moves with the base
and the head, so every run checks the commit it built against the one it was
started for before fuzzing, fails on a difference, and records the commit a
finding is replayed on.
"""
from __future__ import annotations

import os
import shutil
import stat
import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from tests.repository import (
    clusterfuzzlite_corpus_test_support as corpus_support,
    clusterfuzzlite_workflow_test_support as support,
)

_restore = corpus_support.load_restore_module()

_SECONDS_PER_MINUTE = 60
_TRIGGERS = (
    ("clusterfuzzlite-pr.yml", "on:\n  pull_request:\n\n"),
    ("clusterfuzzlite-batch.yml", 'on:\n  schedule:\n    - cron: "23 2 * * *"\n  workflow_dispatch:\n\n'),
    ("clusterfuzzlite-prune.yml", 'on:\n  schedule:\n    - cron: "47 5 * * *"\n  workflow_dispatch:\n\n'),
)
# The workflows that restore a corpus and leave its successor.
_CORPUS_WORKFLOWS = ("clusterfuzzlite-batch.yml", "clusterfuzzlite-prune.yml")
_READ_ONLY = "\npermissions:\n  contents: read\n\n"
_ACTIONS_READ = "\n      actions: read"
# The two lines a token is handed to a step by.
_TOKEN_LINES = frozenset((
    "          GITHUB_TOKEN: ${{ github.token }}",
    "          GH_TOKEN: ${{ github.token }}",
))
_PULL_REQUEST_LANE = "concurrency:\n  group: ${{ github.workflow }}-${{ github.ref }}\n  cancel-in-progress: true\n"
_CORPUS_LANE = "concurrency:\n  group: clusterfuzzlite-corpus-${{ github.ref }}\n  cancel-in-progress: false\n"
# Lines every run step carries: the two switches the pinned action leaves off,
# the build it runs, and no dry run, which would pass a finding green.
_RUN_LINES = (
    '          REPORT_TIMEOUTS: "true"',
    '          REPORT_OOMS: "true"',
    "          language: python",
    "          sanitizer: address",
    "          dry-run: false",
)
_KEPT_WHATEVER_RAN = "        if: always() && steps.build.outcome == 'success'\n"
_CHECK = "Check the fuzzed commit"
_IDENTITY = (
    ("GIT_AUTHOR_NAME", "Fuzz drill"),
    ("GIT_AUTHOR_EMAIL", "fuzz-drill@example.invalid"),
    ("GIT_COMMITTER_NAME", "Fuzz drill"),
    ("GIT_COMMITTER_EMAIL", "fuzz-drill@example.invalid"),
    ("GIT_CONFIG_NOSYSTEM", "1"),
)
_RESTORE = (
    'run: python3 source/.github/scripts/clusterfuzzlite_corpus.py "$GITHUB_WORKSPACE" source/fuzz/corpus'
)
_ESCAPES_ALLOWED = "--allow-escape-sequences"
_LOG_COPY = f'gh api {_ESCAPES_ALLOWED} "repos/$GITHUB_REPOSITORY/actions/jobs/$job/logs"'
_RUN_ID = 4215
_RUN_ATTEMPT = 2
# Each job a log copy can find in its run's listing, by its id.
_JOBS = (("fuzz", 11), ("prune", 12), ("log", 13))
# A job's log as GitHub serves it, the build's and libFuzzer's lines colored.
_COLORED_LOG = "\x1b[36;1mINFO: the {job} job ran\x1b[0m\n#2\tINITED cov: 412 ft: 518\n"
# The runner's `gh`, each REST path it is handed sent to the local server instead of GitHub.
_GH_STAND_IN = """#!/usr/bin/env bash
arguments=()
for argument in "$@"; do
  case $argument in
    repos/*) arguments+=("$FAKE_GITHUB/$argument") ;;
    *) arguments+=("$argument") ;;
  esac
done
exec "$REAL_GH" "${arguments[@]}"
"""
# A refused copy then fails at once rather than after a minute of retries.
_SLEEP_STAND_IN = "#!/bin/sh\nexit 0\n"


def _every_workflow() -> dict[str, str]:
    return {
        path.name: path.read_text(encoding="utf-8")
        for path in sorted(support.WORKFLOW_DIR.glob("*.yml"))
    }


class ClusterFuzzLiteTriggerTest(unittest.TestCase):
    def test_each_workflow_runs_on_its_own_events(self) -> None:
        for name, trigger in _TRIGGERS:
            with self.subTest(workflow=name):
                self.assertIn(f"\n{trigger}permissions:", support.workflow_text(name))
        named = [fuzzing.workflow for fuzzing in support.FUZZING]
        self.assertEqual([workflow for workflow, _ in _TRIGGERS], named)

    def test_restored_corpora_come_from_corpus_runs(self) -> None:
        """A corpus is restored from a scheduled or manual run of the two workflows that restore one."""
        trusted = {f".github/workflows/{name}" for name in _CORPUS_WORKFLOWS}
        self.assertEqual(_restore.TRUSTED_WORKFLOWS, trusted)
        self.assertEqual(_restore.TRUSTED_EVENTS, {"schedule", "workflow_dispatch"})
        for name in _CORPUS_WORKFLOWS:
            with self.subTest(workflow=name):
                self.assertIn(_RESTORE, support.workflow_text(name))

    def test_no_workflow_runs_on_pull_request_target(self) -> None:
        for name, workflow in _every_workflow().items():
            with self.subTest(workflow=name):
                self.assertNotIn("pull_request_target", workflow)


class ClusterFuzzLiteTokenTest(unittest.TestCase):
    def test_no_workflow_reads_a_secret(self) -> None:
        for name, workflow in _every_workflow().items():
            with self.subTest(workflow=name):
                self.assertNotIn("secrets.", workflow)

    def test_only_the_reads_back_hold_the_token(self) -> None:
        for fuzzing in support.FUZZING:
            workflow = support.workflow_text(fuzzing.workflow)
            self.assertIn(_READ_ONLY, workflow)
            self.assertNotIn("github-token", workflow)
            self.assertNotIn(": write", workflow)
            for job, steps in support.jobs(workflow).items():
                with self.subTest(workflow=fuzzing.workflow, job=job):
                    self.assert_token_matches_grant(steps)

    def assert_token_matches_grant(self, job: str) -> None:
        """A job hands the token on only in the two known lines, and is granted `actions: read` only then.

        A checkout takes the token by default, so one may sit only in a job
        that hands it on explicitly too, and never keeps it.
        """
        handed = [line for line in job.splitlines() if "github.token" in line]
        self.assertLessEqual(set(handed), _TOKEN_LINES)
        self.assertEqual(_ACTIONS_READ in job, bool(handed))
        checkouts = job.count("uses: actions/checkout@")
        self.assertEqual(job.count("\n          persist-credentials: false\n"), checkouts)
        self.assertLessEqual(checkouts, len(handed))


class ClusterFuzzLiteBudgetTest(unittest.TestCase):
    def test_each_run_states_mode_budget_and_reports(self) -> None:
        for fuzzing in support.FUZZING:
            run = support.step(support.job_of(fuzzing), fuzzing.run_step).splitlines()
            with self.subTest(workflow=fuzzing.workflow):
                for line in _RUN_LINES:
                    self.assertIn(line, run)
                self.assertIn(f"          mode: {fuzzing.mode}", run)
                self.assertIn(f"          fuzz-seconds: {fuzzing.fuzz_seconds}", run)

    def test_each_ceiling_covers_what_runs_inside_it(self) -> None:
        for fuzzing in support.FUZZING:
            job = support.job_of(fuzzing)
            job_minutes, *step_minutes = support.minutes(job)
            run_minutes = support.minutes(support.step(job, fuzzing.run_step))
            with self.subTest(workflow=fuzzing.workflow):
                self.assertGreater(run_minutes[0] * _SECONDS_PER_MINUTE, fuzzing.fuzz_seconds)
                self.assertGreater(job_minutes, sum(step_minutes))

    def test_corpus_runs_queue_and_pr_runs_cancel(self) -> None:
        self.assertIn(_PULL_REQUEST_LANE, support.workflow_text("clusterfuzzlite-pr.yml"))
        for name in _CORPUS_WORKFLOWS:
            with self.subTest(workflow=name):
                self.assertIn(_CORPUS_LANE, support.workflow_text(name))


class ClusterFuzzLiteArtifactTest(unittest.TestCase):
    def test_crashing_inputs_are_kept_whatever_ran(self) -> None:
        for fuzzing in support.FUZZING:
            kept = support.step(support.job_of(fuzzing), "Keep the crashing inputs")
            with self.subTest(workflow=fuzzing.workflow):
                self.assertTrue(kept.startswith(f"name: Keep the crashing inputs\n{_KEPT_WHATEVER_RAN}"))
                self.assertIn("          path: out/artifacts\n", kept)
                self.assertIn("          if-no-files-found: ignore\n", kept)
                self.assertIn(f"          retention-days: {fuzzing.retention_days}\n", kept)

    def test_the_job_log_is_kept_beside_them(self) -> None:
        for fuzzing in support.FUZZING:
            log = support.jobs(support.workflow_text(fuzzing.workflow))["log"]
            with self.subTest(workflow=fuzzing.workflow):
                self.assertIn(f"    needs: {fuzzing.job}\n    if: ${{{{ !cancelled() }}}}\n", log)
                self.assertIn(f'select(.name == "{fuzzing.job}")', log)
                self.assertIn(f"          path: {fuzzing.job}-job.log\n", log)
                self.assertIn(_LOG_COPY, log)
                self.assertIn(f"          retention-days: {fuzzing.retention_days}", log)

    def test_a_crash_while_pruning_fails_the_job(self) -> None:
        prune = support.jobs(support.workflow_text("clusterfuzzlite-prune.yml"))["prune"]
        check = support.step(prune, "Fail on inputs the merge stopped on")
        self.assertTrue(check.startswith(f"name: Fail on inputs the merge stopped on\n{_KEPT_WHATEVER_RAN}"))
        self.assertIn("exit 1", check)


class ClusterFuzzLiteLogCopyTest(unittest.TestCase):
    """Each `log` job copies its own job's log whole, terminal escapes included.

    The copy runs with the real GitHub CLI, which a stand-in `gh` hands every
    request after sending it to the local server, so the CLI's refusal to
    print escapes applies as it does on a hosted runner. A CLI older than that
    refusal has no switch to lift it, and the check is skipped.
    """

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        gh = shutil.which("gh")
        if gh is None:
            raise unittest.SkipTest("the GitHub CLI is not installed")
        usage = subprocess.run(
            [gh, "api", "--help"],
            capture_output=True,
            text=True,
            check=False,
        )
        if _ESCAPES_ALLOWED not in usage.stdout:
            raise unittest.SkipTest("the GitHub CLI predates its refusal to print terminal escapes")
        cls.gh = gh

    def setUp(self) -> None:
        self.github = corpus_support.FakeGitHub()
        self.addCleanup(self.github.stop)
        self.serve_run()
        scratch = Path(self.enterContext(TemporaryDirectory()))
        tools = scratch / "tools"
        tools.mkdir()
        self.stand_in(tools / "gh", _GH_STAND_IN)
        self.stand_in(tools / "sleep", _SLEEP_STAND_IN)
        self.environment = {
            "PATH": f"{tools}{os.pathsep}{os.environ['PATH']}",
            "HOME": str(scratch),
            "GH_TOKEN": corpus_support.TOKEN,
            "REAL_GH": self.gh,
            "FAKE_GITHUB": self.github.url,
            "GITHUB_REPOSITORY": corpus_support.REPOSITORY,
            "GITHUB_RUN_ID": str(_RUN_ID),
            "GITHUB_RUN_ATTEMPT": str(_RUN_ATTEMPT),
        }

    def test_each_log_is_copied_whole(self) -> None:
        for fuzzing in support.FUZZING:
            with self.subTest(workflow=fuzzing.workflow):
                copied, log = self.copy(fuzzing)
                served = _COLORED_LOG.format(job=fuzzing.job).encode()
                self.assertEqual(copied.returncode, 0, copied.stderr)
                self.assertEqual(log.read_bytes(), served)

    def serve_run(self) -> None:
        """The run's job listing and each job's own colored log."""
        listed = [{"id": job_id, "name": job} for job, job_id in _JOBS]
        jobs = f"/actions/runs/{_RUN_ID}/attempts/{_RUN_ATTEMPT}/jobs"
        self.github.answer(jobs, {"total_count": len(listed), "jobs": listed})
        for job, job_id in _JOBS:
            log = _COLORED_LOG.format(job=job).encode()
            self.github.answer(f"/actions/jobs/{job_id}/logs", log)

    def copy(self, fuzzing: support.Fuzzing) -> tuple[subprocess.CompletedProcess[str], Path]:
        """`fuzzing`'s log copy, run as a hosted runner runs it in a workspace of its own, and the log it left."""
        log_job = support.jobs(support.workflow_text(fuzzing.workflow))["log"]
        copy_step = support.step(log_job, f"Copy the {fuzzing.job} job's log")
        workspace = Path(self.enterContext(TemporaryDirectory()))
        command = ["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", support.script(copy_step)]
        copied = subprocess.run(
            command,
            cwd=workspace,
            env=self.environment,
            capture_output=True,
            text=True,
            check=False,
        )
        return copied, workspace / f"{fuzzing.job}-job.log"

    def stand_in(self, tool: Path, text: str) -> None:
        tool.write_text(text, encoding="utf-8")
        tool.chmod(tool.stat().st_mode | stat.S_IXUSR)


class ClusterFuzzLiteCommitTest(unittest.TestCase):
    """A run fuzzes the commit it was started for, whatever its build checked out."""

    def setUp(self) -> None:
        scratch = Path(self.enterContext(TemporaryDirectory()))
        self.environment = dict(_IDENTITY)
        self.environment.update(PATH=os.environ["PATH"], HOME=str(scratch))
        self.summary = scratch / "summary.md"
        self.checkout = scratch / "storage" / "chipping-orchestrator"
        self.checkout.mkdir(parents=True)
        self.git("init")
        self.git("commit", "--allow-empty", "-m", "the commit the run is for")
        self.started_for = self.git("rev-parse", "HEAD")
        self.git("commit", "--allow-empty", "-m", "the merge ref after it moved")
        self.moved = self.git("rev-parse", "HEAD")

    def test_every_run_checks_before_it_fuzzes(self) -> None:
        checks = set()
        for fuzzing in support.FUZZING:
            job = support.job_of(fuzzing)
            names = ("Build the fuzz targets", _CHECK, fuzzing.run_step)
            order = [job.index(f"name: {name}") for name in names]
            with self.subTest(workflow=fuzzing.workflow):
                self.assertEqual(order, sorted(order))
            checks.add(support.script(support.step(job, _CHECK)))
        self.assertEqual(len(checks), 1)

    def test_a_moved_checkout_fails_the_run(self) -> None:
        checked = self.check()

        self.assertEqual(checked.returncode, 1)
        expected = f"::error::the build checked out {self.moved}, not {self.started_for}"
        self.assertIn(expected, checked.stdout)
        self.assertFalse(self.summary.exists())

    def test_the_fuzzed_commit_is_recorded(self) -> None:
        self.git("checkout", self.started_for)

        checked = self.check()

        self.assertEqual(checked.returncode, 0)
        self.assertEqual(checked.stdout, f"Fuzzed commit: {self.started_for}\n")
        self.assertEqual(self.summary.read_text(encoding="utf-8"), checked.stdout)

    def check(self) -> subprocess.CompletedProcess[str]:
        """The pull request workflow's check, run as a hosted runner runs it from the workspace."""
        check = support.step(support.job_of(support.FUZZING[0]), _CHECK)
        command = ["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", support.script(check)]
        job_environment = {
            "GITHUB_REPOSITORY": "chippingway/chipping-orchestrator",
            "GITHUB_SHA": self.started_for,
            "GITHUB_STEP_SUMMARY": str(self.summary),
        }
        workspace = self.checkout.parents[1]
        return subprocess.run(
            command,
            cwd=workspace,
            env=self.environment | job_environment,
            capture_output=True,
            text=True,
            check=False,
        )

    def git(self, *arguments: str) -> str:
        completed = subprocess.run(
            ["git", *arguments],
            cwd=self.checkout,
            env=self.environment,
            capture_output=True,
            text=True,
            check=True,
        )
        return completed.stdout.strip()


if __name__ == "__main__":
    unittest.main()
