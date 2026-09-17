# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The one id space every comment this double hands out is numbered in.

GitHub numbers issue comments in a single ascending space per repository, and
the orchestrator reads a thread by COMPARING those ids: a watermark says
everything at or below it has been read, and a comment posted after a reply
lands above it. A double that numbers each thread from its own comments, or
that mints pinned records and pull-request comments from a counter the threads
never move, reproduces neither -- it hands two threads the same id, puts a
seeded reply below a record minted after it, and makes every bug that turns on
that ordering invisible.

So there is exactly one allocator and every id comes out of it. It sits in its
own module rather than on the issue-comment service because the pull-request
service and the pinned-record service mint ids too, and an allocator owned by
one of the three is one the other two are free to bypass.

A thread handed straight to the real adapter has no client behind it at all --
the issue is the only object in the call -- so it cannot consult that counter.
It draws from `next_thread_comment_id` below, which holds the same floor over
the same threads, and both sources therefore still number in one space.
"""

from __future__ import annotations

from typing import Any

# Where the space starts. High enough that a case hand-picking a small id is
# still below everything minted, which is what a seeded "already read" mark is.
_FIRST_COMMENT_ID = 1000

# The two attributes a thread keeps its comments under: an issue's own, and
# the issue-comment list a pull request carries.
_THREADS = ("comments", "issue_comments")


class _CommentIdAllocator:
    """The shared, monotonic source of every comment id this double mints.

    Monotonic against what the client has MINTED and against what any thread
    already carries, because those are two different things. A case that
    preloads an issue with hand-numbered comments never went through here, so
    a mark read off the counter alone hands out an id such a thread already
    uses -- and a reply sharing an id with the watermark is one no reader ever
    sees.
    """

    def _next_comment_id(self, *threads: Any) -> int:
        """The next id this client mints, above every id it can see.

        `threads` are the ones the caller holds and this client may not know:
        an issue a case built without registering it. `None` among them is a
        caller that had only a number and could not resolve it, which is an
        allocation over the threads this client knows and nothing more.
        Everything it does know -- its issues and its pull requests -- is
        scanned regardless, since an id handed out twice across two threads is
        the same collision as one handed out twice on one.
        """
        self._comment_id = max(self._comment_id, self._highest_seen(threads))
        self._comment_id += 1
        return self._comment_id

    def _highest_seen(self, threads: tuple) -> int:
        """The highest id any thread this call can reach already carries."""
        known = [*self._issues.values(), *self.pulls.values()]
        known.extend(thread for thread in threads if thread is not None)
        seen = [0]
        for thread in known:
            seen.extend(posted.id for posted in _comments_on(thread))
        return max(seen)


def next_thread_comment_id(thread: Any) -> int:
    """The next id a thread mints for itself, with no client in the call.

    The real pinned-state write is handed an issue and nothing else, so the
    only ids in reach are the ones that thread already carries. Drawn above
    the floor as well as above them, which is the promise the allocator makes
    and the one that matters here: a case is free to hand-number a thread
    below the floor, and a minted id repeating one of those is a comment some
    reading hides.
    """
    seen = [_FIRST_COMMENT_ID, *(posted.id for posted in _comments_on(thread))]
    return max(seen) + 1


def _comments_on(thread: Any) -> tuple:
    """Every comment one thread carries, whichever attribute it keeps them in.

    An issue keeps its own; a pull request keeps the issue comments posted
    onto it. Both are numbered in the space above, so both have to be seen.
    """
    return tuple(
        posted
        for kept in _THREADS
        for posted in getattr(thread, kept, ())
    )
