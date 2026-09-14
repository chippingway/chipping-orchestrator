# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""How many lines a candidate adds over its base, counted across every path.

The count is the prospective pull request's own diff -- the frozen base
against the exact candidate commit, three-dot, so a base that moved on since
the branch forked is not read as work this branch did -- and it is deliberately
the plainest reading of it there is. Every path counts. There is no exemption
for a lockfile, generated code, a migration, a snapshot, a golden fixture, an
i18n catalog, a notebook, a vendored tree, a mass move, or a mass reformat: an
exemption list is a bypass anybody can move work into, and the number is only
worth adjudicating if a reader can reproduce it from the diff in front of them.

Two of the readings that follow from that are git's to make rather than this
owner's. Binary content has no lines in it to add, so git reports `-` for the
path and it totals nothing. And a move is not one event here: `--no-renames`
is passed, so a relocated file is reported as the deletion and the addition it
literally is, and the content that arrived at its new path counts like content
arriving anywhere else. With rename detection on it would cost nothing at all,
which is a candidate made to measure small by moving into place what it was
going to write anyway.

Which paths have lines at all -- and how many lines they come to -- is decided
by inputs the agent can write, so the reading is pinned to the commit rather
than to the checkout it is taken in. The algorithm is part of that: git's
algorithms pair a change with repeated lines in it differently, and the same
two commits count 4 additions per path under `myers` and 7 under `histogram`,
so a count left to `diff.algorithm` is one a `git config` beside the work can
retune the ceiling from below. By
default git resolves `.gitattributes` out of the WORKING TREE, so an
uncommitted `* -diff` beside the work has every path report as binary and a
candidate of any size measure as zero -- while the pull request a human then
reads shows the text in full. The attribute source is therefore pinned to the
candidate's own tree -- in the ENVIRONMENT, since `GIT_ATTR_SOURCE` outranks
the config a `-c` would set and an inherited one would otherwise name any tree
it liked -- the user and system attribute files are taken out of the reading,
and the size above which git stops looking for lines is restated at its default
so a `core.bigFileThreshold` planted in the shared repository cannot lower it. A
`.gitattributes` the candidate COMMITS is left to speak: it is part of what is
being measured and part of what a reviewer sees.

Two inputs are outside all of that, and a measurement refuses rather than
reports when either is present. `$GIT_DIR/info/attributes` is not config, so no
override on the command line reaches it, and it outranks the pinned tree. A
diff driver defined in the repository's own config can declare a path binary
once anything assigns it. Both live where the agent works, and neither can be
neutralized from here.

A reading that could not be taken is never a small candidate. A diff that
failed and a record this build cannot account for are both typed failures with
no number beside them, because what a failed `git diff` writes to stdout is
nothing -- the same thing a candidate that changes nothing writes -- and
publishing on that reading is how an unadjudicated implementation goes out.
"""
from __future__ import annotations

import logging
import os
import stat
from collections.abc import Mapping
from pathlib import Path
from types import MappingProxyType

from orchestrator.config import models as _config_models
from orchestrator.git import commands
from orchestrator.git.measurement import commits
from orchestrator.git.measurement.models import (
    AdditionMeasurement,
    MeasurementFailure,
)

log = logging.getLogger("orchestrator.git_plumbing")

# What the diff is asked for and how it comes back. `--numstat` is the only
# form that reports per-path counts machine-readably AND says outright that a
# path was binary; `-z` because the caller counts records rather than reading
# paths, and git's default output quotes an unusual name and could split one
# record across what reads as two.
_NUMSTAT = "--numstat"

_NO_RENAMES = "--no-renames"

_NUL_DELIMITED = "-z"

# Spelled on the command line because the worktree's own `.git/config` is
# agent-writable and `diff.ignoreSubmodules=all` set there would drop a moved
# gitlink from a count that is supposed to cover every path.
_IGNORE_SUBMODULES_NONE = "--ignore-submodules=none"

# Which of git's algorithms decides what "added" means, stated at the default
# rather than left to `diff.algorithm`. The algorithms disagree about how to
# pair up a change with repeated lines in it, and they disagree by whole lines:
# the same two commits count 4 additions per path under `myers` and 7 under
# `histogram`. A number that moves with a setting in the shared repository is
# not one a verdict can be defended by -- two hosts would adjudicate the same
# candidate differently, and a `git config` beside the work would retune the
# ceiling from below it.
_DIFF_ALGORITHM = "--diff-algorithm=myers"

# `diff.relative` restricts a diff to the directory it is run from and reports
# what survives under relative names. Every call here runs at the root of the
# worktree, so it changes nothing today -- and it is stated anyway, because
# "across every path" is the whole of what this count claims and no config in
# the checkout may narrow it.
_NO_RELATIVE = "--no-relative"

# The user-level attributes file, which lives at its own default path
# (`~/.config/git/attributes`) and is therefore still consulted with global and
# system CONFIG detached. A `* -diff` line planted there by anything running as
# this user would have every path report as binary. Pointed at nothing here.
_NO_ATTRIBUTES_FILE = ("-c", f"core.attributesFile={os.devnull}")

# Git's own default for the size at which it stops looking for lines and calls
# a blob binary, restated so the value cannot come from the shared
# repository's config -- which the agent's worktree can write, and where a
# threshold of `1` makes every file in the candidate binary.
_DEFAULT_BIG_FILE_THRESHOLD = ("-c", "core.bigFileThreshold=512m")

# Where the in-tree `.gitattributes` of the diff are read from, and it is an
# ENVIRONMENT setting rather than a `-c` because that is the one that wins:
# `GIT_ATTR_SOURCE` outranks the `attr.tree` config, so a value this process
# inherited would decide the reading over any pin on the command line. Left to
# itself git reads attributes out of the working tree -- the checkout the agent
# was just writing in -- so an UNCOMMITTED `* -diff` beside the work would have
# the commit measure as zero. Pinned to the candidate's own tree, the answer
# comes from the content being measured and matches what the pull request
# shows.
_ATTRIBUTE_SOURCE = "GIT_ATTR_SOURCE"

# The attributes installed beside git itself, which no `-c` reaches either.
# They are root-owned rather than agent-writable, but a measurement is only
# worth what it reports on any host, so the host-wide file is left out of it
# the same way the user's own is.
_NO_SYSTEM_ATTRIBUTES = MappingProxyType({"GIT_ATTR_NOSYSTEM": "1"})

# The attribute source no command line reaches: not config, so no `-c`
# overrides it, and it outranks both the pinned tree and the user file.
_INFO_ATTRIBUTES = "info/attributes"

# Config that can declare a path binary once an attribute assigns it. Global
# and system config are detached by the hardened envelope, so a match is the
# shared repository's own -- writable from the agent's worktree, and reachable
# by nothing on the command line.
_BINARY_DRIVER_CONFIG = r"^diff\..*\.(binary|textconv|command)$"

# The field layout of one `--numstat -z` record: added, deleted, and the path,
# tab-separated, with `-` in both count fields when git has nothing textual to
# report for it. Only the two count fields are split off, because a path is
# allowed to contain a tab and splitting on every one of them would make a
# legal filename unreadable.
_NUMSTAT_FIELDS = 3

_COUNT_FIELDS = 2

_FIELD_SEPARATOR = "\t"

_BINARY_COUNT = "-"

_NUL_SEPARATOR = "\0"


def _measure_candidate(
    spec: _config_models.RepoSpec, worktree: Path, revision: str,
) -> AdditionMeasurement:
    """Measure what `revision` adds over the frozen remote base, or say why not.

    The whole measurement in the order its steps have to be taken: freeze the
    base the remote names, prove the candidate is a commit this host can read,
    then count between the two ids that survived. Each step is asked only once
    the one before it succeeded, so a failure names the first thing that was
    missing rather than a diff error standing in for a missing token.

    What was established before the stop is carried on the result. A candidate
    that could not be proved still reports the base that was frozen for it, so
    the record written before the retry -- and the comment a human reads --
    names the commit this attempt was going to measure against rather than
    re-deriving one from a branch that has moved since. The stopping end's own
    line travels with it for the same reason: this is the last owner that
    holds it, and everything past here reports a measurement that did not
    happen from the record alone.
    """
    base = commits._freeze_base_commit(spec, worktree)
    if not base.is_frozen:
        return AdditionMeasurement(
            failure=base.failure, detail=base.detail,
        )
    candidate = commits._prove_candidate_commit(worktree, revision)
    if not candidate.is_frozen:
        return AdditionMeasurement(
            base_sha=base.sha,
            failure=candidate.failure,
            detail=candidate.detail,
        )
    return _count_added_lines(worktree, base.sha, candidate.sha)


def _count_added_lines(
    worktree: Path, base_sha: str, candidate_sha: str,
) -> AdditionMeasurement:
    """Count the lines `candidate_sha` adds against `base_sha`.

    Both ends are ids the caller established, and naming them is what makes
    the reading repeatable: the same pair measures to the same number on the
    next tick, on a retry after a crash, and in the diff a human opens to check
    it. Nothing here consults a ref, so neither the branch moving nor the base
    advancing changes what a frozen pair says.

    Hardened for the reasons every read of an agent-writable worktree is, and
    for one that belongs to this reading in particular: object replacement
    would have git count the diff of a commit nobody wrote under the id the
    record names, so the envelope that turns it off is what ties this number to
    the commit that gets published.

    Pinned as well as hardened, because both what counts as text and how many
    lines it comes to are decided by inputs that are not commits: the attribute
    source is the candidate's own tree rather than the checkout the diff is
    taken in, the user and system attribute files are taken out of it, the
    big-file threshold is restated at its default, the algorithm that pairs a
    change up is named, and the diff is held to the whole repository rather
    than to a directory. The two pins that go in the environment are there
    because the environment outranks the command line for them -- an inherited
    `GIT_ATTR_SOURCE` would otherwise name whatever tree it liked. What none of
    that reaches is refused rather than reported on, since a reading nobody can
    pin would call a candidate of any size zero.
    """
    unpinnable = _unpinnable_diff_inputs(worktree)
    if unpinnable:
        log.error(
            "refusing to measure %s...%s in %s: the diff would be decided by "
            "%s, which no override here reaches",
            base_sha, candidate_sha, worktree, unpinnable,
        )
        return AdditionMeasurement(
            base_sha=base_sha,
            candidate_sha=candidate_sha,
            failure=MeasurementFailure.DIFF_UNPINNABLE,
        )
    diff_result = commands._git_hardened(
        *_NO_ATTRIBUTES_FILE,
        *_DEFAULT_BIG_FILE_THRESHOLD,
        "diff", _NUMSTAT, _NO_RENAMES, _NUL_DELIMITED,
        _IGNORE_SUBMODULES_NONE, _DIFF_ALGORITHM, _NO_RELATIVE,
        f"{base_sha}...{candidate_sha}",
        cwd=worktree,
        env_extra=_pinned_attributes(candidate_sha),
    )
    if diff_result.returncode != 0:
        log.warning(
            "the diff %s...%s could not be taken in %s: %s",
            base_sha, candidate_sha, worktree,
            (diff_result.stderr or "").strip(),
        )
        return AdditionMeasurement(
            base_sha=base_sha,
            candidate_sha=candidate_sha,
            failure=MeasurementFailure.DIFF_FAILED,
        )
    additions = _added_lines(diff_result.stdout or "")
    if additions is None:
        log.warning(
            "the diff %s...%s in %s reported a record this build cannot "
            "count, so the candidate has no measured size",
            base_sha, candidate_sha, worktree,
        )
        return AdditionMeasurement(
            base_sha=base_sha,
            candidate_sha=candidate_sha,
            failure=MeasurementFailure.DIFF_UNREADABLE,
        )
    return AdditionMeasurement(
        base_sha=base_sha, candidate_sha=candidate_sha, additions=additions,
    )


def _pinned_attributes(candidate_sha: str) -> Mapping[str, str]:
    """The environment one diff reads its attributes under.

    Both entries are here rather than on the command line because for these
    two the environment is what git consults last: an inherited
    `GIT_ATTR_SOURCE` beats an `attr.tree` given as config, so a `-c` pin would
    be overridden by whatever the process was started with, and the system
    attributes answer to no config key at all.
    """
    return {_ATTRIBUTE_SOURCE: candidate_sha, **_NO_SYSTEM_ATTRIBUTES}


def _unpinnable_diff_inputs(worktree: Path) -> str:
    """What would decide this diff that nothing on the command line reaches.

    Everything else this reading depends on is stated as an override, and an
    override wins over any config a worktree carries. These two do not answer
    to one. `$GIT_DIR/info/attributes` is a file rather than a setting, and it
    outranks every attribute source there is; a diff driver declared in the
    shared repository's config turns a path binary the moment any attribute
    assigns it, including one the candidate legitimately committed. Both are
    writable from the checkout the agent works in.

    So a measurement that finds either refuses instead of reporting, and says
    what it found: the alternative is a number that reads as a small candidate
    and was decided by whatever was planted. Empty when the reading can be
    pinned, and the two findings are joined rather than one shadowing the
    other, since an operator clearing one has to clear both.
    """
    found = []
    drivers = commands._git_hardened(
        "config", "--get-regexp", _BINARY_DRIVER_CONFIG, cwd=worktree,
    )
    driver_config = (drivers.stdout or "").strip()
    if drivers.returncode == 0 and driver_config:
        found.append(f"repository diff-driver config ({driver_config})")
    planted = _planted_attributes(worktree)
    if planted:
        found.append(planted)
    return "; ".join(found)


def _planted_attributes(worktree: Path) -> str:
    """The repository-local attributes file, named if it carries anything.

    Located through git rather than assembled from the worktree path, because
    a linked worktree keeps its own git directory while `info/` stays in the
    shared one -- so the file an agent plants from the issue's checkout is the
    file every other checkout of that clone is measured under.

    Inspected rather than read, and inspected without following a link. The
    path is one the agent can create, so what sits there is not necessarily a
    file: a FIFO would block the tick on the open, a symlink to `/dev/zero`
    would return bytes until the process ran out of memory, and a large regular
    file would be read into it for nothing. A `stat` of the link itself answers
    the only question that matters -- is anything there, and does it have
    content -- without opening whatever is behind it.

    Fail-closed at every step, since the whole point of the check is to refuse:
    a git directory that cannot be located, an entry that is not a regular
    file, and one that cannot be stat-ed are all reported as blocking. Only an
    answer that the path holds an empty regular file, or nothing at all, lets a
    measurement proceed.
    """
    located = commands._git_hardened(
        "rev-parse", "--git-path", _INFO_ATTRIBUTES, cwd=worktree,
    )
    answered = (located.stdout or "").strip()
    if located.returncode != 0 or not answered:
        return f"an unlocatable {_INFO_ATTRIBUTES}"
    attributes_path = Path(answered)
    if not attributes_path.is_absolute():
        attributes_path = worktree / attributes_path
    try:
        planted = attributes_path.lstat()
    except FileNotFoundError:
        return ""
    except OSError as error:
        return f"an unreadable {attributes_path} ({error})"
    if not stat.S_ISREG(planted.st_mode):
        return f"a {attributes_path} that is not a regular file"
    return f"the attributes in {attributes_path}" if planted.st_size else ""


def _added_lines(numstat_stdout: str) -> int | None:
    """Total the added lines a numstat report names, or None if one is unread.

    None on the first record that cannot be accounted for, rather than a total
    over the rest of them: a partial count is a number that looks exactly like
    a whole one and would be adjudicated as though a reviewer had seen the
    paths it skipped.
    """
    total = 0
    for record in numstat_stdout.split(_NUL_SEPARATOR):
        if not record:
            continue
        added = _record_additions(record)
        if added is None:
            return None
        total += added
    return total


def _record_additions(record: str) -> int | None:
    """The lines one numstat record adds, 0 for binary, None if unreadable.

    Binary is a real answer and zero is the right count for it: the path is in
    the diff and nothing was ruled out, there are simply no lines in it to add.
    Anything else this owner cannot read -- a record with a count missing, a
    count that is not a whole number, a negative one, a record naming no path
    at all -- is not a count, and saying so is what keeps an unrecognized
    report from being totalled as nothing.

    Only the two counts are split off the front. A path is bytes, and a tab is
    one of the bytes it may contain -- under `-z` it arrives unquoted, so a
    record split on every tab would report four fields for a perfectly legal
    filename and refuse the whole count over a path that changed like any
    other.
    """
    fields = record.split(_FIELD_SEPARATOR, _COUNT_FIELDS)
    if len(fields) != _NUMSTAT_FIELDS or not fields[-1]:
        return None
    if fields[0] == _BINARY_COUNT:
        return 0
    if not fields[0].isascii() or not fields[0].isdigit():
        return None
    return int(fields[0])
