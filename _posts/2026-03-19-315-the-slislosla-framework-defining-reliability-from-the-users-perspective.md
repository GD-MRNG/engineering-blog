---
layout: post
title: "3.1.5 The SLI/SLO/SLA Framework: Defining Reliability from the User's Perspective"
author: "Glenn Lum"
date:   2026-03-19 11:00:00 +0800
categories: journal
image: tier_3.jpg
tags: [Tier 3, Cross-Cutting Disciplines, Depth]
---

Most teams that adopt SLOs get the definitions right and the mechanics wrong. They can tell you that an SLI is a measurement of user experience, that an SLO is a target for that measurement, and that the error budget is what falls out of the gap between the target and perfection. Then they set a 99.9% availability target because it sounds reasonable, measure it against HTTP status codes at the load balancer, and wonder why the framework never actually changes how they make decisions. The definitions are not the hard part. The hard part is the chain of specific, consequential choices that connect a percentage on a dashboard to an engineering team's behavior — and getting any single link in that chain wrong renders the entire framework inert.

## The SLI Is a Specification, Not a Metric

The most common mistake is treating the SLI as a metric you pick from your existing monitoring. It is not. An SLI is a **specification** of what "good" means for a user interaction, which you then figure out how to measure. The distinction matters because it changes the order of operations: you do not start by looking at what you can measure and picking something. You start by asking what the user experiences, then work backward to find the closest measurable proxy.

Consider a checkout service. The user's experience of "good" is: I clicked "Place Order," the order was accepted, and I got confirmation within a few seconds. The SLI specification for this might be: the proportion of checkout requests that return a success response within 2000ms. That is not a metric yet. It is a statement about what you intend to measure and the boundary between "good" and "not good."

The **SLI implementation** is where you decide how to actually capture that measurement. You have options, and they are not equivalent. You could measure at the load balancer, counting responses with 2xx status codes returned within 2000ms. You could measure inside the application, logging whether the business logic completed successfully. You could measure from the client, capturing whether the user's browser actually received and rendered the confirmation. Each of these will produce a different number for the same SLI specification because each sits at a different point in the stack and captures a different subset of failure modes.

Measuring at the load balancer misses failures the load balancer cannot see: a 200 response that contains an error message in the body, a response that technically succeeded but wrote corrupt data to the database, a connection that the client never received because of a network issue downstream of the balancer. Measuring from the client captures the most complete picture of user experience but introduces noise from client-side conditions you do not control and creates data collection challenges. There is no universally correct measurement point. The decision depends on which failure modes matter most for the specific interaction, and on what instrumentation you can realistically maintain.

This is why the specification matters as a separate artifact. It defines the intent. The implementation is a pragmatic approximation of that intent, and you should be explicit about the gap between them.

## How Error Budgets Actually Work in Practice

The Level 1 framing of error budgets — "if your SLO is 99.9%, then 0.1% of requests may fail" — is correct but incomplete. The critical missing piece is the **time window**, because an error budget is not a rate. It is a finite quantity that depletes over a specific period.

A 99.9% SLO measured over a rolling 30-day window means: over the last 30 days, at least 99.9% of eligible events must have been "good" according to the SLI. If your service handles 10 million requests per month, your error budget is 10,000 bad requests. That is a concrete number. You can spend it, and you can run out.

The choice between a **rolling window** and a **calendar-aligned window** is not cosmetic. A rolling 30-day window is continuously evaluated; every minute, the oldest data falls off and the newest data enters. This means that a bad incident gradually "heals" as it ages out of the window, and there is no artificial reset point. A calendar-aligned window (say, a calendar month) resets at the start of each month, which means a team that burned 80% of its error budget on January 28th gets a full budget back on February 1st. Calendar windows are easier for humans to reason about and align naturally with business planning cycles. Rolling windows are more mathematically honest but can create a demoralizing situation where a single bad incident haunts the budget for its entire duration.

Most organizations start with calendar-aligned windows because they are simpler to explain to stakeholders and easier to use in error budget policies. The tradeoff is real, but the simplicity usually wins, especially when you are trying to get organizational buy-in for the framework itself.

### Burn Rate: The Mechanic That Makes SLOs Operational

Knowing the remaining error budget is useful for planning. It is nearly useless for alerting. If your SLO is 99.9% over 30 days, and you alert when the budget hits zero, you are alerting roughly 30 days too late to do anything about it. If you alert on any instantaneous dip below 99.9%, you will fire alerts constantly for brief transient errors that will never threaten the monthly budget.

**Burn rate** is the concept that bridges this gap. A burn rate of 1x means you are consuming error budget at exactly the rate that would exhaust it at the end of the window. A burn rate of 10x means you are consuming budget ten times faster than sustainable — at this rate, the budget will be gone in 3 days instead of 30. A burn rate of 0 means everything is healthy.

The insight is that you alert on burn rate, not on budget remaining and not on instantaneous error rate. A 10x burn rate sustained over an hour is an urgent page: something is actively broken and will exhaust your budget fast. A 2x burn rate sustained over six hours is a slower-moving concern: something is degraded, and you need to investigate before it becomes a crisis, but it does not need to wake someone at 3am.

Google's approach, documented in the SRE Workbook, uses **multi-window, multi-burn-rate alerts**. The structure works like this: you define a fast-burn alert that looks at a short window (say, the last 5 minutes against a 1-hour lookback) with a high burn rate threshold (say, 14x), and a slow-burn alert that looks at a longer window (say, the last 6 hours against a 3-day lookback) with a lower burn rate threshold (say, 2x). Each alert condition requires the burn rate to exceed the threshold in *both* the short window and the long window simultaneously. The short window confirms the problem is happening *right now*, not just residually from an earlier incident. The long window confirms the problem is sustained enough to matter.

This is where the framework becomes genuinely powerful, and it is the mechanic most teams never implement. Without burn-rate alerting, your SLO is a reporting metric — something you look at in a weekly review. With burn-rate alerting, your SLO is an operational tool that drives real-time incident response.

### The Concrete Math

If your 30-day error budget is 10,000 bad requests and your service handles roughly 14,000 requests per hour:

At a **1x burn rate**, you lose about 14 bad requests per hour (10,000 / 720 hours). This is sustainable for the full window.

At a **10x burn rate**, you lose 140 bad requests per hour. Your budget is exhausted in 72 hours. This warrants a ticket and investigation during business hours.

At a **100x burn rate**, you lose 1,400 bad requests per hour. Your budget is gone in about 7 hours. This is a page.

These numbers make the abstraction concrete. A burn rate is not a fancy metric — it is a direct translation of "how quickly is the user experience degrading, relative to what we committed to tolerate?"

## Choosing the SLO Target: Where Engineering Meets Economics

The target number — 99.9% vs 99.95% vs 99.99% — is not a reliability aspiration. It is an engineering and business constraint, and the relationship between the target and the cost of meeting it is profoundly non-linear.

Going from 99% to 99.9% might require redundancy: a second replica, a failover database, health checks. Going from 99.9% to 99.99% might require active-active multi-region deployment, sophisticated load shedding, graceful degradation paths for every downstream dependency, and extensive chaos engineering. Going from 99.99% to 99.999% might require custom infrastructure, dedicated on-call rotations, and architectural constraints that permeate every design decision.

Each additional nine roughly multiplies the engineering investment required. And the error budget shrinks by an order of magnitude: a 99.99% SLO over 30 days on 10 million requests gives you 1,000 bad requests. A 99.999% SLO gives you 100. At that budget, a single transient network hiccup can consume a meaningful fraction of your allowance.

The correct SLO target is not "as high as possible." It is **the lowest target your users will tolerate**, because every fraction of a percent above that is engineering cost you are paying without corresponding user value. This is counterintuitive. It means the SLO-setting process must start with understanding user expectations and business requirements, not with measuring your current reliability and rounding up.

A practical heuristic: your SLO should be slightly more strict than any SLA you offer externally (so that you have a buffer before contractual consequences kick in) and slightly less strict than what your system actually achieves on a good month (so that the error budget is real and usable, not perpetually exhausted). If your system achieves 99.95% and your SLO is 99.95%, you have no error budget. You cannot deploy anything without risking a violation.

## Where the Framework Breaks

### SLO Theater

The most pervasive failure mode is what you might call **SLO theater**: the team defines SLIs and SLOs, puts them on a dashboard, and then nothing changes. No one looks at the error budget. No deployment decisions are tied to it. No alerts are configured against burn rates. The SLO exists in a document and on a Grafana panel, and it has zero operational impact.

This happens when the SLO is adopted as a reporting practice rather than an operational framework. The SLO is meaningless unless there is an **error budget policy** — an explicit, agreed-upon set of actions that trigger when the budget is at specific thresholds. At 50% consumed, maybe you review recent deploys and recent changes. At 80% consumed, maybe you freeze non-critical deployments. At 100% consumed, maybe all engineering effort shifts to reliability work until the budget recovers. Without these policies, the SLO is decoration.

### Gaming the SLI

When the SLI implementation diverges too far from the SLI specification, teams can "pass" their SLO while users are suffering. If your SLI counts only HTTP 5xx responses as failures, a service that returns `200 OK` with an error message in the JSON body will look healthy by the SLI while users see failures. If your latency SLI is measured at the server but users experience an additional 500ms of network latency, the SLI will undercount slow experiences. This is usually not deliberate gaming — it is a natural consequence of measurement convenience trumping measurement accuracy. The fix is to periodically audit your SLI implementations against actual user experience data (support tickets, client-side metrics, synthetic monitors) and adjust.

### Dependency Chains and SLO Math

If your service depends on three downstream services, each with a 99.9% SLO, your theoretical upper-bound availability is not 99.9%. It is approximately 99.7% (0.999 × 0.999 × 0.999), assuming independent failures. In practice, failures are often correlated (a network partition affects all downstream services simultaneously), so the actual reliability may be better or worse than this calculation suggests. But the directional point holds: **you cannot offer an SLO that is more aggressive than what your dependencies support**, unless you have built resilience mechanisms (retries, fallbacks, caching, graceful degradation) that decouple your availability from theirs. Setting an SLO without understanding the dependency chain is setting a target you have no mechanical basis to meet.

## The Mental Model

The SLI/SLO/error budget framework is not a monitoring practice. It is a **decision-making framework** that uses measurement to automate the negotiation between reliability and velocity. The SLI defines what "good" means. The SLO defines how much "not good" is acceptable. The error budget converts that tolerance into a finite, spendable resource. Burn rate makes that resource visible in real time. And the error budget policy converts budget state into team behavior.

Every link in that chain must be present. An SLI without an SLO is a metric without a target. An SLO without an error budget is a target without consequences. An error budget without a policy is a number without teeth. And a policy without burn-rate alerting is a rule no one knows when to enforce. The framework's power is not in any single component — it is in the closed loop from measurement to decision to action.

## Key Takeaways

- An SLI is a specification of what "good" means for a user interaction, not a metric you pick from existing monitoring — you define the spec first, then find the best available measurement.

- Error budgets are finite quantities over specific time windows, not rates — a 99.9% SLO over 30 days on 10 million requests means exactly 10,000 bad requests are allowed.

- Burn rate is the mechanic that makes SLOs operational in real time: it measures how fast you are consuming your error budget relative to sustainable consumption, and it is what your alerts should be based on.

- The cost of reliability is non-linear — each additional nine roughly multiplies the required engineering investment, so the correct SLO is the lowest target your users will tolerate, not the highest number your system can achieve.

- Without an error budget policy that defines concrete actions at specific budget thresholds, the SLO framework has no operational impact and becomes reporting theater.

- Your service's achievable SLO is bounded by the SLOs of your dependencies unless you have built explicit resilience mechanisms (retries, fallbacks, degradation) that decouple your availability from theirs.

- The SLI measurement point matters: server-side, load-balancer, and client-side measurements will produce different numbers for the same SLI specification, and each captures a different subset of failure modes.

- The complete framework is a closed loop — SLI to SLO to error budget to burn-rate alert to error budget policy to team action — and removing any link breaks the loop.

[← Back to Home]({{ "/" | relative_url }})
