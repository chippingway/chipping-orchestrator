# Remaining Poetry operator cutover

Working notes for the operator cutover after the repository migration. The current tooling and
operator cutover procedure are documented under
[dependency tooling](../docs/configuration/operations.md#dependency-tooling) and
[Poetry migration for operators](../docs/configuration/operations.md#poetry-migration-for-operators).
These notes do not authorize changes to running services. The remaining findings below are from the 2026-10-06 audit.

- Convert the hourly analytics sync (`05 * * * *`, `orchestrator.observability.analytics.sync.cli`) and nightly
  trajectory pruning (`0 4 * * *`) cron entries from `uv run` to
  `env -u VIRTUAL_ENV -u CONDA_PREFIX poetry run` or the checkout's absolute `.venv/bin/python` path.
- Recreate the production `.venv/` from the committed `poetry.lock` using the documented cutover procedure, selecting
  any required optional groups. The audit found 16 installed versions differing from the lock, including psycopg
  3.3.6 versus the locked 3.3.4 and packaging 26.3 versus the locked 26.2.
- Restart `orchestrator.service` and its `run.sh` wrapper through the documented procedure so the wrapper loads
  Poetry dependency refreshes. The audited wrapper started before the updated `run.sh` was installed, and
  `.venv/.poetry-dependencies` was absent.
- Verify services and scheduled jobs use Poetry or their checkout's `.venv/bin/python`, installed versions agree
  with the committed lock, required optional groups are present in each deployment, and a successful wrapper refresh
  records `.venv/.poetry-dependencies`.

Remove this working note once the operator cutover is complete and verified.
