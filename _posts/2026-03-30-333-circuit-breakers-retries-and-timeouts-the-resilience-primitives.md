---
layout: post
title: "3.3.3 Circuit Breakers, Retries, and Timeouts: The Resilience Primitives"
author: "Glenn Lum"
date:   2026-03-30 11:00:00 +0800
categories: journal
image: tier_3.jpg
tags: [Tier 3, Cross-Cutting Disciplines, Depth]
---

Most engineers can describe what retries, timeouts, and circuit breakers do. Retries repeat failed requests. Timeouts cap how long you wait. Circuit breakers stop calling a failing service. That surface understanding is sufficient right up until the moment a downstream service starts responding slowly, your retry logic triples the load on it, your generous timeouts hold open thousands of connections waiting for responses that will never come, and your circuit breaker — configured with defaults you never revisited — hasn't tripped because it's measuring the wrong thing. The system doesn't just fail; it fails in a way that's *caused by the resilience mechanisms themselves*. Understanding these three patterns individually is straightforward. Understanding how they interact — how they amplify or cancel each other's effects — is where the actual engineering lives.

## Timeouts: The Cost Bound

A timeout is not a single concept. There are at least three distinct timeouts in a typical HTTP call, and conflating them leads to misconfigurations that are invisible until they cause an outage.

**Connection timeout** bounds how long the client waits to establish a TCP connection. If the remote host is unreachable or its connection queue is full, this is the timer that fires. Connection timeouts should almost always be short — hundreds of milliseconds, not seconds. If a service can't accept a connection within 500ms, it is either down or so overloaded that waiting longer won't help.

**Read timeout** (sometimes called socket timeout) bounds how long the client waits for data after the connection is established and the request is sent. This is where most timeout misconfiguration happens. A read timeout that's too short cuts off legitimate slow responses. A read timeout that's too long holds the calling thread, connection, and socket open while a degraded service takes 30 seconds to respond with an error.

**Overall request timeout** bounds the total wall-clock time for the entire operation, including connection, TLS handshake, sending the request, and reading the response. Some HTTP clients expose this directly; others require you to compose it from connection and read timeouts.

The non-obvious mechanical consequence of a too-generous timeout is **resource exhaustion at the caller**. Consider a service that normally responds in 50ms. You set a read timeout of 30 seconds because you "don't want to cut off valid responses." The downstream service starts degrading — responses now take 25 seconds before returning an error. Your service handles 500 requests per second. Each request now holds a thread (or connection, or goroutine — the specific resource depends on your runtime) for 25 seconds instead of 50ms. Where you previously needed roughly 25 concurrent connections to handle your load, you now need 12,500. Your connection pool is exhausted within seconds. Requests that have nothing to do with the degraded service start failing because they can't acquire connections from the pool. The downstream service's slowness has propagated *upstream* through your timeout configuration.

This is the mechanism behind most cascading failures: not errors propagating down a call chain, but **latency propagating up one**. Errors are fast. Slowness is what kills you.

### Timeout Budgets in Service Chains

When Service A calls Service B, which calls Service C, timeouts must be set with awareness of the full chain. If A gives B a 5-second timeout, and B gives C a 5-second timeout, then B can time out waiting for C and still have no time left to do anything useful before A times out on B. The timeout at each layer must be strictly less than the timeout of the layer above it, leaving room for the intermediary service's own processing time and any retry attempts.

**Deadline propagation** is the pattern where the outermost timeout is set at the edge of the system, and each downstream call receives the *remaining* budget rather than its own independent timeout. gRPC does this natively through its deadline mechanism: when you set a deadline on a gRPC call, that deadline is propagated through metadata to every downstream service in the chain, and each service can check how much time remains before starting expensive work. If you're not using a framework with built-in deadline propagation, you need to implement this logic yourself — or accept that your timeouts across service boundaries are uncoordinated, which means they will interact in surprising ways under load.

## Retries: The Load Multiplier

A retry is the simplest resilience pattern and the most dangerous. The basic mechanic: if a request fails, send it again. The assumption is that the failure was **transient** — a blip in the network, a single unlucky routing to an overloaded instance, a momentary resource contention. For genuinely transient failures, retries work beautifully. The problem is that retries don't know whether a failure is transient.

### The Amplification Problem

When a downstream service is failing because it's overloaded, retries increase the load on it. Here's the arithmetic. Suppose Service A sends 1,000 requests per second to Service B. Service B starts failing 50% of requests. With a naive retry policy of "retry once on failure," Service A now sends 1,500 requests per second to Service B (1,000 original + 500 retries). Service B, already overloaded, now fails 80% of requests. Service A retries those too: now it's sending 1,800 requests per second. The service that was struggling under 1,000 RPS is now receiving nearly double that, *entirely because of the mechanism designed to improve reliability*.

In a deep call chain, this multiplies further. If Service A calls B calls C, and each layer retries 3 times, a single failure at C can generate up to 9 requests at C (3 retries from B × 3 retries from A). With five layers and 3 retries each, a single user request can generate 243 downstream requests. This is a **retry storm**, and it is the single most common way that resilience patterns cause outages rather than prevent them.

### Taming Retries

Three mechanisms make retries safe:

**Exponential backoff with jitter** spreads retry attempts over time rather than hammering the failing service immediately. The backoff increases the delay between retries exponentially (100ms, 200ms, 400ms...), and jitter adds randomness to prevent **thundering herd** behavior where many clients that started failing at the same time all retry at the same time. Without jitter, backoff just synchronizes the retry bursts at longer intervals.

**Retry budgets** cap the *proportion* of traffic that can be retries. Instead of "retry each failed request 3 times," a retry budget says "no more than 20% of our total requests to this service can be retries." When the service is healthy and failures are rare, individual requests get retried. When the service is failing broadly, the budget is exhausted quickly and most failures are not retried. This directly prevents the amplification spiral described above. Envoy, Linkerd, and other service mesh proxies support retry budgets natively.

**Idempotency awareness** determines *which* requests are safe to retry. Retrying a GET request is almost always safe. Retrying a POST that creates an order is dangerous unless the receiving service implements idempotency (typically via an idempotency key that deduplicates requests). Naive retry logic that doesn't distinguish between idempotent and non-idempotent operations will create duplicate records, double charges, or other data corruption under failure conditions.

## Circuit Breakers: The Negative Feedback Loop

A circuit breaker is a state machine with three states, and its purpose is to create a **fast failure path** that prevents a degraded downstream service from dragging down its callers.

**Closed** is the normal state. All requests pass through to the downstream service. The circuit breaker monitors the results — tracking failure rate, slow response rate, or both over a sliding window.

**Open** is the tripped state. The circuit breaker has determined the downstream service is unhealthy. All requests immediately fail without being sent. This is the critical behavior: instead of waiting for a timeout on a service that you already know is failing, you fail in microseconds. This protects the caller's resources (threads, connections, memory) and stops adding load to the downstream service, giving it room to recover.

**Half-open** is the probe state. After a configured sleep window (say, 30 seconds), the circuit breaker allows a limited number of requests through to test whether the downstream service has recovered. If those probe requests succeed, the circuit breaker transitions back to Closed. If they fail, it goes back to Open and resets the sleep window.

### What the Circuit Breaker Measures

The trip condition is the most important configuration decision. Common approaches:

**Failure rate threshold** trips the breaker when the percentage of failed requests exceeds a threshold (e.g., 50% failure rate over the last 10 seconds). This works well for services that fail cleanly with error responses. It works poorly for services that degrade by becoming slow — if the service returns 200 OK after 25 seconds, the failure rate is zero, but the service is effectively down.

**Slow call rate threshold** trips the breaker when the percentage of calls exceeding a duration threshold is too high. This catches the degradation pattern that failure rate alone misses.

**Count-based vs. time-based sliding windows** determine how many observations the breaker needs before making a decision. A count-based window (last 100 requests) can react quickly to sudden failures but may trip spuriously during low-traffic periods when a few errors in a small sample look like a high failure rate. A time-based window (last 60 seconds) provides more stable measurements but reacts more slowly.

The **minimum number of calls** setting prevents the breaker from tripping when the sample size is too small. If you've only sent 3 requests in the last window, a 66% failure rate (2 out of 3) is probably noise, not a real outage. Setting a minimum call threshold (e.g., don't evaluate until you've seen at least 20 requests) prevents false trips during low-traffic periods.

## How the Three Patterns Compose

The three patterns are not independent features you bolt onto a service. They form a coherent system that must be configured as a unit.

The **timeout** determines how long you're willing to wait for a single attempt. The **retry policy** determines how many attempts you'll make and how you space them. The **circuit breaker** determines when you stop attempting altogether.

Consider the full sequence: Service A calls Service B with a 2-second timeout, a retry policy of 2 retries with exponential backoff (200ms, 400ms), and a circuit breaker that trips at 50% failure rate over 10 seconds. A request to B hangs. After 2 seconds, the timeout fires. The retry policy triggers a second attempt, waits 200ms, then sends it. That attempt also times out after 2 seconds. A third attempt waits 400ms, then times out after 2 seconds. Total elapsed time for this single call: roughly 7 seconds. If Service A itself has a 5-second timeout from its caller, the second retry will never complete — Service A will be timed out first. The retry policy and the timeout budget are in conflict.

Meanwhile, if 50% of calls to Service B are timing out, the circuit breaker trips. Subsequent requests fail immediately — in microseconds, not seconds. The caller gets an error fast enough to serve a fallback response within its own timeout budget. *This* is the value of the circuit breaker: not just protecting the downstream service, but giving the upstream service its time back.

## Where the Patterns Break

### Retries Without Circuit Breakers

This is the most common and most damaging misconfiguration. Every major cloud provider has published post-mortems involving retry storms. The pattern is always the same: a service degrades, clients retry aggressively, the retries overwhelm the service, the service degrades further, and the positive feedback loop continues until the service is completely down. A circuit breaker converts this positive feedback loop (more failures → more retries → more load → more failures) into a negative feedback loop (more failures → breaker opens → less load → recovery possible).

### Timeouts Set at Framework Defaults

Many HTTP clients ship with default timeouts of 30 seconds, 60 seconds, or — in some cases — no timeout at all. These defaults are almost never appropriate for service-to-service communication. A service that calls three downstream dependencies, each with a 30-second default timeout, can hang for 90 seconds on a single request before failing. If that service has its own callers, those callers are now also hanging. Timeouts should be set based on observed P99 latency of the downstream service, plus a margin — not based on framework defaults.

### Circuit Breaker Sensitivity Mismatch

A circuit breaker that's too sensitive trips on normal variance. A service with a steady-state error rate of 2% will regularly trip a breaker set at 3%. A circuit breaker that's too insensitive doesn't trip until the calling service is already overwhelmed. Getting this right requires knowing the normal failure baseline of your dependencies and setting thresholds above that baseline but below the point where failures start impacting your own SLO. This is an empirical tuning problem, not a theoretical one. You need production metrics to do it well.

### Half-Open Thundering Herd

When a circuit breaker transitions to half-open, it sends probe requests to test recovery. If you have 50 instances of Service A all circuit-broken against Service B, and they all transition to half-open at roughly the same time, Service B receives a burst of probe traffic from all 50 instances simultaneously. If B has just barely recovered, this probe burst can push it back into failure. Adding jitter to the sleep window duration — so that different instances probe at different times — prevents this.

## The Mental Model

Think of these three patterns as a control system. The timeout is the **cost bound** — it caps the maximum resources any single request can consume. The retry is the **optimistic recovery** — it assumes the failure was transient and tries again, but in doing so it multiplies load. The circuit breaker is the **governor** — it monitors the aggregate result of your requests and, when it detects systemic failure, it shuts off the load to prevent retries from making the problem worse.

The key conceptual shift is this: retries are a positive feedback mechanism (failure causes more load, which causes more failure), and a circuit breaker is the negative feedback mechanism that counterbalances it. Without the circuit breaker, retries don't just fail to help — they actively accelerate the collapse of a degraded service. Without retries, you lose the ability to transparently recover from the transient errors that represent the vast majority of failures in distributed systems. Without appropriate timeouts, neither pattern matters because your resources are pinned waiting for responses that may never come. The three patterns don't just complement each other — they are incomplete without each other.

## Key Takeaways

- **Timeouts are the most fundamental resilience primitive** because they bound the cost of a single failed interaction; a missing or overly generous timeout turns a downstream slowdown into upstream resource exhaustion.
- **Latency, not errors, is what propagates cascading failures.** An error response takes microseconds to process; a hanging request holds threads, connections, and memory for the duration of the timeout.
- **Naive retries on a degraded service amplify load in direct proportion to the retry count**, turning a partial failure into a complete outage through a positive feedback loop.
- **Retry budgets (capping retries as a percentage of total traffic) are fundamentally safer than per-request retry counts** because they self-limit under systemic failure conditions instead of amplifying them.
- **A circuit breaker is a state machine with three states (closed, open, half-open)**, and its trip condition must be tuned to the specific dependency's normal failure baseline — not set to a textbook default.
- **Circuit breakers must measure slow calls, not just errors**, or they will miss the most common degradation pattern: a service that returns 200 OK but takes 30 seconds to do it.
- **Timeouts across a service call chain must be coordinated**: each layer's timeout must be shorter than the layer above it, or retries at intermediate layers will be silently killed by upstream timeouts before they complete.
- **These three patterns form a control system, not a feature checklist.** Retries without a circuit breaker are actively dangerous, timeouts without retries are unnecessarily brittle, and circuit breakers without sensible timeouts have nothing meaningful to measure.

[← Back to Home]({{ "/" | relative_url }})
