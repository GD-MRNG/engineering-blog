---
layout: post
title: "3.3.4 Chaos Engineering: Deliberately Breaking Things"
author: "Glenn Lum"
date:   2026-03-31 11:00:00 +0800
categories: journal
image: tier_3.jpg
tags: [Tier 3, Cross-Cutting Disciplines, Depth]
---

Most teams that say they do chaos engineering are just breaking things. They kill a pod, watch the replacement spin up, confirm the service recovers, and call it a successful experiment. But that is not an experiment — it is a demo of Kubernetes' scheduling behavior. Nothing was learned that was not already known. The circuit breaker was not tested. The fallback path was not exercised under realistic conditions. The alerting chain was not validated. The team walks away with increased confidence that is not backed by increased understanding.

The gap between "we inject failures" and "we run chaos experiments that improve our system's resilience" is the gap between a tool and a discipline. The tool is the failure injection. The discipline is everything else: what you choose to break, what you predict will happen, how you measure whether your prediction held, and what you do when it does not. That discipline is what this post is about.

## The Experiment as the Unit of Work

Chaos engineering borrows its structure from the scientific method, and the borrowing is not metaphorical. A chaos experiment has the same components as any controlled experiment: a hypothesis, an independent variable, dependent variables, controls, and abort conditions. Skip any of these and you are not experimenting — you are just causing incidents on purpose.

The **hypothesis** is the most important part, and it is the part most teams skip or treat as a formality. A useful hypothesis is not "the system should handle this failure." A useful hypothesis is specific and falsifiable: "When the primary database becomes unreachable, the order service will begin returning cached inventory data within 5 seconds, the checkout error rate will remain below 2%, and the alerting pipeline will page the on-call engineer within 3 minutes." That hypothesis encodes your understanding of three separate systems — the caching layer, the error-handling logic, and the monitoring stack. When you run the experiment, you are testing all three simultaneously. If any of them fails to behave as predicted, you have found a gap between your mental model and reality. That gap is the entire point.

The **steady state** is your baseline — the measurable behavior of the system under normal conditions that you expect to hold (or degrade within defined bounds) during the experiment. Steady state is not "the system is up." It is a set of concrete metrics: request latency at the 95th percentile, error rate, throughput, business-level indicators like orders per minute or search results returned. You must define steady state in terms you can measure in real time, because during the experiment you need to continuously compare current behavior against this baseline.

The **abort conditions** define when you stop the experiment immediately because the impact has exceeded what you are willing to tolerate. This is not optional. An abort condition might be: "If the overall error rate exceeds 5% for more than 30 seconds, terminate the experiment and restore normal conditions." Without predefined abort conditions, you are one unexpected cascade away from turning a controlled experiment into an uncontrolled outage. The mechanism for aborting must be tested independently — an abort switch that itself depends on the system you are breaking is not an abort switch.

## What Steady State Actually Requires

Defining steady state sounds straightforward until you try to do it. The difficulty is that most systems do not have a single stable baseline — they have patterns that vary by time of day, day of week, and season. Your order volume at 3 AM on a Tuesday looks nothing like your order volume at noon on Black Friday. A steady-state definition that works for one context will produce false positives or false negatives in another.

This reveals a hard prerequisite: **you cannot practice chaos engineering without mature observability**. If you do not already have instrumented services emitting structured metrics, distributed traces that show request flow across service boundaries, and dashboards that represent the real health of your system in business terms, then chaos engineering will not help you. You will inject a failure, look at your metrics, and not know whether what you are seeing is the effect of the experiment or normal variance. Chaos engineering does not replace observability. It consumes it.

In practice, steady-state definition often starts with your SLIs (service level indicators). If you already track request success rate, latency distribution, and throughput as part of your SLO practice, those same indicators become your steady-state metrics for chaos experiments. This is not a coincidence — chaos engineering and SLO-based reliability engineering share a foundation of measuring what matters to users, not what is convenient to instrument.

## The Taxonomy of Failure Injection

What you choose to break determines what you learn. Different categories of failure exercise different parts of your resilience architecture, and understanding the taxonomy helps you design experiments that target specific hypotheses rather than poking randomly.

**Infrastructure failures** — killing instances, terminating containers, rebooting hosts — test your redundancy and orchestration layer. These are the simplest to execute and the most commonly run, which is why they are also the least likely to reveal surprising behavior. If your system runs on Kubernetes with proper replica counts and health checks, killing a pod tells you that Kubernetes works. That was already well-established. Infrastructure failures become genuinely informative when you escalate: what happens when you lose an entire availability zone? What happens when the control plane itself degrades?

**Network failures** — injecting latency, dropping packets, partitioning services from each other — test your timeout configuration, retry logic, and circuit breaker behavior. These are far more revealing than instance kills because network failures create ambiguity. A killed instance is clearly gone; a service experiencing 3-second latency on every response is technically alive but functionally useless. This ambiguity is where most systems break. Your HTTP client has a 30-second default timeout. Your retry policy retries 3 times with no backoff. Your circuit breaker threshold is set to 50% error rate over 60 seconds. Under a latency injection of 3 seconds, none of those thresholds will trip — and meanwhile, your thread pool fills up, your connection pool exhausts, and the caller cascades into failure. Latency injection reveals more about your system's real behavior than almost any other category of experiment.

**Resource exhaustion** — filling disks, consuming memory, saturating CPU — tests how your system behaves under pressure rather than under absence. A dependency that is gone triggers your fallback logic. A dependency that is slow and consuming shared resources triggers a different failure mode entirely: resource contention that bleeds across isolation boundaries. If your payment service and your search service share a database connection pool, exhausting that pool from the payment side will kill search as well. This is exactly what bulkhead patterns are supposed to prevent, and resource exhaustion experiments are how you verify they actually do.

**Dependency failures** — making an external API return 500s, simulating DNS resolution failures, returning malformed responses — test your integration resilience. These are particularly valuable because they exercise code paths that are almost never tested in development. Most integration tests mock the happy path and maybe a clean error. They do not simulate a third-party API that returns a 200 status code with a completely malformed JSON body, or one that hangs for 45 seconds before returning a TCP reset.

## Blast Radius as an Engineering Problem

The Level 1 post introduced blast radius as a concept — start small, expand gradually. The mechanics of how you actually constrain and control blast radius are worth understanding because they impose real architectural requirements.

The most common approach is **traffic-based scoping**: apply the failure condition only to a percentage of requests or a subset of users. This requires your failure injection mechanism to be aware of your traffic routing. If you are injecting latency at the network level (using something like `tc` on Linux or a service mesh fault injection rule), you need the ability to scope that injection to specific routes, specific source services, or specific header values. A service mesh like Istio or Linkerd makes this straightforward — you can apply fault injection rules to specific virtual services with match conditions. Without a service mesh, you are either injecting application-level faults (which requires code changes or middleware) or injecting infrastructure-level faults that affect all traffic indiscriminately.

The **kill switch** — the mechanism to immediately halt an experiment — deserves its own engineering attention. A kill switch that requires someone to SSH into a box and run a script is not fast enough. A kill switch that relies on the same deployment pipeline you are testing is not independent enough. In practice, kill switches are implemented as feature flags with a separate control plane, or as service mesh rules that can be reverted with a single API call. The latency between "decide to abort" and "experiment is actually stopped" is itself a metric you should measure and optimize.

**Monitoring during the experiment** is not the same as your regular monitoring. Your regular dashboards are designed to show trends over minutes or hours. During a chaos experiment, you need to see the effect in seconds. This often means purpose-built dashboards or real-time streaming views of the specific metrics in your steady-state definition, refreshing at a cadence that lets you detect deviation and trigger abort conditions before the blast radius expands beyond your tolerance.

## Game Days and the Path to Continuous Chaos

There is a maturity progression in how organizations practice chaos engineering, and understanding where you are on it prevents you from either underinvesting or overreaching.

**Manual experiments** are where everyone starts. An engineer injects a specific failure, watches dashboards, and manually evaluates whether the hypothesis held. This is labor-intensive, infrequent, and perfectly appropriate for a team that is just beginning. The value of a manual experiment is not just in the system behavior it reveals — it is in forcing the team to articulate a hypothesis and define steady state, which are cognitive exercises that improve system understanding even if the experiment itself is uneventful.

**Game days** are scheduled events where the team runs multiple chaos experiments together, often with broader scope — simulating a regional failover, for example, or testing the response to a simulated data breach. Game days add a human dimension: they test not just the system's automated responses but the team's ability to detect, diagnose, and respond to failures. A circuit breaker that opens correctly is worthless if no one notices the alert it generates. Game days often reveal that the runbooks are outdated, the escalation paths are wrong, or the person who "knows how to do this" is on vacation.

**Automated continuous chaos** is the end state — experiments that run on a schedule or are triggered by deployment events, with automated steady-state verification and automated abort conditions. Tools like Gremlin, Litmus, or Chaos Mesh (for Kubernetes environments) enable this, but the tooling is the easy part. The hard part is having enough confidence in your abort conditions and blast radius controls to let experiments run without a human watching. Most teams that reach this stage did so incrementally over months or years, not by adopting a platform and flipping it on.

## Where Chaos Engineering Breaks Down

**The political problem is harder than the technical problem.** Running experiments that might cause user-visible impact requires organizational trust — trust that leadership understands the value, trust that the team will not be blamed if an experiment goes wrong, trust that the short-term cost of a controlled experiment is worth the long-term confidence it produces. Teams that skip the organizational buy-in and run experiments quietly will have their program killed the first time an experiment causes an unexpected page.

**Passing experiments are not proof of resilience.** An experiment that confirms your hypothesis tells you that one specific failure mode is handled. It tells you nothing about the failure modes you did not test. And the failures that take down production systems are overwhelmingly the ones no one anticipated — the compound failures, the correlated failures, the failures that only manifest under specific load conditions. Chaos engineering reduces the space of unknown failure modes; it does not eliminate it. Teams that run a few experiments and declare their system "chaos-tested" have replaced one form of false confidence with another.

**Experiments in staging are not experiments in production.** Staging environments differ from production in ways that matter: traffic volume, data distribution, infrastructure configuration, the number and variety of dependent services. A chaos experiment in staging tells you how your system behaves in staging. Production chaos engineering — where the real value lives — requires the blast radius controls, kill switches, and organizational maturity discussed above. Teams that are not ready for production chaos should acknowledge that rather than pretending staging results generalize.

**The cost of a chaos program is ongoing.** Experiments must be maintained as the system evolves. A hypothesis about how a service handles a database failure becomes invalid when the service adds a caching layer, changes its connection pooling strategy, or migrates to a different database. Stale experiments produce stale confidence. The experiment suite needs to evolve with the architecture, which means someone needs to own it continuously.

## The Mental Model

Chaos engineering is not a tool, a product, or a practice you adopt by injecting failures. It is a discipline of forming specific, falsifiable hypotheses about how your system behaves under failure, and then testing those hypotheses against reality. The failure injection is the easy part. The hard part is knowing what to predict, knowing how to measure whether your prediction held, and having the organizational maturity to act on what you learn.

The core insight is this: the value of a chaos experiment is proportional to the specificity of the hypothesis. "The system should handle this" teaches you nothing. "This specific metric should remain within this specific bound while this specific failure is active" teaches you exactly where your understanding is correct and where it is wrong. Every experiment that produces a surprise — a metric that moved when you expected it to hold steady, an alert that never fired, a fallback that returned errors instead of cached data — is an experiment that prevented a future outage.

## Key Takeaways

- A chaos experiment without a specific, falsifiable hypothesis is just an unplanned outage with extra steps — the hypothesis is what makes it an experiment.
- Steady state must be defined in terms of measurable metrics you can observe in real time; "the system is up" is not a steady-state definition.
- Chaos engineering is impossible without mature observability — if you cannot measure your system's behavior precisely, you cannot detect whether an experiment changed it.
- Latency injection reveals more about real system resilience than instance termination, because latency creates ambiguity that exposes misconfigured timeouts, missing circuit breakers, and connection pool exhaustion.
- Abort conditions and kill switches are safety-critical infrastructure that must be tested independently and must not depend on the systems being experimented on.
- Passing a chaos experiment proves that one specific failure mode is handled — it does not prove general resilience, and treating it as such replaces one form of false confidence with another.
- The organizational and political prerequisites for chaos engineering — leadership buy-in, blameless culture, tolerance for controlled risk — are harder to establish than the technical prerequisites and more likely to be the bottleneck.
- Chaos experiments are not write-once artifacts; they must evolve with the system architecture or they produce stale confidence that is worse than no confidence at all.

[← Back to Home]({{ "/" | relative_url }})
