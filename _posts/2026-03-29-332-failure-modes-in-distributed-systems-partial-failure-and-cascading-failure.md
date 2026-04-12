---
layout: post
title: "3.3.2 Failure Modes in Distributed Systems: Partial Failure and Cascading Failure"
author: "Glenn Lum"
date:   2026-03-29 11:00:00 +0800
categories: journal
image: tier_3.jpg
tags: [Tier 3, Cross-Cutting Disciplines, Depth]
---

Most engineers, when they think about failure in distributed systems, picture a server that crashes, a process that dies, a network cable that gets unplugged. These failures are dramatic and visible. They trigger alerts. Health checks fail. Load balancers route around them. Kubernetes restarts the pod. The system heals. These are the failures your infrastructure is *already designed to handle*, and handling them is largely a solved problem.

The failures that actually take down production systems in spectacular ways are quieter. A database query that normally returns in 4 milliseconds starts taking 12 seconds. A downstream service doesn't crash — it just gets slow. A garbage collection pause causes a node to stop responding for 800 milliseconds every few minutes. The node is still alive. It still passes health checks. The load balancer keeps sending it traffic. And this is precisely where things go wrong, because a slow component is almost always more destructive than a dead one. Understanding *why* that's true — mechanically, at the level of threads and connections and queues — is what separates engineers who design resilient systems from engineers who design systems that look resilient until they aren't.

## Why Slow Is Worse Than Down

When a service dies, it stops accepting connections. Callers get an immediate error — connection refused — and they can act on it. The failure is unambiguous. The resource cost to the caller is negligible: the time it takes to attempt a TCP handshake and receive a RST packet is measured in microseconds.

When a service gets slow, everything changes. The caller sends a request and *waits*. While it waits, it holds resources open. A thread from the thread pool. A connection from the connection pool. Memory allocated for request and response buffers. A file descriptor for the socket. If the response normally takes 5 milliseconds, those resources are occupied for 5 milliseconds. If the downstream service is degraded and takes 10 seconds to respond, those same resources are occupied for 10 seconds — 2,000 times longer.

This is where **Little's Law** makes the problem concrete. The number of concurrent in-flight requests in a system equals the arrival rate multiplied by the average time each request spends in the system. If your service handles 1,000 requests per second and each request completes in 5 milliseconds, you have roughly 5 concurrent requests at any moment. Your thread pool of 200 is barely touched. Now suppose your downstream dependency gets slow and response time jumps to 5 seconds. Same arrival rate, same service. You now have 5,000 concurrent requests trying to be in-flight simultaneously. Your thread pool of 200 is exhausted in under a second. Every subsequent request queues, which increases its latency, which means it holds resources even longer, which deepens the queue further. This is a positive feedback loop, and it happens fast.

A dead node gets removed from the pool. A slow node *stays in the pool and keeps absorbing traffic it can't serve quickly enough*. It acts as a black hole — traffic goes in, and the responses come back too late to be useful, but the resources were consumed anyway.

## The Anatomy of a Cascading Failure

Cascading failure is the process by which slowness or resource exhaustion in one component propagates upstream through the call graph, taking out services that are themselves perfectly healthy. Here's how it unfolds in a concrete sequence.

Suppose you have a request path: **User → API Gateway → Order Service → Inventory Service → Database**. The database develops a slow query — maybe an index was dropped during a migration, maybe the working set exceeded available memory, maybe a long-running analytics query is holding locks. Query latency goes from 3 milliseconds to 8 seconds.

The Inventory Service is making synchronous calls to the database. Its connection pool to the database has 50 connections. At the previous 3ms latency, those 50 connections could serve roughly 16,000 queries per second. At 8 seconds per query, those 50 connections can serve about 6 queries per second. The pool fills up almost instantly. New requests to the Inventory Service now block waiting for a database connection. The Inventory Service's own response time goes from 10 milliseconds to however long it takes to get a database connection — which is governed by the connection pool's wait timeout, often defaulted to 30 seconds.

Now the Order Service, which calls the Inventory Service, has the same problem one layer up. Its thread pool threads are all blocked waiting for the Inventory Service to respond. Its thread pool fills. Its response time degrades to the Inventory Service's degraded response time *plus* its own queuing time.

The API Gateway, calling the Order Service, fills its connection pool or thread pool in the same way. The gateway stops responding to *all* requests — not just the ones that touch inventory. If the gateway shares a thread pool across all endpoints, a slow inventory path can starve the user profile endpoint, the search endpoint, every other endpoint that routes through the same gateway.

The entire request path is now effectively down. But here's the critical detail: **no single component has crashed**. Every process is running. Every health check endpoint returns 200. Every pod shows Ready in Kubernetes. The failure exists *in the interactions between components*, not in any individual component. This is why it's invisible to the monitoring that catches crashes.

## The Timeout Coordination Problem

The instinctive response to the cascade scenario is "just set timeouts." This is correct but deeply insufficient, because *how* you set timeouts matters more than *whether* you set them.

Consider the same call chain: User → A → B → C. The user's browser has an implicit timeout — most users abandon a page load after about 3 seconds. Service A sets a 30-second timeout when calling B. Service B sets a 30-second timeout when calling C.

When C gets slow, B waits up to 30 seconds for C. A waits up to 30 seconds for B. The user gave up after 3 seconds. But A and B are still holding threads and connections open for a request that *nobody is waiting for anymore*. For the next 27 seconds, those resources are wasted, actively contributing to the resource exhaustion that will cascade into other requests.

This is the **timeout budget** problem. If the end-to-end tolerance is 3 seconds, then the total time spent across all hops must fit within 3 seconds. A's timeout to B must be less than 3 seconds. B's timeout to C must be less than A's timeout to B, minus B's own processing time. These timeouts must be coordinated across the call chain, and in practice, they almost never are. Each team sets their timeouts independently, usually to generous values ("30 seconds should be plenty"), and the result is a system that holds resources open long after anyone cares about the result.

The harder version of this problem: **timeouts that are too aggressive**. If you set B's timeout to C at 100 milliseconds, and C has a normal P99 latency of 80 milliseconds, you'll start timing out on a meaningful percentage of requests during any minor latency variation — a GC pause, a brief network hiccup, normal load variance. This triggers retries, which adds load to C, which increases its latency, which causes more timeouts. You've created the cascade you were trying to prevent.

The right timeout is not a single number. It's a function of the downstream service's latency distribution, and it requires knowing that distribution.

## Retry Amplification

Retries are the second mechanism that turns a localized problem into a system-wide one. They are necessary — transient failures are real, and a single retry often succeeds. But retries have a multiplicative cost that is easy to underestimate.

If User calls A, A calls B, B calls C, and each layer retries failed requests 3 times, then a single failed request at C generates 3 attempts from B. Each of B's failures generates 3 attempts from A. A single user request can produce up to 9 requests at C. With four layers and 3 retries each, it's 27 requests. With more layers or more retries, the number grows exponentially.

This is a **retry storm**, and it happens at the worst possible time. C is already struggling — that's why requests are failing. Retry amplification multiplies the load on C by a factor determined by the depth of the call chain and the retry count at each layer. The service that was slow under normal load is now receiving 10x or 27x the normal request volume. It doesn't recover. It gets worse.

Three mechanics matter for controlling this. **Exponential backoff with jitter** spreads retries over time rather than immediately hammering the failing service. **Retry budgets** cap the percentage of requests that can be retries — if more than, say, 20% of your outgoing requests in the last 10 seconds have been retries, stop retrying and fail fast. **Limiting retries to the edge** means that only the outermost caller retries; intermediate services propagate failures rather than amplifying them. Each of these has tradeoffs — retry budgets can cause you to stop retrying during brief transient errors, and limiting retries to the edge requires that the edge caller have enough context to decide whether retrying is safe (idempotency matters here).

## Why Your Monitoring Doesn't See It

Standard monitoring is built to detect crashes, high error rates, and resource utilization thresholds. Partial failure evades all three.

**Health checks** verify that a process is running and can respond to a probe. A service whose thread pool is 95% exhausted will still respond to a lightweight `/health` endpoint on a dedicated thread. Kubernetes distinguishes between **liveness probes** (is the process running?) and **readiness probes** (can the process serve traffic?), but most readiness probes check something trivial — can the process reach the database? — rather than something meaningful like "is my thread pool saturated?" or "is my P99 latency within expected bounds?" A readiness probe that returns healthy while the service is functionally unable to serve production traffic is worse than no probe at all, because it actively directs traffic to a degraded instance.

**Average latency** is the most common latency metric and the least useful for detecting partial failure. If 95% of requests complete in 5 milliseconds and 5% take 30 seconds, your average latency is about 1.5 seconds. It looks like the service is "a bit slow." In reality, you have a bimodal distribution: most requests are fine, and a subset are catastrophically slow. Those slow requests are consuming resources at a rate thousands of times higher than normal requests. **P99 and P999 latencies** are where partial failure becomes visible, but many dashboards don't display them by default, and many alerting rules are written against P50 or average.

**Error rates** stay low because the requests aren't failing — they're still in flight. A service whose response time has gone from 10 milliseconds to 10 seconds has no elevated error rate. It just has a growing queue of in-flight requests, each one consuming thread pool and connection pool resources. By the time those requests start timing out and the error rate spikes, the thread pool has been saturated for minutes and the cascade is already in progress.

The monitoring that catches partial failure is different in kind: thread pool utilization, connection pool utilization, in-flight request counts, latency percentile distributions, and queue depths. These are the leading indicators. Error rate is a lagging indicator — it tells you the cascade has already happened.

## Where This Gets Practitioners in Trouble

The most common failure mode in practice is not the absence of protective mechanisms — it's protective mechanisms that are configured based on intuition rather than measurement.

Teams set timeouts to round numbers (5 seconds, 30 seconds) without knowing their downstream service's actual latency distribution. They set connection pool sizes to defaults that were appropriate for a different traffic pattern. They implement circuit breakers that open at thresholds chosen arbitrarily, either too sensitive (tripping on normal latency variance) or too permissive (tripping only after the cascade has already propagated). They add retries at every layer of the stack because each team independently decides "we should retry," unaware that combined retries across layers produce exponential amplification.

The deeper trap is **testing only for total failure**. Chaos engineering exercises that kill a pod or shut down a database instance are valuable, but they test the failure mode your system already handles well. The chaos experiment that reveals real weakness is the one that makes a dependency *slow* — inject 5 seconds of latency into 10% of responses from a downstream service and watch what happens to thread pools, queue depths, and upstream response times. Most teams that run this experiment for the first time are surprised by the result.

## The Mental Model

The conceptual shift this post is trying to produce is this: in a distributed system, a component's failure mode is defined not by what happens inside that component, but by what happens to every resource held open while waiting for that component to respond. A crashed process releases resources immediately. A slow process holds them hostage.

Every synchronous call between services is a resource loan: the caller lends a thread, a connection, and memory to the request, and expects them back quickly. When the callee is slow, the loan duration extends, and the caller's capacity to make new loans decreases. When the caller's capacity hits zero, it becomes slow itself, extending the resource loans *its* callers have made. This is the cascade mechanism, and it is an emergent property of the interactions between services, not a bug in any single service.

Designing for partial failure means designing every inter-service interaction with an explicit answer to the question: *what happens to the resources I'm holding if this call takes 1,000 times longer than expected?*

## Key Takeaways

- A slow service is more destructive than a dead service because it holds caller resources (threads, connections, memory) open for the duration of the slow response, while a dead service releases them immediately via connection refusal.

- Little's Law governs why slowness causes resource exhaustion: if response time increases by 1,000x, the number of concurrent in-flight requests increases by 1,000x, overwhelming fixed-size thread and connection pools.

- Cascading failure propagates upstream through the call graph via thread pool and connection pool exhaustion — each layer becomes slow because the layer below it is slow, and no individual component needs to crash for the entire path to become unavailable.

- Timeouts must be coordinated across the call chain as a budget; a 30-second timeout on a call whose end user will wait 3 seconds wastes resources on work nobody will use for 27 seconds.

- Retry amplification is exponential in the depth of the call chain — 3 retries across 3 layers produces up to 27 requests at the leaf, hitting the struggling service with multiplied load at the worst possible time.

- Standard health checks, average latency metrics, and error rate alerts are lagging indicators that miss partial failure; leading indicators are thread pool utilization, connection pool saturation, in-flight request count, and P99/P999 latency.

- The chaos experiment that reveals real system weakness is not killing a dependency but making it slow — injecting latency into a percentage of responses exposes cascade propagation paths that pod-kill tests never touch.

- Designing for partial failure requires an explicit answer, for every synchronous inter-service call, to the question: what happens to every resource I hold open if this call takes 1,000 times longer than expected?

[← Back to Home]({{ "/" | relative_url }})
