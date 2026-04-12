---
layout: post
title: "2.4.2 Semantic Versioning: What a Version Number Communicates"
author: "Glenn Lum"
date:   2026-02-22 11:00:00 +0800
categories: journal
image: tier_2.jpg
tags: [Tier 2,Core Lifecycle Stages,Depth]
---

Most engineers treat a version number like a label — a name tag that goes up by one when you ship something new. That mental model is fine until your build breaks at 2 AM because a transitive dependency four levels deep released a "patch" that changed a return type. The problem is not that semver failed. The problem is that the version number was never just a label. It is an input to an algorithm — one that your package manager runs to decide, without asking you, which exact code ends up in your build. Understanding semver means understanding that algorithm and the contract it depends on.

## What the Spec Actually Defines

The semver specification (semver.org) is short and worth reading in full, but its most important contribution is a concept most people skip past: the **public API**. Semver only has meaning relative to a declared public API surface. The MAJOR version increments when you make incompatible changes to that API. The MINOR version increments when you add functionality that is backward-compatible. The PATCH version increments when you make backward-compatible bug fixes. Without a defined API boundary, these categories are meaningless.

This matters in practice because "breaking change" is not self-evident. If a library changes the order of keys in a JSON response that was never part of its documented interface, is that breaking? According to semver, no. According to the three services that parsed that JSON positionally, absolutely. The spec puts the burden on the library author to define what the public API is and to classify changes against that boundary. This is a human judgment call, and it is where most semver problems originate.

### The 0.x Escape Hatch

The spec has a provision that is widely used and poorly understood: any version with a major version of **0** (e.g., `0.3.7`) signals that the public API is not stable. Under `0.x.y`, anything can change at any time. There are no backward-compatibility promises. The minor and patch numbers in a `0.x` version carry no semver guarantees whatsoever.

This matters because a staggering number of packages in every ecosystem live at `0.x` permanently. In npm, PyPI, and crates.io, many widely-used, production-critical libraries have never released a `1.0`. When you take a dependency on a `0.x` library, you are opting into a regime where the author has explicitly declined to make stability commitments. Package managers know this and treat `0.x` ranges differently — a point we will return to.

### Pre-release Versions and Build Metadata

The spec defines two additional segments. A **pre-release** version is denoted by a hyphen after the patch number: `2.0.0-alpha.1`, `3.1.0-rc.2`. Pre-release versions have lower precedence than the associated release — `2.0.0-alpha.1` sorts before `2.0.0`. This is how library authors publish candidate versions for testing without having them automatically pulled into consumer builds.

**Build metadata** is appended with a `+` sign: `1.0.0+build.42`. The spec is explicit that build metadata must be ignored when determining version precedence. Two versions that differ only in build metadata are equal. This segment exists purely for informational tracing; it plays no role in resolution.

## How Package Managers Resolve Versions

The version number is half the story. The other half is the **range specifier** — the syntax a consumer uses to express which versions they are willing to accept. This is where the human contract becomes a machine instruction.

### Range Specifiers Are Semver Assertions

When you write a dependency declaration, you are making an assertion about your own compatibility. Consider these npm-style specifiers:

```json
"lodash": "^4.17.0"
```

The `^` (caret) operator means: accept any version that is compatible according to semver, starting from this floor. For a version `>=1.0.0`, this means the major version is locked and the minor and patch can float. So `^4.17.0` resolves to `>=4.17.0 <5.0.0`. The caret is encoding a belief: "I depend on the public API of lodash 4, and any non-breaking release within major version 4 should work for me."

The `~` (tilde) operator is more conservative: it locks the minor version and lets only the patch float. `~4.17.0` resolves to `>=4.17.0 <4.18.0`. This encodes a narrower belief: "I trust bug fixes, but new features might affect me."

Here is the critical subtlety with `0.x` versions: `^0.2.3` does **not** resolve to `>=0.2.3 <1.0.0`. Because the spec treats `0.x` as unstable, most package managers treat the caret on a `0.x` version as pinning to the minor version: `^0.2.3` resolves to `>=0.2.3 <0.3.0`. The reasoning is that in the `0.x` regime, even minor bumps can be breaking. Different package managers handle this slightly differently — Cargo, npm, and Poetry all implement this contraction, but the exact boundary varies for `0.0.x` versions. If you depend on `0.x` libraries and do not understand this behavior, your range specifiers are not doing what you think.

### The Resolution Algorithm

When you run `npm install` or `pip install` or `cargo build`, the resolver must find a set of concrete versions — one per package — that satisfies every range constraint in your entire dependency tree simultaneously. This includes your direct dependencies and every transitive dependency they pull in.

The process works roughly as follows. The resolver starts with your declared dependencies and their range constraints. For each dependency, it queries the registry for all published versions that fall within the specified range. It picks a candidate (usually the highest matching version, though strategies vary). Then it examines that candidate's own declared dependencies, adds their constraints to the problem, and recurses. If at any point a constraint conflicts with an already-selected version, the resolver backtracks and tries a different candidate.

This is, in the general case, an NP-complete problem — it is equivalent to Boolean satisfiability (SAT). Modern resolvers use heuristics and caching to make it fast in practice, but the fundamental complexity means that resolution can fail in non-obvious ways, and small changes in the dependency graph can produce unexpectedly large changes in the resolved output.

### The Diamond Dependency Problem

The most common resolution pain point is the **diamond dependency**. Suppose your application depends on libraries A and B. Both A and B depend on library C, but A requires `^1.3.0` and B requires `^1.5.0`. The resolver can satisfy both: it picks C at `1.5.x` or higher (within `<2.0.0`), which falls within both ranges.

Now suppose B updates its constraint to `^2.0.0`. A still requires `^1.3.0`. The resolver cannot pick a single version of C that satisfies both constraints. In ecosystems that allow only one version of a package (Python, Go), this is a hard failure — the build does not resolve. In ecosystems that allow multiple versions of the same package (npm for Node.js), the resolver can install both C@1.x and C@2.x in different subtrees of `node_modules`. This "solves" the resolution problem but introduces a new one: if A and B pass objects from C to each other, those objects come from different versions of C and may be incompatible at runtime, producing errors that no type checker or linter will catch.

## Where Semver Breaks Down

### The Contract Is Social, Not Technical

Nothing in the publishing pipeline of any major registry verifies that a version bump correctly classifies the nature of the change. An author can ship a breaking change as a patch. They usually do not do this maliciously — they do it because determining whether a change is breaking requires understanding every way consumers use the public API, which is impossible at scale.

**Hyrum's Law** captures this precisely: with a sufficient number of users, every observable behavior of your system will be depended upon by somebody. You change the order of items in an unordered collection — technically not a public API change — and someone's test suite, or worse, their production system, breaks. Semver gives authors a framework for communicating intent, but it cannot guarantee impact.

### Wide Ranges Trade Stability for Freshness

The caret operator is the default in most ecosystems because it maximizes the chance that security patches and bug fixes flow into builds automatically. The cost is non-determinism across time: running `npm install` today and next Tuesday may produce different `node_modules` trees. Lock files exist specifically to counteract this — they freeze the resolved output. But lock files only help when they are used correctly. Libraries (as opposed to applications) typically do not publish their lock files, meaning the resolution for a library's own dependencies happens fresh at install time in the consumer's context.

This creates a category of bug that is notoriously hard to reproduce: your CI passes because the lock file is committed, but a fresh install on a new machine pulls a slightly different transitive dependency and fails. Or worse, it succeeds but behaves differently.

### Major Version Increments Create Ecosystem-Wide Friction

Bumping the major version is the correct thing to do when you make a breaking change. But it is also expensive for the entire ecosystem. Every consumer must update their code and release a new version with an updated constraint. Their consumers must then update, and so on up the graph. In practice, this means major version bumps of widely-used libraries create long periods where different parts of the ecosystem are pinned to different major versions, producing diamond dependency conflicts.

This is why many library authors avoid major version bumps for as long as possible, accumulating deprecation warnings instead of breaking changes. It is also why some ecosystems (notably Go) have adopted conventions where a major version bump results in a new import path (`github.com/user/lib/v2`), treating the new major version as an entirely separate package. This sidesteps the diamond problem but at the cost of duplicating the dependency in the graph.

## The Mental Model

A version number is a lossy compression. It takes an arbitrarily complex set of code changes and encodes them into three integers and a promise. The major number says "I changed the contract." The minor number says "I extended the contract." The patch number says "I upheld the contract more faithfully." But the accuracy of that encoding depends entirely on the author's diligence and judgment.

The system works not because it is enforceable, but because package managers treat it as ground truth. Every caret, every tilde, every resolution decision is predicated on the assumption that authors classify their changes correctly. When you write `^2.4.0`, you are not just expressing a version preference — you are delegating a trust decision to every maintainer in your transitive dependency tree. Understanding this lets you reason clearly about when to trust that delegation (mature, well-maintained libraries with strong API discipline), when to constrain it (tilde ranges, exact pins), and when to verify it (lock files, CI-time dependency auditing).

## Key Takeaways

- **Semver is a protocol, not a label.** Package managers algorithmically consume version numbers to make resolution decisions — the number is a machine-readable input, not just a human-readable tag.

- **The `^` operator on `0.x` versions behaves differently than on `1.x+` versions.** Most resolvers contract the range to pin the minor version under `0.x`, because the spec treats the entire `0.x` range as unstable.

- **Dependency resolution is a constraint satisfaction problem across your entire transitive graph.** A single incompatible range constraint anywhere in that graph can break resolution, and small changes can cascade into large shifts in the resolved output.

- **Diamond dependency conflicts are the most common practical failure mode of semver.** They occur when two dependencies require incompatible version ranges of a shared transitive dependency, and they get worse with every major version bump of a widely-used library.

- **Hyrum's Law means that any observable behavior change can be breaking in practice, regardless of how the author classifies it.** Semver communicates intent, not verified impact.

- **Lock files freeze resolution output, but only for the context that generated them.** Libraries do not ship lock files, so their transitive dependencies resolve fresh in the consumer's build — a common source of "works on my machine" bugs.

- **Wide version ranges optimize for receiving patches at the cost of determinism; narrow ranges optimize for stability at the cost of missing fixes.** The right choice depends on how much you trust the upstream maintainer's semver discipline and how sensitive your system is to unexpected changes.

- **A major version bump is semantically correct for breaking changes but creates real ecosystem cost.** It forces a cascade of updates through every consumer in the dependency graph, which is why authors defer it and why some ecosystems treat new major versions as separate packages entirely.


[← Back to Home]({{ "/" | relative_url }})
