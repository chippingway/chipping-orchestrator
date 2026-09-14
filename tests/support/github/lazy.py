# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A pull request that fails where a real one does: past the lookup.

The other doubles here are records -- what GitHub holds, spelled as fields. This
one is a behaviour: PyGithub hands back a lazy object, so `get_pr` asks GitHub
nothing and the requests that can fail are the attribute accesses behind it. A
guard around the lookup alone therefore covers none of them, and that is the
shape this double exists to reproduce.
"""
from __future__ import annotations

from tests.support.github.pull_request_models import FakePR

# What a lazy attribute read answers with where the request behind it failed.
LAZY_READ_REFUSED = "the pull request could not be read"

# The two attributes `pr_state` is derived from, both of them requests.
_LAZY_STATE_FIELDS = frozenset(("merged", "state"))


class LazyPullRequest:
    """A pull request whose facts are requests, the way PyGithub's are.

    A fetched pull request asks GitHub nothing; the request that can fail is
    the ATTRIBUTE READ behind it -- the state, or the head. So a reading that
    fails fails past the lookup, which is exactly where a `try` around the
    lookup alone stops covering. `failing` names which read refuses: `state`
    for either attribute `pr_state` is derived from, or any attribute name.
    """

    def __init__(self, pull_request: FakePR, *, failing: str) -> None:
        self._pull_request = pull_request
        self._failing = failing

    def __getattr__(self, name: str):
        if self._failing == name or (
            self._failing == "state" and name in _LAZY_STATE_FIELDS
        ):
            raise RuntimeError(LAZY_READ_REFUSED)
        return getattr(self._pull_request, name)
