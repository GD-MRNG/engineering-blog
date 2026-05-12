# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
bundle exec jekyll serve    # local dev server (http://localhost:4000)
bundle exec jekyll build    # build static site to _site/
```

No test suite. Linting is manual review of Markdown and front matter.

## What this project is

A Jekyll blog (Lagrange theme v4.0.0) that serves as a structured software engineering curriculum — "From Coder to Engineer." Content is organized as a three-tier knowledge framework covering DevOps and platform engineering concepts.

## Content architecture

**Three tiers**, each with two levels of posts:

| Tier | Topic | Image |
|------|-------|-------|
| Tier 1 | Foundation Knowledge (networking, compute, service arch) | `tier_1.jpg` |
| Tier 2 | Core Lifecycle Stages (source control, CI/CD, IaC, etc.) | `tier_2.jpg` |
| Tier 3 | Cross-Cutting Disciplines (observability, security, reliability, FinOps, emerging tech) | `tier_3.jpg` |

**Two post levels per topic:**
- `CONCEPT` (L1) — overview post, numbered X.Y (e.g., `1.1 Networking Fundamentals`)
- `DEPTH` (L2) — deep-dive posts, numbered X.Y.Z (e.g., `1.1.1 The OSI Model`)

## Post filename convention

```
YYYY-MM-DD-{number}-{slug}.md
```

The `{number}` mirrors the content numbering (no dots): `11`, `111`, `21`, `211`, etc. Dates are sequential and control display order — not the actual publish date.

## Post front matter

```yaml
layout: post
title: "X.Y.Z Title Here"
author: "Glenn Lum"
date:   YYYY-MM-DD 11:00:00 +0800
categories: journal
image: tier_1.jpg          # tier_1.jpg | tier_2.jpg | tier_3.jpg
tags: [Tier 1, Foundation Knowledge, Depth]
```

Tag options:
- Tier: `Tier 1` / `Tier 2` / `Tier 3`
- Section: `Foundation Knowledge` / `Core Lifecycle Stages` / `Cross-Cutting Disciplines`
- Level: `Concept` (L1 overview) / `Depth` (L2 deep dive)

## Adding new content

When adding a new post, also update the corresponding archive page in `menu/`:
- `menu/t1_archive.md` — Tier 1 index with `CONCEPT` / `DEPTH` links
- `menu/t2_archive.md` — Tier 2 index
- `menu/t3_archive.md` — Tier 3 index

Archive pages use Jekyll relative URL links: `{{ "/slug-here" | relative_url }}`

## Key config files

- `_config.yml` — Jekyll build settings, plugins, permalink style (`:title`)
- `_data/settings.yml` — menu items, social links, Disqus, Google Analytics, pagination labels
- `menu/start.md` — landing page ("From Coder to Engineer"); site root redirects here via `index.html`
- `index.html` — meta-refresh + JS redirect to `/start`; not a content page

## L1 vs L2 post structure

L1 (Concept) posts are concise overviews — no `## Key Takeaways` section, end with `[← Back to Home]({{ "/" | relative_url }})`.

L2 (Depth) posts are long-form with `##` section headers, include a `## Key Takeaways` section with bullet points at the end, and also close with `[← Back to Home]({{ "/" | relative_url }})`.
