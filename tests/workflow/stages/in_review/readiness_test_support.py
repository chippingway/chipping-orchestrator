# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""An issue in review one tick from its ready ping, and what can move under the evidence that ping rests on.

The world is the ready ping's (`ready_ping_test_support`): a mergeable,
unvetoed pull request on `HEAD` whose settled report a reviewer approved over
its own passing run of the configured suite, published as a verification
artifact and settled as the current evidence. A case qualifies the head by
one route or the other (`seeded_on`): the final-docs pass stamped on it, with
no GitHub review at all, or a GitHub approval of it, with no docs stamp.

What moves under that evidence is spelled here as a maintainer, a pusher, or
GitHub would move it -- the artifact edited, deleted, or rewritten whole in
the current format, the report or the issue edited, a push, the verification
configuration changed, a pinned record edited by hand -- and so are the ways a
reading stops answering, and the windows the ping's own checkpoints open for
any of that to land in: behind its arming, and behind the reading its
settlement is prepared over. Every tick proves the evidence over the checkout
on this host and the branch fetched where the pull request stands, unless a
case names another reading.
"""
from __future__ import annotations

from dataclasses import replace
from types import MappingProxyType
from unittest.mock import patch

from orchestrator import config
from orchestrator.github import verification_artifacts as _artifacts
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    report_settlement_state as _report_settlement,
    verification_record_state as _record_state,
    verification_records as _records,
    verification_settled_fields as _settled_fields,
    verification_settlement_state as _settlement,
)
from orchestrator.workflow.stages.validating import approved_evidence as _approved_evidence
from tests.workflow import (
    published_reports as _published_reports,
    verdict_values as _verdict_values,
    verified_approvals as _verified,
)
from tests.workflow.stages.in_review import ready_ping_test_support as _ping

HEAD = _ping.HEAD

# The two routes that qualify a head for the ping.
DOCS_ROUTE = "final docs"

GITHUB_ROUTE = "GitHub approval"

ROUTES = (DOCS_ROUTE, GITHUB_ROUTE)

# The command the configuration requires, which the approving run declared.
SUITE = _verdict_values.REVIEWER_SUITE

# A head a push moves the pull request on to, and a tree no evidence was
# gathered on.
PUSHED = "0dd5a1e0" * 5

OTHER_TREE = "7e5a1c00" * 5

# What a human leaves of the issue, the report, and the artifact once they edit them.
EDITED_BODY = "An edited body nobody reviewed."

EDITED_REPORT = "A different account of the work."

FAILED_OUTPUT = "1 failed"

# The pinned records a case reads the ping back by, beside the evidence's own.
CURRENT_EVIDENCE = "verification_evidence_current"

_DOCS_STAMPS = MappingProxyType({"docs_checked_sha": HEAD, "docs_verdict": "no_change"})


class EvidenceMoves:
    """What a human or a push does to what the evidence answers for, each on the case it is done on."""

    def pushes(self) -> None:
        """A push standing the pull request on a head nobody verified."""
        self.pull_request.head.sha = PUSHED

    def edits_the_issue(self) -> None:
        """A human editing the issue's requirements."""
        self.issue.body = EDITED_BODY

    def edits_the_report(self) -> None:
        """A human editing the settled developer report in place, at its location."""
        located = _report_settlement.read_current_report(PinnedState(state_data=self.pinned())).location
        posted = self.comment_at(located.comment_id)
        posted.body = posted.body.replace(_published_reports.DELIVERED_REPORT, EDITED_REPORT)

    def edits_the_artifact(self) -> None:
        """A human editing the current evidence's artifact to report a failure."""
        posted = self.comment_at(_current_evidence(self).comment_id)
        posted.body = posted.body.replace(_verdict_values.REVIEWER_SUITE_OUTPUT, FAILED_OUTPUT)

    def deletes_the_artifact(self) -> None:
        """A human deleting the current evidence's artifact from the pull request."""
        self.pull_request.issue_comments.remove(self.comment_at(_current_evidence(self).comment_id))

    def comment_at(self, comment_id: int):
        """The pull request's comment `comment_id` names."""
        return next(posted for posted in self.pull_request.issue_comments if posted.id == comment_id)

    def ends_behind_the_next_artifact_read(self, *, merged: bool) -> None:
        """A human merging, or closing, the pull request behind the next re-read of an artifact that answers.

        The head stays where it was, as a merge or a close leaves it, so only
        a reading of the pull request's state can see the end.
        """
        ends = _Ends(self, merged=merged)
        self.enterContext(patch.object(self.github, "reread_verification_artifact", ends))


class RecordEdits:
    """What a maintainer, or a settlement between ticks, leaves on the pinned comment and its artifact."""

    def restates(self, **fields) -> None:
        """Rewrite each record `fields` names to the value beside it, as a hand edit of the comment would."""
        pinned = self.github._pinned[_ping.ISSUE]
        pinned.data.update(fields)

    def rewrites_the_evidence(self, commands: tuple, *, claimed: bool = True) -> None:
        """Leave the current evidence carrying `commands`, its artifact and record each describing the other.

        The artifact rendered afresh in the current format, and the record's
        digest and pass flag the ones those commands earn, so the evidence
        proves current and only what the commands say decides. `claimed`, the
        approval's claim names the rewritten evidence exactly; otherwise the
        approval records no claim at all, as one nothing held to evidence.
        """
        current = _current_evidence(self)
        rerun = _records.PendingEvidence(
            receipt=current.receipt, revision=current.revision, binding=current.binding, commands=commands,
        )
        self.comment_at(current.comment_id).body = _artifacts.render_verification_artifact(rerun.artifact)
        rewritten = replace(current, content_revision=rerun.content_revision, passed=rerun.passed)
        self.restates(**{
            CURRENT_EVIDENCE: _settled_fields.current_object(rewritten),
            _approved_evidence.APPROVED_EVIDENCE: _verified.claim_on(rerun).recorded() if claimed else None,
        })

    def drops_the_evidence(self, *, claimed: bool = True) -> None:
        """Leave no current evidence recorded: the approval's claim naming what was there, or no claim at all."""
        self.restates(**{CURRENT_EVIDENCE: None})
        if not claimed:
            self.restates(**{_approved_evidence.APPROVED_EVIDENCE: None})

    def moves_the_context(self) -> None:
        """An operator changing `VERIFY_TIMEOUT` for the rest of the case, which moves the verification context."""
        self.enterContext(patch.object(config, "VERIFY_TIMEOUT", config.VERIFY_TIMEOUT + 1))

    def records_a_later_run(self) -> None:
        """A later transaction of the same run recorded between ticks, its publication still owed.

        Minted past every revision the issue has spent and recorded by the
        evidence domain's own recorder, which raises the revision floor: the
        current evidence is no longer the latest this issue has recorded.
        """
        state = self.github.read_pinned_state(self.issue)
        current = _current_evidence(self)
        pending = _record_state.mint_pending_evidence(
            state, self.issue.number, current.binding, _verified.passing_run(),
        )
        if not _record_state.record_pending_evidence(state, pending):
            raise AssertionError("the pinned comment would not record the later run")
        self.restates(**state.data)


class _ReadinessFixture(EvidenceMoves, RecordEdits, _ping._ReadyPingFixture):
    """The ready ping's world under a configuration requiring the suite, qualified by one route or the other."""

    def setUp(self) -> None:
        super().setUp()
        self.enterContext(patch.object(config, "VERIFY_COMMANDS", (SUITE,)))

    def seeded_on(self, route: str) -> None:
        """Seed the world with `HEAD` qualified by `route`: its docs stamped, or approved on GitHub, and no more."""
        self.seeded()
        documented = route == DOCS_ROUTE
        self.pull_request.approved = not documented
        if documented:
            self.restates(**_DOCS_STAMPS)

    def tick(self, **run_options):
        """One in_review tick, over the checkout here and the branch where the pull request stands, unless named."""
        return self._run_in_review(
            self.github, self.issue, run_agent=_ping._agent(),
            **{**_verified.proving(self.github, self.issue), **run_options},
        )

    def standing(self) -> tuple:
        """What the ping has done: the pings on the thread, the ping recorded and pending, writes, and relabels."""
        pinned = self.pinned()
        return (
            len(self.pings()),
            pinned.get(_ping.READY_PING_SHA),
            pinned.get(_ping.PENDING),
            self.github.write_state_calls,
            tuple(self.github.label_history),
        )

    def assert_withheld(self, before: tuple) -> None:
        """Nobody pinged, nothing armed or recorded, nothing written or relabelled since `before`."""
        self.assertEqual(self.standing(), before)
        self.assertEqual(before[:3], (0, None, None))

    def armed(self, route: str) -> str:
        """Seed `route` and tick with the arming's answer lost; the receipt it armed, nothing posted."""
        self.seeded_on(route)
        with _ping.failing(self, _ping.LOST, settling=False):
            self.tick()
        return self.pinned()[_ping.PENDING]["receipt"]

    def withheld_over(self, route: str, moves, **readings) -> None:
        """Seed `route`, have `moves` move the world where given, and tick over `readings`: the ping is withheld.

        The case is set up afresh behind it, for the next.
        """
        self.seeded_on(route)
        if moves is not None:
            moves(self)
        before = self.standing()
        self.tick(**readings)
        self.assert_withheld(before)
        self.doCleanups()
        self.setUp()


class BehindTheArming:
    """GitHub landing the ping's arming, `move` made on the case once it has; every other edit answered as always."""

    def __init__(self, case, move) -> None:
        self._case = case
        self._move = move
        self._edit = case.github.edit_pinned_state

    def __call__(self, issue, state, **options):
        edited = self._edit(issue, state, **options)
        arming = isinstance(state.get(_ping.PENDING), dict)
        if arming and not isinstance(options["over"].get(_ping.PENDING), dict):
            self._move(self._case)
        return edited


class BehindThePreparation:
    """The pinned comment read for the ping's settlement to be prepared over, `move` made on the case behind it.

    That reading is the first the tick takes, past its opening one, of a
    comment recording a ping pending: the arming's own reading precedes the
    record, and a pending record an earlier tick armed is already on the
    opening one. `nth` 2 is the second such reading instead: the comment read
    afresh behind the last proof. Every other reading is answered as always.
    """

    def __init__(self, case, move, nth: int = 1) -> None:
        self._case = case
        self._move = move
        self._read = case.github.read_pinned_state
        self._reads = 0
        self._owed = nth

    def __call__(self, issue):
        state = self._read(issue)
        self._reads += 1
        if self._reads > 1 and isinstance(state.get(_ping.PENDING), dict):
            self._owed -= 1
            if not self._owed:
                self._move(self._case)
        return state


class _Ends:
    """Every re-read of an artifact answered, the pull request merged or closed behind it, its head where it was."""

    def __init__(self, case, *, merged: bool) -> None:
        self._pull_request = case.pull_request
        self._reread = case.github.reread_verification_artifact
        self._merged = merged

    def __call__(self, *asked, **named):
        answered = self._reread(*asked, **named)
        self._pull_request.merged = self._merged
        self._pull_request.state = "closed"
        return answered


def _current_evidence(case) -> _records.CurrentEvidence:
    """The evidence `case`'s pinned comment records as current."""
    return _settlement.read_current_evidence(PinnedState(state_data=case.pinned()))
