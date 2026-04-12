---
layout: post
title: "3.3.1 SLIs, SLOs, and Error Budgets: The Language of Reliability"
author: "Glenn Lum"
date:   2026-03-28 11:00:00 +0800
categories: journal
image: tier_3.jpg
tags: [Tier 3, Cross-Cutting Disciplines, Depth]
---

Most teams that adopt SLOs treat them as monitoring thresholds — a number goes red when reliability drops below a target. This misses the point entirely. An SLO that only triggers an alert is just a health check with extra steps. The actual value of the SLI/SLO/error budget framework is not that it measures reliability. You already have metrics for that. The value is that it converts reliability from a feeling into a *decision-making input* — a finite resource you can spend, track, and make policy around. The difference between "we should probably slow down on deployments" and "we have consumed 80% of our error budget with nine days remaining in the window" is the difference between a subjective argument and a quantified constraint. Understanding the mechanics of how SLIs, SLOs, and error budgets actually work — how they are defined, where they are measured, how they interact, and where they fail — is what determines whether this framework produces real engineering decisions or just produces dashboards.

## SLIs: The Ratio That Defines "Good"

An SLI is not a metric. It is a metric *expressed as a ratio*. Specifically, it is the ratio of good events to total events, measured over some time window. This distinction matters because raw metrics — request count, error count, latency — do not by themselves tell you whether your users are having a good experience. An SLI answers a specific question: of all the interactions users had with this system, what fraction were good?

**The definition of "good" is the entire design decision.** For an availability SLI, a good event might be any HTTP response that is not a 5xx. For a latency SLI, a good event might be any request that completes in under 300 milliseconds. For a correctness SLI, a good event might be any response where the returned data matches the source of truth. For a freshness SLI, a good event might be any read that returns data no more than one minute old. Each of these is a different SLI, with a different numerator, applied to the same denominator of total events.

### Where You Measure Changes What You Measure

The measurement point of your SLI is not a minor implementation detail — it fundamentally determines what your SLI captures. Consider an availability SLI for an API service. You can measure it at the load balancer, at the application server, or at the client.

If you measure at the **load balancer**, you capture failures from your application but miss failures caused by the load balancer itself, by network issues between the load balancer and the client, or by DNS resolution failures. If you measure at the **application server**, you miss everything upstream of it. If you measure at the **client** — through real-user monitoring or synthetic probes — you capture the full path that your user actually experiences, including network latency, CDN failures, and DNS problems. Client-side measurement is the most accurate representation of user experience but is also the noisiest, hardest to instrument, and most expensive to operate.

The general principle: **measure as close to the user as you can afford to maintain reliably.** For most backend services, measurement at the load balancer or API gateway is the practical sweet spot — it captures the vast majority of failures your users will see, and the data is clean and available in infrastructure you already control.

### Latency SLIs: Why Percentiles Are Non-Negotiable

Average latency is almost useless as an SLI. A service with 100ms average latency could be serving 95% of requests in 10ms and 5% in 1,900ms. The average looks fine. The experience for that 5% is catastrophic.

Latency SLIs use percentile thresholds: the fraction of requests faster than a given duration. A latency SLI might be defined as "the proportion of requests served in under 200ms" — and you would typically set separate SLOs for different percentiles. You might target 99% of requests under 200ms (your p99 latency SLO) and 99.9% under 800ms (your p999 SLO). The higher percentiles capture the tail latency that affects your worst-served users, who are often your most engaged users — the ones making the most requests.

The practical challenge is that latency distributions are almost always long-tailed, and the tail is where the interesting failures live: garbage collection pauses, cold cache misses, database lock contention, network retries. Your p50 tells you about the common case. Your p99 tells you about the failure modes.

## SLOs: The Threshold That Creates a Decision

An SLO is a target value for an SLI, applied over a specific time window. "99.9% of requests will return a non-5xx response over a rolling 30-day window." That sentence contains three components: the SLI definition (non-5xx responses), the target (99.9%), and the window (rolling 30 days). All three are load-bearing. Change any one of them and you change the operational behavior of the system.

### Why the Target Is Never 100%

This is well-trodden ground, but the *reason* matters for the mechanics that follow. A 100% SLO means zero tolerance for any failure, which means zero tolerance for any change — because any deployment, migration, or configuration change carries nonzero risk of causing a failure. A 100% target also means you are promising to be more reliable than any of your dependencies. If your cloud provider's compute SLA is 99.99%, your service cannot be 100% reliable unless you are multi-cloud with seamless failover, which introduces its own failure modes. The SLO target is the explicit, quantified answer to the question: *how much unreliability can our users tolerate before it materially harms their experience or our business?*

Deriving that number is not a pure engineering exercise. It requires understanding your users' actual tolerance — which is shaped by their alternatives, their expectations, and the criticality of the interaction. A payment processing API and an internal dashboard for viewing weekly reports have radically different user tolerance profiles, and their SLOs should reflect that.

### Rolling Windows vs. Calendar Windows

A **rolling window** (e.g., the trailing 30 days) means the error budget is continuously recalculated. A bad day that consumed significant budget three weeks ago will eventually "roll off" as time passes, naturally restoring budget. A **calendar window** (e.g., each calendar month) resets the budget at a fixed boundary — the first of the month, the start of the quarter.

The behavioral difference is significant. Calendar windows create a perverse incentive: if you've already blown your budget mid-month, there is no additional cost to further unreliability until the reset. Conversely, if you've been perfectly reliable for 28 days, you have a large unspent budget that vanishes in three days regardless. Rolling windows avoid both of these problems by making budget a continuous function. Most mature implementations use rolling windows.

## Error Budgets: The Currency of the Framework

The error budget is the gap between perfection and your SLO target, applied to your actual traffic volume. If your SLO is 99.9% availability over 30 days, your error budget is 0.1% of all requests in that window. If you serve 10 million requests per day, your 30-day error budget is 300,000 failed requests — or equivalently, roughly 43 minutes of total downtime.

This is not a monitoring number. This is an **allocation**. You are explicitly deciding that 0.1% unreliability is acceptable, and you are assigning that unreliability a concrete magnitude that everyone — product managers, engineers, leadership — can see and reason about.

### Burn Rate: The Speed of Consumption

The raw error budget remaining tells you how much budget is left. The **burn rate** tells you how fast you are consuming it, and this is the operationally useful signal.

A burn rate of 1x means you are consuming budget at exactly the rate that would exhaust it precisely at the end of the window. A burn rate of 10x means you will exhaust your 30-day budget in 3 days at the current rate. A burn rate of 0.5x means you are consuming budget slower than your allocation — you are "under budget."

Burn rate is what connects error budgets to alerting. Rather than alerting when the error rate exceeds a fixed threshold, you alert when the burn rate exceeds a multiple that implies the budget will be exhausted before the window ends. This is fundamentally different from threshold-based alerting because it is *contextual*: a 0.5% error rate that lasts for two minutes might be noise, but a 0.5% error rate that has persisted for six hours is a serious budget burn. Burn rate captures duration and magnitude together.

Practical implementations use **multi-window, multi-burn-rate alerts**. A fast burn (e.g., 14x over the last five minutes, confirmed by a 1-hour lookback) triggers a page — something is actively broken. A slow burn (e.g., 2x over the last six hours, confirmed by a 3-day lookback) triggers a ticket — something is degraded and needs investigation, but not at 3 AM. This structure dramatically reduces false positives compared to static error rate thresholds.

### When the Budget Runs Out

The error budget only has teeth if exhausting it triggers a concrete policy response. This is where the framework transitions from measurement to governance. Common policies when the error budget is exhausted include: freezing feature deployments until the budget recovers, redirecting engineering effort from feature work to reliability work, requiring all changes to go through additional review or canary stages, or escalating to leadership for a risk-acceptance decision.

The specific policy matters less than its existence and enforcement. An error budget with no exhaustion policy is just a metric. An error budget with an enforced exhaustion policy is a governance mechanism that automatically balances velocity and stability without requiring any individual to make a judgment call about whether "now is a good time to slow down."

## Where This Framework Breaks

### Measuring the Wrong Thing

The most common failure mode is SLIs that track system health rather than user experience. CPU utilization, memory pressure, queue depth — these are useful operational signals, but they are not SLIs. A service can be at 95% CPU and serving every request correctly in under 100ms. A service can be at 10% CPU and returning stale data to every user. If your SLIs are disconnected from what users actually experience, your SLOs will be green while your users are suffering, and your error budget will be meaningless.

### SLOs That Nobody Enforces

Many teams set SLOs, build dashboards, and then treat budget exhaustion as informational rather than prescriptive. When the budget runs out, nothing changes — deployments continue, priorities don't shift, and the SLO becomes a number that reflects past reliability but doesn't shape future behavior. This is the most common way the framework dies in practice. It requires organizational commitment to a policy, and that policy will, at some point, require telling a product team that their feature launch is delayed because the error budget is exhausted. If leadership overrides that decision every time, the framework is decoration.

### Goodhart's Law in Action

Once an SLI becomes a target, teams optimize for it — sometimes at the expense of the user experience it was supposed to represent. A team measured on availability SLI might add aggressive retries that keep the success ratio high but double the latency for failed-then-retried requests. A team measured on latency SLI might return fast, empty responses rather than waiting for slow backends to provide complete data. The SLI looks healthy. The user experience degrades. This is why mature implementations use multiple SLIs per service — availability *and* latency *and* correctness — to make it difficult to game one dimension without visibly degrading another.

### The Coverage Gap

SLOs only cover the interactions you instrument. If your SLI is defined at the API gateway, you have no coverage for failures that prevent requests from reaching the gateway — DNS outages, certificate expiration, network partitions between users and your edge. These are often the most impactful incidents (total outage, affecting all users) and the ones your SLO-based alerting is blind to. Synthetic monitoring — external probes that simulate real user interactions — fills this gap and should be considered a complement to, not a replacement for, event-based SLIs.

## The Mental Model

Think of the SLI/SLO/error budget system as a closed-loop control mechanism. The SLI is the sensor — it continuously measures the user-facing output of your system. The SLO is the setpoint — the threshold that defines acceptable. The error budget is the control signal — it translates the difference between actual and target into a quantified resource that drives action. When budget is ample, the system permits higher velocity: more deployments, more experiments, more risk. When budget is thin, the system constrains velocity: slower rollouts, more review, reliability-focused work. The output is not a dashboard. The output is an engineering decision — deploy or don't deploy, invest in features or invest in reliability — made against a quantified constraint rather than a subjective feeling.

What makes this framework powerful is not its precision — the specific numbers are always somewhat arbitrary. What makes it powerful is that it forces reliability to be *negotiated and explicit*. The moment you write down "99.9% over 30 days," you have committed to a definition of good enough, and every minute of downtime, every elevated error rate, every slow response is now countable against a finite budget that everyone in the organization can see. Reliability stops being the thing that one team argues about in incident reviews and becomes the quantified constraint that shapes how the whole organization ships software.

## Key Takeaways

- An SLI is not a metric — it is the ratio of good events to total events, where the definition of "good" is the design decision that determines whether the SLI actually reflects user experience.

- Where you measure your SLI (client, load balancer, application) determines what failures it can see; measure as close to the user as you can reliably maintain.

- Average latency conceals tail behavior; latency SLIs must use percentile thresholds (p99, p999) to capture the experience of your worst-served users.

- Rolling time windows are generally superior to calendar windows because they avoid the perverse incentive of budget resets and budget-expiration waste.

- Burn rate — not raw budget remaining — is the operationally useful signal, because it captures both the magnitude and duration of an issue and enables tiered alerting (page for fast burns, ticket for slow burns).

- An error budget without an enforced exhaustion policy is just a metric; the framework only produces decisions if exceeding the budget triggers concrete, pre-agreed consequences.

- Multiple SLIs per service (availability, latency, correctness) guard against Goodhart's Law — optimizing one dimension at the expense of others becomes visible.

- SLO-based alerting has a coverage gap for failures that prevent requests from reaching your instrumentation; synthetic monitoring from external vantage points is the necessary complement.

[← Back to Home]({{ "/" | relative_url }})
