# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A parked implementing thread, and one resume taken over whatever is on it.

The resume under these cases is the real one; what is seeded is the agent run
behind it, because every question here is about the batch the run was handed
and what the issue records once it comes back. `_Resumed` carries the three
answers one call produces -- whether anything resumed, the call it made, and
the id of a reply written while the run was out -- since a case about the
window a run opens needs the last of those to say what must still be unread.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from unittest.mock import patch

from orchestrator.github.pinned_state import PINNED_STATE_MARKER
from orchestrator.workflow.engine import comments as _comments
from orchestrator.workflow.stages.implementing import (
    resume as _resume,
    resume_batch as _resume_batch,
    state as _state,
)
from tests.support.fakes import FakeComment, FakeGitHubClient, FakeUser, make_issue
from tests.workflow.fixtures import (
    _FAKE_WT,
    _TEST_SPEC,
    LABEL_IMPLEMENTING,
    _agent,
    _PatchedWorkflowMixin,
)

# The issue every case here is about, and how far its park had read the thread.
ISSUE_NUMBER = 614
PARKED_AT = 900

# The account the allowlist would name, and the one the token belongs to. They
# are separate here because the shared-PAT cases are about them being one.
TRUSTED_AUTHOR = "alice"
BOT_LOGIN = "orchestrator"

GUIDANCE = "make it smaller, please"
MORE_GUIDANCE = "and add a test"
NOTICE = "this issue is waiting on a human"

# A body somebody else pasted our own hidden marker into. An HTML comment is
# text anybody may write, so it admits nothing and refuses nothing but itself.
FORGED = f"looks fine to me\n\n{_comments._ORCH_COMMENT_MARKER}"

# A human reply quoting the pinned record's marker -- a payload pasted back to
# ask about it. Only the pinned comment itself is the record; this is a reply.
QUOTES_THE_RECORD = (
    f"why does it still say {PINNED_STATE_MARKER} "
    '{"awaiting_human": true}-- ? please retry'
)

RESUME_DEV_WITH_TEXT = "_resume_dev_with_text"

# Where the followup text lands in the positional resume call: the shape is a
# contract several callers wrote against, so a case reads the prompt off it.
FOLLOWUP_ARGUMENT = 4


@dataclass(frozen=True)
class _Resumed:
    """What one resume answered, what it asked for, and what landed under it."""

    answered: Any
    call: Any
    landed: int = 0

    @property
    def followup(self) -> str:
        """The prompt text the developer was handed."""
        return self.call.call_args.args[FOLLOWUP_ARGUMENT]


class _RunsWhileOneLands:
    """The seeded run, and a reply written in the minutes it is out for.

    A class rather than a closure because what it stands in for is a value
    with a name -- the resume this repository patches -- and the reply it
    writes has to land between the prompt being built and the settlement
    being taken, which is the only window a test can put it in.
    """

    def __init__(self, case, resumed: tuple, lands: str = "") -> None:
        self._case = case
        self._resumed = resumed
        self._lands = lands
        self.landed = 0

    def __call__(self, *called, **options) -> tuple:
        if self._lands:
            self.landed = self._case._they_say(self._lands)
        return self._resumed


class _ParkedThread(_PatchedWorkflowMixin):
    """An implementing issue parked awaiting a human, its thread already read.

    The hermetic patch context comes with it, for the cases that run a whole
    tick rather than the resume helper: what a prompt really carried is a
    question only the dispatched handler can answer.
    """

    def setUp(self) -> None:
        self.github = FakeGitHubClient(bot_login=BOT_LOGIN)
        self.issue = make_issue(ISSUE_NUMBER, label=LABEL_IMPLEMENTING)
        self.github.add_issue(self.issue)
        self._seed()

    def _seed(self, **pinned) -> None:
        """Replace the pinned comment with the park a case is about."""
        self.github.seed_state(ISSUE_NUMBER, **{
            _state._AWAITING_HUMAN: True,
            _state._LAST_ACTION_COMMENT_ID: PARKED_AT,
            **pinned,
        })
        self.state = self.github.read_pinned_state(self.issue)

    def _we_say(self, body: str) -> int:
        """Post one comment the way this workflow posts every one of them."""
        posted = _comments._post_issue_comment(
            self.github, self.issue, self.state, body,
        )
        self.github.write_pinned_state(self.issue, self.state)
        return posted.id

    def _we_said_unrecorded(self, body: str) -> int:
        """One of our own comments whose id-recording write never landed.

        Posted through the client the way the workflow posts it -- marker and
        our own login included -- and then left out of the ledger, which is
        what a process dying between the post and the pinned write leaves.
        """
        posted = self.github.comment(
            self.issue, _comments._with_orch_marker(body),
        )
        return posted.id

    def _they_say(self, body: str, author: str = TRUSTED_AUTHOR) -> int:
        """Add one reply past the park's watermark, from `author`."""
        identified = self.github.next_reply_id(self.issue)
        self.issue.comments.append(
            FakeComment(identified, body, user=FakeUser(author)),
        )
        return identified

    def _watermark(self) -> Any:
        return self.state.get(_state._LAST_ACTION_COMMENT_ID)

    def _resumes(self, *, run: Any = None, lands: str = "", **frozen) -> _Resumed:
        """Take one resume over this thread with the run's outcome seeded.

        `paused` is the live-pause flag the run comes back with; everything
        else in `frozen` reaches the freeze -- `continue_claimed`, which is how
        a caller says the parked-continue classifier has already looked at this
        thread. `implementing`'s preflight guarantees that and `validating`'s
        awaiting-human road deliberately does not, so the asymmetry is the
        caller's to state.
        """
        returned = (
            _FAKE_WT, _agent() if run is None else run, frozen.pop("paused", False),
        )
        running = _RunsWhileOneLands(self, returned, lands)
        with patch.object(_resume, RESUME_DEV_WITH_TEXT) as resumed:
            resumed.side_effect = running
            answered = _resume._resume_developer_on_human_reply(
                self.github,
                _TEST_SPEC,
                self.issue,
                _resume_batch._freeze(
                    self.github, self.issue, self.state, **frozen,
                ),
            )
            return _Resumed(answered, resumed, running.landed)
