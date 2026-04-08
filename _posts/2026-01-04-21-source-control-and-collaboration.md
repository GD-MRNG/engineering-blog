---
layout: post
title: "2.1 Source Control and Collaboration"
author: "Glenn Lum"
date:   2026-01-04 11:00:00 +0800
categories: journal
image: tier_2.jpg
tags: [Tier 2, Core Lifecycle Stages, Concept]
---

`[Tier 2, Core Lifecycle Stages, Concept]` 

Source control is foundational enough that most developers take it for granted, but there is a significant gap between using Git to save your work and using Git as a precision tool for collaborative engineering. The core idea is simple: every change to every file in your system is recorded, attributed, and reversible. But the operational implications run much deeper.

The concept of a **branching strategy** describes how a team organizes parallel work. In **trunk-based development**, developers commit to a single shared branch (the trunk or main branch) continuously, using feature flags to hide incomplete work from users. This approach keeps integration costs low because conflicts are discovered immediately rather than accumulating over time. In **GitFlow**, developers work on long-lived feature branches that are merged back to a development branch and then to a release branch on a schedule. This gives teams more isolation but creates "integration hell" when branches diverge significantly. The choice between these strategies has direct consequences for your CI pipeline: trunk-based development requires your CI to be fast and reliable enough to run on every commit, while long-lived branches shift that cost to infrequent but painful merges.

**Code review and the pull request process** is not just a quality gate; it is the primary mechanism for knowledge distribution across a team. A code review ensures that at least one other person understands every change that enters the codebase. This matters operationally because it means that when something fails at 2am, the person being paged is not the only person who knows how that system works. Good code review culture treats the review as a collaborative conversation, not a performance evaluation, and is explicit about whether feedback is blocking or advisory.

**Commit hygiene** matters more than most developers think. An "atomic commit" is a commit that makes one coherent, complete change. It passes tests. It does not mix refactoring with feature additions. It has a clear message that describes *why* the change was made, not just *what* was changed. The reason this matters operationally is that your commit history is a debugging tool. When you need to identify which change introduced a regression (using `git bisect`, for example), a history of clean, atomic commits can turn a four-hour investigation into a fifteen-minute one. A history of "WIP", "fix", and "asdasd" commits provides no leverage at all.

**The monorepo versus polyrepo decision** is an architectural choice about your source control topology that has deep implications for team workflow, CI pipeline design, and dependency management. A monorepo places all services and shared libraries in a single repository. This makes cross-cutting changes (updating a shared library that dozens of services depend on) straightforward, ensures that every change is visible and reviewable in one place, and allows a single CI system to understand the dependency graph and only rebuild what actually changed. The challenge is that this requires sophisticated build tooling to avoid running every service's tests on every commit. A polyrepo gives each service its own repository, providing clean ownership boundaries and simpler per-service CI pipelines, but making coordinated changes across services operationally painful and making it harder to maintain consistency in tooling and standards across teams.

**The "Everything as Code" principle** extends source control beyond application code. Infrastructure definitions, CI pipeline configurations, database schema migrations, environment configuration, documentation, and even security policies should all live in version control. This turns the repository into a complete, auditable record of the entire system: not just what the code does, but how it is built, where it runs, how it is secured, and how it has changed over time.

[← Back to Home]({{ "/" | relative_url }})