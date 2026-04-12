---
layout: post
title: "2.5.5 The Release as a Decoupled Event: Feature Flags and Dark Launches"
author: "Glenn Lum"
date:   2026-03-03 11:00:00 +0800
categories: journal
image: tier_2.jpg
tags: [Tier 2,Core Lifecycle Stages,Depth]
---

Most teams adopt feature flags as a simple idea: wrap new code in a conditional, toggle it on when you're ready. An `if` statement with a remote control. That mental model is accurate enough to get started and incomplete enough to cause real damage at scale. The gap is this: a feature flag is not a conditional in your code. It is a **runtime decision point** that creates an entirely separate control plane for feature activation — one that runs parallel to your deployment pipeline, has its own availability requirements, its own failure modes, and its own operational costs. Teams that treat flags as disposable conditionals end up with a system they cannot reason about: untestable state combinations, zombie flags that nobody dares remove, and a flag service whose outage takes down features that have been "fully released" for months. Understanding the actual mechanics — how flag evaluation works, how targeting and progressive delivery function under the hood, and what dark launches really require — is what separates using feature flags from being in control of them.

## How Flag Evaluation Actually Works

A feature flag, at the point of evaluation, needs to answer a question: for *this* context (this user, this request, this environment), should this code path be active? The mechanics of answering that question have significant implications.

The simplest implementation is a remote evaluation model: every time your application hits a flagged code path, it calls an external service that returns the flag's state. This is architecturally clean and operationally disastrous. Flag evaluations happen on hot paths — potentially every incoming request, potentially multiple times per request if several flags are in play. Adding a synchronous network call to each evaluation means your flag service's latency is now added to every flagged code path, and your flag service's availability is now a hard dependency for your entire application.

This is why production-grade flag systems use **local evaluation with a synced rule set**. The pattern works like this: the flag service maintains the canonical set of flag rules (targeting rules, percentage allocations, default values). An SDK embedded in your application periodically fetches this rule set — or receives it via a persistent connection like server-sent events — and caches it locally in memory. When your code evaluates a flag, the SDK resolves it locally against the cached rules. No network call per evaluation. Evaluation latency drops to microseconds instead of milliseconds.

The cost is **eventual consistency**. When you toggle a flag in the management interface, there is a propagation delay before all application instances have the updated rule set. For most use cases — releasing a feature, ramping a percentage rollout — a few seconds of propagation delay is irrelevant. For emergency kill switches, those seconds matter, and you need to understand what your propagation window actually is.

Every flag evaluation also needs a **default value** — what happens when the SDK cannot reach the flag service at all, when the cached rules have expired, or when the flag key doesn't exist. This default is not a formality. It is the behavior your system exhibits when your flag infrastructure is unavailable. If your default for a new, unreleased feature is `true`, a flag service outage releases the feature to everyone. Defaults should always be the *safe* state: for unreleased features, `false`; for kill switches, the "feature is enabled" state (so the kill switch only activates when you explicitly flip it, not when the flag service goes down).

## The Taxonomy of Flags and Why It Matters

Not all feature flags serve the same purpose, and conflating their types is the root cause of the most common operational failure: flag accumulation.

**Release flags** control the rollout of a new feature. They are born when the feature enters development, they are toggled on when the feature is released, and they should be **removed** shortly after. Their entire lifecycle should be measured in days to weeks. The code path behind a release flag is intended to become the only code path. The flag is scaffolding.

**Operational flags** (often called **kill switches**) give you runtime control over system behavior in production. They let you disable an expensive computation, shed load on a non-critical feature during an incident, or force a degraded mode. Unlike release flags, operational flags may be permanent. They are not scaffolding — they are circuit breakers built into your architecture.

**Experiment flags** control A/B tests or multivariate experiments. They route users into cohorts and must maintain consistent assignment for the duration of the experiment to avoid polluting results. Experiment flags have a defined lifecycle tied to the experiment's duration and analysis, but they carry additional requirements around assignment consistency and statistical validity that release flags do not.

**Permission flags** gate access based on entitlement — a user's plan tier, an account-level setting, a contractual agreement. These are effectively configuration, and they often persist indefinitely.

The reason this taxonomy is operationally important: release flags are the most numerous and the most dangerous to leave in place, because they contain dead code paths (the old behavior) that diverge further from the living codebase with every subsequent change. A release flag that remains in the codebase six months after the feature was fully released is not harmless. It is a conditional branch that nobody tests, that interacts with every subsequent change in the same area, and that will fail in unexpected ways when someone finally tries to remove it or accidentally toggles it.

## Sticky Targeting and Progressive Delivery

When you "roll out a feature to 5% of users," the mechanics of how that 5% is selected and maintained are non-trivial.

The naive approach — generate a random number on each request and activate the flag if it's below 0.05 — is wrong. A user refreshing the page would randomly oscillate between the old and new experience. For any feature with state or user-visible behavior, this is unacceptable.

Production systems use **deterministic hashing** for percentage-based targeting. The flag SDK takes a stable identifier (typically the user ID) and the flag key, hashes them together, and maps the hash output to a value between 0 and 100. If the user's hash value falls below the rollout percentage, they get the new experience. Critically, because the hash is deterministic, the same user always gets the same result for the same flag, regardless of which application instance serves the request. Increase the rollout from 5% to 20%, and the original 5% of users remain in the cohort — you're widening the bucket, not re-randomizing it.

This is what enables **progressive delivery**: the practice of incrementally increasing a rollout percentage while monitoring key metrics at each stage. You deploy the code. You enable the flag for 1%. You watch error rates, latency percentiles, and business metrics for that cohort. If everything is clean, you move to 5%, then 20%, then 50%, then 100%. At any point, you can set the percentage back to 0% and every user immediately reverts to the old behavior — no deployment, no rollback, no database migration concern. The toggle is a configuration change that propagates in seconds.

The nuance practitioners miss: the metrics you compare must be **segmented by flag state**. Watching your global error rate while 2% of traffic is on the new code path will not surface a problem — the 98% of healthy traffic will drown out the signal. Your monitoring must be able to answer: "What is the error rate *for users who are evaluating this flag as true* versus *those evaluating it as false*?" This requirement — flag-aware observability — is what separates teams that use progressive delivery from teams that think they use progressive delivery.

## Dark Launches: Running Invisible Code in Production

A dark launch is not the same as a feature that is flagged off. When a flag is off, the new code path does not execute. In a dark launch, the new code path **does execute** — but its results are not returned to the user. The old code path still serves the response. You are running both paths simultaneously: one is live, one is shadow.

The purpose is to observe the new code path's behavior under real production load: its latency characteristics, its error rates, its resource consumption, its output correctness — all with real traffic patterns that synthetic tests cannot replicate.

The implementation typically works like this: the application receives a request. It routes the request through the old (live) code path and returns that result to the user. Concurrently — or sequentially, depending on latency tolerance — it also routes the request through the new code path. The new path's result is logged, compared to the old path's result, and discarded. Metrics from the new path are emitted to your observability stack. If the new path throws an exception, it is captured and reported but does not affect the user's response.

The critical constraint is **side effects**. If the new code path writes to a database, enqueues a job, sends a notification, or calls an external API that charges money, you cannot simply run it in shadow mode without consequence. Dark launches require either that the new code path is read-only, or that its side effects are explicitly intercepted and neutralized. Common approaches include routing writes to a separate shadow database, wrapping external calls in no-op adapters during shadow execution, or structuring the dark launch to cover only the computation and comparison logic while deferring the write path to a separate, later rollout phase.

This constraint is why dark launches are most naturally applied to **read paths and computation**: a new search ranking algorithm, a new recommendation engine, a new pricing calculation, a new query optimization. You can compare the new output against the old output for every request and build statistical confidence that the new path is correct before you ever expose it to a user.

## Tradeoffs and Failure Modes

### Combinatorial State Explosion

Each boolean flag doubles the number of possible states your system can be in. Ten boolean flags produce 1,024 possible configurations. You will not test all of them. You cannot. The practical consequence: you must treat flags as having **minimal interaction**. Each flag should control an isolated code path that does not depend on the state of other flags. When two flags *do* interact — feature B only makes sense if feature A is enabled — that dependency must be explicit in the flag rules, not implicit in the code. Implicit flag dependencies are a category of bug that is nearly impossible to catch in testing and manifests only in the specific state combination that production happens to encounter.

### The Zombie Flag Problem

The most predictable failure mode of feature flags is accumulation. Teams add flags with discipline and remove them with negligence. Within a year, a codebase can accumulate hundreds of flags, the majority of which are release flags whose features were fully rolled out months ago. Each zombie flag is a branch in your code that makes the surrounding logic harder to read, harder to modify, and harder to test. The fix is not cultural ("let's be better about cleanup") — it is mechanical. Set expiration dates on release flags at creation time. Emit warnings or fail CI builds when a release flag exceeds its expiration. Treat flag removal as part of the feature's definition of done, not as a follow-up task.

### The Flag Service as Infrastructure

Once your system depends on feature flags for release control, the flag evaluation system is on the critical path. If you are using local evaluation with a synced rule set, the blast radius of a flag service outage is limited to the propagation of changes — existing cached rules continue to work. But if your caching layer has a bug, if the SDK's initialization fails on application startup, or if a bad rule set propagates that causes evaluation errors, you can experience widespread, correlated failures across every flagged code path simultaneously. The flag system deserves the same operational rigor — monitoring, redundancy, incident response — as any other infrastructure dependency.

## The Mental Model

A feature flag system is a **runtime routing layer** for feature activation. It is not a convenience wrapper around `if/else`. It is infrastructure that accepts targeting rules as input, evaluates them against request context on every relevant code path, and controls which version of your system's behavior any given user experiences. It runs parallel to your deployment pipeline: deployments put code on machines, the flag system decides which code paths are active for whom.

This means it carries the responsibilities of infrastructure: it needs availability guarantees, failure modes you have reasoned about, lifecycle management for the rules it evaluates, and observability that is aware of flag state. The decoupling of release from deployment is genuinely powerful — it transforms releases from irreversible deployment events into reversible configuration changes. But that power comes from operating a new system, not from adding conditionals to an existing one.

## Key Takeaways

- Feature flag evaluation should happen locally against a cached rule set, not via synchronous remote calls on every evaluation — the flag service's latency and availability should not be on the hot path of every request.

- Default flag values are not a formality; they define your system's behavior during flag infrastructure outages, and they should always resolve to the safe state (unreleased features off, kill switches inactive).

- Release flags, operational flags, experiment flags, and permission flags have fundamentally different lifecycles; treating them identically is the root cause of flag accumulation and technical debt.

- Percentage-based rollouts use deterministic hashing of user identity and flag key, not random sampling, so that users experience consistent behavior across requests and the rollout cohort is stable as percentages increase.

- Progressive delivery only works if your observability is segmented by flag state — watching global metrics while a small percentage of traffic is on a new code path will not surface regressions.

- A dark launch executes the new code path without exposing its results to users, which means it is only safe for read-only or side-effect-free paths unless you explicitly neutralize writes and external calls.

- Implicit dependencies between flags — where the behavior of one flag only makes sense given a particular state of another — are a category of bug that is nearly impossible to detect in testing and should be made explicit in flag rules.

- Flag removal must be enforced mechanically (expiration dates, CI checks, automated warnings), not culturally; no team sustains manual cleanup discipline across hundreds of flags over time.

[← Back to Home]({{ "/" | relative_url }})
