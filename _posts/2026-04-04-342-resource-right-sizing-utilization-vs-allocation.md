---
layout: post
title: "3.4.2 Resource Right-Sizing: Utilization vs Allocation"
author: "Glenn Lum"
date:   2026-04-04 11:00:00 +0800
categories: journal
image: tier_3.jpg
tags: [Tier 3, Cross-Cutting Disciplines, Depth]
---

Most engineers understand that right-sizing means "don't pay for resources you're not using." That framing is correct but shallow, and it leads to a specific failure: someone looks at a utilization graph, sees 15% average CPU, halves the instance size, and causes a latency regression or an outage. The problem was not the intent to right-size. The problem was that "utilization" is not one number, allocation is not a continuous dial, and the consequences of sizing down are not the mirror image of the consequences of sizing up. Right-sizing is a decision under uncertainty with asymmetric penalties, and doing it well requires understanding the mechanics of how resources are allocated, how utilization is actually measured, and why those two things interact in ways that averages obscure.

## How Cloud Resource Allocation Actually Works

Cloud resources are not continuous. You cannot buy 2.7 CPUs or 5.3 GB of memory from a cloud provider. Instance types come in discrete sizes — `t3.medium` gives you 2 vCPUs and 4 GB of memory, `t3.large` gives you 2 vCPUs and 8 GB. If your workload needs 5 GB of memory, you pay for 8. This **quantization** means that right-sizing is not a smooth optimization — it is a step function. You are choosing between fixed bundles of CPU, memory, network, and sometimes disk I/O, and the gaps between those bundles are where waste hides or performance problems emerge.

In Kubernetes environments, allocation works differently but has its own discrete mechanics. Each pod declares **resource requests** and **resource limits**:

```yaml
resources:
  requests:
    cpu: "500m"
    memory: "256Mi"
  limits:
    cpu: "1000m"
    memory: "512Mi"
```

The request is what the scheduler uses for bin-packing — it is the guaranteed minimum the pod is promising to need. The limit is the ceiling the pod is allowed to hit. These are two independent levers with very different consequences. Setting requests too high wastes cluster capacity because the scheduler treats that capacity as spoken for even if the pod never uses it. Setting limits too low causes throttling (for CPU) or kills (for memory). Setting requests too low causes noisy-neighbor problems when the node is under contention.

The critical distinction: **requests determine cost, limits determine stability**. When people talk about right-sizing in Kubernetes, they usually mean adjusting requests, because that is what determines how many pods fit on a node and therefore how many nodes you need. But adjusting requests without understanding the relationship to limits and to actual usage patterns is where things break.

## What Utilization Actually Measures (and What It Hides)

When you look at a CPU utilization graph in CloudWatch, Datadog, or Grafana, you are almost always looking at a **time-averaged value over a sampling window**. The default in many monitoring systems is a 1-minute or 5-minute average. This matters enormously.

Consider a web service that handles requests in bursts. For 55 seconds of every minute, the CPU is nearly idle. For 5 seconds, it spikes to 90% handling a batch of requests. The 1-minute average reads as roughly 12% utilization. A 5-minute average might smooth it further. If you right-size based on that 12% number, you will provision a smaller instance that cannot handle the 5-second spike, and your p99 latency will degrade or requests will queue.

This is the **averaging trap**, and it is the single most common mechanical cause of right-sizing failures. The fix is not to avoid averages — it is to look at the right statistics. For right-sizing decisions, you need at minimum:

**Peak utilization** (or a high percentile like p99 or p95) over a representative time window. This tells you the headroom you actually have. If your p99 CPU over the past two weeks is 45%, you have real headroom. If your average is 15% but your p99 is 85%, you do not.

**The distribution shape** of your utilization. A workload that sits at a steady 30% is fundamentally different from one that oscillates between 5% and 80%, even if their averages are similar. The steady workload is a strong right-sizing candidate. The oscillating one requires understanding what drives the peaks before you can safely reduce allocation.

**The time window** of observation. A workload that peaked at 90% once during a monthly batch job looks very different from one that peaks at 90% every day at market open. Right-sizing decisions based on a single week of data will miss monthly patterns, seasonal traffic, and failure-mode spikes (when a downstream dependency is slow and connections pool up).

### CPU and Memory Are Different Problems

This is genuinely non-obvious and causes real incidents: CPU and memory have fundamentally different failure modes when you under-provision.

**CPU is compressible.** When a process needs more CPU than is available, the kernel throttles it. The process runs slower but continues to run. In Kubernetes, exceeding CPU limits causes CFS throttling — the scheduler simply stops giving the process CPU time for portions of each scheduling period. The symptom is increased latency, not failure.

**Memory is incompressible.** When a process exceeds its memory allocation, the outcome is not "slower." It is termination. The OOM killer fires, the pod restarts, in-flight requests are dropped. There is no graceful degradation.

This asymmetry means that the right-sizing strategy for CPU and memory must be different. You can right-size CPU more aggressively because the downside is latency degradation, which is observable and recoverable. Memory right-sizing requires wider safety margins because the downside is hard failure. A workload with 40% average memory utilization and a p99 of 65% looks like it has headroom, but if there is a memory leak that manifests under specific conditions, or a request payload that causes a spike, you need to account for that in a way you do not need to for CPU.

### The Kubernetes Scheduling Tax

In Kubernetes, there is a secondary cost to over-requesting that is invisible on per-pod metrics. Every pod's resource request is subtracted from the node's allocatable capacity, whether or not the pod uses those resources. If ten pods each request 1 CPU but only use 200m, the scheduler sees 10 CPUs as consumed. The node is "full" at 20% actual utilization. You then need more nodes to schedule new pods, and each of those nodes carries its own overhead (kubelet, kube-proxy, daemonsets, OS reserved memory).

This means that in containerized environments, the aggregate over-request across all pods is often a larger cost driver than any single workload. Right-sizing is not just about individual services — it is about **recovering schedulable capacity** across the cluster. A 200m reduction in CPU requests across 500 pods recovers 100 CPUs of schedulable capacity, which might eliminate several nodes entirely.

## Why Engineers Overprovision (And Why It Is Rational)

Overprovisioning is not laziness. It is the predictable outcome of an incentive structure where the costs of under-provisioning are immediate, visible, and personal, while the costs of over-provisioning are diffuse, delayed, and organizational.

If you under-provision a service and it falls over at 3 AM, you get paged. Your name is on the incident. The RCA is traceable to your sizing decision. If you over-provision the same service by 4x, nothing happens. There is no alert for "this service is wasting money." The cost appears as a line item in a cloud bill that a finance team reviews quarterly. Nobody gets paged.

This is compounded by the fact that right-sizing is a **recurring maintenance task**, not a one-time decision. Traffic patterns change. Code changes alter resource profiles. A dependency change can shift a workload from CPU-bound to memory-bound. The engineer who right-sizes a service today accepts an ongoing obligation to monitor it and re-evaluate — or accepts the risk that the workload will grow into its new, tighter allocation and cause problems.

Organizations that want right-sizing to happen must change the incentive structure: make waste visible per-team, make right-sizing recommendations automatic, and ensure that the tooling exists to make the process low-effort and reversible.

## Tradeoffs and Failure Modes

### Right-Sizing Into a Latency Cliff

The most common failure: a team sees low average utilization, reduces instance size, and does not notice the impact because average latency barely moves. But p99 latency doubles. The tail is where CPU contention manifests. Customers on the unlucky end of the distribution experience the degradation, support tickets trickle in, and nobody connects them to the sizing change from two weeks ago because the dashboards show "normal" averages.

The defense is to measure latency percentiles before and after any sizing change and to hold the change for at least one full traffic cycle (daily, weekly, or monthly depending on the workload).

### The Vertical Scaling Trap

Right-sizing by moving to a smaller instance type sometimes triggers a qualitative change, not just a quantitative one. Moving from `m5.xlarge` to `m5.large` halves CPU and memory, but it also halves network bandwidth and EBS throughput. If your workload was not CPU-bound but was occasionally hitting network limits, the smaller instance may fail in ways that CPU and memory metrics never predicted.

### Over-Automation Without Guardrails

Automated right-sizing tools (Kubernetes VPA, cloud provider recommendations) generate suggestions based on observed usage. They are useful as input but dangerous as policy. A VPA that automatically adjusts requests based on a 24-hour window will confidently downsize a service on Tuesday that needs 3x the resources on Saturday for a weekly batch job. Automated right-sizing without minimum bounds, change rate limits, and human review of outlier recommendations will eventually cause an outage.

### The Organizational Stall

Right-sizing analysis often reveals that 80% of the waste comes from 20% of the workloads — and those workloads are owned by teams that are busy, understaffed, or uninterested. The mechanical knowledge of what to resize is rarely the bottleneck. The bottleneck is organizational: who prioritizes the work, who bears the risk, and who is accountable for the outcome. Right-sizing programs that generate recommendations without a mechanism for adoption produce reports, not savings.

## The Mental Model

Think of right-sizing not as "find the minimum" but as **choosing the right position on a risk-cost curve**. On one end, you have maximum overprovisioning: high cost, near-zero risk of resource-related incidents. On the other, you have exact-fit provisioning: minimum cost, high sensitivity to any variance in load. The optimal position depends on the workload's criticality, its variability, the observability you have into its behavior, and how quickly you can scale if you get it wrong.

The core conceptual shift is this: utilization is not a single number, and allocation is not a smooth knob. Right-sizing is the practice of making informed bets about where a workload sits on that curve, using distributional data about actual usage, with full awareness that CPU and memory fail differently, that averages lie, and that the organizational cost of making the change is part of the equation.

## Key Takeaways

- **Utilization averages hide the information you need most.** Right-sizing decisions should be based on peak or p95/p99 utilization over a representative time window, not averages, because averages smooth out the spikes that actually determine whether your allocation is sufficient.

- **CPU and memory have asymmetric failure modes.** CPU under-provisioning causes throttling and latency degradation; memory under-provisioning causes OOM kills and hard restarts. Right-size memory more conservatively than CPU.

- **In Kubernetes, resource requests determine cost, not resource limits.** Over-requesting across many pods wastes schedulable capacity cluster-wide, often requiring more nodes even when actual utilization is low.

- **Cloud resources are quantized, not continuous.** Instance types bundle CPU, memory, network, and I/O in fixed ratios. A sizing change can affect dimensions you were not targeting, including network bandwidth and disk throughput.

- **Overprovisioning is rational under most default incentive structures.** Engineers are personally penalized for under-provisioning (outages) and organizationally invisible when over-provisioning (cloud bill). Changing this requires making per-team waste visible and right-sizing low-effort.

- **Automated right-sizing tools are useful as input, dangerous as policy.** Without minimum bounds, rate limits, and awareness of non-daily traffic patterns, automation will confidently downsize workloads that need burst capacity on longer cycles.

- **Right-sizing is a recurring obligation, not a one-time fix.** Traffic patterns, code changes, and dependency shifts alter resource profiles over time. A service right-sized six months ago may already be misaligned.

- **The bottleneck for right-sizing is usually organizational, not technical.** Generating recommendations is easy; getting teams to prioritize, execute, and monitor the changes is where most right-sizing programs stall.


[← Back to Home]({{ "/" | relative_url }})
