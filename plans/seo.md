# SEO Plan — `chippingway/chipping-orchestrator`

Planned work to improve GitHub discovery, search visibility, and project distribution.

## Priority 1 — Documentation discoverability

### 1.1 Finish site verification and indexing

Verify `https://chippingway.github.io/chipping-orchestrator/` in Google Search Console and Bing Webmaster Tools,
and submit its `sitemap.xml`.

### 1.2 Describe the focused pages

Add distinct `description` front matter to the 18 focused pages under the area directories and to
`docs/release-timeline.md`, following the page-description convention in `docs/configuration/operations.md`.
Add each described page to the list `tests/repository/test_docs_output.py` holds to its description.

---

## Priority 2 — README structure

Help readers choose an orchestrator by explaining how its workflow differs from these tools. Compare against:

- GitHub Copilot coding agent
- OpenHands
- Aider
- Devin

Axes worth using: self-hosted vs. hosted, where state lives, whether a separate reviewer pass exists, multi-repo
support, cost visibility.

---

## Priority 3 — Smaller on-page items

- **Social preview image.** Create and upload a 1280×640 PNG in Settings → General → Social preview.
- **Publish to PyPI.** Add relevant `keywords` to `pyproject.toml` and finish the remaining
  [PyPI release preparation](pypi-release.md).
- **Code of conduct.** Add `.github/CODE_OF_CONDUCT.md`.

---

## Priority 4 — Distribution

Complete Priorities 1–3 before starting distribution, so arriving visitors find a clear introduction, useful docs,
and a complete package page.

Check for existing posts and submissions before publishing to each target, and skip targets already covered.

Targets:

- **Show HN** — lead with the state-machine design and the `MAX_ADDED_LINES` adjudication mechanism.
- **Reddit** — r/ClaudeAI, r/LocalLLaMA, r/ExperiencedDevs.
- **Awesome lists** — `awesome-ai-agents`, `awesome-claude-code`, `awesome-codex`, `awesome-devops`. Submit PRs.
- **Vendor community showcases** — Anthropic and OpenAI developer community forums.
- **Written post** — dev.to or Habr, explaining the state machine and the split-decomposition path. Link to the
  docs site.
- **Product Hunt** — submit the project.

---

## Keyword consistency

Pick 2–3 primary phrases and align README copy and relevant docs page titles with the repository description and topics.
Candidates:

1. AI coding agent orchestrator
2. GitHub issue to PR automation
3. Claude Code / Codex CLI / Antigravity CLI automation
