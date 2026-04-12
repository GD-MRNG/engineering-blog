---
layout: post
title: "2.1.6 Monorepo vs Polyrepo: Repository Structure as an Architectural Decision"
author: "Glenn Lum"
date:   2026-02-09 11:00:00 +0800
categories: journal
image: tier_2.jpg
tags: [Tier 2,Core Lifecycle Stages,Depth]
---

Most teams frame the monorepo-versus-polyrepo decision as a preference about organization — do you like one big repo or many small ones? That framing is dangerously shallow. The actual decision is about where your system pays its coordination costs. A monorepo centralizes coordination into build tooling and code ownership conventions. A polyrepo distributes coordination into versioning protocols and cross-repo orchestration. Neither eliminates the cost. They relocate it. And the place you put that cost determines what kinds of work become easy, what kinds become painful, and what kinds become nearly impossible without dedicated engineering investment. Understanding the mechanics of *where that cost lands* is what separates a deliberate architectural choice from a default that slowly constrains everything downstream.

## The Dependency Graph Is the Real Decision

The most important thing your repository structure determines is not who owns which directory. It is how your system models, versions, and enforces its **dependency graph** — the set of relationships between every service, library, and shared component in your codebase.

In a monorepo, dependencies between components are **source-level dependencies**. Service A imports Shared Library X directly from a path within the same repository. There is no version number involved. When you change Library X, every consumer of Library X sees that change at the same commit. The entire repository exists at a single point in time — HEAD — and all components are, by definition, compatible with each other at that point.

In a polyrepo, dependencies between components are **artifact-level dependencies**. Service A declares a dependency on Shared Library X at version `2.4.1` in a manifest file (`package.json`, `go.mod`, `pom.xml`, whatever). Library X is published as a versioned artifact to a registry. Service A pulls that artifact at build time. Service B might depend on Library X at version `2.3.0`. Service C might be on `2.5.0`. At any given moment, different services are running against different versions of shared code.

This single difference — source dependencies versus artifact dependencies — cascades into nearly every operational concern: how you make cross-cutting changes, how your CI pipelines are structured, how you reason about compatibility, and how you debug production issues that involve multiple services.

## How Cross-Cutting Changes Actually Propagate

Consider a concrete scenario: your team maintains a shared authentication library used by fifteen services. A security vulnerability requires changing the token validation logic. The fix is not backward-compatible.

**In a monorepo**, you open one pull request. That PR modifies the authentication library and updates all fifteen call sites. The CI system runs tests for the library and for every affected service. If any service breaks, you see it immediately in the same PR. The change either lands atomically — all services move to the new behavior in a single merge — or it does not land at all. The coordination cost is paid upfront, in the form of a larger PR that requires reviews from multiple team owners. But the cost is visible and bounded.

**In a polyrepo**, you first push the fix to the authentication library repository, bump its version to `3.0.0`, and publish a new artifact. Then you open fifteen separate pull requests across fifteen service repositories, each updating their dependency declaration from `2.x` to `3.0.0`. Each PR triggers its own CI pipeline. Some will pass immediately. Some will require code changes. Some will sit in review queues for days because the owning team has other priorities. During the rollout window, your fleet is running a mix of patched and unpatched services. The coordination cost is distributed across time and teams, and the most dangerous part is that no single dashboard or tool shows you the current state of the migration.

This is not an edge case. Cross-cutting changes — security patches, API contract updates, logging format changes, dependency upgrades — are routine in any system with shared code. Your repository structure determines whether these changes are atomic or eventual, and whether completeness is enforced by tooling or tracked by spreadsheets.

## Build System Mechanics: What the Monorepo Actually Demands

The Level 1 post noted that a monorepo requires "sophisticated build tooling." Here is what that means concretely and why it is non-trivial.

A naive CI configuration for a monorepo runs every test for every service on every commit. In a repository with fifteen services, this means your CI time is the sum of all service test suites. At even moderate scale — say, forty services — this becomes untenable. CI runs take an hour. Developers stop waiting for green builds. The feedback loop collapses.

The solution is **affected-target analysis**: the build system must understand the full dependency graph of the repository, determine which files changed in a given commit, trace which components depend on those files (directly or transitively), and run only the tests for those affected components. Tools like **Bazel**, **Nx**, **Turborepo**, and **Pants** exist specifically to solve this problem, each with different approaches.

Bazel, for example, requires you to declare every dependency explicitly in `BUILD` files. It constructs a directed acyclic graph of the entire repository's build targets. When you change a file, Bazel walks the graph to find every target that transitively depends on that file and rebuilds only those targets. It also provides **hermetic builds** — builds that are fully determined by their declared inputs — which enables aggressive **remote caching**. If the inputs to a build target have not changed, the cached output can be reused, even across different machines and developers.

This is powerful. It is also a significant ongoing engineering investment. Someone has to write and maintain the build definitions. Someone has to operate the remote cache infrastructure. Someone has to debug cache invalidation issues when they arise — and they will arise. Someone has to onboard every new developer into a build system that is likely more complex than anything they have used before.

**The polyrepo sidesteps this entirely.** Each repository has a self-contained build. CI is a simple pipeline: clone, install dependencies, build, test, deploy. There is no graph analysis because there is no graph to analyze — each repo only knows about its own code and its declared external dependencies. The simplicity is real and has genuine value, especially for smaller teams or organizations that do not have dedicated platform engineering capacity.

## Versioning: Living at HEAD vs. Managing a Version Matrix

In a monorepo, there is one version of truth: HEAD. Every component is tested against every other component at the same commit. **Compatibility is a property of the repository state**, not of individual component versions. You do not need to think about whether Service A works with Library X version `2.4.1` because both are always at the same commit.

This is sometimes called **trunk-based compatibility**, and it eliminates an entire class of problems — but it introduces a constraint. If you break Library X in a way that fails Service A's tests, your commit is blocked. You cannot land the library change independently and let Service A catch up later. This tight coupling is the point: it forces compatibility to be maintained continuously. But it also means that a change to a foundational library can be blocked by a flaky test in a service you have never heard of.

In a polyrepo, each service controls when it upgrades its dependencies. This is a real form of autonomy. A team can say, "We are in the middle of a critical launch; we will upgrade the auth library next sprint." That flexibility is valuable. But it creates a **version matrix**: fifteen services, each potentially on a different version of the same library. Multiply this by every shared dependency and you get combinatorial complexity that no human tracks manually.

The worst manifestation of this is the **diamond dependency problem**. Service A depends on Library X at `2.0` and Library Y at `1.0`. Library Y also depends on Library X, but at `3.0`. Now Service A has two incompatible versions of Library X in its dependency tree. Some language ecosystems handle this gracefully (Go's module system, for example, allows major version coexistence). Others do not (Python, notoriously). In a monorepo, diamond dependencies cannot exist because there is only one version of everything.

## Access Control and Ownership Boundaries

In a polyrepo, access control is structural. Each repository has its own permissions. Team A has write access to `service-a-repo`. Team B has write access to `service-b-repo`. Neither can accidentally — or intentionally — modify the other's code without being granted access. The boundary is enforced by the hosting platform (GitHub, GitLab, etc.) at the repository level.

In a monorepo, everyone with repository access can technically modify any file. Ownership boundaries are enforced by convention and tooling rather than by platform-level permissions. **CODEOWNERS files** (on GitHub) or equivalent mechanisms define which team must approve changes to which paths. A change to `/services/payments/` requires review from the payments team, even if the PR was opened by someone on the search team. Path-based ownership works, but it is a policy layer on top of a permissive access model, not a hard boundary. It requires discipline to maintain and can be circumvented by administrators.

For organizations in regulated industries — finance, healthcare, defense — this distinction matters operationally. Auditors asking "who can modify the billing service?" want a simpler answer than "anyone with repo access, but we have a CODEOWNERS file that requires approval from the billing team." Some organizations solve this with **path-level permissions** offered by platforms like Bitbucket or GitLab's Protected Paths, but these features vary in maturity and granularity across providers.

## CI/CD Pipeline Topology

The repository structure determines the shape of your CI/CD system.

A polyrepo CI topology is **one pipeline per repository**. Each pipeline is self-contained: it knows how to build, test, and deploy its service. Pipeline definitions live in the repository they serve. This is simple to reason about, simple to debug, and gives each team full control over their deployment cadence. The cost appears when you need to coordinate: deploying a change that spans three services means triggering three pipelines in the right order, sometimes with sequencing constraints ("deploy the database migration before the API, deploy the API before the frontend").

A monorepo CI topology is **one pipeline that fans out**. A single commit triggers the pipeline, which runs affected-target analysis to determine which services changed, then builds and tests only those services, then deploys only the affected artifacts. This requires the CI system to understand the repository's internal structure — which paths map to which services, what the dependency graph looks like, and how to parallelize test execution across potentially dozens of services. Tools like Bazel integrate with CI systems to enable this, but the integration is custom engineering work, not a checkbox.

The monorepo pipeline also introduces a subtle operational risk: **trunk contention**. When many teams are committing to the same repository, the main branch moves fast. If your CI run takes ten minutes and three other PRs merge during that window, your PR may need to be rebased and re-tested before it can merge. At high commit volumes, this creates a merge queue bottleneck that requires dedicated tooling (GitHub's merge queue, Bors, Mergify) to manage efficiently.

## Tradeoffs and Failure Modes

**The most common monorepo failure** is adopting the structure without investing in the tooling. A team puts everything in one repository, uses a standard CI provider with a naive "run all tests" configuration, and within six months, CI takes forty-five minutes per commit. Developer productivity craters. The response is often to carve services back out into separate repos — a painful migration that could have been avoided by understanding upfront that the monorepo's value proposition is inseparable from its tooling requirements.

**The most common polyrepo failure** is underestimating the coordination tax. Everything feels clean and fast when services are independent. The pain emerges gradually: shared libraries drift across versions, cross-service changes take weeks instead of hours, and tooling standardization erodes because there is no single place to enforce it. Teams end up building internal tools for "bulk PRs" and "dependency update bots" that are, in effect, poorly reimplementing the coordination a monorepo provides natively.

**The hybrid trap** deserves mention. Some organizations adopt a middle ground: a monorepo for shared libraries with polyrepos for services, or a few "domain monorepos" that group related services. These can work, but they combine the costs of both models. You need build tooling for the monorepo portions and cross-repo coordination for the polyrepo portions. Hybrids are not inherently wrong, but they should be chosen deliberately, not arrived at by drift.

## The Mental Model

Repository structure is a decision about where coordination costs live. A monorepo makes coordination automatic but requires you to invest in tooling that can manage a large, interconnected codebase efficiently. A polyrepo makes independence the default but requires you to invest in process and tooling to coordinate across boundaries when — not if — cross-cutting work is needed.

The key variable is not team size or codebase size in isolation. It is the **ratio of cross-cutting work to independent work**. If your services are genuinely independent — different teams, different deployment cadences, minimal shared code — the polyrepo's coordination tax is low and its simplicity is a real advantage. If your services share significant infrastructure, libraries, or API contracts that change together, the monorepo's atomic cross-cutting changes and enforced compatibility save more time than its tooling costs.

Do not choose based on what Google or Facebook does. Choose based on where your system's coordination costs actually are, and whether you have the engineering capacity to invest in the tooling that your chosen model demands.

## Key Takeaways

- The monorepo-versus-polyrepo decision is fundamentally about whether dependencies between components are managed as source-level references (monorepo) or versioned artifacts (polyrepo), and this distinction drives nearly every downstream operational difference.

- Monorepos enforce compatibility at HEAD: every component must work with every other component at every commit, which eliminates version matrix complexity but requires that broken compatibility be fixed before changes can land.

- Polyrepos give teams version-pinning autonomy — the ability to upgrade shared dependencies on their own schedule — but this creates a version matrix that introduces diamond dependency risks and makes fleet-wide migration tracking an ongoing operational burden.

- A monorepo without affected-target analysis and remote caching in CI is not a monorepo strategy; it is a slow CI problem waiting to happen. The tooling investment is not optional.

- Cross-cutting changes — security patches, shared API updates, logging standards — are atomic in a monorepo and eventual in a polyrepo. The frequency of these changes in your system should heavily influence your choice.

- Access control in a monorepo is policy-based (CODEOWNERS, path protections) rather than structural (repository-level permissions), which may not satisfy compliance requirements in regulated environments without additional platform-level controls.

- Polyrepo CI is simple per-repo but requires orchestration for multi-service changes; monorepo CI requires graph-aware build systems but provides a single pipeline that understands cross-service impact.

- The correct choice depends on the ratio of cross-cutting work to independent work in your system and on whether your organization has the platform engineering capacity to support the tooling that each model demands.

[← Back to Home]({{ "/" | relative_url }})
