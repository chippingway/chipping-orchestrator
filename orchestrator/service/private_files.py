# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Setup files only their owner reads, each written whole or not at all.

A setup keeps what it writes under the home directory, readable by the user
alone: a directory it creates is mode 0700 and a file it writes mode 0600,
each set exactly rather than left to the umask. A file is first written in
full to a temporary sibling, flushed to disk, and only then given its name, so
a reader -- the configuration loading the ``.env``, a poller reading a token
-- sees the previous file or the new one and never a part of either, and a
write that fails part way leaves nothing behind.

The name is given one of two ways. A write that may replace a file renames the
sibling over it. One that must not hard-links the sibling to the name, which
the kernel refuses when the name is taken: unlike a check made ahead of the
write, that refusal cannot miss a file that appears in between.

Nothing here imports from the package: the files are written on a host with
no configuration, by commands that run before any exists.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

_DIRECTORY_MODE = 0o700
_FILE_MODE = 0o600


def private_directory(directory: Path) -> None:
    """Create ``directory``, and each parent missing above it, with mode 0700.

    A missing parent -- ``~/.config`` on a fresh home -- gets the mode the XDG
    base directory specification asks for, set exactly like the rest: left to
    a umask that takes the owner's own write bit away, it would be a parent
    nothing can be created in. A directory already in place is kept as it is,
    since the files a setup writes into it are private whatever it allows.
    """
    missing = []
    for path in (directory, *directory.parents):
        if path.is_dir():
            break
        missing.append(path)
    for path in reversed(missing):
        path.mkdir(mode=_DIRECTORY_MODE, exist_ok=True)
        path.chmod(_DIRECTORY_MODE)


def write_private(path: Path, text: str, *, replace: bool) -> None:
    """Write ``text`` to ``path`` with mode 0600, whole or not at all.

    ``replace`` says whether a file already at ``path`` is replaced; without
    it the write raises ``FileExistsError`` and leaves that file untouched.
    The directory holding ``path`` has to exist already.
    """
    # The temporary name is removed on the way out whatever happened: after a
    # rename it is already gone, and after a link it is the second name.
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        newline="",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    ) as stream:
        os.fchmod(stream.fileno(), _FILE_MODE)
        stream.write(text)
        stream.flush()
        os.fsync(stream.fileno())
        if replace:
            os.replace(stream.name, path)
        else:
            os.link(stream.name, path)
