# Contributing to chipping-orchestrator

Bug reports, ideas, documentation fixes, tests, and pull requests are welcome. A short issue is enough to get started.

## Report a problem or suggest a change

Check existing issues and pull requests to see whether someone has already raised the same topic, then use the
[issue forms](https://github.com/chippingway/chipping-orchestrator/issues/new/choose).

For a bug, tell us what happened and what you expected. For a change, describe the problem and the improvement you want.
Steps to reproduce, examples, your version, or redacted logs are helpful if you have them. Share what you know;
maintainers can ask for more details and help clarify scope and success criteria.

Report suspected vulnerabilities privately through [SECURITY.md](SECURITY.md). Redact secrets and private details
from anything you share publicly.

Issues can start automated agent work. Maintainers manage workflow labels; for a question or design discussion,
say so clearly so they can choose the appropriate route. Leave the orchestrator's pinned state comment intact.
See the [README](README.md#how-it-works) for how issues become pull requests.

## Set up a development checkout

Use Linux, Git, Python 3.12 or newer, and `uv`. Fork the repository, then:

```sh
git clone https://github.com/YOUR-LOGIN/chipping-orchestrator.git
cd chipping-orchestrator
git switch -c my-change
uv sync --locked
```

Local lint and test checks work without GitHub credentials or coding-agent setup. For dashboard work, install the
optional dependencies with `uv sync --locked --group dashboard`.

Live orchestrator runs perform real GitHub operations. Use a dedicated test repository and follow the
[configuration](docs/configuration.md) and [security](docs/security.md) guides.
Do not access or change `analytics-db/data/`; it holds operator-owned runtime data.

## Make a focused change

Small fixes can go straight to a PR. Discuss larger features or new dependencies in an issue first, and coordinate
with anyone already working on the same issue.

Add or update tests for behavioral changes and update the affected documentation. Tests follow the package layout.
Preserve existing workflow labels, pinned-state fields, comment markers, watermarks, and event payloads. For workflow
or agent changes, consult the [state machine](docs/state-machine.md) and [workflow guide](docs/workflow.md).

The [development guide](.agents/skills/develop/SKILL.md) covers detailed conventions, license headers, and the full
pre-push checklist. The [documentation index](docs/README.md) helps you find the relevant reference pages.

## Check your changes

Before submitting a PR, run:

```sh
uv run ruff check orchestrator tests
uv run flake8 orchestrator tests --select=WPS
uv run python -m pytest tests
git diff --check
```

Fix failing checks. Report a baseline failure only after reproducing it on the unchanged base commit, and note
any relevant optional tests you skipped.

## Open a pull request

Target `main`. Briefly explain what changed and why, link any related issue, and say which checks you ran.
Use a single Conventional Commit subject, such as `fix: preserve paused issue state` or `docs: clarify retry controls`,
with no body or trailers. Keep issue references in the PR description.

Agent-assisted contributions follow the same checks; review and understand the code you submit. A human makes the
final merge decision. Contributions use the repository's [Apache-2.0 license](LICENSE).
