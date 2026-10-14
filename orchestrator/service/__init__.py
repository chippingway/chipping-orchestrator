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

Nothing here imports ``orchestrator.config``. That package resolves and
validates the settings as it is imported, and an installed package with no
``REPOS`` exits there -- which is exactly the state a first setup starts from.
The configuration reads ``checkouts`` and ``paths`` back instead, to hold its
targets to the same check and to choose the ``.env`` it loads, which those two
can serve from below it because they import nothing beyond each other. This
initializer binds nothing, so naming the package costs no owner beneath it.
"""
