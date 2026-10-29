# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Git execution domain owners.

Plain and hardened `git` invocation together with the local
transport-config probe live in ``commands``; the hardened form for an
answer this process may not hold whole -- the request handed in on stdin,
the answer passed to a consumer a chunk at a time and assembled nowhere --
lives in ``streaming``, spawned on the argv prefix and the environment
``commands`` assembles rather than on copies of them; the per-repository
token and the askpass session built from it live in ``credentials``; the
authenticated fetches and the lease-pinned branch push that spend one of
those sessions live in ``branch_transport``; the exact-ref read and the
lease-pinned writes it leases, each named by a whole refname, live in
``ref_transport``; the listing of every refname a remote carries under a
pattern lives in ``ref_discovery``, apart from the transport because
nothing is pinned to what it says; the process-local per-target-root lock
registry lives in ``locks``; and the question a caller hands in for the
length of a push -- whose checkout this still is -- which the branch push
asks immediately before ``git push``, lives in ``push_questions``. Every
git-execution name is defined on one of these owners, and callers import
the owner they need directly, so this initializer binds nothing and an
import pulls in only what the chosen owner itself needs --
``branch_transport`` builds on ``ref_transport`` for the one remote read a
branch shares with a refname and on ``push_questions`` for the caller's
question, those two build on ``commands``, ``credentials``, and ``locks``,
``ref_discovery`` on the first two of those alone since it takes no lock,
``credentials`` on ``commands``, ``streaming`` on ``commands`` alone for
the hardening policy it is spawned under, while ``commands``, ``locks``,
and ``push_questions`` depend on nothing else in the package.

No facade of this domain's own sits beside the package, and nothing above it
republishes these names either, so each answers on the owner that defines it
and a test intercepting one targets that owner -- which is what every caller
in the tree names: the ``git/worktrees/``, ``git/publication/``, and
``git/base_sync/`` owners; the conflicts, documenting, implementing, and
validating stages for the fetches and the push, and the discussion and
implementing stages for the push question; ``git/snapshots/`` for the
leased ref read and writes, with ``git/worktrees/`` naming the same delete
once a teardown has proved what it stands on and the pattern listing on the
namespace it discovers those branches in; ``git/measurement/`` for the
streamed runner a contribution's fingerprint is folded through, since the
content it hashes is as large as an agent committed it; and the conflicts,
documenting, and fixing stages for the two runners. The two transports and
the discovery listing are the only callers ``credentials`` has and each
names that owner rather than importing a session helper of its own, so a test
intercepting the session targets the module that defines it. All four name
their logger ``orchestrator.git_plumbing`` rather than after this package,
because that is the name operator log filters select on.
"""
