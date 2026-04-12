---
layout: post
title: "2.4.3 Dependency Graphs and Transitive Dependencies"
author: "Glenn Lum"
date:   2026-02-23 11:00:00 +0800
categories: journal
image: tier_2.jpg
tags: [Tier 2,Core Lifecycle Stages,Depth]
---

Most engineers think of their dependencies as a list. You open `package.json` or `requirements.txt` or `build.gradle`, and you see a flat enumeration of libraries your project uses. This is the view your tooling presents, and it is misleading. What you actually have is a graph — a directed, potentially cyclic, deeply nested structure where every node can pull in dozens of nodes you never asked for, never audited, and may not know exist. The difference between seeing a list and seeing a graph is the difference between thinking you have 12 dependencies and discovering you have 1,400. That gap is where the real complexity of dependency management lives, and it is where most production incidents involving dependencies originate.

## The Shape of the Graph

A **dependency graph** is a directed graph where each node is a package at a specific version and each edge represents a "depends on" relationship. Your application is the root node. Your declared dependencies are its immediate children. Their dependencies are the next layer. This continues until you reach leaf nodes — packages with no dependencies of their own.

The term **transitive dependency** refers to any node in this graph that is not a direct child of the root. If your application depends on library A, and library A depends on library B, then B is a transitive dependency of your application. You did not choose B. You may not know B exists. But B's code runs in your process, has access to your application's memory space, and can fail in ways that crash your service.

The graph expands fast. A typical mid-size Node.js application with 30 direct dependencies will commonly have 800 to 1,500 total packages in its `node_modules` directory. A Java application with 20 declared dependencies in Maven can easily resolve to 200+ JARs. The ratio of transitive to direct dependencies is typically 10:1 or higher. This is not pathological — it is the normal state of modern software.

The shape that causes the most trouble is the **diamond dependency**. Your application depends on libraries A and B. Both A and B depend on library C, but they require different versions of C. Your application has never heard of library C, yet a version conflict in C now determines whether your application can build at all.

```
        Your App
        /      \
       A        B
       \       /
      C@1.2  C@2.0
```

This is not a hypothetical. It is the central problem of dependency resolution, and every package manager in existence has to have a strategy for it.

## How Resolution Actually Works

When you run `npm install` or `pip install` or `mvn dependency:resolve`, the package manager is doing something considerably more complex than downloading files. It is solving a constraint satisfaction problem: find a set of package versions such that every declared version constraint in the entire graph is simultaneously satisfied.

The inputs to this problem are version constraints — expressions like `^2.3.0` (compatible with 2.3.0), `>=1.0 <2.0`, or `~=3.4.1`. Each dependency in the graph declares constraints on its own dependencies. The resolver must find a concrete version for every package in the graph that satisfies all constraints from all packages that depend on it.

This is, in the general case, NP-complete. It reduces to Boolean satisfiability. Real-world package managers cope with this through heuristics, greedy algorithms, and ecosystem-specific simplifications — but the computational hardness is real. It is why `pip` resolution can take minutes on complex projects, and why you occasionally see resolvers fail entirely or produce inconsistent results.

### Different Ecosystems, Different Strategies

The strategy a package manager uses to resolve conflicts fundamentally shapes what kinds of problems you encounter.

**npm (Node.js)** sidesteps the diamond problem by allowing multiple versions of the same package to coexist in the dependency tree. If A needs `C@1.2` and B needs `C@2.0`, npm installs both. Each gets its own copy nested inside the directory of the package that requested it. This means your `node_modules` directory can contain three different versions of the same library simultaneously. The upside is that resolution almost always succeeds. The downside is binary size bloat, increased memory usage, and subtle bugs when two parts of your application are operating on different versions of a shared library, producing objects that are structurally identical but fail `instanceof` checks because they come from different module instances.

**Maven (Java)** uses a **nearest-wins** strategy. When two paths through the graph require different versions of the same artifact, Maven picks the version declared closest to the root. If your application directly declares `C@2.0`, that wins over A's transitive request for `C@1.2`. If neither is direct and both are at the same depth, the one encountered first in declaration order wins. This is deterministic but not necessarily correct — there is no guarantee that A will actually work with `C@2.0`. Maven selects one version and loads it into a flat classpath. If A calls a method that existed in `C@1.2` but was removed in `C@2.0`, you get a `NoSuchMethodError` at runtime, not at build time.

**Go modules** take a different approach entirely: **Minimum Version Selection (MVS)**. Instead of picking the newest version that satisfies all constraints, Go picks the minimum version that satisfies all constraints. If A requires `C >= 1.2` and B requires `C >= 1.5`, Go selects `C@1.5` — not the latest available release of C, even if `C@2.3` exists and satisfies both constraints. The reasoning is that the minimum version is the one closest to what each library was actually tested against. This makes resolution deterministic, fast (no SAT solving needed), and reproducible without a lock file. The cost is that you do not automatically get the latest patches and security fixes.

**pip (Python)** historically had no real resolver and simply installed whatever it encountered first, leading to silent version conflicts. Modern pip (since version 20.3) includes a backtracking resolver that attempts to find a globally consistent solution. When it encounters a conflict, it backtracks and tries alternative versions. This can be slow, and on complex dependency graphs, it can fail with resolution errors that are genuinely difficult to diagnose.

### What the Resolver Cannot See

A critical limitation of all resolution strategies: they operate purely on declared version constraints. They do not know whether two packages are actually compatible at runtime. If library A declares that it works with `C >= 1.0` but actually uses an internal API that was removed in `C@1.8`, the resolver has no way to know this. It will happily resolve `C@1.8` or later, and the incompatibility will surface as a runtime error — or worse, as silently incorrect behavior.

This is why overly broad version constraints are dangerous. A library that declares `>=1.0` as its constraint on a dependency is asserting compatibility with every future major version of that dependency — an assertion that is almost certainly false. The resolver takes library authors at their word.

## Blast Radius and the Propagation Problem

The graph structure means that a change to a single deeply-shared package can affect an enormous number of applications that have no idea they depend on it.

Consider a utility library — something like `is-promise` in the Node ecosystem or `commons-io` in Java. These sit near the leaves of thousands of dependency trees. When `is-promise` shipped a breaking change in a minor version update in 2020, it broke builds across the Node ecosystem because it was a transitive dependency of widely-used middleware packages. Developers whose direct dependencies had not changed at all found their builds failing.

The blast radius of a change is a function of two properties: how many packages transitively depend on the changed package (**reverse dependency count**), and how tightly version constraints pin it. A package with 10,000 reverse dependents and constraints like `^2.0.0` has massive blast radius, because a new `2.x` release will be automatically pulled into all of those trees the next time anyone resolves.

This is also the mechanism through which supply chain attacks propagate. A compromised package does not need to be popular on its own — it needs to be a transitive dependency of something popular. The `event-stream` incident in 2018 exploited exactly this: a rarely-maintained transitive dependency was taken over by a malicious actor, and the payload reached a widely-used cryptocurrency wallet because it was three levels deep in the dependency graph.

## Tradeoffs and Failure Modes

### The Phantom Dependency

In ecosystems that flatten the dependency tree (like npm with hoisting, or Maven's flat classpath), your code can accidentally import a transitive dependency directly — and it works, because the package happens to be installed. This is a **phantom dependency**: you are using a package you never declared, and it will vanish without warning when the intermediate dependency that brought it in drops it or changes its version. The result is breakage in a future build that appears to have no cause, because your `package.json` or `pom.xml` did not change.

### The Lock File Divergence

Lock files record the resolved graph at a point in time. When two developers resolve at different times — or when CI resolves without a committed lock file — they can get different dependency graphs even from identical declared dependencies. This produces the infamous "works on my machine" category of bugs, except the root cause is invisible in the source code. The lock file is not an optional convenience; it is the authoritative record of what your application actually depends on. Treating it as generated output that does not need review is how inconsistencies enter production.

### Update Paralysis

The deeper and wider your graph, the harder updates become. Updating a direct dependency may require updating its transitive dependencies, which may conflict with the requirements of your other direct dependencies. Engineers encounter this as a resolver that cannot find a valid solution, or a lock file diff that changes 300 packages when they intended to update one. The rational response is often to delay updates, which compounds the problem: the further behind you fall, the more changes accumulate, and the harder the eventual update becomes. This creates a stable equilibrium of outdated dependencies — exactly the condition that maximizes vulnerability exposure.

### Duplication vs. Inconsistency

Ecosystems that allow multiple versions of the same package (npm) trade correctness risks for resolution flexibility. Ecosystems that enforce a single version (Maven, Go) trade resolution flexibility for the risk of runtime incompatibility. Neither is universally better. The choice depends on whether the greater danger in your context is inconsistent shared state (where duplication is worse) or runtime method-not-found errors (where forced unification is worse). Understanding which strategy your ecosystem uses tells you what category of bugs to watch for.

## The Mental Model

Your declared dependencies are an interface into a graph that is mostly outside your control. The graph is resolved by an algorithm that is working from constraints declared by other people, about compatibility properties they may not have verified, across a tree that is too large for any human to audit by hand.

The practical consequence is this: you are not managing a list of libraries. You are managing a snapshot of a constraint satisfaction solution. Your lock file is that snapshot. Your resolver is the solver. The version constraints declared by every package author in your tree are the inputs. When any input changes — even one authored by a stranger, three levels deep — the solution can shift, and the behavior of your application can change.

Reasoning about dependencies means reasoning about graphs, not lists. It means understanding that your blast radius extends to every node in your transitive closure, that your attack surface includes code you have never read, and that the correctness of your build depends on the truthfulness of version constraints you did not write.

## Key Takeaways

- Your actual dependency set is not what you declared — it is the full transitive closure of the dependency graph, which is typically an order of magnitude larger than your direct dependencies.

- The diamond dependency problem — two paths through the graph requiring different versions of the same package — is the central challenge of dependency resolution, and every package manager handles it differently with different failure modes.

- npm allows duplicate versions (risking inconsistency and bloat), Maven picks the nearest version (risking runtime incompatibility), Go selects the minimum satisfying version (risking stale dependencies), and pip backtracks through possibilities (risking slow or failed resolution).

- Dependency resolvers operate only on declared version constraints, not on actual runtime compatibility. A library that declares an overly broad version range is making an unverified promise that the resolver will trust.

- The blast radius of a change to any package is proportional to its reverse transitive dependency count — a breaking change in a deeply-shared leaf package can break builds across an entire ecosystem.

- Phantom dependencies — transitive packages you use directly without declaring — are a common source of mysterious build failures when the undeclared package disappears from the resolved graph.

- A lock file is not a generated convenience artifact; it is the authoritative record of the exact graph your application was built and tested against, and it deserves the same review discipline as source code.

- Delaying dependency updates to avoid resolution complexity creates a stable equilibrium of outdated packages that maximizes exposure to known vulnerabilities — the cost of not updating compounds over time.

[← Back to Home]({{ "/" | relative_url }})
