---
layout: post
title: "3.1.1 Monitoring vs Observability: Known Unknowns vs Unknown Unknowns"
author: "Glenn Lum"
date:   2026-03-15 11:00:00 +0800
categories: journal
image: tier_3.jpg
tags: [Tier 3, Cross-Cutting Disciplines, Depth]
---

Most teams that say they've adopted observability have actually built better monitoring. They have more dashboards, more alerts, more metrics, fancier visualization — but the underlying data model is the same. When a novel failure mode hits production, they still find themselves staring at graphs that confirm something is wrong without revealing what. The distinction between monitoring and observability is not about tooling or vendor choice. It is about a fundamental difference in *when you decide what questions to ask* — and that difference has deep mechanical consequences for how you instrument, store, and query your system's output.

## The Epistemic Split: Write-Time vs Query-Time

Monitoring is built on a model where you decide what matters *before* something goes wrong. You choose your metrics, define your thresholds, build your dashboards. When an incident occurs, you look at the predefined views and check whether any of your anticipated failure modes are active. This works extraordinarily well for **known failure modes** — the database is down, disk is full, CPU is pegged, error rate has spiked. These are things that have happened before or that you can reasonably predict.

The problem is not that monitoring is bad at this. It is excellent at this. The problem is that production systems — especially distributed ones — fail in ways you did not predict. A specific combination of a deployment, a traffic pattern, a downstream dependency's changed behavior, and a particular customer's data shape produces a failure you've never seen. Your dashboards are green or ambiguously yellow. Your alerts haven't fired because the failure doesn't map to any threshold you set. You know something is broken because users are telling you, but your tooling cannot answer the question *why*.

Observability inverts the model. Instead of deciding at instrumentation time which questions matter, you emit rich, detailed records of what your system did, and you retain the ability to ask arbitrary questions about those records *after* the fact. The critical word is **arbitrary**. Not "any question from a predefined set." Any question, including ones you've never asked before, composed on the fly during an incident.

This is the known-unknowns vs unknown-unknowns distinction made mechanical. Monitoring handles known unknowns: you know the database *could* go down, you just don't know *when*, so you watch it. Observability handles unknown unknowns: you didn't know that requests from a specific region, using a specific API version, hitting a specific shard, during a specific traffic pattern would produce a latency spike — but you can discover it by slicing your data along those dimensions after the symptoms appear.

## Cardinality: The Constraint That Forces the Fork

The reason you can't just "make monitoring better" until it becomes observability is **cardinality** — the number of unique values a dimension can take. This is the mechanical constraint that makes the two approaches structurally different.

A metric like `http_request_duration` with labels for `method`, `status_code`, and `endpoint` has manageable cardinality. There are a handful of HTTP methods, a few dozen status codes, maybe a few hundred endpoints. The combinations are in the thousands. Your time-series database stores one series per unique label combination and pre-aggregates values into buckets. This is efficient and fast.

Now try adding `user_id` as a label. If you have a million users, you've just created a million time series *per endpoint per method per status code*. Your time-series database — Prometheus, InfluxDB, whatever — will fall over. This is not a scaling problem you solve with more hardware. Time-series databases are architecturally designed for low-to-moderate cardinality because they pre-aggregate and index on label combinations. High-cardinality dimensions break the data model.

But `user_id` is exactly the kind of dimension you need when debugging. "Which users are affected?" is one of the first questions in any incident. So are "which tenant?", "which deployment version?", "which feature flag combination?", "which specific database shard?" These are all high-cardinality dimensions. Monitoring tools force you to choose between keeping those dimensions (and blowing up storage and query cost) or dropping them (and losing the ability to ask the questions that matter most during incidents).

Observability tooling resolves this by using a fundamentally different storage model: instead of pre-aggregating into time series, it stores **individual events** and indexes them for ad-hoc query. When you ask "show me the p99 latency for requests from users on plan tier 'enterprise' that hit the payments service on shard 3 during the last 20 minutes," the system scans the raw events and computes the answer on the fly. The cost moves from write time (maintaining millions of pre-aggregated series) to query time (scanning and aggregating raw events). This is the architectural fork. Everything else follows from it.

## Wide Events: The Data Model That Makes It Work

The unit of data in observability is not a metric point or a log line. It is a **wide event** — a single structured record with many fields (often dozens to hundreds) that captures everything known about one unit of work at the moment it completes. For a web request, a wide event might include:

```json
{
  "trace_id": "abc123",
  "service": "checkout-api",
  "endpoint": "/api/v2/checkout",
  "method": "POST",
  "status_code": 200,
  "duration_ms": 842,
  "user_id": "u_98234",
  "tenant_id": "t_acme",
  "plan_tier": "enterprise",
  "feature_flags": ["new_payment_flow", "async_inventory"],
  "build_id": "a1b2c3d",
  "db_shard": "shard-7",
  "db_query_count": 4,
  "db_duration_ms": 310,
  "cache_hit": true,
  "downstream_calls": 3,
  "payment_provider": "stripe",
  "payment_duration_ms": 480,
  "region": "us-east-1",
  "az": "us-east-1c"
}
```

Every field is a potential dimension for grouping, filtering, and aggregating. You don't decide in advance which fields are "labels" (indexed) and which are "values" (aggregated). All of them are available for both operations. This is what enables the arbitrary-question property: any field can be a filter, any field can be a group-by, any numeric field can be an aggregation target. The query "break down p99 `duration_ms` by `build_id` where `plan_tier` = 'enterprise' and `payment_provider` = 'stripe'" is something you compose when you need it, not something you configure in advance.

This is the **schema-on-read** model. Monitoring uses schema-on-write: you define the shape of your data (which metrics, which labels) before you emit it, and the storage system optimizes for those specific shapes. Observability uses schema-on-read: you emit richly structured events, and the query engine interprets their shape at query time. Schema-on-write is cheaper to query but rigid. Schema-on-read is more expensive to query but flexible.

The Level 1 post described the three pillars — metrics, logs, and traces. The wide-event model shows why practitioners increasingly treat these as facets of the same underlying data rather than three separate systems. A wide event *is* a structured log. Aggregate the numeric fields across many events and you get metrics. Link events by `trace_id` and you get traces. The three pillars are not three separate investments; they are three views of the same instrumentation, if the instrumentation is rich enough.

## How Debugging Workflows Actually Differ

The mechanical difference becomes most visible during an incident. Consider the scenario: error rates have increased and p99 latency has doubled, but only for some requests.

In a monitoring-first workflow, you open your dashboards and check the usual suspects. Is a host down? No. Is a dependency degraded? Not according to its health check. Is one endpoint worse than others? Maybe — the `/checkout` dashboard looks worse, but the aggregation is across all users and all code paths, so it's hard to tell if the problem is isolated. You start reading logs, grepping for errors, trying to manually correlate timestamps across services. This works, but it is slow, and it depends on you guessing the right dimensions to investigate.

In an observability-first workflow, you start from the symptom — the elevated error rate — and iteratively decompose it. You query: "group errors by `endpoint`." Checkout is elevated. You drill in: "for `/checkout` errors, group by `build_id`." The new build has a higher error rate. Further: "for `/checkout` errors on the new build, group by `payment_provider`." Stripe is fine, but Adyen is failing. Further: "group by `error` field." You see `payment_timeout`. Further: "for Adyen timeouts, show `duration_ms` distribution." Every Adyen call is hitting a 5-second timeout. You've gone from symptom to root cause by progressively narrowing, and you didn't need to know in advance that `payment_provider` would be the relevant dimension.

This iterative decomposition — sometimes called **exploratory debugging** or **slicing and dicing** — is only possible when the data supports arbitrary grouping and filtering across high-cardinality dimensions. It is the fundamental workflow that observability enables and that monitoring structurally cannot.

## Where This Breaks: Cost, Complexity, and Cargo Culting

The wide-event, schema-on-read model has real costs.

**Storage is expensive.** You are storing individual events instead of pre-aggregated time series. A service handling 10,000 requests per second, emitting a 1KB event per request, generates 864 GB per day of raw event data. Multiply by dozens of services and you're looking at serious storage bills. Sampling — storing only a fraction of events — is the standard mitigation, but it introduces its own tradeoffs: rare events (the ones that often matter most in debugging) are exactly the ones most likely to be dropped by random sampling. **Dynamic sampling** strategies (sample more from error paths, less from healthy ones; sample more from rare combinations, less from common ones) help, but they add instrumentation complexity and can introduce subtle blind spots.

**Query performance is harder.** Scanning raw events is inherently more expensive than reading pre-aggregated time series. Columnar storage formats and purpose-built query engines (the kind used by Honeycomb, Cribl, or the columnar backends behind some Datadog and Grafana features) mitigate this, but you are fundamentally trading write-time efficiency for query-time flexibility. For real-time alerting on simple conditions — "is the error rate above 1%?" — pre-aggregated metrics are faster, cheaper, and more appropriate. Observability does not replace monitoring for this use case. It supplements it.

**The most common failure mode is cargo culting.** Teams adopt an observability platform but continue emitting narrow, low-context events — essentially shipping logs to a more expensive backend. If your events only contain `timestamp`, `level`, `message`, and `service`, you have a log aggregator, not an observability system. The power comes from the width of the events: the more dimensions you attach to each unit of work, the more questions you can answer later. This requires deliberate instrumentation effort — adding context about the request, the user, the infrastructure, the feature flags, the dependency calls — at the point where the work is performed. That effort is the actual investment in observability. The tooling is secondary.

A related failure mode is **treating observability as a platform team problem.** The platform team can provide the infrastructure — the collector, the pipeline, the query engine. But the instrumentation lives in application code, and only the application developers know which context is meaningful. If the team building the checkout service doesn't attach `payment_provider` and `plan_tier` to their events, no amount of platform investment will make that dimension queryable during an incident.

## The Model to Carry Forward

The core distinction is not tooling, not three pillars, not dashboards vs query interfaces. It is this: **monitoring encodes your hypotheses about failure into the system before failure occurs; observability preserves the raw dimensionality of your system's behavior so you can form hypotheses after failure occurs.**

This is not a binary. Every production system needs both. You need monitoring for the known failure modes — the things you can predict and should alert on automatically. You need observability for the novel failures — the things you could not have predicted and need to investigate interactively. The mistake is thinking one replaces the other, or that buying an observability vendor's product gives you observability. What gives you observability is instrumentation that emits wide, richly contextualized events from every meaningful unit of work in your system — and a storage/query layer that lets you explore those events along any dimension without deciding which dimensions matter in advance.

## Key Takeaways

- Monitoring requires you to decide what questions to ask before failures happen; observability lets you ask new questions after failures happen. This is the structural difference, not a difference in tool quality.

- Cardinality is the mechanical constraint that prevents monitoring tools from becoming observability tools — time-series databases cannot efficiently handle dimensions like user ID, tenant ID, or trace ID that are essential for debugging.

- The foundational data model for observability is the wide event: a single structured record per unit of work with dozens to hundreds of fields, any of which can be used for filtering, grouping, or aggregation at query time.

- Schema-on-write (monitoring) is cheaper to store and faster to query but rigid; schema-on-read (observability) is more expensive but supports the arbitrary exploration that novel incidents require.

- Metrics, logs, and traces are not three separate systems to invest in independently — they are three views of the same underlying instrumentation when events are rich enough.

- Observability without wide, context-rich instrumentation in application code is just expensive log aggregation. The instrumentation is the investment; the platform is the enabler.

- Sampling is necessary to manage observability costs at scale, but naive random sampling drops the rare events that matter most — dynamic sampling strategies are essential but add real complexity.

- Every production system needs both monitoring (for known failure modes and real-time alerting) and observability (for novel failures and interactive investigation). Treating them as competing approaches rather than complementary layers is a common and costly mistake.

[← Back to Home]({{ "/" | relative_url }})
