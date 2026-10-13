# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Application entrypoints.

The destination for the targets an operator starts something with, as opposed
to the domain owners those targets compose. An app names owners; no owner names
an app, which is the direction the observability tree's own layering check
enforces from the other side. Both Streamlit pages have their target here; the
polling loop is the ``run`` command composed at ``orchestrator/cli.py``, which
the console script and the ``python -m orchestrator`` form both call.

``bootstrap`` is what every app here shares: the repo-root ``sys.path`` shim a
launcher that executes a file as a top-level script needs, since such a launch
puts only the file's own directory on the path and the absolute
``orchestrator.*`` imports beneath it would not resolve.

``analytics_dashboard`` is the Postgres-backed analytics page's ``streamlit
run`` target, and ``trajectory_dashboard`` the file-backed trajectory viewer's.
Each composes its owners inside the pass that reaches them rather than at
module scope, alongside the optional dependency group itself: the shim has to
run before an ``orchestrator.*`` name is resolved at all under a script launch,
so deferring the composition is what keeps the two orderings the same one.
Importing either module therefore costs the shim and nothing else, which is
what lets a caller reach one in an install carrying no page dependencies.

Callers name the app they start, so this initializer binds nothing.
"""
