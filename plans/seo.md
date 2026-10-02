# SEO Plan — `chippingway/chipping-orchestrator`

Remaining work after checking this checkout, live GitHub metadata/releases, and PyPI on 2026-10-02.
Includes the contributor guide, simple issue forms, and repository-slug fixes already present in this checkout.
The MkDocs/Pages publishing setup builds and deploys `docs/`; verify deployment status in Actions.

Two distinct surfaces need separate work:

1. **GitHub internal search** — repo name, description, topics, README text, stars, activity recency.
2. **External search + AI answer engines** — Google/Bing indexing, backlinks, docs site, how models describe the
   project when asked for alternatives.

---

## Current state audit

| Item | Current value | Assessment |
|---|---|---|
| Repo references | `chippingway/chipping-orchestrator` in README, examples, and docs | Complete |
| Docs site | MkDocs/Pages publishing setup over `docs/` | Verify deployment in Actions |
| Website field | Operator-owned GitHub setting | Point to the docs URL after a successful deployment |
| Social preview | GitHub auto-generated | Weak share CTR |
| PyPI | not published | `pyproject.toml` already present |
| Stars / forks | 13 / 1 | Distribution is the binding constraint |

---

## Priority 1 — Highest leverage

### 1.1 Publish `docs/` as a real docs site

Google heavily deprioritizes `github.com/.../blob/...` URLs, so the entire existing documentation tree is currently
close to invisible to search.

MkDocs uses the existing `docs/` tree, the GitHub Pages workflow builds and deploys it, and the README links to the
site URL. Preview, build, and deployment setup instructions are in the
[operations guide](../docs/configuration/operations.md#publishing-the-documentation).

Deployment and the repository Website field depend on operator-owned GitHub settings. Check the workflow's latest
deployment and the public site to confirm their current status.

Remaining steps:

1. Confirm the
   [GitHub Pages setup](../docs/configuration/operations.md#github-pages-setup), and verify a successful deployment to
   `https://chippingway.github.io/chipping-orchestrator/`.
2. Set the resulting URL in the repo's **website** field.

Payoff: a dozen-plus indexable HTML pages able to rank on long-tail queries such as "claude code codex reviewer loop
configuration" or "github issue to PR state machine labels". Likely the single biggest external win given how much
documentation already exists.

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

On-page optimization has a low ceiling at 13 stars. GitHub's internal ranking is dominated by stars and recent activity;
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

1. README tagline, scope section, comparison section, and image alt text
2. Social preview image
3. Verify the docs deployment, then set the Website field
4. Code of conduct and PyPI publication
5. Distribution push, once the above is in place so arriving traffic lands well
