---
layout: post
title: "1.2.6 Compute Resource Models: CPU, Memory, and I/O as First-Class Constraints"
author: "Glenn Lum"
date:   2026-01-26 11:00:00 +0800
categories: journal
image: tier_1.jpg
tags: [Tier 1,Foundation Knowledge,Depth]
---

Most engineers treat CPU, memory, and I/O as configuration fields — numbers you plug into a deployment spec or instance type selector. You set `cpu: "500m"` and `memory: "256Mi"`, maybe because a teammate suggested those values, maybe because they were copy-pasted from a boilerplate. The workload runs. Nobody asks questions until something breaks: tail latency spikes inexplicably, a pod gets killed with no warning, or a service that handles ten requests per second falls over at twelve. When it does break, the debugging is painful precisely because the engineer never built an intuition for *which resource was the actual constraint* and *how that resource behaves when it runs out*. CPU, memory, and I/O are not interchangeable "resources" with a shared behavior model. They are fundamentally different physical constraints with different contention mechanics, different failure modes, and different observability signatures. Understanding those differences is the prerequisite for right-sizing anything.

## CPU: A Compressible, Time-Shared Resource

CPU is time. Specifically, it is access to a processor's execution cycles, shared across all processes competing for them. The key property that governs everything else: **CPU is compressible**. When a process cannot get the CPU time it wants, it does not crash. It slows down. It waits its turn. This makes CPU contention insidious — your workload degrades gradually, and the degradation shows up as latency, not errors.

On Linux, the scheduler responsible for dividing CPU time among processes is the **Completely Fair Scheduler (CFS)**. CFS assigns each process a *weight* proportional to its priority, then distributes available CPU time accordingly. When you set a CPU request in a container orchestrator, you are setting that weight. A container requesting 500 millicores gets half the scheduling weight of one requesting 1000 millicores. This matters only during contention: if the host has spare cycles, both containers can burst beyond their requested share.

CPU *limits* work differently. They impose a hard ceiling using a mechanism called **CFS bandwidth control**. The scheduler gives each cgroup a quota of microseconds per a defined period (typically 100ms). A container with a limit of 500 millicores gets 50ms of CPU time per 100ms period. If it exhausts that quota before the period ends, the scheduler **throttles** it — the container's threads are paused until the next period begins, even if the CPU is otherwise idle.

This throttling behavior is the source of a common, painful production issue. Consider a service that handles HTTP requests with a p50 latency of 5ms. Under normal load, it rarely hits its CPU limit. Under a burst, several requests arrive simultaneously, the container burns through its 50ms quota in the first 30ms of a period, and the remaining in-flight requests stall for 70ms waiting for the next period to start. The p99 latency jumps from 20ms to 90ms. From the application's perspective, nothing went wrong — no errors, no crashes. From the user's perspective, the service became unusable. The only observable signal is the throttling metric (`nr_throttled` and `throttled_time` in the cgroup's cpu.stat), which most teams do not monitor until they have already been burned by it.

A CPU-bound workload is one where adding more CPU time directly reduces execution time: mathematical computation, serialization/deserialization, compression, image processing. The defining characteristic is that the process is *runnable* — it has work to do and is just waiting for the processor. You can identify this by looking at CPU utilization relative to the limit and checking for throttling. If your container is using 95% of its CPU limit and your latency is climbing, you are CPU-bound.

## Memory: An Incompressible, Cliff-Edge Resource

Memory is space. Specifically, it is addressable bytes of RAM. The defining property: **memory is incompressible**. When a process needs more memory than is available, the system cannot simply slow it down and ask it to wait. Something must give. Either the kernel evicts pages to make room, or it kills a process to reclaim memory. There is no graceful degradation — there is a cliff.

When a process allocates memory, it is working with **virtual memory** — addresses that the kernel maps to physical RAM on demand. The actual physical memory consumed is the **resident set size (RSS)**. A process might have a virtual address space of 4GB but only 200MB resident in physical memory. What matters for resource accounting is the RSS (plus cache and other kernel-attributed memory for that cgroup), because that is what is actually occupying the finite physical resource.

In a container orchestrator, a memory *request* tells the scheduler how much memory to *guarantee* — it influences which node the container is placed on. A memory *limit* tells the kernel the absolute maximum. When a container's memory usage (as tracked by the cgroup) reaches its limit, the kernel's **OOM (Out-Of-Memory) killer** terminates a process within that cgroup. The container restarts (if your orchestrator is configured that way), users see errors, and in-flight work is lost.

This cliff-edge behavior makes memory the most dangerous resource to get wrong. Consider a Java service with a heap configured to 512MB running in a container with a 600MB memory limit. The JVM's heap is 512MB, but the JVM also needs memory for thread stacks, the metaspace (class metadata), JIT compiler buffers, native libraries, and the garbage collector itself. Total JVM memory consumption can easily reach 650MB, which exceeds the container's 600MB limit. The OOM killer fires. The container restarts. It loads state back into memory, climbs back to 650MB, and gets killed again. This crash loop is entirely predictable from the mechanics, but engineers routinely set memory limits based on heap size alone without accounting for off-heap consumption.

A memory-bound workload is one constrained by how much data it can hold resident at once: large in-memory caches, services that buffer large request/response payloads, batch jobs processing datasets that don't fit in available RAM. The symptom is not slowness (that's CPU) — it's either OOM kills or, when the system starts swapping, catastrophic latency degradation as every memory access potentially hits disk.

### The Asymmetry Between CPU and Memory Failure

This asymmetry is worth making explicit. CPU overcommitment causes degradation: things get slower. Memory overcommitment causes failure: things get killed. This means the consequences of getting your resource model wrong depend entirely on *which* resource you got wrong. Teams that set aggressive limits on CPU get latency surprises. Teams that set aggressive limits on memory get availability incidents. The operational posture should be different for each: you can afford tighter CPU limits if you accept some throttling during peaks, but memory limits need headroom because the failure mode is binary.

## I/O: The Queue You Cannot See

I/O encompasses disk reads and writes, network sends and receives, and any interaction where the process is waiting on an external system. The key property: **I/O-bound workloads are blocked, not busy**. The CPU is not doing useful work — it is waiting for data to arrive from a disk, a network socket, or a downstream service.

This creates a counterintuitive observability signature. An I/O-bound service under load can show low CPU utilization. An engineer looking at a dashboard sees CPU at 15% and concludes there is plenty of headroom. In reality, the service is saturated — every thread is blocked waiting on disk or network, and adding more CPU will not help at all. The correct diagnostic signals are **I/O wait time** (shown as `iowait` in system-level CPU breakdowns, representing time the CPU spent idle while waiting for I/O), disk latency and throughput metrics, and network socket queue depths.

Disk I/O contention manifests in two distinct ways. **Throughput-bound** workloads need to move large volumes of data — sequential reads for analytics, log shipping, large file transfers. They saturate the disk's bandwidth. **Latency-bound** workloads need many small random reads or writes — database queries hitting indexes, key-value store lookups. They saturate the disk's IOPS (I/O operations per second). An SSD might provide 500MB/s throughput and 100,000 IOPS, but a workload doing 4KB random reads will hit the IOPS ceiling long before the throughput ceiling. Choosing storage based on throughput when your workload is latency-bound is a common and expensive mistake.

Network I/O introduces another dimension: the latency and reliability of downstream dependencies. A service making synchronous calls to a database with a p99 latency of 50ms will spend the overwhelming majority of its wall-clock time waiting, regardless of how fast its CPU-bound code is. This is why architectures that involve many synchronous service-to-service calls are fundamentally I/O-bound systems, even if each individual service considers itself compute-intensive.

### Resource Interaction: When Bottlenecks Shift

In practice, workloads are rarely purely CPU-bound, memory-bound, or I/O-bound. Bottlenecks shift under load. A service at low request rates might be I/O-bound, spending most time waiting for database queries. As request rates increase, more data gets cached in memory, reducing I/O wait — but now the CPU is doing more work deserializing and processing cached results. Push further, and the growing number of in-flight requests inflates memory usage until the process approaches its memory limit. Garbage collection kicks in more frequently (a CPU cost triggered by memory pressure), stealing cycles from request processing and reintroducing CPU as the bottleneck.

This dynamic shifting is why static resource allocation based on a single load test at a single traffic level is unreliable. The resource profile of a workload at 30% capacity is often qualitatively different from its profile at 85% capacity.

## Where Resource Models Break in Practice

**The overcommitment trap.** Orchestrators allow you to request fewer resources than the node actually has — this is overcommitment, and it's how you get utilization above 50%. But overcommitment works only when not all workloads peak simultaneously. If they do, CPU-bound workloads all throttle at once (correlated latency spikes across services), and memory-bound workloads trigger cascading OOM kills. Cluster-level resource utilization metrics look healthy right up until this correlated peak, which is why per-pod and per-container metrics are essential.

**Confusing limits with right-sizing.** Setting a CPU limit of 2 cores does not mean the workload *needs* 2 cores. It means it is *allowed* 2 cores. Without profiling under realistic load, limits are guesses. The common failure pattern is setting limits generously during initial deployment ("give it plenty of room"), never revisiting them, and then paying 3x in compute costs because every instance of the service reserves resources it never uses. On the other end, setting limits too tight based on average usage rather than peak usage produces intermittent failures that are difficult to reproduce in testing because test environments rarely replicate production traffic patterns.

**Ignoring I/O in capacity planning.** Most resource discussions focus exclusively on CPU and memory because those are the resources container orchestrators expose as first-class scheduling constraints. I/O is often unmanaged — there are no default request/limit fields for disk IOPS or network bandwidth in a standard pod spec. This does not mean I/O contention does not exist. It means it is invisible to the scheduler. Two pods on the same node competing for the same underlying disk can starve each other in ways that the orchestrator's resource model cannot detect or prevent.

**The GC death spiral.** In garbage-collected languages (Java, Go, C#), memory pressure triggers garbage collection, which consumes CPU. If the container has tight CPU limits, GC pauses become longer because the collector is throttled. Longer pauses mean more objects accumulate, increasing memory pressure further. This feedback loop between memory and CPU constraints produces symptoms (high latency, eventual OOM kill) that are nearly impossible to diagnose if you are looking at each resource in isolation.

## The Model to Carry Forward

Every compute workload is bounded by some resource at any given moment. The resource it's bounded by determines how it degrades, how you diagnose it, and how you fix it. CPU contention slows you down. Memory exhaustion kills you. I/O contention blocks you. These are not three flavors of the same problem — they are three different problems with different observability signals, different failure modes, and different remediation strategies.

The mental model is this: before you can right-size a workload, you must first identify which resource is the binding constraint under realistic load. Before you can interpret a performance problem, you must know whether the process is *running and throttled* (CPU), *running and about to be killed* (memory), or *idle and waiting* (I/O). The resource model is not a configuration exercise. It is a diagnostic framework. Every decision you make about instance types, container limits, autoscaling thresholds, and storage tiers is downstream of this understanding.

## Key Takeaways

- **CPU is compressible; memory is not.** CPU contention causes gradual latency degradation through throttling. Memory contention causes hard failures through OOM kills. Your tolerance for tight limits should reflect this asymmetry.
- **CPU throttling is invisible unless you monitor it explicitly.** CFS bandwidth control can pause your container's threads even when the host CPU is idle, and the only evidence is in cgroup-level throttling counters that most default dashboards do not surface.
- **Memory limits must account for total process memory, not just application-level allocation.** JVM off-heap memory, thread stacks, native libraries, and memory-mapped files all count against the cgroup limit.
- **Low CPU utilization does not mean the workload has headroom.** An I/O-bound service waiting on disk or network will show idle CPU while being completely saturated. Diagnose with I/O wait time and queue depths, not CPU percentage.
- **Bottlenecks shift under load.** A workload that is I/O-bound at low traffic can become CPU-bound or memory-bound at high traffic. Static resource allocation based on a single traffic level will be wrong at other levels.
- **Container orchestrators do not manage I/O contention by default.** Disk IOPS and network bandwidth are not first-class scheduling constraints in most platforms, which means I/O-bound workloads can suffer noisy-neighbor effects the scheduler cannot see or prevent.
- **The GC death spiral is a cross-resource failure mode.** Memory pressure increases garbage collection, which consumes CPU; CPU throttling slows garbage collection, which increases memory pressure. Diagnosing this requires looking at CPU and memory together.
- **Resource configuration is not a one-time decision.** Traffic patterns change, code changes, and dependency performance changes. Resource profiles must be observed continuously, not set at deploy time and forgotten.

[← Back to Home]({{ "/" | relative_url }})
