# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The park reasons, pinned-state keys, and run identity the question owners share.

The reasons and keys go into the pinned JSON comment live issues already carry,
so renaming one is a migration rather than a refactor -- and two of them are
read from outside this package as well: `workflow/stages/implementing/` refuses
a `question` -> `implementing` relabel by matching the `question_` prefix, and
the `question_agent` / `question_session_id` pair is what keeps a multi-turn
Q&A locked to the backend that answered its first round.

`_PR_NUMBER` is the one key here this stage never writes. An issue arrives at a
question carrying whatever the stage before it recorded, so it is read to
correlate a park with the pull request the conversation is about -- and absent
on every issue that has never had one, which is why nothing here may infer it.

`_UNSAFE_QUESTION_PARKS` is the set that decides a tick's cleanup policy before
it runs anything: those three are the outcomes where the agent left something on
disk, so the worktree has to survive for an operator to inspect.

`_QUESTION_STAGE` is not pinned state at all: it is what an audit event and an
analytics row attribute a run to, and the role the stage's own agent answers
under. The two route names beside it are the same kind of value -- the road a
tick reached its park from, which a park's record carries because nothing
downstream can re-derive it. The stage on that record says which handler wrote
the park, never whether the conversation was being opened or answered, and the
flag that told those apart is cleared by the resume itself on its way to the
disposition.
"""
from __future__ import annotations

_QUESTION_STAGE = "question"

_ROUTE_QUESTION_ROUND = "question_round"

_ROUTE_QUESTION_RESUME = "question_resume"

_QUESTION_AGENT_KEY = "question_agent"

_QUESTION_SESSION_KEY = "question_session_id"

_PR_NUMBER = "pr_number"

_QUESTION_ANSWER = "question_answer"

_QUESTION_COMMITS = "question_commits"

_QUESTION_DIRTY = "question_dirty"

_QUESTION_SILENT = "question_silent"

_QUESTION_TIMEOUT = "question_timeout"

_UNSAFE_QUESTION_PARKS = frozenset((
    _QUESTION_TIMEOUT, _QUESTION_COMMITS, _QUESTION_DIRTY,
))
