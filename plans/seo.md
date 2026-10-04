# SEO Plan — `chippingway/chipping-orchestrator`

Remaining work after checking this checkout, the live documentation site, live GitHub metadata/releases, and PyPI on
2026-10-04. Includes the contributor guide, simple issue forms, and repository-slug fixes already present in this
checkout.

Two distinct surfaces need separate work:

1. **GitHub internal search** — repo name, description, topics, README text, stars, activity recency.
2. **External search + AI answer engines** — Google/Bing indexing, backlinks, docs site, how models describe the
   project when asked for alternatives.

---

## Current state audit

| Item | Current value | Assessment |
|---|---|---|
| Repo references | `chippingway/chipping-orchestrator` in README, examples, and docs | Complete |
| Docs site | Published at `https://chippingway.github.io/chipping-orchestrator/`, deployed from `main` | Complete |
| Page descriptions | Homepage and the six reference-area landing pages; focused pages have none | Partial |
| Docs build check | Runs on every PR, required on `main`; no blocked merge observed yet | Confirm with a failing PR |
| Website field | Empty | Point to the docs URL |
| Social preview | GitHub auto-generated | Weak share CTR |
| PyPI | not published | `pyproject.toml` already present |
| Code of conduct | none | Community profile at 62% |
| Stars / forks | 14 / 1 | Distribution is the binding constraint |

---

## Priority 1 — Highest leverage

### 1.1 Publish `docs/` as a real docs site

Google heavily deprioritizes `github.com/.../blob/...` URLs, so the documentation tree was close to invisible to
search until it was published as HTML.

Done:

- MkDocs builds the existing `docs/` tree, and the README links to the site. The **Documentation** workflow deploys
  every qualifying push to `main` through the `github-pages` environment; the current `main` deployment succeeded, and
  the site serves its pages, sitemap, and search index.
- Every pull request builds the site strictly once, and that one build is checked for links, anchors, search, sitemap,
  and descriptions before `main` uploads it. Source links stay checked in the CI matrix.
- The `main` ruleset requires that `build` check beside `ci (3.12)`, `ci (3.13)`, `ci (3.14)`, and
  `dependency-review`, as the [required-checks list](../docs/security.md#required-checks) asks.
- The homepage and the six reference-area landing pages each emit their own `<meta name="description">`, written as
  `description` front matter and covered by the site tests. The homepage introduction reads on both GitHub and the
  site. Conventions are in the
  [operations guide](../docs/configuration/operations.md#publishing-the-documentation).

Remaining steps:

1. Confirm that a failing documentation build blocks merging: open a throwaway PR that breaks the strict build, for
   example with a link to a missing page under `docs/`, check that `build` fails and GitHub refuses the merge, close
   the PR, and record it here.
2. Set `https://chippingway.github.io/chipping-orchestrator/` in the repo's **website** field.
3. Verify the site in Google Search Console and Bing Webmaster Tools, and submit its `sitemap.xml`.

### 1.2 Describe the focused pages

The 18 focused pages under the area directories, and the release timeline, emit no description, so search results
fall back to whatever text the engine extracts. Add distinct `description` front matter to each, following the
[page descriptions](../docs/configuration/operations.md#page-descriptions) convention, and add each described page to
the list `tests/repository/test_docs_output.py` holds to its description.

---

## Priority 2 — README structure

Crawlers and AI answer engines read the top of the README first. The introduction already explains the issue-to-PR
workflow, but there is no concise tagline or explicit scope/comparison section.

### 2.1 Add a tagline under the H1

```markdown
# chipping-orchestrator

**Autonomous GitHub issue → PR pipeline for Claude Code and Codex CLI.**
```

### 2.2 Add a "when to use / when not to use" section

Explicit scope framing is what gets a project correctly cited rather than vaguely mentioned.

Sketch:

- **Use it when:** you have a `codex` or `claude` login, run solo or on a small team, want issue-to-PR autonomy without
  a separate planner, queue, or database, and want to merge by hand.
- **Don't use it when:** you need a hosted service, want auto-merge, cannot give an agent a host as the sandbox
  boundary, or need non-GitHub issue trackers.

### 2.3 Add a comparison section

Comparative sections are disproportionately cited when someone asks a model "what are the options for autonomous
issue-to-PR automation". Compare against:

- GitHub Copilot coding agent
- OpenHands
- Aider
- Devin

Axes worth using: self-hosted vs. hosted, where state lives, whether a separate reviewer pass exists, multi-repo
support, cost visibility.

### 2.4 Improve image alt text

`![Analytics page]` → something describing what it shows, e.g. per-tick agent run, verification, and PR outcome
analytics with cost breakdown.

---

## Priority 3 — Smaller on-page items

- **Social preview image.** Settings → General → Social preview, 1280×640 PNG. Affects click-through when links are
  shared, which drives the backlinks that actually move rankings.
- **Publish to PyPI.** `pyproject.toml` is already in place. The PyPI page ranks independently and backlinks to
  the repo.
- **Code of conduct.** Add `.github/CODE_OF_CONDUCT.md` to finish the remaining community health item.

---

## Priority 4 — Distribution (the real constraint)

On-page optimization has a low ceiling at 14 stars. GitHub's internal ranking is dominated by stars and recent activity;
Google needs backlinks. One link from a high-authority domain outweighs every topic tag combined.

Completion of the distribution targets below was not verified; confirm existing posts/submissions before repeating them.

Targets:

- **Show HN** — lead with the state-machine design and the `MAX_ADDED_LINES` adjudication mechanism, which are the
  genuinely unusual parts.
- **Reddit** — r/ClaudeAI, r/LocalLLaMA, r/ExperiencedDevs.
- **Awesome lists** — `awesome-ai-agents`, `awesome-claude-code`, `awesome-codex`, `awesome-devops`. Submit PRs.
- **Vendor community showcases** — Anthropic and OpenAI developer community forums.
- **Written post** — dev.to or Habr, explaining the state machine and the split-decomposition path. Link back to the
  docs site, not just the repo.
- **Product Hunt** — lower value for developer infrastructure, but a free backlink.

---

## Keyword consistency

Pick 2–3 primary phrases and use them verbatim across repo name, description, topics, README H1, and docs page titles.
Candidates:

1. AI coding agent orchestrator
2. GitHub issue to PR automation
3. Claude Code / Codex CLI automation

Consistency across surfaces matters more than any individual placement.

---

## Suggested sequence

1. Confirm a failing documentation build blocks merging, and set the Website field
2. Submit the sitemap to Search Console and Bing, and describe the focused docs pages
3. README tagline, scope section, comparison section, and image alt text
4. Social preview image
5. Code of conduct and PyPI publication
6. Distribution push, once the above is in place so arriving traffic lands well
