---
layout: post
title: "1.3.7 Failure Modes in Distributed Systems: Partial Failure and Cascading Failure"
author: "Glenn Lum"
date:   2026-02-04 11:00:00 +0800
categories: journal
image: tier_1.jpg
tags: [Tier 1,Foundation Knowledge,Depth]
---

Most engineers think about distributed system failure as "a service goes down." The service crashes, the health check fails, the load balancer routes around it, and the system recovers. This is the easy case. The failure mode that actually takes down production systems is not a crash — it is a service that is still technically running but responding slowly. A dead service is a solved problem. A slow service is a trap that converts one component's problem into a system-wide outage by consuming resources in every service that depends on it.

The Level 1 post established that microservices turn local function calls into network calls, and that network calls can fail in ways local calls cannot. This post explains exactly *how* that happens — the specific mechanical chain by which a single slow dependency can bring down an entire service mesh, and why the intuitions you developed debugging single-process systems will actively mislead you.

## The Fundamental Problem: Failure Is No Longer Binary

In a single-process system, a function call either returns or it throws. If the process runs out of memory, everything stops. If a thread deadlocks, the process hangs as a unit. Failure is **total** — the whole thing works or the whole thing doesn't. You might lose some data, but you never end up in a state where half the system thinks an operation succeeded and the other half thinks it failed.

Distributed systems break this assumption completely. When Service A calls Service B over the network, there are not two outcomes — there are at least five: the call succeeds, the call fails with an error, the call times out, the call succeeds but Service A never receives the response, or the call is received by Service B but processed after Service A has already given up and moved on. Each of these outcomes leaves the system in a different state, and several of them leave the two services with *inconsistent views of what happened*.

This is **partial failure**: the condition where some components of the system are functioning correctly while others are not, and — critically — no single component has a complete picture of which state the system is in. The hard part is not that things fail. The hard part is that you cannot tell, from inside any single component, what the global state of the system actually is.

Consider a concrete sequence: a user places an order. The order service writes the order to its database, then calls the payment service to charge the card. The network drops the response. The payment service successfully charged the card. The order service, having received no response, doesn't know whether the charge went through or not. It cannot safely retry (double charge) and it cannot safely abort (the user paid but gets no order). This is not an edge case — this is the *default behavior* of any multi-service write operation that does not explicitly account for it.

## Why Slow Is Worse Than Down

A failed service is easy to reason about. The connection is refused, the error propagates immediately, and the caller can execute its fallback path in milliseconds. The load balancer detects the failure and removes the instance from the pool. The operational cost is bounded.

A **slow service** does something far more destructive: it holds resources open. When Service A makes a call to Service B and Service B is slow, the thread (or goroutine, or connection) in Service A that is handling that request sits idle, waiting. It is consuming memory for its stack. It is occupying a slot in Service A's thread pool or connection pool. It is holding open a connection from the finite pool that Service A uses to talk to Service B.

Now multiply this by every concurrent request that is hitting Service A and needs to talk to Service B. If Service B's latency goes from 50ms to 10 seconds, and Service A receives 200 requests per second, those requests start stacking up. In the time it used to complete one request to Service B, Service A now has 200× more in-flight requests waiting on that dependency. Each one is holding a thread. Service A's thread pool, which was comfortably handling its load at normal latency, fills up within seconds.

Once the thread pool is exhausted, Service A cannot accept any new requests — even requests that have nothing to do with Service B. If Service A also serves an endpoint that returns cached data without any downstream calls, that endpoint is now also unavailable, because there are no threads left to handle it. Service B's slowness has made Service A completely unavailable for all callers, for all endpoints.

This is the core mechanical insight: **a slow dependency doesn't just degrade the calls that use it — it exhausts shared resources that all calls depend on**. Thread pools, connection pools, file descriptors, memory — these are the shared resources through which slowness propagates.

## The Cascade: How One Failure Becomes a System Outage

Cascading failure is not a metaphor. It is a specific, reproducible chain of resource exhaustion that propagates through service dependencies. Here is how it unfolds:

Service C, a database lookup service, starts experiencing high latency because of a slow query caused by a new index being rebuilt. Service C is not down — it is still responding, just taking 8 seconds instead of 80 milliseconds.

Service B calls Service C on 40% of its requests. Service B has a thread pool of 200 threads. At 80ms latency, each thread handles a Service C call and is free again almost immediately. At 8 seconds, threads that touch Service C are occupied 100× longer. Within seconds, those 200 threads are all occupied waiting on Service C. Service B's health check might still pass — the process is running, the port is listening. But it is effectively dead: no new requests can be processed.

Service A calls Service B. Service A has its own thread pool. Now *its* threads start backing up, waiting for Service B to respond. Service A's latency spikes. Services D and E, which also depend on Service A, start experiencing the same thread exhaustion.

From the outside, it looks like every service failed simultaneously. In reality, a single slow query in Service C created a wavefront of resource exhaustion that propagated upstream through the entire dependency graph in under a minute.

The critical feature of this cascade is that **every service in the chain was behaving "correctly."** Service B waited patiently for Service C, as it was configured to do. Service A waited patiently for Service B. No service threw an error. No circuit breaker tripped because no requests technically *failed* — they were just slow. The system collapsed under the weight of patience.

## The Mechanisms That Shape Failure Propagation

Three mechanical properties determine how a failure propagates through a distributed system: **timeouts**, **resource pools**, and **retry behavior**.

### Timeouts and the Absence of Timeouts

A network call without a timeout is a resource leak waiting to happen. If Service A calls Service B with no timeout, and Service B hangs, that thread in Service A is gone forever — it will never return to the pool. In practice, the underlying TCP stack may eventually time out the connection, but TCP keepalive defaults are often measured in *hours*, not seconds.

Setting timeouts is necessary but not sufficient. The timeout value itself is a loaded decision. Too long, and you're still holding resources for an unacceptable duration during a slowdown — a 30-second timeout on a call that normally takes 50ms means you'll accumulate 600× more in-flight requests before they start clearing. Too short, and you will start failing requests during normal latency variance, turning a healthy system into a flaky one.

A useful heuristic: your timeout should be set based on the latency you are *willing to wait*, not the latency you *expect*. If your SLA says a request must complete in 500ms, and this downstream call is one of four in the critical path, your timeout for each call needs to leave room for all four plus your own processing. Working backward from the user-facing latency budget gives you a more honest number than looking at p99 latency charts and adding a margin.

### Connection and Thread Pools as Blast Radius Controls

The size and configuration of your resource pools directly determine how much damage a slow dependency can inflict. A single, shared thread pool for all request handling means a slow dependency can starve every endpoint. A **bulkhead** — a dedicated resource pool for each downstream dependency — limits the blast radius. If the pool for Service C calls fills up, requests to Service C fail fast, but threads for serving other endpoints remain available.

This is an allocation problem with real costs. Dedicated pools per dependency mean you need more total threads (or connections), because you've given up the efficiency of sharing. If you allocate 50 threads to Service C calls and Service C is healthy, those 50 threads sit mostly idle while other work queues up for a shared pool that's now smaller. You are trading efficiency for isolation.

### Retries: The Amplifier

Retries are the single most dangerous pattern in distributed systems when applied without thought. When a service is slow or failing, retries multiply the load on the already-struggling service. If every caller retries three times, the failing service receives 3× its normal traffic at precisely the moment it is least able to handle it. If those retries time out and trigger *their own* retries upstream, the amplification compounds exponentially. This is a **retry storm**, and it is one of the most common triggers for a full cascading failure.

Safe retry behavior requires at minimum: a strict retry budget (not "retry three times" but "retry at most once, and only if fewer than 10% of recent requests have been retries"), **exponential backoff** (each subsequent retry waits longer), and **jitter** (randomized delay to prevent synchronized retry waves across many callers). Even with all of these, retries are only safe for *idempotent* operations — operations where executing them twice produces the same result as executing them once. Retrying a payment charge without idempotency keys is how you charge a customer five times for one order.

## Where the Standard Playbook Breaks

The standard advice — "add timeouts, add retries, add circuit breakers" — creates its own failure modes when applied mechanically.

**Circuit breakers with shared state become coordination points.** If your circuit breaker for Service B opens, all traffic to Service B stops. If Service B has partially recovered and could handle some load, the circuit breaker's binary open/closed model prevents you from sending it the traffic that would let it demonstrate health. The half-open state (allowing a small number of probe requests through) helps but introduces its own tuning problem: how many probe requests, how often, and what constitutes success?

**Timeouts create a cliff, not a slope.** If you set a 2-second timeout on a call that normally takes 50ms, and latency increases to 1.9 seconds, every request succeeds but your system is now operating at 1/38th its normal throughput. You haven't failed, but you're about to. Your monitoring shows green (no errors), but your thread pools are nearly full. Then latency ticks to 2.1 seconds and *everything* fails at once. The timeout converted a gradual degradation into a sudden cliff.

**Fallbacks that aren't truly independent mask the real problem.** A common pattern: if the recommendation service is slow, return a default set of recommendations from cache. This works until the cache is stored in a shared Redis instance that is *also* experiencing load because of the same underlying issue that is causing the recommendation service to be slow. Fallbacks only provide resilience when they have genuinely independent failure domains — separate infrastructure, separate network paths, separate resource pools.

**Load shedding that happens too late is useless.** By the time your server's request queue is full and you start returning 503s, every thread is already occupied. The 503 responses clear the queue briefly, but if inbound traffic hasn't decreased, the queue refills immediately. Effective load shedding requires detecting overload *before* resources are fully consumed — based on latency increases, queue depth trends, or CPU saturation — and rejecting requests early enough that the system retains capacity to serve the requests it does accept.

## The Model to Carry Forward

The mental model shift this post is trying to produce is this: **distributed system failure is fundamentally a resource accounting problem, not an error handling problem.**

In a single-process system, you think about failure in terms of exceptions and error codes. In a distributed system, you need to think about failure in terms of threads, connections, memory, and file descriptors — the finite resources that every network call consumes while it is in flight. A call that is "in progress" is not free. It has a cost that is directly proportional to how long it stays in progress. When latency increases, costs increase, and when costs exceed capacity, the system fails — regardless of whether any individual request returned an error.

This means designing for resilience is not about catching errors. It is about bounding the cost of uncertainty. Timeouts bound how long a single call can consume resources. Bulkheads bound how many resources a single dependency can consume. Circuit breakers bound how many calls you make to a dependency that is unlikely to respond. Load shedding bounds how many requests your service attempts to handle simultaneously. Every one of these mechanisms is a resource constraint, not an error handler.

## Key Takeaways

- A slow service is more dangerous than a dead service because it holds resources open for extended periods, exhausting thread pools and connection pools that all other operations depend on.
- Partial failure means components in a distributed system can disagree about the current state of the world, and no single component has a complete view — this is not a bug to fix but a fundamental property to design around.
- Cascading failure is a specific chain of resource exhaustion: one service's latency increase causes its callers to hold threads longer, filling their thread pools, which makes *them* slow, propagating the exhaustion upstream through the entire dependency graph.
- Timeouts should be derived from the latency budget you can afford, not from the latency you observe — working backward from the user-facing SLA gives a more honest number than padding the p99.
- Retries without budgets, backoff, jitter, and idempotency guarantees will amplify a failure rather than recover from it, often turning a partial outage into a complete one.
- Bulkheads (dedicated resource pools per dependency) trade resource efficiency for blast radius control — this is a cost worth paying for critical paths, but it is a cost.
- Fallback paths only provide real resilience when they have genuinely independent failure domains; a fallback that shares infrastructure with the primary path will fail at the same time.
- Resilience in distributed systems is not about catching errors — it is about bounding the resource cost of every network call so that uncertainty in one dependency cannot consume the capacity needed to serve everything else.

[← Back to Home]({{ "/" | relative_url }})
