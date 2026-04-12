---
layout: post
title: "3.1.6 Alerting Philosophy: Symptoms Over Causes, and the Cost of Alert Fatigue"
author: "Glenn Lum"
date:   2026-03-20 11:00:00 +0800
categories: journal
image: tier_3.jpg
tags: [Tier 3, Cross-Cutting Disciplines, Depth]
---

Most teams don't have an alerting problem. They have a classification problem they've never examined. They've instrumented dozens of system internals — CPU usage, memory pressure, disk I/O, thread pool sizes, queue depths — set thresholds on each one, and wired every threshold breach to a page. The system dutifully fires alerts. Engineers dutifully investigate. Most of the time, nothing is actually wrong — users are unaffected, the spike was transient, the system self-corrected. The engineer marks the alert as resolved and goes back to what they were doing. This cycle repeats hundreds of times. And then one night, a real outage begins, the pager fires, and the on-call engineer glances at their phone, assumes it's another false alarm, and rolls over. The alerting system didn't fail. The engineer didn't fail. The *design* of the alerting system made this outcome inevitable.

Understanding why requires looking at the actual mechanics: what makes symptom-based alerting structurally different from cause-based alerting, how alert fatigue develops as a learned behavior, and what a well-designed alerting system actually computes.

## The Asymmetry Between Causes and Symptoms

The fundamental argument for symptom-based alerting is not a preference. It is a structural property of complex systems.

**Symptoms are finite and stable.** For any given service, the ways users experience failure are constrained: requests return errors, requests take too long, requests return wrong data. These categories don't change when you refactor your infrastructure, swap databases, or add a new dependency. The user-visible failure modes of your checkout service are roughly the same whether it runs on bare metal or Kubernetes.

**Causes are infinite and unpredictable.** A service can fail because of a memory leak, a connection pool exhaustion, a kernel bug, a misconfigured load balancer, a slow downstream dependency, a poison-pill message in a queue, a clock skew between nodes, a certificate expiration, a DNS resolution failure, or a cascading retry storm triggered by a deploy two services away. You cannot enumerate all the causes in advance. Every cause-based alert you write covers a failure mode you've already imagined. The outage that actually takes you down is usually one you haven't.

This creates an asymmetry that no amount of alert tuning can fix. A symptom-based alert on "error rate > 1% for 5 minutes" catches *every* cause that produces user-facing errors, including causes you've never seen before. A cause-based alert on "CPU > 90%" catches only the subset of problems that manifest as high CPU, and it also fires for the many situations where high CPU is completely benign — a batch job running on schedule, a JVM garbage collection cycle, a burst of legitimate traffic.

Consider a concrete scenario. Your payment service starts returning HTTP 500s to 3% of requests. The root cause is that a downstream fraud-detection service deployed a change that causes it to timeout on certain request patterns. If you have a symptom-based alert on payment service error rate, you are paged immediately. If you are relying on cause-based alerts, you need to have predicted this specific failure mode in advance and built an alert for it. You probably didn't, because the failure is in a dependency's behavior, not in any of your own system's internal metrics. Your CPU is fine. Your memory is fine. Your connection pools are fine. Your database is fine. You are just returning errors.

## Every Alert Is a Classifier

It helps to think about each alert rule as a binary classifier. It makes a decision every evaluation cycle: fire or don't fire. Like any classifier, it has four outcomes: true positives (alert fires, real problem exists), false positives (alert fires, no real problem), true negatives (alert doesn't fire, nothing is wrong), and false negatives (alert doesn't fire, but something is actually wrong).

The quality of an alerting system depends on two properties: **precision** (what fraction of fired alerts correspond to real problems) and **recall** (what fraction of real problems generate an alert). Cause-based alerts tend to have poor precision, because many causes occur without producing user-visible problems. CPU spikes, memory pressure, elevated disk I/O — these are often transient, self-correcting, or simply normal operating behavior under load. A cause-based alert fires whenever the metric crosses a threshold, regardless of whether any user is affected.

This matters because of the **base rate problem**. If 90% of CPU spikes are benign, then even a perfectly calibrated CPU threshold will page you nine times for every one time the spike actually matters. The on-call engineer doesn't experience "this alert has 10% precision." They experience "this alert is almost always wrong." The rational behavioral response to an alert that is almost always wrong is to stop treating it as urgent.

Symptom-based alerts are not immune to false positives, but they have a structural advantage: they are measuring the thing you actually care about. An alert that says "5% of user requests are failing" can be wrong (a measurement artifact, a monitoring pipeline delay), but it cannot be *irrelevant*. The base rate of "user-facing error rate breaches threshold and it doesn't matter" is much lower than the base rate of "CPU crosses 90% and it doesn't matter."

## The Mechanics of Alert Fatigue

Alert fatigue is not merely "too many alerts." It is a specific learned behavior that develops through a well-understood psychological mechanism, and once it takes hold, it is remarkably difficult to reverse.

Every time an alert fires and the engineer investigates and finds nothing actionable, a small amount of trust in the alerting system is destroyed. Every time an alert fires and the engineer finds a real problem, trust is reinforced. The problem is that this process is **asymmetric**: trust erodes faster than it builds. One week of false alarms does more damage than one month of accurate alerts can repair. This is not a character flaw in engineers. It is the same cognitive mechanism that makes people stop listening to car alarms.

The behavioral progression is predictable. First, the engineer starts taking longer to respond to pages, because experience has taught them the alert is probably not real. Then they start glancing at the alert details and making a snap judgment about whether to investigate, based on pattern recognition rather than actual diagnosis. Then they start silencing certain alerts entirely. Then new engineers join the on-call rotation and are told by their peers which alerts to ignore. At this point, the alerting system is not just failing — it is *actively harmful*, because it provides the organizational illusion of monitoring coverage while delivering none.

The critical insight is that **alert fatigue is a property of the system, not the individual.** You cannot fix it by hiring more disciplined engineers or by writing better runbooks. If the alert system has a high false positive rate, the humans in the loop will adapt to that rate. The only fix is to change the signal-to-noise ratio of the alerts themselves.

## Burn Rate: How Symptom-Based Alerting Actually Works

Naive symptom-based alerting — "page me when the error rate exceeds X%" — is better than cause-based alerting but still has problems. A brief spike that lasts 30 seconds and affects a handful of requests probably isn't worth a page. A slow elevation in error rate from 0.1% to 0.5% over several days might be eating through your error budget without ever crossing a threshold that feels acute.

The mechanism that solves both problems is **burn rate alerting**, tied directly to your SLO. The concept: instead of alerting on the raw metric value, you alert on the *rate at which you are consuming your error budget*.

Here is how the math works. Suppose your SLO is 99.9% availability over a 30-day window. That gives you an error budget of 0.1% — roughly 43 minutes of total downtime, or equivalently, 0.1% of requests can fail. A **burn rate of 1** means you are consuming your error budget at exactly the sustainable pace — you will use 100% of it by the end of the 30-day window. A burn rate of 14 means you are consuming budget 14 times faster than sustainable — at this rate, you will exhaust your entire monthly budget in about two days.

A well-designed alerting system uses **multiple burn rates with multiple time windows**. The fast-burn alert catches acute incidents: a burn rate of 14x sustained over 5 minutes, confirmed by a 1-hour window. This fires for sudden outages — your service starts returning 50% errors and you need to act now. The slow-burn alert catches chronic degradation: a burn rate of 3x sustained over a 6-hour window. This catches the scenario where your error rate has crept up slightly, not enough to feel urgent in any given minute, but enough to exhaust your error budget well before the end of the month.

In practice, a burn rate alerting rule looks something like this:

```
# Fast burn: exhausts 30-day budget in ~2 days
alert: HighErrorBudgetBurn_Fast
expr: |
  (1 - (rate(http_requests_total{code!~"5.."}[5m]) 
  / rate(http_requests_total[5m]))) > (14 * 0.001)
for: 2m
```

```
# Slow burn: exhausts 30-day budget in ~10 days
alert: HighErrorBudgetBurn_Slow
expr: |
  (1 - (rate(http_requests_total{code!~"5.."}[6h]) 
  / rate(http_requests_total[6h]))) > (3 * 0.001)
for: 30m
```

The fast-burn alert pages the on-call engineer. The slow-burn alert creates a ticket. This distinction — **page for acute, ticket for chronic** — is itself a critical design choice. Not every problem that needs fixing needs to wake someone up.

## Where Cause-Based Alerts Belong

Symptom-based alerting does not make cause-based monitoring irrelevant. It changes its role. Causes become your **diagnostic layer**, not your **notification layer**.

When a symptom-based alert fires — error rate is elevated — the engineer needs to diagnose *why*. This is where dashboards showing CPU, memory, connection pools, queue depths, and downstream latency become essential. They are investigative tools, not alerting triggers.

There is one legitimate exception: **predictive resource exhaustion**. A disk filling up at a rate that will hit 100% in four hours is not yet causing user-visible symptoms, but it will. A TLS certificate expiring in 72 hours is not yet causing errors, but it will. These are not truly "cause" alerts — they are alerts on *imminent future symptoms*. The distinction matters: they are justified not because they represent internal state you should care about, but because they represent inevitable user impact you can still prevent. Even these should typically generate tickets, not pages, unless the time-to-impact is measured in minutes.

## Tradeoffs and Failure Modes

**Detection latency.** Symptom-based alerting is structurally slower than cause-based alerting. A cause-based alert on connection pool exhaustion fires the moment connections are exhausted. A symptom-based alert fires only after that exhaustion has produced enough errors, for long enough, to cross your threshold. If your burn-rate window is 5 minutes, you will not be paged until users have been experiencing errors for 5 minutes. For most services, this tradeoff is correct — the cost of five minutes of degradation is far lower than the cost of an on-call rotation that doesn't trust its pager. For systems with extremely tight latency requirements (payment processing, real-time bidding), you may need to accept some well-chosen cause-based alerts alongside your symptom-based ones, understanding that you are trading higher noise for faster detection.

**The debugging gap.** A symptom-based alert tells you *that* users are affected but not *why*. This is a feature, not a bug — it separates detection from diagnosis — but it requires investment. If your dashboards, logs, and traces are not good enough to support rapid diagnosis once you've been paged, you will feel pressure to add cause-based alerts "just so we know what's wrong faster." This is a trap. The correct response is to improve your observability tooling, not to degrade your alerting system.

**The quiet system.** Teams migrating from cause-based to symptom-based alerting often experience anxiety when their pagers go quiet. They were accustomed to receiving several alerts per week — each one felt like proof that the monitoring system was working. A well-tuned symptom-based system might page once a month. This silence feels like something is broken. It isn't. But the psychological transition is real, and teams that don't expect it sometimes regress by adding cause-based alerts back "just in case."

**Organizational contagion.** Alert fatigue is not contained to the individual who experiences it. It propagates through on-call rotations via institutional knowledge. Senior engineers tell junior engineers which alerts are noise. Runbooks accumulate notes like "this usually resolves on its own — wait 10 minutes before investigating." Dashboards are built that filter out entire categories of alerts. Once this culture takes root, restoring trust in the alerting system requires not just fixing the alerts themselves but actively unwinding the institutional muscle memory built around ignoring them. This is significantly harder than getting it right the first time.

## The Mental Model

An alerting system is a communication channel between your infrastructure and your engineers. Like any communication channel, it has a credibility budget. Every false positive spends credibility. Every true positive that leads to meaningful action earns it back — but slower than it was spent. The system fails not when it stops sending signals, but when the humans on the other end stop believing them.

Your alerting layer should be a thin, high-trust surface that answers one question: *are users being harmed right now, or are they about to be?* Everything else — what's causing it, which component is misbehaving, what the internal metrics look like — belongs in your diagnostic layer, accessible on demand, not pushed to your pager.

The shift from cause-based to symptom-based alerting is not a tuning change. It is a structural decision about what your alerting system is *for*. It is for protecting users, not for narrating system internals.

## Key Takeaways

- **Symptoms are finite; causes are infinite.** A symptom-based alert on error rate or latency catches every failure mode that affects users, including ones you haven't imagined. A cause-based alert only catches the specific failure you predicted.

- **Every alert is a binary classifier, and precision matters more than coverage.** A pager that fires ten times with nine false positives doesn't have a "tuning" problem — it has a structural problem that trains engineers to ignore it.

- **Alert fatigue is a system property, not an individual discipline problem.** You cannot solve it with better runbooks or more diligent engineers. You solve it by changing the false positive rate of the alerts themselves.

- **Burn rate alerting is the mechanical link between SLOs and your pager.** Instead of alerting on raw metric thresholds, alert on the rate at which you are consuming your error budget, using fast-burn windows for acute incidents and slow-burn windows for chronic degradation.

- **Page for acute, ticket for chronic.** Not every problem that needs attention needs to wake someone up. Fast budget burn gets a page. Slow budget burn gets a ticket. Predictive resource exhaustion (disk, certificates) gets a ticket unless impact is imminent.

- **Cause-based metrics are diagnostic tools, not alerting triggers.** CPU, memory, connection pools, and queue depths are essential for investigating *why* an alert fired. They should live on dashboards and in runbooks, not on your pager.

- **The silence of a well-tuned alerting system is a feature, not a sign of failure.** Teams accustomed to noisy pagers often mistake quiet for broken. A system that pages once a month and is right every time is vastly superior to one that pages daily and is wrong 90% of the time.

- **Alert fatigue propagates culturally and is harder to reverse than to prevent.** Once an on-call rotation develops the institutional habit of ignoring pages, restoring trust requires changing both the alerts and the organizational muscle memory built around dismissing them.

[← Back to Home]({{ "/" | relative_url }})
