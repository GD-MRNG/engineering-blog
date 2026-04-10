---
layout: post
title: "1.2.4 Container Orchestration: The Scheduling Problem"
author: "Glenn Lum"
date:   2026-01-24 11:00:00 +0800
categories: journal
image: tier_1.jpg
tags: [Tier 1,Foundation Knowledge,Depth]
---

Most engineers interact with container orchestration as a deployment target. You write a manifest, apply it, and pods appear. When things work, the orchestrator feels like a black box you don't need to open. When things break — a pod stuck in Pending for ten minutes, a service unreachable after a node failure, containers getting OOM-killed on a node that appeared to have free memory — the black box becomes the problem. The gap between "I use Kubernetes" and "I understand what the scheduler is actually doing" is where most operational surprises live.

The Level 1 post established that orchestration manages scheduling, scaling, networking, health checking, and rollout management. This post is about the machinery underneath those words. Specifically: how does an orchestrator decide where to place a workload, what information drives that decision, what happens when reality diverges from intent, and where do the mechanics create problems that aren't obvious from the API surface?

## The Problem the Scheduler Solves

Running a container on a single host is a solved problem. You pull an image, start a process, map some ports. The difficulty begins the moment you have more workloads than one machine can handle, or the moment you need any workload to survive the failure of the machine it's running on.

At that point, you have a **cluster** — a pool of machines (nodes) available to run workloads. And you have a question that sounds simple but is computationally hard: given N workloads with different resource needs, constraints, and priorities, and M nodes with different capacities and current utilization, which workload goes where?

This is a variant of the **bin packing problem**, which is NP-hard in the general case. You can't compute the globally optimal placement in reasonable time for any non-trivial cluster. Every orchestrator uses heuristics — good-enough solutions computed fast — rather than optimal ones computed slowly. Understanding that the scheduler is making approximations, not guarantees, is the first conceptual shift that matters.

## The Reconciliation Loop

Before diving into scheduling mechanics, you need to understand the execution model that drives them. Orchestrators like Kubernetes don't operate as a sequence of imperative commands. They operate as **control loops**.

You declare a desired state: "there should be three replicas of service-A, each requesting 512Mi of memory and 250m of CPU." This declaration is written to a central data store (in Kubernetes, etcd). A set of independent controllers continuously watch for discrepancies between desired state and observed state. When a discrepancy exists, a controller takes action to close the gap.

This is not one loop. It's many. The **ReplicaSet controller** notices that three replicas are desired but only two pods exist, so it creates a third pod object. The **scheduler** notices that a pod exists with no node assignment, so it selects a node and binds the pod. The **kubelet** on that node notices a pod bound to it that isn't running, so it pulls the image and starts the container. Each controller is responsible for one narrow transition, and they operate independently and asynchronously.

This architecture has a critical implication: there is no single moment where "deployment happens." Convergence toward desired state is eventual. A pod can exist as an API object for seconds before the scheduler assigns it to a node, and more seconds pass before the kubelet starts the container, and more before health checks pass and the pod starts receiving traffic. When someone says a deployment "takes too long," the latency lives in the gaps between these independent loops, not in any single operation.

## How Scheduling Decisions Are Made

When an unscheduled pod appears, the scheduler runs a two-phase process: **filtering**, then **scoring**.

**Filtering** eliminates nodes that cannot run the pod. The reasons a node gets filtered out are concrete: it doesn't have enough allocatable CPU or memory to satisfy the pod's resource requests; it has a **taint** that the pod doesn't tolerate; it doesn't match a required **node selector** or **node affinity** rule; it would violate a **pod anti-affinity** constraint (e.g., "don't place two replicas of this service on the same node"). After filtering, you have a set of feasible nodes. If that set is empty, the pod stays in Pending — a state that means "the scheduler tried and failed to find a valid placement," not "the scheduler hasn't gotten around to it."

**Scoring** ranks the feasible nodes. Each node gets a score based on multiple weighted factors: how much the pod's resource request would balance utilization across the cluster (the **LeastRequestedPriority** or **MostRequestedPriority** strategies, depending on configuration), whether the node already has the container image cached (avoiding a pull), whether the pod has a **preferred** (soft) affinity for that node, and others. The highest-scoring node wins.

The critical detail: scheduling decisions are based on **requests**, not on actual utilization. If a node has 4 GiB of allocatable memory and pods with requests totaling 3.5 GiB are already scheduled there, the scheduler sees 512 MiB available — regardless of whether those pods are actually using 200 MiB or 3.5 GiB. This is the single most important mechanic to understand about resource management in an orchestrated cluster, and it's the one most commonly misunderstood.

## Requests, Limits, and the Overcommitment Trap

A **resource request** is a scheduling guarantee. It tells the scheduler: "this pod needs at least this much CPU and memory to be placed." The scheduler uses requests to make bin-packing decisions.

A **resource limit** is a runtime ceiling. It tells the container runtime: "if this pod tries to use more than this, throttle it (CPU) or kill it (memory)."

These are independent values. You can set a request of 256Mi of memory and a limit of 1Gi. The scheduler will place the pod on any node with 256Mi available in its accounting, but the pod can burst up to 1Gi at runtime if the memory is physically free on the node.

This gap between requests and limits is where **overcommitment** lives. If every pod on a node has a request of 256Mi but a limit of 1Gi, and every pod simultaneously bursts, the node runs out of physical memory. The kernel's OOM killer starts terminating processes. From the scheduler's perspective, the node had enough capacity. From the kernel's perspective, it didn't. The result: pods get killed on nodes that the scheduler thought were fine.

The practical failure mode looks like this: a team sets low requests to make scheduling easy (pods land quickly, bin packing is efficient) and high limits "just in case." The cluster runs well under normal load. During a traffic spike, multiple pods burst simultaneously, the node runs out of memory, and the OOM killer takes out pods semi-randomly — often including the ones handling the traffic spike. The operator sees pods restarting across the cluster and has no obvious explanation because the scheduler's resource accounting looks healthy.

The opposite failure is equally common: setting requests equal to limits (no overcommitment) on workloads that use a fraction of their requested resources. Nodes appear full to the scheduler while running at 15% actual utilization. The cluster is stable, but you're paying for four times the infrastructure you need.

## Service Discovery in a Dynamic Environment

On a single host, containers find each other by port mapping or a shared Docker network. In a cluster, the pod running your API server might be on node-7 right now and on node-12 after a reschedule. Its IP address changes every time it's re-created. Hard-coding addresses is impossible.

Orchestrators solve this with an abstraction layer between "the set of pods that implement a service" and "the network address that clients use to reach it." In Kubernetes, this is the **Service** object. A Service provides a stable virtual IP (the **ClusterIP**) and a DNS name. Behind that stable address, the Service maintains a dynamically updated list of pod IPs (**endpoints**) that match a label selector.

When a pod is created and passes its readiness checks, its IP is added to the endpoint list. When a pod is terminated or fails its readiness check, its IP is removed. Clients connect to the stable Service address and traffic is distributed across the current set of healthy pods, typically via iptables rules or IPVS on every node, updated by the **kube-proxy** component.

The non-obvious failure here is the gap between a pod starting and becoming ready. If your readiness probe is misconfigured — either too aggressive (passing before the app can handle traffic) or too slow (delaying for minutes) — the endpoint list doesn't reflect reality. Traffic arrives at pods that can't handle it, or healthy pods sit idle while the service appears degraded.

## Self-Healing: What Actually Happens During Failure

"The orchestrator restarts failed containers" is the surface description. The actual sequence during a node failure reveals more:

The kubelet on every node sends heartbeats to the control plane. When heartbeats from a node stop arriving, the **node controller** waits for a configurable timeout (the default in Kubernetes is 40 seconds of missed heartbeats before marking the node as `Unknown`, then another 5 minutes — the **pod-eviction-timeout** — before evicting pods). Only after this timeout does the control plane delete the pods assigned to the failed node, at which point the ReplicaSet controller notices replicas are missing and creates new pod objects, which the scheduler then places on surviving nodes.

The total elapsed time from node failure to replacement pods serving traffic can easily be six to seven minutes with default settings. During that window, the pods on the failed node are gone but haven't been replaced. If you had three replicas spread across three nodes and one node dies, you're running at two-thirds capacity for several minutes. If you had three replicas all on the same node — because you didn't configure anti-affinity rules and the scheduler's scoring happened to favor that placement — you're running at zero capacity.

This is why **pod disruption budgets**, **topology spread constraints**, and **anti-affinity rules** exist. They aren't advanced features for edge cases. They're the mechanisms that make self-healing actually work at the level most people assume it already works at by default.

## The Tradeoffs That Bite

The scheduler's design optimizes for generality — it handles stateless web servers, batch jobs, stateful databases, GPU workloads, and daemon processes through the same machinery. This generality has costs.

**Rescheduling doesn't mean zero-downtime.** Moving a workload from a failed node to a healthy one takes time. For stateless services behind a load balancer, this may be transparent. For a stateful workload with a persistent volume, the volume must be detached from the dead node and reattached to the new one — a process that can take minutes, especially in cloud environments where volume attachment is an API call with its own latency and failure modes.

**The scheduler is not aware of your application's behavior.** It knows about resource requests, labels, taints, and topology. It doesn't know that your service has a three-minute warmup period, or that two of your services compete for the same shared lock, or that scheduling a batch job next to a latency-sensitive service will cause cache eviction that degrades both. Everything the scheduler doesn't know has to be expressed through its constraint language (affinities, tolerations, topology constraints), or it won't be considered.

**Cluster autoscaling adds another feedback loop.** If no node has capacity for a pending pod, a cluster autoscaler can provision a new node. But provisioning a cloud VM takes one to five minutes. During that time, the pod is Pending, the scheduler is waiting, and the application is under-provisioned. The autoscaler's decision is also based on the same request-based accounting — it responds to scheduling failures, not to actual resource pressure. If your requests are artificially low, the autoscaler won't trigger even as nodes buckle under real load.

## The Mental Model

An orchestrator is a set of independent control loops driving observed state toward declared state. The scheduler is the loop that solves the placement problem, and it does so using a constraint-satisfaction approach: filter nodes that violate hard constraints, score the rest, pick the winner. Every scheduling decision is based on the resource model you declared (requests and limits), not the resources your application actually consumes.

This means the quality of your scheduling outcomes is a direct function of the accuracy of your resource declarations and the specificity of your placement constraints. The orchestrator will faithfully execute a bad declaration — placing all replicas on one node, overcommitting memory, or leaving pods Pending because requests don't match reality. The machinery is precise. The inputs are your responsibility.

When you look at a cluster and see pods in unexpected states — Pending, OOMKilled, CrashLoopBackOff on a node that looks underutilized — don't start with the application. Start with the scheduling model. Ask: what did the scheduler see when it made this decision? What did the resource accounting say? What constraints were in play? That's the reasoning path the mechanics support, and it resolves the majority of operational surprises.

## Key Takeaways

- **The scheduler solves a bin-packing problem using heuristics, not optimal solutions.** Placement decisions are good-enough approximations made quickly, which means edge cases in packing efficiency are expected, not bugs.

- **Scheduling decisions are based on resource requests, not actual utilization.** A node that appears idle to monitoring tools can appear full to the scheduler, and vice versa. Misaligned requests are the root cause of most scheduling surprises.

- **Requests and limits serve different purposes and are set independently.** Requests are for scheduling (where does the pod land). Limits are for runtime enforcement (what happens when the pod exceeds expectations). Setting them incorrectly in either direction — too low or too high — creates real operational problems.

- **Self-healing is not instant.** Default timeouts mean that recovery from a node failure takes minutes, not seconds. The gap between failure and recovery must be accounted for in your availability design through replica counts, anti-affinity rules, and pod disruption budgets.

- **Service discovery depends on the accuracy of readiness probes.** A stable Service IP is only useful if the endpoint list behind it reflects which pods can actually handle traffic. Misconfigured readiness probes are one of the most common causes of intermittent service errors in orchestrated environments.

- **Convergence toward desired state is eventual and multi-step.** No single controller handles a deployment end-to-end. Multiple independent loops act in sequence, and the total time from declaration to running workload is the sum of their individual latencies.

- **The scheduler can only optimize for what it's told.** Application-level concerns — warmup time, cache locality, resource contention patterns — must be expressed as scheduling constraints (affinities, tolerations, topology spread) or they will be invisible to placement decisions.

- **Overcommitment is a deliberate tradeoff, not a default you can ignore.** The gap between requests and limits determines how much risk you're carrying. Clusters that look efficient on paper can be fragile under load if overcommitment isn't managed intentionally.

[← Back to Home]({{ "/" | relative_url }})
