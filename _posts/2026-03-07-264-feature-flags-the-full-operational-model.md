---
layout: post
title: "2.6.4 Feature Flags: The Full Operational Model"
author: "Glenn Lum"
date:   2026-03-07 11:00:00 +0800
categories: journal
image: tier_2.jpg
tags: [Tier 2,Core Lifecycle Stages,Depth]
---

Most engineers interact with feature flags at the surface: a function call that returns a boolean, a conditional that gates a code path, a toggle in a dashboard. This makes flags feel simple — they look like configuration. But the system behind that function call is doing substantially more work than most practitioners realize, and the operational consequences of that system's design show up in places that have nothing to do with the feature being flagged. The gap between "I use feature flags" and "I understand what my flag system is actually doing" is where incidents live. A flag isn't an if/else statement. It's a runtime decision engine with distributed state, evaluation semantics that depend on ordering and context, and a lifecycle that interacts with every deployment, rollback, and incident response process you have.

## How Flag Evaluation Actually Works

A feature flag check in your application code looks like a local function call:

```python
if flag_client.is_enabled("new-checkout-flow", user_context):
    render_new_checkout()
else:
    render_old_checkout()
```

What happens inside that call depends entirely on whether you're running a **server-side SDK** or a **client-side SDK**, and the difference matters.

A server-side SDK — the kind running in your backend services — typically connects to the flag management service on startup, downloads the entire set of flag definitions (rules, targeting configuration, percentage allocations, default values), and caches them locally in memory. Evaluation happens entirely within your process. When you call `is_enabled`, the SDK is not making a network request. It's evaluating the flag's rules against the context you passed in, using the locally cached configuration. This is why flag evaluation adds microseconds of latency, not milliseconds — there is no network hop in the critical path.

The SDK keeps this local cache current through one of two mechanisms: **polling** (fetching the full configuration on an interval, typically 30 seconds to a few minutes) or **streaming** (maintaining a persistent connection via SSE or WebSocket, receiving updates pushed from the flag service in near-real-time). Streaming gives you sub-second propagation of flag changes. Polling gives you simpler infrastructure at the cost of a propagation delay window where different instances of your service may be evaluating different versions of a flag's rules.

A client-side SDK — running in a browser or mobile app — works differently. You cannot ship your entire flag ruleset to the client, because it may contain targeting rules that reference other users' attributes, internal business logic, or information you simply don't want to expose. So client-side SDKs send the evaluation context (the current user's attributes) to the flag service, and the service returns the evaluated results for that specific context. This means client-side flag checks do involve a network call, or more precisely, they involve a network call on initialization, with the results cached locally for subsequent checks. The tradeoff: client-side evaluation depends on an initial fetch succeeding, and your application needs a strategy for what to render before that fetch completes.

Both models share a critical design property: **the flag service being unavailable should not break your application.** Server-side SDKs keep serving from their last-known-good cache. Client-side SDKs fall back to hardcoded defaults you provide at initialization. This means flag evaluation is eventually consistent by design. When you toggle a flag in your dashboard, the change does not take effect atomically across your fleet. It propagates over seconds (streaming) or minutes (polling), and any instance that can't reach the flag service continues operating on stale configuration indefinitely.

## Targeting Rules and Evaluation Order

A flag is not just an on/off switch with a percentage. It is a small rules engine. A typical flag definition has this structure: an overall kill switch (flag enabled or disabled), an ordered list of targeting rules, and a default rule that applies when nothing else matches.

Each targeting rule specifies a set of conditions evaluated against the **evaluation context** — the bag of attributes you pass in at call time. That context might include a user ID, an email domain, a country code, an account tier, a device type, or any other attribute your application knows at the point of evaluation. A rule says: "if the context matches these conditions, serve this variant."

The rules are evaluated top-to-bottom, and **the first matching rule wins**. This ordering is not incidental — it's the primary mechanism for expressing priority. A common pattern: the first rule targets a list of specific user IDs (your internal testers) and serves them the new variant. The second rule targets users in a specific region and serves them the new variant at 50%. The default rule serves the old variant. If you reorder the rules, your internal testers might fall into the regional rule instead, and half of them would see the old variant. The evaluation order *is* the logic.

This is where flags stop being configuration and start being code. The targeting rules are business logic expressed as data. They have the same properties as code — they can have bugs, they interact with each other, and the only way to understand what a given user sees is to trace the evaluation path through the full ruleset. A flag with six targeting rules and three variants is a decision tree. Treating it as "just a toggle" is how you end up debugging behavior that isn't in your source code.

## Percentage Rollouts and Consistent Hashing

When a targeting rule says "serve the new variant to 20% of users," the system needs to decide which 20%. The naive approach — generate a random number on each evaluation — fails immediately, because the same user would get different variants on successive page loads. Rollouts need to be **sticky**: a user who gets the new variant on their first visit must get it on every subsequent visit, without storing per-user assignments.

The standard solution is **deterministic hashing**. The SDK takes the flag key and the user's identifier, concatenates them, runs the result through a hash function, and maps the hash output to a value between 0 and 99. If that value falls below the rollout percentage, the user gets the new variant. Same inputs, same hash, same result, every time, on every server instance, with no shared state required.

```
hash("new-checkout-flow" + "user-7829") % 100 → 34
```

If the rollout is at 20%, user 7829 gets the old variant (34 ≥ 20). If you later increase the rollout to 50%, user 7829 now gets the new variant (34 < 50). Critically, every user who was already in the 20% cohort remains in the 50% cohort, because their hash values haven't changed and the threshold only moved in one direction. This **monotonic rollout** property means increasing a percentage never yanks the new experience away from someone who already had it.

The flag key is included in the hash input so that different flags assign different cohorts. Without it, the same 20% of users would be in the "on" group for every flag at 20%, which would make your "random" samples entirely correlated and your A/B test results meaningless.

One subtlety practitioners miss: percentage rollouts are only as good as your user identifier. If you're evaluating a flag before authentication and you don't have a stable user ID, you fall back to something like a session cookie or a device fingerprint. If that identifier changes, the user gets re-bucketed. This is a common source of inconsistent behavior in pre-login experiences.

## The Flag Configuration Surface

A single feature flag is trivial. The problem is that you don't have a single feature flag. A production system at any reasonable scale accumulates tens to hundreds of flags, and each flag with targeting rules is an independent axis of variation in your application's behavior.

Consider what this means for your system's configuration surface. If you have 15 active boolean flags, the theoretical state space of your application is 2^15: 32,768 possible combinations of behavior. Nobody is testing all of those combinations. Nobody is even enumerating them. In practice, many combinations are never exercised — but some of them are exercised, accidentally, by users who happen to fall into a particular intersection of targeting rules across multiple flags.

This is the mechanical reason flag interactions are dangerous. Two flags, each benign in isolation, can produce a broken experience in combination. The new checkout flow assumes a cart data structure that the new inventory display flag doesn't produce. Both flags work independently. Together, for the 3% of users who are in both rollout cohorts, the checkout page throws an error. This class of bug is invisible to unit tests, invisible to integration tests that toggle one flag at a time, and invisible to anyone reading either flag's targeting rules. It only exists in the intersection.

## Flag Lifecycle as an Operational Discipline

The Level 1 post mentioned that flags accumulate and need lifecycle management. The mechanics of *why* this is hard deserve examination.

A flag starts with a clear purpose: gate a feature rollout. The feature ships, the rollout reaches 100%, and the flag should be removed. But removal means: deleting the flag definition from the management service, removing every conditional in the codebase that references it, removing the old code path that is no longer reachable, and verifying that no other flag's targeting rules or no external system references this flag's key. For a flag that touches three services, this is a cross-team code change that requires coordination, review, and deployment. It is, in effect, a small project — and it delivers zero user-facing value.

This is why flags rot. The incentive to create a flag is immediate and strong (you need it to ship safely). The incentive to remove a flag is diffuse and weak (it makes the codebase marginally cleaner). Without a forcing function — a policy, a tech debt budget, an automated alert when flags exceed their planned lifespan — removal doesn't happen.

**Stale flags** are not inert. A flag that has been at 100% for eight months and that "everyone knows" is fully rolled out is still a conditional in your code. If someone accidentally disables it during an incident response — because they're toggling flags trying to isolate a problem and they don't recognize this one — they've just disabled a feature that has been in production for eight months. The blast radius of a stale flag is proportional to how long it has been at 100% without being removed, because that is how much production behavior silently depends on it.

The mechanical fix is **flag metadata and expiration**. Every flag should carry an owner, a creation date, an intended removal date, and a flag type (release flag, experiment flag, operational kill switch, permission flag). Operational kill switches — flags that exist permanently to allow you to disable an expensive code path during an incident — are explicitly long-lived and should be marked as such. Release flags should be aggressively expired. The tooling should surface flags past their expiration date as tech debt, ideally with the same urgency as a failing build.

## The Tradeoffs and Where It Breaks

**Evaluation latency is real on the client side.** If your flag service is slow or unreachable on first load, users see default behavior (typically the old variant) and then potentially flash to the new variant when the evaluated flags arrive. This **flicker** is not a cosmetic problem — it's a trust problem. Users see the interface rearrange itself. Solving this requires either server-side rendering with flag evaluation baked in, or a loading state that waits for flags before rendering — both of which add architectural complexity.

**Testing becomes a coverage problem.** You can't test every flag combination, so you need a strategy. The most practical approach is to test two states per flag — fully on and fully off — and to explicitly test known interactions between flags that affect the same user-facing surface. This is a judgment call, not an automated solution, and it requires that engineers actually know which flags are active and what they affect.

**Flag systems are invisible dependencies.** Your flag service is now in the critical path of every service that uses it (mediated by caching and defaults, but still). Your flag management dashboard is now a production control plane — anyone with access can change production behavior without a deployment, a code review, or an audit trail unless you've explicitly configured one. Treat flag changes as production changes. If your deployment pipeline requires approval and your flag dashboard doesn't, your controls have a gap.

**Debugging is harder.** When a user reports a bug, you need to know not just what code is deployed, but what flag state that user was evaluated against. This means logging flag evaluations per-request, or at minimum, being able to reconstruct a user's flag assignments after the fact. Without this, you're debugging with incomplete information about what code path was actually executed.

## The Mental Model

A feature flag system is a **runtime rules engine** that sits alongside your application code and governs which code paths execute for which users. It is not configuration in the way an environment variable is configuration. It is behavioral logic, expressed as data, evaluated at request time, and distributed across your infrastructure with eventual consistency semantics.

The critical conceptual shift is this: every active flag is a branch in your codebase that exists outside your source control, outside your test suite, and outside your deployment pipeline. The flag system is powerful precisely because it decouples these decisions from your release process — and it is dangerous for exactly the same reason. The discipline required to operate flags well is not about the tooling. It is about treating the flag inventory as production infrastructure that requires the same rigor you apply to your code and your deployments.

## Key Takeaways

- Server-side flag SDKs evaluate locally from a cached ruleset, adding microseconds of latency; client-side SDKs depend on a network fetch, which introduces latency, flicker, and a dependency on flag service availability at page load.

- Targeting rules are evaluated top-to-bottom with first-match-wins semantics — the order of rules is logic, not presentation, and reordering them changes behavior.

- Percentage rollouts use deterministic hashing of the flag key and user identifier, making assignments sticky without per-user storage and ensuring that increasing a rollout percentage never removes users from the existing cohort.

- The flag key is included in the hash input specifically to prevent different flags from assigning the same users to the same cohorts, which would make experiments and rollouts statistically correlated.

- With N active boolean flags, your application has 2^N possible behavioral states, and flag interaction bugs exist in combinations that no individual flag test will catch.

- Stale flags — flags that reached 100% and were never removed — are the highest-risk flags in your inventory because disabling them during incident response affects features users have depended on for months.

- Flag changes are production changes; if your flag dashboard allows changes without the same approval, audit, and rollback controls you require for deployments, your operational controls have a gap.

- Debugging user-reported issues requires knowing the flag state evaluated for that user at request time — if you aren't logging flag evaluations per-request, you are missing a dimension of observability that you will eventually need.

[← Back to Home]({{ "/" | relative_url }})
