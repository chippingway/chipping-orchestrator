# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What the per-tick wrapper swallows, and what the sink lock protects."""

import contextlib
import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from orchestrator.observability.analytics import recording, retention
from tests.observability.analytics import (
    retention_test_support as _support,
)
from tests.observability.analytics.analytics_jsonl_helpers import (
    read_records as _read_records,
    timestamp_days_ago as _ts_days_ago,
    write_json_lines as _write_json_lines,
)
from tests.observability.analytics.analytics_reload_helpers import reload_analytics as _reload

# The rewrite step's own `os`, named rather than imported: this module wants
# the owner only as a patch target, and naming it keeps the import list under
# the ceiling.
_OS_REPLACE = "orchestrator.observability.analytics.retention_rewrite.os.replace"


_APPEND_TIMEOUT = 5.0


_FINISH_TIMEOUT = 5.0


_PRUNE_NOW = _support.PRUNE_NOW


_STAGE_ENTER = "stage_enter"


_APPENDED_ISSUE = 99


def _record(timestamp: str, issue: int, **extras) -> dict:
    return {
        _support.TIMESTAMP_KEY: timestamp,
        _support.REPO_KEY: _support.REPO_SHORT,
        _support.ISSUE_KEY: issue,
        _support.EVENT_KEY: _STAGE_ENTER,
        **extras,
    }


class _PruneAppendRace:
    def __init__(self, timestamp: str) -> None:
        self.timestamp = timestamp
        self.after_read = threading.Event()
        self.appender_done = threading.Event()
        self._real_replace = os.replace

    def replace(self, source, destination):
        self.after_read.set()
        self.appender_done.wait(timeout=0.5)
        return self._real_replace(source, destination)

    def append(self) -> None:
        self.after_read.wait(timeout=_APPEND_TIMEOUT)
        recording.append_record(_record(self.timestamp, _APPENDED_ISSUE))
        self.appender_done.set()

    def finish(self, thread: threading.Thread) -> None:
        self.after_read.set()
        thread.join(timeout=_FINISH_TIMEOUT)


def _run_prune_race(fresh_timestamp: str) -> int:
    race = _PruneAppendRace(fresh_timestamp)
    appender_thread = threading.Thread(target=race.append)
    appender_thread.start()
    with contextlib.ExitStack() as cleanup:
        cleanup.callback(race.finish, appender_thread)
        with patch(_OS_REPLACE, race.replace):
            return retention.prune_old_records(now=_PRUNE_NOW)


def _issue_numbers(path: Path) -> list[int]:
    records = _read_records(path)
    return sorted(record[_support.ISSUE_KEY] for record in records)


def _reloaded_against(path: Path) -> None:
    _reload(
        {
            _support.ANALYTICS_LOG_PATH: str(path),
            _support.ANALYTICS_RETENTION_DAYS: _support.DEFAULT_RETENTION,
        }
    )


@contextlib.contextmanager
def _reject_github_mutations(client_type, method_names: tuple[str, ...]):
    with contextlib.ExitStack() as guards:
        for method_name in method_names:
            guards.enter_context(
                patch.object(
                    client_type,
                    method_name,
                    side_effect=AssertionError(f"prune must not call GitHubClient.{method_name}"),
                )
            )
        yield


class PruneWithRetentionLoggingTest(unittest.TestCase):
    """`prune_with_retention_logging` is the end-of-pass wrapper that
    `runtime.ticks.run_tick` calls. It dispatches `prune_old_records` on its own
    owner, catches runaway exceptions so an analytics
    misconfiguration cannot abort the polling loop, and logs the
    removed-record count. The helper itself is local-filesystem only -- the
    prune never imports `github`, so it cannot mutate pinned GitHub state
    regardless of where it is called from.
    """

    def test_delegates_to_prune_old_records(self) -> None:
        with patch.object(
            retention,
            "prune_old_records",
            return_value=0,
        ) as prune:
            retention.prune_with_retention_logging()
            prune.assert_called_once_with()

    def test_exception_is_swallowed(self) -> None:
        # A runaway error inside `prune_old_records` must not propagate
        # -- analytics is observability, never authoritative workflow
        # state, so a misconfiguration must not abort the polling loop.
        with patch.object(
            retention,
            "prune_old_records",
            side_effect=RuntimeError("boom"),
        ):
            # No raise: the wrapper logs and swallows.
            retention.prune_with_retention_logging()

    def test_parallel_append_survives_prune(self) -> None:
        # Under the scheduler-driven dispatch `runtime.ticks.run_tick` drives,
        # `workflow.tick` returns as soon as the per-issue callables have
        # been submitted to the scheduler, so the retention prune can run
        # while scheduler workers are still calling `append_record()`.
        # Without a shared lock, an append that landed between
        # `prune_old_records`'s read and its `os.replace` would be
        # written to the soon-unlinked inode and silently lost.
        #
        # This test forces the race by patching the file ops inside
        # `prune_old_records` so the read happens, then the appender
        # thread fires, then the rewrite (`os.replace`) finishes --
        # exactly the window the lock has to close. With the lock in
        # place, the appender blocks until the prune releases it, so
        # its line is preserved.
        with tempfile.TemporaryDirectory(prefix="analytics-race-") as td:
            path = Path(td) / "analytics.jsonl"
            fresh = _ts_days_ago(_support.FRESH_RECORD_AGE_DAYS, now=_PRUNE_NOW)
            # One old record (will be pruned) plus one recent record
            # (the prune rewrite must keep it). After the rewrite, an
            # appender adds a fresh record concurrently; the prune
            # must NOT drop it.
            _write_json_lines(
                path,
                [
                    _record(
                        _ts_days_ago(
                            _support.VERY_OLD_RECORD_AGE_DAYS, now=_PRUNE_NOW,
                        ),
                        1,
                    ),
                    _record(fresh, 2),
                ],
            )
            _reloaded_against(path)

            # The replace callback opens the real post-read race window while
            # the append callback contends on analytics' file lock.
            self.assertEqual(_run_prune_race(fresh), 1)
            # The old record (issue=1) is gone. Both the kept record
            # (issue=2) and the concurrent append (issue=99) survive.
            self.assertEqual(_issue_numbers(path), [2, _APPENDED_ISSUE])

    def test_prune_rewrites_without_github_writes(self) -> None:
        # "Analytics is not authoritative workflow state" enforced at
        # the boundary: the prune helper takes no GitHub client and the
        # real `prune_old_records` implementation never imports `github`
        # at all. The polling-loop tests verify the wrapper is called once
        # per tick; this verifies that calling it cannot mutate pinned
        # state through any client method.
        from orchestrator.github.client import GitHubClient

        with tempfile.TemporaryDirectory(prefix="analytics-retention-") as td:
            path = Path(td) / "analytics.jsonl"
            _write_json_lines(
                path,
                [
                    _record(
                        _ts_days_ago(
                            _support.VERY_OLD_RECORD_AGE_DAYS, now=_PRUNE_NOW,
                        ),
                        1,
                        stage="implementing",
                    ),
                    _record(
                        _ts_days_ago(
                            _support.FRESH_RECORD_AGE_DAYS, now=_PRUNE_NOW,
                        ),
                        2,
                        stage="validating",
                    ),
                ],
            )
            _reloaded_against(path)
            # Patch every GitHub-mutating method on the class so the
            # prune cannot side-effect through any client instance that
            # some future refactor accidentally routes it through.
            with _reject_github_mutations(
                GitHubClient,
                (
                    "write_pinned_state",
                    "comment",
                    "set_workflow_label",
                    "create_child_issue",
                    "open_pr",
                    "pr_comment",
                    "merge_pr",
                    "delete_remote_branch",
                    "emit_event",
                ),
            ):
                self.assertEqual(retention.prune_old_records(now=_PRUNE_NOW), 1)
            self.assertEqual(_issue_numbers(path), [2])


if __name__ == "__main__":
    unittest.main()
