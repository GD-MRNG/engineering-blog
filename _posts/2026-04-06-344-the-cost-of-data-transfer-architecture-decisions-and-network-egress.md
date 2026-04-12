---
layout: post
title: "3.4.4 The Cost of Data Transfer: Architecture Decisions and Network Egress"
author: "Glenn Lum"
date:   2026-04-06 11:00:00 +0800
categories: journal
image: tier_3.jpg
tags: [Tier 3, Cross-Cutting Disciplines, Depth]
---

Most engineers can estimate their compute costs within a reasonable margin before a service launches. Storage costs are similarly predictable — you know roughly how much data you have and what kind of storage it sits on. Data transfer is different. It is the line item that shows up on a cloud bill and makes someone say, "Where did *that* come from?" The reason is not that data transfer pricing is hidden. The pricing pages are public. The reason is that data transfer costs are emergent — they arise from the interaction between your architecture and a pricing model that charges differently depending on which direction data moves and which boundaries it crosses. Understanding compute costs requires knowing how much you run. Understanding data transfer costs requires understanding the *topology* of how your system communicates.

The Level 1 post established that architectural decisions have cost profiles and that cost awareness belongs in design conversations. This post explains the specific mechanics of how data transfer pricing works, how architectural patterns interact with those mechanics, and where the real money hides.

## The Asymmetry: Why Ingress Is Free and Egress Is Not

Cloud providers do not charge symmetrically for data movement. Moving data *into* a cloud provider's network (ingress) is free or nearly free on every major provider. Moving data *out* of their network (egress) is where the charges appear. This is not arbitrary. Free ingress is an economic strategy: the easier it is to move your data in, the more data you store, the more services process it, and the harder it becomes to leave. Data has gravity. The more of it you have in one place, the more expensive it is to extract, and the more other workloads you co-locate alongside it to avoid paying for extraction.

This asymmetry means that the cost of data transfer is fundamentally directional. A system that pulls data in from external sources and processes it locally looks very different on the bill than a system that serves processed data outward to clients or to other networks. When you are evaluating an architecture, the question is not "how much data moves?" but "how much data moves *outward*, and across *which boundaries*?"

## The Topology of Charges

Not all egress is priced the same. Cloud providers define a hierarchy of network boundaries, and the cost of crossing each one is different. Understanding this hierarchy is the single most important thing for reasoning about data transfer costs.

**Internet egress** is the most expensive boundary. This is data leaving the cloud provider's network entirely and traveling to an end user, an on-premises data center, or another cloud provider. On AWS, this starts at roughly $0.09 per gigabyte for the first 10 TB per month, with declining tiers at higher volumes. Azure and GCP have comparable rates. At these prices, serving 100 TB per month of internet egress costs approximately $8,500 on AWS — and that is *just* the data transfer, independent of the compute, storage, or bandwidth required to generate it.

**Cross-region transfer** is the next tier. Data moving between regions within the same cloud provider — US East to EU West, for example — typically costs around $0.02 per gigabyte. This is cheaper than internet egress but far from trivial at scale. A database replication setup that synchronizes 500 GB per day across two regions generates roughly $300 per month in transfer costs alone. If you replicate across three regions, that number multiplies.

**Cross-availability-zone transfer** is the boundary that surprises people most often. Within a single region, cloud providers operate multiple availability zones (AZs) — physically separate data centers connected by low-latency links. Data moving between AZs within the same region is typically charged at around $0.01 per gigabyte in each direction (so $0.02 round trip). This seems trivial until you realize that every high-availability deployment distributes services across multiple AZs by design, which means every internal service-to-service call that crosses an AZ boundary incurs this charge.

**Same-AZ transfer** within a VPC is generally free. This is the one boundary that costs nothing to cross, and it is why service placement within AZs matters for cost even when it does not matter for latency or correctness.

Here is the hierarchy in summary form, because this is genuinely easier to parse as a comparison:

| Boundary | Approximate Cost (AWS) | When You Hit It |
|---|---|---|
| Same AZ, same VPC | Free | Services co-located in one AZ |
| Cross-AZ, same region | ~$0.01/GB per direction | HA deployments, multi-AZ load balancing |
| Cross-region | ~$0.02/GB | Multi-region replication, disaster recovery |
| Internet egress | ~$0.09/GB (first 10 TB) | APIs serving external clients, CDN origin pulls |
| Cross-cloud / on-prem | Internet egress rates | Hybrid architectures, multi-cloud strategies |

The practical consequence: your architecture is a map of network boundaries, and every boundary your data crosses on every request or replication cycle is a toll.

## How Architecture Decisions Create Egress

The charges above are static — they are the price list. What makes data transfer costs dynamic and hard to predict is how architectural decisions determine *how often* and *across which boundaries* your data moves.

### Multi-AZ Deployments and the Availability Tax

Running services across multiple availability zones is a best practice for fault tolerance. It is also a cost decision that is rarely modeled. If you have a service in AZ-a that calls a service in AZ-b, and the response payload averages 50 KB, and this happens 10 million times per day, you are generating approximately 500 GB of cross-AZ transfer per day. At $0.01/GB in each direction, that is $300 per month for a single service-to-service path — before considering that the originating request also crossed an AZ boundary, and the database query behind it might have crossed another.

A system with twenty microservices, each distributed across three AZs, with an average internal fan-out of four service calls per request, generates cross-AZ transfer on nearly every call chain. The individual per-call cost is invisible. The aggregate monthly cost is not.

### Service Placement and Data Locality

When a service reads from a database, the cost depends on whether the service and the database are in the same AZ. If your application runs in three AZs but your primary database is in one of them, two-thirds of your read traffic crosses an AZ boundary. Read replicas in each AZ eliminate this cost, but now you are paying for the replica instances and the replication traffic between them. This is a real tradeoff, not a free optimization. The question is whether the cross-AZ transfer cost exceeds the cost of running and replicating additional database instances. At low volumes, it does not. At high volumes, it often does.

### API Chattiness and Payload Design

The size and frequency of data exchanged between services directly determines egress volume. An API that returns a full 200 KB user object when the caller only needs three fields generates roughly 65 times more transfer than one that returns a 3 KB partial response. Across millions of calls, this is the difference between a rounding error and a significant line item.

This applies equally to external APIs. If your public API returns large payloads, your internet egress scales with your customer base and their request frequency. **Response shaping** — allowing clients to specify which fields they need, compressing responses, using pagination to limit payload size — is a latency optimization, a bandwidth optimization, *and* a cost optimization simultaneously.

### Observability as a Hidden Egress Source

Logs, metrics, and traces are data. If your observability pipeline ships logs to a third-party platform outside your cloud provider's network, every byte of log data is internet egress. A service that emits 10 GB of logs per day across a fleet — not unusual for a verbose application under load — generates 300 GB of internet egress per month just for logging. At $0.09/GB, that is $27 per month for one service. Across fifty services, it is $1,350 per month, and that is *only* the transfer cost, not the cost of the observability platform itself.

This is why many organizations use log aggregation and filtering within the cloud network before exporting, or choose observability platforms that offer ingestion endpoints within the same cloud provider's network via private connectivity, which converts internet egress into cheaper private transfer.

### Multi-Region and Multi-Cloud Architectures

Multi-region deployments multiply every data movement path by the number of regions. If your architecture requires consistent state across regions — whether through database replication, event streaming, or cache synchronization — the replication traffic is continuous and scales with write volume. A system writing 1 GB of new data per hour and replicating it to two additional regions pays for 2 GB per hour of cross-region transfer, continuously, which is roughly $30 per month. Scale that to 100 GB per hour of writes, and replication transfer alone is $3,000 per month.

Multi-cloud architectures face an even sharper version of this. Data moving between AWS and GCP, for example, is internet egress from both providers' perspectives. There is no discounted "peer" rate. Every byte crosses the most expensive boundary.

## Where This Breaks: Tradeoffs and Failure Modes

The most common failure mode is not a single bad decision — it is the accumulation of architecturally reasonable decisions that each carry a small, invisible transfer cost. No one designs a system thinking "I will generate 50 TB of cross-AZ traffic per month." It happens because each service is independently deployed across three AZs (correct for reliability), each service calls two or three downstream services (reasonable for separation of concerns), each call returns a moderately sized payload (reasonable for developer productivity), and the aggregate transfer volume is the *product* of all these factors, not the sum.

A concrete example: an organization migrated from a monolithic application to thirty microservices. The monolith processed everything in-memory within a single process on a single machine. The microservices architecture was better in every measurable dimension — deployability, team autonomy, fault isolation — except cost. The data that previously moved between functions via in-memory calls now moved between services via HTTP across AZ boundaries. Their cross-AZ data transfer bill went from effectively zero to $14,000 per month. Nothing was misconfigured. Every service was deployed according to best practices. The cost was a structural consequence of the architecture.

Another failure mode: **CDN origin pull amplification.** A CDN reduces internet egress by caching content at edge locations close to users. But every cache miss results in an origin pull — a request back to your origin server, which *is* internet egress. If your cache hit rate is 60%, you have only eliminated 60% of your egress. If your content is highly personalized or your cache TTLs are short, your CDN might reduce latency while barely reducing egress cost. Worse, some CDN configurations generate *more* total origin traffic than serving directly, because each edge location independently pulls content that a centralized setup could have served from cache once.

The third failure mode is **ignoring egress during vendor selection**. Choosing a managed service that runs outside your cloud provider's network — a hosted Elasticsearch cluster on a different cloud, a SaaS analytics tool that pulls data via public endpoints — means every byte exchanged is internet egress. The managed service might be cheaper than running the software yourself, but the total cost includes the transfer charges, which can exceed the service cost at high data volumes.

## The Mental Model

Think of your architecture as a physical layout of rooms connected by doors. Data is cargo being carried between rooms. Some doors are free to walk through — same AZ, same VPC. Some doors have a small toll — cross-AZ. Some have a large toll — cross-region or internet. You do not pay based on how much cargo exists. You pay based on how many tolled doors each piece of cargo passes through, how many times per second your system carries cargo through them, and how large each piece of cargo is.

When you evaluate an architecture for data transfer cost, you are drawing the map of doors, estimating the traffic through each one, and multiplying by the toll. The decisions that determine this cost — where you place services, how many boundaries replication crosses, how large your payloads are, whether your observability data stays internal or leaves the network — are all made long before the bill arrives. By the time you see the cost, the architecture is the cost.

## Key Takeaways

- **Cloud data transfer pricing is asymmetric by design**: ingress is free to attract data in; egress is charged to make it expensive to move data out. This asymmetry is an economic moat, not an operational detail.

- **Cross-AZ transfer is the most commonly underestimated cost**: at $0.01/GB per direction, it is invisible per-request but compounds aggressively in microservice architectures deployed across multiple availability zones.

- **Every service-to-service call that crosses an AZ boundary is a billable event**: multi-AZ high availability is a reliability best practice that carries a concrete, ongoing data transfer cost which should be modeled, not ignored.

- **Payload size is a cost lever, not just a performance lever**: reducing response payloads through field selection, compression, or pagination directly reduces egress volume across every network boundary.

- **Observability pipelines are data transfer pipelines**: shipping logs, metrics, and traces to external platforms generates internet egress that can rival the transfer costs of your production traffic.

- **Microservices architectures convert in-memory data movement into network data movement**: the same data that moved for free within a monolith's process now crosses network boundaries with per-gigabyte charges in a distributed system.

- **Multi-region and multi-cloud architectures multiply egress by the number of replication targets and boundary types**: model the continuous replication transfer cost before committing to these topologies, not after the first bill arrives.

- **The total egress cost of an architecture is the product of call frequency, payload size, and boundary cost across every communication path**: small, reasonable decisions at each service compound into large aggregate transfer bills because the costs multiply, they do not merely add.

[← Back to Home]({{ "/" | relative_url }})
