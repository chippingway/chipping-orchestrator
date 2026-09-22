# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What happens inside the windows a report round leaves open.

A report is written to the pinned comment before the size gate and before the
push, so every window past that write is one a tick can die in and come back to
an issue that still says what its developer reported. The minutes a developer
is OUT are a window of the same kind, and what moves in them belongs here too:
a thread somebody merged, a push that landed, a description edit. These are the
shapes those windows leave and the readings a case about one actually needs.

The CHECKOUT is the first, re-proved by every report road rather than
remembered, which a case has to answer for itself because the recovery counts a
path no host holds among its refusals. The readings are kept apart the way the
owner keeps them: whether the checkout is THERE, what its tree says, and what
head it names are three separate answers, and the whole of what the recovery is
about is that two of them refuse for good and the other two only say the poll
could not take them.

The PULL REQUEST is the second, and the same distinction runs through it: a
thread this report may not go onto is a reading a road TOOK, while a read
nobody could take is not. Its refusals are held to the shapes a pull request
really has -- a number is all that brings the object back, so a second thread
on another branch and a fork's can each stand on the very commit a round
proved -- and its failures are delivered by the lazy double, because a fetched
pull request asks GitHub nothing and every fact behind it is a request of its
own.
"""

from __future__ import annotations

import contextlib
import dataclasses
import tempfile
from pathlib import Path
from types import MappingProxyType
from unittest.mock import patch

from orchestrator.git.verification.status import _WorktreeStatus
from orchestrator.workflow.engine import (
    report_delivery as _report_delivery,
    report_delivery_state as _delivery_state,
)
from tests.support import fakes
from tests.workflow.git_owners import seam_patch
from tests.workflow.stages.fixing import report_settlement_support as _support

# A branch and a repository that are not this issue's. A pull request's number
# is all that brings the object back, so a second thread raised on another
# branch and a FORK -- which carries this repository's ref names over somebody
# else's commits -- can each stand on the very commit a round proved.
OTHER_BRANCH = "somebody/else/issue-880"

FORK_SLUG = "someone-else/orchestrator"

# Every read behind a fetched pull request that is a request of its own, plus
# the lookup in front of them. PyGithub hands back a lazy object, so a guard
# around the lookup alone covers none of the rest: `state` is both members
# `pr_state` derives from, `head` is the ref, the repository and the sha, and
# `body` is the description a verification may be living on.
LOOKUP = "lookup"

FAILING_READS = (LOOKUP, "state", "head", "body")

# The debt the release leaves behind, which outlives the record it drops.
OWED_REPORT = _report_delivery.OWED_REPORT

# What every road that cannot move a report parks under.
UNDELIVERABLE = _report_delivery.UNDELIVERABLE_REPORT

# A phrase out of each notice the recovery can post, enough to say which.
UNREADABLE_PHRASE = "the record cannot be read"

UNPUBLISHABLE_PHRASE = "cannot say whether the code it describes got there"

# A path no host holds. It is the missing-checkout READING rather than a
# backdrop for anything else: a worktree that went with the tick that made it
# is one of the two refusals no later poll takes back.
_GONE = Path("/nonexistent/orchestrator-fixing-report-checkout")


def _a_head(sha: str, ref: str, slug: str) -> MappingProxyType:
    """One whole head, as a replacement for the pull request in hand."""
    return MappingProxyType({"head": fakes.FakePRRef(
        sha=sha, ref=ref, repo=fakes.FakePRRepo(slug),
    )})


# The threads a report proved on the round's own head may not be published
# onto. Each keeps whatever the preflight read wherever it can, so what refuses
# is the FRESH reading rather than something a case moved out from under the
# road: a thread that ended, one a push moved past the commit, one open on
# somebody else's branch, and a fork's -- the last two standing on the very
# commit the round proved, since a number is all that brought the object back.
PUBLICATIONS_IT_IS_NOT_ABOUT = (
    ("head moved", _a_head(
        _support.MOVED_SHA, _support.BRANCH, _support.TEST_REPO_SLUG,
    )),
    ("merged", MappingProxyType({"merged": True})),
    ("closed", MappingProxyType({"state": "closed"})),
    ("another branch", _a_head(
        _support.HEAD_SHA, OTHER_BRANCH, _support.TEST_REPO_SLUG,
    )),
    ("a fork", _a_head(_support.HEAD_SHA, _support.BRANCH, FORK_SLUG)),
)


@contextlib.contextmanager
def a_failing_read(case, read: str):
    """One read of this issue's pull request that GitHub does not answer.

    The lookup is patched and every other read is delivered by the lazy
    double, which is the shape the real object has: `get_pr` asks GitHub
    nothing, so the requests that can fail are the attribute accesses behind
    it -- and a guard around the lookup alone covers none of them.
    """
    if read == LOOKUP:
        with patch.object(case.gh, "get_pr", side_effect=RuntimeError(read)):
            yield
        return
    case.gh.add_pr(fakes.LazyPullRequest(case.pull_request, failing=read))
    yield


@contextlib.contextmanager
def a_publication(case, moved) -> None:
    """Where the pull request stands NOW, the copy in hand left alone.

    The two are told apart on purpose: the copy a road holds was fetched
    before the developer ran, so a case that moved THAT would be answered by a
    road reading either one.
    """
    with patch.object(
        case.gh, "get_pr",
        return_value=dataclasses.replace(case.pull_request, **moved),
    ):
        yield


def a_tree(*, readable: bool = True, paths=()) -> _WorktreeStatus:
    """One worktree status probe answer, spelled by the case that wants it.

    The two refusals a report road tells apart live here rather than in a
    case: a tree this host PROVED dirty is one no later poll takes back, and a
    status nobody could read is not that at all.
    """
    return _WorktreeStatus(readable=readable, paths=tuple(paths))


@contextlib.contextmanager
def a_checkout(*, present: bool = True, tree: _WorktreeStatus | None = None, head: str = ""):
    """The checkout a report road re-proves, answered by the case.

    A real directory where the case says the checkout is there, because the
    owner asks the path itself rather than a probe -- so a fixture naming one
    no host holds would answer the missing-checkout refusal whatever else it
    meant to be about.
    """
    with tempfile.TemporaryDirectory() as checkout, contextlib.ExitStack() as seams:
        standing = Path(checkout) if present else _GONE
        seams.enter_context(seam_patch("_worktree_path", lambda *_args: standing))
        seams.enter_context(
            seam_patch("_worktree_status", lambda *_args: tree or a_tree()),
        )
        seams.enter_context(seam_patch("_head_sha", lambda *_args: head))
        yield


def a_standing_park(case, reason: str) -> None:
    """Leave the comment a park somebody already took, durably.

    Written through GitHub rather than staged, because what a case about one
    asks is whether a later road's own write still lands over it -- and read
    off a state the case only staged, a write that never happened would look
    exactly like one that did.
    """
    case.state.set(_support.AWAITING_HUMAN, True)
    case.state.set(_support.PARK_REASON, reason)
    case.gh.write_pinned_state(case.issue, case.state)


def frozen_record(state):
    """The unbound report record this comment is still holding, or None.

    Read off the record rather than off the comment, because that is the whole
    difference a reported round makes: the readers it consumed and the round
    its route spends both exist and neither has been applied, and only the
    write that publishes the report may apply either.
    """
    return _delivery_state.read_delivered_report(state)
