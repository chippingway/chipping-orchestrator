# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The close a poll observed, put where the tests of two packages can set it.

A poll that finds a late-split owner closed while a worker holds it latches
that reading process-wide and leaves a marked receipt on the issue thread. The
latch is what the run in flight asks before every step the remote keeps; the
receipt is what the process after a restart has instead of it.

All of it is process state -- the latch, the cycle a read tied each latched
close to, the moment each was read at, the memo saying which cycle's receipt
landed, the generation that memo is counted against, the claim a poll posts
one under, the claim on the thread walk a process owes each owner and cycle,
the cycle a worker is retiring off a record right now, the issues a worker is
acting on, the settlements one of those windows has postponed, and the moment
this process last restarted each owner's cycle -- so every case that touches
any of them replaces all eleven first. That is also how a RESTART
is written: fresh registries beside a thread that still carries the receipt are
exactly what a new process wakes up to.

Here rather than beside either caller because the dispatcher's own tests set
these and the decomposition stage's tests read them, and a second copy of the
fixture would drift from whichever of the two it was not written for. So is
the record admission refuses that both packages' close cases pin against, and
the account of everything a pass over it may not change.
"""
from __future__ import annotations

import contextlib
from unittest.mock import patch

from orchestrator.github.pinned_state import SCHEMA_VERSION_KEY, PinnedState
from orchestrator.scheduler import claim_notes as _claim_notes, writer_claims as _writer_claims
from orchestrator.workflow.engine import observation_state as _observation_state, observations as _observations
from orchestrator.workflow.stages.decomposition import (
    late_close_reading as _late_close_reading,
)

# Every registry the shared observation-state owner keeps, with the empty container a new
# process starts each one on: two of them count rather than merely hold, so a
# case that replaced them all with sets would be testing a record production
# cannot produce.
_REGISTRIES = (
    ("_observed", set),
    ("_scopes", dict),
    ("_since", dict),
    ("_receipted", dict),
    ("_posting", set),
    ("_settlements", dict),
    ("_scanned", dict),
    ("_retiring", dict),
    ("_publishing", dict),
    ("_deferred", set),
    ("_restarted", dict),
)


def read_now() -> int:
    """The moment a reading these cases take in-process is read at: now.

    Taken where the case reads the issue, so a hold of another poller the case
    makes after it is one the reading predates.
    """
    return _claim_notes.moment()


def receipt_for(issue_number: int, cycle_id: int) -> str:
    """The receipt one cycle's observed close is stamped with.

    Built through the production spelling, so a test that plants one plants
    exactly what a later process scans for.
    """
    return _late_close_reading._observed_close_marker(issue_number, cycle_id)


def refuse_record(github, issue_number: int, *, parsed: bool = True) -> None:
    """Leave this issue's pinned record one admission refuses, its fields in place.

    Parsed, it is the record as a release before version 1 pinned it: every
    field a cycle wrote, and no version. Unparsed, it is a comment a hand edit
    left that no longer parses at all. Either reads back empty and refused,
    and neither writer lays anything over it.
    """
    recorded = github.pinned_data(issue_number)
    recorded.pop(SCHEMA_VERSION_KEY, None)
    github.seed_state(issue_number, raw=True, **recorded)
    if not parsed:
        github._pinned[issue_number] = PinnedState(
            comment_id=github._pinned[issue_number].comment_id, parsed=False,
        )


def left_on_github(github, issue_number: int) -> dict:
    """Everything a pass could change about one issue and the remote it owns.

    The thread, the labels, every pinned write and the record itself, whether
    the issue is open, every pull request's state and what was said or edited
    on one, and the branches deleted -- the account a pass over a record
    admission refuses has to leave exactly as it found it.
    """
    issue = github.get_issue(issue_number)
    return {
        "comments": list(github.posted_comments),
        "relabels": list(github.label_history),
        "pinned writes": github.write_state_calls,
        "record": github._pinned.get(issue_number),
        "closed": issue.closed,
        "labels": sorted(label.name for label in issue.labels),
        "pull requests": _pull_requests(github),
        "deleted branches": list(github.deleted_remote_branches),
    }


def _pull_requests(github) -> list:
    """Each pull request's number, state, merge, body, and labels, with every comment and body edit made on one."""
    held = sorted(
        (number, pull.state, pull.merged, pull.body, list(pull.labels))
        for number, pull in github.pulls.items()
    )
    return [held, list(github.posted_pr_comments), list(github.edited_pr_bodies)]


class ObservedCloseCase:
    """A case whose process-wide close observations are its own."""

    def _fresh_process(self) -> None:
        """Replace every registry with the one a new process starts on."""
        for held, empty in _REGISTRIES:
            replaced = patch.object(_observation_state, held, empty())
            replaced.start()
            self.addCleanup(replaced.stop)

    @contextlib.contextmanager
    def _under_the_claim(self, repo_id: int, issue_number: int, *, alongside: bool = False):
        """Hold the issue's writer claim, as the dispatch seam a reconciliation runs under does.

        `alongside` is the poll's receipt beside this process's own writer.
        """
        with _writer_claims.issue_writer(repo_id, issue_number, alongside=alongside) as held:
            self.assertTrue(held)
            yield

    def _latch_close(self, repo_slug: str, issue_number: int) -> None:
        """What the polling thread does with a close it can hand nowhere.

        Read now, so a hold of another poller the case makes afterwards is
        one the reading predates.
        """
        _observations.observe_close(repo_slug, issue_number, read_now())

    def _observed(self, repo_slug: str) -> frozenset:
        """Which of this repo's closes no pass has settled."""
        return _observations.observed_closes(repo_slug)

    def _settle_latches(self, repo_slug: str) -> None:
        """What the pass that took an observation leaves behind: nothing."""
        for held in _observations.observed_closes(repo_slug):
            _observations.settle_close(repo_slug, held)
