# Remaining work before the first PyPI release

Working notes for unfinished release preparation. The recurring tag, build, validation, upload, retry, and
constraints-asset procedure lives in the [maintainer release guide](../CONTRIBUTING.md#notes-for-maintainers).

## Installation and upgrade documentation

- Add a concise PyPI installation entry to `README.md`, linking to the operator instructions.
- Add installation, upgrade, and rollback commands to `docs/configuration/operations.md` for both supported routes:
  `pipx install chipping-orchestrator==X.Y.Z`, and a dedicated `python -m venv` managed with `python -m pip`.
  Show how each route applies the release's `constraints.txt`. Use environment-specific installers, never bare `pip`.
- Explain how an installed user obtains the basic and advanced `.env` templates for their chosen signed release tag
  without cloning the repository. Use the installed configuration location and required settings already documented
  in [configuration](../docs/configuration.md#basic-setup); do not introduce a separate launch-directory convention.
- Document stopping the process, backing up operator settings, installing a chosen version, checking compatibility,
  and restarting. Keep upgrades operator-initiated and preserve configuration, credentials, targets, worktrees, and
  logs. Include separate commands for returning to the previous version through pipx and through the dedicated venv.
- Explain configuration drift: where release notes and version-matched templates identify added, renamed, or removed
  settings, changed defaults, and stricter validation; how to compare them while retaining local overrides; and how
  startup diagnostics guide repairs before polling resumes. Cover configuration changes that also affect rollback.
- Link the operator release instructions to `CONTRIBUTING.md#notes-for-maintainers` and keep the
  [configuration overview](../docs/configuration.md) consistent with those instructions.

## Remaining validation and policy

- Cover configuration reuse and diagnostics across a manual package upgrade and rollback. Reuse the existing
  installed-layout and startup-refusal coverage rather than repeating its scenarios.
- Validate the installation and upgrade instructions in isolated pipx and venv environments, including constrained
  installs and saved settings from a previous version. Exercise configured startup outside a source checkout;
  the release guide's `--help` checks alone do not exercise configuration loading.
- Document local publishing credentials and protected release tags in [security](../docs/security.md), preserving
  the existing GitHub Pages deployment policy.

## First publication

- Complete the release machine and PyPI account setup in the maintainer guide, including Poetry **2.5.1**, the
  separately installed export plugin and Twine, and real Python 3.12, 3.13, and 3.14 interpreters.
- Choose the first release version, or a real prerelease if claiming the name before the stable release. Follow the
  maintainer guide from the signed tag through artifact checks, local upload, SHA-256 comparison, installation checks,
  and attaching `constraints.txt` to the GitHub release. Record the publication in the
  [release timeline](../docs/release-timeline.md).
- After the first upload, confirm `geserdugarov` owns the project, replace the temporary account-scoped API token with
  a project-scoped token, and revoke the temporary token. Keep credentials outside the repository.

A PyPI organization and transfer into it remain optional follow-up work. This plan does not select a version,
perform an upload, or authorize live changes to an operator's deployment.
