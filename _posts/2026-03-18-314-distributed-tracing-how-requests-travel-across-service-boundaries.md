---
layout: post
title: "3.1.4 Distributed Tracing: How Requests Travel Across Service Boundaries"
author: "Glenn Lum"
date:   2026-03-18 11:00:00 +0800
categories: journal
image: tier_3.jpg
tags: [Tier 3, Cross-Cutting Disciplines, Depth]
---

Most engineers encounter distributed tracing for the first time as a request ID. Someone adds a header — `X-Request-ID` or similar — and suddenly every log line from every service can be correlated back to the same user request. This feels like tracing, and it solves a real problem, but it is not what distributed tracing actually is. A correlation ID gives you a shared label. A distributed trace gives you a **causal graph** — a structured record of every operation that happened, which operation caused which, how long each one took, and where in that chain the failure or slowdown occurred. The difference between "these log lines are related" and "this span was the child of that span, and it consumed 80% of the total latency" is the difference that makes tracing uniquely powerful. Understanding how that structure gets built — across process boundaries, across networks, across independently deployed services that share no memory — is what this post is about.

## The Data Model: Traces, Spans, and Parent-Child Relationships

A **trace** represents the complete lifecycle of a single request through your system. It is not a single record. It is a collection of **spans**, where each span represents one unit of work: handling an HTTP request, making a database query, publishing a message to a queue, calling another service. A trace is the tree formed by those spans' parent-child relationships.

Every span carries a small set of critical fields. The **trace ID** is a globally unique identifier (typically 128 bits) shared by every span in the trace. The **span ID** is unique to that individual span. The **parent span ID** points to the span that caused this one to exist. Together, these three fields are what allow a collection of independently emitted span records — reported by different services, at different times, from different machines — to be assembled into a coherent tree after the fact.

Consider a checkout request. The API gateway receives the HTTP request and creates the **root span** — the one with no parent. It calls the order service, so it creates a child span representing that outbound call. The order service receives the request, creates its own span (whose parent is the gateway's outbound span), and makes two downstream calls: one to the inventory service and one to the payment service. Each of those produces its own spans. The resulting structure is a tree:

```
[API Gateway: handle-checkout] ─── 350ms
  └── [Order Service: create-order] ─── 320ms
        ├── [Inventory Service: reserve-items] ─── 45ms
        └── [Payment Service: charge] ─── 270ms
              └── [Payment DB: insert-transaction] ─── 12ms
```

This is not a flat list of events. It is a tree with causal edges. You can see immediately that the payment service is responsible for the bulk of the latency, and that the inventory and payment calls happened concurrently (their timings overlap within the parent span's duration). No combination of per-service logs or aggregate metrics can reconstruct this structure. Metrics can tell you the payment service's p99 latency is elevated. Logs can tell you the individual services processed the request. Only the trace shows you that *this specific request* was slow because *this specific call* to the payment service took 270ms, and that it was on the critical path.

Each span also carries **attributes** (key-value pairs like `http.method: POST`, `db.statement: INSERT INTO transactions...`, `user.id: 8842`) and **events** (timestamped annotations within the span's lifetime, useful for recording things like retry attempts or cache misses). These are what make spans useful for debugging, not just latency attribution.

## How Context Crosses Service Boundaries

The fundamental challenge of distributed tracing is that no single service has visibility into the full request path. Each service only knows about its own work. The trace can only be assembled if every service agrees on the trace ID and correctly records its parent span ID. This requires **context propagation**: the mechanism by which trace identity travels alongside the request itself.

Context propagation happens **in-band** — it is carried in the same transport as the request. For HTTP, this means headers. For gRPC, metadata fields. For message queues, message attributes or headers. The trace context rides with the request because the request *is* the causal link between spans. If service A calls service B, the only way service B knows its span is a child of service A's span is if service A tells it — by injecting the trace context into the outgoing request.

The **W3C Trace Context** standard defines two headers that have become the dominant propagation format:

```
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
tracestate: vendor1=value1,vendor2=value2
```

The `traceparent` header encodes four fields: version, trace ID, parent span ID, and trace flags (most importantly, whether this trace is being sampled). The `tracestate` header carries vendor-specific data. When the order service receives a request with this header, it extracts the trace ID and span ID, uses them as its parent context, generates a new span ID for its own work, and injects an updated `traceparent` into any downstream calls it makes.

This is the critical mechanical insight: **every service in the chain performs an extract-process-inject cycle.** It extracts trace context from the incoming request, uses it to establish parentage for its own spans, and injects updated context into every outgoing request. If any service in the chain fails to perform this cycle — because it wasn't instrumented, because it uses a middleware that strips unknown headers, because someone deployed a proxy that doesn't forward the headers — the trace is **severed**. The downstream spans will either start a new trace (appearing as an unrelated root span) or be lost entirely. The result is partial traces: you see the beginning of the request and then it vanishes into a gap.

This is why instrumentation is not optional for services on the request path. A single uninstrumented service doesn't just lose its own spans — it breaks the causal chain for everything downstream of it.

## Span Collection and Trace Assembly

While context propagation happens in-band with the request, **span reporting happens out-of-band.** Each service, after completing a span, sends that span record to a collector — typically via a background process that batches spans and ships them asynchronously. The service does not wait for the collector to acknowledge receipt. This is essential because tracing cannot be on the critical path of request handling; adding synchronous network calls to a tracing backend on every span would be an unacceptable latency tax.

The consequence is that traces are **assembled after the fact.** The tracing backend (Jaeger, Tempo, an OTLP-compatible backend, or a commercial vendor) receives a stream of span records from many services. When you query for a trace by its trace ID, the backend collects all spans sharing that trace ID and reconstructs the tree using the parent span IDs. This means the trace you see in your UI is an eventually consistent view. If a service is slow to report its spans, or if the collector drops a batch, the trace will appear incomplete until all spans arrive — or permanently, if some are lost.

This also means the tracing backend has no way to know when a trace is "complete." It assembles whatever spans it has. A trace with missing spans in the middle will show a parent span with unexplained gaps in its timeline — the child spans simply won't be there. This is one reason that broken propagation is so insidious: the resulting traces look plausible but misleading. You see a span that took 500ms with no children, and you conclude that service was slow, when in reality it made a downstream call that was never traced.

## Sampling: Why You Cannot Trace Everything

In a high-throughput system, tracing every single request is prohibitively expensive. Each span is a structured record that must be serialized, transmitted, stored, and indexed. A single request that touches eight services and makes a few database calls might produce 15–25 spans. At 10,000 requests per second, that is 150,000–250,000 span records per second flowing into your tracing backend. The storage, network, and compute costs scale linearly.

**Head-based sampling** makes the sampling decision at the start of the trace — at the root span — and propagates that decision through the trace context. The `traceparent` header's trace flags field carries a "sampled" bit. If the root span decides this trace is not sampled, every downstream service sees that flag and either skips span creation entirely or creates spans but does not export them. This is efficient: unsampled traces impose near-zero overhead. The problem is that the decision is made before you know whether the request will be interesting. A 1% head-based sampling rate means that 99% of your errors, timeouts, and edge cases are never captured.

**Tail-based sampling** defers the decision until the trace is complete (or nearly so). All spans are collected initially, and then a sampling processor examines the assembled trace and decides whether to keep it based on its properties: did it contain an error? Was any span's duration above a threshold? Did it touch a specific service? Tail-based sampling is far more powerful — you can keep 100% of error traces and only 1% of successful ones — but it requires a buffer that holds all spans until the decision can be made, and it is architecturally more complex. The sampling tier must see all spans for a trace before it can decide, which means it needs to handle the full unsampled span volume at ingestion.

In practice, most production systems use head-based sampling with targeted overrides: always sample traces for specific endpoints, increase the rate during incidents, or use a hybrid approach where head-based sampling handles the common case and a tail-based layer captures anomalies.

## Tradeoffs and Failure Modes

**Broken propagation is the most common failure mode** and the hardest to detect. It does not produce errors. It produces silence. A reverse proxy that strips non-standard headers will break propagation silently. A service written in a language without auto-instrumentation that manually makes HTTP calls without injecting headers will sever every trace that passes through it. An async worker that pulls a message from a queue but doesn't extract trace context from the message attributes will start a new, disconnected trace. You won't notice until you go looking for an end-to-end trace and find that none of your traces extend past a certain service.

**Clock skew distorts the timeline.** Spans from different services carry timestamps set by different machines. If those machines' clocks are not synchronized (via NTP or a similar protocol), child spans can appear to start before their parents, or the visual timeline of the trace can be misleading. This doesn't break trace assembly — the parent-child links are established by IDs, not timing — but it undermines the visual representation and any latency analysis that depends on absolute timestamps.

**Cardinality in span attributes is a hidden cost.** Every unique combination of attribute values creates indexing and storage pressure in the tracing backend. Adding `user.id` to every span is useful for debugging but creates an attribute with potentially millions of distinct values. Adding high-cardinality attributes thoughtlessly will inflate your tracing costs and degrade query performance.

**Async boundaries require deliberate handling.** When a service publishes a message to a queue instead of making a synchronous call, the trace context must be explicitly attached to the message and extracted by the consumer. This is not automatic, even with instrumentation libraries, because the transport mechanisms vary. Any architecture that uses queues, event buses, or background job systems will have trace gaps at every async boundary unless each one is individually instrumented.

## The Mental Model

A distributed trace is not a log. It is not a request ID. It is a tree of causally linked span records, assembled after the fact from data emitted independently by every service a request touched. The tree structure — specifically, the parent span ID on each span — is what gives tracing its unique power: the ability to show not just *what* happened, but *what caused what* and *where time was actually spent* for a specific request.

The fragility of this system lives in one place: context propagation. Every service in the request path must faithfully extract trace context from incoming requests and inject it into outgoing ones. If the chain is unbroken, the trace is complete. If any link fails to propagate, everything downstream is severed. When you evaluate your tracing setup, the first question is not "which backend should we use?" It is "can we guarantee propagation across every service boundary in our system, including async ones?"

## Key Takeaways

- A trace is a tree of spans connected by parent-child IDs, not a flat list of correlated log entries — the tree structure is what enables causal reasoning and critical-path latency analysis.

- Context propagation is the mechanism that makes tracing work: trace identity travels in-band with the request (via HTTP headers, gRPC metadata, or message attributes), while span data is reported out-of-band to a collector.

- Every service performs an extract-inject cycle on trace context; a single service that fails to propagate severs the trace for everything downstream, not just for itself.

- Traces are assembled after the fact by the tracing backend, which collects independently emitted spans sharing a trace ID — this means traces are eventually consistent and can be permanently incomplete if spans are lost.

- Head-based sampling is cheap but blind (the decision is made before you know if the request is interesting); tail-based sampling can keep error traces selectively but requires buffering the full span volume before deciding.

- Broken propagation is the most common and most dangerous failure mode because it is silent — it produces incomplete traces that look plausible rather than errors that demand attention.

- Async boundaries (message queues, event buses, background jobs) do not propagate trace context automatically; each one requires explicit instrumentation or the trace will be severed at that boundary.

- High-cardinality span attributes (user IDs, request IDs, session tokens) are valuable for debugging but create real storage and indexing costs — add them deliberately, not by default.

[← Back to Home]({{ "/" | relative_url }})
