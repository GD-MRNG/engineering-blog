---
layout: post
title: "2.1.2 Branching Strategies: Trunk-Based Development vs GitFlow"
author: "Glenn Lum"
date:   2026-02-05 11:00:00 +0800
categories: journal
image: tier_2.jpg
tags: [Tier 2,Core Lifecycle Stages,Depth]
---

Most teams treat their branching strategy as a workflow preference — a set of conventions about how branches get named and when they get merged. The actual decision is more fundamental than that: it determines how your team pays for integration. Every line of code written on a branch that is not the shared mainline is divergence, and divergence has a cost. That cost is not fixed. It compounds. The mechanics of *how* it compounds, and the very different strategies that exist to manage it, are what separate teams that integrate smoothly from teams that dread every merge.

The Level 1 post introduced trunk-based development and GitFlow as two ends of a spectrum. This post is about the underlying dynamics that make each strategy behave the way it does — the specific mechanisms that determine merge conflict rates, the way CI effectiveness degrades with branch lifetime, and the prerequisites that each strategy silently demands from your team and tooling.

## The Cost Curve of Divergence

The most important mechanic to internalize is that integration cost grows **superlinearly** with branch lifetime. Not linearly — superlinearly. A branch that lives for five days is not five times harder to merge than a branch that lives for one day. It can easily be ten or twenty times harder, depending on team size and the rate of change on trunk.

Here is why. Suppose three developers are working on feature branches in a codebase. On day one, each has changed a small, mostly independent set of files. The probability of a conflict between any two branches is low. By day five, each developer has touched more files, modified more function signatures, moved more code around, and altered more shared state. The surface area for conflict has grown in each branch individually, but the *probability* of overlap between branches has grown combinatorially. Developer A refactored a utility module on day two. Developer B added new call sites to that module on day three. Developer C changed the module's return type on day four. None of them see each other's changes until merge day. When they all try to integrate on day five, the result is not three small conflicts — it is a tangled set of interdependent changes that must be reconciled simultaneously.

This is the dynamic that creates integration hell. It is not a cultural failure or a skills problem. It is a structural consequence of how long branches are allowed to diverge.

### Textual Conflicts vs. Semantic Conflicts

Git's merge machinery can detect **textual conflicts** — cases where two branches modified the same lines in the same file. These are annoying but safe, because Git refuses to merge and forces you to resolve them manually. The far more dangerous category is **semantic conflicts**: two branches modify different files, Git merges them cleanly with no conflict markers, and the result is broken code.

A concrete example: you change a function's signature from `processOrder(order)` to `processOrder(order, options)` and update all existing call sites in your branch. A teammate, on a separate branch, writes a new module that calls `processOrder(order)` — the old signature. Git merges both branches without complaint because the changes are in different files. The build breaks. Or worse, if `options` has a default value, the build passes but behavior is silently wrong.

The only reliable defense against semantic conflicts is **frequent integration combined with comprehensive CI**. The shorter your branches live, the smaller the window in which a semantic conflict can develop undetected. This is not a nice-to-have benefit of short-lived branches. It is the primary reason they exist.

## How Trunk-Based Development Actually Works

Trunk-based development is often described as "everyone commits to main." In practice, the mechanics are more specific than that, and the specific mechanics are what make it work or fail.

The actual workflow involves short-lived feature branches — typically measured in hours, ideally not exceeding one to two days. Developers branch from trunk, make a small, coherent change, open a pull request, get a review, and merge. The critical constraint is that **trunk must always be in a releasable state**. Every merge to trunk triggers CI, and if CI fails, fixing trunk takes priority over all other work. This is the "stop the line" principle borrowed from lean manufacturing: a broken trunk blocks the entire team, so it gets fixed immediately.

This creates a specific set of requirements that are non-negotiable:

**Fast CI is structural, not aspirational.** If your CI pipeline takes 45 minutes, developers cannot merge multiple times per day without either waiting idle or merging blind. Trunk-based development requires CI that completes in minutes, not tens of minutes. Teams that attempt trunk-based development with a slow pipeline end up either serializing all work (one merge at a time, everyone waits) or skipping CI (which defeats the entire purpose).

**Feature flags are load-bearing infrastructure.** In trunk-based development, you will frequently need to merge code that is not yet ready for users. A half-built feature, a refactoring that is partway through, a new endpoint that is not yet fully tested. Feature flags allow this code to exist on trunk without being active in production. Without feature flags, you are forced into one of two bad options: merge incomplete features and expose them to users, or keep branches alive until features are complete — which destroys the short-lived branch discipline that makes trunk-based development work. Feature flags are not optional tooling. They are a prerequisite.

**Small, decomposed changes are a skill.** Trunk-based development requires developers to break work into increments that are individually mergeable, individually reviewable, and individually safe to deploy. This is a learned skill. A developer accustomed to working on a three-week feature branch needs to learn how to decompose that same feature into a sequence of fifteen to twenty small changes, each of which leaves trunk in a working state. This decomposition skill is the most underestimated prerequisite of trunk-based development.

## How GitFlow Actually Works

GitFlow defines a specific topology of long-lived branches with strict merge direction rules. Understanding the topology explains why it behaves the way it does.

The two permanent branches are `main` (which always reflects production) and `develop` (which is the integration target for all ongoing work). Feature branches are created from `develop` and merged back to `develop` when complete. When the team decides to prepare a release, a `release` branch is cut from `develop`. On the release branch, only stabilization work happens — bug fixes, documentation, configuration changes. When the release is ready, the release branch is merged to both `main` (which triggers a production deployment or tag) and back to `develop` (so the stabilization fixes are not lost). Hotfix branches are created from `main` for urgent production fixes and merged to both `main` and `develop`.

This topology was designed for a specific problem: **software that ships discrete, versioned releases and must support multiple live versions simultaneously.** Desktop applications, mobile apps distributed through app stores, embedded firmware, open-source libraries — these are contexts where GitFlow's overhead pays for itself. You need a `release/2.3` branch because 2.3 is going through QA while development continues toward 2.4. You need `hotfix` branches because a critical bug in the production version of 2.2 cannot wait for the 2.3 release cycle.

For a web service that deploys to a single environment continuously, this topology solves a problem that does not exist. There is no version 2.3 separate from version 2.4. There is only "what is on trunk" and "what is in production," and ideally those are the same thing or very close to it.

## The CI Freshness Problem

When CI runs on a feature branch, it is testing your changes against the state of the base branch **at the time you last rebased or merged from it**. If your branch is three days old and you have not rebased, CI is validating your code against a three-day-old snapshot of trunk. Even if CI passes, merging may break trunk because trunk has moved.

This is the **CI freshness problem**, and it is the mechanical reason that long-lived branches degrade CI effectiveness. The longer the branch lives without rebasing, the wider the gap between "CI passed on my branch" and "this change is actually safe to integrate." Teams using GitFlow with feature branches that live for weeks often discover this the hard way: every branch is green in isolation, but merging three of them into `develop` in the same afternoon produces a broken build.

Trunk-based development minimizes this gap by keeping branches so short-lived that the base they branch from is never more than a few hours stale. At scale, even this small gap matters, which is why **merge queues** exist. A merge queue (such as GitHub's merge queue or tools like Bors or Mergify) tests pull requests not against current trunk, but against trunk *plus* all the other pull requests ahead of them in the queue. This speculative testing ensures that the post-merge state of trunk has been validated before the merge happens. Without a merge queue, two independently-green pull requests can be merged back-to-back and break trunk because they were never tested together.

## Where Each Strategy Breaks

### Trunk-Based Without the Prerequisites

The most common failure mode is a team that adopts trunk-based development because they read that high-performing teams use it, without investing in the infrastructure it requires. They have a 30-minute CI pipeline. They have no feature flag system. Their developers are accustomed to large, multi-day branches. What happens: trunk breaks frequently because untested combinations of changes collide. Developers start avoiding merging to trunk to avoid being the one who breaks it. Feature branches quietly grow longer. The team ends up with the worst of both worlds — the overhead of trying to keep trunk green without the tooling to actually do it, and branches that are long-lived in practice but lack the structured merge flow that GitFlow provides.

### GitFlow for Continuous Deployment

When a team running a continuously deployed web service adopts GitFlow, the overhead is immediate and the benefit is absent. The `develop` branch becomes a bottleneck where integration problems accumulate. Release branches become a ceremony with no purpose — there is no version to stabilize because the team deploys trunk on every merge anyway. Feature branches live for days or weeks, accumulating divergence. The team spends hours each sprint resolving merge conflicts and debugging integration failures that would not have occurred with shorter-lived branches. The branching model is not actively harmful in the way a bug is harmful — it is harmful in the way that friction is harmful. It slows everything down by a constant factor, and that factor compounds over months.

### The Hybrid Trap

Many teams land on an informal hybrid: "We do trunk-based development, but some branches live a bit longer." This works until it does not. The danger is the absence of a clear contract. In trunk-based development, the contract is explicit — branches live hours, trunk is always green, breaking trunk stops the line. In GitFlow, the contract is also explicit — merge flow follows a defined topology. The hybrid often has no contract at all. Branches live "a few days, usually" which becomes a week during crunch, which becomes two weeks when a feature is complex. Without an explicit maximum branch lifetime and the discipline to enforce it, teams drift toward long-lived branches without the structured merge flow that makes long-lived branches manageable.

## The Mental Model to Carry Forward

A branching strategy is a policy for **when you pay integration costs**. Trunk-based development is a pay-as-you-go model: you pay a small, predictable cost on every merge, multiple times a day. GitFlow is a deferred-payment model: you accumulate integration debt on branches and pay it down in batch during merge windows. The deferred-payment model charges compound interest — the cost of that batch payment grows faster than the time the branch has been alive.

Neither model is universally correct. The right choice depends on your deployment model, your team's discipline and tooling maturity, and the nature of your release process. But the underlying dynamic is always the same: divergence is debt, integration is payment, and the interest rate is determined by team size, rate of change, and the quality of your CI. Once you see branching strategy through this lens, the specific choice for any given context becomes much easier to reason about.

## Key Takeaways

- **Integration cost grows superlinearly with branch lifetime.** A five-day-old branch is not five times harder to merge than a one-day-old branch — it can be an order of magnitude harder, because the surface area for conflict grows combinatorially across concurrent branches.

- **Semantic conflicts are more dangerous than textual conflicts.** Git detects textual conflicts and forces resolution. Semantic conflicts — where independently correct changes combine into broken behavior — merge cleanly and silently. Short-lived branches and comprehensive CI are the only reliable defense.

- **Trunk-based development has three non-negotiable prerequisites: fast CI, feature flags, and the skill to decompose work into small, independently mergeable increments.** Adopting it without all three produces a broken trunk and a demoralized team.

- **GitFlow was designed for versioned, packaged software.** Its branch topology solves the problem of stabilizing releases while continuing development on the next version. For continuously deployed web services, that topology adds ceremony without corresponding benefit.

- **CI on a long-lived branch validates against a stale snapshot of the base branch.** The gap between "CI passed on my branch" and "this is safe to merge to trunk" grows with every hour the branch lives without rebasing. Merge queues exist specifically to close this gap at scale.

- **The most common failure mode is adopting trunk-based development without the infrastructure it demands**, resulting in a system that has neither the safety of short-lived branches nor the structure of a defined long-lived branch topology.

- **A branching strategy without an explicit contract degrades over time.** Teams that do not enforce a maximum branch lifetime or a defined merge flow will drift toward long-lived branches without the safeguards that make long-lived branches workable.

- **Your branching strategy is a policy for when you pay integration costs.** Trunk-based development pays continuously in small increments. GitFlow pays in deferred batches with compound interest. Choosing between them is choosing a payment schedule, and that choice should be driven by your deployment model, team size, and tooling maturity.

[← Back to Home]({{ "/" | relative_url }})
