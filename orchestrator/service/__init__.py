# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What an installed orchestrator carries for setting itself up.

``templates`` reads the two ``.env`` templates that ship beside it as package
data: ``.env.example``, the basic template a setup starts from, and
``.env.example.advanced``, the optional overrides and developer settings. Both
files live in this directory and nowhere else, so every install carries the
copies that match its own version, and a source checkout reads the same files
its documentation links to and its tests parse.

The rest is what a setup checks and derives before it writes anything.
``checkouts`` answers whether a directory is the top of a git checkout, as git
itself reads one, and ``paths`` where the running package sits -- its own
source checkout or an installed distribution -- where an installed one keeps
its ``.env`` and logs, and the refusal a setup command gives a source
checkout. ``validation`` holds one validator per setup field and the
``FieldError`` each refuses with; ``remote_urls`` reads which GitHub
repository a remote's URL names; ``clone_defaults`` derives a clone's
repository, remote, and base branch from its remotes; and ``repos_entry``
writes the ``REPOS`` entry those fields make.

Then the writing. ``dotenv_text`` sets a setting in a ``.env``'s text on the
line the configuration reads it from, and ``private_files`` writes a file
whole, mode 0600, into a directory made with mode 0700, as is each parent
missing above it. ``configure`` is the
command that writes an installed package's ``.env`` from the basic template
with all of the above, its core called in process with the answers as typed,
and ``commands`` puts it on the command line ``orchestrator/cli.py`` parses.

Nothing here imports ``orchestrator.config``. That package resolves and
validates the settings as it is imported, and an installed package with no
``REPOS`` exits there -- which is exactly the state a first setup starts from.
The configuration reads ``checkouts`` and ``paths`` back instead, to hold its
targets to the same check and to choose the ``.env`` it loads, which those two
can serve from below it because they import nothing beyond each other. This
initializer binds nothing, so naming the package costs no owner beneath it.
"""
