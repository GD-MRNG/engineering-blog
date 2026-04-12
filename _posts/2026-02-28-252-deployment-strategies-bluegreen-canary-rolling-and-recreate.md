---
layout: post
title: "2.5.2 Deployment Strategies: Blue/Green, Canary, Rolling, and Recreate"
author: "Glenn Lum"
date:   2026-02-28 11:00:00 +0800
categories: journal
image: tier_2.jpg
tags: [Tier 2,Core Lifecycle Stages,Depth]
---

Most engineers can whiteboard all four deployment strategies in under a minute. Boxes, arrows, a load balancer in the middle. The descriptions are simple enough to fit on a slide. But the moment a deployment goes wrong — a memory leak that only manifests under real load, a schema change that breaks serialization for the old version, a canary that looks healthy on latency but is silently corrupting data — the whiteboard version falls apart. The gap is not in knowing what these strategies are. It is in understanding what each strategy makes *possible* and *impossible* during the fifteen minutes between "we started the deploy" and "we're confident it's good." That intermediate state — where your system is between versions, partially old and partially new — is where deployment strategy actually matters, and it is the part most descriptions skip entirely.

## The State Between Versions

Every deployment strategy is a set of rules governing a transition between two states: the system running version N, and the system running version N+1. The differences between strategies come down to three questions about that transition. First, how many versions of the application are running simultaneously, and for how long? Second, how much production traffic is exposed to the new version at each stage? Third, when something goes wrong, what is the mechanical path back to the known-good state, and how long does that path take?

These three questions — **version coexistence**, **traffic exposure**, and **rollback mechanics** — are the axes along which every deployment strategy makes its tradeoffs. The rest of this post walks through each strategy along those axes.

## Recreate: The Only Strategy With No Coexistence

Recreate is the simplest strategy and the only one where two versions of your application never run at the same time. The process is: stop all instances of version N, then start all instances of version N+1. There is a window of downtime between those two steps. No traffic is served during the gap.

This simplicity has a real benefit that is easy to overlook. Because version N is fully stopped before version N+1 starts, you never have two versions hitting the same database, the same cache, or the same message queue simultaneously. If your deployment includes a breaking schema change — renaming a column, changing a serialization format, altering the structure of messages on a queue — Recreate is the only strategy where that change does not require backward compatibility. Every other strategy creates a window where both versions must coexist, and coexistence with a shared data layer means both versions must understand each other's data.

Rollback is a full redeployment. If version N+1 is broken, you run the same process in reverse: stop N+1, start N. That takes as long as a fresh deployment. There is no fast path.

Recreate is appropriate for batch processing systems, internal tools where brief downtime is acceptable, and any situation where the cost of maintaining backward compatibility between versions exceeds the cost of a few seconds of downtime.

## Rolling: Coexistence as the Default State

In a rolling update, instances are replaced incrementally. The orchestrator (typically Kubernetes, an ASG update policy, or a deployment coordinator) takes down a subset of version N instances and brings up version N+1 instances to replace them. This repeats until all instances are running N+1.

Two parameters control the shape of this process. In Kubernetes, they are `maxUnavailable` and `maxSurge`. **maxUnavailable** is how many old instances can be taken down before new ones are ready. **maxSurge** is how many extra instances beyond the desired count can exist during the rollout. A configuration of `maxSurge: 1, maxUnavailable: 0` means: bring up one new instance, wait until it's healthy, then take down one old instance. Repeat. This is the most conservative option — capacity never drops below the desired count — but it is the slowest rollout and requires spare capacity. A configuration of `maxSurge: 0, maxUnavailable: 1` means: kill one old instance, then start one new instance in its place. No extra infrastructure needed, but capacity temporarily drops.

The critical characteristic of rolling updates is that **both versions serve production traffic simultaneously for the entire duration of the rollout**. If you have 20 instances and replace one at a time, there is a long window where some users hit version N and some hit version N+1. You do not control which users hit which version. Load balancers distribute traffic to all healthy instances, so the split is roughly proportional to the instance count — after replacing 5 of 20, roughly 25% of traffic hits the new version.

This has direct implications. If version N+1 changes an API response format, some clients will get the old format and some will get the new format during the rollout. If version N+1 writes data in a new structure, version N instances may read that data and fail to parse it. The rolling update does not protect you from these incompatibilities — it exposes you to them for the full duration of the rollout.

Rollback in a rolling update is mechanically identical to the original deployment: another rolling update, this time replacing N+1 instances with N instances. It takes approximately the same amount of time as the original rollout. If your rollout takes ten minutes, your rollback also takes ten minutes. There is no instant rollback in this strategy.

Health checks are the mechanism that gates progress. The orchestrator will not continue replacing instances if newly created instances fail their readiness checks. This is your safety net, but it is only as good as your health check. A health check that returns 200 from a `/health` endpoint while the application is silently writing corrupt data to the database will not stop the rollout.

## Blue/Green: Atomic Traffic Switching

Blue/green maintains two complete environments. Blue runs version N. Green is provisioned with version N+1. Once green is fully running and passing health checks, traffic is switched from blue to green at the routing layer — a load balancer rule change, a service mesh configuration update, or a DNS record swap.

The critical property is that the **traffic switch is atomic from the user's perspective**. One moment, all traffic goes to blue. The next moment, all traffic goes to green. There is no extended period of mixed-version traffic. (DNS-based switching is the exception here: DNS TTLs mean that some clients will continue resolving to blue for minutes or hours after the switch. For this reason, most production blue/green implementations use load balancer or reverse proxy switching, not DNS.)

Rollback is the strategy's strongest feature. If green is broken, you switch traffic back to blue. Blue is still running, still warm, still has its connection pools and caches populated. The rollback is as fast as the traffic switch — typically seconds, sometimes less.

But there is an important constraint that the simple description obscures: **both environments usually share a database**. You do not run two production databases. This means that even though traffic switches atomically, the data layer does not. While green is being validated before the switch, any writes green makes hit the same database blue is using. After the switch, if you roll back to blue, blue must be able to read any data green wrote during its brief time serving traffic. The schema compatibility requirement that rolling updates have for the duration of the rollout, blue/green has for the period between green going live and blue being decommissioned.

The infrastructure cost is real. During the deployment window, you are running 2x the compute capacity. If your service runs 40 instances, you need 40 more for the green environment. Some organizations keep both environments permanently, using one as a hot standby. Others spin up the green environment on demand. The cost depends on how long the second environment exists and whether your infrastructure supports rapid provisioning.

**Connection draining** is a detail that matters operationally. When traffic switches from blue to green, in-flight requests on blue instances need to complete. The load balancer must stop sending *new* requests to blue while allowing *existing* requests to finish. If your application handles long-running requests — file uploads, streaming responses, WebSocket connections — the drain timeout must account for them. A 30-second drain timeout will kill a file upload that takes 60 seconds.

## Canary: Controlled Traffic Exposure

A canary deployment routes a small, deliberate percentage of production traffic to the new version while the majority continues going to the old version. You start at a low percentage — 1%, 5%, 10% — observe the new version's behavior under real traffic, and either increase the percentage or abort.

What distinguishes canary from the other strategies is **explicit control over traffic exposure**. In a rolling update, traffic exposure to the new version is a side effect of how many instances have been replaced — you control instance count, and traffic exposure follows implicitly. In a canary, traffic exposure is the primary control. You decide exactly how much production traffic the new version sees, independent of how many instances are running it.

This control is implemented at the routing layer. A service mesh like Istio or Linkerd can split traffic by weight: 95% to the stable version's pods, 5% to the canary's pods. A load balancer with weighted target groups can do the same. The implementation matters because it determines the granularity of control. Instance-count-based splitting (run 1 canary instance alongside 19 stable instances for a roughly 5% split) is coarse and inexact. Traffic-weight-based splitting at the mesh or proxy layer is precise but requires that infrastructure to exist.

The canary's value is proportional to your ability to observe it. Sending 5% of traffic to the new version and then checking it manually an hour later captures some value. Automated metric comparison — comparing the canary's error rate, latency p99, and saturation against the stable version's baseline over the same time window — captures far more. Tools like Flagger and Argo Rollouts automate this loop: deploy canary, shift small traffic percentage, compare metrics for a defined bake time, promote or abort automatically based on thresholds. This is **progressive delivery**, and it transforms canary from a manual process into an automated feedback loop.

A failure mode specific to canary deployments is **insufficient traffic volume**. If your service handles 100 requests per minute and you send 1% to the canary, the canary receives one request per minute. You cannot draw statistically meaningful conclusions about error rates or latency distributions from one request per minute over a ten-minute bake time. For low-traffic services, canary percentages must be higher, or bake times must be longer, or both. The alternative is that the canary phase gives you false confidence — the metrics looked fine, but the sample size was meaningless.

Rollback is fast for the traffic that was going to the canary: you set the canary weight to 0%, and all traffic returns to the stable version. The blast radius of a bad canary is explicitly bounded by the traffic percentage. A canary at 2% that serves errors for five minutes affects 2% of your traffic for five minutes. The same bad version deployed via a rolling update with no canary phase would affect an increasing percentage of traffic over the entire rollout window.

## Where These Strategies Break

**The shared data layer is the universal complication.** Every strategy except Recreate involves two versions of your application running simultaneously for some period. If both versions read and write to the same database, cache, or message queue, the data they produce and consume must be mutually intelligible. A rolling update with a migration that renames a column from `user_name` to `username` will cause the still-running old instances to throw errors the moment the migration executes. Blue/green does not save you — green's migration changes the schema that blue is still reading. Canary does not save you either. The expand-and-contract pattern described in the Level 1 post is not optional for these strategies; it is a structural requirement.

**Rollback speed is not the same as recovery speed.** Blue/green gives you instant rollback, but if the bad version wrote corrupt data to the database during the minutes it served traffic, rolling back the code does not roll back the data. You are now running the old code against a database that contains data the old code may not expect. Rollback restores the code path, not the system state. Data remediation is a separate, often manual, process.

**Health checks gate rollouts but do not validate correctness.** A rolling update or canary that checks `/health` and gets a 200 will proceed even if the application is returning wrong results, charging incorrect amounts, or silently dropping events. The sophistication of your deployment safety is capped by the sophistication of your observability. A canary with automated metric comparison against error rates, business metrics, and latency distributions is fundamentally safer than a canary that only checks health endpoints, which is in turn fundamentally safer than a rolling update with no canary phase at all.

**Long rollout times create extended vulnerability windows.** A rolling update across 200 instances, one at a time, with a 30-second readiness check per instance, takes 100 minutes. For those 100 minutes, your system is in a mixed-version state. Any version incompatibility bug has 100 minutes to cause damage before the rollout completes. Increasing `maxSurge` shortens the rollout but increases the resource cost. This is a direct, linear tradeoff.

## The Model to Carry Forward

The deployment strategy you choose determines three things: how long two versions of your code coexist in production, how much traffic the new version receives before you have confidence in it, and how fast you can get back to the last known-good state when confidence fails. These three properties — coexistence duration, traffic exposure curve, and rollback latency — are the complete framework for reasoning about any deployment strategy, including hybrid ones you construct yourself.

Recreate eliminates coexistence entirely at the cost of downtime. Rolling updates spread coexistence across the full rollout window with traffic exposure that grows as instances are replaced. Blue/green minimizes the coexistence window and gives instant rollback but requires double the infrastructure and does not solve data-layer compatibility. Canary gives you explicit control over traffic exposure and bounds the blast radius of failures but demands real observability to justify its complexity.

No strategy eliminates risk. Each one moves risk to a different place. Your job is to know where each strategy puts the risk and decide which location you can best tolerate and monitor.

## Key Takeaways

- Every deployment strategy except Recreate runs two versions simultaneously, which means every deployment involving a shared database, cache, or message queue requires backward-compatible data changes — not as a best practice, but as a correctness requirement.

- Rolling updates offer no explicit control over traffic exposure; the percentage of traffic hitting the new version is a function of how many instances have been replaced, and you cannot target it precisely.

- Blue/green rollback is instant for traffic routing but does not undo any data written by the bad version — rollback restores the code path, not the system state.

- Canary deployments are only as valuable as the metrics you compare; a canary with no automated metric analysis and insufficient traffic volume provides false confidence, not safety.

- Rollback in a rolling update is itself another rolling update, meaning it takes approximately the same time as the original deployment — there is no fast rollback path.

- The blast radius of a bad deployment is determined by how much traffic the new version receives before the problem is detected; canary bounds this explicitly, rolling update bounds it implicitly by rollout speed, and blue/green has no partial exposure (it is all or nothing).

- DNS-based traffic switching in blue/green deployments is not atomic due to TTL caching; production implementations should use load balancer or proxy-level switching for reliable cutover and rollback.

- The safety ceiling of any deployment strategy is set by your observability, not by the strategy itself — a health check that returns 200 while the application serves incorrect results will not prevent a bad rollout from completing.

[← Back to Home]({{ "/" | relative_url }})
