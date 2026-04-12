---
layout: post
title: "2.1.5 Conflict Resolution: Textual vs Semantic Conflicts"
author: "Glenn Lum"
date:   2026-02-08 11:00:00 +0800
categories: journal
image: tier_2.jpg
tags: [Tier 2,Core Lifecycle Stages,Depth]
---

Most engineers think of a merge conflict as the thing that interrupts their workflow — the moment Git stops and demands manual intervention. That framing is exactly backwards. When Git raises a textual conflict, it is doing its job correctly. It detected incompatible changes and refused to guess. The actual danger is the merge that completes without any conflict at all, producing code that compiles, passes the linter, and introduces a defect that nobody catches until production. Understanding why requires looking at what Git actually does during a merge, and more importantly, what it cannot do.

## How a Three-Way Merge Works

Git's merge operation is not a comparison between two branches. It is a comparison between three snapshots: the two branch tips and their **merge base**, the most recent common ancestor commit. This is the foundation that makes auto-resolution possible, and also the foundation that makes it dangerous.

When you run `git merge feature` from `main`, Git identifies the merge base — the commit where `feature` diverged from `main`. It then computes two diffs: one from the base to the tip of `main`, and one from the base to the tip of `feature`. The merge algorithm applies both sets of changes to the base simultaneously.

The logic is straightforward. For any given region of a file, there are four possible states: neither side changed it (keep the base version), only `main` changed it (take `main`'s version), only `feature` changed it (take `feature`'s version), or both sides changed it. That last case is a textual conflict. The first three cases are auto-resolved.

The critical detail: Git defines "region" at the level of **text lines**. It does not parse your code. It does not understand functions, classes, variable scopes, type signatures, or call graphs. It sees lines of text, groups changes into hunks, and determines whether two hunks overlap. If two changes modify different lines — even adjacent lines in the same function — Git will merge them silently. It has no mechanism to evaluate whether the combined result is logically coherent.

## Textual Conflicts: The Safe Failure Mode

A textual conflict arises when both branches modify overlapping lines in the same file relative to the merge base. Git inserts conflict markers and stops:

```
<<<<<<< HEAD
    return price * 0.85;
=======
    return price - discount;
```

The developer must choose one version, combine them, or write something new. This is the most visible form of conflict, and it is the least dangerous. It forces human review at exactly the point where the tool's ability to reason has been exhausted.

Textual conflicts are not a sign that something went wrong with your workflow. They are a signal that the merge tool correctly identified an ambiguity it could not resolve. The frequency of textual conflicts is driven by two factors: how long branches live before merging, and how concentrated changes are within the same files. Trunk-based development produces fewer textual conflicts not because it eliminates conflicting intent, but because it reduces the window of divergence during which the same lines can be modified independently.

There is one subtle class of textual conflict worth understanding: the **edit-delete conflict**. One branch modifies a region of a file; the other branch deletes the entire file (or deletes the section containing that region). Git cannot auto-resolve this because it cannot decide whether the deletion should take precedence over the edit or vice versa. These are textual conflicts that signal a potentially deep disagreement about the structure of the codebase, not just about the content of a line.

## Semantic Conflicts: The Silent Failure Mode

A **semantic conflict** occurs when Git merges two changes cleanly — no conflict markers, no human intervention — but the resulting code is incorrect. The merge succeeds textually but fails logically. This is possible because Git merges text, not meaning.

Consider a concrete scenario. Your codebase has a function:

```python
def calculate_discount(price):
    return price * 0.15  # returns absolute discount amount
```

Branch A changes the function's contract. The team decides discounts should be represented as multipliers, not absolute values:

```python
def calculate_discount(price):
    return 0.85  # returns the multiplier to apply
```

Branch A updates all existing call sites to use the new contract: `final = price * calculate_discount(price)`.

Meanwhile, Branch B — developed in parallel — adds a new checkout flow in a completely different file:

```python
final_price = item_price - calculate_discount(item_price)
```

Branch B's author wrote this against the original contract, where subtracting the return value made sense. Git merges these branches without any conflict. The changes are in different files. There are no overlapping lines. The result compiles. Branch A's tests pass because they validate the new contract. Branch B's tests pass because they were written to validate the new checkout flow in isolation. But in the merged codebase, the new checkout flow is now computing `item_price - 0.85` instead of `item_price - (item_price * 0.15)`. The customer pays $99.15 instead of $85.00. This ships.

This is not an exotic edge case. This is the ordinary consequence of two developers changing code that is related by call graph, data flow, or implicit contract — but not related by file location or line proximity.

### The Spectrum of Detectability

Not all semantic conflicts are equally invisible. They fall along a spectrum based on how far downstream the failure manifests:

**Compile-time detectable.** One branch renames a function; the other adds a call using the old name. Git merges cleanly, but the compiler catches it. In statically typed languages, a meaningful subset of semantic conflicts manifest as type errors or unresolved references after the merge. This is one of the underappreciated safety benefits of strong type systems — they act as a second layer of conflict detection after Git's textual merge. Dynamic languages lose this safety net entirely.

**Test-detectable.** The merged code compiles but produces wrong results that an existing integration test catches. This requires that your test suite exercises the specific interaction created by the merge — not just the behavior of each branch in isolation. Most test suites do not have this property, because tests are typically written to validate the change being made, not to validate the interaction between that change and an unknown concurrent change.

**Silently incorrect.** The merged code compiles, passes all tests, and produces subtly wrong behavior in production. The discount example above falls here if the test suite only validates the checkout flow with mocked discount values. These are the conflicts that produce the bugs you spend days tracking down, because nothing in the commit history or the merge record suggests anything went wrong.

### Why Semantic Conflicts Happen in Different Files

The most counterintuitive property of semantic conflicts is that they almost always involve changes in different files or in well-separated regions of the same file. This is precisely why Git cannot detect them — Git's auto-resolution works perfectly when changes don't overlap textually.

The root cause is that **code has coupling that text does not**. A function's callers are semantically coupled to its contract, but textually they exist in completely different locations. A configuration value is semantically coupled to every code path that reads it, but those code paths may be spread across dozens of files. When one branch changes the source of that coupling (the function contract, the config schema, the database column meaning) and another branch adds or modifies a consumer of it, Git sees two non-overlapping text changes and combines them without hesitation.

## Where This Breaks in Practice

### The Clean Merge Trap

Teams that judge merge safety by the absence of textual conflicts are operating with a false signal. A merge that completes cleanly provides zero information about semantic correctness. The confidence should come not from Git's merge result, but from what runs after it: the CI pipeline on the merged commit, the integration test suite, the type checker. Teams that skip post-merge validation because "there were no conflicts" are relying on a text tool to guarantee program correctness.

### Long-Lived Branches Amplify Semantic Risk Non-Linearly

The Level 1 post described how long-lived branches create "integration hell." The specific mechanism worth understanding is that semantic conflict risk grows non-linearly with branch lifetime. A branch that lives for two days overlaps with whatever else was merged in those two days. A branch that lives for two weeks overlaps with everything merged in two weeks — but the number of potential semantic interactions between your changes and all of those merged changes grows combinatorially, not linearly. Every new function you add can conflict with every contract change that landed on `main`. Every contract change you make can conflict with every new consumer added on `main`. This is why the pain of long-lived branches feels disproportionate to their length.

### The Test Gap

The standard advice for catching semantic conflicts is "write good tests." This is correct but insufficient. The specific gap is that branch-level testing validates each branch's changes against the codebase as it existed when the branch was created. It does not validate those changes against the concurrent changes landing from other branches.

Only tests that run against the **post-merge commit** can catch semantic conflicts, and only if those tests exercise the specific interaction that was broken. This is why CI pipelines that run the full test suite on every merge to `main` are not optional overhead — they are the primary detection mechanism for the class of bugs that Git is structurally incapable of preventing. And even then, the detection is only as good as the coverage of cross-cutting interactions, which is almost always the weakest part of any test suite.

### Refactoring as a Semantic Conflict Generator

Large refactors — renaming a widely-used function, changing a shared data structure's shape, modifying a return type's semantics — are disproportionate generators of semantic conflicts. The refactor changes a contract that many consumers depend on, and if any other branch is concurrently adding or modifying a consumer of that contract, a semantic conflict is nearly guaranteed. This is one reason atomic, well-communicated refactoring that lands quickly on the trunk is less risky than a refactoring branch that lives for a week. The faster the contract change lands, the smaller the window for concurrent work to be written against the old contract.

## The Model to Carry Forward

Git is a text merge tool. It guarantees textual consistency — that the bytes in the merged file represent a coherent combination of both sides' textual changes. It provides zero guarantees about semantic consistency — that the merged program does what either author intended.

This means there are two entirely separate categories of merge risk, and they require different defenses. Textual conflicts are handled by Git itself — they force human resolution and are therefore self-limiting. Semantic conflicts pass through Git undetected and must be caught by everything downstream: compilers, type checkers, test suites running on the post-merge commit, integration environments, and ultimately code review of the merge itself. The most important conceptual shift is this: a clean merge is not a safe merge. It is an unvalidated merge. Safety comes from what you build after the merge tool finishes.

## Key Takeaways

- A textual conflict means Git detected overlapping changes to the same lines and refused to guess — this is the merge tool working correctly, not a failure of your workflow.
- Git's three-way merge compares both branch tips against their common ancestor; it auto-resolves when changes affect different text regions, regardless of whether those regions are semantically related.
- Semantic conflicts occur when Git merges cleanly but the combined code is logically incorrect — these are more dangerous than textual conflicts precisely because no tool flags them at merge time.
- Statically typed languages provide a partial safety net against semantic conflicts by catching type errors and unresolved references in the post-merge compile step; dynamic languages offer no equivalent automatic detection.
- Tests written to validate a single branch's changes do not protect against semantic conflicts — only tests run on the post-merge result that exercise cross-cutting interactions can catch them.
- Semantic conflict risk grows non-linearly with branch lifetime because the number of potential interactions between your changes and concurrent changes is combinatorial.
- Large refactors that change widely-used contracts are disproportionate sources of semantic conflicts and should land on the trunk as quickly as possible to minimize the window of divergence.
- A merge that completes without conflict markers provides no information about semantic correctness — post-merge CI, not merge cleanliness, is your actual safety signal.

[← Back to Home]({{ "/" | relative_url }})
