---
layout: post
title: "3.1.2 The Three Pillars: Metrics, Logs, and Traces"
author: "Glenn Lum"
date:   2026-03-16 11:00:00 +0800
categories: journal
image: tier_3.jpg
tags: [Tier 3, Cross-Cutting Disciplines, Depth]
---

Most teams have metrics, logs, and traces. They have dashboards, they have a log aggregator, they might even have distributed tracing turned on. And when something breaks at 2 AM, they still can't figure out what happened. The reason is almost never that they're missing a pillar. It's that they don't understand the data model underneath each one — what it can and cannot represent, why it costs what it costs, and how to move between pillars during an investigation. The three pillars are not three flavors of the same thing. They are three fundamentally different data structures, optimized for fundamentally different query patterns, with fundamentally different cost profiles. Until you understand that, you'll keep collecting all three and getting the diagnostic power of one.

## The Data Models Are the Point

Each pillar exists because it represents system behavior in a way the other two structurally cannot. This isn't a matter of preference or tooling — it follows from what the underlying data looks like.

**Metrics** are pre-aggregated numerical time series. A single metric is a name, a set of label key-value pairs, and a stream of timestamped numerical values. When your application records that it handled a request in 230ms, that number doesn't get stored as an individual event. It gets folded into an aggregate: a histogram bucket is incremented, a counter ticks up, a gauge is updated. The raw event is gone. What remains is a compact summary of behavior over a time window.

This is why metrics are cheap to store and fast to query. A counter tracking HTTP requests with labels for `method`, `status`, and `endpoint` produces one time series per unique combination of those label values. Whether your service handled ten requests or ten million in the last minute, the storage cost is roughly the same — it's proportional to the number of unique label combinations, not the number of events. This property is what makes metrics viable for real-time alerting and long-term trending. It's also the source of their fundamental limitation: once you've aggregated, you cannot disaggregate. You can see that p99 latency spiked, but you cannot ask "which specific request was slow?" The individual events no longer exist in the metrics system.

**Logs** are the opposite. Each log record is a discrete, individual event with arbitrary fields. Nothing is pre-aggregated. When your service handles a request and emits a structured log line, every field you attached — user ID, request ID, duration, response code, downstream service called — is preserved as-is. This means logs can answer questions about specific events: "What happened to this particular request from this particular user at this particular time?" But it also means your storage cost scales linearly with event volume. Every request, every database query, every retry produces a record that must be ingested, indexed, and stored. A service handling 50,000 requests per second is producing 50,000 log records per second, each of which might be several hundred bytes.

This cost structure is not incidental. It's the reason log retention policies exist, the reason log sampling becomes necessary at scale, and the reason teams are perpetually fighting their log aggregation bill. The diagnostic power of logs comes precisely from their un-aggregated nature, and that nature is expensive.

**Traces** are neither aggregates nor flat event records. A trace is a **directed acyclic graph of spans**, where each span represents a unit of work and the edges represent causal relationships — "this service called that service," "this database query happened inside this request handler." The data model is inherently relational. A single trace captures the structure of a request's journey: what called what, in what order, and how long each piece took. This structural information is what neither metrics nor logs can represent. Metrics can tell you that the payment service is slow. Logs can tell you that a specific request to the payment service timed out. Only a trace can tell you that the request was slow because the payment service made a synchronous call to the fraud-detection service, which made three retries to an external API, and the third retry took four seconds.

### Cardinality: The Constraint That Governs Metrics

The single most important concept in metrics systems is **cardinality** — the number of unique time series produced by a metric. Every unique combination of label values creates a new time series, and each time series consumes memory in your metrics backend for as long as it's active.

Consider a metric like `http_request_duration_seconds` with labels `method`, `endpoint`, `status_code`, and `customer_id`. The first three labels are bounded: you have a handful of HTTP methods, a known set of endpoints, and a finite set of status codes. The product might be 5 × 30 × 5 = 750 time series. Manageable. But `customer_id` is unbounded. If you have 100,000 customers, you've just created 75 million time series. Your metrics backend will either fall over or your bill will make someone in finance ask hard questions.

This is why experienced operators are careful about which labels they attach to metrics. The rule is: **metrics labels must have low, bounded cardinality**. If you need to break down behavior by a high-cardinality dimension like user ID, request ID, or session token, that's a job for logs or traces, not metrics. Violating this rule is one of the most common ways teams accidentally take down their monitoring infrastructure — which means losing visibility precisely when they need it most.

### How Trace Context Propagation Actually Works

Traces don't magically appear. They require active cooperation between every service in a request path, and understanding the mechanism matters because it's where traces most commonly break.

When a request enters your system, the first service generates a **trace ID** — a globally unique identifier for this entire request journey — and a **span ID** for its own unit of work. When that service makes an outbound call to another service, it injects both IDs (plus a new parent span ID) into the request headers. The downstream service extracts those IDs, creates its own span as a child of the parent, and does the same for any further downstream calls. This is **context propagation**, and it happens via headers in HTTP calls (typically `traceparent` in the W3C Trace Context standard), message metadata in async systems, or similar carrier mechanisms.

Every service in the chain must participate. If one service in the middle doesn't extract and propagate the context, the trace breaks — you get two disconnected fragments instead of one coherent picture. This is why instrumenting traces in a polyglot microservice architecture is genuinely hard. Every service, in every language, using every framework, must correctly handle context propagation. A single uninstrumented service creates a gap.

### Sampling: The Unavoidable Compromise in Traces

At any meaningful scale, collecting 100% of traces is economically impractical. A system handling 100,000 requests per second, where each request touches eight services, produces 800,000 spans per second. Each span carries timing data, attributes, status codes, and often log-like event annotations. The storage and processing cost is enormous.

The answer is **sampling**, and the strategy you choose has direct consequences for what you can and cannot see.

**Head-based sampling** makes the decision at the entry point: when a trace is created, you decide probabilistically (e.g., keep 1% of traces) whether to record it. This is simple and predictable in terms of cost, but it means you'll miss rare events. If an error occurs on 0.01% of requests and you're sampling at 1%, most error traces are never recorded.

**Tail-based sampling** waits until the trace is complete, examines it, and then decides whether to keep it — typically retaining all traces that contain errors or high latency while discarding routine successful traces. This is far more useful for debugging but requires a collector that can buffer complete traces before making the keep/drop decision, which adds architectural complexity and its own resource costs.

The choice between these strategies is not academic. It determines whether your tracing system will actually contain the traces you need during an incident.

## Where the Pillars Break and Where Teams Get Stuck

### The Correlation Gap

The most common failure mode isn't a missing pillar — it's three pillars that don't talk to each other. A team sees a latency spike on a metrics dashboard, switches to their log aggregator to search for errors in the affected time window, finds some timeout errors, but can't connect those errors to a specific trace showing the causal chain. They're doing archaeology across three disconnected tools.

The fix is **correlation identifiers**. Every log line should carry a trace ID. Metrics should support **exemplars** — references from an aggregate data point back to a specific trace that contributed to it. When your p99 histogram bucket shows a spike, an exemplar lets you click through to an actual trace that experienced that latency. Without these links, you have three data stores and a manual process of jumping between them with timestamps and guesswork.

Building this correlation in isn't free. It requires that your instrumentation layer — whether OpenTelemetry or something custom — consistently attaches trace and span IDs to log records, and that your metrics library supports exemplar emission. It requires that your tooling can follow those links. But without it, the promise of "three pillars" remains theoretical.

### Logs as a Crutch

Teams that haven't invested in metrics or traces tend to pour everything into logs. They log request durations (a metric), they log the call chain between services (a trace), and they also log actual event data (the thing logs are for). The result is a multi-terabyte-per-day log pipeline that is simultaneously expensive and slow to query. Asking "what is my p99 latency right now?" by scanning billions of log records is orders of magnitude slower and more expensive than reading it from a pre-aggregated time series. Using logs to reconstruct call graphs between services is possible but brittle — it requires consistent request ID propagation and careful log correlation that replicates what a tracing system does natively.

The right instinct is: if you're aggregating log data to produce a number, that should probably be a metric. If you're joining log records across services to reconstruct a request path, that should be a trace. Logs should capture what only logs can capture — the context and detail of individual events.

### Metric Averages Lie

A metric showing average latency of 150ms might mean all requests take 140-160ms, or it might mean 99% take 50ms and 1% take 10 seconds. The average hides the distribution. This is why percentile-based metrics (p50, p95, p99) exist — but percentiles have their own problem: **they cannot be aggregated across instances**. The p99 of service instance A and the p99 of service instance B cannot be averaged to produce the true p99 of the service. Histograms solve this (you can merge histogram buckets and then compute percentiles from the merged result), but only if you set your bucket boundaries appropriately before collection. The boundaries you choose determine what granularity of latency distribution you can see. This is a decision you make at instrumentation time that constrains your analysis options permanently.

## The Model to Carry Forward

Think of the three pillars as three projections of the same underlying reality — the stream of everything happening in your system. Metrics are the statistical projection: they discard individual identity in exchange for cheap, fast, aggregable summaries. Logs are the event projection: they preserve individual identity and context at the cost of volume and query expense. Traces are the structural projection: they capture causal relationships between units of work at the cost of propagation complexity and sampling tradeoffs.

No single projection can reconstruct the full picture. A metric tells you something is wrong. A log tells you what happened in one place. A trace tells you why it happened across places. The skill isn't choosing the right pillar — it's knowing which projection answers the question you're currently asking and being able to pivot between them using correlation identifiers when the first projection isn't enough. If your pillars aren't linked, you have three separate tools. If they are, you have one observability system with three lenses.

## Key Takeaways

- **Metrics are pre-aggregated by design.** Their cost scales with the number of unique label combinations (cardinality), not with request volume, which is why they're cheap — and why they can never answer questions about individual events.

- **Cardinality is the single most important constraint in metrics systems.** Adding a high-cardinality label like user ID or request ID to a metric can produce millions of time series and destabilize your monitoring infrastructure.

- **Logs preserve individual event identity, and that's both their power and their cost.** Storage scales linearly with event volume, which is why log retention, sampling, and careful selection of what to log are operational necessities, not optimizations.

- **A trace is a graph of causally related spans, not a flat list.** Its unique value is representing the structure of a request's journey — what called what, in what order, and where time was spent — which neither metrics nor logs can capture.

- **Trace context propagation requires every service in the request path to participate.** A single uninstrumented service breaks the trace into disconnected fragments, which is why full-stack instrumentation is a prerequisite, not an enhancement.

- **Tail-based sampling retains interesting traces (errors, high latency) at the cost of architectural complexity; head-based sampling is simple but randomly discards the traces you most need during incidents.**

- **The three pillars only function as a system when they are linked by correlation identifiers** — trace IDs in log records, exemplars in metrics — allowing you to pivot from an aggregate anomaly to a specific event to a causal chain without manual timestamp matching.

- **If you're aggregating logs to produce a number, you need a metric. If you're joining logs across services to reconstruct a call path, you need a trace.** Misusing one pillar as a substitute for another produces worse results at higher cost.


[← Back to Home]({{ "/" | relative_url }})
