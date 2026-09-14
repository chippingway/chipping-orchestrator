# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Trust policy for GitHub-authored content.

The orchestrator feeds issue and PR comments to coding agents as
workflow-driving instructions. On a public repo that is an injection
surface: any account can post a comment that steers the agent. These
helpers centralize the "may this author supply workflow-driving content?"
decision so every consumer applies one allowlist policy.

The decision is about an author on a GitHub thread, so it belongs beside
the readers that produce those threads rather than above them: the git
base-sync owners and the workflow stage leaves both gate on it, and
neither should have to reach up into the workflow layer to ask.

Policy (keyed on `config.ALLOWED_ISSUE_AUTHORS`):

* Empty (the default) -- no allowlist configured. Preserve the legacy
  single-user behavior: every author is trusted.
* Populated -- only accounts whose login is in the allowlist are trusted,
  compared case-insensitively (GitHub logins are case-insensitive). This
  gates Bot / GitHub-App accounts too: a bot is trusted only when its own
  login is explicitly listed, so a stray CI or dependency bot cannot
  inject workflow-driving content, while an intentionally allowlisted
  automation account still can.

The low-level readers (`GitHubClient.comments_after`, the PR comment /
review readers) stay raw. Callers that want the allowlist applied filter
their result through `filter_trusted`, or gate a single author on
`is_trusted_author`.

`authored_by_us` and the `carries_own_marker` built on it answer a different
question and live here for the same reason: whether a comment on a thread is
one this orchestrator wrote. That question is asked wherever a comment is the
receipt for an effect that cannot be made one operation with recording it, and
the author is part of it -- text anybody may post is text anybody may use to
suppress the sentence it stands for, whether the receipt is a hidden marker or
the sentence itself. A client with no authenticated login to compare against
takes the content alone, which is the same fallback the pinned-state read
takes.
"""
from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from orchestrator import config

# What every hidden receipt this orchestrator writes begins with -- the pinned
# state comment, the split's forward link and supersession notices, and the
# marker a child issue is stamped with. One prefix because they are one thing:
# a claim, invisible in the rendered thread, that a step already happened.
RECEIPT_MARKER_PREFIX = "<!--orchestrator-"


def _allowed_logins(allowed: Iterable[str] | None) -> set[str]:
    """Lower-cased allowlist set, defaulting to `config.ALLOWED_ISSUE_AUTHORS`.

    Falsy entries are dropped so a stray empty string in the configured
    tuple cannot match a user whose login failed to load (empty login).
    """
    if allowed is None:
        allowed = config.ALLOWED_ISSUE_AUTHORS
    return {login.lower() for login in allowed if login}


def is_trusted_author(
    user: Any, *, allowed: Iterable[str] | None = None
) -> bool:
    """True if `user` may supply workflow-driving content.

    `user` is any object exposing a `.login` attribute -- a PyGithub
    `NamedUser`, the test `FakeUser`, or `None` for a comment whose author
    failed to load. `allowed` defaults to `config.ALLOWED_ISSUE_AUTHORS`;
    pass an explicit iterable to exercise the policy without patching config.

    An empty allowlist trusts everyone (legacy behavior). A populated
    allowlist trusts only logins it contains, compared case-insensitively;
    a missing user or empty login is untrusted. Bot / App accounts follow
    the same rule -- trusted only when their login is explicitly allowlisted.
    """
    allowed_lower = _allowed_logins(allowed)
    if not allowed_lower:
        return True
    login = getattr(user, "login", None) or ""
    return login.lower() in allowed_lower


def filter_trusted[CommentT](
    comments: Iterable[CommentT], *, allowed: Iterable[str] | None = None
) -> list[CommentT]:
    """Keep only comments whose author is trusted (see `is_trusted_author`).

    Each item is any object exposing a `.user` attribute. Input order is
    preserved. With no allowlist configured every item is kept, so this is
    a safe drop-in over a raw `comments_after` / PR-reader result that
    changes behavior only once an operator opts into the allowlist.
    """
    allowed_lower = _allowed_logins(allowed)
    if not allowed_lower:
        return list(comments)
    return [
        comment for comment in comments
        if is_trusted_author(getattr(comment, "user", None), allowed=allowed_lower)
    ]


def carries_reserved_marker(written: Any) -> bool:
    """Whether text somebody else wrote carries a receipt marker of OURS.

    The other half of `carries_own_marker`, asked of content BEFORE it is
    embedded rather than of a thread after it is read back. A receipt is
    recognized by substring, because that is all a body search can do -- so
    text that already carries one, from an agent's declared scope to a human's
    issue body, can make a later lookup read some other issue as the receipt
    for a step nobody took there. Content carrying one is refused where it is
    declared, which is the only place the two can still be told apart.

    Anything that is not text carries nothing, so a missing field answers no
    rather than raising: the caller is validating somebody else's structure,
    and an absent title is not a forged one.
    """
    return isinstance(written, str) and RECEIPT_MARKER_PREFIX in written


def authored_by_us(comment: Any, *, bot_login: str | None) -> bool:
    """Whether this orchestrator is the one that posted a comment.

    The author half of every receipt read off a thread, spelled once because
    the receipts differ and the rule does not: a hidden marker, and a park
    notice whose whole sentence is its identity, are both plain text on a
    public thread and both trivially copied. Read from anybody, either would
    let a third party discharge an obligation nobody discharged.

    A client with no authenticated login of its own answers True. There is
    nothing to compare against there, so the content is the whole of what can
    be checked -- the same fallback the pinned-state read takes.
    """
    if bot_login is None:
        return True
    author = getattr(getattr(comment, "user", None), "login", None)
    return author == bot_login


def carries_own_marker(
    comments: Iterable[Any], marker: str, *, bot_login: str | None,
) -> bool:
    """Whether one of these comments is OURS and carries `marker`.

    Both halves are required. The marker says which effect the comment is the
    receipt for, and it has to be scoped by its caller to the one episode it
    belongs to -- a marker shared across episodes reads a previous one's
    receipt as this one's. The author says the receipt is ours: an HTML
    comment is invisible in the rendered thread and trivially copied, so
    without the check a third party could post the marker and silence
    whatever the receipt gates.
    """
    return any(
        marker in (getattr(comment, "body", "") or "")
        and authored_by_us(comment, bot_login=bot_login)
        for comment in comments
    )
