---
layout: post
title: "2.4.5 Dependency Pinning vs Version Ranges: The Reproducibility Tradeoff"
author: "Glenn Lum"
date:   2026-02-25 11:00:00 +0800
categories: journal
image: tier_2.jpg
tags: [Tier 2,Core Lifecycle Stages,Depth]
---

Most engineers frame this as a simple binary: pin your dependencies for safety, or use ranges for convenience. That framing is wrong, and it leads to policies that feel rigorous but quietly rot. The real question is not *whether* to pin or use ranges — it is understanding what your package manager actually does when it encounters either strategy, how version resolution compounds across a dependency graph, and why the cost of both approaches is invisible until it becomes an emergency. The mechanics underneath this decision are what determine whether your system is reproducible, updatable, or slowly becoming neither.

## What Version Resolution Actually Does

When you declare a dependency, you are not selecting a version. You are expressing a **constraint**. Your package manager collects constraints from every package in your dependency tree and feeds them into a **resolver** — an algorithm that finds a set of concrete versions satisfying all constraints simultaneously, or fails if no such set exists.

Consider a `package.json` with:

```json
{
  "dependencies": {
    "library-a": "^2.3.0",
    "library-b": "^1.1.0"
  }
}
```

This looks like two decisions, but it is the start of a constraint satisfaction problem. `library-a@2.5.1` might depend on `shared-util@^3.2.0`, while `library-b@1.4.0` might depend on `shared-util@^3.0.0`. The resolver must find a single version of `shared-util` that satisfies both ranges. If `library-a` updates to require `shared-util@^4.0.0` while `library-b` still requires `^3.0.0`, no solution exists. Your build breaks — not because of anything you changed, but because of an incompatibility between your transitive dependencies.

This is the first non-obvious mechanic: **your dependency policy governs your direct dependencies, but the resolver operates on the entire graph.** You control perhaps ten to thirty direct dependencies. The resolved tree might contain hundreds or thousands of packages. The constraints those transitive packages declare are outside your control, and the resolver must satisfy all of them simultaneously.

Different ecosystems handle resolution differently. npm installs a tree structure where multiple versions of the same package can coexist (library-a gets its `shared-util@4.1.0` and library-b gets its `shared-util@3.8.0`). pip, by contrast, installs into a flat namespace — only one version of any package can exist, so conflicts are hard failures. Go modules use **minimum version selection**, always choosing the lowest version that satisfies all constraints, which inverts the usual "give me the latest compatible version" behavior. These are not implementation details you can ignore. They determine what "using a range" actually means in your ecosystem.

## The Manifest vs. the Lock File

Two files govern your dependencies, and confusing their roles is the root of most reproducibility problems.

The **manifest** (`package.json`, `Pipfile`, `Cargo.toml`, `go.mod`) declares your intent: which packages you want and what version constraints you accept. The **lock file** (`package-lock.json`, `Pipfile.lock`, `Cargo.lock`, `go.sum`) records the output of resolution: the exact version of every package — direct and transitive — that the resolver selected.

When you run `npm install` on a project with no lock file, the resolver reads the manifest, solves the constraint problem against the current state of the registry, and writes both a `node_modules` directory and a lock file. When you run `npm install` with a lock file present, the resolver skips the solving step entirely and installs exactly what the lock file specifies — *unless* the manifest has changed in a way that invalidates the lock file.

This means that the lock file is the actual source of reproducibility, not the manifest. A manifest with `"lodash": "^4.17.0"` is compatible with hundreds of resolved versions. The lock file picks one. If your CI pipeline regenerates the lock file from scratch on every build instead of consuming the committed lock file, you have ranges with extra steps — not pinning.

Here is the subtlety that catches people: **the manifest governs what the resolver is allowed to choose, the lock file records what it chose, and the distinction between "pinning" and "ranges" lives in the manifest.** When someone says they "pin dependencies," they usually mean one of two things, and the difference matters enormously. They might mean they use exact versions in the manifest (`"lodash": "4.17.21"`), which constrains the resolver to a single choice for that direct dependency. Or they might mean they commit a lock file, which freezes the entire resolved tree regardless of what the manifest says. These are different strategies with different update behaviors.

## Direct Dependencies vs. Transitive Dependencies

Pinning your direct dependencies does not pin your transitive dependencies. If your manifest says `"express": "4.18.2"` (exact), you have locked the version of Express. But Express depends on dozens of packages, each with their own declared ranges. The first time you resolve — or any time you delete your lock file and re-resolve — the transitive tree beneath Express can change.

This is where the two strategies interact. If you pin direct dependencies in the manifest *and* commit the lock file, you get full reproducibility. If you pin direct dependencies in the manifest but do not commit the lock file (common in library development, where lock files are often gitignored), you have controlled only the surface. The packages three levels deep in your tree can still shift between builds.

Conversely, if you use ranges in the manifest but commit the lock file, you get reproducibility that is easy to update — running `npm update` or equivalent will re-resolve within the constraints and write a new lock file that you can review, test, and commit. This is the strategy most ecosystem maintainers recommend, and it is the one most teams think they are following. The gap between thinking you follow it and actually following it is where breakage lives.

## How Freshness Decays

A fully pinned, locked dependency tree is a snapshot. On day one, that snapshot is current — every package is at or near its latest version, all known vulnerabilities are patched. Over time, the snapshot ages. New vulnerabilities are discovered. New versions are released. Some of those new versions contain security fixes. Some contain breaking changes.

The cost of updating is roughly proportional to how far behind you are. Updating one package from `3.2.1` to `3.2.4` is almost always trivial. Updating from `3.2.1` to `3.9.0` might require adjusting to new behaviors. Updating from `3.2.1` to `5.0.0` might require rewriting integration code. And because dependencies constrain each other, updating one package deep in the tree can force cascading updates to packages that depend on it.

This creates the **update cliff** — the phenomenon where a team pins everything, ignores updates for months, then faces a security advisory that forces an update. The vulnerable package is three major versions behind. Updating it breaks compatibility with two other packages that also need to be updated. Those updates surface new deprecation warnings in your code. What should have been a patch-level bump becomes a multi-day project.

The update cliff is the primary failure mode of aggressive pinning, and it is invisible until you hit it. Nothing in your CI pipeline warns you that your dependency tree is gradually becoming unmaintainable. Everything is green. Builds are reproducible. And the cost of your next update is growing every day.

## The Failure Modes That Actually Happen

**Phantom breakage from ranges without lock files.** A team uses ranges in their manifest, does not commit the lock file, and runs `pip install -r requirements.txt` (with `>=` style ranges) in CI. Monday's build works. Tuesday's build fails. Nothing in the repository changed. A transitive dependency released a minor version that changed behavior in a way semantic versioning says should not happen — but did. The team spends hours bisecting their own code before realizing the problem is external. This is the most common argument for pinning, and it is valid.

**Vulnerability accumulation from pinning without update discipline.** A team pins every dependency and commits the lock file. Six months later, a CVE is published against a transitive dependency four levels deep. The fix requires updating the transitive dependency, which requires updating its parent, which requires updating a direct dependency across a major version boundary. The team patches the vulnerability manually (if they can), forks the dependency (if they are desperate), or accepts the risk (if they do not understand it).

**Lock file drift in monorepos and multi-service setups.** Service A and Service B share a library. Each has its own lock file. Service A updates the library; Service B does not. The shared library now behaves differently in each service. Integration tests pass in isolation. Production breaks at the boundary. The lock files are individually correct and collectively inconsistent.

**False reproducibility from misunderstanding lock file scope.** A team commits their lock file but runs `npm ci` on some pipelines and `npm install` on others. `npm ci` faithfully installs from the lock file. `npm install` may update it. The artifact built by the "install" pipeline subtly differs from the one tested by the "ci" pipeline. The build is reproducible in theory and non-deterministic in practice.

## The Policy Space Between the Extremes

The practical solution is neither "pin everything" nor "range everything." It is a combination: use ranges in the manifest for direct dependencies (typically caret or tilde ranges that allow patch and minor updates), commit the lock file for reproducibility, and run automated update tooling (Dependabot, Renovate, or equivalent) on a cadence that keeps the update delta small.

This combination gives you reproducible builds (from the lock file), controlled flexibility (from the ranges), and small update increments (from the automation). The lock file is the artifact of truth. The ranges define the search space for updates. The automation ensures the search space is explored regularly rather than in a panic.

The key nuance: this only works if your CI pipeline installs from the lock file in all paths, if the update PRs are actually reviewed and merged, and if your test suite is comprehensive enough to catch behavioral changes in dependencies. Automated update tooling that produces PRs nobody merges is the same as not having it.

## The Mental Model

Think of your dependency tree as a snapshot of the ecosystem at a point in time. The manifest is a set of constraints that defines a *region* of valid snapshots. The lock file is a specific point within that region. Pinning narrows the region; ranges widen it. But the region only matters at resolution time — the moment the resolver runs and selects a concrete point.

Reproducibility comes from controlling when and how that resolution happens. If you re-resolve on every build, you are at the mercy of the ecosystem's rate of change. If you never re-resolve, you are at the mercy of the ecosystem's vulnerability disclosure rate. The engineering task is not choosing one extreme but choosing the resolution cadence — how often you take a new snapshot, and how much of the tree you allow to change when you do.

The tradeoff is not pinning vs. ranges. It is **resolution frequency vs. update cost per resolution.** Resolve often and each update is small. Resolve rarely and each update is large. The right frequency depends on your risk tolerance, your test coverage, and your team's capacity to review dependency changes — not on a universal best practice.

## Key Takeaways

- Version resolution is a constraint satisfaction problem across your entire dependency graph, not a lookup against a flat list of packages you declared.
- The manifest expresses constraints; the lock file records the resolved result. Reproducibility comes from the lock file, not from pinning versions in the manifest.
- Pinning direct dependencies does not pin transitive dependencies — only a committed lock file freezes the full tree.
- The cost of updating a dependency is roughly proportional to how far behind you are, which means deferred updates compound into increasingly expensive and risky changes.
- Automated update tooling (Dependabot, Renovate) works only if the PRs it produces are actually merged on a regular cadence and validated by meaningful tests.
- Different ecosystems resolve differently: npm allows duplicate versions in a tree, pip requires a flat namespace, Go uses minimum version selection. Your pinning strategy must account for your resolver's behavior.
- The most common reproducibility failure is not choosing the wrong policy but applying the right policy inconsistently — mixing `install` and `ci` commands, regenerating lock files in some pipelines, or gitignoring lock files in applications.
- The real tradeoff is resolution frequency vs. update cost per resolution: resolve often and each change is small, resolve rarely and each change is a project.

[← Back to Home]({{ "/" | relative_url }})
