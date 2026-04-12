---
layout: post
title: "3.1.3 Metrics: Counters, Gauges, Histograms, and What Gets Lost in Aggregation"
author: "Glenn Lum"
date:   2026-03-17 11:00:00 +0800
categories: journal
image: tier_3.jpg
tags: [Tier 3, Cross-Cutting Disciplines, Depth]
---

Most engineers can name the metric types. Fewer can explain why the choice between them determines what questions your monitoring system is capable of answering. The real cost of misunderstanding metric mechanics is not a system that produces errors — it is a system that produces *plausible-looking data that hides real problems*. A dashboard showing 45ms average latency looks healthy. If 2% of your users are experiencing 8-second timeouts, that number is not just unhelpful — it is actively lying to you. Whether your monitoring system can even surface that problem depends entirely on how the underlying metric stores data and what happens when that data is aggregated across instances and time. That is what this post is about.

## Counters: Monotonic Accumulators

A counter is a value that only goes up. Total requests served, total bytes transferred, total errors encountered — these are all counters. The raw value of a counter is almost never what you care about. Knowing that your service has handled 14,230,891 requests since it started tells you nothing useful. What matters is the **rate of change**: how many requests per second, how many errors per minute.

This is why monitoring systems provide rate functions. In Prometheus, `rate(http_requests_total[5m])` computes the per-second average rate of increase over a five-minute window. The counter stores the cumulative total; the query layer derives the velocity.

The reason counters exist as a distinct type — rather than just recording the current rate directly as a gauge — comes down to **resilience to missed scrapes**. Prometheus pulls metrics from your application at a configured interval, typically every 15 or 30 seconds. If a scrape fails or is delayed, a gauge-based rate measurement would have a gap: you would lose whatever happened during the missed interval. A counter does not have this problem. When the next scrape succeeds, the counter's value reflects everything that happened in the interim. The rate calculation accounts for the elapsed time and produces a reasonable approximation.

Counters do reset — when a process restarts, the counter goes back to zero. Monitoring systems detect this: if the current value is lower than the previous value, it is treated as a reset rather than a massive negative rate. This works reliably in practice, but it means you should never manually decrement a counter in application code. If you need a value that goes both up and down, you need a gauge.

## Gauges: Point-in-Time Snapshots

A gauge records a value that can increase or decrease arbitrarily. CPU usage, memory consumption, queue depth, number of active connections, temperature — these are gauges. The value at the moment of collection *is* the data.

The critical limitation of a gauge is **temporal aliasing**. If your queue depth spikes to 10,000 for three seconds and then drains back to zero, but your scrape interval is 15 seconds, you may never observe the spike. The gauge only records what is true at the instant it is sampled. Everything between samples is invisible.

This matters operationally. Gauges are appropriate for values that change slowly relative to your scrape interval, or for values where the instantaneous state is inherently what you care about (current memory usage, current connection count). They are dangerous for values that spike and recover faster than your collection interval, because your monitoring system will show a flat line during an event that caused real user impact.

## Histograms: Preserving Distribution

Histograms are the most mechanically complex metric type, and the one most often misunderstood. A histogram does not store individual observations. It stores the *shape of the distribution* by counting how many observations fell into each of a set of pre-configured **buckets**.

Here is how it works concretely. Suppose you configure a histogram to track request latency with bucket boundaries at 10ms, 25ms, 50ms, 100ms, 250ms, 500ms, and 1000ms. When a request completes in 73ms, the histogram increments the counters for every bucket whose boundary is ≥ 73ms: the 100ms bucket, the 250ms bucket, the 500ms bucket, and the 1000ms bucket all increment. This is what makes histogram buckets **cumulative** — the 250ms bucket does not mean "requests between 100ms and 250ms." It means "requests that took 250ms or less."

Alongside the buckets, the histogram maintains a `_sum` (the total of all observed values) and a `_count` (the number of observations). A single histogram with seven buckets therefore produces nine time series: one per bucket, plus sum, plus count.

### Estimating Percentiles from Buckets

To compute a percentile — say p99 — from a histogram, you find the bucket where the 99th percentile observation falls and interpolate within it. If you have 1,000 observations and need the 990th, you walk through the cumulative bucket counts until you find which bucket contains that observation, then linearly interpolate within the bucket's range.

This means **the accuracy of histogram-derived percentiles is bounded by your bucket boundaries**. If your buckets jump from 100ms to 250ms and your actual p99 is somewhere in that range, the best you get is a linear interpolation that assumes uniform distribution within the bucket. If most of your traffic clusters at 110ms with a tail at 240ms, that interpolation will be wrong. Bucket placement is an engineering decision that directly determines the precision of your percentile estimates, and getting it right requires knowing — or at least guessing well — what your distribution looks like.

### Why Histograms Are Aggregatable

This is the property that makes histograms fundamentally more useful than the alternative. Because each bucket is a counter, you can **sum histogram buckets across instances** and get a mathematically valid result. If instance A's 100ms bucket has counted 4,500 observations and instance B's 100ms bucket has counted 3,200, the combined 100ms bucket is 7,700. You can then compute percentiles from the aggregated buckets, and the result represents the actual distribution of latency across your entire fleet.

This is not true of pre-computed percentiles. Which brings us to summaries.

## Summaries: Accurate but Isolated

A **summary** computes percentiles client-side, inside your application process. Instead of maintaining bucket counts, the application maintains a sliding window of observations and calculates precise quantiles (p50, p95, p99, etc.) directly. The results are more accurate than histogram estimates for a single process — there is no bucket granularity problem.

The tradeoff is fatal for most production use cases: **summary quantiles cannot be aggregated across instances**. You cannot take the p99 from instance A and the p99 from instance B and combine them into a fleet-wide p99. Not by averaging. Not by taking the max. Not by any mathematical operation. The information required to reconstruct the combined distribution has been discarded during the quantile computation.

This is not a minor inconvenience. Any service running more than one instance — which is effectively every production service — needs fleet-wide percentiles to understand user experience. Summaries cannot provide them.

## What Aggregation Actually Destroys

The aggregation problem is the core of why metric type selection matters, so it is worth walking through a concrete example.

Suppose you have two instances of an API service behind a load balancer. Instance A handles 10,000 requests in a five-minute window, with a p99 of 55ms. Instance B handles 200 requests in the same window, with a p99 of 1,200ms — it is hitting a degraded downstream dependency.

If you average the two p99 values, you get 627ms. If you weight by request volume, you get approximately 78ms. Neither number is the actual p99 across all 10,200 requests. The real p99 is probably close to 55ms, because instance A's volume dominates the distribution and only the slowest two requests across the combined set determine the 99th percentile. But it could also be higher if instance B's slow requests are slow enough to push into the top 1% of the combined population.

The point is not that the math is complicated. The point is that **no operation on pre-computed percentiles can recover the information needed to compute the correct combined percentile**. The distribution has already been collapsed into a single number per instance. The shape is gone.

Histograms avoid this because the bucket counts *are* the distribution, at the resolution of the bucket boundaries. Sum the buckets, and you have the combined distribution. Compute the percentile from that, and you have the right answer (within bucket-resolution error).

This is why the Level 1 post's observation that "average latency hides the experience of slow users" is not just a caveat — it is a structural property of the metric type. An average (mean) is computed from sum and count. It is perfectly aggregatable — you can combine averages correctly using weighted means. But it tells you nothing about the tail. A service with a mean latency of 40ms could have a p99 of 60ms or a p99 of 15,000ms. The average cannot distinguish between these two very different realities.

## The Cardinality Tax

Histograms solve the aggregation problem, but they impose a real cost: **cardinality multiplication**. Every unique combination of labels on a metric produces a separate time series. A counter with labels for `method`, `path`, and `status_code` might produce a few hundred time series. A histogram with the same labels and ten buckets produces twelve time series (ten buckets plus sum and count) for every label combination — so a few hundred becomes a few thousand.

In monitoring systems like Prometheus, cardinality is the primary scaling constraint. High-cardinality metrics — metrics with many distinct label combinations — consume memory, slow queries, and can destabilize the monitoring system itself. An engineer who adds a `user_id` label to a histogram has just created a time series explosion that may take down the monitoring infrastructure before it ever provides useful data.

The practical discipline is: use histograms for metrics where you need distributional information (latency is the canonical example), and use counters or gauges for everything else. Do not histogram metrics where the mean is genuinely sufficient. And ruthlessly control label cardinality on histograms — every label you add multiplies the cost by the number of distinct values that label takes.

### Bucket Boundaries as a Commitment

Choosing histogram bucket boundaries is a decision you make at instrumentation time that constrains your analytical precision permanently (or until you re-deploy with new boundaries and lose continuity with historical data). Buckets that are too coarse give you poor percentile estimates. Buckets that are too fine waste cardinality on resolution you do not need.

The default bucket boundaries in most client libraries (Prometheus's defaults are 5ms, 10ms, 25ms, 50ms, 100ms, 250ms, 500ms, 1s, 2.5s, 5s, 10s) are reasonable starting points for HTTP request latency. They are terrible for a batch job that runs for minutes, or for an in-memory cache lookup that completes in microseconds. Matching bucket boundaries to the expected distribution of the thing you are measuring is not optional — it is a correctness concern.

## The Mental Model

Think of metric type selection as choosing what questions you are *permitted* to answer later. A counter lets you answer questions about rate and total volume. A gauge lets you answer questions about instantaneous state. A histogram lets you answer questions about distribution — but only at the resolution you chose when you configured the buckets, and only if you pay the cardinality cost.

The deepest insight is about what aggregation preserves and what it destroys. Counters and gauges aggregate naturally — sums of counters are valid counters, and averages of gauges are (often) meaningful. Histogram buckets aggregate naturally because they are counters. Pre-computed percentiles and pre-computed averages do not aggregate into valid percentiles — the distributional information has been irreversibly discarded. Every time you see a dashboard showing an averaged percentile across instances, you are looking at a number that is not mathematically what it claims to be.

This is why the choice of metric type is not a cosmetic or stylistic decision. It determines, at instrumentation time, whether your monitoring system will be able to tell you the truth during an incident — or whether it will show you a reassuring number while your users suffer.

## Key Takeaways

- **Counters only go up**, and you almost always care about their rate of change, not their raw value. Their monotonic property makes them resilient to missed scrapes in a way that gauges are not.

- **Gauges capture instantaneous state** and are subject to temporal aliasing: events that spike and recover between scrape intervals are invisible to gauge-based metrics.

- **Histogram buckets are cumulative counters**, not bins. A histogram with *n* buckets produces *n* + 2 time series per unique label combination (buckets plus sum plus count), which makes cardinality control critical.

- **Histogram bucket boundaries determine the precision of your percentile estimates.** Default boundaries are only appropriate for the distribution they were designed for. Mismatched boundaries produce percentile estimates that can be significantly wrong.

- **Pre-computed percentiles (summaries) cannot be aggregated across instances.** No mathematical operation on per-instance p99 values produces a valid fleet-wide p99. Histograms can be aggregated because their buckets are counters.

- **Averaging a percentile across instances produces a number that is not a percentile.** It looks like one, it sits on a dashboard like one, but it has no valid statistical meaning and will mislead you during incidents where load is unevenly distributed.

- **Averages (means) aggregate correctly but hide distributional shape.** A mean latency of 40ms is consistent with both a tight distribution around 40ms and a bimodal distribution where most requests take 5ms and a significant minority take 500ms. Only percentiles (or histograms) can distinguish these cases.

- **Cardinality is the primary cost of histograms.** Every label you add to a histogram multiplies its storage and query cost by the number of distinct values that label takes. High-cardinality labels on histograms are the most common way engineers accidentally destabilize their monitoring infrastructure.

[← Back to Home]({{ "/" | relative_url }})
