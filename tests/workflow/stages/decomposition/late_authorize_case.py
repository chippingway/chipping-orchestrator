# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A candidate awaiting unsplit authorization, its frozen evidence, and crash setup."""
from __future__ import annotations

import contextlib
from unittest.mock import patch

from orchestrator.git.measurement.models import (
    FINGERPRINT_FORMAT,
    AdditionMeasurement,
    FingerprintFailure,
)
from orchestrator.workflow.late_split import overrides as _overrides
from tests.workflow.stages.decomposition import (
    late_content_replies as _content_replies,
    late_content_support as _support,
    late_test_support as _stage_support,
)
from tests.workflow.stages.decomposition.late_content_support import LateContentCase
from tests.workflow.stages.decomposition.late_run_support import WorktreeSeed
from tests.workflow.stages.decomposition.late_settlement_support import (
    OWNER_GUARD,
    killed_at,
)

ALLOWED_AUTHORS = "ALLOWED_ISSUE_AUTHORS"

LABEL_DECOMPOSING = "workflow:decomposing"
LABEL_IMPLEMENTING = "workflow:implementing"

KEY_LAST_ACTION_COMMENT_ID = "last_action_comment_id"

# The phrase each answer this owner can write is recognized by. Asserted on
# rather than the whole sentence, because what these tests are about is which
# of them was said.
ACCEPTED_NOTICE = "authorized to publish unsplit"
WRONG_CANDIDATE_NOTICE = "names a commit this issue is not waiting on"
NO_VERDICT_NOTICE = "no longer show"
CONTINUE_REFUSED_NOTICE = "is not a decision to publish an oversized change"

SAID_ONCE = 1

# An outsider's own comment, and one a human wrote before the park fired.
# Both sit below the notice's id, which is what makes the second one stale.
OUTSIDER_COMMENT_ID = 200
EARLY_COMMENT_ID = 20

# What one authorization leaves on the pinned comment, and what each field has
# to be. Every term comes from the frozen generation rather than from the
# command: the record is what a later reader holds the decision to, so a term
# the human supplied would let them authorize something they never read.
_AUTHORIZED_TERMS = (
    (_overrides.LATE_OVERRIDE_CANDIDATE_SHA, _stage_support.CANDIDATE_SHA),
    (_overrides.LATE_OVERRIDE_BASE_SHA, _stage_support.BASE_SHA),
    (_overrides.LATE_OVERRIDE_FINGERPRINT, _stage_support.CONTRIBUTION_DIGEST),
    (_overrides.LATE_OVERRIDE_FINGERPRINT_FORMAT, FINGERPRINT_FORMAT),
    (_overrides.LATE_OVERRIDE_ADDITIONS, _stage_support.ADDITIONS),
    (_overrides.LATE_OVERRIDE_THRESHOLD, _stage_support.THRESHOLD),
)

# Every argument that is not the commit this issue is parked on: one it was
# replaced by, the abbreviation nothing here ever writes, prose, and a command
# with no argument at all. All four ARE the command -- an operator wrote it --
# so all four are owed the same answer rather than being read as guidance.
_NOT_THE_CANDIDATE = (_stage_support.OTHER_SHA, _stage_support.CANDIDATE_SHA[:7], "the one above", "")

# A store holding both frozen commits and unable to hand back the content
# between them. Nothing about it is the operator's doing, so their command is
# not spent on it.
_UNFINGERPRINTED = WorktreeSeed(fingerprint=FingerprintFailure.CONTENT_ABSENT)

# The same pair reading back as some OTHER contribution: what a replaced
# object, a hand-edited record, and an older binary's digest all look like from
# the publication's side, and the one term the record cannot arrange for
# itself.
_MOVED_DIGEST = "7" * _stage_support.DIGEST_LENGTH

_MOVED_CONTRIBUTION = WorktreeSeed(fingerprint=_MOVED_DIGEST)

# The one re-measurement that leaves every term of the record matching: the
# developer acknowledged the committed work, nothing moved, and the base is
# the one it was frozen over. Only the generation counter has advanced, which
# is the identity the record deliberately does not carry.
_UNCHANGED_MEASUREMENT = AdditionMeasurement(
    base_sha=_stage_support.BASE_SHA, candidate_sha=_stage_support.CANDIDATE_SHA, additions=_stage_support.ADDITIONS,
)

# What a pinned write that never lands raises. The type is not the point --
# every caller here lets it out -- but the tick dying inside the write is.
_WRITE_REFUSED = "the pinned comment was refused"


@contextlib.contextmanager
def refused_write(github):
    """The pinned write a tick is about to make failing outright.

    What it turns into an assertion is the window every answer this owner
    writes has: the sentence lands and the write that consumes what it answers
    does not, so the next tick reads the same reply again.
    """
    with patch.object(
        github, "write_pinned_state",
        side_effect=RuntimeError(_WRITE_REFUSED),
    ):
        yield


class _AuthorizeCase(LateContentCase):
    """One late issue parked on the decision this command ends."""

    def setUp(self) -> None:
        self._park()

    def _park(self, **state) -> None:
        """Seed the issue as one an adjudicator answered `single` about."""
        self._seed(**{**_support.SINGLE_PARKED, **state})

    def _command(self, named: str = _stage_support.CANDIDATE_SHA):
        """Post the authorization as a reply to the park's own notice."""
        return _content_replies.reply(self.issue, _content_replies.authorization(named))

    def _tick(self, **run_fields):
        """Run one adjudication, keeping the spawn for the caller to assert."""
        outcome, spawn = self._run(**run_fields)
        self.spawn = spawn
        return outcome

    def _authorized(self):
        """The candidate the pinned record says was authorized, if any."""
        return self._pinned().get(_overrides.LATE_OVERRIDE_CANDIDATE_SHA)

    def _authorize_then_crash(self) -> None:
        """Land the authorization, then die before anything it licenses.

        The write goes out before the owner read, so the record, the cleared
        park and the consumed reply are all durable and the publication is
        the only thing left -- which is the state every recovery below is
        about.
        """
        self._command()
        with killed_at(OWNER_GUARD), self.assertRaises(KeyboardInterrupt):
            self._tick()
        self.assertEqual(self._authorized(), _stage_support.CANDIDATE_SHA)

    def _assert_still_parked(self) -> None:
        """Nothing published, nothing recorded, and the question standing."""
        pinned = self._pinned()
        self.assertTrue(pinned.get(_stage_support.KEYS.awaiting))
        self.assertEqual(pinned.get(_stage_support.KEYS.park_reason), _support.PARK_SINGLE_DECISION)
        self.assertIsNone(self._authorized())
        self.assertNotIn(_stage_support.KEYS.exempt_sha, pinned)
        self.assertEqual(
            self.github.workflow_label(self.issue), LABEL_DECOMPOSING,
        )
