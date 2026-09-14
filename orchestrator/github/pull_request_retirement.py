# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""An idempotent supersession notice and the pull-request close it must precede."""
from __future__ import annotations

import logging

from github.PullRequest import PullRequest

from orchestrator.github import pull_request_reads as _pr_reads
from orchestrator.github.comments import carries_own_marker

log = logging.getLogger("orchestrator.github")



class GitHubPullRequestRetirement:
    """GitHubClient operations for retiring a superseded pull request."""

    def supersede_pr(
        self,
        pr: PullRequest,
        *,
        notice: str,
        marker: str,
        carries_marker: bool | None = None,
    ) -> bool:
        """Say once on a pull request that it is superseded, and close it.

        Two effects with one guard, because they are one obligation: a change
        nobody is going to merge has to say so where the humans looking at it
        will read it, and then stop being open. Splitting them would let a
        pull request end up closed with nothing on it saying why, which is the
        state the notice exists to prevent.

        Idempotent by asking the thread rather than by remembering. The comment
        and whatever durable record the caller keeps of it cannot be made one
        operation, so a crash between them is a repeat waiting to happen: the
        thread is searched for `marker` and the notice is posted only when it
        is not already there. Two things make that search safe. The caller
        scopes the marker to the one episode it belongs to, so a reused pull
        request cannot read an earlier episode's receipt as this one's; and
        the comment has to be OURS, since an HTML comment is invisible in the
        rendered thread and anybody could otherwise post the marker to
        suppress the one notice saying this change is not to be merged. The
        close needs no such check; a pull request that is not open is left
        exactly as it is, which also keeps a merged one from being reopened
        and re-closed.

        `carries_marker` is that search already made, and a caller that has
        one hands it over rather than paying for it again. The search is a
        request, so a caller that proved this pull request's state and head a
        moment ago and then let one run has put a round-trip between its proof
        and this write -- long enough for a human to close the change, and
        this helper would then post its notice onto a settlement somebody else
        made and report success. Nothing else can move the answer in that
        window: the marker only counts on a comment of OURS, and the caller
        has posted none since it looked. So the answer travels, and with it
        the write below is the first thing this call sends.

        False is every way this did not finish, and the caller retries the
        whole thing: the notice is idempotent and the close is a no-op on the
        second pass, so a retry costs a read. Every exception is caught rather
        than only GitHub's, because a lazy pull request raises from the first
        attribute read as readily as from the write, and a supersession that
        could not be made must hand the tick back rather than end it.
        """
        try:
            self._supersede(pr, notice, marker, carries_marker)
        except Exception:
            log.warning(
                "could not supersede PR #%s", getattr(pr, "number", "?"),
                exc_info=True,
            )
            return False
        return True

    def _supersede(
        self,
        pr: PullRequest,
        notice: str,
        marker: str,
        carries_marker: bool | None,
    ) -> None:
        """Post the notice this thread does not carry, then close it."""
        if carries_marker is None:
            carries_marker = self._pr_carries_marker(pr, marker)
        if not carries_marker:
            pr.create_issue_comment(notice)
        if _pr_reads.pr_state(pr) == _pr_reads._ISSUE_STATE_OPEN:
            pr.edit(state=_pr_reads._ISSUE_STATE_CLOSED)

    def _pr_carries_marker(self, pr: PullRequest, marker: str) -> bool:
        """Whether a comment of OURS on this pull request carries `marker`."""
        return carries_own_marker(
            pr.get_issue_comments(),
            marker,
            bot_login=getattr(self, "_bot_login", None),
        )
